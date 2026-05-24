"""
MayaNodeToolEditor — Maya 内可视化代码节点编辑器入口。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, QRect, QPoint, Signal

from MayaNodeToolEditor.core.node import Node, Connection
from MayaNodeToolEditor.core.node_graph import NodeGraph
from MayaNodeToolEditor.core.executor import Executor
from MayaNodeToolEditor.core.types import DataType, SocketDirection
from MayaNodeToolEditor.ui.node_editor import NodeEditorScene, NodeEditorView
from MayaNodeToolEditor.ui.node_library import NodeLibraryWidget
from MayaNodeToolEditor.ui.node_widget import NodeWidget
from MayaNodeToolEditor.ui.code_editor import CodeEditorDialog
from MayaNodeToolEditor.ui.saved_tools_panel import SavedToolsPanel, TOOLS_DIR
from MayaNodeToolEditor.export.export_script import compile_to_script


class MainWindow(QtWidgets.QMainWindow):
    """主窗口 — 组装节点库 + 工具收藏 + 画布。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Maya 代码节点工具 v0.2")
        self.setMinimumSize(1200, 700)
        self._setup_style()
        self._setup_ui()
        self._setup_menu()
        self._current_file: Optional[str] = None

    def _setup_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #2D2D30; }
            QMenuBar { background: #3E3E42; color: #CCC; }
            QMenuBar::item:selected { background: #094771; }
            QMenu { background: #2D2D30; color: #CCC; border: 1px solid #555; }
            QMenu::item:selected { background: #094771; }
            QToolBar { background: #3E3E42; border: none; spacing: 4px; padding: 2px; }
            QToolButton {
                background: #3E3E42; color: #CCC; border: 1px solid #555;
                padding: 4px 10px; border-radius: 3px;
            }
            QToolButton:hover { background: #505050; }
            QStatusBar { background: #007ACC; color: white; }
        """)

    def _setup_ui(self) -> None:
        # 场景 + 视图
        self.scene = NodeEditorScene(self)
        self.scene.node_double_clicked.connect(self._on_node_double_click)
        self.view = NodeEditorView(self.scene, self)

        # 节点库
        self.library = NodeLibraryWidget(self)
        self.library.node_add_requested.connect(self._add_node_from_template)

        # 工具收藏面板
        self.tools_panel = SavedToolsPanel(self)
        self.tools_panel.tool_loaded.connect(self._load_tool)

        # 左侧标签页：节点库 | 工具收藏
        self.sidebar = QtWidgets.QTabWidget()
        self.sidebar.addTab(self.library, "📦 节点库")
        self.sidebar.addTab(self.tools_panel, "🔧 工具收藏")
        self.sidebar.setStyleSheet("""
            QTabWidget::pane { border: none; background: #252526; }
            QTabBar::tab {
                background: #3E3E42; color: #999; padding: 6px 14px;
                border: none; font-size: 11px;
            }
            QTabBar::tab:selected { background: #252526; color: #EEE; }
        """)

        # 布局
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 940])
        self.setCentralWidget(splitter)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪 — 从节点库拖入或双击添加节点，工具收藏里双击加载预置工具")

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        new_action = QtWidgets.QAction("新建(&N)", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_graph)
        file_menu.addAction(new_action)

        open_action = QtWidgets.QAction("打开(&O)...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_graph)
        file_menu.addAction(open_action)

        save_action = QtWidgets.QAction("保存(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_graph)
        file_menu.addAction(save_action)

        save_as_action = QtWidgets.QAction("另存为...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_graph_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        save_tool_action = QtWidgets.QAction("收藏为工具(&T)...", self)
        save_tool_action.setShortcut("Ctrl+T")
        save_tool_action.triggered.connect(self._save_as_tool)
        file_menu.addAction(save_tool_action)

        file_menu.addSeparator()

        export_action = QtWidgets.QAction("导出为脚本(&E)...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._export_script)
        file_menu.addAction(export_action)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")

        delete_action = QtWidgets.QAction("删除选中(&D)", self)
        delete_action.setShortcut("Delete")
        delete_action.triggered.connect(self._delete_selected)
        edit_menu.addAction(delete_action)

        # 运行菜单
        run_menu = menubar.addMenu("运行(&R)")

        run_action = QtWidgets.QAction("执行节点图(&X)", self)
        run_action.setShortcut("F5")
        run_action.triggered.connect(self._execute_graph)
        run_menu.addAction(run_action)

    # ========== 节点操作 ==========

    def _add_node_from_template(self, template: Dict[str, Any]) -> None:
        node = Node(
            name=template.get("name", "NewNode"),
            category="自定义",
        )
        node.code = template.get("code", "")

        for inp in template.get("inputs", []):
            node.add_input(
                name=inp.get("name", "input"),
                data_type=DataType(inp.get("type", "any")),
                default=inp.get("default"),
                desc=inp.get("desc", ""),
            )

        for out in template.get("outputs", []):
            node.add_output(
                name=out.get("name", "output"),
                data_type=DataType(out.get("type", "any")),
                description=out.get("desc", ""),
            )

        import random
        node.pos_x = random.randint(-300, 300)
        node.pos_y = random.randint(-300, 300)

        self.scene.add_node_widget(node)
        self.status_bar.showMessage(f"已添加节点: {node.name}")

    def _on_node_double_click(self, node_id: str) -> None:
        node = self.scene.graph.get_node(node_id)
        if node is None:
            return
        dialog = CodeEditorDialog(node, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self._refresh_node_widget(node_id)
            self.status_bar.showMessage(f"已更新节点: {node.name}")

    def _refresh_node_widget(self, node_id: str) -> None:
        widget = self.scene.widget_map.get(node_id)
        if widget:
            node = self.scene.graph.get_node(node_id)
            if node:
                connections = self.scene.graph.get_connections_for_node(node_id)
                self.scene.remove_node_widget(node_id)
                self.scene.add_node_widget(node)
                for conn in connections:
                    self.scene.add_connection_line(conn)

    def _delete_selected(self) -> None:
        selected = self.scene.selectedItems()
        for item in selected:
            if isinstance(item, NodeWidget):
                node_id = item.node.node_id
                self.scene.remove_node_widget(node_id)
                self.status_bar.showMessage(f"已删除节点: {item.node.name}")

    # ========== 文件操作 ==========

    def _new_graph(self) -> None:
        self.scene.graph = NodeGraph()
        self.scene.widget_map.clear()
        self.scene.connection_lines.clear()
        self.scene.clear()
        self._current_file = None
        self.status_bar.showMessage("新建节点图")

    def _save_graph(self) -> None:
        if self._current_file:
            self.scene.graph.save(self._current_file)
            self.status_bar.showMessage(f"已保存: {self._current_file}")
        else:
            self._save_graph_as()

    def _save_graph_as(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存节点图", "", "节点图文件 (*.pngraph)")
        if path:
            self.scene.graph.save(path)
            self._current_file = path
            self.status_bar.showMessage(f"已保存: {path}")

    def _open_graph(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "打开节点图", "", "节点图文件 (*.pngraph);;JSON (*.json)")
        if path:
            self._load_graph_file(path)

    def _load_graph_file(self, path: str) -> None:
        try:
            graph = NodeGraph.load(path)
            self._new_graph()
            self.scene.graph = graph
            for node in graph.nodes.values():
                self.scene.add_node_widget(node)
            for conn in graph.connections.values():
                self.scene.add_connection_line(conn)
            self._current_file = path
            self.status_bar.showMessage(f"已加载: {path}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "加载失败", str(e))

    # ========== 工具收藏 ==========

    def _save_as_tool(self) -> None:
        """将当前节点图收藏为工具。"""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "收藏为工具", "工具名称:",
            text=self.scene.graph.name or "")
        if not ok or not name.strip():
            return

        os.makedirs(TOOLS_DIR, exist_ok=True)
        safe_name = name.strip().replace("/", "_").replace("\\", "_")
        path = os.path.join(TOOLS_DIR, f"{safe_name}.pngraph")

        # 保存工具描述
        graph_data = self.scene.graph.to_dict()
        graph_data["name"] = name.strip()
        graph_data["description"] = f"节点数: {len(graph_data['nodes'])}，连线数: {len(graph_data['connections'])}"

        try:
            import json as _json
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(graph_data, f, ensure_ascii=False, indent=2)
            self.tools_panel.refresh_list()
            self.sidebar.setCurrentIndex(1)  # 切换到工具收藏页
            self.status_bar.showMessage(f"已收藏工具: {name}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "收藏失败", str(e))

    def _load_tool(self, path: str) -> None:
        """从工具收藏加载工具图。"""
        self._load_graph_file(path)

    # ========== 执行与导出 ==========

    def _execute_graph(self) -> None:
        try:
            executor = Executor(self.scene.graph)
            results = executor.execute()

            output_lines = []
            for node_id, data in results.items():
                node = self.scene.graph.get_node(node_id)
                name = node.name if node else "?"
                output_lines.append(f"[{name}] → {data}")

            msg = " | ".join(output_lines[:5])
            self.status_bar.showMessage(f"执行完成: {msg}")

            if executor.errors:
                errors = "\n".join(executor.errors.values())
                QtWidgets.QMessageBox.warning(self, "执行错误", errors)
            else:
                QtWidgets.QMessageBox.information(
                    self, "执行完成",
                    "所有节点执行成功！\n\n详细结果:\n" + "\n".join(output_lines))

        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "执行失败", f"图结构错误: {e}")
        except RuntimeError as e:
            QtWidgets.QMessageBox.warning(self, "执行失败", str(e))

    def _export_script(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出脚本", "", "Python脚本 (*.py)")
        if not path:
            return

        try:
            script = compile_to_script(self.scene.graph)
            with open(path, "w", encoding="utf-8") as f:
                f.write(script)
            self.status_bar.showMessage(f"已导出: {path}")
            QtWidgets.QMessageBox.information(
                self, "导出成功", f"脚本已导出到:\n{path}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "导出失败", str(e))


def launch() -> QtWidgets.QMainWindow:
    """启动编辑器（Maya 内调用此函数）。"""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    window = MainWindow()
    window.show()

    # 防 GC：存到 __main__ 模块
    import __main__
    __main__._hermes_maya_window = window

    return window


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
