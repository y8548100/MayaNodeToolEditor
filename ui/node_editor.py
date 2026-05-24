"""
节点图画布 — PySide2 QGraphicsView/QGraphicsScene 实现。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, QPointF, QRectF, Signal
from PySide2.QtGui import QPainter

from MayaNodeToolEditor.core.node import Node as NodeModel, Connection as ConnectionModel
from MayaNodeToolEditor.core.node_graph import NodeGraph
from MayaNodeToolEditor.ui.node_widget import NodeWidget, SocketItem, NODE_WIDTH, SOCKET_H, NODE_HEADER_H, SOCKET_RADIUS


class ConnectionLine(QtWidgets.QGraphicsPathItem):
    """节点间的连线（贝塞尔曲线）。"""

    def __init__(self, conn: ConnectionModel,
                 source_socket: SocketItem, target_socket: SocketItem) -> None:
        super().__init__()
        self.conn = conn
        self.source_socket = source_socket
        self.target_socket = target_socket
        self.setPen(QtGui.QPen(QtGui.QColor("#888"), 2))
        self.setBrush(Qt.NoBrush)
        self.setZValue(-1)
        self._update_path()

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

    node_selected = Signal(str)  # node_id
    node_double_clicked = Signal(str)  # node_id

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.graph = NodeGraph()
        self.widget_map: Dict[str, NodeWidget] = {}
        self.connection_lines: Dict[str, ConnectionLine] = {}
        self._drag_line: Optional[DragLine] = None
        self._drag_source: Optional[SocketItem] = None

        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setBackgroundBrush(QtGui.QColor("#1E1E1E"))

    def add_node_widget(self, node: NodeModel) -> NodeWidget:
        self.graph.add_node(node)
        widget = NodeWidget(node, self)
        self.addItem(widget)
        self.widget_map[node.node_id] = widget

        # 右键菜单
        widget.setAcceptHoverEvents(True)
        return widget

    def remove_node_widget(self, node_id: str) -> None:
        widget = self.widget_map.pop(node_id, None)
        if widget:
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

    def add_connection_line(self, conn: ConnectionModel) -> None:
        src_widget = self.widget_map.get(conn.source_node_id)
        tgt_widget = self.widget_map.get(conn.target_node_id)
        if not src_widget or not tgt_widget:
            return

        src_socket = self._find_socket(src_widget, conn.source_socket, is_output=True)
        tgt_socket = self._find_socket(tgt_widget, conn.target_socket, is_output=False)
        if not src_socket or not tgt_socket:
            return

        self.graph.add_connection(conn)
        line = ConnectionLine(conn, src_socket, tgt_socket)
        self.addItem(line)
        self.connection_lines[conn.conn_id] = line

    def remove_connection_line(self, conn_id: str) -> None:
        line = self.connection_lines.pop(conn_id, None)
        if line:
            self.removeItem(line)
        self.graph.remove_connection(conn_id)

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

        target = self._find_socket_at(pos)
        if target and target != self._drag_source:
            conn = ConnectionModel(
                source_node_id=target.node_widget.node.node_id
                    if target.socket_def.direction.value == "output"
                    else self._drag_source.node_widget.node.node_id,
                source_socket=target.socket_def.name
                    if target.socket_def.direction.value == "output"
                    else self._drag_source.socket_def.name,
                target_node_id=self._drag_source.node_widget.node.node_id
                    if target.socket_def.direction.value == "output"
                    else target.node_widget.node.node_id,
                target_socket=self._drag_source.socket_def.name
                    if target.socket_def.direction.value == "output"
                    else target.socket_def.name,
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

    def mouseDoubleClickEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        item = self.itemAt(event.scenePos(), QtGui.QTransform())
        if isinstance(item, NodeWidget):
            self.node_double_clicked.emit(item.node.node_id)
        elif isinstance(item, SocketItem):
            self.node_double_clicked.emit(item.node_widget.node.node_id)
        super().mouseDoubleClickEvent(event)


class NodeEditorView(QtWidgets.QGraphicsView):
    """节点编辑器视图（带滚轮缩放/右键平移）。"""

    def __init__(self, scene: NodeEditorScene,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(scene, parent)
        self.editor_scene = scene
        self._is_panning = False
        self._last_mouse_pos = QPointF()
        self._is_connecting = False
        self._drag_socket: Optional[SocketItem] = None

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
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

        # 检查是否点击了插口 → 开始连线
        scene_pos = self.mapToScene(event.pos())
        item = self.editor_scene.itemAt(scene_pos, QtGui.QTransform())
        if event.button() == Qt.LeftButton and isinstance(item, SocketItem):
            self._is_connecting = True
            self._drag_socket = item
            self.editor_scene.start_drag_connection(item)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtWidgets.QMouseEvent) -> None:
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
        # 节点拖动时更新连线
        self.editor_scene.update_all_connections()

    def mouseReleaseEvent(self, event: QtWidgets.QMouseEvent) -> None:
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
