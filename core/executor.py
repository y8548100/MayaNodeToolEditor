from __future__ import annotations
"""
执行引擎 — 按拓扑排序顺序执行节点图。
"""


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
        self._inline_values: Dict[str, Dict[str, Any]] = {}

    def execute(self, inline_values: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        执行整个节点图。
        inline_values: {node_id: {widget_name: value}} — 内嵌控件的值
        返回 {node_id: {socket: value}} 或抛出异常。
        """
        self.results = {}
        self.errors = {}
        self._inline_values = inline_values or {}

        order = self.graph.topological_sort()

        for node_id in order:
            node = self.graph.get_node(node_id)
            if node is None:
                continue

            # 收集输入
            inputs = self._resolve_inputs(node)

            # 合并内嵌控件值
            inline_vals = self._resolve_inline_values(node)
            for k, v in inline_vals.items():
                inputs[k] = v

            # 执行节点代码
            try:
                if node.exec_mode == "ui":
                    output = self._run_ui_node(node, inputs)
                else:
                    output = self._run_node(node, inputs)
                self.results[node_id] = output or {}
            except Exception as e:
                error_msg = f"[{node.name}] {e}\n{traceback.format_exc()}"
                self.errors[node_id] = error_msg
                raise RuntimeError(error_msg) from e

        return self.results

    def execute_ui_node(self, node_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接执行单个 UI 节点（不跑全图）。
        """
        node = self.graph.get_node(node_id)
        if node is None:
            raise ValueError(f"找不到节点: {node_id}")
        if node.exec_mode != "ui":
            raise ValueError(f"节点 [{node.name}] 不是 UI 节点")

        self.results[node_id] = self._run_ui_node(node, inputs) or {}
        return self.results[node_id]

    def execute_node(self, node_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接执行单个普通节点。
        """
        node = self.graph.get_node(node_id)
        if node is None:
            raise ValueError(f"找不到节点: {node_id}")

        self.results[node_id] = self._run_node(node, inputs) or {}
        return self.results[node_id]

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

    def _resolve_inline_values(self, node: Node) -> Dict[str, Any]:
        """获取节点的内嵌控件值。"""
        return self._inline_values.get(node.node_id, {})

    def _run_node(self, node: Node, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个节点的代码。
        节点代码是一个 Python 函数的字符串，需编译执行。
        """
        if not node.code.strip():
            # 空代码节点 → 透传输入作为输出
            return {s.name: inputs.get(s.name) for s in node.outputs}

        local_vars: Dict[str, Any] = {"inputs": inputs}
        # 隔离执行环境：只暴露安全的內建函数
        safe_builtins = {
            "abs": abs, "all": all, "any": any, "bool": bool,
            "dict": dict, "enumerate": enumerate, "filter": filter,
            "float": float, "format": format, "frozenset": frozenset,
            "int": int, "isinstance": isinstance, "iter": iter,
            "len": len, "list": list, "map": map, "max": max,
            "min": min, "next": next, "object": object,
            "pow": pow, "range": range, "reversed": reversed,
            "round": round, "set": set, "slice": slice,
            "sorted": sorted, "str": str, "sum": sum,
            "tuple": tuple, "type": type, "zip": zip,
            "True": True, "False": False, "None": None,
            "print": print, "Exception": Exception,
            "ValueError": ValueError, "TypeError": TypeError,
            "KeyError": KeyError, "IndexError": IndexError,
            "RuntimeError": RuntimeError, "AttributeError": AttributeError,
            "__import__": __import__,  # 保留模块导入能力
        }
        try:
            exec(node.code, {"__builtins__": safe_builtins}, local_vars)
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

    def _run_ui_node(self, node: Node, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个 UI 节点的代码。
        与 _run_node 相同但自动注入 ui_runtime 模块到执行环境。
        """
        if not node.code.strip():
            return {s.name: inputs.get(s.name) for s in node.outputs}

        import MayaNodeToolEditor.core.ui_runtime as ui_runtime

        local_vars: Dict[str, Any] = {"inputs": inputs}
        safe_builtins = {
            "abs": abs, "all": all, "any": any, "bool": bool,
            "dict": dict, "enumerate": enumerate, "filter": filter,
            "float": float, "format": format, "frozenset": frozenset,
            "int": int, "isinstance": isinstance, "iter": iter,
            "len": len, "list": list, "map": map, "max": max,
            "min": min, "next": next, "object": object,
            "pow": pow, "range": range, "reversed": reversed,
            "round": round, "set": set, "slice": slice,
            "sorted": sorted, "str": str, "sum": sum,
            "tuple": tuple, "type": type, "zip": zip,
            "True": True, "False": False, "None": None,
            "print": print, "Exception": Exception,
            "ValueError": ValueError, "TypeError": TypeError,
            "KeyError": KeyError, "IndexError": IndexError,
            "RuntimeError": RuntimeError, "AttributeError": AttributeError,
            "__import__": __import__,
        }
        # ui 模块需注入 globals（函数闭包能访问）而非 local_vars
        exec_globals: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "ui": ui_runtime,
        }
        try:
            exec(node.code, exec_globals, local_vars)
        except Exception as e:
            raise RuntimeError(f"UI节点 [{node.name}] 代码执行失败: {e}") from e

        if "run" in local_vars and callable(local_vars["run"]):
            raw = local_vars["run"](inputs)
            if raw is None:
                return {}
            if not isinstance(raw, dict):
                return {}
            return raw

        return {}
