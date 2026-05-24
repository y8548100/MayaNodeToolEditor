"""
导出引擎 — 将节点图编译为可执行的 Python 脚本。
"""

from __future__ import annotations

import json
from typing import Dict, List

from MayaNodeToolEditor.core.node_graph import NodeGraph


def compile_to_script(graph: NodeGraph) -> str:
    """将节点图编译为完整的 Python 脚本字符串。"""
    lines = [
        "# -*- coding: utf-8 -*-",
        "# 由 MayaNodeToolEditor 自动生成",
        f"# 工具: {graph.name}",
        f"# 节点数: {len(graph.nodes)}  连线数: {len(graph.connections)}",
        "",
        "import sys",
        "import traceback",
        "",
        "",
    ]

    try:
        order = graph.topological_sort()
    except ValueError as e:
        raise RuntimeError(str(e)) from e

    for node_id in order:
        node = graph.get_node(node_id)
        if not node or not node.code.strip():
            continue

        lines.append(f"# === 节点: {node.name} ({node.node_id[:8]}) ===")
        lines.append(f"def _node_{node.node_id[:8]}(inputs):")
        code_lines = node.code.strip().split("\n")
        for cl in code_lines:
            lines.append(f"    {cl}")
        lines.append("")
        lines.append("")

    lines.append("def main():")
    lines.append("    results = {}")
    lines.append("")

    for node_id in order:
        node = graph.get_node(node_id)
        if not node:
            continue
        short_id = node.node_id[:8]
        lines.append(f"    # === {node.name} ===")

        inputs_parts = []
        for sock in node.inputs:
            connected = [
                c for c in graph.connections.values()
                if c.target_node_id == node_id and c.target_socket == sock.name
            ]
            if connected:
                conn = connected[0]
                src_short = conn.source_node_id[:8]
                src_sock = conn.source_socket
                inputs_parts.append(
                    f'"{sock.name}": results.get("{src_short}", {{}}).get("{src_sock}")'
                )
            else:
                val = json.dumps(sock.default_value, ensure_ascii=False)
                inputs_parts.append(f'"{sock.name}": {val}')

        inputs_str = ", ".join(inputs_parts)
        lines.append(f"    _inputs_{short_id} = {{{inputs_str}}}")
        lines.append(f"    try:")
        lines.append(f"        results['{short_id}'] = _node_{short_id}(_inputs_{short_id})")
        lines.append(f"    except Exception as e:")
        lines.append(f"        print(f'[ERROR] 节点 [{node.name}] 执行失败: {{e}}')")
        lines.append(f"        traceback.print_exc()")
        lines.append(f"        results['{short_id}'] = {{}}")
        lines.append("")

    lines.append('    print("=== 执行完成 ===' + '"')
    lines.append("    for k, v in results.items():")
    lines.append('        print(f"  [{k}] {v}")')
    lines.append("")
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    main()")

    return "\n".join(lines)
