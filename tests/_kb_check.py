# -*- coding: utf-8 -*-
"""1.2.5 断言:工具注册表 / 虚拟键盘 / 键盘连按引擎 / 按键改绑

运行: python _kb_check.py
⚠ 会临时改 kb_* / remap_* 注册表键,退出时还原(atexit 兜底)。
"""
import atexit
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from PySide6.QtCore import QSettings                     # noqa: E402
from PySide6.QtGui import QFont                          # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

import pivot as M                                  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  —— {detail}" if detail else ""))


KEYS = ("kb_count", "kb_interval", "remap_map", "remap_on",
        "ser_updated", "icon_patched")
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


def pump(ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


# ============================================================================
print("\n=== T1 工具注册表 ===")
ids = [t["id"] for t in M.TOOLS]
check("T1.1 定时截图已删除", "shot" not in ids, f"ids={ids}")
check("T1.2 键盘连按已就绪",
      any(t["id"] == "keys" and t["ready"] for t in M.TOOLS))
check("T1.3 按键改绑已就绪",
      any(t["id"] == "remap" and t["ready"] for t in M.TOOLS))
check("T1.4 四个工具卡片", len(M.TOOLS) == 4, f"len={len(M.TOOLS)}")


# ============================================================================
print("\n=== T2 虚拟键盘布局 ===")
bad_rows = []
for r, row in enumerate(M.KB_LAYOUT):
    total = sum(u for _l, _k, u in row)
    if abs(total - 15.0) > 1e-9:
        bad_rows.append((r, total))
check("T2.1 每行宽度都是 15u", not bad_rows, f"异常行={bad_rows}")

bad_names = []
for row in M.KB_LAYOUT:
    for _lbl, kname, _u in row:
        try:
            if not __import__("keyboard").key_to_scan_codes(kname):
                bad_names.append(kname)
        except Exception as e:  # noqa: BLE001
            bad_names.append(f"{kname}({e})")
check("T2.2 所有键名 keyboard 库都能解析", not bad_names,
      f"异常={bad_names}")

check("T2.3 行数 7", len(M.KB_LAYOUT) == 7, f"rows={len(M.KB_LAYOUT)}")

# --- 控件行为 ---
vk = M.VirtualKeyboard()
vk.resize(700, 420)
seen = []


def on_changed():
    seen.append(vk.selected())


vk.changed.connect(on_changed)
vk.toggle("t")
vk.toggle("4")
vk.toggle("shift")
check("T2.4 selected() 按布局顺序而不是点击顺序",
      vk.selected() == ["4", "t", "shift"], f"{vk.selected()}")
check("T2.5 同名键(左右 Shift)只出现一次",
      vk.selected().count("shift") == 1)
vk.toggle("t")
check("T2.6 再点一次取消", vk.selected() == ["4", "shift"], f"{vk.selected()}")
check("T2.7 changed 信号每次都发", len(seen) == 4, f"len={len(seen)}")
vk.set_counts({"4": 30})
check("T2.8 set_counts 生效", vk._counts.get("4") == 30)
vk.clear()
check("T2.9 clear 清空选中", vk.selected() == [])

# --- 命中测试:几何算出来的矩形必须落在控件内 ---
rects = vk._layout_rects()
inside = all(0 <= r.left() and r.right() <= vk.width() + 0.5
             and 0 <= r.top() and r.bottom() <= vk.height() + 0.5
             for _r, _i, _k, _l, r, _c in rects)
check("T2.10 缩放后所有键帽都在控件内", inside)
check("T2.11 键帽数量 = 布局键数",
      len(rects) == sum(len(r) for r in M.KB_LAYOUT), f"{len(rects)}")
hit = vk._hit(rects, rects[0][4].center())
check("T2.12 中心命中测试正确", hit is not None and hit[2] == rects[0][2])
# 极端尺寸下不应崩、cw 不低于下限
vk.resize(320, 150)
r2 = vk._layout_rects()
check("T2.13 最小尺寸下仍可布局", r2[0][5] >= M.VirtualKeyboard.MIN_CW - 1e-6,
      f"cw={r2[0][5]:.2f}")


# ============================================================================
print("\n=== T3 键盘连按引擎 ===")
sent = []
_orig_send = M.keyboard.send
M.keyboard.send = lambda k: sent.append((k, time.monotonic()))

rep = M.KeyRepeater()
status_log = []


def st(s):
    status_log.append(s)


ok = rep.start([("4", 3), ("t", 2)], 5, countdown_sec=0,
               on_status_update=st)
check("T3.1 start 成功", ok is True)
deadline = time.time() + 5
while rep.running and time.time() < deadline:
    time.sleep(0.01)
check("T3.2 顺序执行:4 三次再 t 两次",
      [k for k, _t in sent] == ["4", "4", "4", "t", "t"], f"{sent}")
check("T3.3 sent 计数正确", rep.sent == 5, f"sent={rep.sent}")
check("T3.4 total 由序列求和", rep.total == 5, f"total={rep.total}")
check("T3.5 结束状态为 done", status_log[-1] == "done", f"{status_log}")

# 空序列不启动
check("T3.6 空序列拒绝启动",
      rep.start([], 5, countdown_sec=0) is False)

# 倒计时广播
sent.clear()
status_log.clear()
rep2 = M.KeyRepeater()
rep2.start([("a", 1)], 5, countdown_sec=2, on_status_update=st)
deadline = time.time() + 6
while rep2.running and time.time() < deadline:
    time.sleep(0.01)
check("T3.7 倒计时逐秒广播",
      status_log[:2] == ["countdown:2", "countdown:1"], f"{status_log[:3]}")

# stop 能中断
sent.clear()
rep3 = M.KeyRepeater()
done_status = []


def st3(s):
    done_status.append(s)


rep3.start([("a", 100000)], 1, countdown_sec=0, on_status_update=st3)
time.sleep(0.15)
rep3.stop()
time.sleep(0.2)
check("T3.8 stop 能中断长序列",
      (not rep3.running) and rep3.sent < 100000
      and "已停止" in done_status, f"sent={rep3.sent} st={done_status[-1:]}")

# 异常要回传 error
sent.clear()
rep4 = M.KeyRepeater()
err = []


def st4(s):
    err.append(s)


_orig2 = M.keyboard.send
M.keyboard.send = lambda k: (_ for _ in ()).throw(RuntimeError("boom"))
rep4.start([("a", 1)], 5, countdown_sec=0, on_status_update=st4)
deadline = time.time() + 3
while rep4.running and time.time() < deadline:
    time.sleep(0.01)
check("T3.9 发送异常回传 error", any(s.startswith("error") for s in err),
      f"{err}")
M.keyboard.send = _orig_send


# ============================================================================
print("\n=== T4 键名显示 ===")
check("T4.1 单字符转大写", M.fmt_key_name("a") == "A")
check("T4.2 space -> Space", M.fmt_key_name("space") == "Space")
check("T4.3 page up -> PgUp", M.fmt_key_name("page up") == "PgUp")
check("T4.4 shift -> Shift", M.fmt_key_name("shift") == "Shift")
check("T4.5 方向键转箭头", M.fmt_key_name("left") == "←")


# ============================================================================
print("\n=== T5 按键改绑 ===")
win = M.App()
win.resize(1180, 760)
win.show()
pump(300)
win.splash.hide()
win._reveal_wallpaper()
win._blocks_in()
pump(800)

check("T5.1 新页面已挂进 QStackedWidget",
      win.stack.indexOf(win.page_keys) >= 0
      and win.stack.indexOf(win.page_remap) >= 0)
check("T5.2 底部导航 7 个 tab",
      list(win.nav_tabs) == ["home", "clicker", "keys", "remap",
                             "appearance", "settings", "update"],
      f"{list(win.nav_tabs)}")
check("T5.3 切页后 tab 高亮跟着走",
      (win.go("keys") or win.nav_tabs["keys"]._sel)
      and not win.nav_tabs["home"]._sel)
check("T5.4 go('remap') 可切换", (win.go("remap") or True)
      and win.stack.currentWidget() is win.page_remap)

# --- 滚动区 viewport 透明(否则深色玻璃上是一块白板) ---
check("T5.5 已选按键滚动区 viewport 透明",
      win.kb_scroll.viewport().objectName() == "wpViewport"
      and not win.kb_scroll.viewport().autoFillBackground())
check("T5.6 映射表滚动区 viewport 透明",
      win.rm_scroll.viewport().objectName() == "wpViewport"
      and not win.rm_scroll.viewport().autoFillBackground())

# --- 选中 -> 列表 / 键帽徽标 ---
win.go("keys")
win.vkbd.clear()
win.vkbd.toggle("4")
pump(120)
check("T5.7 选键后列表出现一行", win.kb_list.count() == 1,
      f"count={win.kb_list.count()}")
check("T5.8 新键拿默认次数",
      win.kb_count_edits["4"].text() == str(win._kb_default),
      win.kb_count_edits["4"].text())
win.kb_count_edits["4"].setText("77")
pump(80)
check("T5.9 改次数后写入 vkbd 徽标", win.vkbd._counts.get("4") == 77,
      f"{win.vkbd._counts}")
win.kb_bulk.setText("9")
win._kb_apply_bulk()
check("T5.10 统一次数应用到全部",
      win.kb_count_edits["4"].text() == "9"
      and win._kb_default == 9, win.kb_count_edits["4"].text())
win.vkbd.clear()
pump(80)
check("T5.11 清空后列表回到空态",
      win.kb_list.count() == 0 and win.kb_empty.isVisible())

# --- 映射表增删改与持久化 ---
win._remap.clear()
win._remap_on = False
win._save_remaps()
win.rm_src.set_value("4")
win.rm_dst.set_value("t")
win._remap_add()
check("T5.12 添加 4 -> t", win._remap == {"4": "t"}, f"{win._remap}")
check("T5.13 映射表渲染一行", win.rm_list.count() == 1)

win.rm_dst.set_value("4")
win._remap_add()
check("T5.14 源=目标被拒绝", win._remap == {"4": "t"}, f"{win._remap}")

win.rm_dst.set_value("ctrl+t")
win._remap_add()
check("T5.15 组合键被拒绝", win._remap == {"4": "t"}, f"{win._remap}")

win.rm_src.set_value("f8")
win.rm_dst.set_value("f9")
win._remap_add()
check("T5.16 可加多条", win._remap == {"4": "t", "f8": "f9"},
      f"{win._remap}")

win._save_remaps()
raw = _st.value("remap_map")
check("T5.17 映射持久化成 JSON", isinstance(raw, str) and "4" in raw, f"{raw}")

# 开关:真的注册 / 真的摘掉
win.rm_sw.setChecked(True, animate=False)
win._on_remap_toggle(True)
check("T5.18 打开开关后真的注册了改键",
      sorted(win._remap_handles) == ["4", "f8"], f"{sorted(win._remap_handles)}")
check("T5.19 remap_on 落盘",
      _st.value("remap_on") == "true", f"{_st.value('remap_on')}")
win.rm_sw.setChecked(False, animate=False)
win._on_remap_toggle(False)
check("T5.20 关掉后全部摘除", win._remap_handles == {},
      f"{win._remap_handles}")

# 录制期间必须临时摘掉映射(否则源键会被自己的映射吞掉)
win.rm_sw.setChecked(True, animate=False)
win._on_remap_toggle(True)
before = sorted(win._remap_handles)
win._remap_capture(True)
during = sorted(win._remap_handles)
win._remap_capture(False)
after = sorted(win._remap_handles)
check("T5.21 录键期间临时摘掉映射、录完恢复",
      before == ["4", "f8"] and during == [] and after == ["4", "f8"],
      f"{before} / {during} / {after}")
win.rm_sw.setChecked(False, animate=False)
win._on_remap_toggle(False)

# --- reload(模拟重启) ---
win2_map = win._remap.copy()
win._remap = {}
win._load_remaps()
check("T5.22 _load_remaps 能从注册表恢复", win._remap == win2_map,
      f"{win._remap}")

# 冲突提示
win._hk_start = "f8"
win._sync_remap_state()
check("T5.23 源键撞热键时给出提示",
      "撞车" in win.rm_hint.text(), win.rm_hint.text())

# 移除 / 清空
win._hk_start = "f6"
win._remap_remove("f8")
check("T5.24 移除单条", "f8" not in win._remap, f"{win._remap}")
win._remap_clear()
check("T5.25 清空映射表",
      win._remap == {} and win.rm_list.count() == 0
      and win.rm_empty.isVisibleTo(win.page_remap))
win._save_remaps()


# ============================================================================
print("\n=== T6 热键上下文 ===")
calls = []
_ks, _kst = win.kb_start, win.kb_stop
_ms, _mst = win.on_start, win.on_stop
win.kb_start = lambda: calls.append("kb_start")
win.kb_stop = lambda: calls.append("kb_stop")
win.on_start = lambda: calls.append("mouse_start")
win.on_stop = lambda: calls.append("mouse_stop")

win._page = "keys"
win._on_hotkey("start")
win._on_hotkey("stop")
check("T6.1 keys 页上 F6/F7 驱动键盘连按",
      calls == ["kb_start", "kb_stop"], f"{calls}")

calls.clear()
win._page = "clicker"
win._on_hotkey("start")
win._on_hotkey("stop")
check("T6.2 其他页面仍然是鼠标连点器",
      calls == ["mouse_start", "mouse_stop"], f"{calls}")

calls.clear()
win._page = "home"
win._on_hotkey("start")
check("T6.3 home 页也走鼠标连点器", calls == ["mouse_start"], f"{calls}")

win.kb_start, win.kb_stop = _ks, _kst
win.on_start, win.on_stop = _ms, _mst


# ============================================================================
print("\n=== T7 键盘连按端到端(真跑一遍,keyboard.send 打桩) ===")
sent.clear()
M.keyboard.send = lambda k: sent.append(k)
win.go("keys")
win.vkbd.clear()
win.vkbd.toggle("q")
win.kb_count_edits["q"].setText("4")
win.kb_interval.setText("1")
pump(80)
win.kb_start()
check("T7.1 启动后按钮状态切换",
      not win.kb_start_btn.isEnabled() and win.kb_stop_btn.isEnabled())
deadline = time.time() + 8
while win.kbrep.running and time.time() < deadline:
    pump(40)
pump(200)
check("T7.2 端到端连按 4 次", sent == ["q"] * 4, f"{sent}")
check("T7.3 结束后复位", win.kb_start_btn.isEnabled()
      and not win.kb_stop_btn.isEnabled() and win._kb_total == 0)
check("T7.4 计数器显示总数", win.kb_counter._value == 4,
      f"{win.kb_counter._value}")
check("T7.5 卡片状态回到可用",
      win.tool_cards["keys"].badge.text() == "可用",
      win.tool_cards["keys"].badge.text())

# 空选中时拒绝启动
win.vkbd.clear()
pump(60)
before = len(sent)
win.kb_start()
check("T7.6 没选键时拒绝启动且给出提示",
      len(sent) == before and "选" in win.kb_status.text(),
      win.kb_status.text())

M.keyboard.send = _orig_send

# 收尾
win._remap.clear()
win._remap_on = False
win._save_remaps()
win.close()
pump(200)

# ============================================================================
print("\n" + "=" * 62)
print(f"结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
if FAIL:
    print("失败项:")
    for f in FAIL:
        print("   -", f)
sys.exit(1 if FAIL else 0)
