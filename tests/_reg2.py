# -*- coding: utf-8 -*-
"""v1.2 回归:闪屏字标 / 六页 / 用户胶囊删除 / 状态搬移 / 热键自定义 / 壁纸自定义"""
import os, sys, threading, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# 本项目已按类别归档: 脚本在 测试\, 源码在 ..\源码\
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
sys.path.insert(0, SRC)
from PySide6.QtCore import QSettings, QSize, QPoint, QPointF
from PySide6.QtGui import QFont, QPainterPath
from PySide6.QtWidgets import QApplication
import pivot as M

bad = []
QSettings("Pivot", "Pivot").clear()
app = QApplication(sys.argv)
app.setFont(QFont(M._pick_font(), 9)); app.setStyleSheet(M.QSS)
w = M.App(); w.show(); w._glow_timer.stop()

def pump(sec):
    t0 = time.monotonic()
    while time.monotonic() - t0 < sec:
        app.processEvents(); time.sleep(0.008)

def hdr(t):
    print(); print("=" * 68); print(t); print("=" * 68)

hdr("T1 出品方标记(纯字母 wordmark,尺寸自适应)")
wa, wb, need = M.studio_mark_metrics(40)
print(f"  STUDIO_MAIN={M.STUDIO_MAIN!r} STUDIO_SUB={M.STUDIO_SUB!r} 名称={M.STUDIO_NAME!r}")
print(f"  h=40 时 主字={wa:.1f} 副字={wb:.1f} 需要宽={need:.1f}")
if M.STUDIO_NAME != "CHStudios": bad.append("出品方名称不对")
if need <= 0: bad.append("字标度量异常")
if not (0 < wa < need and 0 < wb < need): bad.append("字标分段宽度异常")
if hasattr(M, "_studio_mark_path"): bad.append("旧的 C 印矢量函数还在(应已改为纯字母)")
print(f"  已无图形印记绘制函数 = {not hasattr(M, '_studio_mark_path')}")
mk = M.StudioMark(12, 140)
print(f"  底栏标记控件 {mk.width()}x{mk.height()}")
if mk.width() < need * 12 / 40: bad.append("字标控件宽度不足")
if hasattr(M, "SplashOverlay") and hasattr(M.SplashOverlay, "_draw_logo"):
    bad.append("旧的波纹 logo 绘制函数还在")
print(f"  SplashOverlay._draw_logo 已移除 = {not hasattr(M.SplashOverlay, '_draw_logo')}")

hdr("T2 用户胶囊已删除 / 底栏结构")
print(f"  UserChip 类存在={hasattr(M, 'UserChip')} 期望 False")
print(f"  AvatarBadge 类存在={hasattr(M, 'AvatarBadge')} 期望 False")
if hasattr(M, "UserChip") or hasattr(M, "AvatarBadge"):
    bad.append("用户胶囊类未删除")
print(f"  底栏有出品方标记={hasattr(w, 'studio_mark')}")
if not hasattr(w, "studio_mark"): bad.append("底栏缺少出品方标记")

hdr("T3 状态指示已从标题栏移到连点器页")
bar = w.status_label.parent()
in_console = False
p = w.status_label.parent()
while p is not None:
    if p is w.page_clicker:
        in_console = True; break
    p = p.parent()
print(f"  状态标签在连点器页内 = {in_console}")
if not in_console: bad.append("状态指示没搬进连点器页")
print(f"  状态标签初始文字 = {w.status_label.text()!r}")

hdr("T4 七个页面 + 底栏导航")
_NAV = ["home", "clicker", "keys", "remap", "appearance", "settings", "update"]
print(f"  stack={w.stack.count()}  导航={list(w.nav_tabs)}")
if w.stack.count() != len(_NAV) or list(w.nav_tabs) != _NAV:
    bad.append("页面/导航数量不对")
for k in _NAV:
    w.go(k); pump(0.25)
    cur = w.stack.currentWidget() is getattr(w, f"page_{k}")
    sel = w.nav_tabs[k].property("sel") == "true"
    print(f"  go({k:<11}) 页面正确={cur} 选中={sel}")
    if not cur or not sel: bad.append(f"切到 {k} 异常")
w.go("home"); pump(0.2)

hdr("T5 热键可自定义")
print(f"  初始: start={w._hk_start} stop={w._hk_stop} "
      f"按钮={[b.text() for b in w.hotkey_btns.values()]}")
if (w._hk_start, w._hk_stop) != ("f6", "f7"): bad.append("默认热键不对")
w._on_hotkey_changed("start", "f8")
pump(0.2)
print(f"  改成 F8 -> start={w._hk_start} 按钮={w.hotkey_btns['start'].text()} "
      f"设置={w._settings.value('hotkey_start')}")
if w._hk_start != "f8" or w._settings.value("hotkey_start") != "f8":
    bad.append("改绑未生效/未持久化")
w._on_hotkey_changed("stop", "f8")      # 与 start 撞车 -> 应互换
pump(0.2)
print(f"  停止键也设成 F8 -> 互换后 start={w._hk_start} stop={w._hk_stop}")
if (w._hk_start, w._hk_stop) != ("f7", "f8"):
    bad.append(f"撞车未互换: {w._hk_start}/{w._hk_stop}")
print(f"  按键名格式化: fmt('ctrl+shift+a')={M.fmt_hotkey('ctrl+shift+a')!r}")
if M.fmt_hotkey("ctrl+shift+a") != "Ctrl+Shift+A":
    bad.append("热键显示格式化不对")

hdr("T6 热键跨线程链路(修掉的老 bug)")
calls = {"start": 0, "stop": 0}
w.on_start = lambda: calls.__setitem__("start", calls["start"] + 1)
w.on_stop = lambda: calls.__setitem__("stop", calls["stop"] + 1)
t = threading.Thread(target=lambda: w.sig_hotkey.emit("start"))
t.start(); t.join()
pump(0.4)
t2 = threading.Thread(target=lambda: w.sig_hotkey.emit("stop"))
t2.start(); t2.join()
pump(0.4)
print(f"  从普通线程 emit 信号 -> start={calls['start']} stop={calls['stop']}")
if calls["start"] != 1 or calls["stop"] != 1:
    bad.append("跨线程热键信号没触发(QTimer.singleShot 式失效)")

del w.on_start, w.on_stop     # 还原 T6 的打桩,否则后面测的是桩
hdr("T7 左上角紧急中止开关")
print(f"  初始 FAILSAFE={M.pyautogui.FAILSAFE} 开关={w.failsafe_sw.isChecked()}")
if not M.pyautogui.FAILSAFE or not w.failsafe_sw.isChecked():
    bad.append("初始状态不对")
w.failsafe_sw.setChecked(False, animate=False); pump(0.3)
print(f"  关掉后 FAILSAFE={M.pyautogui.FAILSAFE} 设置={w._settings.value('failsafe')}")
if M.pyautogui.FAILSAFE: bad.append("关闭开关未生效")
w.failsafe_sw.setChecked(True, animate=False); pump(0.3)
if not M.pyautogui.FAILSAFE: bad.append("重新开启未生效")

hdr("T8 壁纸自定义")
print(f"  内置壁纸常量={M.BUILTIN_WALLPAPER!r}  当前={w._root.bg_path!r}")
print(f"  缩略图项={list(w.wp_tiles)}")
if M.BUILTIN_WALLPAPER not in w.wp_tiles: bad.append("内置壁纸没出现在壁纸库")
w._on_alpha(30); w._on_blur(4); pump(0.2)
print(f"  调暗化=30 -> bg_alpha={w._root.bg_alpha} 存={w._settings.value('bg_alpha')}")
print(f"  调柔化=4  -> bg_blur={w._root.bg_blur} 存={w._settings.value('bg_blur')}")
if w._root.bg_alpha != 76 or w._root.bg_blur != 4:
    bad.append(f"滑块换算不对: {w._root.bg_alpha}/{w._root.bg_blur}")
if str(w._settings.value("bg_blur")) != "4":
    bad.append("柔化值未持久化")
dst = M.import_wallpaper(M._res_path(M.BUILTIN_WALLPAPER))
print(f"  导入壁纸 -> {os.path.basename(dst) if dst else None}")
if not dst or not os.path.exists(dst): bad.append("导入壁纸失败")
w._reload_wallpaper_tiles()
w._apply_wallpaper(dst); pump(0.3)
print(f"  应用自定义壁纸后 bg_path 是用户目录={w._root.bg_path == dst} "
      f"缩略图数={len(w.wp_tiles)}")
if w._root.bg_path != dst or len(w.wp_tiles) < 2:
    bad.append("自定义壁纸未生效")
print(f"  预览图已加载={w.wp_preview._pm is not None} 设置={os.path.basename(str(w._settings.value('bg_path')))}")
if not w._settings.value("bg_path"): bad.append("壁纸路径未持久化")

hdr("T9 端到端连点器(自定义改回默认后)仍正常")
w._on_hotkey_changed("start", "f6"); w._on_hotkey_changed("stop", "f7")
M.pyautogui.FAILSAFE = True
clicks = {"n": 0}
M.pyautogui.click = lambda *a, **k: clicks.__setitem__("n", clicks["n"] + 1)
M.pyautogui.moveTo = lambda *a, **k: None
M.pyautogui.position = lambda: (10, 10)
w.interval_edit.setText("30"); w.count_edit.setText("10")
w.use_fixed.setChecked(False)
w.go("home"); pump(0.2)
w.sig_hotkey.emit("start")          # 模拟热键
pump(5.0)
print(f"  点击={clicks['n']} UI计数={w.counter._value} 状态={w.status_label.text()!r} "
      f"页面={w._page} 徽标={w.tool_cards['clicker'].badge.text()!r}")
if clicks["n"] != 10: bad.append(f"点击次数不对 {clicks['n']}")
if w.counter._value != 10: bad.append("计数不对")
if w._page != "clicker": bad.append("热键启动未翻页")
if not w.start_btn.isEnabled(): bad.append("完成后按钮未复位")

hdr("T10 设置持久化:新实例读回")
w.close(); pump(0.4)
w2 = M.App()
print(f"  热键={w2._hk_start}/{w2._hk_stop}  FAILSAFE={M.pyautogui.FAILSAFE}")
print(f"  壁纸={os.path.basename(str(w2._root.bg_path))} alpha={w2._root.bg_alpha} blur={w2._root.bg_blur}")
if (w2._hk_start, w2._hk_stop) != ("f6", "f7"): bad.append("热键没读回")
if w2._root.bg_alpha != 76 or w2._root.bg_blur != 4: bad.append("观感设置没读回")
w2.close(); pump(0.3)
QSettings("Pivot", "Pivot").clear()

hdr("T11 启动流程:纯黑场 → 字标 → 壁纸淡出")
print(f"  SPLASH_MS={M.SPLASH_MS}  play() 默认时长与常量一致="
      f"{M.SplashOverlay.play.__defaults__[0] == M.SPLASH_MS}")
if M.SPLASH_MS < 2200:
    bad.append(f"闪屏时长没放慢: {M.SPLASH_MS}ms")
if M.SplashOverlay.play.__defaults__[0] != M.SPLASH_MS:
    bad.append("play() 默认时长与 SPLASH_MS 不一致")
print(f"  SplashOverlay.fading 信号存在={hasattr(M.SplashOverlay, 'fading')}")
if not hasattr(M.SplashOverlay, "fading"):
    bad.append("闪屏缺少 fading 信号(壁纸淡出的时机钩子)")

w3 = M.App()                       # 新实例:启动即黑场
print(f"  构造后 reveal={w3._root.get_reveal():.2f} (期望 0.00 = 纯黑)")
if w3._root.get_reveal() != 0.0:
    bad.append("启动时不是纯黑场")
w3._reveal_wallpaper()             # 触发壁纸淡出
pump(1.2)
print(f"  淡出后 reveal={w3._root.get_reveal():.2f} (期望 1.00)")
if w3._root.get_reveal() < 0.999:
    bad.append("壁纸没淡出来(黑场卡住)")
w3.close(); pump(0.3)

# 像素级校验必须用【独立的】AuroraRoot 抓图:
# 在 App 里 grab() 会把子控件(整页内容)一起渲染进来,黑底上盖着玻璃面板,
# 采到的根本不是底色像素(第一版就是这么误报的)。
os.chdir(SRC)                      # 内置壁纸是相对路径,得站在源码目录才解得出
solo = M.AuroraRoot()
solo.set_blackout(True)
solo.resize(300, 200)
c = solo.grab().toImage().pixelColor(150, 100)
print(f"  独立黑场中心像素 = ({c.red()},{c.green()},{c.blue()}) (期望 0,0,0)")
if (c.red(), c.green(), c.blue()) != (0, 0, 0):
    bad.append(f"黑场没画成纯黑: {c.red()},{c.green()},{c.blue()}")
solo.set_reveal(1.0)
c2 = solo.grab().toImage().pixelColor(150, 100)
print(f"  恢复后中心像素 = ({c2.red()},{c2.green()},{c2.blue()}) (不再被黑场压住)")
if (c2.red(), c2.green(), c2.blue()) == (0, 0, 0):
    bad.append("黑场撤销后底色仍是纯黑")
solo.deleteLater()

hdr("T12 图标与安装向导素材")
ico_app = os.path.join(SRC, "icon", "app.ico")
ico_box = os.path.join(SRC, "icon", "box.ico")
same = (os.path.getsize(ico_app) == os.path.getsize(ico_box)
        and open(ico_app, "rb").read() == open(ico_box, "rb").read())
print(f"  主图标 = 敞开盒子(与 box.ico 一致)={same}")
if not same: bad.append("主图标没换成盒子")
for name in ("wizard_image.bmp", "wizard_image_2x.bmp"):
    path = os.path.join(SRC, "assets", name)
    with open(path, "rb") as f:
        head = f.read(30)
    bits = int.from_bytes(head[28:30], "little") if head[:2] == b"BM" else 0
    print(f"  {name}: {os.path.getsize(path)} bytes  位深={bits} (Inno 只认 24)")
    if bits != 24:
        bad.append(f"{name} 不是 24-bit BMP(Inno 会静默忽略)")

hdr("T13 末尾那点光:位置 / 尺寸 / 收尾「亮一下」")
# 几何:点要**挪出**字母角外(与笔画留空隙),而不是骑在笔画上。
# 注意 _studio_spark_geom 返回的 x 含墨迹右缘(x_sub=0 时即 right),要减掉。
rs = []
for hh in (12.0, 54.0):
    fs = hh * M.STUDIO_SUB_RATIO
    whole = QPainterPath()
    whole.addText(QPointF(0.0, 0.0), M._studio_font(fs, "sub"), M.STUDIO_SUB)
    right = float(whole.boundingRect().right())
    sx, _, r = M._studio_spark_geom(0.0, 0.0, fs)
    gap = sx - right - r                                # 点左缘到笔画的距离
    rs.append(r)
    print(f"  基准高{hh:>4.0f}px → 副字{fs:5.2f}px  半径 {r:.2f}px  "
          f"圆心外移 {sx - right:.2f}px  与笔画空隙 {gap:.2f}px")
    if gap <= 0.4:
        bad.append(f"{hh}px 档光点贴着笔画(空隙 {gap:.2f}px)")
if rs[1] <= rs[0]:
    bad.append("光点没随字号放大")

# 收尾脉冲:中段=常态、峰值、之后收回
for t, lo, hi, what in ((0.50, 0.999, 1.001, "未开始"),
                        (0.78, 1.60, 1.80, "峰值"),
                        (0.95, 0.999, 1.001, "已收回")):
    sc, gn = M.splash_spark_pulse(t)
    print(f"  t={t:.2f} ({what}) 半径 ×{sc:.3f}  强度 ×{gn:.3f}")
    if not (lo <= sc <= hi):
        bad.append(f"t={t} 的脉冲倍数 {sc:.3f} 不在 {lo}~{hi}")
if M.splash_spark_pulse(0.78)[0] <= M.splash_spark_pulse(0.70)[0]:
    bad.append("脉冲曲线在峰值前没有上升")

print(); print("=" * 68)
print(f"失败 {len(bad)} 项: {bad}" if bad else "全部通过 ✓")
print("=" * 68)
