"""
节点UI组件 — PySide2 QGraphicsItem 实现的视觉节点。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, QRectF, QPointF

from MayaNodeToolEditor.core.node import Node, Connection as NodeConnection
from MayaNodeToolEditor.core.types import DataType, SocketDirection, TYPE_COLORS

if TYPE_CHECKING:
    from MayaNodeToolEditor.ui.node_editor import NodeEditorScene


# 样式常量
NODE_WIDTH = 180
NODE_HEADER_H = 28
SOCKET_H = 22
SOCKET_RADIUS = 5
CORNER_RADIUS = 6


class SocketItem(QtWidgets.QGraphicsItem):
    """插口视觉组件（小圆点）。"""

    def __init__(self, socket_def: Any, node_widget: NodeWidget,
                 parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self.socket_def = socket_def
        self.node_widget = node_widget
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)

        self._rect = QRectF(-SOCKET_RADIUS, -SOCKET_RADIUS,
                            SOCKET_RADIUS * 2, SOCKET_RADIUS * 2)
        self._hovered = False

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        color = TYPE_COLORS.get(self.socket_def.data_type, "#9E9E9E")
        base_color = QtGui.QColor(color)

        if self._hovered:
            painter.setBrush(base_color.lighter(130))
            painter.setPen(QtGui.QPen(base_color.lighter(150), 2))
        else:
            painter.setBrush(base_color)
            painter.setPen(QtGui.QPen(base_color.darker(120), 1.5))

        painter.drawEllipse(self._rect)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def center_pos(self) -> QPointF:
        """返回插口的中心全局坐标（用于画连线）。"""
        return self.mapToScene(self._rect.center())


class NodeWidget(QtWidgets.QGraphicsItem):
    """
    单个节点的视觉组件。
    灰色圆角矩形 + 顶部标题栏 + 输入/输出插口列表。
    """

    def __init__(self, node: Node, scene: NodeEditorScene) -> None:
        super().__init__()
        self.node = node
        self.scene_ref = scene
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)

        # 子项：插口
        self.input_sockets: List[SocketItem] = []
        self.output_sockets: List[SocketItem] = []
        self._create_sockets()

        # 缓存高度（基于插口数量）
        self._height = NODE_HEADER_H + max(len(self.input_sockets), len(self.output_sockets), 1) * SOCKET_H + 10

        # 选中状态
        self._hovered = False

        self.setPos(node.pos_x, node.pos_y)

    def _create_sockets(self) -> None:
        for sock in self.node.inputs:
            item = SocketItem(sock, self, self)
            item.setPos(0, NODE_HEADER_H + len(self.input_sockets) * SOCKET_H)
            self.input_sockets.append(item)
        for sock in self.node.outputs:
            item = SocketItem(sock, self, self)
            item.setPos(NODE_WIDTH, NODE_HEADER_H + len(self.output_sockets) * SOCKET_H)
            self.output_sockets.append(item)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_WIDTH, self._height).adjusted(-2, -2, 2, 2)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QRectF(0, 0, NODE_WIDTH, self._height)

        # 阴影
        shadow = QtGui.QPainterPath()
        shadow.addRoundedRect(rect.translated(2, 2), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(shadow, QtGui.QColor(0, 0, 0, 40))

        # 主体背景
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
        painter.setPen(QtGui.QPen(QtGui.QColor("#555"), 1))
        if self.isSelected():
            painter.setBrush(QtGui.QColor("#2A5A8A"))
        elif self._hovered:
            painter.setBrush(QtGui.QColor("#444"))
        else:
            painter.setBrush(QtGui.QColor("#333"))
        painter.drawPath(path)

        # 标题栏
        header_rect = QRectF(0, 0, NODE_WIDTH, NODE_HEADER_H)
        header_path = QtGui.QPainterPath()
        header_path.addRoundedRect(header_rect, CORNER_RADIUS, CORNER_RADIUS)
        # 只保留顶部圆角
        body_rect = QRectF(0, NODE_HEADER_H, NODE_WIDTH, self._height - NODE_HEADER_H)
        body_path = QtGui.QPainterPath()
        body_path.addRect(QRectF(0, NODE_HEADER_H - 4, NODE_WIDTH, self._height - NODE_HEADER_H + 4))

        # 合并剪裁绘制标题
        header_clip = header_path.subtracted(body_path)
        painter.setClipPath(header_clip)
        color = QtGui.QColor(self.node.color)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(header_rect, CORNER_RADIUS, CORNER_RADIUS)
        painter.setClipping(False)

        # 标题文字
        painter.setPen(QtGui.QColor("#EEE"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(8, 0, -8, 0),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         self.node.name)

        # 输出插口标签（右对齐）
        painter.setPen(QtGui.QColor("#CCC"))
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        for i, sock in enumerate(self.node.outputs):
            y = NODE_HEADER_H + i * SOCKET_H + SOCKET_H // 2
            painter.drawText(QRectF(8, y - 8, NODE_WIDTH - 20, 16),
                             Qt.AlignRight | Qt.AlignVCenter,
                             sock.name)

        # 输入插口标签（左对齐）
        for i, sock in enumerate(self.node.inputs):
            y = NODE_HEADER_H + i * SOCKET_H + SOCKET_H // 2
            painter.drawText(QRectF(12, y - 8, NODE_WIDTH - 24, 16),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             sock.name)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        self.setCursor(Qt.OpenHandCursor)
        self.node.pos_x = self.pos().x()
        self.node.pos_y = self.pos().y()
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)
