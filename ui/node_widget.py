from __future__ import annotations
"""
节点UI组件 — PySide2 QGraphicsItem + QGraphicsProxyWidget 实现的视觉节点。
支持内嵌控件（输入框、滑块、打印输出等）直接显示在节点上。
"""


from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, QRectF, QPointF

from MayaNodeToolEditor.core.node import Node, Connection as NodeConnection
from MayaNodeToolEditor.core.types import DataType, SocketDirection, TYPE_COLORS

if TYPE_CHECKING:
    from MayaNodeToolEditor.ui.node_editor import NodeEditorScene


# UI节点 ▶ 按钮尺寸
UI_BTN_SIZE = 20
UI_BTN_MARGIN = 4

# 样式常量
NODE_WIDTH = 180
NODE_HEADER_H = 28
SOCKET_H = 22
SOCKET_RADIUS = 5
CORNER_RADIUS = 6

# 内嵌控件区域
INLINE_Y_PAD = 4     # 插口区域底部到内嵌控件顶部的间距
INLINE_H = 28        # 每个内嵌控件行高


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
    灰色圆角矩形 + 顶部标题栏 + 输入/输出插口列表 + 内嵌控件区域。
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

        # 内嵌控件代理
        self._proxy_widgets: List[QtWidgets.QGraphicsProxyWidget] = []
        self._inline_controls: Dict[str, QtWidgets.QWidget] = {}
        self._create_inline_widgets()

        # 计算高度
        self._recalc_height()

        # UI 节点 ▶ 按钮区域（右上角）
        self._play_btn_rect = self._get_play_rect() if node.exec_mode == "ui" else None

        # 选中状态
        self._hovered = False
        self._is_moving = False

        self.setPos(node.pos_x, node.pos_y)

    # ========== 内嵌控件 ==========

    def _create_inline_widgets(self) -> None:
        """根据 node.inline_widgets 创建内嵌控件。"""
        for cfg in self.node.inline_widgets:
            wtype = cfg.get("type", "line_edit")
            name = cfg.get("name", "widget")
            default = cfg.get("default", "")
            label = cfg.get("label", "")
            widget = self._build_widget(wtype, name, default, cfg)
            if widget is None:
                continue

            # 创建代理嵌入场景
            proxy = QtWidgets.QGraphicsProxyWidget(self)
            proxy.setWidget(widget)
            proxy.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
            proxy.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
            self._proxy_widgets.append(proxy)
            self._inline_controls[name] = widget

        self._position_inline_widgets()

    def _build_widget(
        self, wtype: str, name: str, default: Any, cfg: Dict[str, Any]
    ) -> Optional[QtWidgets.QWidget]:
        """根据类型创建实际 Qt 控件。"""
        if wtype == "line_edit":
            le = QtWidgets.QLineEdit(str(default) if default is not None else "")
            le.setStyleSheet(_INLINE_EDIT_STYLE)
            return le

        elif wtype == "spin_box":
            sb = QtWidgets.QSpinBox()
            sb.setRange(int(cfg.get("min", -9999)), int(cfg.get("max", 9999)))
            sb.setValue(int(default) if default is not None else 0)
            sb.setStyleSheet(_INLINE_EDIT_STYLE)
            return sb

        elif wtype == "double_spin":
            dsb = QtWidgets.QDoubleSpinBox()
            dsb.setRange(float(cfg.get("min", -9999)), float(cfg.get("max", 9999)))
            dsb.setDecimals(3)
            dsb.setValue(float(default) if default is not None else 0.0)
            dsb.setStyleSheet(_INLINE_EDIT_STYLE)
            return dsb

        elif wtype == "slider":
            container = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(container)
            layout.setContentsMargins(4, 0, 4, 0)
            slider = QtWidgets.QSlider(Qt.Horizontal)
            slider.setRange(int(cfg.get("min", 0)), int(cfg.get("max", 100)))
            slider.setValue(int(default) if default is not None else 50)
            value_lbl = QtWidgets.QLabel(str(int(default) if default is not None else 50))
            value_lbl.setFixedWidth(24)
            value_lbl.setStyleSheet("color: #CCC; font-size: 10px;")
            slider.valueChanged.connect(
                lambda v, lb=value_lbl: lb.setText(str(v)))
            layout.addWidget(slider)
            layout.addWidget(value_lbl)
            # 存值引用
            container._slider = slider
            container._value_lbl = value_lbl
            return container

        elif wtype == "combo":
            combo = QtWidgets.QComboBox()
            options = cfg.get("options", ["A", "B", "C"])
            combo.addItems([str(o) for o in options])
            if default is not None and str(default) in [str(o) for o in options]:
                combo.setCurrentText(str(default))
            combo.setStyleSheet(_INLINE_COMBO_STYLE)
            return combo

        elif wtype == "check_box":
            cb = QtWidgets.QCheckBox(label or name)
            cb.setChecked(bool(default))
            cb.setStyleSheet("color: #CCC; spacing: 4px;")
            return cb

        elif wtype == "button":
            btn = QtWidgets.QPushButton(label or name)
            btn.setStyleSheet(_INLINE_BUTTON_STYLE)
            return btn

        elif wtype == "text_display":
            te = QtWidgets.QTextEdit()
            te.setReadOnly(True)
            te.setPlaceholderText(str(default) if default else "")
            te.setMaximumHeight(60)
            te.setStyleSheet("""
                QTextEdit { background: #1E1E1E; color: #4FC1FF;
                            border: 1px solid #555; border-radius: 3px;
                            padding: 2px; font-size: 10px; }
            """)
            return te

        return None

    def _position_inline_widgets(self) -> None:
        """根据 socket 区域底部和内嵌控件数量计算位置。"""
        sock_bottom = NODE_HEADER_H + max(
            len(self.input_sockets), len(self.output_sockets), 1) * SOCKET_H
        y = sock_bottom + INLINE_Y_PAD

        for i, proxy in enumerate(self._proxy_widgets):
            cfg = self.node.inline_widgets[i] if i < len(self.node.inline_widgets) else {}
            widget_type = cfg.get("type", "line_edit")
            label = cfg.get("label", "")

            # 有 label 的控件（check_box 自带 label）
            if label and widget_type != "check_box":
                label_item = QtWidgets.QLabel(label + ":")
                label_item.setStyleSheet("color: #999; font-size: 10px;")
                # 放在 proxy 前面——用另一个 proxy
                # 简单方案：不用 label proxy，直接把 label 画在 paint 里
                pass

            # 位置
            margin_x = 8
            widget_w = NODE_WIDTH - margin_x * 2
            proxy.setPos(margin_x, y)
            proxy.widget().setFixedWidth(int(widget_w))
            y += INLINE_H

    def _recalc_height(self) -> None:
        """根据插口数 + 内嵌控件数计算节点高度。"""
        sock_area = NODE_HEADER_H + max(
            len(self.input_sockets), len(self.output_sockets), 1) * SOCKET_H
        inline_area = len(self._proxy_widgets) * INLINE_H
        if inline_area > 0:
            inline_area += INLINE_Y_PAD
        self._height = sock_area + inline_area + 6  # bottom padding

    # ========== 控件值读写 ==========

    def get_inline_value(self, name: str) -> Any:
        """读取内嵌控件的当前值。"""
        widget = self._inline_controls.get(name)
        if widget is None:
            return None

        # 从容器里找子控件（如 slider 容器）
        if hasattr(widget, '_slider'):
            return widget._slider.value()

        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        if isinstance(widget, QtWidgets.QSpinBox):
            return widget.value()
        if isinstance(widget, QtWidgets.QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentText()
        if isinstance(widget, QtWidgets.QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QtWidgets.QTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QtWidgets.QPushButton):
            return True  # 被点击过
        return None

    def set_inline_value(self, name: str, value: Any) -> None:
        """设置内嵌控件的值（如打印节点的输出显示）。"""
        widget = self._inline_controls.get(name)
        if widget is None:
            return

        if hasattr(widget, '_slider'):
            widget._slider.setValue(int(value) if value is not None else 0)
        elif isinstance(widget, QtWidgets.QTextEdit):
            widget.setText(str(value) if value is not None else "")
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(str(value) if value is not None else "")
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value) if value is not None else 0)
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setValue(float(value) if value is not None else 0.0)
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentText(str(value) if value is not None else "")

    def get_all_inline_values(self) -> Dict[str, Any]:
        """读取所有内嵌控件的值。"""
        return {name: self.get_inline_value(name)
                for name in self._inline_controls}

    # ========== 标准 QGraphicsItem 方法 ==========

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
                   value: Any) -> Any:
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self._is_moving = True
        elif change == QtWidgets.QGraphicsItem.ItemPositionChange:
            self._is_moving = True
        return super().itemChange(change, value)

    def isMoving(self) -> bool:
        return self._is_moving

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._is_moving = False
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

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
        body_rect = QRectF(0, NODE_HEADER_H, NODE_WIDTH, self._height - NODE_HEADER_H)
        body_path = QtGui.QPainterPath()
        body_path.addRect(QRectF(0, NODE_HEADER_H - 4, NODE_WIDTH, self._height - NODE_HEADER_H + 4))
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

        # 内嵌控件标签（在代理上方绘制）
        for i, cfg in enumerate(self.node.inline_widgets):
            label = cfg.get("label", "")
            wtype = cfg.get("type", "")
            if label and wtype != "check_box":
                sock_bottom = NODE_HEADER_H + max(
                    len(self.input_sockets), len(self.output_sockets), 1) * SOCKET_H
                lbl_y = sock_bottom + INLINE_Y_PAD + i * INLINE_H + 4
                painter.setPen(QtGui.QColor("#999"))
                painter.drawText(QRectF(10, lbl_y, NODE_WIDTH - 20, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, label)

        # UI 节点 ▶ 播放按钮
        self.paint_play_btn(painter)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        self._is_moving = False
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

    # ====== UI 节点 ▶ 直接运行按钮 ======

    def _get_play_rect(self) -> QRectF:
        """返回 ▶ 按钮区域（标题栏右上角）。"""
        return QRectF(
            NODE_WIDTH - UI_BTN_SIZE - UI_BTN_MARGIN,
            UI_BTN_MARGIN,
            UI_BTN_SIZE,
            UI_BTN_SIZE,
        )

    def is_play_btn_at(self, scene_pos: QPointF) -> bool:
        """检查场景坐标是否落在 ▶ 按钮上。"""
        if not self._play_btn_rect:
            return False
        local = self.mapFromScene(scene_pos)
        return self._play_btn_rect.contains(local)

    def paint_play_btn(self, painter: QtGui.QPainter) -> None:
        """绘制 ▶ 播放按钮（仅 UI 节点）。"""
        if not self._play_btn_rect:
            return
        r = self._play_btn_rect
        painter.setBrush(QtGui.QColor("#4CAF50"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(r, 4, 4)

        # ▶ 三角形
        cx = r.x() + r.width() * 0.45
        cy = r.y() + r.height() * 0.5
        size = r.width() * 0.35
        painter.setBrush(QtGui.QColor("#FFF"))
        triangle = QtGui.QPainterPath()
        triangle.moveTo(cx - size * 0.4, cy - size * 0.6)
        triangle.lineTo(cx + size * 0.4, cy)
        triangle.lineTo(cx - size * 0.4, cy + size * 0.6)
        triangle.closeSubpath()
        painter.drawPath(triangle)


# ====== 内嵌控件样式 ======

_INLINE_EDIT_STYLE = """
    QLineEdit, QSpinBox, QDoubleSpinBox {
        background: #3E3E42; color: #CCC; border: 1px solid #555;
        padding: 2px 4px; border-radius: 3px; font-size: 11px;
    }
"""

_INLINE_COMBO_STYLE = """
    QComboBox {
        background: #3E3E42; color: #CCC; border: 1px solid #555;
        padding: 2px 4px; border-radius: 3px; font-size: 11px;
    }
    QComboBox::drop-down { border: none; width: 16px; }
    QComboBox QAbstractItemView {
        background: #2D2D30; color: #CCC; border: 1px solid #555;
        selection-background-color: #094771;
    }
"""

_INLINE_BUTTON_STYLE = """
    QPushButton {
        background: #007ACC; color: white; border: none;
        padding: 4px 12px; border-radius: 3px; font-size: 11px;
    }
    QPushButton:hover { background: #1A8AD4; }
"""
