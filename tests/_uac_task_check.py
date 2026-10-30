# -*- coding: utf-8 -*-
"""按「默认任务集」静默安装,核对 RUNASADMIN 兼容性标志的写入与卸载清理。

为什么单独一个脚本:
    `_install_test.py` 用的是 `/TASKS=`(全部任务不勾),正好把出问题的
    「以管理员身份运行」任务排除掉了 —— 这就是 740 那个坑溜过自测的原因。
    这里故意**不传 /TASKS**,走向导的默认勾选(checkedonce = 默认勾上),
    验证 [Registry] 那段确实把 RUNASADMIN 写进了 HKCU\\...\\AppCompatFlags\\Layers,
    以及卸载时被 uninsdeletevalue 收干净。
    标志在 = 主程序被系统判定为"必须提权才允许启动",这正是 740 的前半段。
"""
import glob
import os
import shutil
import subprocess
import sys
import time
import winreg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 动态取最新一次构建出的安装包 —— 升版本不用再改脚本(按修改时间,防 1.2.10 排序坑)
# 1.3.0 起安装包叫 Pivot_Setup_*；只有还没出新包时才退回旧的 MouseMacro_Setup_*
_setups = (glob.glob(os.path.join(ROOT, "dist", "Pivot_Setup_*.exe"))
           or glob.glob(os.path.join(ROOT, "dist", "MouseMacro_Setup_*.exe")))
PKG = max(_setups, key=os.path.getmtime) if _setups else \
    os.path.join(ROOT, "dist", "Pivot_Setup_1.3.0.exe")
DIR = os.path.join(ROOT, "测试", "_install_tmp_task")   # 必须放项目内(踩过:C:\temp 被拒)
EXE = os.path.join(DIR, "pivot.exe")
LAYERS = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"


def layer(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LAYERS) as k:
            return winreg.QueryValueEx(k, path)[0]
    except OSError:
        return None


def clean_temp():
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
    shutil.rmtree(DIR, ignore_errors=True)
    if layer(EXE) is not None:                 # 上次跑崩留下的
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, LAYERS, 0,
                                winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, EXE)

    print("安装到", DIR, "(默认任务集)")
    subprocess.Popen([PKG, "/VERYSILENT", f"/DIR={DIR}"])
    want = ("pivot.exe", "README.md", "用户协议.txt", "app.ico")
    for _ in range(90):
        time.sleep(1.0)
        if os.path.isdir(DIR) and all(os.path.exists(os.path.join(DIR, w)) for w in want):
            break
    time.sleep(2.5)
    ok_install = all(os.path.exists(os.path.join(DIR, w)) for w in want)
    print("安装完成 =", ok_install)

    got = layer(EXE)
    print(f"RUNASADMIN 标志 = {got!r}  (期望 'RUNASADMIN')")
    print("以管理员身份运行任务生效 =", "是 ✓" if got == "RUNASADMIN" else "否 ✗")

    print("开始卸载…")
    subprocess.Popen([os.path.join(DIR, "unins000.exe"), "/VERYSILENT"])
    for _ in range(45):
        time.sleep(1.0)
        if not os.path.isdir(DIR):
            break
    time.sleep(2.0)
    left = layer(EXE)
    print(f"卸载后标志 = {left!r}  (期望 None)")
    print("卸载清理干净 =", "是 ✓" if left is None else "否 ✗")
    shutil.rmtree(DIR, ignore_errors=True)
    print("清理 Inno 临时目录", clean_temp(), "个")

    good = ok_install and got == "RUNASADMIN" and left is None
    print("\n结论:", "通过 ✓" if good else "不通过 ✗")
    return 0 if good else 2


if __name__ == "__main__":
    sys.exit(main())
