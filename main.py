from __future__ import annotations
"""
MayaNodeToolEditor — Maya 内可视化代码节点编辑器入口。
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, QTimer

from MayaNodeToolEditor.core.node import Node, Connection as ConnModel
from MayaNodeToolEditor.core.node_graph import NodeGraph
from MayaNodeToolEditor.core.executor import Executor
from MayaNodeToolEditor.core.types import DataType, SocketDirection
from MayaNodeToolEditor.ui.node_editor import NodeEditorScene, NodeEditorView, SearchBarWidget
from MayaNodeToolEditor.ui.node_library import NodeLibraryWidget
from MayaNodeToolEditor.ui.node_widget import NodeWidget
from MayaNodeToolEditor.ui.code_editor import CodeEditorDialog
from MayaNodeToolEditor.ui.saved_tools_panel import SavedToolsPanel, TOOLS_DIR
from MayaNodeToolEditor.export.export_script import compile_to_script


class MainWindow(QtWidgets.QMainWindow):
    """主窗口 — 组装节点库 + 工具收藏 + 画布。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Maya 代码节点工具 v0.3")
        self.setMinimumSize(1200, 700)
        self._setup_style()
        self._setup_ui()
        self._setup_menu()
        self._current_file: Optional[str] = None

        # 实时联动防抖定时器 (Phase 1)
        self._reactive_timer = QTimer()
        self._reactive_timer.setSingleShot(True)
        self._reactive_timer.setInterval(300)  # 300ms 防抖
        self._reactive_timer.timeout.connect(self._do_reactive_execute)
        self._pending_reactive_node: Optional[str] = None

        # 撤销/重做 (Phase 7)
        from MayaNodeToolEditor.core.undo_manager import UndoManager
        self.undo_manager = UndoManager(self.scene)
        self.scene.undo_manager = self.undo_manager  # 让 scene 也能 push 快照
        self._undo_timer = QTimer()
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(100)
        self._undo_timer.timeout.connect(self._update_undo_menu_text)

        # 全局快捷键确保任何焦点下都能用
        self._undo_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Z"), self)
        self._undo_shortcut.activated.connect(self._undo)
        self._redo_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), self)
        self._redo_shortcut.activated.connect(self._redo)
        self._copy_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+C"), self)
        self._copy_shortcut.activated.connect(self._copy_selected)
        self._paste_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+V"), self)
        self._paste_shortcut.activated.connect(self._paste_from_clipboard)

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
        self.scene.node_run_requested.connect(self._on_node_run_requested)
        self.scene.inline_widget_changed.connect(self._on_inline_widget_changed)
        self.scene.graph_changed.connect(self._on_graph_changed)
        self.view = NodeEditorView(self.scene, self)

        # 搜索栏 (Phase 8)
        self.search_bar = SearchBarWidget()
        self.search_bar.search_requested.connect(self._on_search)
        self.search_bar.cycle_forward.connect(self._on_search_next)
        self.search_bar.cycle_backward.connect(self._on_search_prev)
        self.search_bar.close_requested.connect(self._on_search_close)
        self.search_bar.hide()

        # 搜索快捷键
        search_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self._show_search_bar)

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
        central = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 搜索栏在最上
        central_layout.addWidget(self.search_bar)

        # 主分割器
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 940])
        central_layout.addWidget(splitter, 1)

        self.setCentralWidget(central)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪 — 从节点库拖入或双击添加节点，工具收藏里双击加载预置工具")

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # ====== 文件菜单 ======
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

        # ====== 编辑菜单 ======
        edit_menu = menubar.addMenu("编辑(&E)")

        # 撤销/重做 (Phase 7)
        self.undo_action = QtWidgets.QAction("撤销(&Z)", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self._undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QtWidgets.QAction("重做(&Y)", self)
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        self.redo_action.triggered.connect(self._redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        # 复制/粘贴 (Phase 3)
        copy_action = QtWidgets.QAction("复制(&C)", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self._copy_selected)
        edit_menu.addAction(copy_action)

        paste_action = QtWidgets.QAction("粘贴(&V)", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self._paste_from_clipboard)
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()

        delete_action = QtWidgets.QAction("删除选中(&D)", self)
        delete_action.setShortcut("Delete")
        delete_action.triggered.connect(self._delete_selected)
        edit_menu.addAction(delete_action)

        # ====== 选择菜单 ======
        select_menu = menubar.addMenu("选择(&S)")
        select_all_action = QtWidgets.QAction("全选(&A)", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self._select_all)
        select_menu.addAction(select_all_action)

        # ====== 运行菜单 ======
        run_menu = menubar.addMenu("运行(&R)")

        run_action = QtWidgets.QAction("执行节点图(&X)", self)
        run_action.setShortcut("F5")
        run_action.triggered.connect(self._execute_graph)
        run_menu.addAction(run_action)

        # ====== 分组菜单 ======
        group_menu = menubar.addMenu("分组(&G)")

        group_action = QtWidgets.QAction("分组选中节点(&G)", self)
        group_action.setShortcut("Ctrl+G")
        group_action.triggered.connect(self._group_selected)
        group_menu.addAction(group_action)

    # ========== Phase 1: 实时联动 ==========

    def _on_inline_widget_changed(self, node_id: str, widget_name: str) -> None:
        """内嵌控件变化时启动防抖定时器。"""
        self._pending_reactive_node = node_id
        self._reactive_timer.start()

    def _do_reactive_execute(self) -> None:
        """防抖到期后执行实时联动。"""
        if self._pending_reactive_node is None:
            return

        node_id = self._pending_reactive_node
        self._pending_reactive_node = None

        # 收集所有内嵌控件值
        inline_values = self.scene.collect_all_inline_values()

        # 获取下游节点
        downstream = self.scene.get_downstream_nodes(node_id)
        if not downstream:
            return  # 没有下游，无需执行

        try:
            executor = Executor(self.scene.graph)

            # 执行所有下游节点
            for dn_id in downstream:
                dn_node = self.scene.graph.get_node(dn_id)
                if dn_node is None:
                    continue

                # 收集该节点输入
                inputs = {}
                for sock in dn_node.inputs:
                    connected = [
                        c for c in self.scene.graph.connections.values()
                        if c.target_node_id == dn_id
                        and c.target_socket == sock.name
                    ]
                    if connected and connected[0].source_node_id in executor.results:
                        upstream_data = executor.results.get(connected[0].source_node_id, {})
                        upstream_val = upstream_data.get(connected[0].source_socket)
                        inputs[sock.name] = upstream_val if upstream_val is not None else sock.default_value
                    elif connected:
                        inputs[sock.name] = sock.default_value
                    else:
                        inputs[sock.name] = sock.default_value

                # 合并内嵌控件值
                dn_inline = inline_values.get(dn_id, {})
                inputs.update(dn_inline)

                # 只有 text_display 节点允许空代码执行
                has_display = any(
                    cfg.get("type") == "text_display"
                    for cfg in dn_node.inline_widgets
                )
                if not dn_node.code.strip() and not has_display:
                    continue

                # 执行
                if dn_node.exec_mode == "ui":
                    result = executor._run_ui_node(dn_node, inputs)
                else:
                    result = executor._run_node(dn_node, inputs)
                executor.results[dn_id] = result or {}

            # 更新显示控件
            self._update_inline_displays(executor.results)

            # 更新状态栏摘要
            updated = len(executor.results) - 1  # 减去源节点
            if updated > 0:
                self.status_bar.showMessage(f"⚡ 实时联动: 更新了 {updated} 个下游节点")

        except Exception as e:
            # 实时联动失败不弹窗，只在状态栏显示
            self.status_bar.showMessage(f"⚠️ 联动执行出错: {e}")

    # ========== Phase 8: 节点搜索 ==========

    def _show_search_bar(self) -> None:
        """显示搜索栏并聚焦输入框。"""
        self.search_bar.show()
        self.search_bar.search_input.setFocus()
        self.search_bar.search_input.selectAll()

    def _on_search(self, query: str) -> None:
        """搜索框文本变化时执行搜索。"""
        matches = self.scene.search_nodes(query)
        if matches:
            self.search_bar.update_count(0, len(matches))
        else:
            self.search_bar.update_count(0, 0)

    def _on_search_next(self) -> None:
        """搜索下一个匹配。"""
        self.scene.cycle_search(forward=True)
        idx = self.scene._search_index
        total = len(self.scene._search_matches)
        self.search_bar.update_count(idx, total)

    def _on_search_prev(self) -> None:
        """搜索上一个匹配。"""
        self.scene.cycle_search(forward=False)
        idx = self.scene._search_index
        total = len(self.scene._search_matches)
        self.search_bar.update_count(idx, total)

    def _on_search_close(self) -> None:
        """关闭搜索栏。"""
        self.search_bar.hide()
        self.search_bar.search_input.clear()
        self.scene.search_nodes("")

    # ========== Phase 7: 撤销/重做 ==========

    def _on_graph_changed(self) -> None:
        """图变化时更新撤销菜单状态。"""
        self._undo_timer.start()

    def _update_undo_menu_text(self) -> None:
        """更新撤销/重做菜单文本。"""
        if self.undo_manager.can_undo:
            self.undo_action.setText(f"撤销 ({self.undo_manager.undo_description()})")
            self.undo_action.setEnabled(True)
        else:
            self.undo_action.setText("撤销")
            self.undo_action.setEnabled(False)

        if self.undo_manager.can_redo:
            self.redo_action.setText(f"重做 ({self.undo_manager.redo_description()})")
            self.redo_action.setEnabled(True)
        else:
            self.redo_action.setText("重做")
            self.redo_action.setEnabled(False)

    def _undo(self) -> None:
        """执行撤销。"""
        cmd = self.undo_manager.undo()
        if cmd:
            self.status_bar.showMessage(f"↩️ 撤销: {cmd.description}")
            self._update_undo_menu_text()

    def _redo(self) -> None:
        """执行重做。"""
        cmd = self.undo_manager.redo()
        if cmd:
            self.status_bar.showMessage(f"↪️ 重做: {cmd.description}")
            self._update_undo_menu_text()

    # ========== Phase 3: 复制/粘贴 ==========

    def _copy_selected(self) -> None:
        """复制选中节点到剪贴板。"""
        text = self.scene.copy_selected_nodes()
        if text:
            try:
                clipboard = QtGui.QGuiApplication.clipboard()
                clipboard.setText(text)
                self.status_bar.showMessage("📋 已复制到剪贴板")
            except Exception:
                pass

    def _paste_from_clipboard(self) -> None:
        """从剪贴板粘贴节点。"""
        try:
            clipboard = QtGui.QGuiApplication.clipboard()
            text = clipboard.text()
            new_ids = self.scene.paste_nodes(text)
            if new_ids:
                self.status_bar.showMessage(f"📋 已粘贴 {len(new_ids)} 个节点")
        except Exception as e:
            self.status_bar.showMessage(f"⚠️ 粘贴失败: {e}")

    def _select_all(self) -> None:
        """全选所有节点。"""
        for widget in self.scene.widget_map.values():
            widget.setSelected(True)
        self.status_bar.showMessage(f"已选中 {len(self.scene.widget_map)} 个节点")

    # ========== 分组 (Phase 4) ==========

    def _group_selected(self) -> None:
        """将选中的节点分组。"""
        group = self.scene.group_selected_nodes("分组")
        if group:
            self.status_bar.showMessage(f"📦 已创建分组 ({len(group.child_nodes)} 个节点)")
        else:
            self.status_bar.showMessage("请先选中至少一个节点")

    # ========== 节点操作 ==========

    def _add_node_from_template(self, template: Dict[str, Any]) -> None:
        exec_mode = template.get("exec_mode", "code")
        node = Node(
            name=template.get("name", "NewNode"),
            category="自定义",
            exec_mode=exec_mode,
        )
        node.code = template.get("code", "")
        # 内嵌控件
        node.inline_widgets = template.get("inline_widgets", [])
        # UI 节点用不同颜色
        if exec_mode == "ui":
            node.color = "#3A6EA5"
        elif node.inline_widgets:
            node.color = "#3A6EA5"  # 内嵌控件节点也用蓝色

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
        self.status_bar.showMessage(f"已添加节点 {node.name}")

    def _on_node_double_click(self, node_id: str) -> None:
        """双击节点打开代码编辑器（非模态，不阻塞监听器）。起始节点不可编辑。"""
        node = self.scene.graph.get_node(node_id)
        if node is None:
            return
        if node.is_start_node:
            self.status_bar.showMessage("起始节点不可编辑")
            return

        # 如果已有该节点的编辑器窗口，激活它
        if hasattr(self, '_code_dialogs') and node_id in self._code_dialogs:
            dialog = self._code_dialogs[node_id]
            if dialog.isVisible():
                dialog.show_and_focus()
                return

        dialog = CodeEditorDialog(node, self)
        dialog.node_saved.connect(lambda nid: self._on_code_saved(nid))
        if not hasattr(self, '_code_dialogs'):
            self._code_dialogs = {}
        self._code_dialogs[node_id] = dialog
        dialog.show_and_focus()

    def _on_code_saved(self, node_id: str) -> None:
        """代码编辑器保存后的回调。"""
        self._refresh_node_widget(node_id)
        node = self.scene.graph.get_node(node_id)
        name = node.name if node else "?"
        self.status_bar.showMessage(f"已更新节点 {name}")

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
                self.status_bar.showMessage(f"已删除节点 {item.node.name}")

    # ========== 文件操作 ==========

    def _new_graph(self) -> None:
        self.scene.graph = NodeGraph()
        self.scene.widget_map.clear()
        self.scene.connection_lines.clear()
        self.scene.group_boxes.clear()
        self.scene.clear()
        # 清理撤销栈
        self.undo_manager._undo_stack.clear()
        self.undo_manager._redo_stack.clear()
        self._update_undo_menu_text()
        # 创建起始节点
        self.scene.ensure_start_node()
        self._current_file = None
        self.status_bar.showMessage("新建节点图（含起始节点）")

    def _save_graph(self) -> None:
        # Phase 2: 先持久化控件值再保存
        self.scene.persist_all_inline_values()

        if self._current_file:
            self.scene.graph.save(self._current_file)
            self.status_bar.showMessage(f"已保存 {self._current_file}")
        else:
            self._save_graph_as()

    def _save_graph_as(self) -> None:
        # Phase 2: 先持久化控件值再保存
        self.scene.persist_all_inline_values()

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存节点图", "", "节点图文件 (*.pngraph)")
        if path:
            self.scene.graph.save(path)
            self._current_file = path
            self.status_bar.showMessage(f"已保存 {path}")

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
            # 清理撤销栈（加载新图后撤销栈应该清空）
            self.undo_manager._undo_stack.clear()
            self.undo_manager._redo_stack.clear()
            self._update_undo_menu_text()
            for node in graph.nodes.values():
                self.scene.add_node_widget(node)
            for conn in graph.connections.values():
                self.scene.add_connection_line(conn)
            # 加载后确保有起始节点（如果图上没有的话）
            self.scene.ensure_start_node()
            # Phase 2: 加载后恢复内嵌控件值
            self.scene.restore_inline_values()
            self._current_file = path
            self.status_bar.showMessage(f"已加载 {path}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "加载失败", str(e))

    # ========== 工具收藏 ==========

    def _save_as_tool(self) -> None:
        """将当前节点图收藏为工具。"""
        # Phase 2: 先持久化控件值
        self.scene.persist_all_inline_values()

        name, ok = QtWidgets.QInputDialog.getText(
            self, "收藏为工具", "工具名称:",
            text=self.scene.graph.name or "")
        if not ok or not name.strip():
            return

        os.makedirs(TOOLS_DIR, exist_ok=True)
        safe_name = name.strip().replace("/", "_").replace("\\", "_")
        path = os.path.join(TOOLS_DIR, f"{safe_name}.pngraph")

        graph_data = self.scene.graph.to_dict()
        graph_data["name"] = name.strip()
        graph_data["description"] = f"节点数: {len(graph_data['nodes'])}，连线数: {len(graph_data['connections'])}"

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
            self.tools_panel.refresh_list()
            self.sidebar.setCurrentIndex(1)
            self.status_bar.showMessage(f"已收藏工具 {name}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "收藏失败", str(e))

    def _load_tool(self, path: str) -> None:
        """从工具收藏加载工具图。"""
        self._load_graph_file(path)

    # ========== 执行 ==========

    def _collect_inline_values(self) -> Dict[str, Dict[str, Any]]:
        """从场景中所有节点收集内嵌控件的值。"""
        return self.scene.collect_all_inline_values()

    def _update_inline_displays(self, results: Dict[str, Dict[str, Any]]) -> None:
        """将执行结果更新到节点的内嵌显示控件（如打印节点的 text_display）。"""
        for nid, data in results.items():
            widget = self.scene.widget_map.get(nid)
            if widget is None:
                continue
            node = self.scene.graph.get_node(nid)
            if node is None:
                continue
            for cfg in node.inline_widgets:
                if cfg.get("type") == "text_display":
                    name = cfg.get("name", "output")
                    if name in data:
                        widget.set_inline_value(name, str(data[name]))
                    else:
                        for k, v in data.items():
                            if k not in ("display", "_raw"):
                                widget.set_inline_value(name, str(v))
                                break
                        else:
                            widget.set_inline_value(name, str(data))

    def _execute_graph(self) -> None:
        try:
            inline_values = self._collect_inline_values()

            executor = Executor(self.scene.graph)
            results = executor.execute(inline_values=inline_values)

            # 更新内嵌显示控件
            self._update_inline_displays(results)

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
                output_text = "\n".join(output_lines)
                QtWidgets.QMessageBox.information(
                    self, "执行完成",
                    "所有节点执行成功！\n\n详细结果:\n" + output_text)

        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "执行失败", f"图结构错误: {e}")
        except RuntimeError as e:
            QtWidgets.QMessageBox.warning(self, "执行失败", str(e))

    def _on_node_run_requested(self, node_id: str) -> None:
        """
        从指定节点开始执行（仅运行该节点及其下游）。
        用在：
        - UI 节点 ▶ 按钮
        - 右键 "▶ 从此运行"
        - F5 如果有起始节点则走这里
        """
        node = self.scene.graph.get_node(node_id)
        if node is None:
            return

        # 收集内嵌控件值
        inline_values = self.scene.collect_all_inline_values()

        # 用 executor 跑子树
        try:
            executor = Executor(self.scene.graph)

            # 查找下游节点
            downstream = self.scene.get_downstream_nodes(node_id)
            all_nodes = [node_id] + downstream

            # 按拓扑顺序执行
            topo = self.scene.graph.topological_sort()
            ordered = [nid for nid in topo if nid in all_nodes]

            for nid in ordered:
                n = self.scene.graph.get_node(nid)
                if n is None:
                    continue

                inputs = {}
                for sock in n.inputs:
                    connected = [
                        c for c in self.scene.graph.connections.values()
                        if c.target_node_id == nid
                        and c.target_socket == sock.name
                    ]
                    if connected:
                        conn = connected[0]
                        upstream_out = executor.results.get(
                            conn.source_node_id, {}).get(conn.source_socket)
                        inputs[sock.name] = upstream_out if upstream_out is not None else sock.default_value
                    else:
                        inputs[sock.name] = sock.default_value

                # 合并内嵌控件值
                inline_vals = inline_values.get(nid, {})
                for k, v in inline_vals.items():
                    if k not in inputs or inputs[k] is None:
                        inputs[k] = v

                # 执行
                if n.exec_mode == "ui":
                    result = executor._run_ui_node(n, inputs)
                else:
                    result = executor._run_node(n, inputs)
                executor.results[nid] = result or {}

            # 更新显示控件
            self._update_inline_displays(executor.results)

            # 状态栏
            node_names = [self.scene.graph.get_node(nid).name
                          for nid in ordered if self.scene.graph.get_node(nid)]
            self.status_bar.showMessage(
                f"▶ 已运行: {' → '.join(node_names[:3])}"
                + (f" +{len(node_names)-3}" if len(node_names) > 3 else ""))

            # 如果有起始节点标记，自动清除非起始节点的印记
            # (不需要，起始节点标记是持久化的)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.warning(
                self, "运行失败",
                f"执行出错:\n{e}")

    def _export_script(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出脚本", "", "Python脚本 (*.py)")
        if not path:
            return

        try:
            script = compile_to_script(self.scene.graph)
            with open(path, "w", encoding="utf-8") as f:
                f.write(script)
            self.status_bar.showMessage(f"已导出 {path}")
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
    window.scene.ensure_start_node()

    # 防 GC：存在 __main__ 模块
    import __main__
    __main__._hermes_maya_window = window

    return window


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
