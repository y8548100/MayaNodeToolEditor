"""
核心层单元测试 — 不依赖 Maya/PySide2。
"""


import json
import os
import sys
import tempfile
import unittest

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MayaNodeToolEditor.core.node import Node, Connection
from MayaNodeToolEditor.core.node_graph import NodeGraph
from MayaNodeToolEditor.core.executor import Executor
from MayaNodeToolEditor.core.types import DataType, SocketDef, SocketDirection


class TestNode(unittest.TestCase):
    """节点数据模型测试。"""

    def test_create_node(self):
        node = Node("测试节点", "测试")
        self.assertEqual(node.name, "测试节点")
        self.assertEqual(node.category, "测试")
        self.assertEqual(len(node.node_id), 12)

    def test_add_sockets(self):
        node = Node("计算节点")
        node.add_input("a", DataType.FLOAT, 0.0, "输入A")
        node.add_input("b", DataType.FLOAT, 0.0, "输入B")
        node.add_output("sum", DataType.FLOAT, description="和")

        self.assertEqual(len(node.inputs), 2)
        self.assertEqual(len(node.outputs), 1)
        self.assertEqual(node.inputs[0].name, "a")
        self.assertEqual(node.outputs[0].name, "sum")

    def test_serialize_roundtrip(self):
        node = Node("测试", "通用")
        node.code = "def run(inputs):\n    return {'x': 1}"
        node.add_input("a", DataType.INT, 0)
        node.add_output("b", DataType.INT)

        data = node.to_dict()
        restored = Node.from_dict(data)

        self.assertEqual(restored.name, "测试")
        self.assertEqual(restored.code, node.code)
        self.assertEqual(len(restored.inputs), 1)
        self.assertEqual(len(restored.outputs), 1)
        self.assertEqual(restored.node_id, node.node_id)


class TestNodeGraph(unittest.TestCase):
    """节点图数据模型测试。"""

    def test_add_remove_node(self):
        graph = NodeGraph()
        n1 = graph.add_node(Node("A"))
        n2 = graph.add_node(Node("B"))

        self.assertEqual(len(graph.nodes), 2)

        graph.remove_node(n1.node_id)
        self.assertEqual(len(graph.nodes), 1)

    def test_connection(self):
        graph = NodeGraph()
        n1 = graph.add_node(Node("A"))
        n2 = graph.add_node(Node("B"))
        conn = graph.add_connection(Connection(n1.node_id, "out", n2.node_id, "in"))
        self.assertEqual(len(graph.connections), 1)

    def test_no_self_connect(self):
        graph = NodeGraph()
        n1 = graph.add_node(Node("A"))
        with self.assertRaises(ValueError):
            graph.add_connection(Connection(n1.node_id, "out", n1.node_id, "in"))

    def test_topological_sort_simple(self):
        graph = NodeGraph()
        n1 = graph.add_node(Node("A"))
        n2 = graph.add_node(Node("B"))
        n3 = graph.add_node(Node("C"))
        # A → B → C
        graph.add_connection(Connection(n1.node_id, "out", n2.node_id, "in"))
        graph.add_connection(Connection(n2.node_id, "out", n3.node_id, "in"))

        order = graph.topological_sort()
        self.assertEqual(order, [n1.node_id, n2.node_id, n3.node_id])

    def test_topological_sort_cycle(self):
        graph = NodeGraph()
        n1 = graph.add_node(Node("A"))
        n2 = graph.add_node(Node("B"))
        graph.add_connection(Connection(n1.node_id, "out", n2.node_id, "in"))
        graph.add_connection(Connection(n2.node_id, "out", n1.node_id, "in"))

        with self.assertRaises(ValueError):
            graph.topological_sort()

    def test_serialize_roundtrip(self):
        graph = NodeGraph("测试图")
        n1 = graph.add_node(Node("A"))
        n2 = graph.add_node(Node("B"))
        graph.add_connection(Connection(n1.node_id, "out", n2.node_id, "in"))

        data = graph.to_dict()
        restored = NodeGraph.from_dict(data)
        self.assertEqual(restored.name, "测试图")
        self.assertEqual(len(restored.nodes), 2)
        self.assertEqual(len(restored.connections), 1)

    def test_save_load(self):
        graph = NodeGraph("保存测试")
        graph.add_node(Node("X"))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
            graph.save(f.name)

        loaded = NodeGraph.load(path)
        self.assertEqual(loaded.name, "保存测试")
        self.assertEqual(len(loaded.nodes), 1)
        os.unlink(path)


class TestExecutor(unittest.TestCase):
    """执行引擎测试。"""

    def test_simple_execution(self):
        graph = NodeGraph()
        n1 = Node("加一")
        n1.code = '''def run(inputs):
    return {"result": inputs.get("x", 0) + 1}
'''
        n1.add_input("x", DataType.FLOAT, 0.0)

        n2 = Node("输出")
        n2.add_input("val", DataType.ANY)
        n2.code = '''def run(inputs):
    return {"out": inputs.get("val")}
'''
        n2.add_output("out", DataType.ANY)

        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_connection(Connection(n1.node_id, "result", n2.node_id, "val"))

        executor = Executor(graph)
        results = executor.execute()

        self.assertIn(n2.node_id, results)
        self.assertEqual(results[n2.node_id].get("out"), 1)

    def test_empty_node_passthrough(self):
        graph = NodeGraph()
        n1 = Node("无代码节点")
        n1.add_output("val", DataType.ANY)

        graph.add_node(n1)
        executor = Executor(graph)
        results = executor.execute()

        self.assertIn(n1.node_id, results)

    def test_execution_order(self):
        graph = NodeGraph()
        order_log: list = []

        n1 = Node("第一步")
        n1.code = "def run(inputs):\n    return {'step': 1}\n"
        n1.add_output("step", DataType.INT)

        n2 = Node("第二步")
        n2.code = "def run(inputs):\n    return {'step': 2}\n"
        n2.add_output("step", DataType.INT)

        graph.add_node(n1)
        graph.add_node(n2)

        executor = Executor(graph)
        results = executor.execute()

        self.assertEqual(results[n1.node_id].get("step"), 1)
        self.assertEqual(results[n2.node_id].get("step"), 2)


if __name__ == "__main__":
    unittest.main()
