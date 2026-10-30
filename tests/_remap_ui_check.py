# -*- coding: utf-8 -*-
r"""按键改绑 · **录键框**的 UI 级回归。

用户报：「这个按键换绑怎么只能用 4 和 t 啊」——
两个录制框永远停在构造时给的默认值 4 / t，点进去按别的键没有任何反应。

根因：HotkeyButton 自己**不存**录到的键名，它只发 changed 信号，
     由使用方调 set_value() 回写。设置页连了 changed，改绑页漏连了。
      于是 keyPressEvent 里 _end() 先把显示刷回旧值，再 emit 一个没人听的信号。

本脚本用真实 QKeyEvent 走一遍 HotkeyButton.keyPressEvent，
所以这类"信号没连"的问题只有它抓得住（直接调 set_value 的测试抓不到）。

运行: python _remap_ui_check.py
⚠ 会临时改 remap_map / remap_on 注册表键,退出时还原(atexit 兜底)。
"""
import atexit
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from PySide6.QtCore import QEvent, QSettings, Qt              # noqa: E402
from PySide6.QtGui import QFont, QKeyEvent                    # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

import pivot as M                                       # noqa: E402

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

app = QApplication(sys.argv)
app.setFont(QFont(M._pick_font(), 9))
app.setStyleSheet(M.QSS)


def pump(ms=60):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


# ============================================================================
print("\n=== 准备：清干净映射并起窗口 ===")
_st.remove("remap_map")
_st.remove("remap_on")
_st.sync()
win = M.App()
pump(120)

SRC_BTN, DST_BTN = win.rm_src, win.rm_dst
BOXES = (("源键", SRC_BTN), ("目标键", DST_BTN))

check("窗口起来了，两个录制框都在",
      SRC_BTN is not None and DST_BTN is not None)
check("初始值为示例 4 / t",
      SRC_BTN.value() == "4" and DST_BTN.value() == "t",
      f"{SRC_BTN.value()!r} / {DST_BTN.value()!r}")


def press(btn, qt_key, mods=Qt.KeyboardModifier.NoModifier):
    """点一下进录制 → 发一个真实 QKeyEvent → 返回是否仍在录制"""
    btn._begin()
    app.processEvents()
    ev = QKeyEvent(QEvent.Type.KeyPress, qt_key, mods)
    QApplication.sendEvent(btn, ev)
    app.processEvents()
    return btn._cap


# ---------------------------------------------------------------------------
print("\n=== T1 源键框：录任意键都要真的存进去 ===")
still = press(SRC_BTN, Qt.Key.Key_5)
check("T1.1 录 '5' 后退出录制态", still is False, f"still_cap={still}")
check("T1.2 录 '5' 后 value() == '5'", SRC_BTN.value() == "5",
      f"实测 {SRC_BTN.value()!r}")
check("T1.3 录 '5' 后显示文本 == '5'", SRC_BTN.text() == "5",
      f"实测 {SRC_BTN.text()!r}")

press(SRC_BTN, Qt.Key.Key_A)
check("T1.4 再录 'a' → value() == 'a'", SRC_BTN.value() == "a",
      f"实测 {SRC_BTN.value()!r}")

press(SRC_BTN, Qt.Key.Key_F9)
check("T1.5 录功能键 'f9'", SRC_BTN.value() == "f9",
      f"实测 {SRC_BTN.value()!r}")

press(SRC_BTN, Qt.Key.Key_Space)
check("T1.6 录空格 'space'", SRC_BTN.value() == "space",
      f"实测 {SRC_BTN.value()!r}")

# ---------------------------------------------------------------------------
print("\n=== T2 目标键框：同样要能录 ===")
press(DST_BTN, Qt.Key.Key_Y)
check("T2.1 录 'y' → value() == 'y'", DST_BTN.value() == "y",
      f"实测 {DST_BTN.value()!r}")
check("T2.2 显示为大写 'Y'（fmt_hotkey）", DST_BTN.text() == "Y",
      f"实测 {DST_BTN.text()!r}")

# ---------------------------------------------------------------------------
print("\n=== T3 录制态的边界行为 ===")
for label, btn in BOXES:
    btn._begin()
    app.processEvents()
    QApplication.sendEvent(
        btn, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Control,
                       Qt.KeyboardModifier.ControlModifier))
    app.processEvents()
    check(f"T3.1 ({label}) 只按修饰键不结束录制", btn._cap is True)
    btn._end()
    app.processEvents()

before = SRC_BTN.value()
SRC_BTN._begin()
app.processEvents()
QApplication.sendEvent(SRC_BTN, QKeyEvent(QEvent.Type.KeyPress,
                                          Qt.Key.Key_Escape,
                                          Qt.KeyboardModifier.NoModifier))
app.processEvents()
check("T3.2 Esc 取消录制且不改值", SRC_BTN._cap is False
      and SRC_BTN.value() == before, f"{before!r} -> {SRC_BTN.value()!r}")

# ---------------------------------------------------------------------------
print("\n=== T4 端到端：录 5 → Y 再添加，映射表要真的变 ===")
press(SRC_BTN, Qt.Key.Key_5)
press(DST_BTN, Qt.Key.Key_Y)
check("T4.1 框里现在是 5 / y",
      SRC_BTN.value() == "5" and DST_BTN.value() == "y",
      f"{SRC_BTN.value()!r} / {DST_BTN.value()!r}")
win._remap_add()
pump(60)
check("T4.2 映射表 == {'5': 'y'}", win._remap == {"5": "y"},
      f"实测 {win._remap!r}")
check("T4.3 落盘 remap_map", "5" in str(_st.value("remap_map", "")),
      f"实测 {_st.value('remap_map', '')!r}")
check("T4.4 列表里出了一行（空态提示隐藏）",
      win.rm_empty.isVisible() is False and win.rm_list.count() == 1,
      f"count={win.rm_list.count()}")

# ---------------------------------------------------------------------------
print("\n=== T5 回归：原来的 4 → T 仍然照做 ===")
press(SRC_BTN, Qt.Key.Key_4)
press(DST_BTN, Qt.Key.Key_T)
win._remap_add()
pump(60)
check("T5.1 4 → t 已加入", win._remap.get("4") == "t",
      f"实测 {win._remap!r}")
check("T5.2 两条映射并存", len(win._remap) == 2, f"实测 {win._remap!r}")

# ---------------------------------------------------------------------------
print("\n=== T6 自映射 / 重复 的拒绝仍然生效 ===")
press(SRC_BTN, Qt.Key.Key_Y)
press(DST_BTN, Qt.Key.Key_Y)
win._remap_add()
pump(40)
check("T6.1 源=目标被拒绝", "y" not in win._remap, f"实测 {win._remap!r}")

# ---------------------------------------------------------------------------
print("\n=== T7 清理并落地真实全局改键（用非 4/T 的键，证明不挑键）===")
win._remap = {"5": "y"}
win._remap_on = True
win._apply_remaps()
pump(120)
check("T7.1 真实注册了改键 5→y", "5" in win._remap_handles,
      f"handles={list(win._remap_handles)}")
win._remap_on = False
win._apply_remaps()
check("T7.2 关掉后句柄清空", len(win._remap_handles) == 0,
      f"handles={list(win._remap_handles)}")

win.close()
pump(60)

# ---------------------------------------------------------------------------
print()
print("=" * 60)
print(f"通过 {len(PASS)} / 失败 {len(FAIL)}")
for n in FAIL:
    print("  FAIL:", n)
print("=" * 60)
sys.exit(1 if FAIL else 0)
