"""
Hermes Maya 远程通讯监听器 v5
特性:
  - executeInMainThreadWithResult 确保代码在主线程执行
  - socket 直返结果
  - /ping /status 心跳自检
  - /batch 多命令批处理
  - /screenshot 通用窗口截图
"""

import maya.cmds as cmds
import maya.utils
import socket
import threading
import traceback
import sys
import os
import io
import time
from contextlib import redirect_stdout

HERMES_PORT = 7002
RESULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.exists(RESULT_DIR):
    RESULT_DIR = "D:/maya_projects"

SS_DIR = f"{RESULT_DIR}/output"
os.makedirs(SS_DIR, exist_ok=True)

_start_time = time.time()
_cmd_count = 0
_cmd_lock = threading.Lock()


# ====== 截图 ======
def hermes_screenshot(filename=None):
    """截取 Maya 主窗口，保存到输出目录"""
    try:
        from PySide2 import QtWidgets
        maya_win = next(
            (w for w in QtWidgets.QApplication.topLevelWidgets()
             if w.objectName() == "MayaWindow"), None
        )
        if not maya_win:
            return False, "MayaWindow not found"
        if not filename:
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{SS_DIR}/ss_{ts}.png"
        pixmap = maya_win.grab()
        pixmap.save(filename, "PNG")
        size = os.path.getsize(filename)
        return True, f"{filename} ({size}B)"
    except Exception as e:
        return False, traceback.format_exc()


def _ping():
    uptime = int(time.time() - _start_time)
    return f"PONG:{uptime}s"


def _status():
    uptime = int(time.time() - _start_time)
    return (
        f"STATUS|v5|uptime:{uptime}s|cmds:{_cmd_count}"
        f"|port:{HERMES_PORT}|output:{SS_DIR}"
    )


def _exec_python(code):
    """执行 Python 代码并捕获 stdout"""
    try:
        buf = io.StringIO()
        g = {
            "__builtins__": __builtins__,
            "cmds": cmds,
            "maya_utils": maya.utils,
            "sys": sys,
            "os": os,
        }
        with redirect_stdout(buf):
            exec(code, g)
        output = buf.getvalue().strip()
        return True, output if output else "(ok)"
    except Exception as e:
        return False, traceback.format_exc()


def _handle_batch(lines):
    """批处理：逐行执行，用 >>>BATCH_N>>> 分隔"""
    results = []
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ok, msg = maya.utils.executeInMainThreadWithResult(_exec_python, line)
        tag = f"[#{i}]"
        results.append(f"{tag} {'OK' if ok else 'ERR'}: {msg[:200]}")
    return "\n---BATCH---\n".join(results)


def _handle(conn):
    global _cmd_count
    try:
        data = conn.recv(65536).decode("utf-8").strip()
        if not data:
            conn.sendall(b"ERR:empty request")
            conn.close()
            return

        with _cmd_lock:
            _cmd_count += 1

        first_line = data.split("\n", 1)[0].strip()

        if first_line == "/ping":
            result = _ping()

        elif first_line == "/status":
            result = _status()

        elif first_line == "/screenshot":
            ok, msg = maya.utils.executeInMainThreadWithResult(
                hermes_screenshot)
            result = f"{'OK' if ok else 'ERROR'}:{msg}"

        elif first_line == "/batch":
            # Strip first line, remaining lines are commands
            rest = data.split("\n", 1)[1] if "\n" in data else ""
            lines = [l.strip() for l in rest.split("\n") if l.strip()]
            if not lines:
                result = "ERR:empty batch"
            else:
                result = _handle_batch(lines)

        else:
            # Normal Python execution
            ok, msg = maya.utils.executeInMainThreadWithResult(
                _exec_python, data)
            result = f"{'OK' if ok else 'ERROR'}:{msg}"

        conn.sendall(result.encode("utf-8"))
    except Exception as e:
        try:
            conn.sendall(f"ERR:{traceback.format_exc()}".encode("utf-8"))
        except Exception:
            pass
    finally:
        conn.close()


def _server():
    sv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sv.bind(("0.0.0.0", HERMES_PORT))
        sv.listen(5)
        sv.settimeout(1.0)
        while True:
            try:
                c, a = sv.accept()
                threading.Thread(target=_handle, args=(c,), daemon=True).start()
            except socket.timeout:
                continue
    except Exception as e:
        with open(f"{RESULT_DIR}/listener_fail.txt", "w") as f:
            f.write(f"FAIL: {traceback.format_exc()}\n")
    finally:
        sv.close()


def launch_hermes():
    t = threading.Thread(target=_server, daemon=True)
    t.start()
