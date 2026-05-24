from __future__ import annotations
"""
节点图画布 — PySide2 QGraphicsView/QGraphicsScene 实现。
"""


import json
from typing import Any, Dict, List, Optional, Tuple

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, QPointF, QRectF, Signal
from PySide2.QtGui import QPainter

from MayaNodeToolEditor.core.node import Node as NodeModel, Connection as ConnectionModel
from MayaNodeToolEditor.core.node_graph import NodeGraph
from MayaNodeToolEditor.core.types import DataType
from MayaNodeToolEditor.ui.node_widget import (
    NodeWidget, SocketItem, GroupBox,
    NODE_WIDTH, SOCKET_H, NODE_HEADER_H, SOCKET_RADIUS,
)


class ConnectionLine(QtWidgets.QGraphicsPathItem):
    """节点间的连线（贝塞尔曲线）。"""

    def __init__(self, conn: ConnectionModel,
                 source_socket: SocketItem, target_socket: SocketItem) -> None:
        super().__init__()
        self.conn = conn
        self.source_socket = source_socket
        self.target_socket = target_socket
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._normal_pen = QtGui.QPen(QtGui.QColor("#888"), 2)
        self._selected_pen = QtGui.QPen(QtGui.QColor("#FFD700"), 3)
        self._hover_pen = QtGui.QPen(QtGui.QColor("#AAA"), 2.5)
        self.setPen(self._normal_pen)
        self.setBrush(Qt.NoBrush)
        self.setZValue(-1)
        self._hovered = False
        self._update_path()

    def boundingRect(self) -> QRectF:
        """扩大选中区域，方便框选和点击。"""
        return super().boundingRect().adjusted(-6, -6, 6, 6)

    def shape(self) -> QtGui.QPainterPath:
        """覆盖默认 shape 让鼠标点击路径本身就能选中。"""
        path = QtGui.QPainterPath()
        if self.path().isEmpty():
            return path
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(12)  # 12px 宽的热区
        return stroker.createStroke(self.path())

    def _update_path(self) -> None:
        p1 = self.source_socket.center_pos()
        p2 = self.target_socket.center_pos()
        dx = abs(p2.x() - p1.x()) * 0.5
        cp1 = QPointF(p1.x() + dx, p1.y())
        cp2 = QPointF(p2.x() - dx, p2.y())

        path = QtGui.QPainterPath()
        path.moveTo(p1)
        path.cubicTo(cp1, cp2, p2)
        self.setPath(path)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        if self.isSelected():
            painter.setPen(self._selected_pen)
        elif self._hovered:
            painter.setPen(self._hover_pen)
        else:
            painter.setPen(self._normal_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def update_position(self) -> None:
        self._update_path()


class DragLine(QtWidgets.QGraphicsLineItem):
    """拖拽中的临时连线。"""

    def __init__(self, start: QPointF) -> None:
        super().__init__()
        self.start = start
        self.end = start
        self.setPen(QtGui.QPen(QtGui.QColor("#FFD700"), 2, Qt.DashLine))
        self.setZValue(10)

    def update_end(self, end: QPointF) -> None:
        self.end = end
        line = QtCore.QLineF(self.start, self.end)
        self.setLine(line)


class NodeEditorScene(QtWidgets.QGraphicsScene):
    """节点编辑场景。"""

    # 信号
    node_selected = Signal(str)       # node_id
    node_double_clicked = Signal(str)  # node_id
    node_run_requested = Signal(str)   # node_id — UI节点直接运行
    inline_widget_changed = Signal(str, str)  # node_id, widget_name
    graph_changed = Signal()          # 图发生任何变化时

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.graph = NodeGraph()
        self.widget_map: Dict[str, NodeWidget] = {}
        self.connection_lines: Dict[str, ConnectionLine] = {}
        self.group_boxes: List[GroupBox] = []
        self._drag_line: Optional[DragLine] = None
        self._drag_source: Optional[SocketItem] = None

        # 搜索匹配
        self._search_matches: List[str] = []  # node_ids matching current search
        self._search_index: int = -1

        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setBackgroundBrush(QtGui.QColor("#1E1E1E"))

        # 执行状态追踪
        self._executing_node_id: Optional[str] = None

        # 撤销/重做管理器引用（由 MainWindow 设置）
        self.undo_manager = None
        self._undo_prev_state = None
        self._undo_nest_counter = 0

    # ========== 拖拽放置 (从节点库拖入) ==========

    def dragEnterEvent(self, event: QtWidgets.QGraphicsSceneDragDropEvent) -> None:
        if event.mimeData().hasFormat("application/x-node-template"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtWidgets.QGraphicsSceneDragDropEvent) -> None:
        if event.mimeData().hasFormat("application/x-node-template"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtWidgets.QGraphicsSceneDragDropEvent) -> None:
        if event.mimeData().hasFormat("application/x-node-template"):
            import json
            raw = event.mimeData().data("application/x-node-template").data()
            try:
                template = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                event.ignore()
                return

            # 通知 MainWindow 添加节点 (通过信号)
            from MayaNodeToolEditor.core.node import Node
            from MayaNodeToolEditor.core.types import DataType

            exec_mode = template.get("exec_mode", "code")
            node = Node(
                name=template.get("name", "NewNode"),
                category="自定义",
                exec_mode=exec_mode,
            )
            node.code = template.get("code", "")
            node.inline_widgets = template.get("inline_widgets", [])
            if exec_mode == "ui" or node.inline_widgets:
                node.color = "#3A6EA5"

            for inp in template.get("inputs", []):
                node.add_input(
                    name=inp.get("name", "input"),
                    data_type=DataType(inp.get("type", "any")),
                    default=inp.get("default"),
                    desc=inp.get("desc", ""),
                    label=inp.get("label", ""),
                    visible_when=inp.get("visible_when", ""),
                )
            for out in template.get("outputs", []):
                node.add_output(
                    name=out.get("name", "output"),
                    data_type=DataType(out.get("type", "any")),
                    description=out.get("desc", ""),
                    label=out.get("label", ""),
                )

            # 放在鼠标释放位置
            drop_pos = event.scenePos()
            node.pos_x = drop_pos.x() - 90  # 居中 (NODE_WIDTH/2)
            node.pos_y = drop_pos.y() - 14  # 居中 (NODE_HEADER_H/2)

            self.add_node_widget(node)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # ========== 添加/移除节点 ==========

    def add_node_widget(self, node: NodeModel) -> NodeWidget:
        self._save_undo_point()
        self.graph.add_node(node)
        widget = NodeWidget(node, self)
        self.addItem(widget)
        self.widget_map[node.node_id] = widget

        # 连接内嵌控件变化信号
        widget._relay.widget_changed.connect(self._on_widget_changed)

        self._commit_undo(f"添加节点 {node.name}")
        return widget

    def ensure_start_node(self) -> NodeWidget:
        """确保画布上有一个起始节点，没有则创建。"""
        for nid, w in self.widget_map.items():
            if w.node.is_start_node:
                return w
        # 创建起始节点
        start = NodeModel("▶ 起点", category="系统")
        start.is_start_node = True
        start.color = "#2E7D32"
        start.code = "# 起始节点 — 执行从此开始"
        start.add_output("run", DataType.ANY, "执行入口", label="执行信号")
        start.pos_x = -300
        start.pos_y = -150
        return self.add_node_widget(start)

    def _on_widget_changed(self, node_id: str, widget_name: str) -> None:
        """转发内嵌控件变化信号。"""
        self.inline_widget_changed.emit(node_id, widget_name)

    def remove_node_widget(self, node_id: str) -> None:
        widget = self.widget_map.get(node_id)
        if widget and widget.node.is_start_node:
            return  # 起始节点不可删除
        self._save_undo_point()
        widget = self.widget_map.pop(node_id, None)
        if widget:
            # 断开信号连接
            try:
                widget._relay.widget_changed.disconnect()
            except Exception:
                pass
            self.removeItem(widget)

        # 删除相关连线
        to_remove = [
            cid for cid, cl in self.connection_lines.items()
            if cl.conn.source_node_id == node_id
            or cl.conn.target_node_id == node_id
        ]
        for cid in to_remove:
            self.remove_connection_line(cid)

        self.graph.remove_node(node_id)
        self._commit_undo("删除节点")
        self.graph_changed.emit()

    # ========== 添加/移除连线 ==========

    def add_connection_line(self, conn: ConnectionModel) -> None:
        src_widget = self.widget_map.get(conn.source_node_id)
        tgt_widget = self.widget_map.get(conn.target_node_id)
        if not src_widget or not tgt_widget:
            return

        src_socket = self._find_socket(src_widget, conn.source_socket, is_output=True)
        tgt_socket = self._find_socket(tgt_widget, conn.target_socket, is_output=False)

        # 起始节点特殊处理：即使目标没有匹配插口也创建连接（标记为执行树成员）
        src_is_start = src_widget.node.is_start_node if src_widget else False
        if src_socket and not tgt_socket and src_is_start:
            # 创建虚拟连接，visual 层面跳过插口匹配
            pass  # 仍走下面的 add_connection

        if not src_socket or not tgt_socket:
            if src_is_start:
                # 起始节点允许无插口匹配的连接（用于标记执行树）
                self._save_undo_point()
                self.graph.add_connection(conn)
                self._commit_undo("添加连线")
                self.graph_changed.emit()
                return
            return

        self._save_undo_point()
        self.graph.add_connection(conn)
        line = ConnectionLine(conn, src_socket, tgt_socket)
        self.addItem(line)
        self.connection_lines[conn.conn_id] = line
        self._commit_undo("添加连线")
        self.graph_changed.emit()

    def remove_connection_line(self, conn_id: str) -> None:
        self._save_undo_point()
        line = self.connection_lines.pop(conn_id, None)
        if line:
            self.removeItem(line)
        self.graph.remove_connection(conn_id)
        self._commit_undo("删除连线")
        self.graph_changed.emit()

    # ========== 辅助方法 ==========

    def _find_socket(self, widget: NodeWidget, socket_name: str,
                     is_output: bool) -> Optional[SocketItem]:
        sockets = widget.output_sockets if is_output else widget.input_sockets
        for sock in sockets:
            if sock.socket_def.name == socket_name:
                return sock
        return None

    def _find_socket_at(self, pos: QPointF) -> Optional[SocketItem]:
        """在场景中查找某位置下的插口。"""
        items = self.items(pos)
        for item in items:
            if isinstance(item, SocketItem):
                return item
        return None

    def get_downstream_nodes(self, node_id: str) -> List[str]:
        """获取指定节点的所有下游节点（BFS）。"""
        downstream: List[str] = []
        visited: set = set()
        queue = [node_id]
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            if nid != node_id:
                downstream.append(nid)
            for conn in self.graph.connections.values():
                if conn.source_node_id == nid and conn.target_node_id not in visited:
                    queue.append(conn.target_node_id)
        return downstream

    def collect_all_inline_values(self) -> Dict[str, Dict[str, Any]]:
        """从场景中所有节点收集内嵌控件的值。"""
        vals: Dict[str, Dict[str, Any]] = {}
        for nid, widget in self.widget_map.items():
            inline = widget.get_all_inline_values()
            if inline:
                vals[nid] = inline
        return vals

    def persist_all_inline_values(self) -> None:
        """持久化所有节点的内嵌控件值回 node 模型。"""
        for nid, widget in self.widget_map.items():
            widget.persist_inline_values()

    def restore_inline_values(self) -> None:
        """从 node 模型恢复内嵌控件值到 UI。"""
        for nid, widget in self.widget_map.items():
            node = self.graph.get_node(nid)
            if node and node.inline_widget_values:
                for name, value in node.inline_widget_values.items():
                    widget.set_inline_value(name, value)

    # ========== 拖拽连接 ==========

    def start_drag_connection(self, socket: SocketItem) -> None:
        self._drag_source = socket
        self._drag_line = DragLine(socket.center_pos())
        self.addItem(self._drag_line)

    def update_drag_connection(self, pos: QPointF) -> None:
        if self._drag_line:
            self._drag_line.update_end(pos)

    def end_drag_connection(self, pos: QPointF) -> None:
        if not self._drag_source or not self._drag_line:
            self._cleanup_drag()
            return

        source_sock = self._drag_source
        target = self._find_socket_at(pos)
        if target and target != source_sock:
            src_is_out = source_sock.socket_def.direction.value == "output"
            tgt_is_in = target.socket_def.direction.value == "input"

            if src_is_out and tgt_is_in:
                conn = ConnectionModel(
                    source_node_id=source_sock.node_widget.node.node_id,
                    source_socket=source_sock.socket_def.name,
                    target_node_id=target.node_widget.node.node_id,
                    target_socket=target.socket_def.name,
                )
                self.add_connection_line(conn)
            elif not src_is_out and tgt_is_in:
                conn = ConnectionModel(
                    source_node_id=target.node_widget.node.node_id,
                    source_socket=target.socket_def.name,
                    target_node_id=source_sock.node_widget.node.node_id,
                    target_socket=source_sock.socket_def.name,
                )
                self.add_connection_line(conn)

        self._cleanup_drag()

    def _cleanup_drag(self) -> None:
        if self._drag_line:
            self.removeItem(self._drag_line)
            self._drag_line = None
        self._drag_source = None

    def update_all_connections(self) -> None:
        """更新所有连线位置（节点移动后调用）。"""
        for line in self.connection_lines.values():
            line.update_position()

    # ========== 分组框 ==========

    def group_selected_nodes(self, group_name: str = "分组") -> Optional[GroupBox]:
        """将选中的节点框入分组。"""
        selected = [item for item in self.selectedItems()
                    if isinstance(item, NodeWidget)]
        if len(selected) < 1:
            return None

        self._save_undo_point()
        group = GroupBox(group_name)
        for w in selected:
            group.add_child(w.node.node_id)
        group.recalc_rect(self)
        self.addItem(group)
        self.group_boxes.append(group)
        self._commit_undo(f"分组 {group_name}")
        self.graph_changed.emit()
        return group

    def ungroup(self, group_box: GroupBox) -> None:
        """解组分組。"""
        if group_box in self.group_boxes:
            self._save_undo_point()
            self.group_boxes.remove(group_box)
            self.removeItem(group_box)
            self._commit_undo("解组")
            self.graph_changed.emit()

    def find_group_at(self, pos: QPointF) -> Optional[GroupBox]:
        """查找位置下的分组框。"""
        for g in reversed(self.group_boxes):
            if g.boundingRect().contains(g.mapFromScene(pos)):
                return g
        return None

    # ========== 搜索 ==========

    def search_nodes(self, query: str) -> List[str]:
        """按名称搜索节点，返回匹配的 node_id 列表。"""
        self._search_matches = []
        self._search_index = -1
        if not query:
            # 清除高亮
            self._clear_search_highlight()
            return []

        query_lower = query.lower()
        matches = []
        for nid, widget in self.widget_map.items():
            node = self.graph.get_node(nid)
            if node and query_lower in node.name.lower():
                matches.append(nid)
                widget.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)

        self._search_matches = matches
        self._search_index = 0 if matches else -1

        # 高亮匹配
        self._highlight_search(clear_first=True)
        return matches

    def _highlight_search(self, clear_first: bool = False) -> None:
        """高亮当前搜索匹配的节点。"""
        for nid, widget in self.widget_map.items():
            if clear_first:
                widget.setSelected(False)
        if self._search_matches and self._search_index >= 0:
            nid = self._search_matches[self._search_index]
            widget = self.widget_map.get(nid)
            if widget:
                widget.setSelected(True)
                # 平移到视图
                view = self.views()[0] if self.views() else None
                if view:
                    view.centerOn(widget)

    def _clear_search_highlight(self) -> None:
        """清除所有搜索高亮。"""
        for widget in self.widget_map.values():
            widget.setSelected(False)

    def cycle_search(self, forward: bool = True) -> None:
        """循环搜索匹配结果。"""
        if not self._search_matches:
            return
        if forward:
            self._search_index = (self._search_index + 1) % len(self._search_matches)
        else:
            self._search_index = (self._search_index - 1) % len(self._search_matches)
        self._highlight_search(clear_first=True)

    # ========== 撤销/重做快照 (Fix: Ctrl+Z) ==========

    def _save_undo_point(self) -> None:
        """保存当前图状态作为 undo 快照起点（支持嵌套调用）。"""
        if self.undo_manager is not None:
            if self._undo_nest_counter == 0:
                self._undo_prev_state = self.graph.to_dict()
            self._undo_nest_counter += 1

    def _commit_undo(self, description: str = "") -> None:
        """提交 undo 快照（从 _save_undo_point 到当前状态的变化）。"""
        if self.undo_manager is not None:
            self._undo_nest_counter -= 1
            if self._undo_nest_counter == 0 and self._undo_prev_state is not None:
                curr = self.graph.to_dict()
                if self._undo_prev_state != curr:
                    from MayaNodeToolEditor.core.undo_manager import SnapshotCommand
                    cmd = SnapshotCommand(self._undo_prev_state, curr, description)
                    self.undo_manager.execute(cmd)
                self._undo_prev_state = None

    def restore_graph_from_dict(self, state: Dict[str, Any]) -> None:
        """完全替换图状态（undo/redo 快照恢复，不触发快照）。"""
        from MayaNodeToolEditor.core.node_graph import NodeGraph
        from MayaNodeToolEditor.ui.node_widget import NodeWidget

        # 清空当前场景项（保留背景）
        self.clear()
        self.widget_map.clear()
        self.connection_lines.clear()
        self.group_boxes.clear()

        # 加载新图
        self.graph = NodeGraph.from_dict(state)

        # 重建所有节点 widget
        for node in self.graph.nodes.values():
            widget = NodeWidget(node, self)
            self.addItem(widget)
            self.widget_map[node.node_id] = widget
            widget._relay.widget_changed.connect(self._on_widget_changed)

        # 重建所有连线
        for conn in self.graph.connections.values():
            src_w = self.widget_map.get(conn.source_node_id)
            tgt_w = self.widget_map.get(conn.target_node_id)
            if src_w and tgt_w:
                src_sock = self._find_socket(src_w, conn.source_socket, is_output=True)
                tgt_sock = self._find_socket(tgt_w, conn.target_socket, is_output=False)
                if src_sock and tgt_sock:
                    line = ConnectionLine(conn, src_sock, tgt_sock)
                    self.addItem(line)
                    self.connection_lines[conn.conn_id] = line

        # 确保起始节点存在（undo 到空图后自动补回）
        has_start = any(w.node.is_start_node for w in self.widget_map.values())
        if not has_start:
            from MayaNodeToolEditor.core.node import Node as NodeModel
            start = NodeModel("▶ 起点", category="系统")
            start.is_start_node = True
            start.color = "#2E7D32"
            start.code = "# 起始节点 — 执行从此开始"
            start.add_output("run", DataType.ANY, "执行入口")
            start.pos_x = -300
            start.pos_y = -150
            # 直接添加，不走 add_node_widget（避免触发 undo 快照）
            self.graph.add_node(start)
            widget = NodeWidget(start, self)
            self.addItem(widget)
            self.widget_map[start.node_id] = widget
            widget._relay.widget_changed.connect(self._on_widget_changed)

        self.graph_changed.emit()

    # ========== 复制/粘贴 ==========

    def copy_selected_nodes(self) -> Optional[str]:
        """复制选中节点到剪贴板（JSON）。"""
        selected = [item for item in self.selectedItems()
                    if isinstance(item, NodeWidget)]
        if not selected:
            return None

        # 收集节点数据及其连线
        node_ids = {w.node.node_id for w in selected}
        data = {
            "nodes": [w.node.to_dict() for w in selected],
            "connections": [
                conn.to_dict() for conn in self.graph.connections.values()
                if conn.source_node_id in node_ids
                and conn.target_node_id in node_ids
            ],
        }
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return text

    def paste_nodes(self, text: str, pos: Optional[QPointF] = None) -> List[str]:
        """从剪贴板 JSON 粘贴节点到场景。"""
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(data, dict) or "nodes" not in data:
            return []

        new_ids = []
        id_map: Dict[str, str] = {}  # old_id -> new_id

        for node_data in data.get("nodes", []):
            old_id = node_data.get("node_id", "")
            # 生成新 ID
            import uuid
            new_id = uuid.uuid4().hex[:12]
            id_map[old_id] = new_id
            node_data["node_id"] = new_id

            # 偏移位置避免重叠
            offset = QPointF(30, 30) if pos is None else QPointF(0, 0)
            node_data["pos_x"] = node_data.get("pos_x", 0) + offset.x()
            node_data["pos_y"] = node_data.get("pos_y", 0) + offset.y()

            node = NodeModel.from_dict(node_data)
            self.add_node_widget(node)
            new_ids.append(new_id)

        for conn_data in data.get("connections", []):
            old_src = conn_data.get("source_node_id", "")
            old_tgt = conn_data.get("target_node_id", "")
            if old_src in id_map and old_tgt in id_map:
                conn_data["source_node_id"] = id_map[old_src]
                conn_data["target_node_id"] = id_map[old_tgt]
                conn_data.pop("conn_id", None)
                conn = ConnectionModel.from_dict(conn_data)
                self.add_connection_line(conn)

        self.graph_changed.emit()
        return new_ids

    # ========== 执行状态追踪 ==========

    def set_executing_node(self, node_id: Optional[str]) -> None:
        """设置当前执行中的节点, None=清除"""
        self._executing_node_id = node_id
        for nid, widget in self.widget_map.items():
            if nid == node_id:
                widget.set_execution_status("running")
            elif getattr(widget, "_execution_status", "idle") != "idle":
                widget.set_execution_status("idle")
        if self.views():
            self.views()[0].viewport().update()

    def reset_execution_status(self) -> None:
        """清除所有节点的执行状态"""
        self._executing_node_id = None
        for widget in self.widget_map.values():
            widget.set_execution_status("idle")

    # ========== 事件处理 ==========

    def _schedule_persist_if_needed(self) -> None:
        """标记场景需要持久化（由外部保存时调用）。"""
        pass  # 外部在保存时调用 persist_all_inline_values

    def mouseDoubleClickEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        item = self.itemAt(event.scenePos(), QtGui.QTransform())
        if isinstance(item, NodeWidget):
            self.node_double_clicked.emit(item.node.node_id)
        elif isinstance(item, SocketItem):
            self.node_double_clicked.emit(item.node_widget.node.node_id)
        super().mouseDoubleClickEvent(event)


class SearchBarWidget(QtWidgets.QWidget):
    """节点搜索栏 — 在画布上方搜索节点。"""

    search_requested = Signal(str)  # query text
    cycle_forward = Signal()
    cycle_backward = Signal()
    close_requested = Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("""
            QWidget { background: #3E3E42; border: 1px solid #555;
                      border-radius: 0px; }
            QLineEdit {
                background: #1E1E1E; color: #CCC; border: 1px solid #555;
                padding: 3px 8px; border-radius: 3px; font-size: 12px;
            }
            QPushButton {
                background: #3E3E42; color: #CCC; border: 1px solid #555;
                padding: 3px 8px; border-radius: 3px; font-size: 11px;
            }
            QPushButton:hover { background: #505050; }
            QLabel { color: #888; font-size: 11px; }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        icon_lbl = QtWidgets.QLabel("🔍")
        layout.addWidget(icon_lbl)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("搜索节点...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self.search_requested.emit)
        self.search_input.returnPressed.connect(self.cycle_forward.emit)
        layout.addWidget(self.search_input)

        self.count_label = QtWidgets.QLabel("")
        self.count_label.setFixedWidth(40)
        layout.addWidget(self.count_label)

        prev_btn = QtWidgets.QPushButton("▲")
        prev_btn.setFixedWidth(24)
        prev_btn.clicked.connect(self.cycle_backward.emit)
        layout.addWidget(prev_btn)

        next_btn = QtWidgets.QPushButton("▼")
        next_btn.setFixedWidth(24)
        next_btn.clicked.connect(self.cycle_forward.emit)
        layout.addWidget(next_btn)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedWidth(24)
        close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(close_btn)

        layout.addStretch()

    def update_count(self, index: int, total: int) -> None:
        if total > 0:
            self.count_label.setText(f"{index + 1}/{total}")
        else:
            self.count_label.setText("0/0")


class NodeEditorView(QtWidgets.QGraphicsView):
    """节点编辑器视图（带滚轮缩放、右键平移、框选）。"""

    def __init__(self, scene: NodeEditorScene,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(scene, parent)
        self.editor_scene = scene
        self._is_panning = False
        self._last_mouse_pos = QPointF()
        self._is_connecting = False
        self._drag_socket: Optional[SocketItem] = None

        # 框选状态 (Fix 3)
        self._is_rubber_band = False
        self._rubber_band_origin = QPointF()
        self._rubber_band: Optional[QtWidgets.QRubberBand] = None

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.MinimalViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)

        self.setStyleSheet("""
            QGraphicsView {
                border: none;
                background: #1E1E1E;
            }
        """)

    def wheelEvent(self, event: QtWidgets.QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event: QtWidgets.QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())

        # ▶ 播放按钮点击（UI节点）
        if event.button() == Qt.LeftButton:
            item = self.editor_scene.itemAt(scene_pos, QtGui.QTransform())
            if isinstance(item, NodeWidget) and item.is_play_btn_at(scene_pos):
                self.editor_scene.node_run_requested.emit(item.node.node_id)
                event.accept()
                return

        # 左键点击空白处 → 框选 (Fix 3)
        if event.button() == Qt.LeftButton:
            item = self.editor_scene.itemAt(scene_pos, QtGui.QTransform())
            if item is None:
                # 空白处左键按下 → 开始框选
                self._is_rubber_band = True
                self._rubber_band_origin = event.pos()
                self._rubber_band = QtWidgets.QRubberBand(
                    QtWidgets.QRubberBand.Rectangle, self)
                self._rubber_band.setGeometry(
                    QtCore.QRect(event.pos(), QtCore.QSize()))
                self._rubber_band.show()
                event.accept()
                return

        # 右键菜单
        if event.button() == Qt.RightButton:
            item = self.editor_scene.itemAt(scene_pos, QtGui.QTransform())
            if isinstance(item, NodeWidget):
                self._show_node_context_menu(item, event.globalPos())
                event.accept()
                return
            elif isinstance(item, GroupBox):
                self._show_group_context_menu(item, event.globalPos())
                event.accept()
                return
            elif isinstance(item, ConnectionLine):
                self._show_connection_context_menu(item, event.globalPos())
                event.accept()
                return
            else:
                # 空白处右键：检查是否有选中的节点
                selected = [i for i in self.editor_scene.selectedItems()
                            if isinstance(i, NodeWidget)]
                if len(selected) > 1 or True:
                    self._show_canvas_context_menu(event.globalPos())
                    event.accept()
                    return

        # 检查是否点击了插口 — 开始连线
        item = self.editor_scene.itemAt(scene_pos, QtGui.QTransform())
        if event.button() == Qt.LeftButton and isinstance(item, SocketItem):
            self._is_connecting = True
            self._drag_socket = item
            self.editor_scene.start_drag_connection(item)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtWidgets.QMouseEvent) -> None:
        # 框选拖拽 (Fix 3)
        if self._is_rubber_band and self._rubber_band:
            rect = QtCore.QRect(self._rubber_band_origin, event.pos()).normalized()
            self._rubber_band.setGeometry(rect)
            event.accept()
            return

        if self._is_panning:
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._is_connecting:
            scene_pos = self.mapToScene(event.pos())
            self.editor_scene.update_drag_connection(scene_pos)
            event.accept()
            return

        super().mouseMoveEvent(event)
        # 性能优化：只更新被拖动节点的相关连线，不重建全部
        moving_items = [i for i in self.items() if isinstance(i, NodeWidget) and i.isMoving()]
        if moving_items:
            moving_ids = {w.node.node_id for w in moving_items}
            for cid, line in list(self.editor_scene.connection_lines.items()):
                if (line.conn.source_node_id in moving_ids or
                        line.conn.target_node_id in moving_ids):
                    line.update_position()

    def mouseReleaseEvent(self, event: QtWidgets.QMouseEvent) -> None:
        # 框选结束 (Fix 3)
        if self._is_rubber_band and self._rubber_band:
            self._is_rubber_band = False
            self._rubber_band.hide()
            self._rubber_band.deleteLater()
            self._rubber_band = None
            # 选中框内所有节点和连线
            rect = QtCore.QRect(self._rubber_band_origin, event.pos()).normalized()
            scene_rect = self.mapToScene(rect).boundingRect()
            for item in self.editor_scene.items(scene_rect):
                if isinstance(item, (NodeWidget, ConnectionLine)):
                    item.setSelected(True)
            event.accept()
            return

        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if self._is_connecting and event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self.editor_scene.end_drag_connection(scene_pos)
            self._is_connecting = False
            self._drag_socket = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    # ====== 右键菜单 ======

    def _show_node_context_menu(self, widget: NodeWidget,
                                global_pos: Any) -> None:
        """显示节点的右键上下文菜单。"""
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("""
            QMenu { background: #2D2D30; color: #CCC; border: 1px solid #555; }
            QMenu::item:selected { background: #094771; }
        """)

        # 起始节点：只可拖动，不可编辑
        if widget.node.is_start_node:
            info_action = menu.addAction("🟢 起始节点 — 执行入口，仅可拖动")
            info_action.setEnabled(False)
            menu.addSeparator()
            info_action2 = menu.addAction("不可编辑，不可删除")
            info_action2.setEnabled(False)
            menu.exec_(global_pos)
            return

        edit_action = menu.addAction("✏️ 编辑代码")
        edit_action.triggered.connect(
            lambda: self.editor_scene.node_double_clicked.emit(
                widget.node.node_id))

        menu.addSeparator()

        if widget.node.exec_mode == "ui":
            run_action = menu.addAction("▶ 直接运行此节点")
            run_action.triggered.connect(
                lambda: self.editor_scene.node_run_requested.emit(
                    widget.node.node_id))
            menu.addSeparator()

        copy_action = menu.addAction("📋 复制")
        copy_action.triggered.connect(
            lambda: self._copy_node_to_clipboard(widget))

        menu.addSeparator()

        # ▶ 从此运行（仅执行该节点及其下游，不保存标记）
        run_here_action = menu.addAction("▶ 从此运行")
        run_here_action.triggered.connect(
            lambda: self.editor_scene.node_run_requested.emit(
                widget.node.node_id))

        menu.addSeparator()

        delete_action = menu.addAction("🗑️ 删除")
        delete_action.triggered.connect(
            lambda: self.editor_scene.remove_node_widget(
                widget.node.node_id))

        menu.exec_(global_pos)

    def _show_group_context_menu(self, group: GroupBox,
                                 global_pos: Any) -> None:
        """分组框右键菜单。"""
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("""
            QMenu { background: #2D2D30; color: #CCC; border: 1px solid #555; }
            QMenu::item:selected { background: #094771; }
        """)

        rename_action = menu.addAction("✏️ 重命名分组")
        rename_action.triggered.connect(
            lambda: self._rename_group(group))

        ungroup_action = menu.addAction("解组")
        ungroup_action.triggered.connect(
            lambda: self.editor_scene.ungroup(group))

        delete_action = menu.addAction("🗑️ 删除分组（不解组）")
        delete_action.triggered.connect(
            lambda: self._delete_group_only(group))

        menu.exec_(global_pos)

    def _show_canvas_context_menu(self, global_pos: Any) -> None:
        """画布空白处右键菜单。"""
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("""
            QMenu { background: #2D2D30; color: #CCC; border: 1px solid #555; }
            QMenu::item:selected { background: #094771; }
        """)

        selected = [i for i in self.editor_scene.selectedItems()
                    if isinstance(i, NodeWidget)]
        if len(selected) >= 2:
            group_action = menu.addAction("📦 分组选中节点")
            group_action.triggered.connect(
                lambda: self.editor_scene.group_selected_nodes("新分组"))

        paste_action = menu.addAction("📋 粘贴")
        paste_action.triggered.connect(
            lambda: self._paste_from_clipboard())

        if menu.actions():
            menu.exec_(global_pos)

    def _rename_group(self, group: GroupBox) -> None:
        """重命名分组。"""
        new_name, ok = QtWidgets.QInputDialog.getText(
            None, "重命名分组", "分组名称:", text=group.group_title)
        if ok and new_name.strip():
            group.group_title = new_name.strip()
            group.update()

    def _delete_group_only(self, group: GroupBox) -> None:
        """仅删除分组框（不解组）。"""
        self.editor_scene.ungroup(group)

    def _copy_node_to_clipboard(self, widget: NodeWidget) -> None:
        """将节点数据复制到剪贴板（JSON 格式）。"""
        text = self.editor_scene.copy_selected_nodes()
        if text:
            try:
                clipboard = QtGui.QGuiApplication.clipboard()
                clipboard.setText(text)
            except Exception:
                pass

    def _paste_from_clipboard(self) -> None:
        """从剪贴板粘贴节点。"""
        try:
            clipboard = QtGui.QGuiApplication.clipboard()
            text = clipboard.text()
            scene_pos = self.mapToScene(self._last_mouse_pos)
            self.editor_scene.paste_nodes(text, scene_pos)
        except Exception:
            pass

    def _show_connection_context_menu(self, line: ConnectionLine,
                                      global_pos: Any) -> None:
        """连线右键菜单——删除连线。"""
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("""
            QMenu { background: #2D2D30; color: #CCC; border: 1px solid #555; }
            QMenu::item:selected { background: #094771; }
        """)

        # 显示从哪个节点到哪个节点
        src = self.editor_scene.graph.get_node(line.conn.source_node_id)
        tgt = self.editor_scene.graph.get_node(line.conn.target_node_id)
        src_name = src.name if src else "?"
        tgt_name = tgt.name if tgt else "?"
        info_action = menu.addAction(f"🔗 {src_name}.{line.conn.source_socket} → {tgt_name}.{line.conn.target_socket}")
        info_action.setEnabled(False)

        menu.addSeparator()

        delete_action = menu.addAction("❌ 删除连线")
        delete_action.triggered.connect(
            lambda: self.editor_scene.remove_connection_line(line.conn.conn_id))

        menu.exec_(global_pos)

    def keyPressEvent(self, event: QtWidgets.QKeyEvent) -> None:
        """键盘快捷键（Delete 删节点/连线，退格删、Ctrl+C/V 等由 main 处理）。"""
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            # 先删选中连线
            selected_lines = [item for item in self.editor_scene.selectedItems()
                              if isinstance(item, ConnectionLine)]
            for line in selected_lines:
                self.editor_scene.remove_connection_line(line.conn.conn_id)

            # 再删选中节点
            selected = [item for item in self.editor_scene.selectedItems()
                        if isinstance(item, NodeWidget)]
            for w in selected:
                self.editor_scene.remove_node_widget(w.node.node_id)
            event.accept()
            return
        super().keyPressEvent(event)
