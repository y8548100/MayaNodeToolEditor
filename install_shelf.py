# 在 Maya shelf 上安装启动按钮
import maya.cmds as cmds
import maya.mel as mel

# Python 代码片段（按钮点击时执行）
EDITOR_CODE = "import sys; sys.path.insert(0, 'D:/maya_projects'); " \
    "from MayaNodeToolEditor.main import launch; " \
    "import __main__; " \
    "__main__._hermes_maya_window = launch()"

TOOLRUN_CODE = "import sys; sys.path.insert(0, 'D:/maya_projects'); " \
    "from MayaNodeToolEditor.ui.tool_run_panel import run_tool_panel; " \
    "import os; from MayaNodeToolEditor.ui.saved_tools_panel import TOOLS_DIR; " \
    "tools = sorted([f for f in os.listdir(TOOLS_DIR) if f.endswith('.pngraph')]); " \
    "run_tool_panel(tools[-1] if tools else '')"

def install():
    shelf = mel.eval('$tmp = `tabLayout -query -selectTab $gShelfTopLevel`')

    # 先检查是否已安装 - 直接查所有 shelfButton
    try:
        all_buttons = cmds.shelfButton(query=True, parent=shelf) or []
    except:
        all_buttons = []
    
    exists = False
    for btn in all_buttons:
        try:
            lbl = cmds.shelfButton(btn, query=True, label=True)
            if lbl in ("NodeEdit", "ToolRun"):
                exists = True
                break
        except:
            pass

    if exists:
        print("按钮已存在，跳过安装")
        return

    # 按钮1：启动编辑器
    cmds.shelfButton(
        parent=shelf,
        annotation="打开节点编辑器",
        label="NodeEdit",
        image="commandButton.png",
        imageOverlayLabel="NE",
        sourceType="python",
        command=EDITOR_CODE,
        style="iconOnly",
    )

    # 按钮2：启动运行面板
    cmds.shelfButton(
        parent=shelf,
        annotation="打开工具运行面板",
        label="ToolRun",
        image="commandButton.png",
        imageOverlayLabel="TR",
        sourceType="python",
        command=TOOLRUN_CODE,
        style="iconOnly",
    )

    print("✅ 已安装: NodeEdit (编辑器) / ToolRun (运行面板)")

install()
