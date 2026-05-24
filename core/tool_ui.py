from __future__ import annotations
"""
工具 UI 规格 — 从节点图自动推导 UI 面板的输入/输出规格。
通用层：不依赖 Qt，纯数据推导。
"""

from typing import Any, Dict, List, Optional

from .node import Node
from .node_graph import NodeGraph
from .types import DataType


# ====== 数据结构 ======

class UiInput:
    """UI 面板上的一个输入控件描述。"""

    def __init__(
        self,
        name: str,              # UI 显示名称
        node_id: str,           # 所属节点 ID
        port_name: str,         # 目标端口名
        data_type: DataType = DataType.ANY,
        default: Any = None,
        description: str = "",
        widget_type: str = "line_edit",  # 控件类型
        order: int = 0,         # 显示顺序
    ) -> None:
        self.name = name
        self.node_id = node_id
        self.port_name = port_name
        self.data_type = data_type
        self.default = default
        self.description = description
        self.widget_type = widget_type
        self.order = order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "node_id": self.node_id,
            "port_name": self.port_name,
            "data_type": self.data_type.value,
            "default": self.default,
            "description": self.description,
            "widget_type": self.widget_type,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UiInput:
        return cls(
            name=data["name"],
            node_id=data["node_id"],
            port_name=data["port_name"],
            data_type=DataType(data.get("data_type", "any")),
            default=data.get("default"),
            description=data.get("description", ""),
            widget_type=data.get("widget_type", "line_edit"),
            order=data.get("order", 0),
        )


class UiOutput:
    """UI 面板上的一个输出结果显示描述。"""

    def __init__(
        self,
        name: str,
        node_id: str,
        port_name: str,
        data_type: DataType = DataType.ANY,
        description: str = "",
        order: int = 0,
    ) -> None:
        self.name = name
        self.node_id = node_id
        self.port_name = port_name
        self.data_type = data_type
        self.description = description
        self.order = order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "node_id": self.node_id,
            "port_name": self.port_name,
            "data_type": self.data_type.value,
            "description": self.description,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UiOutput:
        return cls(
            name=data["name"],
            node_id=data["node_id"],
            port_name=data["port_name"],
            data_type=DataType(data.get("data_type", "any")),
            description=data.get("description", ""),
            order=data.get("order", 0),
        )


class UiSpec:
    """完整的 UI 面板规格。"""

    def __init__(
        self,
        inputs: Optional[List[UiInput]] = None,
        outputs: Optional[List[UiOutput]] = None,
    ) -> None:
        self.inputs: List[UiInput] = inputs or []
        self.outputs: List[UiOutput] = outputs or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inputs": [i.to_dict() for i in sorted(self.inputs, key=lambda x: x.order)],
            "outputs": [o.to_dict() for o in sorted(self.outputs, key=lambda x: x.order)],
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> UiSpec:
        if not data:
            return cls()
        return cls(
            inputs=[UiInput.from_dict(i) for i in data.get("inputs", [])],
            outputs=[UiOutput.from_dict(o) for o in data.get("outputs", [])],
        )

    def is_empty(self) -> bool:
        return not self.inputs and not self.outputs


# ====== DataType → 控件类型映射（可扩展） ======

WIDGET_TYPE_MAP: Dict[DataType, str] = {
    DataType.STRING: "line_edit",
    DataType.INT: "spin_box",
    DataType.FLOAT: "double_spin_box",
    DataType.BOOL: "check_box",
    DataType.LIST: "plain_text_edit",
    DataType.DICT: "plain_text_edit",
    DataType.OBJECT: "line_edit",
    DataType.ANY: "line_edit",
}


def get_widget_type(data_type: DataType, port_name: str = "") -> str:
    """根据数据类型和端口名推断控件类型。可被外部扩展覆盖。"""
    name_lower = port_name.lower()
    if "file" in name_lower or "路径" in name_lower:
        return "file_browser"
    if "color" in name_lower or "颜色" in name_lower:
        return "color_picker"
    if "multi" in name_lower or "多行" in name_lower or name_lower == "text":
        return "plain_text_edit"
    return WIDGET_TYPE_MAP.get(data_type, "line_edit")


# ====== 端口名美化 ======

CLEAN_NAME_MAP: Dict[str, str] = {
    "input": "输入", "output": "输出", "text": "文本",
    "value": "值", "name": "名称", "path": "路径",
    "count": "数量", "index": "索引", "result": "结果",
    "message": "消息", "data": "数据", "prefix": "前缀",
    "suffix": "后缀", "search": "搜索", "replace": "替换",
    "pattern": "模式", "source": "源", "target": "目标",
    "enable": "启用", "disable": "禁用",
}


def _clean_port_name(name: str) -> str:
    """将端口名转为友好中文显示名。"""
    return CLEAN_NAME_MAP.get(name, name)


SKIP_INPUT_PORTS = {"run", "exec", "execute", "trigger"}
SKIP_OUTPUT_PORTS = {"run", "exec", "execute"}


# ====== 推导逻辑 ======

def derive_ui_spec(graph: NodeGraph) -> UiSpec:
    """
    从节点图自动推导 UI 面板规格。
    
    规则：
    1. 输入：所有没有连线接通的输入端口中，排除 run/exec 类端口
    2. 输出：所有没有连线接通的输出端口中，排除 run/exec 类端口
    3. 数据类型 × 端口名 → 控件类型
    """
    inputs: List[UiInput] = []
    outputs: List[UiOutput] = []

    # 收集所有被连线占用的端口
    connected_targets: set = set()
    connected_sources: set = set()

    for conn in graph.connections.values():
        connected_sources.add((conn.source_node_id, conn.source_socket))
        connected_targets.add((conn.target_node_id, conn.target_socket))

    for node_id, node in graph.nodes.items():
        if node.is_start_node:
            continue

        # ---- 输入端口 ----
        for sock in node.inputs:
            if sock.name in SKIP_INPUT_PORTS:
                continue
            if (node_id, sock.name) in connected_targets:
                continue

            widget_type = get_widget_type(sock.data_type, sock.name)
            display_name = _clean_port_name(sock.name)
            inputs.append(UiInput(
                name=display_name,
                node_id=node_id,
                port_name=sock.name,
                data_type=sock.data_type,
                default=sock.default_value,
                description=sock.description or display_name,
                widget_type=widget_type,
                order=len(inputs),
            ))

        # ---- 输出端口 ----
        for sock in node.outputs:
            if sock.name in SKIP_OUTPUT_PORTS:
                continue
            if (node_id, sock.name) in connected_sources:
                continue

            display_name = _clean_port_name(sock.name)
            outputs.append(UiOutput(
                name=display_name,
                node_id=node_id,
                port_name=sock.name,
                data_type=sock.data_type,
                description=sock.description or display_name,
                order=len(outputs),
            ))

    return UiSpec(inputs=inputs, outputs=outputs)
