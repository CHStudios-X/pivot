# -*- coding: utf-8 -*-
"""v1.2.4 回归:SER 更新通道彩蛋链路 —— 标记宽度 / 连点计数 / 访问码 /
   命令提示符控制台 / 1.3.ser 更新 / 注册表持久化 + 重启恢复

运行: python _egg_check.py
注: QT_QPA_PLATFORM=offscreen 下没有真实字体引擎,本脚本只跑【逻辑断言】,
    不做像素断言(字体度量在离屏下虚高,见 归档说明 踩坑记录)。
    脚本会动真实注册表的 ser_updated —— 开头备份原值,atexit 兜底还原,
    绝不替用户解锁彩蛋。
"""
import atexit
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
import pivot as M

bad = []

# ---- 注册表保护:备份 ser_updated,退出时还原(不替用户更新) ----
_st = QSettings("Pivot", "Pivot")
_HAD = _st.contains("ser_updated")
_VAL = _st.value("ser_updated") if _HAD else None
_st.remove("ser_updated")
_st.sync()


def restore_reg():
    try:
        _st.remove("ser_updated")
        if _HAD:
            _st.setValue("ser_updated", _VAL)
        _st.sync()
        print(f"[cleanup] 注册表 ser_updated 已还原(原值: {_VAL!r})")
    except Exception as e:
        print("[cleanup] 还原失败:", e)


atexit.register(restore_reg)

app = QApplication(sys.argv)
app.setFont(QFont(M._pick_font(), 9))
app.setStyleSheet(M.QSS)


def pump(sec):
    t0 = time.monotonic()
    while time.monotonic() - t0 < sec:
        app.processEvents()
        time.sleep(0.008)


def pump_until(cond, timeout):
    t0 = time.monotonic()
    while not cond() and time.monotonic() - t0 < timeout:
        app.processEvents()
        time.sleep(0.008)
    return cond()


def hdr(t):
    print()
    print("=" * 68)
    print(t)
    print("=" * 68)


def ck(cond, msg):
    print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        bad.append(msg)


# ----------------------------------------------------------------
hdr("T1 常量与版本")
print(f"  APP_VER={M.APP_VER}  SER_VER={M.SER_VER}  FOOTER_MARK_H={M.FOOTER_MARK_H}"
      f"  EGG_CLICKS={M.EGG_CLICKS}")
ck(M.APP_VER == "1.3.0", "版本号 1.3.0")
ck(M.SER_VER == "1.3.ser", "SER 目标版本 1.3.ser")
ck(M.FOOTER_MARK_H == 16, "底栏标记主字高 16")
ck(M.EGG_CLICKS == 10, "连点达标线 10 次")
ck(M.SER_CODE == "cher2001", "访问码 cher2001")

# ----------------------------------------------------------------
hdr("T2 标记宽度:16px 光点不再被裁(1.2.4 首发的遮挡修复)")
total = M.studio_mark_metrics(16)[2]
wid = M.studio_mark_widget_width(16)
mk = M.StudioMark(16, 150)
ck(mk.width() == wid, f"控件宽 == studio_mark_widget_width(16) = {wid}")
ck(wid > int(total) + 12, f"新宽度({wid}) > 旧规则字宽+12({int(total) + 12})")
fs = 16 * M.STUDIO_SUB_RATIO
r = max(0.85, fs * (0.105 if fs >= 14.0 else 0.30))
off = r * 1.75 + fs * 0.055
ck((wid - total) / 2.0 >= off + r,
   f"右侧余量 {(wid - total) / 2.0:.1f}px >= 光点伸出量 {off + r:.1f}px")
ck(M.studio_mark_widget_width(12) >= int(M.studio_mark_metrics(12)[2]) + 12,
   "12px 档宽度也不小于旧规则(不倒退)")

# ----------------------------------------------------------------
hdr("T3 连点计数:达标触发 / 未达标不触发 / 超时清零")
fired = []
mk = M.StudioMark(M.FOOTER_MARK_H, 150, egg_reset_ms=260)
mk.egg_activated.connect(lambda: fired.append(1))
for _ in range(M.EGG_CLICKS - 1):
    mk._bump()
ck(not fired and mk.remaining_clicks() == 1,
   f"{M.EGG_CLICKS - 1} 次不触发,剩余 1")
mk._bump()
ck(bool(fired) and mk.remaining_clicks() == M.EGG_CLICKS,
   "第 10 次触发 egg_activated 且计数清零")
fired.clear()
pump(0.40)                       # 超过 260ms 重置窗口
mk._bump(); mk._bump()
ck(not fired and mk.remaining_clicks() == M.EGG_CLICKS - 2,
   "停顿超过重置窗口后计数已清零(防日常误触积累)")

# ----------------------------------------------------------------
hdr("T4 访问码校验(忽略首尾空白与大小写)")
ck(M.check_ser_code("cher2001"), "cher2001 通过")
ck(M.check_ser_code("  CHER2001 "), "空白 + 大小写容错通过")
for t in ("cher2002", "", " ", None, "cher20010", "Cher2001x"):
    ck(not M.check_ser_code(t), f"非法输入 {t!r} 拒绝")

# ----------------------------------------------------------------
hdr("T5 更新控制台 TermWindow")
term = M.TermWindow()
ck(term.windowTitle() == "CHStudios 更新控制台", "窗口标题为更新控制台")
term.show(); pump(0.2)
ck(term.prompt_lbl.text().startswith("C:\\CHStudios"), "提示符为 C:\\CHStudios>")
ck(term._log_lay.count() >= 7, "打开即打印 banner(标题/版权/版本/提示)")
term.input.setText("wrong"); term._submit(); pump(0.1)
ck(term._busy is False, "错误码:不进入更新流程")
ck(term._log_lay.count() >= 9, "错误码:回显了输入 + 无效提示")
term.input.setText("cher2001"); term._submit(); pump(0.1)
ck(term._busy is True, "正确码:进入更新流程(busy)")
ck(term.input.isEnabled() is False, "更新中:输入框禁用")
term.close(); pump(0.2)

# ----------------------------------------------------------------
hdr("T6 端到端:连点 10 次 → 控制台 → cher2001 → 切 1.3.ser")
w = M.App(); w.show(); w._glow_timer.stop()
ck(not w._ser and w._disp_ver == M.APP_VER,
   f"初始为 {M.APP_VER},未启用 SER 通道")
# 底栏导航现在由 apps\ 里的功能模块声明生成;仍然不许有后台页
ck("admin" not in w.nav_tabs and list(w.nav_tabs) ==
   ["home", "clicker", "keys", "remap", "appearance", "settings", "update"],
   "底栏只有七个导航,无后台")
for _ in range(M.EGG_CLICKS):
    w.studio_mark._bump()
ck(getattr(w, "_term", None) is not None, "连点 10 次 → 弹出更新控制台")
w._term.input.setText("cher2001")
w._term._submit()
done = pump_until(lambda: w._ser, 15.0)
ck(done, "更新过程走完,App 切到 SER 通道")
ck(w._disp_ver == M.SER_VER, "_disp_ver 变为 1.3.ser")
ck(w.ver_label.text() == "v1.3.ser", "底栏版本标签 → v1.3.ser")
ck(w._home_ver_lbl.text() == "1.3.ser", "主页大版本号 → 1.3.ser")
ck(w._about_ver_lbl.text() == "1.3.ser", "设置页版本 → 1.3.ser")
ck(not w.windowIcon().isNull(), "窗口/任务栏图标已换成纯黑底 app_ser.ico")
_st.sync()
ck(str(_st.value("ser_updated")) == "true", "更新状态已写入注册表")
w._term.close(); w.close(); pump(0.3)

# ----------------------------------------------------------------
hdr("T7 重启持久化:重建 App 后仍是 1.3.ser")
w2 = M.App(); w2._glow_timer.stop()
ck(w2._ser is True and w2._disp_ver == "1.3.ser", "启动读到持久化,直接进 SER")
ck(w2.ver_label.text() == "v1.3.ser", "重启后底栏版本仍是 v1.3.ser")
ck(not w2.windowIcon().isNull(), "重启后图标仍是纯黑底变体")
w2.close()

# ----------------------------------------------------------------
hdr("T8 已更新状态下再开控制台:提示无可用更新")
w3 = M.App(); w3._glow_timer.stop()
w3._open_terminal(); pump(0.3)
t3 = w3._term
ck(t3.input.isEnabled() is False, "已是 1.3.ser → 输入框收起")
ck(t3.prompt_lbl.isVisible() is False, "已是 1.3.ser → 提示符隐藏")
t3.close(); w3.close()

# ----------------------------------------------------------------
hdr("T9 本体文件图标改写 patch_exe_icon(onefile 副本,不动原 exe)")
from _paths import exe_path as _exe_path        # 1.2.7 起产物是 onedir 目录

EXE = _exe_path()
ICO = os.path.join(SRC, "icon", "app_ser.ico")
if os.path.exists(EXE):
    import ctypes
    import shutil
    from ctypes import wintypes
    PROBE = os.path.join(HERE, "_egg_patch_probe.exe")
    for p in (PROBE, PROBE + ".old", PROBE + ".ser_new"):
        if os.path.exists(p):
            os.remove(p)
    shutil.copy2(EXE, PROBE)

    icons_before, groups_before = M._enum_icon_names(PROBE)
    ck(len(icons_before) == 7 and bool(groups_before),
       f"改写前 exe 已含 7 帧图标,资源组名 {groups_before}")
    n = M.patch_exe_icon(PROBE, ICO)
    ck(n == 7, f"patch_exe_icon 写入 {n} 帧(应为 7)")

    # 字节比对:改写后 RT_ICON#1 == app_ser.ico 第一帧
    with open(ICO, "rb") as f:
        _e, frames = M._parse_ico(f.read())
    k32 = ctypes.WinDLL("kernel32")
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE,
                                   wintypes.DWORD]
    k32.FindResourceW.restype = wintypes.HRSRC
    k32.FindResourceW.argtypes = [wintypes.HMODULE, ctypes.c_void_p,
                                  ctypes.c_void_p]
    k32.SizeofResource.restype = wintypes.DWORD
    k32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    k32.LoadResource.restype = wintypes.HGLOBAL
    k32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    k32.LockResource.restype = ctypes.c_void_p
    k32.LockResource.argtypes = [wintypes.HGLOBAL]
    k32.FreeLibrary.argtypes = [wintypes.HMODULE]
    hmod = k32.LoadLibraryExW(PROBE, None, M._LOAD_LIBRARY_AS_DATAFILE)
    hres = k32.FindResourceW(hmod, ctypes.c_void_p(1),
                             ctypes.c_void_p(M._RT_ICON))
    sz = k32.SizeofResource(hmod, hres)
    ptr = k32.LockResource(k32.LoadResource(hmod, hres))
    buf = ctypes.create_string_buffer(sz)
    ctypes.memmove(buf, ctypes.c_void_p(ptr), sz)
    k32.FreeLibrary(hmod)
    ck(bytes(buf.raw[:sz]) == frames[0],
       "改写后 RT_ICON#1 字节与 app_ser.ico 第一帧一致")
    ck(len(M._enum_icon_names(PROBE)[0]) == 7, "改写后仍为 7 帧(旧图标已删)")
    ck(all(M._read_icon_resource(PROBE, i) == f
           for i, f in enumerate(frames, start=1)),
       "7 个 RT_ICON 资源逐帧与 app_ser.ico 一致")

    # ★ 附加归档必须完好 —— 曾漏测这一条,导致图标改写把 46MB 的
    #   onefile 本体截成 328KB,交付出去直接打不开。
    #   UpdateResource 只写回 PE 映像,尾部 CArchive 会被整块丢掉。
    _o = open(EXE, "rb").read()
    _n = open(PROBE, "rb").read()
    _ie = M._pe_image_end(_o)
    ck(len(_n) > len(_o) * 0.9,
       f"改写后体积未塌陷({len(_n):,} vs 原 {len(_o):,})")
    ck(b"MEI\x0c\x0b\x0a\x0b\x0e" in _n, "改写后 PyInstaller cookie 仍在")
    ck(_n[M._pe_image_end(_n):] == _o[_ie:],
       "附加归档字节完全一致(自解压载荷原样保留)")
    ck(M._exe_icon_is_ser(PROBE, ICO) and M._exe_icon_is_ser(EXE, ICO),
       "_exe_icon_is_ser 判断正确(改写后认得出 / 新包本体出厂即纯黑底 SER)")
    for p in (PROBE, PROBE + ".old", PROBE + ".ser_new"):
        try:
            os.remove(p)
        except OSError:
            pass
else:
    print("  [skip] 未找到 dist\\pivot.exe,跳过文件图标改写测试")

# ----------------------------------------------------------------
# 还原注册表(atexit 兜底,这里主动调一次便于即时验证)
hdr("清理")
restore_reg()
ck(_st.contains("ser_updated") == _HAD,
   f"注册表 ser_updated 已还原(原值: {_VAL!r})")

print()
print("=" * 68)
if bad:
    print(f"FAIL: {len(bad)} 项未过")
    for m in bad:
        print("  -", m)
    sys.exit(1)
print("ALL PASS — SER 更新通道彩蛋链路回归全部通过")
