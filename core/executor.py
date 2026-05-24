"""
执行引擎 — 按拓扑排序顺序执行节点图。
"""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

from .node import Node, Connection
from .node_graph import NodeGraph
from .types import DataType, TYPE_DEFAULTS


class Executor:
    """
    节点图执行器。
    按拓扑排序顺序，对每个节点调用其 run() 函数。
    节点的输入来自上游节点的输出（通过连线传递）。
    """

    def __init__(self, graph: NodeGraph) -> None:
        self.graph = graph
        self.results: Dict[str, Dict[str, Any]] = {}  # node_id → {socket: value}
        self.errors: Dict[str, str] = {}

    def execute(self) -> Dict[str, Any]:
        """
        执行整个节点图。
        返回 {node_id: {socket: value}} 或抛出异常。
        """
        self.results = {}
        self.errors = {}

        order = self.graph.topological_sort()

        for node_id in order:
            node = self.graph.get_node(node_id)
            if node is None:
                continue

            # 收集输入
            inputs = self._resolve_inputs(node)

            # 执行节点代码
            try:
                output = self._run_node(node, inputs)
                self.results[node_id] = output or {}
            except Exception as e:
                error_msg = f"[{node.name}] {e}\n{traceback.format_exc()}"
                self.errors[node_id] = error_msg
                raise RuntimeError(error_msg) from e

        return self.results

    def _resolve_inputs(self, node: Node) -> Dict[str, Any]:
        """
        解析节点的所有输入值。
        对于每个输入插口：
        - 如果有连线连过来，使用上游节点的输出值
        - 如果没有连线，使用默认值
        """
        inputs: Dict[str, Any] = {}

        for sock in node.inputs:
            # 找连到这个输入口的连线
            connected = [
                c for c in self.graph.connections.values()
                if c.target_node_id == node.node_id
                and c.target_socket == sock.name
            ]

            if connected:
                conn = connected[0]
                upstream_output = self.results.get(
                    conn.source_node_id, {}).get(conn.source_socket)
                inputs[sock.name] = upstream_output if upstream_output is not None else sock.default_value
            else:
                inputs[sock.name] = sock.default_value

        return inputs

    def _run_node(self, node: Node, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个节点的代码。
        节点代码是一个 Python 函数的字符串，需编译执行。
        """
        if not node.code.strip():
            # 空代码节点 → 透传输入作为输出
            return {s.name: inputs.get(s.name) for s in node.outputs}

        local_vars: Dict[str, Any] = {"inputs": inputs}
        try:
            exec(node.code, {"__builtins__": __builtins__}, local_vars)
        except Exception as e:
            raise RuntimeError(f"节点 [{node.name}] 代码执行失败: {e}") from e

        if "run" in local_vars and callable(local_vars["run"]):
            raw = local_vars["run"](inputs)
            if raw is None:
                return {}
            if not isinstance(raw, dict):
                return {}
            return raw

        return {}
