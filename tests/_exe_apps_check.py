# -*- coding: utf-8 -*-
r"""1.2.6 出包后验证：打包好的 exe 真的会读"exe 同级的 apps\"，
而且**在那个目录里删文件就能裁掉功能**。

做法：把 exe 连同各种"被裁剪过的 apps"复制到临时目录（exe 只认自己旁边那份
apps\），启动它，再像素扫描底栏导航项的个数 —— 导航项完全由功能模块声明生成，
数目对得上就说明裁剪真的生效了。全程不碰项目里的真实产物。

运行: python _exe_apps_check.py

⚠ 每个用例都要把 47MB 的 exe 复制一份到临时目录 —— 默认临时目录在 C:，
  系统盘紧张时会直接抛 `OSError: [WinError 112] 磁盘空间不足`（踩过一次，
  C: 只剩 3MB）。把临时目录指到别的盘即可：
    TEMP=D:\枢\测试\_tmp TMP=D:\枢\测试\_tmp python _exe_apps_check.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import _exe_pages_check as P                               # noqa: E402

# 1.2.7 起是 onedir 产物：exe 在「安装包\pivot\」，旁边还有 _internal\。
# 所以复制到临时目录时必须整目录复制，只拷 exe 是跑不起来的。
from _paths import app_dir as _app_dir, apps_dir as _apps_dir  # noqa: E402

APP_DIR_SRC = _app_dir()
EXE_SRC = os.path.join(APP_DIR_SRC, "pivot.exe")
APPS_SRC = _apps_dir()

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  —— {detail}" if detail else ""))


def run_case(files, label, expect_nav, expect_switch):
    """files=None 表示不放 apps 目录；files=[] 表示放一个空目录"""
    d = tempfile.mkdtemp(prefix="tb_exe_")
    app_root = os.path.join(d, "pivot")
    exe = os.path.join(app_root, "pivot.exe")
    try:
        try:
            shutil.copytree(APP_DIR_SRC, app_root)
        except OSError as e:                       # noqa: BLE001
            check(f"{label}：复制产物到临时目录", False,
                  f"{e}（临时目录在 {d}；磁盘满时换 TEMP/TMP 到别的盘）")
            return
        # 复制来的产物可能带着上次跑测试留下的状态文件，先清掉
        for junk in ("_apps_state.json",):
            stale = os.path.join(app_root, junk)
            if os.path.exists(stale):
                os.remove(stale)
        ad = os.path.join(app_root, "apps")
        if files is None:
            shutil.rmtree(ad, ignore_errors=True)
        else:
            os.makedirs(ad, exist_ok=True)
            keep = set(files)
            for fn in os.listdir(ad):
                if fn.endswith(".py") and fn not in keep:
                    os.remove(os.path.join(ad, fn))
        P.kill_all()
        time.sleep(0.6)
        proc = subprocess.Popen([exe], cwd=d)
        hwnd = P.find_window(timeout=90)
        if not hwnd:
            check(f"{label}：窗口起来了", False, "没等到主窗口")
            return
        P.pump(3.0)
        img, sig = P.settle_shot(hwnd)          # 用长窗口判据,别抓在半路
        centers, bar_y, _cl = P.locate_nav(img)
        n = len(centers)
        check(f"{label}：窗口起来了", True)
        check(f"{label}：底栏导航 {expect_nav} 项", n == expect_nav,
              f"实测 {n} 项")

        # 点第二个导航项（第一个就是落地页，点了不会变），确认页面真的能切
        switched = None
        if expect_switch and n >= 2:
            P.click(hwnd, centers[1], bar_y)
            P.pump(0.8)
            _img2, sig2 = P.settle_shot(hwnd)
            switched = P.dist(sig, sig2) > P.SAME_TOL
        if expect_switch:
            check(f"{label}：页面仍能正常切换", switched is True,
                  f"switched={switched}")
        img.save(os.path.join(P.OUT, f"exe_apps_{label}.png"))
        P.u32.PostMessageW(hwnd, P.WM_CLOSE, 0, 0)
        P.pump(1.2)
        P.kill_all()
        try:
            proc.wait(timeout=10)
        except Exception:                      # noqa: BLE001
            pass
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    full = [f for f in sorted(os.listdir(APPS_SRC)) if f.endswith(".py")]
    print("=" * 62)
    print("绿色版 + exe 同级的 apps\\ ：删文件裁功能(出包后实测)")
    print("=" * 62)
    print(f"  apps 里共 {len(full)} 个功能文件: {full}")

    run_case(full, "01完整", 7, True)
    run_case([f for f in full if f != "keys.py"], "02删掉键盘连按", 6, True)
    run_case([f for f in full if f != "home.py"], "03删掉主页", 6, True)
    run_case([f for f in full if f != "settings.py"], "04删掉设置", 6, True)
    run_case([f for f in full if f not in ("keys.py", "remap.py",
                                           "appearance.py")], "05只剩四个功能",
             4, True)
    run_case([], "06apps为空", 0, False)
    run_case(None, "07没有apps目录(回退内置)", 7, True)

    print()
    print("=" * 62)
    print(f"通过 {len(PASS)} / 失败 {len(FAIL)}")
    for n in FAIL:
        print("  FAIL:", n)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
