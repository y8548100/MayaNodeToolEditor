# MayaNodeToolEditor

可视化代码节点编辑工具，在 Maya 内通过 PySide2 节点图编辑器进行可视化脚本编程。

## 基础设施架构

```
Linux (mshhermes)                      Windows (192.168.0.101)
─────────────────────────              ─────────────────────────
~/projects/MayaNodeToolEditor/  ──push──→  D:\maya_projects\MayaNodeToolEditor\
  ├── main.py                     sync        ├── main.py
  ├── listener.py (v5)            ──────→     ├── listener.py
  ├── core/                                   ├── core/
  ├── ui/                                     ├── ui/
  └── data/                                   └── data/
                                        D:\maya_projects\
~/.hermes/scripts/                         ├── output/  (截图/输出)
  ├── start-maya.sh                          └── hermes_listener.py (回退)
  ├── maya-restart.sh
  ├── maya-exec                             D:\maya_projects\output\
  ├── maya-screenshot.sh                     └── ss_*.png  (截图)
  ├── maya-push.sh
  ├── maya-pull.sh
  ├── maya-sync.sh
  └── maya-watch.py (daemon)
```

## 监听器协议 (v5)

| 命令 | 效果 | 返回 |
|------|------|------|
| `任意Python代码` | 执行 | `OK:输出` / `ERROR:报错` |
| `/ping` | 心跳 | `PONG:Ns` |
| `/status` | 状态 | `STATUS|v5|...` |
| `/screenshot` | 截 Maya 窗口 | `OK:路径 (大小B)` |
| `/batch` + 多行 | 批处理 | `[#N] OK/ERR:...` 分隔 |

## 日常开发流程

```bash
# 启动 Maya
maya-start

# 改代码 → 自动同步到 Windows
# (maya-watch 守护进程自动监控)
# 或手动同步:
maya-sync

# 重启 Maya 加载新代码
maya-restart

# 测试代码
maya-exec "from MayaNodeToolEditor.main import launch; print(launch())"

# 截图验证
maya-screenshot -v

# 拉回文件
maya-pull "D:\maya_projects\output\result.txt"

# Git 版本管理
cd ~/projects/MayaNodeToolEditor
git add -A && git commit -m "xxx" && git push
```

## 脚本说明

- **start-maya.sh** — 杀旧 Maya → 启动新 Maya → 等监听器上线
- **maya-restart.sh** — 完整重启 + 心跳自检
- **maya-exec** — 向 Maya 发命令拿结果（3种模式：参数 / -f 文件 / stdin）
- **maya-screenshot.sh** — 截 Maya 窗口传回 Linux（-v 先 viewFit）
- **maya-push.sh** — 推文件到 Windows
- **maya-pull.sh** — 从 Windows 拉文件回 Linux
- **maya-sync.sh** — 全项目同步到 Windows
- **maya-watch.py** — 文件变更自动同步守护进程

## 运行状态

- Maya + 监听器通过 schtasks `HermesRun` 持久化（重启不丢）
- 监听器端口: `7002` (TCP)
- 截图输出: `D:\maya_projects\output\`
