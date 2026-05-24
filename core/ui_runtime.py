from __future__ import annotations
"""
Maya UI 运行时 — 在节点执行中创建弹窗 / 表单 / 工具窗口。
所有函数都在 Maya 的 PySide2 环境中运行（或 mock 降级）。
"""

from typing import Any, Dict, List, Optional, Callable


# ===================== 弹窗类 =====================

def show_message(
    title: str = "提示",
    message: str = "你好！",
    buttons: str = "OK",
) -> str:
    """弹出一个简单消息框，返回按下的按钮名。"""
    try:
        import maya.cmds as cmds
        btn_opts = _parse_buttons(buttons)
        result = cmds.confirmDialog(
            title=title, message=message,
            button=btn_opts, defaultButton=btn_opts[0],
            cancelButton=btn_opts[-1], dismissString=btn_opts[-1],
        )
        return result
    except ImportError:
        print(f"[UI Runtime] show_message: {message}")
        return buttons.split(",")[0].strip()


def show_confirm(
    title: str = "确认",
    message: str = "确定继续吗？",
    cancel_text: str = "取消",
    confirm_text: str = "确定",
) -> bool:
    """确认对话框，返回 True=确认 / False=取消。"""
    try:
        import maya.cmds as cmds
        result = cmds.confirmDialog(
            title=title, message=message,
            button=[confirm_text, cancel_text],
            defaultButton=confirm_text, cancelButton=cancel_text,
            dismissString=cancel_text,
        )
        return result == confirm_text
    except ImportError:
        return True


def show_prompt_text(
    title: str = "输入文本",
    message: str = "请输入:",
    default: str = "",
) -> str:
    """弹窗让用户输入文本，返回输入的字符串。"""
    try:
        import maya.cmds as cmds
        result = cmds.promptDialog(
            title=title, message=message,
            text=default, button=["确定", "取消"],
            defaultButton="确定", cancelButton="取消",
        )
        if result == "确定":
            return cmds.promptDialog(query=True, text=True)
        return default
    except ImportError:
        return default


def show_prompt_number(
    title: str = "输入数值",
    message: str = "请输入数字:",
    default: float = 0.0,
) -> float:
    """弹窗让用户输入数字。"""
    try:
        import maya.cmds as cmds
        result = cmds.promptDialog(
            title=title, message=message,
            text=str(default), button=["确定", "取消"],
            defaultButton="确定", cancelButton="取消",
        )
        if result == "确定":
            text = cmds.promptDialog(query=True, text=True)
            try:
                return float(text)
            except ValueError:
                return default
        return default
    except ImportError:
        return float(default)


def show_file_picker(
    title: str = "选择文件",
    file_filter: str = "所有文件 (*.*)",
    start_dir: str = "",
    mode: str = "open",
) -> str:
    """
    文件选择对话框。mode: "open"=打开, "save"=保存, "directory"=文件夹。
    """
    try:
        from PySide2 import QtWidgets
        if mode == "directory":
            path = QtWidgets.QFileDialog.getExistingDirectory(
                None, title, start_dir)
            return path or ""
        elif mode == "save":
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                None, title, start_dir, file_filter)
            return path or ""
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                None, title, start_dir, file_filter)
            return path or ""
    except ImportError:
        print(f"[UI Runtime] file_picker: {title}")
        return start_dir or "/tmp/selected_file.txt"


def show_color_picker(
    title: str = "选择颜色",
    default_color: str = "#FFFFFF",
) -> str:
    """颜色选择器，返回 hex 颜色字符串。"""
    try:
        from PySide2 import QtWidgets, QtGui
        initial = QtGui.QColor(default_color)
        color = QtWidgets.QColorDialog.getColor(initial, None, title)
        if color.isValid():
            return color.name()
        return default_color
    except ImportError:
        print(f"[UI Runtime] color_picker: {default_color}")
        return default_color


# ===================== 表单窗口 =====================

def show_form(
    title: str = "表单",
    fields: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    动态生成一个 PySide2 表单窗口，支持多种控件类型。
    fields 格式: [{"name": "field1", "label": "字段1", "type": "string", "default": ""}, ...]
    支持 type: "string", "int", "float", "bool", "combo", "slider", "file"

    返回 {field_name: value} 或 None(用户取消)。
    """
    if fields is None:
        fields = []

    try:
        from PySide2 import QtWidgets, QtCore
        from PySide2.QtCore import Qt
    except ImportError:
        print(f"[UI Runtime] show_form: {title}")
        result = {}
        for f in fields:
            result[f.get("name", f.get("label", "?"))] = f.get("default")
        return result

    dialog = QtWidgets.QDialog()
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(350)
    dialog.setStyleSheet("""
        QDialog { background: #2D2D30; color: #CCC; }
        QLabel { color: #CCC; font-size: 12px; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background: #3E3E42; color: #CCC; border: 1px solid #555;
            padding: 4px; border-radius: 3px;
        }
        QCheckBox { color: #CCC; }
        QPushButton {
            background: #3E3E42; color: #CCC; border: 1px solid #555;
            padding: 6px 16px; border-radius: 3px;
        }
        QPushButton:hover { background: #505050; }
        QPushButton#btn_ok { background: #007ACC; border-color: #007ACC; }
        QPushButton#btn_ok:hover { background: #1A8AD4; }
        QSlider::groove:horizontal { height: 6px; background: #555; border-radius: 3px; }
        QSlider::handle:horizontal {
            background: #007ACC; width: 14px; height: 14px;
            margin: -4px 0; border-radius: 7px;
        }
    """)

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setSpacing(8)

    widgets: Dict[str, QtWidgets.QWidget] = {}
    control_map: Dict[str, str] = {}  # field_name -> type

    for field in (fields or []):
        name = field.get("name", "?")
        label = field.get("label", name)
        ftype = field.get("type", "string")
        default = field.get("default")
        control_map[name] = ftype

        flayout = QtWidgets.QHBoxLayout()
        flayout.addWidget(QtWidgets.QLabel(label + ":"))

        if ftype == "bool":
            cb = QtWidgets.QCheckBox()
            cb.setChecked(bool(default))
            flayout.addWidget(cb)
            widgets[name] = cb
        elif ftype == "int":
            sb = QtWidgets.QSpinBox()
            if "min" in field:
                sb.setMinimum(int(field["min"]))
            if "max" in field:
                sb.setMaximum(int(field["max"]))
            sb.setValue(int(default) if default is not None else 0)
            flayout.addWidget(sb)
            widgets[name] = sb
        elif ftype == "float":
            dsb = QtWidgets.QDoubleSpinBox()
            dsb.setDecimals(3)
            if "min" in field:
                dsb.setMinimum(float(field["min"]))
            if "max" in field:
                dsb.setMaximum(float(field["max"]))
            dsb.setValue(float(default) if default is not None else 0.0)
            flayout.addWidget(dsb)
            widgets[name] = dsb
        elif ftype == "combo":
            combo = QtWidgets.QComboBox()
            options = field.get("options", [])
            combo.addItems([str(o) for o in options])
            if default is not None and str(default) in [str(o) for o in options]:
                combo.setCurrentText(str(default))
            flayout.addWidget(combo)
            widgets[name] = combo
        elif ftype == "file":
            file_layout = QtWidgets.QHBoxLayout()
            le = QtWidgets.QLineEdit(str(default) if default else "")
            btn = QtWidgets.QPushButton("浏览")
            file_layout.addWidget(le)
            file_layout.addWidget(btn)
            flayout.addLayout(file_layout)
            widgets[name] = le
            # 文件浏览按钮
            def make_file_browser(le_widget):
                def _browse():
                    path, _ = QtWidgets.QFileDialog.getOpenFileName(
                        dialog, "选择文件", le_widget.text())
                    if path:
                        le_widget.setText(path)
                return _browse
            btn.clicked.connect(make_file_browser(le))
        elif ftype == "slider":
            slider_layout = QtWidgets.QVBoxLayout()
            slider = QtWidgets.QSlider(Qt.Horizontal)
            value_label = QtWidgets.QLabel(str(default))
            min_v = int(field.get("min", 0))
            max_v = int(field.get("max", 100))
            slider.setMinimum(min_v)
            slider.setMaximum(max_v)
            slider.setValue(int(default) if default is not None else 50)
            slider.valueChanged.connect(lambda v, lb=value_label: lb.setText(str(v)))
            slider_layout.addWidget(slider)
            slider_layout.addWidget(value_label, alignment=Qt.AlignCenter)
            flayout.addLayout(slider_layout)
            widgets[name] = slider
        else:
            # string / 默认
            le = QtWidgets.QLineEdit(str(default) if default is not None else "")
            flayout.addWidget(le)
            widgets[name] = le

        layout.addLayout(flayout)

    # 确定/取消按钮
    btn_layout = QtWidgets.QHBoxLayout()
    btn_layout.addStretch()
    cancel_btn = QtWidgets.QPushButton("取消")
    cancel_btn.clicked.connect(dialog.reject)
    ok_btn = QtWidgets.QPushButton("确定")
    ok_btn.setObjectName("btn_ok")
    ok_btn.clicked.connect(dialog.accept)
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(ok_btn)
    layout.addLayout(btn_layout)

    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        result = {}
        for name, widget in widgets.items():
            ftype = control_map.get(name, "string")
            if ftype == "bool":
                result[name] = widget.isChecked()
            elif ftype == "int":
                result[name] = widget.value()
            elif ftype == "float":
                result[name] = widget.value()
            elif ftype == "combo":
                result[name] = widget.currentText()
            elif ftype == "slider":
                result[name] = widget.value()
            else:
                result[name] = widget.text()
        return result
    return None  # 用户取消


# ===================== 自定义工具窗口 =====================

def show_window(
    title: str,
    layout_fn: Callable,
    width: int = 400,
    height: int = 300,
    modal: bool = False,
) -> Any:
    """
    创建一个自定义 PySide2 工具窗口。
    layout_fn(parent_widget) -> result_dict (当窗口关闭时返回)

    用法:
        def build(parent):
            layout = QVBoxLayout(parent)
            btn = QPushButton("点击")
            ...
            return {"result": ...}
        show_window("工具", build)
    """
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        from PySide2.QtCore import Qt
    except ImportError:
        print(f"[UI Runtime] show_window (降级): {title}")
        return None

    window = QtWidgets.QWidget()
    window.setWindowTitle(title)
    window.resize(width, height)
    window.setAttribute(Qt.WA_DeleteOnClose)
    window.setStyleSheet("""
        QWidget { background: #2D2D30; color: #CCC; }
        QPushButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { ... }
    """)

    widget = QtWidgets.QWidget(window)
    window.setCentralWidget(widget) if hasattr(window, 'setCentralWidget') else None

    try:
        result = layout_fn(window)
    except Exception:
        result = None

    if modal:
        window.setWindowModality(Qt.ApplicationModal)
    window.show()
    window.raise_()
    window.activateWindow()

    return window


# ===================== 工具函数 =====================

def _parse_buttons(buttons: str) -> List[str]:
    """解析按钮字符串 "OK" / "确定,取消" / "是,否,取消" """
    return [b.strip() for b in buttons.split(",")]


def make_node_window(
    node_name: str,
    input_values: Dict[str, Any],
) -> Dict[str, Any]:
    """
    通用节点工具窗口 — 根据输入自动生成表单。
    适合 "直接运行" 模式：用户填表单 → 输出值流入下游节点。
    """
    fields = []
    for name, value in input_values.items():
        if isinstance(value, bool):
            fields.append({"name": name, "label": name, "type": "bool", "default": value})
        elif isinstance(value, int):
            fields.append({"name": name, "label": name, "type": "int", "default": value})
        elif isinstance(value, float):
            fields.append({"name": name, "label": name, "type": "float", "default": value})
        else:
            fields.append({"name": name, "label": name, "type": "string", "default": str(value) if value is not None else ""})

    result = show_form(title=f"✏️ {node_name}", fields=fields)
    return result if result else {}
