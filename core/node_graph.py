"""
节点图数据 — 管理 Nodes + Connections，提供 JSON 序列化。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .node import Node, Connection


class NodeGraph:
    """节点图 — 管理一组节点及其连线。"""

    def __init__(self, name: str = "Untitled") -> None:
        self.name: str = name
        self.nodes: Dict[str, Node] = {}      # node_id → Node
        self.connections: Dict[str, Connection] = {}  # conn_id → Connection

    def add_node(self, node: Node) -> Node:
        self.nodes[node.node_id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        # 删除连到该节点的所有连线
        to_remove = [
            cid for cid, c in self.connections.items()
            if c.source_node_id == node_id or c.target_node_id == node_id
        ]
        for cid in to_remove:
            del self.connections[cid]
        self.nodes.pop(node_id, None)

    def add_connection(self, conn: Connection) -> Connection:
        # 简单校验：源和目标不能是同一个节点
        if conn.source_node_id == conn.target_node_id:
            raise ValueError("不能自连")
        self.connections[conn.conn_id] = conn
        return conn

    def remove_connection(self, conn_id: str) -> None:
        self.connections.pop(conn_id, None)

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def get_connections_for_node(self, node_id: str) -> List[Connection]:
        return [
            c for c in self.connections.values()
            if c.source_node_id == node_id or c.target_node_id == node_id
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "connections": [c.to_dict() for c in self.connections.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NodeGraph:
        graph = cls(name=data.get("name", "Untitled"))
        for n_data in data.get("nodes", []):
            node = Node.from_dict(n_data)
            graph.nodes[node.node_id] = node
        for c_data in data.get("connections", []):
            conn = Connection.from_dict(c_data)
            graph.connections[conn.conn_id] = conn
        return graph

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, text: str) -> NodeGraph:
        return cls.from_dict(json.loads(text))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> NodeGraph:
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def topological_sort(self) -> List[str]:
        """
        拓扑排序，返回节点执行顺序。
        使用 Kahn 算法。
        Raises ValueError 如果存在环。
        """
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}

        # 构建入度
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for conn in self.connections.values():
            if conn.source_node_id in adj and conn.target_node_id in adj:
                adj[conn.source_node_id].append(conn.target_node_id)
                in_degree[conn.target_node_id] = in_degree.get(
                    conn.target_node_id, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result: List[str] = []

        while queue:
            nid = queue.pop(0)
            result.append(nid)
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            raise ValueError("节点图中存在循环依赖，无法执行")

        return result
