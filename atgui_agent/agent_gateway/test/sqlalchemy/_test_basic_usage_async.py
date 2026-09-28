"""
test/sqlalchemy/_test_basic_usage_async.py —— SQLAlchemy 教学标准姿势（异步版）

三步走换成 async 写法：
    创建异步引擎 → 创建表 → AsyncSession 插入 → commit
适合理解「生产环境 FastAPI 为什么用异步 ORM」。

运行：
    cd F:\\AAA求职相关\\device_agent
    .venv\\Scripts\\python.exe -m agent_gateway.test.sqlalchemy._test_basic_usage_async
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 复用项目里已定义的 User 模型（id / name / ...）
from agent_gateway.infrastructure.database import Base, User


async def main():
    # 1. 创建异步引擎（aiosqlite，内存库，跑完即丢，适合教学演示）
    #    生产环境把 url 换成 mysql+aiomysql://... 即可，代码写法不变
    engine = create_async_engine("sqlite+aiosqlite:///", echo=True)

    # 2. 创建表（异步引擎里建表，要先 run_sync 同步执行）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 3. 创建异步会话工厂（AsyncSession 的「上下文管理器」）  expire_on_commit：提交之后变量是否保留（False 不自动过期）
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 4. 使用异步 session 插入数据
    async with session_factory() as session:
        # 4.1 构造三个用户对象（此时还没进库）
        spongebob = User(id="u1001", name="海绵宝宝")
        sandy = User(id="u1002", name="珊迪")
        patrick = User(id="u1003", name="派大星")

        # 4.2 批量加入 session（只加到「待写入」列表）
        session.add_all([spongebob, sandy, patrick])
        await session.commit()  # 不会自动提交（需要手动 await）

    # 5. 再开一个 session 查回来，验证确实写进去了
    async with session_factory() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        for u in users:
            print(f"读到用户: {u.id} / {u.name}")

    # 6. 关闭引擎，释放资源
    await engine.dispose()


# 测试入口
if __name__ == "__main__":
    asyncio.run(main())
