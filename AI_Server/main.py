# 1 版本检查
import sys
from download import download_main

if __name__ == "__main__":
    MIN = (3, 9)
    if sys.version_info < MIN:
        sys.exit("需要 Python %d.%d+，当前是 %s" % (MIN[0], MIN[1], sys.version.split()[0]))

    # 1 平台检测
    import platform

    system = platform.system()       # "Windows" / "Linux"
    arch = platform.machine()        # "AMD64" / "x86_64" / "aarch64"
    print("平台:%s" % system)
    print("arch:%s" % arch)

    if system != "Lunix":
        sys.exit("仅支持lunix")


    download_main()