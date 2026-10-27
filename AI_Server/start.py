"""start.py —— 一键启动（服务器）

顺序：
  1 前置检查（QQ / SnowLuma 装好没）
  2 起 QQ（xvfb 虚拟显示器，无头也能跑）
  3 起 SnowLuma（WebUI 在 5099）
  4 等 WebUI 就绪 → 去扫码（第一次要手动）
  5 读 OneBot 的 access token
  6 等 3001 起来 → 拉起 bridge.py
  7 Ctrl+C 收工

用法：sudo python3 start.py
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOGS = BASE / "logs"
SNOWLUMA = BASE / "snowluma"

WEBUI_PORT = 5099
WS_PORT = 3001

procs = []          # [(名字, Popen)]


def log(msg):
    print("[start] " + msg, flush=True)


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_port(port, timeout, hint=""):
    end = time.time() + timeout
    while time.time() < end:
        if port_open(port):
            return True
        time.sleep(2)
    log("等 %d 超时 %s" % (port, hint))
    return False


def spawn(name, cmd, cwd):
    """起后台进程，输出写 logs/<name>.log。"""
    LOGS.mkdir(parents=True, exist_ok=True)
    f = open(LOGS / ("%s.log" % name), "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(
        cmd, cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=f, stderr=subprocess.STDOUT,
        start_new_session=True,          # 独立进程组，方便整组收掉
    )
    procs.append((name, p))
    # 记下来，stop.py 靠这个按 PID 收人，不靠 pkill 猜
    with open(LOGS / "pids.txt", "a", encoding="utf-8") as pf:
        pf.write("%s %d\n" % (name, p.pid))
    log("%s 已启动 pid=%d，日志 %s" % (name, p.pid, LOGS / ("%s.log" % name)))
    return p


def stop_all():
    for name, p in reversed(procs):
        if p.poll() is None:
            log("关闭 %s ..." % name)
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    for name, p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


# ── 1 前置检查 ───────────────────────────────────────────
def check():
    if not os.path.exists("/opt/QQ/qq"):
        sys.exit("没找到 QQ，先跑 sudo python3 download.py")
    if not (SNOWLUMA / "index.mjs").exists():
        sys.exit("没找到 SnowLuma，先跑 sudo python3 download.py")
    LOGS.mkdir(parents=True, exist_ok=True)


# ── 2 起 QQ ─────────────────────────────────────────────
def pgrep(pattern):
    return subprocess.run("pgrep -f %s" % pattern, shell=True,
                          capture_output=True).returncode == 0


def start_qq():
    if pgrep("/opt/QQ/qq"):
        log("QQ 已经在跑，跳过启动")
        return
    # 无头环境必须有虚拟显示器；--no-sandbox 是 Electron 在容器里的常规写法
    spawn("qq", ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24",
                 "/opt/QQ/qq", "--no-sandbox"], BASE)


# ── 3 起 SnowLuma ───────────────────────────────────────
def start_snowluma():
    if pgrep("index.mjs"):
        log("SnowLuma 已经在跑，跳过启动")
        return
    spawn("snowluma", [str(SNOWLUMA / "node"), "index.mjs"], SNOWLUMA)


# ── 4 SnowLuma 后台登录 + 自动加载 QQ ───────────────────
def read_webui_password():
    """首次启动时它会把初始密码打在日志里：user=admin password=xxx"""
    log_file = LOGS / "snowluma.log"
    if not log_file.exists():
        return ""
    text = log_file.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"password=([0-9A-Za-z]+)", text)
    return m.group(1) if m else ""


def api(path, payload=None, token=None, method=None):
    url = "http://127.0.0.1:%d%s" % (WEBUI_PORT, path)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-SnowLuma-Token", token)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def login_snowluma():
    pw = read_webui_password()
    if not pw:
        log("日志里没找到初始密码（可能已经改过），跳过自动登录")
        return ""
    try:
        res = api("/api/login", {"password": pw})
    except Exception as e:
        log("登录失败: %s" % str(e)[:80])
        return ""
    token = res.get("token", "")
    if token:
        log("SnowLuma WebUI 已登录（密码来自日志）")
    return token


def load_qq_process(token):
    """把 QQ 主进程拉进来；已经在线就不动。"""
    if not token:
        return
    try:
        items = api("/api/processes", token=token).get("list", [])
    except Exception as e:
        log("取进程列表失败: %s" % str(e)[:80])
        return

    for p in items:
        status = p.get("status")
        if status == "online":
            log("QQ 进程已在线 pid=%s" % p.get("pid"))
            return
        if status == "available":
            log("加载 QQ 进程 pid=%s" % p.get("pid"))
            try:
                api("/api/processes/%s/load" % p.get("pid"), {}, token)
            except Exception as e:
                log("加载失败: %s" % str(e)[:80])
            return
    log("没找到可加载的 QQ 进程（共 %d 个）" % len(items))


# ── 5 token（SnowLuma 把每个号的 OneBot 配置写在这） ────
def read_token():
    cfg_dir = SNOWLUMA / "config"
    if not cfg_dir.exists():
        return ""
    for f in sorted(cfg_dir.glob("onebot_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for ws in data.get("networks", {}).get("wsServers", []):
            if ws.get("port") == WS_PORT and ws.get("accessToken"):
                log("token 来自 %s" % f.name)
                return ws["accessToken"]
    return ""


# ── 入口 ────────────────────────────────────────────────
def start_main():
    if sys.platform != "linux":
        sys.exit("这脚本只在 Linux 上跑")
    if os.geteuid() != 0:
        sys.exit("用 root 跑：sudo python3 start.py")

    check()

    # QQ 先起来：它不开 5099，所以只能等进程活一会儿
    start_qq()
    time.sleep(15)
    log("QQ 起来 15 秒了，接着拉 SnowLuma（它才能注入）")

    start_snowluma()
    if not wait_port(WEBUI_PORT, 120, "（看 logs/snowluma.log）"):
        stop_all()
        sys.exit(1)

    log("WebUI: http://127.0.0.1:%d —— 第一次要在这里扫码登录" % WEBUI_PORT)

    # 自动登录 WebUI，并把 QQ 进程 load 进去（相当于替你点「加载」）
    webui_token = login_snowluma()
    load_qq_process(webui_token)

    log("等 OneBot WS %d 起来（QQ 扫码登录成功后才会开）..." % WS_PORT)
    while not port_open(WS_PORT):
        time.sleep(3)

    token = read_token()
    cmd = [sys.executable, "-u", str(BASE / "bridge.py")]
    if token:
        cmd += ["--token", token]
    else:
        log("没读到 token，先按空 token 试")
    bridge = spawn("bridge", cmd, BASE)

    log("全部起来了，Ctrl+C 收工")
    try:
        bridge.wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == "__main__":
    start_main()
