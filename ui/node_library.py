from __future__ import annotations
"""
节点库侧栏 — 按分类浏览预设节点，拖放添加到画布。
"""


from typing import Any, Callable, Dict, List, Optional

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, Signal

from MayaNodeToolEditor.core.node import Node
from MayaNodeToolEditor.core.types import DataType


# ======= 预设节点模板 =======

# 获取选中对象
NODE_GET_SELECTED = {
    "name": "获取选中对象",
    "code": '''def run(inputs):
    """获取当前 Maya 场景中选中的对象。"""
    try:
        import maya.cmds as cmds
        sel = cmds.ls(selection=True) or []
        return {"selected": sel}
    except ImportError:
        return {"selected": ["mock_object_1", "mock_object_2"]}
''',
    "inputs": [],
    "outputs": [{"name": "selected", "type": "list", "desc": "选中对象列表"}],
}

# 按类型选择
NODE_SELECT_BY_TYPE = {
    "name": "按类型选择",
    "code": '''def run(inputs):
    """按类型选择对象。"""
    node_type = inputs.get("node_type", "joint")
    try:
        import maya.cmds as cmds
        result = cmds.ls(type=node_type) or []
        return {"objects": result}
    except ImportError:
        return {"objects": [f"mock_{node_type}_1", f"mock_{node_type}_2"]}
''',
    "inputs": [{"name": "node_type", "type": "string", "default": "joint", "desc": "Maya 节点类型"}],
    "outputs": [{"name": "objects", "type": "list", "desc": "匹配的对象列表"}],
}

# 获取变换节点
NODE_GET_TRANSFORMS = {
    "name": "获取变换节点",
    "code": '''def run(inputs):
    """从对象列表中只保留变换节点（transform）。"""
    objects = inputs.get("objects", [])
    try:
        import maya.cmds as cmds
        result = [o for o in objects if cmds.nodeType(o) == "transform"]
        return {"transforms": result}
    except ImportError:
        return {"transforms": [o for o in objects if "transform" in o.lower()]}
''',
    "inputs": [{"name": "objects", "type": "list", "default": [], "desc": "对象列表"}],
    "outputs": [{"name": "transforms", "type": "list", "desc": "变换节点列表"}],
}

# 获取子对象
NODE_GET_CHILDREN = {
    "name": "获取子对象",
    "code": '''def run(inputs):
    """获取指定父级的所有子对象。"""
    parent = inputs.get("parent", "")
    child_type = inputs.get("child_type", "transform")
    try:
        import maya.cmds as cmds
        if parent:
            kids = cmds.listRelatives(parent, children=True, type=child_type) or []
            return {"children": kids}
        return {"children": []}
    except ImportError:
        return {"children": [f"{parent}_child_1", f"{parent}_child_2"]}
''',
    "inputs": [
        {"name": "parent", "type": "string", "default": "", "desc": "父对象名称"},
        {"name": "child_type", "type": "string", "default": "transform", "desc": "子对象类型"},
    ],
    "outputs": [{"name": "children", "type": "list", "desc": "子对象列表"}],
}

# 获取BlendShape目标
NODE_GET_BLENDSHAPES = {
    "name": "获取BlendShape目标",
    "code": '''def run(inputs):
    """获取 BlendShape 节点的所有变形目标。"""
    bs_node = inputs.get("blendshape", "")
    try:
        import maya.cmds as cmds
        if not bs_node or not cmds.objExists(bs_node):
            return {"targets": []}
        targets = cmds.listAttr(bs_node, multi=True, string="weight") or []
        alias_list = cmds.aliasAttr(bs_node, query=True) or []
        aliases = [alias_list[i] for i in range(0, len(alias_list), 2)] if alias_list else targets
        return {"targets": aliases if aliases else targets}
    except ImportError:
        return {"targets": ["target_A", "target_B", "target_C"]}
''',
    "inputs": [{"name": "blendshape", "type": "string", "default": "", "desc": "BlendShape 节点名称"}],
    "outputs": [{"name": "targets", "type": "list", "desc": "变形目标列表"}],
}

# 获取所有BlendShape
NODE_GET_SELECTED_BLENDSHAPES = {
    "name": "获取所有BlendShape",
    "code": '''def run(inputs):
    """获取场景中所有 BlendShape 节点及其目标。"""
    try:
        import maya.cmds as cmds
        all_bs = cmds.ls(type="blendShape") or []
        result = {}
        for bs in all_bs:
            targets = cmds.listAttr(bs, multi=True, string="weight") or []
            alias_list = cmds.aliasAttr(bs, query=True) or []
            aliases = [alias_list[i] for i in range(0, len(alias_list), 2)] if alias_list else targets
            result[bs] = aliases if aliases else targets
        return {"blendshapes": result}
    except ImportError:
        return {"blendshapes": {"blendShape1": ["A", "B", "C"]}}
''',
    "inputs": [],
    "outputs": [{"name": "blendshapes", "type": "dict", "desc": "所有BlendShape及其目标"}],
}

# 添加前缀
NODE_ADD_PREFIX = {
    "name": "添加前缀",
    "code": '''def run(inputs):
    """为名称列表添加前缀。"""
    names = inputs.get("names", [])
    prefix = inputs.get("prefix", "_")
    return {"result": [prefix + n for n in names]}
''',
    "inputs": [
        {"name": "names", "type": "list", "default": [], "desc": "名称列表"},
        {"name": "prefix", "type": "string", "default": "_", "desc": "前缀文本"},
    ],
    "outputs": [{"name": "result", "type": "list", "desc": "处理后的名称列表"}],
}

# 添加后缀
NODE_ADD_SUFFIX = {
    "name": "添加后缀",
    "code": '''def run(inputs):
    """为名称列表添加后缀。"""
    names = inputs.get("names", [])
    suffix = inputs.get("suffix", "_suffix")
    return {"result": [n + suffix for n in names]}
''',
    "inputs": [
        {"name": "names", "type": "list", "default": [], "desc": "名称列表"},
        {"name": "suffix", "type": "string", "default": "_suffix", "desc": "后缀文本"},
    ],
    "outputs": [{"name": "result", "type": "list", "desc": "处理后的名称列表"}],
}

# 替换文本
NODE_REPLACE_TEXT = {
    "name": "替换文本",
    "code": '''def run(inputs):
    """替换名称中的文本。"""
    names = inputs.get("names", [])
    old = inputs.get("old", "")
    new = inputs.get("new", "")
    return {"result": [n.replace(old, new) for n in names]}
''',
    "inputs": [
        {"name": "names", "type": "list", "default": [], "desc": "名称列表"},
        {"name": "old", "type": "string", "default": "", "desc": "要替换的文本"},
        {"name": "new", "type": "string", "default": "", "desc": "替换为"},
    ],
    "outputs": [{"name": "result", "type": "list", "desc": "处理后的名称列表"}],
}

# 格式化编号
NODE_FORMAT_NUMBER = {
    "name": "格式化编号",
    "code": '''def run(inputs):
    """为名称列表添加序号（如 name_01, name_02）。"""
    names = inputs.get("names", [])
    start = inputs.get("start", 1)
    digits = inputs.get("digits", 2)
    separator = inputs.get("separator", "_")
    result = []
    for i, n in enumerate(names):
        num = str(start + i).zfill(digits)
        result.append(f"{n}{separator}{num}")
    return {"result": result}
''',
    "inputs": [
        {"name": "names", "type": "list", "default": [], "desc": "名称列表"},
        {"name": "start", "type": "int", "default": 1, "desc": "起始编号"},
        {"name": "digits", "type": "int", "default": 2, "desc": "编号位数"},
        {"name": "separator", "type": "string", "default": "_", "desc": "分隔符"},
    ],
    "outputs": [{"name": "result", "type": "list", "desc": "编号后的名称列表"}],
}

# 提取数字后缀
NODE_EXTRACT_NUMBER = {
    "name": "提取数字后缀",
    "code": '''def run(inputs):
    """提取名称末尾的数字（如 arm_01 -> 01）。"""
    import re
    names = inputs.get("names", [])
    result = []
    for n in names:
        match = re.search(r'(\\d+)$', n)
        if match:
            result.append(match.group(1))
        else:
            result.append("")
    return {"numbers": result}
''',
    "inputs": [{"name": "names", "type": "list", "default": [], "desc": "名称列表"}],
    "outputs": [{"name": "numbers", "type": "list", "desc": "提取的数字列表"}],
}

# 按规则改名（模板）
NODE_RENAME_RULE = {
    "name": "按规则改名",
    "code": '''def run(inputs):
    """按命名规则批量改名（支持 {prefix}{name}{suffix}{num} 格式）。"""
    names = inputs.get("names", [])
    rule = inputs.get("rule", "{prefix}{name}")
    prefix = inputs.get("prefix", "")
    suffix = inputs.get("suffix", "")
    start = inputs.get("start", 1)
    digits = inputs.get("digits", 2)
    result = []
    for i, n in enumerate(names):
        num = str(start + i).zfill(digits)
        new_name = rule.format(prefix=prefix, name=n, suffix=suffix, num=num)
        result.append(new_name)
    return {"result": result}
''',
    "inputs": [
        {"name": "names", "type": "list", "default": [], "desc": "名称列表"},
        {"name": "rule", "type": "string", "default": "{prefix}{name}", "desc": "命名规则"},
        {"name": "prefix", "type": "string", "default": "", "desc": "前缀"},
        {"name": "suffix", "type": "string", "default": "", "desc": "后缀"},
        {"name": "start", "type": "int", "default": 1, "desc": "起始编号"},
        {"name": "digits", "type": "int", "default": 2, "desc": "编号位数"},
    ],
    "outputs": [{"name": "result", "type": "list", "desc": "改名后的名称列表"}],
}

# 执行改名
NODE_EXECUTE_RENAME = {
    "name": "执行改名",
    "code": '''def run(inputs):
    """在 Maya 场景中执行批量改名。"""
    old_names = inputs.get("old_names", [])
    new_names = inputs.get("new_names", [])
    dry_run = inputs.get("dry_run", False)
    try:
        import maya.cmds as cmds
        renamed = []
        errors = []
        for old, new in zip(old_names, new_names):
            if not cmds.objExists(old):
                errors.append(f"不存在 {old}")
                continue
            if dry_run:
                renamed.append(new)
                continue
            try:
                result = cmds.rename(old, new)
                renamed.append(result)
            except Exception as e:
                errors.append(f"{old} -> {new}: {e}")
        return {
            "renamed": renamed,
            "count": len(renamed),
            "errors": errors,
            "error_count": len(errors),
        }
    except ImportError:
        return {"renamed": new_names, "count": len(new_names), "errors": [], "error_count": 0}
''',
    "inputs": [
        {"name": "old_names", "type": "list", "default": [], "desc": "旧名称列表"},
        {"name": "new_names", "type": "list", "default": [], "desc": "新名称列表"},
        {"name": "dry_run", "type": "bool", "default": False, "desc": "仅预览不执行"},
    ],
    "outputs": [
        {"name": "renamed", "type": "list", "desc": "改名后的名称"},
        {"name": "count", "type": "int", "desc": "成功改名数"},
        {"name": "errors", "type": "list", "desc": "错误信息"},
        {"name": "error_count", "type": "int", "desc": "错误数"},
    ],
}

# 验证名称唯一
NODE_VALIDATE_NAMES = {
    "name": "验证名称唯一",
    "code": '''def run(inputs):
    """检查新名称是否与场景中现有对象冲突。"""
    new_names = inputs.get("new_names", [])
    try:
        import maya.cmds as cmds
        all_objs = set(cmds.ls()) or set()
        conflicts = [n for n in new_names if n in all_objs]
        return {"conflicts": conflicts, "safe": [n for n in new_names if n not in all_objs]}
    except ImportError:
        return {"conflicts": [], "safe": new_names}
''',
    "inputs": [{"name": "new_names", "type": "list", "default": [], "desc": "新名称列表"}],
    "outputs": [
        {"name": "conflicts", "type": "list", "desc": "冲突的名称"},
        {"name": "safe", "type": "list", "desc": "安全的名称"},
    ],
}

# 按层级改名
NODE_RENAME_HIERARCHY = {
    "name": "按层级改名",
    "code": '''def run(inputs):
    """按层级结构改名：根_层级1_层级2_名称。"""
    objects = inputs.get("objects", [])
    separator = inputs.get("separator", "_")
    try:
        import maya.cmds as cmds
        result = []
        for obj in objects:
            parents = cmds.listRelatives(obj, parent=True, fullPath=True) or []
            hierarchy = []
            if parents:
                parts = parents[0].split("|")
                hierarchy = [p.split(":")[-1] for p in parts if p]
            base = obj.split(":")[-1].split("|")[-1]
            new_name = separator.join(hierarchy + [base]) if hierarchy else base
            result.append(new_name)
        return {"result": result}
    except ImportError:
        return {"result": objects}
''',
    "inputs": [
        {"name": "objects", "type": "list", "default": [], "desc": "对象列表"},
        {"name": "separator", "type": "string", "default": "_", "desc": "层级分隔符"},
    ],
    "outputs": [{"name": "result", "type": "list", "desc": "带层级路径的名称"}],
}

# 遍历列表
NODE_ITERATE = {
    "name": "遍历列表",
    "code": '''def run(inputs):
    """遍历列表，输出数量。"""
    items = inputs.get("items", [])
    return {"output": items, "count": len(items)}
''',
    "inputs": [{"name": "items", "type": "list", "default": [], "desc": "要遍历的列表"}],
    "outputs": [
        {"name": "output", "type": "list", "desc": "输出列表"},
        {"name": "count", "type": "int", "desc": "数量"},
    ],
}

# 过滤列表
NODE_FILTER = {
    "name": "过滤列表",
    "code": '''def run(inputs):
    """过滤列表（排除空字符串）。"""
    items = inputs.get("items", [])
    result = [i for i in items if str(i).strip()]
    return {"filtered": result, "removed": len(items) - len(result)}
''',
    "inputs": [{"name": "items", "type": "list", "default": [], "desc": "输入列表"}],
    "outputs": [
        {"name": "filtered", "type": "list", "desc": "过滤后的列表"},
        {"name": "removed", "type": "int", "desc": "移除数量"},
    ],
}

# 正则过滤
NODE_REGEX_FILTER = {
    "name": "按命名规则过滤",
    "code": '''def run(inputs):
    """按正则表达式过滤名称列表。"""
    import re
    names = inputs.get("names", [])
    pattern = inputs.get("pattern", ".*")
    include = inputs.get("include", True)
    try:
        regex = re.compile(pattern)
        if include:
            result = [n for n in names if regex.search(n)]
        else:
            result = [n for n in names if not regex.search(n)]
        return {"filtered": result, "removed": len(names) - len(result)}
    except re.error as e:
        return {"filtered": names, "removed": 0, "error": str(e)}
''',
    "inputs": [
        {"name": "names", "type": "list", "default": [], "desc": "名称列表"},
        {"name": "pattern", "type": "string", "default": ".*", "desc": "正则表达式"},
        {"name": "include", "type": "bool", "default": True, "desc": "True=匹配保留"},
    ],
    "outputs": [
        {"name": "filtered", "type": "list", "desc": "过滤后的名称"},
        {"name": "removed", "type": "int", "desc": "移除数量"},
    ],
}

# 数值相加
NODE_ADD = {
    "name": "数值相加",
    "code": '''def run(inputs):
    """两个数值相加。"""
    a = inputs.get("a", 0)
    b = inputs.get("b", 0)
    return {"sum": a + b}
''',
    "inputs": [
        {"name": "a", "type": "float", "default": 0, "desc": "数值A"},
        {"name": "b", "type": "float", "default": 0, "desc": "数值B"},
    ],
    "outputs": [{"name": "sum", "type": "float", "desc": "和"}],
}

# 合并列表
NODE_MERGE = {
    "name": "合并列表",
    "code": '''def run(inputs):
    """合并两个列表。"""
    a = inputs.get("list_a", [])
    b = inputs.get("list_b", [])
    return {"merged": a + b}
''',
    "inputs": [
        {"name": "list_a", "type": "list", "default": [], "desc": "列表A"},
        {"name": "list_b", "type": "list", "default": [], "desc": "列表B"},
    ],
    "outputs": [{"name": "merged", "type": "list", "desc": "合并结果"}],
}

# 打印信息
NODE_PRINT = {
    "name": "打印信息",
    "code": '''def run(inputs):
    """打印信息到 Maya 脚本编辑器。"""
    msg = inputs.get("message", "Hello")
    print(f"[NodeEditor] {msg}")
    return {"output": msg}
''',
    "inputs": [{"name": "message", "type": "string", "default": "Hello", "desc": "要打印的消息"}],
    "outputs": [{"name": "output", "type": "string", "desc": "消息内容"}],
}

# 输入文本
NODE_INPUT = {
    "name": "输入文本",
    "code": '''def run(inputs):
    """直接输出输入的文本。"""
    text = inputs.get("text", "")
    return {"text": text}
''',
    "inputs": [{"name": "text", "type": "string", "default": "", "desc": "文本内容"}],
    "outputs": [{"name": "text", "type": "string", "desc": "文本内容"}],
}

# ====== 交互节点（运行时弹窗让用户输入） ======

NODE_UI_PROMPT_TEXT = {
    "name": "询问文本",
    "code": '''def run(inputs):
    """弹窗让用户输入文本。"""
    title = inputs.get("title", "输入文本")
    msg = inputs.get("message", "请输入")
    default = inputs.get("default", "")
    try:
        import maya.cmds as cmds
        result = cmds.promptDialog(
            title=title, message=msg,
            text=default, button=["确定", "取消"],
            defaultButton="确定", cancelButton="取消",
        )
        if result == "确定":
            value = cmds.promptDialog(query=True, text=True)
            return {"value": value}
        return {"value": default}
    except ImportError:
        return {"value": default}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "输入文本", "desc": "对话框标题"},
        {"name": "message", "type": "string", "default": "请输入", "desc": "提示信息"},
        {"name": "default", "type": "string", "default": "", "desc": "默认值"},
    ],
    "outputs": [{"name": "value", "type": "string", "desc": "用户输入的值"}],
}

NODE_UI_PROMPT_NUMBER = {
    "name": "询问数值",
    "code": '''def run(inputs):
    """弹窗让用户输入数字。"""
    title = inputs.get("title", "输入数值")
    msg = inputs.get("message", "请输入数值")
    default = inputs.get("default", 0)
    try:
        import maya.cmds as cmds
        result = cmds.promptDialog(
            title=title, message=msg,
            text=str(default), button=["确定", "取消"],
            defaultButton="确定", cancelButton="取消",
        )
        if result == "确定":
            text = cmds.promptDialog(query=True, text=True)
            try:
                return {"value": float(text)}
            except ValueError:
                return {"value": default}
        return {"value": default}
    except ImportError:
        return {"value": float(default)}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "输入数值", "desc": "对话框标题"},
        {"name": "message", "type": "string", "default": "请输入数值", "desc": "提示信息"},
        {"name": "default", "type": "float", "default": 0, "desc": "默认值"},
    ],
    "outputs": [{"name": "value", "type": "float", "desc": "用户输入的数值"}],
}

NODE_UI_CONFIRM = {
    "name": "确认对话框",
    "code": '''def run(inputs):
    """弹窗让用户确认/取消操作。"""
    title = inputs.get("title", "确认")
    msg = inputs.get("message", "确定继续？")
    try:
        import maya.cmds as cmds
        result = cmds.confirmDialog(
            title=title, message=msg,
            button=["确定", "取消"],
            defaultButton="确定", cancelButton="取消",
        )
        confirmed = result == "确定"
        return {"confirmed": confirmed, "text": "yes" if confirmed else "no"}
    except ImportError:
        return {"confirmed": True, "text": "yes"}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "确认", "desc": "对话框标题"},
        {"name": "message", "type": "string", "default": "确定继续？", "desc": "提示信息"},
    ],
    "outputs": [
        {"name": "confirmed", "type": "bool", "desc": "用户是否确认"},
        {"name": "text", "type": "string", "desc": "yes/no"},
    ],
}

# ====== 内嵌控件节点（控件直接显示在节点上） ======

NODE_INLINE_TEXT_INPUT = {
    "name": "输入文本",
    "code": '''def run(inputs):
    """文本输入源节点——内嵌输入框的值直接作为输出。"""
    text = inputs.get("text", "")
    return {"text": text}
''',
    "inline_widgets": [
        {"type": "line_edit", "name": "text", "label": "文本", "default": ""},
    ],
    "inputs": [],
    "outputs": [{"name": "text", "type": "string", "desc": "输入的文本"}],
}

NODE_INLINE_NUMBER_INPUT = {
    "name": "输入数字",
    "code": '''def run(inputs):
    """数字输入源节点。"""
    val = inputs.get("value", 0)
    return {"value": val}
''',
    "inline_widgets": [
        {"type": "spin_box", "name": "value", "label": "数值", "default": 0, "min": -9999, "max": 9999},
    ],
    "inputs": [],
    "outputs": [{"name": "value", "type": "int", "desc": "输入的数值"}],
}

NODE_INLINE_SLIDER = {
    "name": "滑块输入",
    "code": '''def run(inputs):
    """滑块输入源节点。"""
    val = inputs.get("value", 50)
    return {"value": val}
''',
    "inline_widgets": [
        {"type": "slider", "name": "value", "label": "滑块", "default": 50, "min": 0, "max": 100},
    ],
    "inputs": [],
    "outputs": [{"name": "value", "type": "int", "desc": "滑块值 0-100"}],
}

NODE_INLINE_COMBO = {
    "name": "下拉选择",
    "code": '''def run(inputs):
    """下拉选择源节点。"""
    selected = inputs.get("selected", "")
    return {"selected": selected}
''',
    "inline_widgets": [
        {"type": "combo", "name": "selected", "label": "选项", "default": "A",
         "options": ["A", "B", "C", "D"]},
    ],
    "inputs": [],
    "outputs": [{"name": "selected", "type": "string", "desc": "选中的项"}],
}

NODE_INLINE_CHECKBOX = {
    "name": "开关",
    "code": '''def run(inputs):
    """开关源节点。"""
    enabled = inputs.get("enabled", False)
    return {"enabled": enabled}
''',
    "inline_widgets": [
        {"type": "check_box", "name": "enabled", "label": "启用", "default": True},
    ],
    "inputs": [],
    "outputs": [{"name": "enabled", "type": "bool", "desc": "是否启用"}],
}

# 打印节点——带内嵌输出显示
NODE_PRINT_WITH_DISPLAY = {
    "name": "打印信息",
    "code": '''def run(inputs):
    """打印信息并显示在节点上。"""
    msg = inputs.get("message", "Hello")
    print(f"[NodeEditor] {msg}")
    return {"display": msg, "output": msg}
''',
    "inline_widgets": [
        {"type": "text_display", "name": "display", "label": "输出", "default": ""},
    ],
    "inputs": [{"name": "message", "type": "string", "default": "Hello", "desc": "要打印的消息"}],
    "outputs": [
        {"name": "display", "type": "string", "desc": "显示内容"},
        {"name": "output", "type": "string", "desc": "消息内容"},
    ],
}

# ====== Phase 5: 新内嵌控件节点 ======

NODE_INLINE_COLOR_PICKER = {
    "name": "颜色选择",
    "code": '''def run(inputs):
    """颜色选择源节点——内嵌颜色按钮，点击弹出颜色选择器。"""
    color = inputs.get("color", "#4FC1FF")
    return {"color": color}
''',
    "inline_widgets": [
        {"type": "color_picker", "name": "color", "label": "颜色", "default": "#4FC1FF"},
    ],
    "inputs": [],
    "outputs": [{"name": "color", "type": "string", "desc": "选择的颜色 hex"}],
}

NODE_INLINE_FILE_BROWSER = {
    "name": "文件浏览",
    "code": '''def run(inputs):
    """文件路径源节点——内嵌文件浏览器按钮。"""
    path = inputs.get("path", "")
    return {"path": path}
''',
    "inline_widgets": [
        {"type": "file_browser", "name": "path", "label": "路径", "default": ""},
    ],
    "inputs": [],
    "outputs": [{"name": "path", "type": "string", "desc": "选择的文件路径"}],
}

NODE_INLINE_MULTILINE_TEXT = {
    "name": "多行文本",
    "code": '''def run(inputs):
    """多行文本输入源节点。"""
    text = inputs.get("text", "")
    return {"text": text}
''',
    "inline_widgets": [
        {"type": "plain_text", "name": "text", "label": "内容", "default": ""},
    ],
    "inputs": [],
    "outputs": [{"name": "text", "type": "string", "desc": "输入的文本"}],
}

# ====== 原 UI 弹窗节点（保持兼容） ======

NODE_UI_POPUP = {
    "name": "弹出窗口",
    "exec_mode": "ui",
    "code": '''def run(inputs):
    """弹出信息窗口，返回按钮结果。"""
    result = ui.show_message(
        title=inputs.get("title", "提示"),
        message=inputs.get("message", "你好！"),
        buttons=inputs.get("buttons", "确定"),
    )
    return {"result": result}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "提示", "desc": "窗口标题"},
        {"name": "message", "type": "string", "default": "你好！", "desc": "显示消息"},
        {"name": "buttons", "type": "string", "default": "确定", "desc": "按钮（逗号分隔）"},
    ],
    "outputs": [{"name": "result", "type": "string", "desc": "按下的按钮名称"}],
}

NODE_UI_CONFIRM_FORM = {
    "name": "确认对话框",
    "exec_mode": "ui",
    "code": '''def run(inputs):
    """确认/取消对话框。"""
    confirmed = ui.show_confirm(
        title=inputs.get("title", "确认"),
        message=inputs.get("message", "确定继续吗？"),
        confirm_text=inputs.get("confirm_text", "确定"),
        cancel_text=inputs.get("cancel_text", "取消"),
    )
    return {"confirmed": confirmed, "text": "yes" if confirmed else "no"}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "确认", "desc": "对话框标题"},
        {"name": "message", "type": "string", "default": "确定继续吗？", "desc": "提示信息"},
        {"name": "confirm_text", "type": "string", "default": "确定", "desc": "确认按钮文字"},
        {"name": "cancel_text", "type": "string", "default": "取消", "desc": "取消按钮文字"},
    ],
    "outputs": [
        {"name": "confirmed", "type": "bool", "desc": "用户是否确认"},
        {"name": "text", "type": "string", "desc": "yes/no"},
    ],
}

NODE_UI_INPUT_FORM = {
    "name": "输入表单",
    "exec_mode": "ui",
    "code": '''def run(inputs):
    """弹出表单窗口，支持多种控件类型。"""
    fields = inputs.get("fields", [
        {"name": "name", "label": "名称", "type": "string", "default": inputs.get("name", "")},
        {"name": "count", "label": "数量", "type": "int", "default": inputs.get("count", 1)},
        {"name": "enabled", "label": "启用", "type": "bool", "default": inputs.get("enabled", True)},
    ])
    result = ui.show_form(
        title=inputs.get("title", "表单输入"),
        fields=fields,
    )
    return result or {}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "表单输入", "desc": "窗口标题"},
        {"name": "name", "type": "string", "default": "", "desc": "默认名称"},
        {"name": "count", "type": "int", "default": 1, "desc": "默认数量"},
        {"name": "enabled", "type": "bool", "default": True, "desc": "默认启用"},
    ],
    "outputs": [
        {"name": "name", "type": "string", "desc": "用户输入的名称"},
        {"name": "count", "type": "int", "desc": "用户输入的数量"},
        {"name": "enabled", "type": "bool", "desc": "用户是否勾选"},
    ],
}

NODE_UI_SLIDER = {
    "name": "滑块输入（弹窗）",
    "exec_mode": "ui",
    "code": '''def run(inputs):
    """弹出滑块窗口让用户调整数值。"""
    result = ui.show_form(
        title=inputs.get("title", "滑块输入"),
        fields=[
            {"name": "value", "label": inputs.get("label", "数值"),
             "type": "slider", "default": inputs.get("default", 50),
             "min": inputs.get("min", 0), "max": inputs.get("max", 100)},
        ],
    )
    if result is None:
        return {"value": inputs.get("default", 50)}
    return result
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "滑块输入", "desc": "窗口标题"},
        {"name": "label", "type": "string", "default": "数值", "desc": "滑块标签"},
        {"name": "default", "type": "int", "default": 50, "desc": "默认值"},
        {"name": "min", "type": "int", "default": 0, "desc": "最小值"},
        {"name": "max", "type": "int", "default": 100, "desc": "最大值"},
    ],
    "outputs": [{"name": "value", "type": "int", "desc": "滑块值"}],
}

NODE_UI_FILE_PICKER = {
    "name": "文件选择器",
    "exec_mode": "ui",
    "code": '''def run(inputs):
    """弹出文件选择对话框。"""
    path = ui.show_file_picker(
        title=inputs.get("title", "选择文件"),
        file_filter=inputs.get("file_filter", "所有文件(*.*)"),
        start_dir=inputs.get("start_dir", ""),
        mode=inputs.get("mode", "open"),
    )
    return {"path": path}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "选择文件", "desc": "对话框标题"},
        {"name": "file_filter", "type": "string", "default": "所有文件(*.*)", "desc": "文件过滤"},
        {"name": "start_dir", "type": "string", "default": "", "desc": "起始目录"},
        {"name": "mode", "type": "string", "default": "open", "desc": "模式: open/save/directory"},
    ],
    "outputs": [{"name": "path", "type": "string", "desc": "选择的文件路径"}],
}

NODE_UI_COLOR_PICKER = {
    "name": "颜色选择器",
    "exec_mode": "ui",
    "code": '''def run(inputs):
    """弹出颜色选择对话框。"""
    color = ui.show_color_picker(
        title=inputs.get("title", "选择颜色"),
        default_color=inputs.get("default_color", "#FFFFFF"),
    )
    return {"color": color}
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "选择颜色", "desc": "对话框标题"},
        {"name": "default_color", "type": "string", "default": "#FFFFFF", "desc": "默认颜色"},
    ],
    "outputs": [{"name": "color", "type": "string", "desc": "选择的颜色 hex"}],
}

NODE_UI_LIST_SELECTOR = {
    "name": "列表选择器",
    "exec_mode": "ui",
    "code": '''def run(inputs):
    """从列表中选择项目。"""
    items = inputs.get("items", ["选项A", "选项B", "选项C"])
    result = ui.show_form(
        title=inputs.get("title", "选择项目"),
        fields=[
            {"name": "selected", "label": "请选择",
             "type": "combo", "default": items[0] if items else "",
             "options": items},
        ],
    )
    if result is None:
        return {"selected": items[0] if items else ""}
    return result
''',
    "inputs": [
        {"name": "title", "type": "string", "default": "选择项目", "desc": "窗口标题"},
        {"name": "items", "type": "list", "default": ["选项A", "选项B", "选项C"], "desc": "选项列表"},
    ],
    "outputs": [{"name": "selected", "type": "string", "desc": "选中的项目"}],
}

# 构建节点库
# 分类目录->节点列表
BUILTIN_NODES: Dict[str, List[Dict[str, Any]]] = {
    "内嵌控件（自带控件）": [
        NODE_INLINE_TEXT_INPUT,
        NODE_INLINE_NUMBER_INPUT,
        NODE_INLINE_SLIDER,
        NODE_INLINE_COMBO,
        NODE_INLINE_CHECKBOX,
        NODE_INLINE_COLOR_PICKER,
        NODE_INLINE_FILE_BROWSER,
        NODE_INLINE_MULTILINE_TEXT,
        NODE_PRINT_WITH_DISPLAY,
    ],
    "弹窗交互": [
        NODE_UI_PROMPT_TEXT,
        NODE_UI_PROMPT_NUMBER,
        NODE_UI_CONFIRM,
        NODE_UI_POPUP,
        NODE_UI_CONFIRM_FORM,
        NODE_UI_INPUT_FORM,
        NODE_UI_SLIDER,
        NODE_UI_FILE_PICKER,
        NODE_UI_COLOR_PICKER,
        NODE_UI_LIST_SELECTOR,
    ],
    "Maya选择/获取": [
        NODE_GET_SELECTED,
        NODE_SELECT_BY_TYPE,
        NODE_GET_TRANSFORMS,
        NODE_GET_CHILDREN,
        NODE_GET_BLENDSHAPES,
        NODE_GET_SELECTED_BLENDSHAPES,
    ],
    "名字处理": [
        NODE_ADD_PREFIX,
        NODE_ADD_SUFFIX,
        NODE_REPLACE_TEXT,
        NODE_FORMAT_NUMBER,
        NODE_EXTRACT_NUMBER,
        NODE_RENAME_RULE,
    ],
    "Maya改名": [
        NODE_EXECUTE_RENAME,
        NODE_VALIDATE_NAMES,
        NODE_RENAME_HIERARCHY,
    ],
    "批量处理": [
        NODE_ITERATE,
        NODE_FILTER,
        NODE_REGEX_FILTER,
    ],
    "计算": [
        NODE_ADD,
        NODE_MERGE,
    ],
}


class NodeLibraryWidget(QtWidgets.QWidget):
    """节点库侧栏 — 分类浏览预设节点，拖放添加。"""

    node_add_requested = Signal(dict)  # 发射节点模板数据

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self.setStyleSheet("""
            QWidget { background: #252526; color: #CCC; }
            QTreeWidget { background: #1E1E1E; border: 1px solid #3E3E42; }
            QTreeWidget::item { padding: 4px; }
            QTreeWidget::item:selected { background: #094771; }
            QLineEdit {
                background: #3E3E42; color: #CCC;
                border: 1px solid #555; padding: 4px; border-radius: 3px;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        title = QtWidgets.QLabel("📦 节点库")
        title.setStyleSheet("font-size: 12px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("搜索节点...")
        self.search_box.textChanged.connect(self._filter_nodes)
        layout.addWidget(self.search_box)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self.tree.setAnimated(True)
        self.tree.itemDoubleClicked.connect(self._on_item_double_click)
        layout.addWidget(self.tree)

        self._populate_tree()

    def _populate_tree(self, filter_text: str = "") -> None:
        self.tree.clear()
        for category, nodes in BUILTIN_NODES.items():
            cat_item = QtWidgets.QTreeWidgetItem([f"  {category}"])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsDragEnabled)
            font = cat_item.font(0)
            font.setBold(True)
            cat_item.setFont(0, font)
            cat_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#4FC1FF")))

            for node_data in nodes:
                name = node_data.get("name", "Unnamed")
                if filter_text and filter_text.lower() not in name.lower():
                    continue
                node_item = QtWidgets.QTreeWidgetItem([f"    {name}"])
                node_item.setData(0, Qt.UserRole, node_data)
                # 拖放数据
                mime_data = QtCore.QMimeData()
                import json
                mime_data.setData("application/x-node-template",
                                  json.dumps(node_data, ensure_ascii=False).encode())
                node_item.setFlags(node_item.flags() | Qt.ItemIsDragEnabled)
                cat_item.addChild(node_item)

            if cat_item.childCount() > 0:
                self.tree.addTopLevelItem(cat_item)

    def _filter_nodes(self, text: str) -> None:
        self._populate_tree(text)

    def _on_item_double_click(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        node_data = item.data(0, Qt.UserRole)
        if node_data:
            self.node_add_requested.emit(node_data)
