from __future__ import annotations

"""
撤销/重做管理器 — 支持节点操作的撤消与重做。
"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from MayaNodeToolEditor.ui.node_editor import NodeEditorScene
    from MayaNodeToolEditor.core.node import Node, Connection


class UndoCommand:
    """单个可撤消的操作基类。"""

    def __init__(self, description: str = "") -> None:
        self.description = description

    def undo(self, scene: NodeEditorScene) -> None:
        raise NotImplementedError

    def redo(self, scene: NodeEditorScene) -> None:
        raise NotImplementedError


class AddNodeCommand(UndoCommand):
    def __init__(self, node_data: Dict[str, Any]) -> None:
        super().__init__(f"添加节点 {node_data.get('name', '?')}")
        self.node_data = node_data
        self._node_id: Optional[str] = None

    def undo(self, scene: NodeEditorScene) -> None:
        if self._node_id:
            scene.remove_node_widget(self._node_id)

    def redo(self, scene: NodeEditorScene) -> None:
        from MayaNodeToolEditor.core.node import Node
        node = Node.from_dict(self.node_data)
        scene.graph.add_node(node)
        scene.add_node_widget(node)
        self._node_id = node.node_id


class RemoveNodeCommand(UndoCommand):
    def __init__(self, node: Node, connections: List[Dict[str, Any]]) -> None:
        super().__init__(f"删除节点 {node.name}")
        self.node_data = node.to_dict()
        self.connection_data = connections

    def undo(self, scene: NodeEditorScene) -> None:
        from MayaNodeToolEditor.core.node import Node, Connection
        node = Node.from_dict(self.node_data)
        scene.graph.add_node(node)
        scene.add_node_widget(node)
        for cd in self.connection_data:
            conn = Connection.from_dict(cd)
            scene.graph.add_connection(conn)
            scene.add_connection_line(conn)

    def redo(self, scene: NodeEditorScene) -> None:
        nid = self.node_data.get("node_id", "")
        if nid:
            scene.remove_node_widget(nid)


class MoveNodeCommand(UndoCommand):
    def __init__(self, node_id: str, old_x: float, old_y: float,
                 new_x: float, new_y: float) -> None:
        super().__init__(f"移动节点 {node_id[:8]}")
        self.node_id = node_id
        self.old_x = old_x
        self.old_y = old_y
        self.new_x = new_x
        self.new_y = new_y

    def undo(self, scene: NodeEditorScene) -> None:
        widget = scene.widget_map.get(self.node_id)
        if widget:
            widget.setPos(self.old_x, self.old_y)
            widget.node.pos_x = self.old_x
            widget.node.pos_y = self.old_y
            scene.update_all_connections()

    def redo(self, scene: NodeEditorScene) -> None:
        widget = scene.widget_map.get(self.node_id)
        if widget:
            widget.setPos(self.new_x, self.new_y)
            widget.node.pos_x = self.new_x
            widget.node.pos_y = self.new_y
            scene.update_all_connections()


class AddConnectionCommand(UndoCommand):
    def __init__(self, connection: Connection) -> None:
        super().__init__("添加连线")
        self.connection_data = connection.to_dict()

    def undo(self, scene: NodeEditorScene) -> None:
        cid = self.connection_data.get("conn_id", "")
        if cid:
            scene.remove_connection_line(cid)

    def redo(self, scene: NodeEditorScene) -> None:
        from MayaNodeToolEditor.core.node import Connection
        conn = Connection.from_dict(self.connection_data)
        scene.add_connection_line(conn)


class RemoveConnectionCommand(UndoCommand):
    def __init__(self, connection: Connection) -> None:
        super().__init__("删除连线")
        self.connection_data = connection.to_dict()

    def undo(self, scene: NodeEditorScene) -> None:
        from MayaNodeToolEditor.core.node import Connection
        conn = Connection.from_dict(self.connection_data)
        scene.add_connection_line(conn)

    def redo(self, scene: NodeEditorScene) -> None:
        cid = self.connection_data.get("conn_id", "")
        if cid:
            scene.remove_connection_line(cid)


class EditNodeCommand(UndoCommand):
    def __init__(self, node_id: str, old_data: Dict[str, Any],
                 new_data: Dict[str, Any]) -> None:
        super().__init__("编辑节点")
        self.node_id = node_id
        self.old_data = old_data
        self.new_data = new_data

    def undo(self, scene: NodeEditorScene) -> None:
        self._apply(scene, self.old_data)

    def redo(self, scene: NodeEditorScene) -> None:
        self._apply(scene, self.new_data)

    def _apply(self, scene: NodeEditorScene, data: Dict[str, Any]) -> None:
        node = scene.graph.get_node(self.node_id)
        if not node:
            return
        node.name = data.get("name", node.name)
        node.code = data.get("code", node.code)
        node.color = data.get("color", node.color)
        node.exec_mode = data.get("exec_mode", node.exec_mode)
        node.inline_widgets = data.get("inline_widgets", [])
        node.inline_widget_values = data.get("inline_widget_values", {})
        # 重建 widget
        connections = scene.graph.get_connections_for_node(self.node_id)
        scene.remove_node_widget(self.node_id)
        scene.graph.add_node(node)
        scene.add_node_widget(node)
        for conn in connections:
            scene.add_connection_line(conn)


class SnapshotCommand(UndoCommand):
    """快照命令 — 保存图的前后完整状态用于撤销/重做。"""

    def __init__(self, prev_state: Dict[str, Any],
                 next_state: Dict[str, Any], description: str = "") -> None:
        super().__init__(description)
        self.prev_state = prev_state
        self.next_state = next_state

    def undo(self, scene: NodeEditorScene) -> None:
        scene.restore_graph_from_dict(self.prev_state)

    def redo(self, scene: NodeEditorScene) -> None:
        scene.restore_graph_from_dict(self.next_state)


class UndoManager:
    """撤销/重做管理器。"""

    def __init__(self, scene: NodeEditorScene,
                 max_stack: int = 50) -> None:
        self.scene = scene
        self.max_stack = max_stack
        self._undo_stack: List[UndoCommand] = []
        self._redo_stack: List[UndoCommand] = []

    def execute(self, command: UndoCommand) -> None:
        """执行一个命令并压入撤销栈（不调 redo — 操作已执行）。"""
        self._undo_stack.append(command)
        self._redo_stack.clear()
        if len(self._undo_stack) > self.max_stack:
            self._undo_stack.pop(0)

    def undo(self) -> Optional[UndoCommand]:
        if not self._undo_stack:
            return None
        cmd = self._undo_stack.pop()
        cmd.undo(self.scene)
        self._redo_stack.append(cmd)
        return cmd

    def redo(self) -> Optional[UndoCommand]:
        if not self._redo_stack:
            return None
        cmd = self._redo_stack.pop()
        cmd.redo(self.scene)
        self._undo_stack.append(cmd)
        return cmd

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo_description(self) -> str:
        return self._undo_stack[-1].description if self._undo_stack else ""

    def redo_description(self) -> str:
        return self._redo_stack[-1].description if self._redo_stack else ""
