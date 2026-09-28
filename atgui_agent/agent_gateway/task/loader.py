"""流程加载门面：对齐「YAML → 可展开对象树」的调试/教学用法。

真实校验逻辑在 task.models.load_catalog；
本模块只提供更顺手的 load_many 入口，方便在 IDE 调试器里展开 Flow。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Union

from agent_gateway.task.models import (
    FlowCatalog,
    SYSTEM_FLOWS_PATH,
    USER_FLOWS_PATH,
    load_catalog,
)

PathLike = Union[str, Path]


class FlowLoader:
    """把 flow_config 下的 YAML 加载成 FlowCatalog（可调试对象树）。"""

    def load_many(self, paths: Iterable[PathLike] | None = None) -> FlowCatalog:
        """加载业务流 + 系统流。

        Args:
            paths: 可选 [user_flows.yml, system_flows.yml]；缺省用项目默认路径。

        Returns:
            FlowCatalog: 含 slots / flows / system_flows。

        Raises:
            ValueError: YAML 结构或引用不合法。
        """
        if paths is None:
            return load_catalog()
        path_list = [Path(p) for p in paths]
        if len(path_list) != 2:
            raise ValueError("load_many 需要 [user_flows.yml, system_flows.yml] 两个路径")
        return load_catalog(user_path=path_list[0], system_path=path_list[1])


if __name__ == "__main__":

    """在 PyCharm 里 Debug 本文件，Variables 窗口即可展开对象树。
        loader = FlowLoader()
        flows_list = loader.load_many([user_flow_path, system_flow_path])
        print(flows_list)
    """
    from pathlib import Path

    # agent_gateway/task/loader.py → 上跳 2 级到 atgui_agent/
    base_path = Path(__file__).resolve().parents[2]
    user_flow_path = base_path / "flow_config" / "user_flows.yml"
    system_flow_path = base_path / "flow_config" / "system_flows.yml"

    loader = FlowLoader()
    # ↓↓↓ 在这一行打断点，Debug 运行后在 Variables 里展开 catalog.flows / steps
    catalog = loader.load_many([user_flow_path, system_flow_path])

    print("=== FlowCatalog ===")
    print(f"slots        : {sorted(catalog.slots)}")
    print(f"user flows   : {sorted(catalog.flows)}")
    print(f"system flows : {sorted(catalog.system_flows)}")

    print("\n=== 业务流程步骤树（可对照 Variables 展开）===")
    for flow_id, flow in catalog.flows.items():
        print(f"\n[{flow_id}] {flow.name}  entry={flow.entry}")
        for step in flow.steps:
            print(f"  - {step.id}: {type(step).__name__}  next={step.next}")

    print("\n=== 系统流程 ===")
    for flow_id, flow in catalog.system_flows.items():
        kinds = ",".join(type(s).__name__ for s in flow.steps)
        print(f"  [{flow_id}] type={flow.context_type}  steps=[{kinds}]")
