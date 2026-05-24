from __future__ import annotations
"""
工具运行面板 — 根据工具图的 UI 规格自动生成参数表单，
填参数 → 执行 → 看结果。通用组件，适用于所有工具。
"""

import json
import os
import traceback
from typing import Any, Dict, List, Optional

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, Signal

from MayaNodeToolEditor.core.executor import Executor
from MayaNodeToolEditor.core.node_graph import NodeGraph
from MayaNodeToolEditor.core.tool_ui import (
    UiInput, UiOutput, UiSpec,
    derive_ui_spec,
)


# ====== 控件工厂 ======

def _create_form_widget(ui_input: UiInput, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """根据 UiInput 的 widget_type 创建对应的 Qt 控件。"""
    widget_type = ui_input.widget_type

    if widget_type == "spin_box":
        w = QtWidgets.QSpinBox(parent)
        w.setRange(-999999, 999999)
        if ui_input.default is not None:
            try:
                w.setValue(int(ui_input.default))
            except (ValueError, TypeError):
                w.setValue(0)
        w.setMinimumWidth(200)

    elif widget_type == "double_spin_box":
        w = QtWidgets.QDoubleSpinBox(parent)
        w.setRange(-999999.0, 999999.0)
        w.setDecimals(3)
        if ui_input.default is not None:
            try:
                w.setValue(float(ui_input.default))
            except (ValueError, TypeError):
                w.setValue(0.0)
        w.setMinimumWidth(200)

    elif widget_type == "check_box":
        w = QtWidgets.QCheckBox(ui_input.name, parent)
        if ui_input.default:
            w.setChecked(bool(ui_input.default))
        # 给 check_box 添加特殊标记，form 遍历时跳过名字
        w._is_checkbox = True
        return w

    elif widget_type == "plain_text_edit":
        w = QtWidgets.QPlainTextEdit(parent)
        if ui_input.default is not None:
            w.setPlainText(str(ui_input.default))
        w.setMinimumHeight(60)
        w.setMaximumHeight(120)

    elif widget_type == "file_browser":
        w = _FileBrowserWidget(parent)
        if ui_input.default is not None:
            w.set_path(str(ui_input.default))

    elif widget_type == "color_picker":
        w = _ColorPickerWidget(parent)
        if ui_input.default is not None:
            w.set_color(str(ui_input.default))

    else:  # line_edit 及其他
        w = QtWidgets.QLineEdit(parent)
        if ui_input.default is not None:
            w.setText(str(ui_input.default))
        w.setPlaceholderText(ui_input.description)
        w.setMinimumWidth(200)

    return w


def _get_widget_value(widget: QtWidgets.QWidget) -> Any:
    """从控件提取当前值。"""
    if isinstance(widget, QtWidgets.QLineEdit):
        return widget.text()
    elif isinstance(widget, QtWidgets.QSpinBox):
        return widget.value()
    elif isinstance(widget, QtWidgets.QDoubleSpinBox):
        return widget.value()
    elif isinstance(widget, QtWidgets.QCheckBox):
        return widget.isChecked()
    elif isinstance(widget, QtWidgets.QPlainTextEdit):
        return widget.toPlainText()
    elif hasattr(widget, 'get_path'):
        return widget.get_path()
    elif hasattr(widget, 'get_color'):
        return widget.get_color()
    return ""


def _set_widget_value(widget: QtWidgets.QWidget, value: Any) -> None:
    """设置控件的值。"""
    if isinstance(widget, QtWidgets.QLineEdit):
        widget.setText(str(value) if value is not None else "")
    elif isinstance(widget, QtWidgets.QSpinBox):
        try:
            widget.setValue(int(value))
        except (ValueError, TypeError):
            pass
    elif isinstance(widget, QtWidgets.QDoubleSpinBox):
        try:
            widget.setValue(float(value))
        except (ValueError, TypeError):
            pass
    elif isinstance(widget, QtWidgets.QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, QtWidgets.QPlainTextEdit):
        widget.setPlainText(str(value) if value is not None else "")


# ====== 自定义控件 ======

class _FileBrowserWidget(QtWidgets.QWidget):
    """文件选择控件：文本框 + 浏览按钮。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._line = QtWidgets.QLineEdit()
        self._line.setPlaceholderText("选择文件...")
        btn = QtWidgets.QPushButton("...")
        btn.setFixedWidth(30)
        btn.clicked.connect(self._browse)
        layout.addWidget(self._line)
        layout.addWidget(btn)

    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择文件")
        if path:
            self._line.setText(path)

    def set_path(self, path: str) -> None:
        self._line.setText(path)

    def get_path(self) -> str:
        return self._line.text()


class _ColorPickerWidget(QtWidgets.QWidget):
    """颜色选取控件：色块按钮 + 颜色选择器。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._color = QtGui.QColor("#FFFFFF")
        self._btn = QtWidgets.QPushButton()
        self._btn.setFixedSize(40, 24)
        self._btn.clicked.connect(self._pick)
        self._label = QtWidgets.QLabel("#FFFFFF")
        layout.addWidget(self._btn)
        layout.addWidget(self._label)
        self._update_preview()

    def _pick(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self._color, self, "选择颜色")
        if color.isValid():
            self._color = color
            self._update_preview()

    def _update_preview(self) -> None:
        hex_color = self._color.name()
        self._btn.setStyleSheet(
            f"background: {hex_color}; border: 1px solid #555; border-radius: 3px;")
        self._label.setText(hex_color)

    def set_color(self, color_str: str) -> None:
        c = QtGui.QColor(color_str)
        if c.isValid():
            self._color = c
            self._update_preview()

    def get_color(self) -> str:
        return self._color.name()


# ====== 主面板 ======

class ToolRunPanel(QtWidgets.QWidget):
    """工具运行面板 — 通用参数表单 + 执行 + 结果展示。"""

    # 信号：用户点击"在编辑器中打开"
    open_in_editor = Signal(str)  # tool_path

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._tool_path: Optional[str] = None
        self._graph: Optional[NodeGraph] = None
        self._spec: UiSpec = UiSpec()
        self._input_widgets: Dict[str, QtWidgets.QWidget] = {}  # key: "node_id:port_name"
        self._output_labels: Dict[str, QtWidgets.QLabel] = {}   # key: "node_id:port_name"

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setMinimumWidth(260)
        self.setMaximumWidth(400)
        self.setStyleSheet("""
            ToolRunPanel { background: #252526; color: #CCC; }
            QLabel { color: #CCC; }
            QLabel#title { font-size: 13px; font-weight: bold; padding: 6px; color: #EEE; }
            QLabel#section { font-size: 11px; font-weight: bold; padding: 4px 6px;
                            background: #333; color: #999; margin-top: 4px; }
            QLabel#empty { color: #666; font-size: 12px; padding: 20px; }
            QLabel#result { padding: 6px; background: #1E1E1E; border: 1px solid #333;
                           border-radius: 3px; font-family: monospace; }
            QPushButton#execute {
                background: #0E639C; color: white; border: none;
                padding: 8px 20px; border-radius: 4px; font-size: 13px;
                font-weight: bold;
            }
            QPushButton#execute:hover { background: #1177BB; }
            QPushButton#execute:disabled { background: #444; color: #888; }
            QPushButton#open_editor {
                background: transparent; color: #555; border: 1px solid #444;
                padding: 4px 8px; border-radius: 3px; font-size: 10px;
            }
            QPushButton#open_editor:hover { color: #888; border-color: #666; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
                background: #1E1E1E; color: #CCC; border: 1px solid #3E3E42;
                border-radius: 3px; padding: 4px;
            }
            QComboBox {
                background: #1E1E1E; color: #CCC; border: 1px solid #3E3E42;
                border-radius: 3px; padding: 4px;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 标题区
        self._title_label = QtWidgets.QLabel("🎛 工具运行面板")
        self._title_label.setObjectName("title")
        layout.addWidget(self._title_label)

        # 描述
        self._desc_label = QtWidgets.QLabel("")
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet("color: #888; font-size: 11px; padding: 0 6px;")
        self._desc_label.hide()
        layout.addWidget(self._desc_label)

        # 空状态
        self._empty_label = QtWidgets.QLabel("双击工具收藏中的工具\n即可在此面板运行")
        self._empty_label.setObjectName("empty")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        # 表单区域（可滚动的参数列表）
        self._form_scroll = QtWidgets.QScrollArea()
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._form_scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical { background: #333; width: 8px; }"
            "QScrollBar::handle:vertical { background: #555; border-radius: 4px; }"
        )
        self._form_widget = QtWidgets.QWidget()
        self._form_layout = QtWidgets.QVBoxLayout(self._form_widget)
        self._form_layout.setContentsMargins(4, 4, 4, 4)
        self._form_layout.setSpacing(6)
        self._form_scroll.setWidget(self._form_widget)
        self._form_scroll.hide()
        layout.addWidget(self._form_scroll, 1)

        # 执行按钮
        self._execute_btn = QtWidgets.QPushButton("▶ 执行")
        self._execute_btn.setObjectName("execute")
        self._execute_btn.clicked.connect(self._on_execute)
        self._execute_btn.hide()
        layout.addWidget(self._execute_btn)

        # 结果区域
        self._result_label = QtWidgets.QLabel("")
        self._result_label.setObjectName("result")
        self._result_label.setWordWrap(True)
        self._result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._result_label.hide()
        layout.addWidget(self._result_label)

        # 底栏：在编辑器中打开
        self._editor_btn = QtWidgets.QPushButton("✏ 在编辑器中打开")
        self._editor_btn.setObjectName("open_editor")
        self._editor_btn.clicked.connect(self._on_open_editor)
        self._editor_btn.hide()
        layout.addWidget(self._editor_btn)

        layout.addStretch()

    # ====== 公共接口 ======

    def set_tool(self, path: str) -> None:
        """加载工具文件并生成面板。"""
        self._tool_path = path
        self._clear_result()

        try:
            self._graph = NodeGraph.load(path)
        except Exception as e:
            self._show_error(f"加载工具失败: {e}")
            return

        # 推导/读取 UI 规格（兼容旧工具）
        if self._graph.ui_spec:
            self._spec = UiSpec.from_dict(self._graph.ui_spec)
        else:
            self._spec = derive_ui_spec(self._graph)

        # 更新标题
        name = self._graph.name or os.path.basename(path).replace(".pngraph", "")
        self._title_label.setText(f"🎛 {name}")

        # 描述
        if self._graph.description:
            self._desc_label.setText(self._graph.description)
            self._desc_label.show()
        else:
            self._desc_label.hide()

        # 空 spec 处理
        if self._spec.is_empty():
            self._empty_label.setText("该工具没有可暴露的参数\n可以直接执行")
            self._empty_label.show()
            self._form_scroll.hide()
            self._execute_btn.show()
            return

        self._build_form()
        self._empty_label.hide()
        self._form_scroll.show()
        self._execute_btn.show()
        self._editor_btn.show()

    def clear_tool(self) -> None:
        """清空面板。"""
        self._tool_path = None
        self._graph = None
        self._spec = UiSpec()
        self._input_widgets.clear()
        self._output_labels.clear()
        self._clear_form()
        self._clear_result()
        self._title_label.setText("🎛 工具运行面板")
        self._desc_label.hide()
        self._empty_label.setText("双击工具收藏中的工具\n即可在此面板运行")
        self._empty_label.show()
        self._form_scroll.hide()
        self._execute_btn.hide()
        self._editor_btn.hide()
        self._result_label.hide()

    # ====== 表单构建 ======

    def _build_form(self) -> None:
        """根据 UiSpec 生成表单。"""
        self._clear_form()
        self._input_widgets.clear()
        self._output_labels.clear()

        # ---- 输入参数区 ----
        if self._spec.inputs:
            section = QtWidgets.QLabel("📥 输入参数")
            section.setObjectName("section")
            self._form_layout.addWidget(section)

            for ui_input in self._spec.inputs:
                row = QtWidgets.QHBoxLayout()
                row.setSpacing(6)

                label = QtWidgets.QLabel(ui_input.name)
                label.setFixedWidth(60)
                label.setStyleSheet("color: #AAA; font-size: 11px;")
                row.addWidget(label)

                widget = _create_form_widget(ui_input, self._form_widget)
                key = f"{ui_input.node_id}:{ui_input.port_name}"
                self._input_widgets[key] = widget
                row.addWidget(widget, 1)

                self._form_layout.addLayout(row)

                # 提示文字
                if ui_input.description and ui_input.description != ui_input.name:
                    hint = QtWidgets.QLabel(ui_input.description)
                    hint.setStyleSheet("color: #666; font-size: 10px; padding-left: 66px;")
                    hint.setWordWrap(True)
                    self._form_layout.addWidget(hint)

        # ---- 输出结果区 ----
        if self._spec.outputs:
            self._form_layout.addSpacing(4)
            section = QtWidgets.QLabel("📤 输出结果")
            section.setObjectName("section")
            self._form_layout.addWidget(section)

            for ui_output in self._spec.outputs:
                row = QtWidgets.QHBoxLayout()
                row.setSpacing(6)
                label = QtWidgets.QLabel(ui_output.name)
                label.setStyleSheet("color: #AAA; font-size: 11px;")
                row.addWidget(label)

                value_label = QtWidgets.QLabel("-")
                value_label.setObjectName("result")
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                row.addWidget(value_label, 1)

                key = f"{ui_output.node_id}:{ui_output.port_name}"
                self._output_labels[key] = value_label
                self._form_layout.addLayout(row)

        self._form_layout.addStretch()

    def _clear_form(self) -> None:
        """清空表单控件。"""
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # 递归清理子布局
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

    # ====== 执行 ======

    def _on_execute(self) -> None:
        """执行工具。"""
        if not self._graph:
            return

        self._execute_btn.setEnabled(False)
        self._execute_btn.setText("⏳ 执行中...")
        self._clear_result()
        QtCore.QCoreApplication.processEvents()

        try:
            # 收集输入值 → {node_id: {port_name: value}}
            inline_values: Dict[str, Dict[str, Any]] = {}
            for key, widget in self._input_widgets.items():
                node_id, port_name = key.split(":", 1)
                value = _get_widget_value(widget)
                if node_id not in inline_values:
                    inline_values[node_id] = {}
                inline_values[node_id][port_name] = value

            # 执行
            executor = Executor(self._graph)
            results = executor.execute(inline_values=inline_values)

            # 更新输出
            for key, label in self._output_labels.items():
                node_id, port_name = key.split(":", 1)
                node_result = results.get(node_id, {})
                value = node_result.get(port_name, "-")
                display = str(value) if value is not None else "-"
                label.setText(display)

            # 显示摘要
            if executor.errors:
                err_msg = list(executor.errors.values())[0]
                self._show_error(f"执行有错误:\n{err_msg[:200]}")
            else:
                count = len(results)
                self._show_success(f"✅ 执行完成，涉及 {count} 个节点")

        except Exception as e:
            self._show_error(f"执行失败:\n{traceback.format_exc()[:500]}")

        finally:
            self._execute_btn.setEnabled(True)
            self._execute_btn.setText("▶ 执行")

    # ====== 结果显示 ======

    def _clear_result(self) -> None:
        self._result_label.hide()
        self._result_label.setText("")

    def _show_error(self, msg: str) -> None:
        self._result_label.setStyleSheet(
            "padding: 6px; background: #2D1B1B; border: 1px solid #663333;"
            " border-radius: 3px; color: #F88; font-family: monospace;")
        self._result_label.setText(msg)
        self._result_label.show()

    def _show_success(self, msg: str) -> None:
        self._result_label.setStyleSheet(
            "padding: 6px; background: #1B2D1B; border: 1px solid #336633;"
            " border-radius: 3px; color: #8F8; font-family: monospace;")
        self._result_label.setText(msg)
        self._result_label.show()

    def _on_open_editor(self) -> None:
        """通知外部在编辑器中打开工具。"""
        if self._tool_path:
            self.open_in_editor.emit(self._tool_path)
