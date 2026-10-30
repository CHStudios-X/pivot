# -*- coding: utf-8 -*-
"""静默安装 → 检查安装目录内容 → 卸载 → 核对残留

除了"文件在不在",还要比对**安装出来的文档与当前源文件是否逐字节一致** ——
文档在打包之后被改过是很容易漏掉的漂移(README 改完了但忘了重出安装包)。
"""
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 动态取最新一次构建出的安装包 —— 升版本不用再改脚本(按修改时间,防 1.2.10 排序坑)
# 1.3.0 起安装包叫 Pivot_Setup_*；只有还没出新包时才退回旧的 MouseMacro_Setup_*
_setups = (glob.glob(os.path.join(ROOT, "dist", "Pivot_Setup_*.exe"))
           or glob.glob(os.path.join(ROOT, "dist", "MouseMacro_Setup_*.exe")))
PKG = max(_setups, key=os.path.getmtime) if _setups else \
    os.path.join(ROOT, "dist", "Pivot_Setup_1.3.0.exe")
DOC = os.path.join(ROOT, "docs")
# 随装的两个文档来自不同位置：README 在仓库根（GitHub 首页要它），
# 用户协议在 docs\（安装器当 LicenseFile 用）
DOC_SOURCES = {
    "README.md": os.path.join(ROOT, "README.md"),
    "用户协议.txt": os.path.join(DOC, "用户协议.txt"),
}
# 装到项目内的临时目录:① 注入沙箱下 C:\temp 会被拒(踩过,表现为"安装目录没出现")
#                          ② 卸载脚本本来就会清空它,不会留垃圾
DIR = os.path.join(ROOT, "tests", "_tmp", "install")


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def clean_temp():
    """清掉 Inno 在 %TEMP%\\is-*.tmp 留下的工作目录(卸载后常残留一份)。"""
    import glob
    n = 0
    for d in sorted(glob.glob(os.path.join(os.environ.get("TEMP", ""), "is-*.tmp"))):
        try:
            shutil.rmtree(d)
            n += 1
        except OSError:
            pass
    return n


def main():
    if os.path.exists(DIR):
        shutil.rmtree(DIR, ignore_errors=True)
    print("安装到", DIR)
    subprocess.Popen([PKG, "/VERYSILENT", f"/DIR={DIR}", "/TASKS="])
    want = ("pivot.exe", "README.md", "用户协议.txt", "app.ico")
    # 1.2.6: 功能模块作为外置目录随装到 {app}\apps\ —— 这是"装完还能删功能"
    # 的前提,必须验。源码里 apps\ 有哪些 .py,装出来就该有哪些(一个不少)。
    src_apps = os.path.join(ROOT, "apps")
    want_apps = sorted(f for f in os.listdir(src_apps) if f.endswith(".py")) \
        if os.path.isdir(src_apps) else []
    # 注意不能只等 unins000.exe 出现就查 —— 那一刻主程序还在解压
    # (目录里会看到一个 is-XXXX.tmp),要等到目标文件全都到位
    for _ in range(90):
        time.sleep(1.0)
        if os.path.isdir(DIR) and all(
                os.path.exists(os.path.join(DIR, w)) for w in want):
            break
    time.sleep(2.5)                      # 让 Inno 收尾
    if not os.path.isdir(DIR):
        print("!! 安装目录没出现")
        return 1
    items = sorted(os.listdir(DIR))
    print("安装目录内容:")
    for n in items:
        p = os.path.join(DIR, n)
        print(f"   {n:20} {os.path.getsize(p) if os.path.isfile(p) else '<目录>'}")

    miss = [w for w in want if w not in items]
    print("缺失文件 =", miss if miss else "无 ✓")

    # --- 外置功能目录 apps\ ---
    got_apps_dir = os.path.join(DIR, "apps")
    if os.path.isdir(got_apps_dir):
        got_apps = sorted(f for f in os.listdir(got_apps_dir) if f.endswith(".py"))
        miss_apps = [f for f in want_apps if f not in got_apps]
        extra_apps = [f for f in got_apps if f not in want_apps]
        print(f"apps\\ 目录已随装 ✓  ({len(got_apps)} 个功能文件)")
        print("   apps 缺失 =", miss_apps if miss_apps else "无 ✓")
        print("   apps 多余 =", extra_apps if extra_apps else "无 ✓")
        print("   说明.txt   =",
              "在 ✓" if os.path.exists(os.path.join(got_apps_dir, "说明.txt"))
              else "缺 ✗")
    else:
        miss_apps = ["<整个 apps 目录>"]
        print("apps\\ 目录已随装 ✗  (整目录缺失 —— 装完就删不了功能了)")
    miss = list(miss) + miss_apps

    lic = os.path.join(DIR, "用户协议.txt")
    if os.path.exists(lic):
        head = open(lic, encoding="utf-8-sig").read().splitlines()[:3]
        print("协议开头 =", " / ".join(head))
        signed = any("CHStudios" in ln for ln in
                     open(lic, encoding="utf-8-sig").read().splitlines())
        print("协议已署名 CHStudios =", signed)

    print("--- 文档一致性(安装出的 vs 当前源文件) ---")
    drift = []
    for name, src in DOC_SOURCES.items():
        got = os.path.join(DIR, name)
        if not (os.path.exists(src) and os.path.exists(got)):
            drift.append(name + "(缺失)")
            print(f"   {name:12} 缺失")
            continue
        a, b = md5(src), md5(got)
        same = a == b
        if not same:
            drift.append(name)
        print(f"   {name:12} {'一致 ✓' if same else '不一致 ✗'}  "
              f"源={os.path.getsize(src)} 装={os.path.getsize(got)}")
    print("文档漂移 =", drift if drift else "无 ✓")

    # 卸载
    print("开始卸载…")
    subprocess.Popen([os.path.join(DIR, "unins000.exe"), "/VERYSILENT"])
    for _ in range(45):
        time.sleep(1.0)
        if not os.path.isdir(DIR):
            break
    time.sleep(2.0)
    print("卸载后目录仍存在 =", os.path.isdir(DIR))
    if os.path.isdir(DIR):
        rest = os.listdir(DIR)
        print("  残留:", rest if rest else "(空)")
        shutil.rmtree(DIR, ignore_errors=True)

    import winreg
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
    hits, i = [], 0
    while True:
        try:
            sub = winreg.EnumKey(k, i)
        except OSError:
            break
        i += 1
        try:
            kk = winreg.OpenKey(k, sub)
            dn = winreg.QueryValueEx(kk, "DisplayName")[0]
            if "枢" in dn or "Pivot" in dn:
                hits.append(dn)
        except OSError:
            pass
    print("注册表残留 =", hits if hits else "无 ✓")
    print("清理 Inno 临时目录", clean_temp(), "个")
    return 0 if (not miss and not drift) else 2


if __name__ == "__main__":
    sys.exit(main())
