from __future__ import annotations

"""
节点数据模型 — 节点、插口、连接的纯数据定义。
"""


import uuid
from typing import Any, Dict, List, Optional

from .types import DataType, SocketDef, SocketDirection


class Node:
    """
    单个节点。
    - 基础节点：含 code（Python 方法）
    - 组合节点：含 sub_graph（内部节点图）
    """

    def __init__(
        self,
        name: str = "NewNode",
        category: str = "通用",
        node_id: Optional[str] = None,
        exec_mode: str = "code",
    ) -> None:
        self.node_id: str = node_id or uuid.uuid4().hex[:12]
        self.name: str = name
        self.category: str = category
        self.code: str = ""
        self.color: str = "#3A3A3A"
        self.exec_mode: str = exec_mode  # "code"=直执行, "ui"=弹UI窗

        # 插口
        self.inputs: List[SocketDef] = []
        self.outputs: List[SocketDef] = []

        # 组合节点专用：内部子图
        self.is_compound: bool = False
        self.sub_graph: Optional[Dict[str, Any]] = None

        # UI 位置
        self.pos_x: float = 0.0
        self.pos_y: float = 0.0

    def add_input(self, name: str, data_type: DataType = DataType.ANY,
                  default: Any = None, desc: str = "") -> SocketDef:
        sock = SocketDef(name, data_type, SocketDirection.INPUT, default, desc)
        self.inputs.append(sock)
        return sock

    def add_output(self, name: str, data_type: DataType = DataType.ANY,
                   description: str = "") -> SocketDef:
        sock = SocketDef(name, data_type, SocketDirection.OUTPUT, description=description)
        self.outputs.append(sock)
        return sock

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "node_id": self.node_id,
            "name": self.name,
            "category": self.category,
            "code": self.code,
            "color": self.color,
            "exec_mode": self.exec_mode,
            "inputs": [s.to_dict() for s in self.inputs],
            "outputs": [s.to_dict() for s in self.outputs],
            "is_compound": self.is_compound,
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
        }
        if self.is_compound and self.sub_graph:
            data["sub_graph"] = self.sub_graph
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Node:
        node = cls(
            name=data.get("name", "NewNode"),
            category=data.get("category", "通用"),
            node_id=data.get("node_id"),
        )
        node.code = data.get("code", "")
        node.color = data.get("color", "#3A3A3A")
        node.exec_mode = data.get("exec_mode", "code")
        node.is_compound = data.get("is_compound", False)
        node.sub_graph = data.get("sub_graph")
        node.pos_x = data.get("pos_x", 0.0)
        node.pos_y = data.get("pos_y", 0.0)

        for s_data in data.get("inputs", []):
            node.inputs.append(SocketDef.from_dict(s_data))
        for s_data in data.get("outputs", []):
            node.outputs.append(SocketDef.from_dict(s_data))
        return node

    def __repr__(self) -> str:
        return f"<Node:{self.name}[{self.node_id[:8]}]>"


class Connection:
    """两个节点之间的连线。"""

    def __init__(
        self,
        source_node_id: str,
        source_socket: str,
        target_node_id: str,
        target_socket: str,
        conn_id: Optional[str] = None,
    ) -> None:
        self.conn_id: str = conn_id or uuid.uuid4().hex[:12]
        self.source_node_id = source_node_id
        self.source_socket = source_socket
        self.target_node_id = target_node_id
        self.target_socket = target_socket

    def to_dict(self) -> Dict[str, str]:
        return {
            "conn_id": self.conn_id,
            "source_node_id": self.source_node_id,
            "source_socket": self.source_socket,
            "target_node_id": self.target_node_id,
            "target_socket": self.target_socket,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> Connection:
        return cls(
            source_node_id=data["source_node_id"],
            source_socket=data["source_socket"],
            target_node_id=data["target_node_id"],
            target_socket=data["target_socket"],
            conn_id=data.get("conn_id"),
        )

    def __repr__(self) -> str:
        return (f"<Conn {self.source_node_id[:6]}.{self.source_socket}"
                f" → {self.target_node_id[:6]}.{self.target_socket}>")
