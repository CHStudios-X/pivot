# -*- coding: utf-8 -*-
r"""1.2.6 出包后验证:exe 里那份 HotkeyButton **真的能录到任意键**。

背景:用户报「按键换绑只能用 4 和 t」——
      根因是 HotkeyButton 只发 changed、不自己存键名,改绑页又漏连了 changed,
      于是两个录制框永远停在构造时的 4 / T。修完必须验**交付产物**(exe),
      不能只在源码上跑。

做法(不碰交付产物):
  1. 把 exe 同级的 apps\*.py 复制到临时目录;
  2. 只在临时副本的 remap.py 末尾**追加一段探针**——
     页面构建完 600ms 后,用真实 QKeyEvent 走 HotkeyButton.keyPressEvent
     录 5 和 Y,再调 _remap_add(),把结果写进 JSON;
  3. 用 TOOLBOX_APPS_DIR 指到那个临时目录启动**真 exe**
     (exe 内置的 pivot_kit / HotkeyButton 是真货,只有功能模块是副本);
  4. 等 JSON,断言 src=='5' / dst=='y' / map=={'5':'y'}。
     —— 坏版本会写出 src=='4' / dst=='t'(框认不出录的键)。

这样验的是"出包后真实跑的代码路径",又完全不依赖坐标猜测,不会假阳性。

运行: python _exe_remap_check.py
⚠ 会临时改 remap_map / remap_on 注册表键,退出时还原(atexit 兜底)。
"""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from _paths import apps_dir as _apps_dir, exe_path as _exe_path  # noqa: E402

EXE_SRC = _exe_path()
APPS_SRC = _apps_dir()

from PySide6.QtCore import QSettings                        # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  —— {detail}" if detail else ""))


KEYS = ("remap_map", "remap_on")
_st = QSettings("Pivot", "Pivot")
_BACKUP = {k: (_st.contains(k), _st.value(k) if _st.contains(k) else None)
           for k in KEYS}


def restore_reg():
    for k, (had, val) in _BACKUP.items():
        _st.remove(k)
        if had:
            _st.setValue(k, val)
    _st.sync()
    print("[cleanup] 注册表已还原")


atexit.register(restore_reg)


PROBE = '''

# ==================== 出包后探针（仅测试注入，不改动任何原逻辑）==========
def _probe_run(self, out_path):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    import json as _json

    def _rec(btn, key):
        btn._begin()
        QApplication.processEvents()
        ev = QKeyEvent(QEvent.Type.KeyPress, key,
                       Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(btn, ev)          # 走真实 keyPressEvent
        QApplication.processEvents()

    _rec(self.rm_src, Qt.Key.Key_5)
    _rec(self.rm_dst, Qt.Key.Key_Y)
    self._remap_add()
    QApplication.processEvents()
    with open(out_path, "w", encoding="utf-8") as fp:
        _json.dump({"src": self.rm_src.value(),
                    "dst": self.rm_dst.value(),
                    "map": self._remap,
                    "src_text": self.rm_src.text(),
                    "dst_text": self.rm_dst.text()}, fp, ensure_ascii=False)


_ORIG_BUILD_REMAP = Feature._build_remap


def _probe_build(self):
    pg = _ORIG_BUILD_REMAP(self)
    from PySide6.QtCore import QTimer
    _out = __import__("os").environ.get("TOOLBOX_REMAP_PROBE_OUT", "")
    if _out:
        QTimer.singleShot(700, lambda: _probe_run(self, _out))
    return pg


Feature._build_remap = _probe_build
# ========================================================================
'''


def kill_all():
    subprocess.run(["taskkill", "/F", "/IM", "pivot.exe"],
                   capture_output=True)


def main():
    print("=" * 62)
    print("出包后：exe 里的按键改绑录制框能录任意键吗")
    print("=" * 62)

    if not os.path.exists(EXE_SRC):
        print("FAIL 找不到", EXE_SRC)
        return 1

    tmp = tempfile.mkdtemp(prefix="tb_remap_")
    apps = os.path.join(tmp, "apps")
    os.makedirs(apps)
    for fn in sorted(os.listdir(APPS_SRC)):
        if fn.endswith(".py"):
            shutil.copy2(os.path.join(APPS_SRC, fn), apps)
    # 别写死 7 —— 每加一个功能模块这条就假失败一次。按源目录实际文件比。
    _src_py = sorted(f for f in os.listdir(APPS_SRC) if f.endswith(".py"))
    check("临时 apps 里的功能文件全部就位",
          sorted(f for f in os.listdir(apps) if f.endswith(".py")) == _src_py,
          f"{len(_src_py)} 个: {_src_py}")

    rp = os.path.join(apps, "remap.py")
    with open(rp, "a", encoding="utf-8") as fp:
        fp.write(PROBE)

    out_file = os.path.join(tmp, "probe.json")
    env = dict(os.environ)
    env["TOOLBOX_APPS_DIR"] = apps
    env["TOOLBOX_REMAP_PROBE_OUT"] = out_file

    # 先把映射清干净,免得旧数据干扰
    _st.remove("remap_map")
    _st.remove("remap_on")
    _st.sync()

    kill_all()
    time.sleep(0.6)
    print("  启动真 exe(仍用交付的那份 pivot.exe)")
    proc = subprocess.Popen([EXE_SRC], cwd=tmp, env=env)

    data = None
    for _ in range(120):                     # 最多等 60 秒(onefile 解包慢)
        time.sleep(0.5)
        if os.path.exists(out_file):
            time.sleep(0.3)
            try:
                with open(out_file, encoding="utf-8") as fp:
                    data = json.load(fp)
                break
            except Exception:                # noqa: BLE001
                pass

    check("exe 起来了并跑完录键探针", data is not None,
          "没等到 probe.json" if data is None else "")

    if data:
        check("源键框录到 '5'(不再是默认的 4)",
              data["src"] == "5", f"实测 {data['src']!r}")
        check("目标键框录到 'y'(不再是默认的 t)",
              data["dst"] == "y", f"实测 {data['dst']!r}")
        check("显示文本同步更新",
              data["src_text"] == "5" and data["dst_text"] == "Y",
              f"{data['src_text']!r} / {data['dst_text']!r}")
        check("映射表 == {'5': 'y'}", data["map"] == {"5": "y"},
              f"实测 {data['map']!r}")
        check("映射已落盘 QSettings",
              "5" in str(_st.value("remap_map", "")),
              f"实测 {_st.value('remap_map', '')!r}")

    kill_all()
    try:
        proc.wait(timeout=10)
    except Exception:                        # noqa: BLE001
        pass
    shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 62)
    print(f"通过 {len(PASS)} / 失败 {len(FAIL)}")
    for n in FAIL:
        print("  FAIL:", n)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
