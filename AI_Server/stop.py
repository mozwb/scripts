"""stop.py —— 按 PID 收掉 start.py 起的进程

start.py 会把 pid 记到 logs/pids.txt（每行：名字 pid）。
这里逐个按进程组杀掉，杀完删掉文件。

用法：sudo python3 stop.py
"""

import os
import signal
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PID_FILE = BASE / "logs" / "pids.txt"


def log(msg):
    print("[stop] " + msg, flush=True)


def kill_group(pid, name):
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        log("SIGTERM %s pid=%d" % (name, pid))
    except ProcessLookupError:
        log("%s pid=%d 已经不在了" % (name, pid))
        return
    except PermissionError:
        log("%s pid=%d 没权限（要 sudo）" % (name, pid))
        return

    import time
    for _ in range(20):
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        log("SIGKILL %s pid=%d" % (name, pid))
    except ProcessLookupError:
        pass


def main():
    if os.geteuid() != 0:
        sys.exit("用 root 跑：sudo python3 stop.py")

    if not PID_FILE.exists():
        sys.exit("没有 %s，可能没跑过 start.py；手动看看：pgrep -af QQ" % PID_FILE)

    for line in PID_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, pid = line.partition(" ")
        if pid.isdigit():
            kill_group(int(pid), name)

    PID_FILE.unlink()
    log("收工")


if __name__ == "__main__":
    main()
