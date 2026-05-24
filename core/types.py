from __future__ import annotations

"""类型系统 — 节点输入/输出数据类型声明。"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union


class DataType(Enum):
    """节点插口的数据类型。"""
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    DICT = "dict"
    OBJECT = "object"
    ANY = "any"


TYPE_DEFAULTS: Dict[DataType, Any] = {
    DataType.STRING: "",
    DataType.INT: 0,
    DataType.FLOAT: 0.0,
    DataType.BOOL: False,
    DataType.LIST: [],
    DataType.DICT: {},
    DataType.OBJECT: "",
    DataType.ANY: None,
}


class SocketDirection(Enum):
    INPUT = "input"
    OUTPUT = "output"


class SocketDef:
    """插口定义"""

    def __init__(
        self,
        name: str,
        data_type: DataType = DataType.ANY,
        direction: SocketDirection = SocketDirection.INPUT,
        default_value: Any = None,
        description: str = "",
        label: str = "",
        visible_when: str = "",
    ) -> None:
        self.name = name
        self.data_type = data_type
        self.direction = direction
        self.default_value = (
            default_value if default_value is not None
            else TYPE_DEFAULTS.get(data_type)
        )
        self.description = description
        self.label = label or name
        self.visible_when = visible_when

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type.value,
            "direction": self.direction.value,
            "default_value": self.default_value,
            "description": self.description,
            "label": self.label,
            "visible_when": self.visible_when,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SocketDef":
        return cls(
            name=data["name"],
            data_type=DataType(data.get("data_type", "any")),
            direction=SocketDirection(data.get("direction", "input")),
            default_value=data.get("default_value"),
            description=data.get("description", ""),
            label=data.get("label", ""),
            visible_when=data.get("visible_when", ""),
        )

    def __repr__(self) -> str:
        return f"<{self.direction.value}:{self.name}({self.data_type.value})>"


TYPE_COLORS: Dict[DataType, str] = {
    DataType.STRING: "#4CAF50",
    DataType.INT: "#2196F3",
    DataType.FLOAT: "#00BCD4",
    DataType.BOOL: "#FF9800",
    DataType.LIST: "#9C27B0",
    DataType.DICT: "#E91E63",
    DataType.OBJECT: "#607D8B",
    DataType.ANY: "#9E9E9E",
}
