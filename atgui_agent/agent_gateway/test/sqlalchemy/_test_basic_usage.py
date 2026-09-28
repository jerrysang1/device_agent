"""
test/sqlalchemy/_test_basic_usage.py —— SQLAlchemy 教学标准姿势（同步版）

和生产代码（async + MySQL）不同，这里用最经典的：
    创建引擎 → 创建表 → Session 插入 → commit
适合入门理解 ORM 三步走。

运行：
    cd F:\\AAA求职相关\\device_agent
    .venv\\Scripts\\python.exe -m agent_gateway.test.sqlalchemy._test_basic_usage
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# 复用项目里已定义的 User 模型（id / name / ...）
from agent_gateway.infrastructure.database import Base, User


def main():
    # 1. 创建引擎（sqlite:/// 内存库，跑完即丢，适合教学演示）
    engine = create_engine("sqlite:///", echo=True)

    # 2. 创建表（把 User 映射的 users 表建出来）
    Base.metadata.create_all(engine)

    # 3. 使用上下文管理器方式使用 session 对象
    with Session(engine) as session:
        # 3.1 构造三个用户对象（此时还没进库）
        spongebob = User(id="u1001", name="海绵宝宝")
        sandy = User(id="u1002", name="珊迪")
        patrick = User(id="u1003", name="派大星")

        # 3.2 批量加入 session（只加到「待写入」列表）
        session.add_all([spongebob, sandy, patrick])
        session.commit()  # 不会自动提交（需要手动）

    # 4. 再开一个 session 查回来，验证确实写进去了
    with Session(engine) as session:
        users = session.execute(select(User)).scalars().all()
        for u in users:
            print(f"读到用户: {u.id} / {u.name}")


# 测试入口
if __name__ == "__main__":
    main()
