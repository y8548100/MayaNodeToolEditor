"""
批量改名核心逻辑 v2 — 覆盖几乎所有 Maya 对象类型。
支持：4种改名模式 × 20+对象大类 × 名称过滤 × 预览/执行
"""

import re
from typing import Any, Dict, List, Optional


# ====== 改名模式 ======

MODE_PREFIX_SUFFIX = "前缀后缀"
MODE_SEARCH_REPLACE = "搜索替换"
MODE_SEQUENTIAL = "序号编号"
MODE_REGEX = "正则替换"
ALL_MODES = [MODE_PREFIX_SUFFIX, MODE_SEARCH_REPLACE, MODE_SEQUENTIAL, MODE_REGEX]


# ====== 对象类型系统 ======
# 每个大类：mayatypes=查询类型, shapeParent=是否取父transform, desc=描述

OBJECT_CATEGORIES = {
    "选中物体":   {"types": ["__selected__"], "shapeParent": False, "desc": "当前选中的物体"},
    "多边形网格": {"types": ["mesh"], "shapeParent": True, "desc": "Polygon网格的Transform"},
    "NURBS曲面":  {"types": ["nurbsSurface"], "shapeParent": True, "desc": "NURBS曲面的Transform"},
    "NURBS曲线":  {"types": ["nurbsCurve"], "shapeParent": True, "desc": "NURBS曲线的Transform"},
    "细分曲面":   {"types": ["subdiv"], "shapeParent": True, "desc": "细分曲面的Transform"},
    "骨骼":       {"types": ["joint"], "shapeParent": False, "desc": "Joint关节骨骼"},
    "IK手柄":     {"types": ["ikHandle"], "shapeParent": False, "desc": "IK控制手柄"},
    "约束":       {"types": ["pointConstraint", "aimConstraint", "orientConstraint",
                             "scaleConstraint", "parentConstraint", "normalConstraint",
                             "geometryConstraint"], "shapeParent": False, "desc": "各类约束节点"},
    "变形器":     {"types": ["cluster", "lattice", "blendShape", "skinCluster",
                             "sculpt", "wire", "wrap", "shrinkWrap",
                             "jiggle", "softMod", "deltaMush"],
                   "shapeParent": False, "desc": "Cluster/晶格/BlendShape/蒙皮"},
    "灯光":       {"types": ["ambientLight", "directionalLight", "pointLight",
                             "spotLight", "areaLight", "volumeLight"],
                   "shapeParent": False, "desc": "环境/平行/点/聚光/区域/体积光"},
    "相机":       {"types": ["camera"], "shapeParent": True, "desc": "所有相机"},
    "材质":       {"types": ["lambert", "phong", "blinn", "standardSurface",
                             "aiStandardSurface", "aiSurfaceShader",
                             "lambert", "phongE", "anisotropic", "shadingEngine"],
                   "shapeParent": False, "desc": "标准/Arnold材质 + ShadingEngine"},
    "贴图":       {"types": ["file", "place2dTexture", "place3dTexture",
                             "psdFileTex", "aiImage", "aiNoise", "aiCellNoise",
                             "checker", "ramp", "noise", "fractal", "bulletCloud",
                             "brownian", "cloud", "stucco", "wood", "leather",
                             "granite", "marble", "rock", "snow", "water"],
                   "shapeParent": False, "desc": "文件/程序/2D/3D贴图节点"},
    "定位器":     {"types": ["locator"], "shapeParent": True, "desc": "Locator辅助对象"},
    "标注":       {"types": ["annotation"], "shapeParent": True, "desc": "Annotation标注"},
    "组(空Transform)": {"types": ["__empty_transform__"], "shapeParent": False,
                        "desc": "没有形状子节点的Transform（空组）"},
    "动画曲线":   {"types": ["animCurve"], "shapeParent": False, "desc": "Animation Curve"},
    "动画层":     {"types": ["animLayer"], "shapeParent": False, "desc": "Animation Layer"},
    "角色":       {"types": ["character"], "shapeParent": False, "desc": "Character角色集"},
    "粒子":       {"types": ["particle", "nParticle", "particleCloud"],
                   "shapeParent": False, "desc": "粒子系统"},
    "发射器":     {"types": ["emitter", "nEmitter"], "shapeParent": False, "desc": "粒子发射器"},
    "场":         {"types": ["airField", "dragField", "gravityField", "NewtonField",
                             "radialField", "turbulenceField", "vortexField",
                             "uniformField", "volumeAxisField"],
                   "shapeParent": False, "desc": "空气/重力/漩涡/紊流等场"},
    "刚体":       {"types": ["rigidBody", "nRigidBody"], "shapeParent": False, "desc": "主动/被动刚体"},
    "弹簧":       {"types": ["spring"], "shapeParent": False, "desc": "Spring弹簧约束"},
    "显示层":     {"types": ["displayLayer"], "shapeParent": False, "desc": "Display Layer显示层"},
    "渲染层":     {"types": ["renderLayer"], "shapeParent": False, "desc": "Render Layer渲染层"},
    "自定义类型": {"types": ["__custom__"], "shapeParent": False, "desc": "手写Maya类型名"},
    "全部":       {"types": ["__all__"], "shapeParent": False, "desc": "场景中所有Transform"},
}

ALL_OBJECT_TYPES = list(OBJECT_CATEGORIES.keys())


# ====== 注册下拉框选项到 tool_ui ======

def _register_options():
    """注册改名工具的端口 → 下拉选项映射。"""
    try:
        from MayaNodeToolEditor.core.tool_ui import register_combobox_port
        register_combobox_port("mode", ALL_MODES)
        register_combobox_port("object_type", ALL_OBJECT_TYPES)
    except ImportError:
        pass


_register_options()


class RenameTool:
    """批量改名工具核心逻辑 v2。"""

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """执行改名，返回 {result, count, summary}。"""
        mode = inputs.get("mode", MODE_PREFIX_SUFFIX)
        prefix = inputs.get("prefix", "")
        suffix = inputs.get("suffix", "")
        search = inputs.get("search", "")
        replace = inputs.get("replace", "")
        start_num = int(inputs.get("start_num", 1) or 1)
        pad_width = int(inputs.get("pad_width", 3) or 3)
        object_type = inputs.get("object_type", "选中物体")
        name_pattern = inputs.get("name_pattern", "")
        extra_type = inputs.get("extra_type", "")  # 自定义 Maya 类型
        preview = inputs.get("preview", True)

        # 获取对象
        objects = self._get_objects(object_type, name_pattern, extra_type)
        if not objects:
            return {
                "result": "⚠️ 没有找到符合条件的对象",
                "count": 0,
                "summary": "未匹配任何对象\n请检查对象类型、名称过滤条件",
            }

        # 执行改名
        renamed = []
        errors = []
        for i, obj in enumerate(objects):
            old_name = obj["name"]
            try:
                if mode == MODE_PREFIX_SUFFIX:
                    new_name = f"{prefix}{old_name}{suffix}"
                elif mode == MODE_SEARCH_REPLACE:
                    new_name = old_name.replace(search, replace) if search else old_name
                elif mode == MODE_SEQUENTIAL:
                    seq = str(start_num + i).zfill(pad_width)
                    # 序号模式：前缀+序号+_ +原名+后缀，或前缀+原名+序号+后缀
                    if prefix and not suffix:
                        new_name = f"{prefix}{seq}_{old_name}"
                    elif suffix and not prefix:
                        new_name = f"{old_name}_{seq}{suffix}"
                    else:
                        new_name = f"{prefix}{seq}_{old_name}{suffix}"
                elif mode == MODE_REGEX:
                    new_name = self._regex_replace(old_name, search, replace) if search else old_name
                else:
                    new_name = old_name

                if new_name and new_name != old_name:
                    renamed.append({
                        "old": old_name,
                        "new": new_name,
                        "type": obj["type"],
                    })
                    if not preview:
                        self._do_rename(obj["dag_path"], new_name)

            except Exception as e:
                errors.append(f"{old_name}: {e}")

        # === 结果摘要 ===
        count = len(renamed)
        total = len(objects)
        lines = [f"共 {total} 个对象 | 改名 {count} 个"]
        if errors:
            lines.append(f"失败 {len(errors)} 个")
        if preview:
            lines.append("🔍 预览模式（未实际改名）")
        else:
            lines.append("✅ 已实际执行改名")
        lines.append("")

        # 前30条记录
        for r in renamed[:30]:
            lines.append(f"  {r['old']}  →  {r['new']}  ({r['type']})")
        if len(renamed) > 30:
            lines.append(f"  ... 还有 {len(renamed) - 30} 个")

        if errors:
            lines.append("")
            lines.append("错误:")
            for e in errors[:10]:
                lines.append(f"  ⚠️  {e}")

        # 按类型分组统计
        if renamed:
            type_stats = {}
            for r in renamed:
                t = r["type"]
                type_stats[t] = type_stats.get(t, 0) + 1
            lines.append("")
            lines.append("统计:")
            for t, c in sorted(type_stats.items(), key=lambda x: -x[1]):
                lines.append(f"  {t}: {c}")

        return {
            "result": f"改名 {count}/{total} 个" if count == total else f"改名 {count}/{total} 个（有变动）",
            "count": count,
            "summary": "\n".join(lines),
        }

    # ====== 对象获取 ======

    def _get_objects(self, obj_type: str, name_pattern: str,
                     extra_type: str = "") -> List[Dict]:
        try:
            import maya.cmds as cmds
        except ImportError:
            return self._get_mock_objects(obj_type)

        cat = OBJECT_CATEGORIES.get(obj_type)
        if not cat:
            return []

        maya_types = cat["types"]
        shape_parent = cat["shapeParent"]
        objs = []

        # 特殊类型处理
        if "__selected__" in maya_types:
            raw = cmds.ls(selection=True, long=True) or []
            if not raw:
                return []
            for dag in raw:
                short = dag.split("|")[-1]
                if name_pattern and name_pattern not in short:
                    continue
                t = cmds.objectType(dag) if cmds.objExists(dag) else "?"
                objs.append({"dag_path": dag, "name": short, "type": t})
            return objs

        elif "__all__" in maya_types:
            raw = cmds.ls(transforms=True, long=True) or []

        elif "__empty_transform__" in maya_types:
            all_transforms = cmds.ls(type="transform", long=True) or []
            raw = []
            for t in all_transforms:
                shapes = cmds.listRelatives(t, shapes=True, fullPath=True) or []
                if not shapes:
                    raw.append(t)

        elif "__custom__" in maya_types:
            if not extra_type:
                return []
            raw = cmds.ls(type=extra_type, long=True) or []
            shape_parent = False  # 自定义类型不改父对象

        else:
            raw = []
            seen = set()
            for mt in maya_types:
                items = cmds.ls(type=mt, long=True) or []
                for item in items:
                    if item not in seen:
                        seen.add(item)
                        raw.append(item)

        for dag in raw:
            short = dag.split("|")[-1]
            if name_pattern and name_pattern not in short:
                continue

            # 取父 transform（针对形状节点）
            final_dag = dag
            if shape_parent:
                parent = cmds.listRelatives(dag, parent=True, fullPath=True)
                if parent:
                    final_dag = parent[0]
                    short = final_dag.split("|")[-1]

            t = cmds.objectType(final_dag) if cmds.objExists(final_dag) else "?"
            objs.append({"dag_path": final_dag, "name": short, "type": t})

        return objs

    # ====== 改名逻辑 ======

    def _regex_replace(self, name: str, pattern: str, replacement: str) -> str:
        try:
            return re.sub(pattern, replacement, name)
        except re.error:
            return name

    def _do_rename(self, dag_path: str, new_name: str) -> None:
        try:
            import maya.cmds as cmds
            cmds.rename(dag_path, new_name)
        except Exception as e:
            # 改名失败不抛异常，外部会捕获
            raise RuntimeError(f"改名失败: {e}")

    # ====== Mock（无Maya环境时）======

    def _get_mock_objects(self, obj_type: str) -> List[Dict]:
        mock_data = {
            "选中物体": ["pCube1", "pSphere1"],
            "多边形网格": ["pCube1", "pSphere1", "pCylinder1", "pPlane1", "pTorus1"],
            "骨骼": ["joint1", "joint2", "joint3", "hip_L", "hip_R",
                     "spine_01", "spine_02", "neck", "head"],
            "约束": ["pCube1_pointConstraint1", "pSphere1_aimConstraint1"],
            "变形器": ["blendShape1", "cluster1", "lattice1"],
            "灯光": ["directionalLight1", "pointLight1", "spotLight1"],
            "相机": ["persp", "top", "front", "side"],
            "材质": ["lambert1", "standardSurface1", "blinn1"],
            "贴图": ["file1", "place2dTexture1", "checker1"],
            "定位器": ["locator1", "locator2"],
            "动画曲线": ["animCurve1", "animCurve2"],
            "组(空Transform)": ["group1", "group2", "null1"],
        }
        names = mock_data.get(obj_type, ["pCube1", "pSphere1"])
        return [{"dag_path": n, "name": n, "type": "mock"} for n in names]
