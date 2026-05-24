from __future__ import annotations
"""
代码编辑器窗口 — 非模态，双击节点时弹出 Python 代码编辑对话框。
支持保存/取消，保存时发射 node_saved 信号（不阻塞监听器）。
"""


from typing import Optional

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, Signal

from MayaNodeToolEditor.core.node import Node
from MayaNodeToolEditor.core.types import DataType, SocketDirection


class CodeEditorDialog(QtWidgets.QDialog):
    """节点代码编辑器对话框（非模态）。"""

    node_saved = Signal(str)  # 发射 node_id

    def __init__(self, node: Node, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(f"编辑节点: {node.name}")
        self.setMinimumSize(700, 500)
        self.setAttribute(Qt.WA_DeleteOnClose, False)  # 关闭时不会销毁，可重新打开
        self.setStyleSheet("""
            QDialog { background: #2D2D30; color: #CCC; }
            QLabel { color: #CCC; }
            QLineEdit, QTextEdit {
                background: #1E1E1E; color: #D4D4D4;
                border: 1px solid #3E3E42; padding: 4px;
                font-family: "Consolas", "Monaco", monospace;
            }
            QPushButton {
                background: #0E639C; color: white;
                border: none; padding: 6px 16px; border-radius: 3px;
            }
            QPushButton:hover { background: #1177BB; }
            QPushButton:pressed { background: #0D56A6; }
            QPushButton#btn_cancel { background: #3E3E42; }
            QPushButton#btn_cancel:hover { background: #555; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        # 名称
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("节点名称:"))
        self.name_edit = QtWidgets.QLineEdit(node.name)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # 代码编辑器
        layout.addWidget(QtWidgets.QLabel("Python 代码 (定义 def run(inputs) -> dict):"))
        self.code_edit = QtWidgets.QPlainTextEdit()
        self.code_edit.setPlainText(node.code)
        self.code_edit.setMinimumHeight(200)
        font = QtGui.QFont("Consolas", 10)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.code_edit.setFont(font)
        layout.addWidget(self.code_edit)

        # 输入插口管理
        layout.addWidget(QtWidgets.QLabel("输入插口:"))
        self.input_widget = SocketListWidget(node.inputs)
        layout.addWidget(self.input_widget)

        # 输出插口管理
        layout.addWidget(QtWidgets.QLabel("输出插口:"))
        self.output_widget = SocketListWidget(node.outputs)
        layout.addWidget(self.output_widget)

        # 按钮
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.setObjectName("btn_cancel")
        cancel_btn.clicked.connect(self.close)
        save_btn = QtWidgets.QPushButton("保存")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        # 窗口关闭时发射保存信号（如果用户通过 ✕ 关闭则不保存）
        self._saved = False

    def _save(self) -> None:
        """保存节点属性并发射信号。"""
        self.node.name = self.name_edit.text()
        self.node.code = self.code_edit.toPlainText()
        self.node.inputs = self.input_widget.get_sockets()
        self.node.outputs = self.output_widget.get_sockets()
        self._saved = True
        self.node_saved.emit(self.node.node_id)
        self.close()

    def closeEvent(self, event: QtCore.QEvent) -> None:
        """关闭时清理。"""
        self._saved = False
        super().closeEvent(event)

    def show_and_focus(self) -> None:
        """显示窗口并激活。"""
        self.show()
        self.raise_()
        self.activateWindow()


class SocketRowWidget(QtWidgets.QWidget):
    """单行插口编辑器。"""

    def __init__(self, socket_def: Optional[dict] = None) -> None:
        super().__init__()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self.name_edit = QtWidgets.QLineEdit(
            socket_def.get("name", "") if socket_def else "")
        self.name_edit.setPlaceholderText("插口名")
        self.name_edit.setFixedWidth(120)
        layout.addWidget(self.name_edit)

        self.type_combo = QtWidgets.QComboBox()
        for dt in DataType:
            self.type_combo.addItem(dt.value, dt.value)
        if socket_def:
            idx = self.type_combo.findText(socket_def.get("data_type", "any"))
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        layout.addWidget(self.type_combo)

        self.default_edit = QtWidgets.QLineEdit(
            str(socket_def.get("default_value", "")) if socket_def else "")
        self.default_edit.setPlaceholderText("默认值")
        self.default_edit.setFixedWidth(100)
        layout.addWidget(self.default_edit)

        del_btn = QtWidgets.QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setStyleSheet(
            "QPushButton { background: #C04040; border: none; color: white; }"
            "QPushButton:hover { background: #D06060; }")
        del_btn.clicked.connect(self.deleteLater)
        layout.addWidget(del_btn)

    def get_socket(self) -> dict:
        return {
            "name": self.name_edit.text(),
            "data_type": self.type_combo.currentText(),
            "default_value": self.default_edit.text(),
        }


class SocketListWidget(QtWidgets.QWidget):
    """插口列表编辑器（可增删行）。"""

    def __init__(self, sockets: Optional[list] = None) -> None:
        super().__init__()
        self._sockets = sockets or []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.list_layout = QtWidgets.QVBoxLayout()
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.list_layout)

        add_btn = QtWidgets.QPushButton("+ 添加插口")
        add_btn.setStyleSheet(
            "QPushButton { background: #0E639C; border: none; color: white; "
            "padding: 3px 10px; }"
            "QPushButton:hover { background: #1177BB; }")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn)

        # 初始化已有行
        for sock in self._sockets:
            self._add_row(sock.to_dict())

    def _add_row(self, socket_def: dict = None) -> None:
        row = SocketRowWidget(socket_def)
        self.list_layout.addWidget(row)

    def get_sockets(self) -> list:
        from core.types import SocketDef
        result = []
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            if item and item.widget():
                data = item.widget().get_socket()
                if data["name"]:
                    result.append(
                        SocketDef.from_dict({
                            "name": data["name"],
                            "data_type": data["data_type"],
                            "default_value": data.get("default_value", ""),
                        })
                    )
        return result
