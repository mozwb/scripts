"""download.py —— 服务器端「检查 → 缺了就装」

只管第一部分：把跑起来需要的东西都备齐（不启动）。
顺序：
  1 基础依赖（xvfb / 中文字体 / unzip / curl）
  2 Linux QQ
  3 Node.js（SnowLuma 要 24+）
  4 DSH
  5 SnowLuma

用法：sudo python3 download.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / "_downloads"


# ── 小工具 ────────────────────────────────────────────────
def has_cmd(name):
    return shutil.which(name) is not None


def sh(cmd):
    print("+", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)


def out(cmd):
    """跑一条命令拿输出，失败返回空串。"""
    try:
        return subprocess.run(
            cmd, shell=True, check=True, capture_output=True, text=True
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def download(url, dest):
    """带进度地下载，已有且够大就跳过。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print("已存在，跳过下载:", dest.name)
        return dest

    req = urllib.request.Request(url, headers={"User-Agent": "dsh"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        last = 0
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if time.time() - last > 2:
                pct = (done / total * 100) if total else 0
                print("  %.1f%%  %.1f/%.1f MB"
                      % (pct, done / 1048576, total / 1048576), flush=True)
                last = time.time()
    print("  完成: %s (%.1f MB, %.0fs)"
          % (dest.name, dest.stat().st_size / 1048576, time.time() - start))
    return dest


# ── 1 基础依赖 ────────────────────────────────────────────
def step_base():
    need = []
    if not has_cmd("Xvfb"):
        need.append("xvfb")
    if not has_cmd("unzip"):
        need.append("unzip")
    if not has_cmd("curl"):
        need.append("curl")
    if not need:
        print("[1] 基础依赖齐全")
        return

    print("[1] 安装:", " ".join(need))
    sh("apt-get update")
    sh("apt-get install -y %s fonts-noto-cjk" % " ".join(need))


# ── 2 Linux QQ ───────────────────────────────────────────
# 官方地址写在一个 JS 配置里，每次发版都变，所以运行时去取，别写死
QQ_CONFIG = "https://cdn-go.cn/qq-web/im.qq.com_new/latest/rainbow/linuxConfig.js"
# 官方 CDN 会拦机房 IP（403），备胎是一个镜像仓库的 Release
QQ_MIRROR_REPO = "Rodert/qq-versions"


def resolve_qq_url():
    req = urllib.request.Request(QQ_CONFIG, headers={"User-Agent": "Mozilla/5.0"})
    js = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    for u in re.findall(r"https?://[^\"'\s]+", js):
        if u.endswith("_amd64_01.deb"):
            print("  官方 deb:", u)
            return u
    raise RuntimeError("官方配置里没找到 amd64 的 deb")


def resolve_qq_mirror():
    api = "https://api.github.com/repos/%s/releases/latest" % QQ_MIRROR_REPO
    req = urllib.request.Request(api, headers={"User-Agent": "dsh"})
    info = json.load(urllib.request.urlopen(req, timeout=30))
    for a in info.get("assets", []):
        if a["name"].endswith("_amd64_01.deb"):
            print("  镜像 deb: %s (%.0f MB)" % (a["name"], a["size"] / 1048576))
            return a["browser_download_url"]
    raise RuntimeError("镜像里也没有 amd64 的 deb")


def step_qq():
    if os.path.exists("/opt/QQ/qq") or has_cmd("qq"):
        print("[2] QQ 已安装")
        return

    print("[2] 安装 Linux QQ")
    try:
        url = resolve_qq_url()
        deb = download(url, CACHE / "linuxqq.deb")
    except Exception as e:
        print("  官方源不行（%s），换镜像" % str(e)[:60])
        try:
            url = resolve_qq_mirror()
            deb = download(url, CACHE / "linuxqq.deb")
        except Exception as e2:
            raise SystemExit(
                "两条源都失败了: %s\n"
                "手动下好放进 %s 并改名 linuxqq.deb 再重跑" % (e2, CACHE)
            )
    sh("apt-get install -y %s" % deb)


# ── 2.5 QQ 跑起来需要的系统库 ────────────────────────────
# 无头容器里这些基本都没有，缺一个 QQ 就起不来（libasound 最常见）
QQ_DEPS = [
    "libasound2", "libnss3", "libgbm1", "libxss1", "libxtst6",
    "libatk1.0-0", "libatk-bridge2.0-0", "libcups2", "libdrm2",
    "libgtk-3-0", "libxcomposite1", "libxdamage1", "libxrandr2",
    "libxkbcommon0", "libpango-1.0-0", "libcairo2", "libxshmfence1",
    "libx11-xcb1", "xauth",
]


def step_qq_deps():
    print("[2.5] 检查 QQ 运行库")
    sh("apt-get update -qq")
    for pkg in QQ_DEPS:
        # 有的发行版包名带 t64 后缀，装不上就试一下，别整段挂掉
        r = subprocess.run("apt-get install -y %s" % pkg, shell=True,
                           capture_output=True, text=True)
        if r.returncode != 0:
            alt = pkg + "t64"
            r2 = subprocess.run("apt-get install -y %s" % alt, shell=True,
                                capture_output=True, text=True)
            if r2.returncode != 0:
                print("  跳过（装不上）:", pkg)
    print("  运行库就绪")


# ── 3 Node.js 24+ ────────────────────────────────────────
def node_major():
    v = out("node -v")          # 形如 v24.22.1
    m = re.match(r"v(\d+)", v)
    return int(m.group(1)) if m else 0


def step_node():
    if node_major() >= 24:
        print("[3] Node 版本够:", out("node -v"))
        return

    print("[3] 安装 Node 24")
    sh("curl -fsSL https://deb.nodesource.com/setup_24.x | bash -")
    sh("apt-get install -y nodejs")


# ── 4 DSH ────────────────────────────────────────────────
def step_dsh():
    if has_cmd("dsh"):
        print("[4] DSH 已安装")
        return

    print("[4] 安装 DSH")
    sh("npm install -g @deepseek-ai/dsh")


# ── 5 SnowLuma ───────────────────────────────────────────
REPO = "SnowLuma/SnowLuma"
VERSION = "latest"                     # 想钉版本就写 "v2.2.1"
ASSET_SUFFIX = "-linux-x64.tar.gz"     # 别选 -lite


def resolve_snowluma():
    api = ("https://api.github.com/repos/%s/releases/latest" % REPO
           if VERSION == "latest"
           else "https://api.github.com/repos/%s/releases/tags/%s" % (REPO, VERSION))
    req = urllib.request.Request(api, headers={"User-Agent": "dsh"})
    info = json.load(urllib.request.urlopen(req, timeout=30))

    for a in info.get("assets", []):
        name = a["name"]
        if name.endswith(ASSET_SUFFIX) and "-lite" not in name:
            print("  版本 %s (%d MB)" % (info["tag_name"], a["size"] // 1048576))
            return info["tag_name"], a["browser_download_url"]
    raise SystemExit("没找到 %s 结尾的包" % ASSET_SUFFIX)


def step_snowluma():
    target = BASE / "snowluma"
    if (target / "index.mjs").exists():
        print("[5] SnowLuma 已就位:", target)
        return

    print("[5] 安装 SnowLuma")
    tag, url = resolve_snowluma()
    tar = download(url, CACHE / ("snowluma-%s.tar.gz" % tag))

    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar, "r:gz") as tf:
        # 压缩包里通常带一层 SnowLuma-xxx/ 目录，剥掉它
        members = []
        for m in tf.getmembers():
            parts = m.name.split("/", 1)
            if len(parts) == 2 and parts[1]:
                m.name = parts[1]
                members.append(m)
        tf.extractall(target, members=members)
    print("  解压到:", target)


# ── 入口 ────────────────────────────────────────────────
def download_main():
    if sys.platform != "linux":
        sys.exit("这个脚本只跑 Linux，当前是 %s" % sys.platform)
    if os.geteuid() != 0:
        sys.exit("要用 root 跑：sudo python3 download.py")

    CACHE.mkdir(parents=True, exist_ok=True)

    step_base()
    step_qq()
    step_qq_deps()
    step_node()
    step_dsh()
    step_snowluma()

    print("\n全部就绪。下一步：sudo python3 start.py")


if __name__ == "__main__":
    download_main()
