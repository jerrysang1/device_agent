"""数据库基础设施：异步引擎、会话管理与 ORM 模型定义。

职责：
    1. 创建并缓存 SQLAlchemy 异步引擎。
    2. 提供自动提交/回滚的会话上下文管理器。
    3. 定义 User / ChatMessage / AgentTask 三个业务表。

设计要点：
    1. 配置统一走 get_settings()，本模块不读 .env。
    2. get_session() 是事务壳：异常回滚、正常提交、无论如何都归还连接。
    3. 业务代码不要直接持有引擎，一律通过 get_session() 拿会话。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agent_gateway.config.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。

    继承它的模型会在 init_database() 时被 create_all 一次建出表。
    """


class User(Base):
    """用户表：会话归属，对应前端 sender_id / customer_id。

    设备与工单主数据仍在中台，本库只存用户档案与对话归属。
    主键直接用业务号（u1001），便于与中台 customer_id 对齐。

    Attributes:
        id: 用户ID，如 u1001。
        name: 用户昵称。
        phone: 联系电话，转人工时使用，可为空。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户ID，如 u1001")
    name: Mapped[str] = mapped_column(String(64), default="", comment="用户昵称")
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="联系电话")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )


class ChatMessage(Base):
    """对话消息表：支撑 GET /api/chat/history 按用户拉取历史。

    Attributes:
        id: 自增主键。
        sender_id: 归属用户ID，外键 users.id。
        role: 角色，user / bot / divider。
        message_type: 消息类型，text / object。
        content: 文本内容。
        payload: 结构化载荷 JSON（设备/工单对象、建议词等）。
        created_at: 创建时间，排序用。
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="消息ID")
    sender_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    role: Mapped[str] = mapped_column(String(16), comment="角色：user/bot/divider")
    message_type: Mapped[str] = mapped_column(
        String(16), default="text", comment="消息类型：text/object"
    )
    content: Mapped[str] = mapped_column(String(4096), default="", comment="文本内容")
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="结构化载荷 JSON"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, comment="创建时间"
    )


class AgentTask(Base):
    """任务状态表：支撑多轮报修与中断恢复。

    状态机：
        NEW -> COLLECTING_SLOTS -> WAITING_CONFIRMATION -> EXECUTING -> COMPLETED
        旁路：FAILED / TRANSFERRED / PAUSED

    Attributes:
        id: 自增主键。
        sender_id: 归属用户ID，外键 users.id。
        task_type: 任务类型，如 create_service_ticket。
        status: 当前状态。
        slots: 已收集槽位 JSON。
        paused_context: PAUSED 时保存的原任务上下文。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="任务ID")
    sender_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    task_type: Mapped[str] = mapped_column(String(64), comment="任务类型标识")
    status: Mapped[str] = mapped_column(
        String(32), default="NEW", index=True,
        comment="NEW/COLLECTING_SLOTS/WAITING_CONFIRMATION/EXECUTING/COMPLETED/FAILED/TRANSFERRED/PAUSED",
    )
    slots: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="槽位 JSON"
    )
    paused_context: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="PAUSED 时保存的原任务上下文"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )


_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """创建并缓存异步 SQLAlchemy 引擎。

    Returns:
        AsyncEngine: 已绑定 DATABASE_URL 的异步引擎。

    Raises:
        RuntimeError: 未配置 DATABASE_URL。
    """
    global _engine
    # 1. 单例已存在直接复用，close_database() 会把它置 None
    if _engine is not None:
        return _engine

    # 2. 读取连接串
    database_url = get_settings().database.url_str()
    if not database_url:
        raise RuntimeError(
            "缺少 DATABASE_URL。请在 flow_config/.env 中配置后再启动。"
        )

    # 3. 创建引擎
    #    pool_pre_ping：取连接前探活，避免 MySQL wait_timeout 断连后报错
    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """创建并缓存异步会话工厂。

    Returns:
        async_sessionmaker[AsyncSession]: 用于创建 AsyncSession 的工厂。
    """
    global _session_factory
    # 1. 已有工厂直接返回
    if _session_factory is not None:
        return _session_factory

    # 2. expire_on_commit=False：提交后对象属性仍可读
    _session_factory = async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取一个自动提交/回滚的异步会话。

    用法::

        async with get_session() as session:
            await session.execute(...)

    步骤：
        1. 创建会话并 yield 给调用方。
        2. 业务正常结束则提交事务。
        3. 出现异常必须回滚，避免脏数据写进库。
        4. finally 中关闭会话，归还连接池。

    Yields:
        AsyncSession: 可执行 SQL 的会话对象。
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def close_database() -> None:
    """关闭引擎并释放数据库连接池。

    建议在应用关停钩子里调用一次。

    Returns:
        None
    """
    global _engine, _session_factory
    # 1. 引擎存在则销毁
    if _engine is not None:
        await _engine.dispose()
    # 2. 单例置空，下次调用重新创建
    _engine = None
    _session_factory = None


async def init_database() -> None:
    """初始化数据库：连接探活 + 按需建表。

    步骤：
        1. 执行 SELECT 1，确认 DATABASE_URL 可连。
        2. create_all 建出 Base 子类映射的表，已存在则跳过。

    Returns:
        None
    """
    # 1. 探活
    async with get_session() as session:
        await session.execute(text("SELECT 1"))

    # 2. 建表
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    """冒烟测试：初始化 → 写入/查询 User → 关闭连接池。"""

    async def _smoke_test() -> None:
        """执行一次完整的建表与读写验证。"""
        from sqlalchemy import select

        # 1. 初始化（探活 + 建表）
        print("[1] 初始化数据库 ...")
        await init_database()
        print("[2] 初始化成功（连接可用，users/chat_messages/agent_tasks 表已就绪）")

        try:
            async with get_session() as session:
                # 2.1 幂等查询
                user = await session.get(User, "u1001")
                if user is None:
                    # 2.2 不存在则插入演示用户
                    user = User(id="u1001", name="演示用户")
                    session.add(user)
                    await session.flush()
                    print(f"[3] 新建用户: id={user.id}, name={user.name}")
                else:
                    print(f"[3] 用户已存在: id={user.id}, name={user.name}")

                # 2.3 select 再查一遍，走完整查询链路
                result = await session.execute(select(User).where(User.id == "u1001"))
                row = result.scalar_one()
                print(f"[4] 查询成功: {row.id} / {row.name}")
        finally:
            await close_database()
            print("[5] 数据库连接池已关闭")

    asyncio.run(_smoke_test())
