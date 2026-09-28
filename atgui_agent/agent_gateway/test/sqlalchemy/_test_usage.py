"""
test/sqlalchemy/_test_usage.py —— 数据库建表/读写验证脚本

职责：
    1. 调用 init_database() 建表到 MySQL 的 device_service 库
    2. 查 device_service 库的 information_schema，确认 users / chat_messages / agent_tasks 是否存在
    3. 在 device_service 库里写入一条 User 再读回来，验证读写通路

连接目标（见 flow_config/.env 的 DATABASE_URL）：
    mysql+aiomysql://...@192.168.10.15:3306/device_service

运行：
    cd F:\\AAA求职相关\\device_agent
    .venv\\Scripts\\python.exe -m agent_gateway.test.sqlalchemy._test_usage
"""

import asyncio

from sqlalchemy import select, text

from agent_gateway.infrastructure.database import (
    AgentTask,
    ChatMessage,
    User,
    close_database,
    get_session,
    init_database,
)


async def _check_tables() -> list[str]:
    """
    查询 MySQL，确认三张业务表在 device_service 库中是否存在
    Args：
        无
    Returns:
        List[str]: device_service 库中已存在的表名列表
    """
    # 1. 在 device_service 库（当前 DATABASE()）的 information_schema.tables 里查表名
    sql = text(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name IN ('users', 'chat_messages', 'agent_tasks')
        """
    )
    async with get_session() as session:
        result = await session.execute(sql)
        # 2. 取出所有命中的表名（兼容大小写）
        names = [row[0] for row in result.all()]
    return names


async def _test_user_crud() -> str:
    """
    User 读写验证：插入 u1001（已存在则跳过）→ 查回来
    Args：
        无
    Returns:
        str: 读到的用户描述，如 "u1001 / 演示用户"
    """
    async with get_session() as session:
        # 1. 先查，保证测试可重复执行（幂等）
        user = await session.get(User, "u1002")
        if user is None:
            # 2. 不存在则新建演示用户
            user = User(id="u1002", name="演示用户")
            session.add(user)
            await session.flush()
        # 3. 用 select 再查一遍，走完整查询链路
        result = await session.execute(select(User).where(User.id == "u1002"))
        row = result.scalar_one()
        return f"{row.id} / {row.name}"


async def _test_task_insert() -> str:
    """
    AgentTask 写入验证：插入一条 NEW 状态任务
    Args：
        无
    Returns:
        str: 任务描述，如 "task_id=1 status=NEW"
    """
    async with get_session() as session:
        # 1. 新建任务（收集槽位阶段）
        task = AgentTask(
            sender_id="u1001",
            task_type="create_service_ticket",
            status="NEW",
            slots={"device_id": "DEV-2026-0001"},
        )
        session.add(task)
        await session.flush()
        # 2. 读回来确认自增主键与状态
        return f"task_id={task.id} status={task.status}"


async def main() -> None:
    """
    测试主流程
    步骤：
        1. init_database：连接 MySQL 的 device_service 库 + 建表
        2. 查 device_service 库的 information_schema，确认三张表是否已创建
        3. 在 device_service 库里跑 User / AgentTask 读写各一次
        4. finally 里 close_database()
    """
    try:
        # 1. 建表（写入 device_service 库）
        print("[1] 正在连接 MySQL device_service 库并建表 ...")
        await init_database()
        print("[2] init_database() 完成")

        # 2. 核对 device_service 库中表是否存在
        tables = await _check_tables()
        expected = {"users", "chat_messages", "agent_tasks"}
        found = expected.intersection({t.lower() for t in tables})
        print(f"[3] device_service 库中实际存在的表: {sorted(found)}")
        if found != expected:
            missing = expected - found
            print(f"[!] 仍缺少表: {sorted(missing)}")
        else:
            print("[3] 三张表全部就绪 ✓")

        # 3. User 读写
        user_desc = await _test_user_crud()
        print(f"[4] User 读写: {user_desc}")

        # 4. AgentTask 写入
        task_desc = await _test_task_insert()
        print(f"[5] AgentTask 写入: {task_desc}")

        print("\n全部通过：表已建到 MySQL device_service 库，读写正常。")
    finally:
        # 5. 释放连接池
        await close_database()
        print("[6] 数据库连接池已关闭")


if __name__ == "__main__":
    asyncio.run(main())
