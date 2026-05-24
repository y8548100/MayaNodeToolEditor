from __future__ import annotations
"""
工具收藏面板 — 显示可用的已保存工具图，支持双击加载。
"""


import json
import os
from typing import Any, Dict, List, Optional

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, Signal

from MayaNodeToolEditor.core.node_graph import NodeGraph


TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


class SavedToolsPanel(QtWidgets.QWidget):
    """工具收藏面板 — 显示可用的已保存工具图。"""

    tool_loaded = Signal(str)  # 发射工具文件路径

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self.setStyleSheet("""
            QWidget { background: #252526; color: #CCC; }
            QListWidget { background: #1E1E1E; border: 1px solid #3E3E42;
                          font-size: 12px; }
            QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #333; }
            QListWidget::item:selected { background: #094771; }
            QListWidget::item:hover { background: #2A2D2E; }
            QPushButton {
                background: #0E639C; color: white; border: none;
                padding: 5px 12px; border-radius: 3px; font-size: 11px;
            }
            QPushButton:hover { background: #1177BB; }
            QLabel { color: #888; font-size: 11px; padding: 4px; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        title = QtWidgets.QLabel("🔧 工具收藏")
        title.setStyleSheet("font-size: 12px; font-weight: bold; padding: 4px; color: #CCC;")
        layout.addWidget(title)

        self.tool_list = QtWidgets.QListWidget()
        self.tool_list.setAlternatingRowColors(True)
        self.tool_list.itemDoubleClicked.connect(self._on_load_tool)
        layout.addWidget(self.tool_list)

        btn_layout = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_list)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.refresh_list()

    def refresh_list(self) -> None:
        """扫描 tools/ 目录，刷新工具列表。"""
        self.tool_list.clear()
        if not os.path.isdir(TOOLS_DIR):
            os.makedirs(TOOLS_DIR, exist_ok=True)
            self.tool_list.addItem("（尚无收藏的工具）")
            return

        files = sorted([f for f in os.listdir(TOOLS_DIR) if f.endswith(".pngraph")])
        if not files:
            self.tool_list.addItem("（尚无收藏的工具）")
            return

        for fn in files:
            path = os.path.join(TOOLS_DIR, fn)
            try:
                graph = NodeGraph.load(path)
                name = graph.name if graph.name else fn.replace(".pngraph", "")
                graph_dict = graph.to_dict()
                desc = graph_dict.get("description", "")
                item_text = f"{name}\n  ({len(graph.nodes)}个节点 · {len(graph.connections)}条连线)"
                if desc:
                    item_text = f"{name}\n  {desc}"
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(Qt.UserRole, path)
                item.setToolTip(f"双击加载\n路径: {path}")
                self.tool_list.addItem(item)
            except Exception as e:
                item = QtWidgets.QListWidgetItem(f"⚠️ {fn}")
                item.setToolTip(str(e))
                self.tool_list.addItem(item)

    def _on_load_tool(self, item: QtWidgets.QListWidgetItem) -> None:
        """双击工具项时加载。"""
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            self.tool_loaded.emit(path)
