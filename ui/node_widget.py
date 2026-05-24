from __future__ import annotations
"""
节点UI组件 — PySide2 QGraphicsItem + QGraphicsProxyWidget 实现的视觉节点。
支持内嵌控件（输入框、滑块、打印输出等）直接显示在节点上。
"""


import json
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, QRectF, QPointF, Signal

from MayaNodeToolEditor.core.node import Node, Connection as NodeConnection
from MayaNodeToolEditor.core.types import DataType, SocketDirection, TYPE_COLORS

if TYPE_CHECKING:
    from MayaNodeToolEditor.ui.node_editor import NodeEditorScene


# UI节点 — 按钮尺寸
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
INLINE_H_TALL = 60   # 多行文本等较高控件的行高


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

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        # 阻止事件冒泡到节点 widget（避免拖拽节点时触发移动）
        if event.button() == Qt.LeftButton:
            event.accept()
        else:
            super().mousePressEvent(event)


# ======================== 内嵌控件信号中继 ========================

class InlineSignalRelay(QtCore.QObject):
    """QGraphicsItem 内信号中继（QGraphicsItem 不能直接发射 signal）。"""
    widget_changed = Signal(str, str)  # node_id, widget_name


# ======================== 分组框 ========================

class GroupBox(QtWidgets.QGraphicsItem):
    """节点分组框 — 将多个节点框在一起，整体移动。"""

    def __init__(self, title: str = "分组", parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self.group_title = title
        self.child_nodes: List[str] = []  # node_ids
        self._rect = QRectF(0, 0, 200, 100)
        self._padding = 30
        self._title_h = 24
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(-10)  # 在节点下层
        self._hovered = False
        self._collapsed = False

    def add_child(self, node_id: str) -> None:
        if node_id not in self.child_nodes:
            self.child_nodes.append(node_id)

    def remove_child(self, node_id: str) -> None:
        if node_id in self.child_nodes:
            self.child_nodes.remove(node_id)

    def contains_node(self, node_id: str) -> bool:
        return node_id in self.child_nodes

    def recalc_rect(self, scene: NodeEditorScene) -> None:
        """根据子节点位置重新计算分组框大小。"""
        if not self.child_nodes:
            return
        xs = []
        ys = []
        for nid in self.child_nodes:
            w = scene.widget_map.get(nid)
            if w:
                p = w.pos()
                xs.append(p.x())
                ys.append(p.y())
                xs.append(p.x() + NODE_WIDTH)
                ys.append(p.y() + w._height)
        if not xs:
            return
        min_x = min(xs) - self._padding
        min_y = min(ys) - self._padding - self._title_h
        max_x = max(xs) + self._padding
        max_y = max(ys) + self._padding
        self._rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        self.setPos(0, 0)  # 分组框自身不偏移，子节点在场景中绝对定位
        # 将分组框移到所有子节点的上层
        self.setZValue(-10)

    def update_child_positions(self, scene: NodeEditorScene) -> None:
        """分组框移动后，同步移动子节点。"""
        # GroupBox 本身不移动子节点——我们只提供可视化分组
        pass

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-4, -4, 4, 4)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self._rect

        # 背景
        bg = QtGui.QColor("#2A3A4A" if self._hovered else "#1E2A3A")
        bg.setAlpha(80)
        painter.setBrush(bg)
        pen_color = QtGui.QColor("#4FC1FF" if self._hovered else "#3A6EA5")
        painter.setPen(QtGui.QPen(pen_color, 1.5, Qt.DashLine))
        painter.drawRoundedRect(rect, 8, 8)

        # 标题栏
        title_rect = QRectF(rect.x(), rect.y(), rect.width(), self._title_h)
        painter.setBrush(QtGui.QColor("#2A3A4A"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(title_rect, 8, 8)
        # 填平底部
        painter.drawRect(QRectF(rect.x(), rect.y() + 4, rect.width(), self._title_h - 4))

        # 标题文字
        painter.setPen(QtGui.QColor("#4FC1FF"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(title_rect.adjusted(8, 0, -8, 0),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         self.group_title)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)


# ======================== 节点 Widget ========================

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

        # 信号中继 — scene 连接此信号处理联动
        self._relay = InlineSignalRelay()

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

        # UI 节点 — 按钮区域（右上角）
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

            # Check if we have a persisted value
            persisted = self.node.inline_widget_values.get(name)
            if persisted is not None:
                cfg = dict(cfg)
                cfg["default"] = persisted

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
        """根据类型创建实际 Qt 控件，并连接变化信号。"""
        node_id = self.node.node_id

        if wtype == "line_edit":
            le = QtWidgets.QLineEdit(str(default) if default is not None else "")
            le.setStyleSheet(_INLINE_EDIT_STYLE)
            le.textChanged.connect(
                lambda text, nid=node_id, wn=name: self._emit_change(nid, wn))
            return le

        elif wtype == "spin_box":
            sb = QtWidgets.QSpinBox()
            sb.setRange(int(cfg.get("min", -9999)), int(cfg.get("max", 9999)))
            sb.setValue(int(default) if default is not None else 0)
            sb.setStyleSheet(_INLINE_EDIT_STYLE)
            sb.valueChanged.connect(
                lambda val, nid=node_id, wn=name: self._emit_change(nid, wn))
            return sb

        elif wtype == "double_spin":
            dsb = QtWidgets.QDoubleSpinBox()
            dsb.setRange(float(cfg.get("min", -9999)), float(cfg.get("max", 9999)))
            dsb.setDecimals(3)
            dsb.setValue(float(default) if default is not None else 0.0)
            dsb.setStyleSheet(_INLINE_EDIT_STYLE)
            dsb.valueChanged.connect(
                lambda val, nid=node_id, wn=name: self._emit_change(nid, wn))
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
            slider.valueChanged.connect(
                lambda val, nid=node_id, wn=name: self._emit_change(nid, wn))
            layout.addWidget(slider)
            layout.addWidget(value_lbl)
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
            combo.currentTextChanged.connect(
                lambda text, nid=node_id, wn=name: self._emit_change(nid, wn))
            return combo

        elif wtype == "check_box":
            cb_label = cfg.get("label", "") or name
            cb = QtWidgets.QCheckBox(cb_label)
            cb.setChecked(bool(default))
            cb.setStyleSheet("color: #CCC; spacing: 4px;")
            cb.stateChanged.connect(
                lambda state, nid=node_id, wn=name: self._emit_change(nid, wn))
            return cb

        elif wtype == "button":
            btn_label = cfg.get("label", "") or name
            btn = QtWidgets.QPushButton(btn_label)
            btn.setStyleSheet(_INLINE_BUTTON_STYLE)
            btn.clicked.connect(
                lambda checked, nid=node_id, wn=name: self._emit_change(nid, wn))
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

        # ====== Phase 5: 新控件类型 ======

        elif wtype == "color_picker":
            container = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(container)
            layout.setContentsMargins(4, 0, 4, 0)
            color_btn = QtWidgets.QPushButton()
            initial_color = str(default) if default else "#4FC1FF"
            color_btn.setStyleSheet(
                f"QPushButton {{ background: {initial_color}; border: 1px solid #777; "
                f"border-radius: 3px; min-width: 30px; min-height: 20px; }}"
                f"QPushButton:hover {{ border-color: #4FC1FF; }}")
            color_label = QtWidgets.QLabel(initial_color)
            color_label.setStyleSheet("color: #CCC; font-size: 10px;")
            color_label.setFixedWidth(70)

            def pick_color(btn=color_btn, lbl=color_label, nid=node_id, wn=name):
                from PySide2 import QtGui
                initial = QtGui.QColor(btn.property("current_color") or initial_color)
                color = QtWidgets.QColorDialog.getColor(initial, None, "选择颜色")
                if color.isValid():
                    hex_color = color.name()
                    btn.setProperty("current_color", hex_color)
                    btn.setStyleSheet(
                        f"QPushButton {{ background: {hex_color}; border: 1px solid #777; "
                        f"border-radius: 3px; min-width: 30px; min-height: 20px; }}"
                        f"QPushButton:hover {{ border-color: #4FC1FF; }}")
                    lbl.setText(hex_color)
                    self._emit_change(nid, wn)

            color_btn.clicked.connect(pick_color)
            color_btn.setProperty("current_color", initial_color)
            layout.addWidget(color_btn)
            layout.addWidget(color_label)
            layout.addStretch()
            return container

        elif wtype == "file_browser":
            container = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(container)
            layout.setContentsMargins(4, 0, 4, 0)
            le = QtWidgets.QLineEdit(str(default) if default else "")
            le.setStyleSheet(_INLINE_EDIT_STYLE)
            le.setReadOnly(True)
            browse_btn = QtWidgets.QPushButton("📁")
            browse_btn.setFixedWidth(24)
            browse_btn.setStyleSheet("QPushButton { background: #3E3E42; border: 1px solid #555; "
                                      "border-radius: 3px; padding: 2px; font-size: 12px; }"
                                      "QPushButton:hover { background: #505050; }")

            def browse_file(line_edit=le, nid=node_id, wn=name):
                path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    None, "选择文件", le.text() or "")
                if path:
                    line_edit.setText(path)
                    self._emit_change(nid, wn)

            browse_btn.clicked.connect(browse_file)
            layout.addWidget(le)
            layout.addWidget(browse_btn)
            return container

        elif wtype == "plain_text":
            pte = QtWidgets.QPlainTextEdit(str(default) if default else "")
            pte.setMaximumHeight(50)
            pte.setStyleSheet("""
                QPlainTextEdit { background: #1E1E1E; color: #CCC;
                                 border: 1px solid #555; border-radius: 3px;
                                 padding: 2px; font-size: 10px; }
            """)
            pte.textChanged.connect(
                lambda nid=node_id, wn=name: self._emit_change(nid, wn))
            return pte

        return None

    def _emit_change(self, node_id: str, widget_name: str) -> None:
        """发射内嵌控件变化信号（由信号中继转发到 scene）。"""
        self._relay.widget_changed.emit(node_id, widget_name)

    def _position_inline_widgets(self) -> None:
        """根据 socket 区域底部和内嵌控件数量计算位置。"""
        sock_bottom = NODE_HEADER_H + max(
            len(self.input_sockets), len(self.output_sockets), 1) * SOCKET_H
        y = sock_bottom + INLINE_Y_PAD

        for i, proxy in enumerate(self._proxy_widgets):
            cfg = self.node.inline_widgets[i] if i < len(self.node.inline_widgets) else {}
            widget_type = cfg.get("type", "line_edit")

            # 位置
            margin_x = 8
            widget_w = NODE_WIDTH - margin_x * 2
            proxy.setPos(margin_x, y)
            proxy.widget().setFixedWidth(int(widget_w))

            if widget_type in ("plain_text",):
                y += INLINE_H_TALL
            elif widget_type in ("color_picker", "file_browser"):
                y += INLINE_H - 4  # slightly shorter
            else:
                y += INLINE_H

    def _recalc_height(self) -> None:
        """根据插口数 + 内嵌控件数计算节点高度。"""
        sock_area = NODE_HEADER_H + max(
            len(self.input_sockets), len(self.output_sockets), 1) * SOCKET_H
        inline_area = 0
        for cfg in self.node.inline_widgets:
            wtype = cfg.get("type", "line_edit")
            if wtype == "plain_text":
                inline_area += INLINE_H_TALL
            elif wtype in ("color_picker", "file_browser"):
                inline_area += INLINE_H - 4
            else:
                inline_area += INLINE_H
        if inline_area > 0:
            inline_area += INLINE_Y_PAD
        self._height = sock_area + inline_area + 6  # bottom padding

    # ========== 控件值读取 ==========

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
        if isinstance(widget, QtWidgets.QPlainTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QtWidgets.QPushButton):
            # color picker 按钮：查属性
            color = widget.property("current_color")
            if color:
                return color
            return True  # 被点击过
        if isinstance(widget, QtWidgets.QWidget):
            # 容器控件：找 QLabel 的内容（color_picker）
            for child in widget.findChildren(QtWidgets.QLabel):
                text = child.text()
                if text.startswith("#"):
                    return text
            # file_browser: 找 QLineEdit
            for child in widget.findChildren(QtWidgets.QLineEdit):
                return child.text()
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
        elif isinstance(widget, QtWidgets.QPlainTextEdit):
            widget.setPlainText(str(value) if value is not None else "")
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(str(value) if value is not None else "")
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value) if value is not None else 0)
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setValue(float(value) if value is not None else 0.0)
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentText(str(value) if value is not None else "")
        elif isinstance(widget, QtWidgets.QPushButton):
            # color picker 按钮
            if value and isinstance(value, str) and value.startswith("#"):
                widget.setProperty("current_color", value)
                widget.setStyleSheet(
                    f"QPushButton {{ background: {value}; border: 1px solid #777; "
                    f"border-radius: 3px; min-width: 30px; min-height: 20px; }}"
                    f"QPushButton:hover {{ border-color: #4FC1FF; }}")
                # 更新旁边的标签
                parent_w = widget.parentWidget()
                if parent_w:
                    for child in parent_w.findChildren(QtWidgets.QLabel):
                        child.setText(value)
        elif isinstance(widget, QtWidgets.QWidget):
            # 容器控件：file_browser 的 QLineEdit
            for child in widget.findChildren(QtWidgets.QLineEdit):
                child.setText(str(value) if value is not None else "")
                break

    def get_all_inline_values(self) -> Dict[str, Any]:
        """读取所有内嵌控件的值。"""
        return {name: self.get_inline_value(name)
                for name in self._inline_controls}

    def persist_inline_values(self) -> None:
        """将内嵌控件值存回 node.inline_widget_values（持久化用）。"""
        self.node.inline_widget_values = self.get_all_inline_values()

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
            if label and wtype not in ("check_box", "color_picker", "file_browser"):
                sock_bottom = NODE_HEADER_H + max(
                    len(self.input_sockets), len(self.output_sockets), 1) * SOCKET_H
                lbl_y = sock_bottom + INLINE_Y_PAD + i * INLINE_H + 4
                painter.setPen(QtGui.QColor("#999"))
                painter.drawText(QRectF(10, lbl_y, NODE_WIDTH - 20, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, label)

        # UI 节点 — 播放按钮
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
        # 持久化：移动后保存位置
        self.scene_ref._schedule_persist_if_needed()
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    # ====== UI 节点 — 直接运行按钮 ======

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

        # ▶ 三角
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
