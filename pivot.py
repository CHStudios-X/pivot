# -*- coding: utf-8 -*-
r"""
枢 Pivot —— 外壳（Liquid Glass / iOS 26 风格）

  源码\pivot.py         外壳：窗口骨架、闪屏、标题栏、底栏、热键、SER 通道，
                        以及**功能模块的容错装载**
  源码\pivot_kit.py   公共件：玻璃面板/按钮/开关/分段控件/键盘控件/主题常量
  源码\apps\            放功能：一个文件一个功能页

★ 关于命名：1.3.0 起软件改名为「枢 / Pivot」（原「工具盒子 / ToolBox」）。
  改的只是对外的名字与安装/更新链路，图标与界面设计一概没动。老版本的
  配置在启动时会自动搬到新键下（见 _migrate_legacy_settings）。

★ 关于 apps\：每个 .py 就是一个功能（连点器 / 键盘连按 / 按键改绑 / 外观 /
  设置 / 主页）。**删掉其中任意几个，本程序照常启动** —— 被删的功能只是从
  底栏、主页卡片和热键分派里消失，其余一切照旧；连整个 apps\ 删掉也只是
  变成"什么功能都没有的空壳"，不会崩。所以想精简功能，直接删文件就行。

  装载顺序：exe 同级的 apps\（便于用户裁剪）优先，内置的那一份兜底，
  所以只拷一个 exe 出去也能跑。

视觉要素（Windows 上可复刻的部分）:
- Aurora 背景:缓慢漂移的彩色光斑,给玻璃提供可透出的内容
- 液态玻璃面板:自绘 —— 上亮下暗的玻璃体 + 镜面高光描边 + 底部反光
- 光标光泽:柔和径向高光跟随鼠标,玻璃"活"起来
- 全胶囊造型:按钮 / 分段控件 / 开关一律圆角拉满
- 系统级 Acrylic 打底,与自绘玻璃叠加
"""

import ctypes
import json
import math
import os
import sys
import threading
import time
from ctypes import wintypes

import pyautogui
import keyboard  # 全局热键

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, Signal,
    QPointF, QPoint, QRectF, QRect, QSize, QSettings, QVariantAnimation,
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient,
    QFontDatabase, QFontMetricsF, QPainterPath, QCursor, QIcon, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QProgressBar,
    QGraphicsOpacityEffect, QStackedWidget, QSlider, QScrollArea,
    QFileDialog, QDialog,
)

from pivot_kit import (  # noqa: F401  (一批名字只为兼容旧引用与测试脚本)
    APP_NAME, APP_NAME_EN, APP_VER, SER_VER, STUDIO_NAME, QSS,
    C_ACCENT_1, C_ACCENT_2, C_TEXT, C_TEXT_DIM, C_TEXT_FAINT,
    BUILTIN_WALLPAPER, _resolve_bg,
    GlassPanel, RiseFade, PillButton, PulseDot, SegmentedControl,
    ToggleSwitch, AnimatedCounter, CountdownOverlay, ToolIcon, ToolCard,
    NavTab, HotkeyButton,
    fmt_hotkey, fmt_key_name, qt_key_to_name, _pick_font, _res_path,
    _clamp01, _ease_out_cubic, _ease_out_back,
)

import updater_core          # 更新内核：与本文件同级，属于基础设施，不可删

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0


# ============================================================================
# 用户设置 & 旧版搬家（1.3.0 改名：工具盒子 → 枢 / Pivot）
#
# 改名最容易被忽略的坑就是 QSettings 的「组织名 / 应用名」跟着变 —— 不处理
# 的话老用户的热键、窗口位置、壁纸、连点参数会全部"突然回到默认"，看起来
# 像掉档。搬家只在新键**完全为空**时做一次，旧键原样保留（万一要跑回
# 1.2.x，那边还能读到自己那份）。
# ============================================================================

ORG_NAME = "Pivot"
LEGACY_ORG = "MouseMacro"


def settings_store():
    """本项目唯一的 QSettings 入口 —— 别的文件要用设置，也走这里。"""
    return QSettings(ORG_NAME, ORG_NAME)


def _migrate_legacy_settings():
    """把 1.2.x 的 MouseMacro 设置抄到 Pivot 下；返回搬过去的项数。"""
    try:
        old = QSettings(LEGACY_ORG, LEGACY_ORG)
        new = settings_store()
        if new.allKeys():                 # 新键已有内容：用户自己调过，不覆盖
            return 0
        keys = old.allKeys()
        for k in keys:
            new.setValue(k, old.value(k))
        if keys:
            new.sync()
        return len(keys)
    except Exception:                     # noqa: BLE001
        return 0


def _migrate_wallpaper_dir():
    """壁纸目录 ...\\MouseMacro\\wallpapers → ...\\Pivot\\wallpapers。

    新目录不存在时整份复制过去；旧目录不删 —— 设置里存的 bg_path 可能
    还是旧目录的绝对路径，两边都留着最省事，也不去动用户的原文件。
    """
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return False
    old = os.path.join(base, LEGACY_ORG, "wallpapers")
    new = os.path.join(base, ORG_NAME, "wallpapers")
    if not os.path.isdir(old) or os.path.exists(new):
        return False
    try:
        import shutil
        shutil.copytree(old, new)
        return True
    except OSError:
        return False



# ============================================================================
# 功能模块装载（容错）
#
# 三条硬性要求，所以这里写得啰嗦但不肯省：
#   1. 找不到文件  -> 静默跳过（这是用户"删功能"的正常操作，不该报警）
#   2. 导入就炸了  -> 记下来，跳过（语法错、少依赖、第三方库缺失都算）
#   3. 契约不对    -> 记下来，跳过（没有 META / 没有 Feature / id 重复）
# 任何一种情况都不能让外壳起不来。
# ============================================================================


def _apps_dirs():
    """apps 目录的搜索顺序

    1) 环境变量 PIVOT_APPS_DIR 指定的目录（测试与"功能目录放别处"用）；
       旧名 TOOLBOX_APPS_DIR 仍然认，免得老的测试脚本与批处理失效；
    2) 打包成 exe 后，**exe 同级**的 apps\\ —— 用户直接删里面的文件就能
       裁掉功能（绿色版 / 安装版都是这个玩法）；
    3) 内置的那一份（源码目录 / PyInstaller 解包目录）兜底，
       所以只拷一个 exe 出去也能正常跑。
    """
    dirs = []
    override = (os.environ.get("PIVOT_APPS_DIR")
                or os.environ.get("TOOLBOX_APPS_DIR"))
    if override:
        dirs.append(override)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), "apps"))
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    dirs.append(os.path.join(base, "apps"))
    return dirs


def _load_one(path):
    """按文件路径装载一个功能模块；返回 (模块, 原因)，原因非空表示失败"""
    import importlib.util
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem.startswith("_"):
        return None, ""                    # 下划线开头 = 不是功能模块
    mod_name = f"_pivot_apps.{stem}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return None, "无法解析"
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    except Exception as e:                 # noqa: BLE001
        sys.modules.pop(mod_name, None)
        return None, f"{type(e).__name__}: {e}"

    meta = getattr(mod, "META", None)
    feat = getattr(mod, "Feature", None)
    if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
        return None, "缺少合法的 META（至少要 id）"
    if not isinstance(feat, type):
        return None, "缺少 Feature 类"
    for k, v in (("order", 999), ("nav", None), ("card", False),
                 ("ready", True), ("builder", None), ("state", None),
                 ("hotkeys", {}), ("desc", ""),
                 ("icon", "more"), ("accent", "#8a93a8")):
        meta.setdefault(k, v)
    meta["module"] = stem
    return mod, ""


def load_features():
    """装载全部功能模块，返回 (功能列表, 错误列表)

    错误只记录不抛 —— 出错的那个功能消失，其它的照常。
    目录选择规则：**第一个"存在"的 apps 目录说了算**，哪怕它一个功能都没有。
    这样"删光 apps\\ 里的文件"就等于"把功能全删掉"，不会被内置那份偷偷补回来
    （目录本身不存在才回退到下一层，那是"只拷了一个 exe 出去"的场景）。
    """
    feats, errors = [], []
    for d in _apps_dirs():
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            mod, err = _load_one(os.path.join(d, fn))
            if err:
                errors.append((fn, err))
            elif mod is not None:
                feats.append(mod)
        break                          # 目录存在就用它，空也算

    feats.sort(key=lambda m: m.META["order"])
    seen, uniq = set(), []
    for m in feats:
        fid = m.META["id"]
        if fid in seen:
            errors.append((m.META["module"], f"id 重复: {fid}（已跳过）"))
            continue
        seen.add(fid)
        uniq.append(m)
    return uniq, errors


FEATURES, LOAD_ERRORS = load_features()
FEATURE_BY_ID = {m.META["id"]: m for m in FEATURES}
_FEATURE_BASES = tuple(m.Feature for m in FEATURES)
# 主页卡片：功能自己在 META 里声明 card=True
TOOLS = [dict(m.META) for m in FEATURES if m.META["card"]]
# 「当前页 -> F6/F7 该驱动谁」
_PAGE_HOTKEYS = {m.META["id"]: m.META["hotkeys"] for m in FEATURES}

# --- 兼容再导出：这些名字以前就住在本文件里，测试脚本还在按老路径取 ---
if "keys" in FEATURE_BY_ID:                # noqa: SIM102
    _k = FEATURE_BY_ID["keys"]
    KeyRepeater = _k.KeyRepeater
    VirtualKeyboard = _k.VirtualKeyboard
    KB_LAYOUT = _k.KB_LAYOUT
if "appearance" in FEATURE_BY_ID:
    import_wallpaper = FEATURE_BY_ID["appearance"].import_wallpaper


def report_load_errors():
    """把装载失败的功能打到 stderr（用户看不到，但排查时是唯一线索）"""
    for fn, err in LOAD_ERRORS:
        print(f"[apps] 跳过 {fn}: {err}", file=sys.stderr)


# ============================================================================
# Win32 背景材质:Mica (Win11) / Acrylic (Win10)
# ============================================================================

class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WCAD(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


# --- WM_NCHITTEST:让系统直接接管无边框窗口的边缘缩放 ---
# 走系统命中测试而不是 Qt 的 startSystemResize,是因为前者会自带
# 正确的缩放光标(↔ ↕ ⤡),后者只能"盲拖"。
WM_NCHITTEST = 0x0084
_HT = {
    "left": 10, "right": 11, "top": 12, "topleft": 13,
    "topright": 14, "bottom": 15, "bottomleft": 16, "bottomright": 17,
}


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


def _apply_mica(hwnd: int, dark: bool = True) -> bool:
    try:
        dwm = ctypes.WinDLL("dwmapi")
        v = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
        try:
            v = ctypes.c_int(2)
            dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(v), 4)
        except Exception:
            v = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 1029, ctypes.byref(v), 4)
        v = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(v), 4)
        return True
    except Exception:
        return False


def _apply_acrylic(hwnd: int, rgba=(20, 20, 26, 200), dark: bool = True) -> bool:
    try:
        r, g, b, a = rgba
        policy = _ACCENT_POLICY()
        policy.AccentState = 4
        policy.AccentFlags = 2
        policy.GradientColor = (a << 24) | (b << 16) | (g << 8) | r
        data = _WCAD()
        data.Attribute = 19
        data.Data = ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(policy)
        fn = ctypes.WinDLL("user32").SetWindowCompositionAttribute
        fn.argtypes = [wintypes.HWND, ctypes.POINTER(_WCAD)]
        fn.restype = ctypes.c_bool
        ok = fn(hwnd, ctypes.byref(data))
        if dark:
            v = ctypes.c_int(1)
            ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(v), 4)
        return bool(ok)
    except Exception:
        return False


def apply_backdrop(hwnd: int, dark: bool = True) -> str:
    build = 0
    try:
        build = sys.getwindowsversion().build
    except Exception:
        pass
    if build >= 22000 and _apply_mica(hwnd, dark):
        return "mica"
    if build >= 17763 and _apply_acrylic(hwnd, dark=dark):
        return "acrylic"
    return "none"

# 启动闪屏总时长(ms)。用户几次反馈"动画太快",逐轮放慢:
# 1250(初版) → 1550 → 2400(当前,配合纯黑底,节奏更从容)
SPLASH_MS = 2400

# 出品方标记:纯字母 wordmark —— 两段用【两种字体】,同基线,无任何图形符号。
# 层次靠三件事叠出来,而不是把字距拉大:
#   · 字体对比:Bahnschrift 半窄黑(工业、收紧) vs Segoe UI 细体(人文、舒展)
#   · 字重对比:DemiBold vs Light
#   · 字号对比:1.00 vs 0.66 —— 两段互相咬合成一个整体
# 结构上刻意避开「两段文字夹一个符号」那类排布(那是 CORONA ) STUDIO 的骨架)。
# 选型经过 12px 底栏实拍档 ×8 放大比对(见 测试\_logo_zoom.py),小字仍要读得清。
STUDIO_MAIN = "CH"        # 主字:半窄黑体
STUDIO_SUB = "Studios"    # 副字:细体 + 轻微展开

STUDIO_SUB_RATIO = 0.66   # 副字高 = 主字高 × 此值
STUDIO_GAP = 0.30         # 两段之间的间距(相对主字高)
STUDIO_TRACK_MAIN = -0.01 # 主字字距(负 = 收紧,让 CH 咬成一个整体)
STUDIO_TRACK_SUB = 0.11   # 副字字距(细体要稍微展开才不发虚)

# 字体族按可用性回退 —— 缺 Bahnschrift 的老系统退到 Segoe UI,字重再补回来
STUDIO_FAMS_MAIN = ("Bahnschrift SemiBold SemiCondensed", "Bahnschrift SemiBold",
                    "Bahnschrift", "Segoe UI")
STUDIO_FAMS_SUB = ("Segoe UI Semilight", "Segoe UI Light", "Segoe UI")
_STUDIO_FAM_CACHE = {}

# ---- SER 更新通道彩蛋(1.2.4) ------------------------------------------
# 底栏出品标记是入口:左键连点 EGG_CLICKS 次,弹出命令提示符风格的
# 「CHStudios 更新控制台」;在控制台输入 SER_CODE 回车,更新过程逐行
# 完整打印(含下载进度)。走完后本体切到 SER 通道,版本标识显示 1.2.ser。
# 图标自 1.2.4 起**主图标本身就是纯黑底**(icon/app.ico),所以窗口 /
# 任务栏 / 资源管理器里的文件图标天然一致;更新流程的图标步骤会拿
# app_ser.ico 做比对,一致即判定"已是 SER"并跳过 —— 不会改动本体文件。
# 更新状态写进注册表(ser_updated),重启后保留。功能与 1.2.4 完全一致。
FOOTER_MARK_H = 16        # 底栏标记主字高(1.2.3 为 12,用户要求加大)
EGG_CLICKS = 10           # 连点达标线
EGG_RESET_MS = 3500       # 点击窗口:停顿超过此时长清零,防日常误触积累
SER_CODE = "cher2001"     # 更新通道访问码(忽略大小写与首尾空白)


def _studio_pick_family(names):
    key = names[0]
    if key not in _STUDIO_FAM_CACHE:
        try:
            fam = set(QFontDatabase.families())
        except Exception:
            fam = set()
        got = next((n for n in names if n in fam), names[-1])
        _STUDIO_FAM_CACHE[key] = got
    return _STUDIO_FAM_CACHE[key]


def _studio_main_family():
    return _studio_pick_family(STUDIO_FAMS_MAIN)


def _studio_sub_family():
    return _studio_pick_family(STUDIO_FAMS_SUB)


def _studio_font(px, seg="main", family=None, weight=None, tracking=None):
    """seg: "main"(CH) / "sub"(Studios) —— 字体、字重、字距都按段默认"""
    if seg == "sub":
        fam = family or _studio_sub_family()
        w = QFont.Weight.Light if weight is None else weight
        tr = STUDIO_TRACK_SUB if tracking is None else tracking
    else:
        fam = family or _studio_main_family()
        w = QFont.Weight.DemiBold if weight is None else weight
        tr = STUDIO_TRACK_MAIN if tracking is None else tracking
    f = QFont(fam)
    f.setPixelSize(max(1, int(px)))
    f.setWeight(w)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px * tr)
    return f


def _wordmark_widths(height):
    """主字 / 副字两段的实测宽度 —— 字重、字号都不同,必须分别量。

    ★ 实测结论(见 测试\\_probe_track.py):`QFontMetricsF.horizontalAdvance`
    **已经计入 letterSpacing** —— 带字距与不带字距的差恰好 = 字符数 × 字号 × 字距
    (54px 档:advance("Studios") 136.34 vs 109.00,差 27.34 ≈ 7 × 35.64 × 0.11)。
    所以这里只取 advance 本身;再按字符数补一次字距就是**重复计算**,
    整块会凭空偏左约半个补偿量(54px 档 6.9px)。
    """
    h = max(1.0, float(height))
    fs = h * STUDIO_SUB_RATIO
    wa = float(QFontMetricsF(_studio_font(h, "main"))
               .horizontalAdvance(STUDIO_MAIN))
    wb = float(QFontMetricsF(_studio_font(fs, "sub"))
               .horizontalAdvance(STUDIO_SUB))
    return wa, wb


def studio_mark_metrics(height):
    """给定主字高,返回 (主字宽, 副字宽, 整体所需宽)"""
    wa, wb = _wordmark_widths(height)
    return wa, wb, wa + float(height) * STUDIO_GAP + wb


def studio_mark_widget_width(height):
    """标记控件需要的总宽:字宽 + 末尾光点向右伸出的量(两侧对称留白)。

    光点圆心在墨迹右缘外 off 处、半径 r —— 只按「字宽 + 12」定宽的话,
    12px 档 (off+r ≈ 7.0px) 勉强够,16px 档 (off+r ≈ 9.3px) 就会超过
    右侧 6px 余量,光点被窗口边缘裁掉一截(1.2.4 首发的遮挡问题)。
    这里按「光点最右缘 + 2px 呼吸」对称反推,任何字号都不会再裁。
    """
    total = studio_mark_metrics(height)[2]
    fs = height * STUDIO_SUB_RATIO
    r = max(0.85, fs * (0.105 if fs >= 14.0 else 0.30))
    off = r * 1.75 + fs * 0.055
    return int(total + 2 * (off + r + 2.0))


_SPARK_BOX_CACHE = {}


def _studio_spark_geom(x_sub, base, fs):
    """量出 Studios **末尾那个 s** 的墨迹框,给出「s 右上角那点光」的圆心与半径。

    为什么落在末尾的 s(而不是首字母 S):
      · 它在词尾,右边是空白 —— 光点可以真正骑在字母右上角的外侧,
        不必像首字母 S 那样为了避让后面的 t 而只能收在那道缝里
      · 它是小写(x-height),比首字母 S(cap 高)矮一大截。实测 54px 档:
        x-height 顶 = -17.9,cap 顶 = -24.9 —— 锚点要跟着落到低的那一档,
        否则光点会飘在词的上方空处,像一颗无关的星

    定位不靠 advance 累加猜起点:`QPainterPath.addText` 画整串时**已经**按
    真实排版推进(含 letterSpacing),所以整串的 `boundingRect().right()`
    就是末尾 s 的墨迹右缘。顶部则单独量那一个字符 ——
    整串的 top 是 cap 高(S / d / i 的顶),不是我们要的 x-height 顶。

    实测对照(见 测试\\_probe_tail_s.py,逐像素扫描 vs 上面的 path 量法):
      · 主字 54px → 右缘 130.0 vs 131.1、顶 -17.9 vs -17.9
      · 主字 12px → 副字仅 7.92px,字符块在扫描里已连成一片,只信 path 值
    """
    key = round(float(fs), 3)
    hit = _SPARK_BOX_CACHE.get(key)
    if hit is None:
        f = _studio_font(fs, "sub")
        whole = QPainterPath()
        whole.addText(QPointF(0.0, 0.0), f, STUDIO_SUB)
        last = QPainterPath()
        last.addText(QPointF(0.0, 0.0), f, STUDIO_SUB[-1])
        hit = (float(whole.boundingRect().right()),
               float(last.boundingRect().top()))
        _SPARK_BOX_CACHE[key] = hit
    right, top = hit
    # 半径跟着字号走。底栏(副字仅 7.92px)要反过来给宽一点 ——
    # 太小被抗锯齿一摊就找不到了。两档系数差得多,是因为抗锯齿的"吃掉量"
    # 在小尺寸里占比大得多。
    r = max(0.85, fs * (0.105 if fs >= 14.0 else 0.30))
    # 圆心沿右上 45° 挪出墨迹框 —— 要的是"浮在角外的一点光",
    # 不是"嵌在笔画里的一颗珠"。偏移量 = 半径 + 一段按字号走的可见空隙,
    # 这样点变大时它自己会跟着后退,永远不会压到末位 s 的笔画。
    off = r * 1.75 + fs * 0.055
    return (x_sub + right + off, base + top - off, r)


def draw_studio_mark(p, cx, cy, height, *, max_width=0,
                     letter_alpha=255, mark_alpha=255,
                     spread=1.0, mark_open=1.0, glow=False,
                     spark_alpha=None, spark_scale=1.0):
    """在 (cx, cy) 居中绘制纯字母出品标记「CH Studios」。

    height       主字 CH 的高度(px);副字按 STUDIO_SUB_RATIO 缩小,两段共用基线
    max_width    >0 时按可用宽度反推主字高,保证再窄的窗口也不溢出
    mark_alpha   主字 alpha
    letter_alpha 副字 alpha
    spread       两段间距的展开程度 0→1(入场动画:从贴合成一个词到分开)
    mark_open    历史参数(旧版"印记开口"动画),纯字母版不再使用
    glow         主字外面加一圈柔光
    spark_alpha  Studios 末尾那个 s 右上角的一点光;None = 跟随副字 alpha
    spark_scale  那点光的放大倍数(入场收尾时"亮一下"用)
    """
    if max_width > 0:
        need = studio_mark_metrics(height)[2]
        if need > max_width:
            height *= max_width / need

    wa, wb, _ = studio_mark_metrics(height)
    fs = height * STUDIO_SUB_RATIO
    gap = height * STUDIO_GAP * max(0.0, min(1.0, spread))
    # 按【实际】宽度居中 —— 否则展开动画过程中整块会往右飘
    x = cx - (wa + gap + wb) / 2.0
    base = cy + height * 0.355              # 两段共用基线

    # ---------------- 主字 CH ----------------
    if mark_alpha > 0:
        f_main = _studio_font(height, "main")
        if glow:
            path = QPainterPath()
            path.addText(QPointF(x, base), f_main, STUDIO_MAIN)
            lw0 = max(2.0, height * 0.20)
            p.save()
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(3):
                p.setPen(QPen(QColor(150, 200, 255, 30 - i * 9),
                              lw0 * (1.0 - i * 0.34)))
                p.drawPath(path)
            p.restore()
        p.setFont(f_main)
        p.setPen(QColor(255, 255, 255, mark_alpha))
        p.drawText(QPointF(x, base), STUDIO_MAIN)

    # ---------------- 副字 Studios ----------------
    if letter_alpha < 12:
        return
    p.setFont(_studio_font(fs, "sub"))
    # 比主字暗一档 —— 纯字母标记里,层次只能靠字重 + 明度双保险
    p.setPen(QColor(206, 220, 246, letter_alpha))
    p.drawText(QPointF(x + wa + gap, base), STUDIO_SUB)

    # ---------------- 末尾 s 右上角的一点光 ----------------
    # 全标记唯一的彩色元素,也是唯一的实体点缀。强度跟随副字 alpha,
    # 这样入场动画里它是随副字一起亮起来的,不需要另接一根时间轴。
    sa = letter_alpha if spark_alpha is None else spark_alpha
    if sa > 0:
        sx, sy, r = _studio_spark_geom(x + wa + gap, base, fs)
        r *= max(0.05, float(spark_scale))
        # 它是整个标记里最亮的一点,所以要**比副字更亮** ——
        # 直接跟副字 alpha 走的话,底栏(副字 151)那点会淡到看不见。
        # 超过 1 的强度留给入场收尾的"亮一下"(那时 spark_alpha > 255)。
        lit = max(0.0, min(1.85, sa / 255.0 * 1.6))
        p.setPen(Qt.PenStyle.NoPen)
        # 柔光晕只在闪屏那一档画:底栏副字才 7px,光晕铺开就是一团糊,
        # 反而把末位 s 整个罩住(实测见 截图\_spark_12px.png)。
        if fs >= 14.0:
            # 光占大头、实心核只占一点 —— 要的是"晕",不是"珠"
            hr = min(r * 4.2, fs * 0.42 * max(1.0, float(spark_scale)))
            g = QRadialGradient(QPointF(sx, sy), hr)
            g.setColorAt(0.0, QColor(128, 180, 255, int(min(255, 132 * lit))))
            g.setColorAt(0.35, QColor(128, 180, 255, int(min(255, 44 * lit))))
            g.setColorAt(1.0, QColor(128, 180, 255, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(sx, sy), hr, hr)
        p.setBrush(QColor(186, 219, 255, int(min(255, 242 * lit))))
        p.drawEllipse(QPointF(sx, sy), r, r)


class StudioMark(QWidget):
    """固定尺寸的出品方标记(底栏 / 设置页用)

    1.2.4 起兼任 SER 更新通道入口:左键连点 EGG_CLICKS 次(停顿超过
    egg_reset_ms 清零)触发 egg_activated。每次点击,末尾那点光都会
    「亮一下」—— 曲线与闪屏收尾是同一条 splash_spark_pulse,只是把
    0→1 的脉冲进度映射进它的时间窗(0.64→0.92),不另写一套缓动。
    """

    egg_activated = Signal()

    def __init__(self, height=12, alpha=150, parent=None,
                 egg_reset_ms=EGG_RESET_MS):
        super().__init__(parent)
        self._h = height
        self._a = alpha
        self.setFixedHeight(int(height * 1.9) + 2)
        self.setFixedWidth(studio_mark_widget_width(height))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # ---- 彩蛋连点 ----
        self._clicks = 0
        self._egg_reset_ms = max(200, int(egg_reset_ms))
        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.setInterval(self._egg_reset_ms)
        self._reset_timer.timeout.connect(self._reset_clicks)
        # ---- 点击时的光点脉冲 ----
        self._spark_t = 0.0
        self._spark_on = False
        self._spark_gain = 1.0
        self._spark_anim = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        kw = {}
        if self._spark_on:
            sc, gain = splash_spark_pulse(0.64 + 0.28 * self._spark_t)
            kw["spark_scale"] = sc
            kw["spark_alpha"] = min(319, int(255 * gain * self._spark_gain))
        draw_studio_mark(p, self.width() / 2.0, self.height() / 2.0, self._h,
                         max_width=self.width() - 8.0,
                         # 副字比传入值略亮一档 —— 12px 下再按比例压暗就糊成灰条了
                         letter_alpha=min(255, int(self._a * 1.08)),
                         mark_alpha=min(255, int(self._a * 1.75)), **kw)

    # ---------- 彩蛋连点 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._bump()
        super().mousePressEvent(e)

    def _bump(self):
        self._clicks += 1
        self._reset_timer.start()
        if self._clicks >= EGG_CLICKS:
            self._reset_clicks()
            self._pulse(1.0)          # 达标:满强度「亮一下」
            self.egg_activated.emit()
        else:
            self._pulse(0.55)         # 半途:轻微一闪,能感知但不出戏

    def _reset_clicks(self):
        self._clicks = 0
        self._reset_timer.stop()

    def remaining_clicks(self):
        """距离触发还差几下(回归脚本用)"""
        return max(0, EGG_CLICKS - self._clicks)

    # ---------- 光点脉冲 ----------
    def _pulse(self, gain=1.0):
        if self._spark_anim is not None:
            self._spark_anim.stop()
        self._spark_gain = max(0.05, float(gain))
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(420)
        anim.valueChanged.connect(self._on_pulse_step)
        anim.finished.connect(self._on_pulse_done)
        self._spark_anim = anim
        self._spark_on = True
        self._spark_t = 0.0
        self.update()
        anim.start()

    def _on_pulse_step(self, v):
        self._spark_t = float(v)
        self.update()

    def _on_pulse_done(self):
        self._spark_on = False
        self._spark_anim = None
        self.update()


# 工具注册表已改由功能模块自己声明：想加一个工具，就在 apps\ 里放一个文件，
# 写好 META（id / name / desc / icon / accent / order / card / builder），
# 主页会自动多出一张卡片、底栏会自动多一个导航项，这里一个字都不用改。


# ============================================================================
# 自绘控件
# ============================================================================

class AuroraRoot(QFrame):
    """窗口底:照片背景(或缓慢漂移的彩色光斑),让上层玻璃有内容可透

    背景图存在时:按 cover 方式铺满(等比放大到填满窗口,溢出部分居中裁掉,
    保证不变形),再压一层暗化蒙层,让玻璃面板与文字保持可读。
    找不到图片时自动退回光斑背景 —— 单独跑源码 / 打包漏带资源都不会白屏。
    """

    BLOBS = [
        (0.14, 0.05, 0.62, QColor(126, 92, 255, 76)),
        (0.92, 0.20, 0.55, QColor(64, 190, 255, 74)),
        (0.50, 1.05, 0.66, QColor(255, 104, 176, 66)),
        (0.02, 0.78, 0.48, QColor(72, 235, 190, 56)),
        (0.62, 0.54, 0.40, QColor(122, 148, 255, 44)),
    ]

    BG_FILE = os.path.join("assets", "bg.jpg")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("root")
        self._phase = 0.0
        self._radius = 20
        self.base_alpha = 226      # 深色基底不透明度(调低会更透,但宽窗易发灰)
        self.bg_alpha = 150        # 照片上压的暗化蒙层(0-255)
        self.bg_blur = 2           # 柔化倍率(缩小 N 倍再放大回来 ≈ 高斯模糊;1=不模糊)
        self.bg_path = None        # 当前壁纸路径(None = 内置)
        self._bg = None
        self._bg_scaled = None
        self._bg_key = None
        # 0 = 纯黑场(启动闪屏期间) , 1 = 壁纸完全显示。中间值用于交叉淡入。
        self._reveal = 1.0
        self._reveal_anim = None
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self.set_background(None)

    def set_background(self, path):
        """切换壁纸。

        bg_path 始终是"设置值":内置壁纸用相对常量,自定义用绝对路径;
        传入的路径解不出来就回退到内置,内置也没有才退到光斑。
        """
        real = _resolve_bg(path)
        if real is None:
            path = BUILTIN_WALLPAPER
            real = _resolve_bg(BUILTIN_WALLPAPER)
        pm = QPixmap(real) if real else QPixmap()
        if pm.isNull():
            self._bg = None
            self.bg_path = None
            print(f"[bg] 未找到背景图 {self.BG_FILE},回退到光斑背景")
            self._t.start(130)
        else:
            self._bg = pm
            self.bg_path = path
            self._t.stop()             # 静态照片不需要刷新
        self._bg_scaled = None
        self._bg_key = None
        self.update()

    def set_radius(self, r):
        self._radius = r
        self.update()

    # ---------- 黑场 / 壁纸揭示 ----------
    def get_reveal(self):
        return self._reveal

    def set_reveal(self, v):
        self._reveal = float(v)
        self.update()

    reveal = Property(float, get_reveal, set_reveal)

    def set_blackout(self, on=True):
        """启动瞬间切到纯黑场(不画壁纸/光斑),等主页要露面时再淡出来"""
        if self._reveal_anim is not None:
            self._reveal_anim.stop()
            self._reveal_anim = None
        self._reveal = 0.0 if on else 1.0
        self.update()

    def reveal_bg(self, duration=640):
        """从黑场把壁纸淡出来 —— 与闪屏遮罩的退场同步,不会"啪"地跳出来"""
        if self._reveal >= 0.999:
            return
        a = QPropertyAnimation(self, b"reveal", self)
        a.setDuration(duration)
        a.setStartValue(self._reveal)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()
        self._reveal_anim = a       # 必须留住引用,否则被 GC 连带动画消失
        return a

    def _tick(self):
        if not self.isVisible():
            return                     # 最小化/隐藏时不烧 CPU
        self._phase += 0.10
        self.update()

    # ---------- 照片背景 ----------
    def _scaled_bg(self, w, h):
        """cover 裁切 + 缓存:同一尺寸只重算一次"""
        if self._bg is None:
            return None
        if self._bg_scaled is not None and self._bg_key == (w, h):
            return self._bg_scaled
        sw, sh = self._bg.width(), self._bg.height()
        if sw <= 0 or sh <= 0 or w <= 0 or h <= 0:
            return None
        s = max(w / sw, h / sh)        # 取大比例 -> 铺满,不留白
        tw, th = max(1, round(sw * s)), max(1, round(sh * s))
        scaled = self._bg.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        cropped = scaled.copy((tw - w) // 2, (th - h) // 2, w, h)
        if self.bg_blur > 1:
            # 缩小再放大 = 廉价高斯模糊。不做的话照片细节会和玻璃面板抢视觉,
            # 面板上的文字对比度也压不住。
            bw, bh = max(1, w // self.bg_blur), max(1, h // self.bg_blur)
            cropped = cropped.scaled(
                bw, bh, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation).scaled(
                w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        self._bg_scaled = cropped
        self._bg_key = (w, h)
        return self._bg_scaled

    def _paint_photo(self, p, w, h):
        pm = self._scaled_bg(w, h)
        if pm is None:
            return False
        p.drawPixmap(0, 0, pm)
        # 整体压暗:玻璃面板/文字要在照片上依然可读
        p.fillRect(self.rect(), QColor(10, 11, 18, self.bg_alpha))
        # 上下再各压一层,中间留一点亮部给画面主体
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.00, QColor(8, 9, 14, 142))
        g.setColorAt(0.42, QColor(8, 9, 14, 34))
        g.setColorAt(1.00, QColor(8, 9, 14, 158))
        p.fillRect(self.rect(), QBrush(g))
        return True

    def _paint_aurora(self, p, w, h):
        # 基底:深色玻璃底。
        # alpha 必须够高 —— 横屏窗口很宽,右侧很容易压在亮色桌面/亮窗上,
        # 透过来的背景会把整块玻璃洗成灰色(实测 202 就会发灰)。
        p.fillRect(self.rect(), QColor(15, 15, 21, self.base_alpha))

        # 彩色光斑(缓慢正弦漂移)
        for i, (rx, ry, rr, col) in enumerate(self.BLOBS):
            dx = math.sin(self._phase * 0.9 + i * 1.7) * 0.055
            dy = math.cos(self._phase * 0.7 + i * 2.3) * 0.045
            cx = (rx + dx) * w
            cy = (ry + dy) * h
            # 半径按【短边】缩放 —— 用 max(w,h) 的话,窗口一拉宽光斑就随之
            # 放大数十倍,整块玻璃会被糊成一片灰白(横屏改造时踩过)。
            rad = rr * min(w, h) * 1.15
            a = col.alpha()
            g = QRadialGradient(QPointF(cx, cy), rad)
            g.setColorAt(0.0, QColor(col.red(), col.green(), col.blue(), a))
            g.setColorAt(0.55,
                         QColor(col.red(), col.green(), col.blue(), int(a * 0.34)))
            g.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(cx, cy), rad, rad)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)

        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)

        rv = max(0.0, min(1.0, self._reveal))

        p.save()
        p.setClipPath(path)
        if rv <= 0.001:
            p.fillRect(self.rect(), QColor(0, 0, 0))       # 纯黑场:启动闪屏期间
        else:
            if not self._paint_photo(p, w, h):
                self._paint_aurora(p, w, h)
            if rv < 0.999:
                # 黑场压在壁纸上淡出 = 交叉淡入,比直接切换柔和
                p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * (1.0 - rv))))
        p.restore()

        # 外描边:左上亮 → 右下淡(黑场里不描边,纯黑要干净)
        if rv <= 0.001:
            return
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, QColor(255, 255, 255, int(92 * rv)))
        g.setColorAt(0.45, QColor(255, 255, 255, int(34 * rv)))
        g.setColorAt(1.0, QColor(255, 255, 255, int(18 * rv)))
        p.setPen(QPen(QBrush(g), 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


def splash_spark_pulse(t):
    """启动闪屏收尾「末尾那点光亮一下」的曲线。

    返回 (半径倍数, 强度倍数);t 是 0→1 的动画进度。
    一段 sin 成形:0 → 峰值 → 0,点在动画最后胀一下再收回。
    半径与强度必须同时走 —— 点本体早就满白了,只改亮度肉眼看不出。

    抽成模块级函数是为了让预览/回归脚本调**同一个**曲线;
    否则脚本里再抄一份,改了主程序图还是旧的(这个项目栽过这种跟头)。
    """
    pulse = 0.0
    if 0.64 < t < 0.92:
        pulse = math.sin((t - 0.64) / 0.28 * math.pi)
    return 1.0 + 0.72 * pulse, 1.0 + 0.34 * pulse


class SplashOverlay(QWidget):
    """启动闪屏:纯字母 wordmark 的入场 —— 主字弹出 + 副字擦出 + 柔光脉冲 + 进度光带。

    只用一个 0→1 的 progress 动画驱动,paintEvent 内按时间段自己算缓动 ——
    比堆十几个并行动画好调，也不会出现"删 effect 时还在跑"的时序问题。

    时间轴(占总时长的比例):
      0.00 背景蒙层淡入
      0.10 主字 CH 带一点回弹弹出
      0.30 副字 Studios 从主字右侧擦出(两段间距同时展开)
      0.46 主字亮起一圈柔光脉冲
      0.58 底部进度光带开始走
      0.64 末尾那点光「亮一下」(胀一下再收回,与光带收尾重叠)
    """

    finished = Signal()
    fading = Signal()          # 遮罩开始退场(此刻可以放壁纸出来了)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t = 0.0
        self._anim = None
        self._fade = None
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def get_progress(self):
        return self._t

    def set_progress(self, v):
        self._t = v
        self.update()

    progress = Property(float, get_progress, set_progress)

    def play(self, duration=2400):
        self._t = 0.0
        self.show()
        self.raise_()
        self._anim = QPropertyAnimation(self, b"progress")
        self._anim.setDuration(duration)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)  # 缓动在绘制里做
        self._anim.finished.connect(self._on_played)
        self._anim.start()

    def _on_played(self):
        self.fade_out()

    def fade_out(self, duration=560):
        self.fading.emit()
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(1.0)
        self.setGraphicsEffect(eff)
        self._fade = QPropertyAnimation(eff, b"opacity")
        self._fade.setDuration(duration)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade.finished.connect(self._on_faded)
        self._fade.start()

    def _on_faded(self):
        self.setGraphicsEffect(None)
        self.hide()
        self.finished.emit()

    # ------------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        t = self._t

        # ---- 背景蒙层:启动期间整窗纯黑 ----
        bg = _ease_out_cubic(_clamp01(t / 0.16))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 20, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, QColor(0, 0, 0, int(255 * bg)))
        # 中心再压一点 —— 照片亮部(云/窗)会透过蒙层,压暗后 Logo 才够跳
        rg = QRadialGradient(QPointF(w / 2.0, h * 0.40), min(w, h) * 0.66)
        rg.setColorAt(0.0, QColor(0, 0, 0, int(96 * bg)))
        rg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(rg))
        p.drawRect(self.rect())

        cx = w / 2.0
        cy = h * 0.46                      # 产品名去掉后,字标在垂直方向更居中

        # 主字基准高度:按短边取,横屏下窗口变宽也不会显得过小。
        mh = max(17.0, min(min(w, h) * 0.080, w * 0.050))

        # ---- 主字弹出(带一点回弹) ----
        pop = _clamp01((t - 0.10) / 0.26)
        main_a = int(255 * _ease_out_cubic(pop))
        main_scale = 0.86 + 0.14 * _ease_out_back(pop)

        # ---- 副字从主字右侧擦出,两段间距同步展开 ----
        ea = _ease_out_cubic(_clamp01((t - 0.30) / 0.28))
        letter_a = int(238 * ea)
        spread = ea

        # ---- 收尾:末尾那点光「亮一下」 ----
        # 曲线在 splash_spark_pulse() 里,预览脚本调的是同一个函数,不会各写一套。
        spark_scale, spark_gain = splash_spark_pulse(t)
        spark_a = int(min(319, letter_a * spark_gain))

        if main_a > 0 or letter_a > 0:
            p.save()
            p.translate(cx, cy)
            p.scale(main_scale, main_scale)
            p.translate(-cx, -cy)
            draw_studio_mark(p, cx, cy, mh, max_width=w * 0.74,
                             letter_alpha=letter_a, mark_alpha=main_a,
                             spread=spread, glow=True,
                             spark_alpha=spark_a, spark_scale=spark_scale)
            p.restore()

        # ---- 主字亮起(一圈柔光脉冲,不改变字形本身) ----
        gp = _clamp01((t - 0.46) / 0.30)
        if 0.0 < gp < 1.0:
            e = math.sin(gp * math.pi)          # 0→1→0
            rr = mh * (2.4 + 1.6 * e)
            gg = QRadialGradient(QPointF(cx, cy), rr)
            gg.setColorAt(0.0, QColor(126, 176, 255, int(44 * e)))
            gg.setColorAt(0.55, QColor(126, 176, 255, int(15 * e)))
            gg.setColorAt(1.0, QColor(126, 176, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(gg))
            p.drawEllipse(QPointF(cx, cy), rr, rr)

        # ---- 进度光带 ----
        bp = _clamp01((t - 0.58) / 0.42)
        if bp > 0.0:
            bw = min(180.0, w * 0.40)
            bh = 3.5
            bx = cx - bw / 2.0
            by = cy + mh * 1.9
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(QRectF(bx, by, bw, bh), bh / 2, bh / 2)

            e = _ease_out_cubic(bp)
            fg = QLinearGradient(bx, 0, bx + bw, 0)
            fg.setColorAt(0.0, QColor("#6FB4FF"))
            fg.setColorAt(1.0, QColor("#A78BFA"))
            p.setBrush(QBrush(fg))
            p.drawRoundedRect(QRectF(bx, by, max(bh, bw * e), bh),
                              bh / 2, bh / 2)

            # 行进光头部的柔光
            if 0.03 < e < 0.98:
                hx = bx + bw * e
                hg = QRadialGradient(QPointF(hx, by + bh / 2), 16)
                hg.setColorAt(0.0, QColor(255, 255, 255, 140))
                hg.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(QBrush(hg))
                p.drawEllipse(QPointF(hx, by + bh / 2), 16, 16)


class WinBtn(QPushButton):
    """窗口控制按钮(自绘图标)"""

    def __init__(self, kind="min", parent=None):
        super().__init__(parent)
        self.kind = kind
        self._hover = False
        self.setFixedSize(30, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ff5f57") if self.kind == "close"
                       else QColor(255, 255, 255, 34))
            p.drawRoundedRect(QRectF(r).adjusted(1, 1, -1, -1), 6, 6)
        pen = QPen(QColor(255, 255, 255, 244 if self._hover else 208), 1.25)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        cx, cy = r.center().x(), r.center().y()
        if self.kind == "min":
            p.drawLine(cx - 5, cy + 1, cx + 5, cy + 1)
        elif self.kind == "max":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(cx - 4.5, cy - 4.5, 9, 9))
        elif self.kind == "restore":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(cx - 5.0, cy - 2.5, 7.5, 7.5))
            p.drawLine(cx - 2.5, cy - 5.0, cx + 2.5, cy - 5.0)
            p.drawLine(cx + 2.5, cy - 5.0, cx + 2.5, cy - 2.5)
        else:
            p.drawLine(cx - 4, cy - 3, cx + 4, cy + 5)
            p.drawLine(cx - 4, cy + 5, cx + 4, cy - 3)


# ============================================================================
# SER 更新通道彩蛋(1.2.4):命令提示符风格的更新控制台
# ============================================================================

def check_ser_code(text):
    """访问码校验:忽略首尾空白与大小写( cher2001 )"""
    return (text or "").strip().lower() == SER_CODE


# ---------- 本体文件图标自替换(1.2.4) --------------------------------
# exe 文件的图标是打包时烧进 PE 资源段的:运行时 setWindowIcon 只换
# 窗口/任务栏,资源管理器里看到的文件图标不会变。这里保留一条「自改写」
# 通路:复制本体 → 用 UpdateResourceW 改写副本的图标资源 → 原位换回。
# 运行中的 exe 不能被覆盖,但**可以改名**(Windows 允许给运行中的映像
# 改名)—— 于是先把旧本体改名成 <exe>.old,再把改好图标的副本挪回原名。
# .old 备份留到下一次本体成功启动后自动清理;万一改写后的本体起不来,
# .old 就是退路,手动改名回去即可。
#
# 注:1.2.4 起主图标本身就是纯黑底,打包出的 exe 图标资源天然与
# app_ser.ico 一致 —— 所以这条通路通常**直接判定"已是 SER"并跳过**,
# 不触碰本体文件;只有本体图标被换回(或来自更早的紫底构建)时才真正改写。
#
# ⚠ 踩坑(1.2.4 首次实现时):UpdateResourceW / EndUpdateResourceW 只写回
#   PE 映像,会**丢弃尾部附加数据** —— PyInstaller onefile 的自解压归档
#   恰好挂在文件尾部,一改写就被截成 300 多 KB、彻底打不开。现在改写完
#   必须把 overlay 原样接回并校验体积,塌陷即放弃换名(见 patch_exe_icon
#   与 swap_exe_icon_to_ser)。

_RT_ICON = 3
_RT_GROUP_ICON = 14
_LOAD_LIBRARY_AS_DATAFILE = 0x00000002


def _parse_ico(data):
    """解析 .ico 字节 → ([(宽,高,色数,保留,位面数,位深,字节数)...],
    [每帧图像字节,...])。目录里的偏移字段换成资源 id 在调用方拼。"""
    import struct
    _rsv, _typ, cnt = struct.unpack_from("<HHH", data, 0)
    entries, frames = [], []
    for i in range(cnt):
        off = 6 + 16 * i
        w, h, cc, rsv, planes, bits, size, imgoff = struct.unpack_from(
            "<BBBBHHII", data, off)
        entries.append((w, h, cc, rsv, planes, bits, size))
        frames.append(data[imgoff:imgoff + size])
    return entries, frames


def _k32_icon_api():
    """带完整原型声明的 kernel32 图标资源 API。

    必须显式声明:LoadLibraryExW 的返回值是 64 位模块句柄,不声明
    restype 会被 ctypes 按 32 位 c_int 截断 —— 截断后的句柄一传给
    EnumResourceNamesW 就静默失败,枚举永远是 0(踩过:首次实现漏了
    这一步,RT_ICON 枚举为空,patch 直接 0 帧)。
    """
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE,
                                   wintypes.DWORD]
    k32.EnumResourceNamesW.restype = wintypes.BOOL
    k32.EnumResourceNamesW.argtypes = [
        wintypes.HMODULE, ctypes.c_void_p,
        _ENUMRESNAMEPROC, ctypes.c_void_p]
    k32.FreeLibrary.restype = wintypes.BOOL
    k32.FreeLibrary.argtypes = [wintypes.HMODULE]
    k32.BeginUpdateResourceW.restype = wintypes.HANDLE
    k32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k32.UpdateResourceW.restype = wintypes.BOOL
    k32.UpdateResourceW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    k32.EndUpdateResourceW.restype = wintypes.BOOL
    k32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    return k32


_ENUMRESNAMEPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p,
    ctypes.c_void_p, ctypes.c_void_p)


def _enum_icon_names(exe_path):
    """枚举 exe 现有的图标资源名(整数 id 或字符串名),返回 (icon, group)"""
    k32 = _k32_icon_api()

    def _make(bucket):
        def cb(_hmod, _typ, name, _lp):
            v = ctypes.cast(name, ctypes.c_void_p).value or 0
            bucket.append(int(v) if v < 0x10000
                          else ctypes.wstring_at(v))
            return True
        return _ENUMRESNAMEPROC(cb)

    hmod = k32.LoadLibraryExW(str(exe_path), None,
                              _LOAD_LIBRARY_AS_DATAFILE)
    if not hmod:
        return [], []
    icons, groups = [], []
    try:
        k32.EnumResourceNamesW(hmod, ctypes.c_void_p(_RT_ICON),
                               _make(icons), None)
        k32.EnumResourceNamesW(hmod, ctypes.c_void_p(_RT_GROUP_ICON),
                               _make(groups), None)
    finally:
        k32.FreeLibrary(hmod)
    return icons, groups


def _pe_image_end(raw):
    """返回 PE 映像在文件里结束的偏移(各节 RawPtr+RawSize 的最大值)。

    这个偏移之后的字节是「附加数据」(overlay):PyInstaller onefile 的
    CArchive 自解压载荷就挂在那儿,占整个文件的 99%。

    解析失败返回 0(调用方按「没有附加数据」处理)。
    """
    import struct
    if len(raw) < 0x40:
        return 0
    try:
        e = struct.unpack_from("<I", raw, 0x3C)[0]
        if e + 24 > len(raw) or raw[e:e + 4] != b"PE\0\0":
            return 0
        nsec = struct.unpack_from("<H", raw, e + 6)[0]
        optsz = struct.unpack_from("<H", raw, e + 20)[0]
        sec = e + 24 + optsz
        end = 0
        for i in range(nsec):
            o = sec + i * 40
            if o + 40 > len(raw):
                return 0
            end = max(end,
                      struct.unpack_from("<I", raw, o + 20)[0]
                      + struct.unpack_from("<I", raw, o + 16)[0])
        return end
    except struct.error:
        return 0


def _read_icon_resource(exe_path, res_id=1):
    """读出 exe 里 RT_ICON #res_id 的原始字节;读不到返回 None。"""
    k32 = _k32_icon_api()
    k32.FindResourceW.restype = wintypes.HRSRC
    k32.FindResourceW.argtypes = [wintypes.HMODULE, ctypes.c_void_p,
                                  ctypes.c_void_p]
    k32.SizeofResource.restype = wintypes.DWORD
    k32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    k32.LoadResource.restype = wintypes.HGLOBAL
    k32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    k32.LockResource.restype = ctypes.c_void_p
    k32.LockResource.argtypes = [wintypes.HGLOBAL]
    hmod = k32.LoadLibraryExW(str(exe_path), None,
                              _LOAD_LIBRARY_AS_DATAFILE)
    if not hmod:
        return None
    try:
        hres = k32.FindResourceW(hmod, ctypes.c_void_p(res_id),
                                 ctypes.c_void_p(_RT_ICON))
        if not hres:
            return None
        size = int(k32.SizeofResource(hmod, hres) or 0)
        ptr = k32.LockResource(k32.LoadResource(hmod, hres))
        if not size or not ptr:
            return None
        buf = ctypes.create_string_buffer(size)
        ctypes.memmove(buf, ctypes.c_void_p(ptr), size)
        return bytes(buf.raw[:size])
    finally:
        k32.FreeLibrary(hmod)


def _exe_icon_is_ser(exe_path, ico_path):
    """本体 exe 的文件图标是否已经是纯黑底 SER 变体。

    按真实资源字节判断,不看注册表标志 —— 标志会说谎(exe 被换回旧版、
    或上次改写中途失败,标志却还留着 true),这里只认实际内容。
    """
    try:
        with open(ico_path, "rb") as f:
            frames = _parse_ico(f.read())[1]
    except (OSError, ValueError):
        return False
    if not frames:
        return False
    return _read_icon_resource(exe_path) == frames[0]


def patch_exe_icon(exe_path, ico_path):
    """把 exe_path 的图标资源整体替换为 ico_path 的内容。

    成功返回写入的帧数(>0),失败返回 0。只动 RT_ICON / RT_GROUP_ICON,
    版本信息等其它资源原样保留;资源组沿用原 exe 的组名 —— 任务栏与
    快捷方式都按它解析,换内容不动名字。

    ⚠ UpdateResource 系列 API **只写回 PE 映像**:文件尾部的附加数据
    (PyInstaller onefile 的 CArchive)会被整块丢弃,而且它重建的 .rsrc
    比原来的更紧凑 —— 实测 46.5MB 的本体被截成 328KB,截完直接起不来
    (1.2.4 首个构建就栽在这里)。所以这里先把映像末尾量出来、把附加
    数据整段记下来,写完再原样接回去,并校验接回成功。
    """
    import struct
    k32 = _k32_icon_api()
    try:
        with open(exe_path, "rb") as f:
            orig = f.read()
        with open(ico_path, "rb") as f:
            ico = f.read()
        entries, frames = _parse_ico(ico)
    except (OSError, ValueError):
        return 0
    if not frames:
        return 0

    img_end = _pe_image_end(orig)
    overlay = orig[img_end:] if img_end and img_end < len(orig) else b""

    icons, groups = _enum_icon_names(exe_path)
    grp_name = groups[0] if groups else 1

    def _name_arg(v):
        # 整数资源 id 按 MAKEINTRESOURCE 传值;字符串名传 wchar 指针。
        # keep 持有临时对象,保证指针在调用期间有效。
        if isinstance(v, int):
            return ctypes.c_void_p(v), None
        keep = ctypes.c_wchar_p(v)
        return ctypes.cast(keep, ctypes.c_void_p), keep

    hup = k32.BeginUpdateResourceW(str(exe_path), False)
    if not hup:
        return 0
    ended = False
    try:
        for old in icons:                     # 先删旧图标(传 NULL 即删除)
            arg, keep = _name_arg(old)
            k32.UpdateResourceW(hup, ctypes.c_void_p(_RT_ICON), arg,
                                0, None, 0)
        for old in groups:
            arg, keep = _name_arg(old)
            k32.UpdateResourceW(hup, ctypes.c_void_p(_RT_GROUP_ICON),
                                arg, 0, None, 0)
        for i, frame in enumerate(frames, start=1):
            buf = ctypes.create_string_buffer(frame, len(frame))
            if not k32.UpdateResourceW(hup, ctypes.c_void_p(_RT_ICON),
                                       ctypes.c_void_p(i), 0, buf,
                                       len(frame)):
                raise OSError("UpdateResource(RT_ICON) failed")
        # GRPICONDIR: 6B 头 + 每帧 14B 目录项(nID 从 1 起)
        dirbuf = struct.pack("<HHH", 0, 1, len(frames))
        for i, (w, h, cc, rsv, planes, bits, size) in enumerate(
                entries, start=1):
            dirbuf += struct.pack("<BBBBHHIH", w, h, cc, rsv, planes,
                                  bits, size, i)
        gbuf = ctypes.create_string_buffer(dirbuf, len(dirbuf))
        arg, keep = _name_arg(grp_name)
        if not k32.UpdateResourceW(hup, ctypes.c_void_p(_RT_GROUP_ICON),
                                   arg, 0, gbuf, len(dirbuf)):
            raise OSError("UpdateResource(RT_GROUP_ICON) failed")
        if not k32.EndUpdateResourceW(hup, False):
            raise OSError("EndUpdateResource failed")
        ended = True
    except OSError:
        if not ended:
            k32.EndUpdateResourceW(hup, True)   # 改写失败:回滚,不留半成品
        return 0

    # ---- 把附加数据接回文件尾部(API 只写了映像那一部分) ----
    if overlay:
        try:
            with open(exe_path, "rb") as f:
                cur = f.read()
            if not cur.endswith(overlay):
                with open(exe_path, "ab") as f:
                    f.write(overlay)
                with open(exe_path, "rb") as f:
                    cur = f.read()
            if not cur.endswith(overlay):
                raise OSError("附加归档未能接回")
        except OSError:
            return 0                    # 调用方在副本上操作,丢弃副本即可
    return len(frames)


def swap_exe_icon_to_ser():
    """把当前运行中的本体 exe 文件图标换成纯黑底 SER 变体。

    返回 (状态, 说明):
      ("ok",   "已备份为 <exe>.old · 图标 ×N")   替换完成,下次启动生效
      ("skip", ...)                             源码模式 / 图标已是 SER
      ("fail", 原因)                             权限/占用等,不影响软件功能

    安全守则(1.2.4 踩坑后加的):改写只在**副本**上做,做完先验体积,
    体积塌陷就直接放弃、绝不换名 —— 宁可图标不换,也不能把本体写成
    一个起不来的残废文件。
    """
    exe = sys.executable if getattr(sys, "frozen", False) else None
    if not exe or not exe.lower().endswith(".exe"):
        return "skip", "源码模式运行,跳过本体文件图标替换"
    ico = _res_path(os.path.join("icon", "app_ser.ico"))
    if not os.path.exists(ico):
        return "fail", "找不到 SER 图标资源 (app_ser.ico)"
    if _exe_icon_is_ser(exe, ico):
        return "skip", "本体文件图标已是纯黑底 SER 变体"
    _dir = os.path.dirname(os.path.abspath(exe))
    if not os.access(_dir, os.W_OK):
        return "fail", f"本体所在目录不可写,需管理员权限 ({_dir})"
    new, old = exe + ".ser_new", exe + ".old"
    for p in (new, old):
        if os.path.exists(p):
            try:
                os.remove(p)                  # 清掉上次残留
            except OSError:
                pass
    try:
        import shutil
        shutil.copy2(exe, new)
        n = patch_exe_icon(new, ico)
        if not n:
            raise OSError("图标资源改写失败")
        sz_src, sz_new = os.path.getsize(exe), os.path.getsize(new)
        if sz_new < sz_src * 0.9:              # 附加归档没接回去的信号
            raise OSError(f"改写后体积异常({sz_new} < {sz_src}),已放弃")
        os.rename(exe, old)                   # 运行中不能覆盖,但可以改名
        os.rename(new, exe)
        return "ok", (f"已备份为 {os.path.basename(old)}"
                      f" · 图标 ×{n}")
    except OSError as e:
        try:                                  # 尽力回滚:本体必须保持原名
            if os.path.exists(old) and not os.path.exists(exe):
                os.rename(old, exe)
        except OSError:
            pass
        try:
            if os.path.exists(new):
                os.remove(new)
        except OSError:
            pass
        return "fail", str(e)


class TermWindow(QDialog):
    """命令提示符风格的更新控制台(底栏标记连点 EGG_CLICKS 次弹出)。

    视觉对齐 Windows 控制台:#0C0C0C 黑底 + 浅灰等宽字 + 原生标题栏。
    输入 SER_CODE 回车后,更新过程逐行完整打印(下载一行做进度动画),
    打到「√ 更新完成」时发 updated —— App 收到后切到 1.2.ser 通道
    (版本标识 + 纯黑底图标)。全程本机演示,不联网。

    窗口生命周期:中途关窗 = 流程作废,下次打开清空重来;走完后重开
    则保留完整更新记录,输入行收起。
    """

    updated = Signal()

    TERM_BG = "#0C0C0C"
    TERM_FG = "#CCCCCC"
    TERM_DIM = "#8A8A8A"
    TERM_OK = "#16C60C"
    PROG_W = 22              # 进度条格数

    def __init__(self, parent=None, already_ser=False):
        super().__init__(parent)
        self.setWindowTitle("CHStudios 更新控制台")
        self.setModal(False)
        self.resize(700, 440)
        self.setMinimumSize(QSize(560, 360))
        self.setStyleSheet(f"background-color: {self.TERM_BG};")

        self._mono = QFont("Consolas", 10)
        self._already_ser = already_ser
        self._greeted = False      # banner 只在日志为空时打
        self._busy = False         # 更新流程进行中(禁止再输指令)
        self._done = False         # 更新流程已走完
        self._steps = []           # 待执行队列 [(延时ms, 类型, 数据, 颜色)]
        self._prog_anim = None
        self._prog_lab = None

        self._step_timer = QTimer(self)
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._print_next)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------- 日志区(黑底等宽,逐行 QLabel) ----------------
        # 逐行 QLabel 而不是 QPlainTextEdit:下载进度那一行要原位刷新,
        # 且不同行可以给不同颜色,QTextEdit 里做这两件事都别扭。
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {self.TERM_BG}; border: none; }}")
        host = QWidget()
        host.setStyleSheet(f"background: {self.TERM_BG};")
        self._log_lay = QVBoxLayout(host)
        self._log_lay.setContentsMargins(14, 12, 14, 10)
        self._log_lay.setSpacing(3)
        self._log_lay.addStretch(1)      # 行数少时顶格排,空当留给底部
        self._scroll.setWidget(host)
        root.addWidget(self._scroll, 1)

        # ---------------- 输入行:提示符 + 内联输入框 ----------------
        row = QWidget()
        row.setStyleSheet(f"background: {self.TERM_BG};")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 2, 14, 12)
        rl.setSpacing(0)
        self.prompt_lbl = QLabel("C:\\CHStudios> ")
        self._style_term_label(self.prompt_lbl, self.TERM_FG)
        rl.addWidget(self.prompt_lbl)
        self.input = QLineEdit()
        self.input.setFont(self._mono)
        self.input.setFrame(False)
        self.input.setStyleSheet(
            "QLineEdit { background: transparent; border: none; "
            f"color: {self.TERM_FG}; font-family: Consolas, monospace; "
            "font-size: 13px; selection-background-color: #3B7DD8; }")
        self.input.returnPressed.connect(self._submit)
        rl.addWidget(self.input, 1)
        root.addWidget(row)

    # ---------- 终端输出 ----------
    def _style_term_label(self, lab, color):
        lab.setFont(self._mono)
        lab.setStyleSheet(f"color: {color}; background: transparent;")
        lab.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)

    def _add_line(self, text="", color=None):
        lab = QLabel(text)
        self._style_term_label(lab, color or self.TERM_FG)
        # 插在 stretch 之前,保持内容顶格
        self._log_lay.insertWidget(self._log_lay.count() - 1, lab)
        self._scroll_bottom()
        QTimer.singleShot(0, self._scroll_bottom)
        return lab

    def _scroll_bottom(self):
        try:
            sb = self._scroll.verticalScrollBar()
            sb.setValue(sb.maximum())
        except RuntimeError:
            pass

    def _reset_log(self):
        """清空日志(中途关窗作废,下次打开重新走)"""
        while self._log_lay.count() > 1:          # 末位是 stretch
            item = self._log_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._greeted = False
        self._busy = False
        self.input.setEnabled(True)
        self.prompt_lbl.setVisible(True)

    # ---------- 访问码 ----------
    def _submit(self):
        if self._busy or not self.input.isEnabled():
            return
        txt = self.input.text().strip()
        self.input.clear()
        if not txt:
            return
        self._add_line(f"C:\\CHStudios> {txt}")
        if check_ser_code(txt):
            self._add_line("访问码校验... 通过")
            self._start_update()
        else:
            self._add_line(f"‘{txt}’ 不是有效访问码,请检查后重新输入。")
            self._scroll_bottom()

    # ---------- 更新流程 ----------
    def _start_update(self):
        """逐行打印更新过程;单发定时器串步进,行间留呼吸不刷屏"""
        self._busy = True
        self.input.setEnabled(False)
        self.prompt_lbl.setVisible(False)
        self._steps = [
            (260, "line", "正在初始化更新环境... 完成", None),
            (300, "line", "正在检查运行状态... 连点器空闲", None),
            (300, "line", "正在备份用户配置... 完成 (HKCU\\Software\\Pivot)",
             None),
            (320, "line", "正在连接更新服务器... 已连接 (SER 通道 · 本机镜像)",
             None),
            (240, "prog", "正在下载增量包 pivot_ser_1.3.pkg", None),
            (300, "line", "正在校验包完整性... SHA-256 OK", None),
            (260, "line", "正在解包资源文件... 完成", None),
            (300, "patch", None, None),
            (320, "line",
             f"正在更新版本标识: {APP_VER} → {SER_VER} ... 完成", None),
            (260, "line", "正在清理临时文件... 完成", None),
            (430, "gap", None, None),
            (30, "line", f"√ 更新完成 — 当前版本 {SER_VER}", self.TERM_OK),
            (60, "emit", None, None),
            (340, "line",
             "  本版本功能与 1.2.4 保持一致,新特性将在后续版本逐步开放。",
             self.TERM_DIM),
            (300, "line", "  更新状态已写入本机,重启后保留。", self.TERM_DIM),
            (380, "note", "窗口将在 4 秒后自动关闭,也可直接关闭本窗口。", None),
            (4200, "close", None, None),
        ]
        self._step_timer.start(180)

    def _print_next(self):
        if not self._steps:
            return
        delay, kind, data, color = self._steps.pop(0)
        if kind == "line":
            self._add_line(data, color)
            self._step_timer.start(delay)
        elif kind == "gap":
            self._add_line()
            self._step_timer.start(delay)
        elif kind == "note":
            self._add_line(data, color or self.TERM_DIM)
            self._step_timer.start(delay)
        elif kind == "emit":
            # 先切本体再打收尾说明:关窗前版本标识已经变过来了
            self.updated.emit()
            self._step_timer.start(delay)
        elif kind == "close":
            self._done = True
            self.close()
        elif kind == "patch":
            self._run_patch()
        elif kind == "prog":
            self._run_progress(data)
            # 进度动画结束(_on_prog_done)后再续队列,这里不排程

    def _run_patch(self):
        """真正改写本体文件图标:备份 → 改写副本 → 原位换回,逐行打印。

        与「下载/校验」等演示行不同,这一步是真实落盘操作 —— 改写的是
        当前正在运行的这个 exe 文件的图标资源,让资源管理器里看到的
        文件图标也变成纯黑底(运行时换 QIcon 做不到这一点)。
        """
        if not getattr(sys, "frozen", False):
            self._add_line("正在替换本体文件图标... 完成 (纯黑底 · SER)")
            self._step_timer.start(300)
            return
        self._add_line("正在替换本体文件图标 (纯黑底 · SER) ...")
        st, msg = swap_exe_icon_to_ser()
        if st in ("ok", "skip"):
            self._add_line(f"  • {msg}", self.TERM_DIM)
            if st == "ok":
                self._add_line("  • 图标资源改写完成,资源管理器即用此图标",
                               self.TERM_DIM)
                self._add_line("  • 已原位换回本体,下次启动即生效",
                               self.TERM_DIM)
            try:
                settings_store().setValue("icon_patched", "true")
            except Exception:
                pass
        else:
            self._add_line(f"  ! 本体文件图标替换未完成 ({msg})", "#E7B100")
            self._add_line(
                "    软件功能不受影响;窗口/任务栏图标已同步为纯黑底。",
                self.TERM_DIM)
        self._step_timer.start(360)

    def _run_progress(self, prefix):
        """下载行:同一行原位刷新 [####----] 42%,走完再续后面的步骤"""
        self._prog_lab = self._add_line(prefix)
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(1500)
        anim.valueChanged.connect(self._on_prog_tick)
        anim.finished.connect(self._on_prog_done)
        self._prog_anim = anim
        anim.start()

    def _on_prog_tick(self, v):
        try:
            n = int(float(v) * self.PROG_W)
            bar = "█" * n + "-" * (self.PROG_W - n)
            self._prog_lab.setText(
                f"正在下载增量包 pivot_ser_1.3.pkg [{bar}] "
                f"{int(float(v) * 100):3d}%")
        except RuntimeError:
            pass

    def _on_prog_done(self):
        try:
            full = "█" * self.PROG_W
            self._prog_lab.setText(
                f"正在下载增量包 pivot_ser_1.3.pkg [{full}] 100%")
        except RuntimeError:
            return
        self._step_timer.start(240)

    # ---------- 窗口行为 ----------
    def _greet(self):
        self._add_line("CHStudios 更新控制台 [版本 1.2.4.0]")
        self._add_line("(c) 2026 CHStudios。保留所有权利。")
        self._add_line()
        if self._already_ser:
            self._add_line(f"当前版本: {SER_VER}")
            self._add_line("已是最新,没有可用的更新。")
            self.input.setEnabled(False)
            self.prompt_lbl.setVisible(False)
        else:
            self._add_line(f"检测到当前版本: {APP_VER}")
            self._add_line(f"可用更新: {SER_VER} (SER 通道 · 内部)")
            self._add_line()
            self._add_line("输入访问码并回车以开始更新。", self.TERM_DIM)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._greeted:
            self._greeted = True
            self._greet()
        self.input.setFocus()
        self._scroll_bottom()

    def closeEvent(self, e):
        self._step_timer.stop()
        if self._prog_anim is not None:
            try:
                self._prog_anim.stop()
            except RuntimeError:
                pass
        if not self._done:
            self._reset_log()          # 中途关窗:流程作废,重来
        super().closeEvent(e)

class App(*_FEATURE_BASES, QWidget):
    """外壳窗口。

    `*_FEATURE_BASES` 来自 apps\\ 里装载成功的那几个功能模块 —— 每个功能把
    自己的 Feature 混进来，方法体里的 self 就是本类实例。所以某个功能模块
    被删掉时，这里少一个基类、对应的方法自然不存在；外壳对这些方法一律用
    getattr 兜底，窗口照常起来，只是少了那一页。
    """

    # 跨线程信号:业务线程 emit,Qt 自动排队到主线程执行
    sig_status = Signal(str)
    sig_count = Signal(int)
    sig_hotkey = Signal(str)       # keyboard 监听线程 -> 主线程
    sig_kb_status = Signal(str)    # 键盘连按引擎 -> 主线程
    sig_kb_count = Signal(int)

    def __init__(self):
        super().__init__()
        # 系统级窗口标题只放一个「枢」：任务栏悬浮提示、Alt-Tab 里都清爽；
        # 窗口内的自绘标题栏另有「枢  PIVOT」两段排版，不必在这里重复。
        # （测试脚本按标题找窗口，用的就是这一个精确匹配的 "枢"。）
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 横屏窗口:可自由缩放,并记住上次的尺寸与位置
        self.setMinimumSize(QSize(940, 600))
        self._settings = settings_store()
        self._is_max = False
        self._pre_max_geo = None
        self._restored_pos = False
        self._pending_max = False
        self._restore_geometry()

        # 引擎与各功能的状态都归功能模块自己管（见 apps\clicker.py 等）：
        # 模块在就建引擎，模块被删掉就没有 —— 所以这里只留外壳必需的状态。
        self.macro = None              # 连点器引擎（apps\clicker.py 装）
        self.kbrep = None              # 键盘连按引擎（apps\keys.py 装）
        self._mode = "left"
        self._pending_count = 0
        self._count_scheduled = False
        self._progress_total = 0
        self._panels = []
        # 主页卡片清单：由功能模块的 META 汇总而来（home 模块读它来铺网格）
        self.tool_registry = TOOLS
        # 信号槽按"功能在不在"来决定接不接 —— 功能被删了就没人处理，别硬连
        for sig, slot in ((self.sig_status, "_handle_status"),
                          (self.sig_count, "_queue_count"),
                          (self.sig_kb_status, "_handle_kb_status"),
                          (self.sig_kb_count, "_queue_kb_count")):
            fn = getattr(self, slot, None)
            if fn is not None:
                sig.connect(fn)
        self.sig_hotkey.connect(self._on_hotkey)

        # 键盘连按与按键改绑的状态、持久化、页面，全部归各自的 apps\\ 模块管，
        # 外壳不再替它们预设属性 —— 模块不在时这些名字就不存在，调用方自己兜。

        # 热键(可在设置页改绑)与安全中止开关
        self._hk_start = str(self._settings.value("hotkey_start", "f6"))
        self._hk_stop = str(self._settings.value("hotkey_stop", "f7"))
        pyautogui.FAILSAFE = str(
            self._settings.value("failsafe", "true")) == "true"
        # 壁纸与观感
        self._root_ready = False
        # SER 通道状态(更新彩蛋,持久化;1.2.ser 只换标识与图标,功能不变)
        self._ser = str(
            self._settings.value("ser_updated", "false")) == "true"
        self._disp_ver = SER_VER if self._ser else APP_VER

        self._build_ui()
        self._root.set_background(self._settings.value("bg_path"))
        self._root.bg_alpha = self._to_int(
            self._settings.value("bg_alpha", 150), 150, lo=0, hi=255)
        self._root.bg_blur = self._to_int(
            self._settings.value("bg_blur", 2), 2, lo=1, hi=6)
        self._apply_hotkeys()
        # 上次开启的按键改绑在启动时恢复（remap 模块不在就跳过）
        restore = getattr(self, "_apply_remaps", None)
        if restore is not None:
            restore()
        if self._ser:
            self._apply_ser_mode()
            self._ser_icon_housekeeping()

        # 光标光泽:轮询全局鼠标位置驱动玻璃高光。
        # 鼠标不动就完全跳过重绘,否则静止时也在白烧 CPU。
        self._last_cursor = None
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._update_glow)
        self._glow_timer.start(45)

        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(460)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 启动后静默查一次更新。故意放在最后、且延迟 3 秒：
        # 闪屏与入场动画先走完，网络请求在后台线程里跑，绝不拖慢启动。
        # 检查本身永远不会抛出来 —— 断网时用户看到的只是"检查失败"一行字。
        QTimer.singleShot(3000, self._silent_check_update)

    def _silent_check_update(self):
        """启动时自动检查一次更新。

        只在「更新」功能页还在时做：apps\\update.py 被删掉后就没有能
        展示结果的界面，这时候再联网查一次纯属浪费，直接跳过。
        """
        if not hasattr(self, "_on_upd_check"):
            return
        try:
            if str(self._settings.value("auto_check", "true")) != "true":
                return
            self._on_upd_check()
        except Exception:                                   # noqa: BLE001
            pass

    # ---------- 窗口几何 ----------
    DEFAULT_SIZE = QSize(1080, 690)

    def _restore_geometry(self):
        """恢复上次的窗口大小与位置;超出当前屏幕则退回默认"""
        scr = QApplication.primaryScreen().availableGeometry()
        try:
            sz = self._settings.value("size")
            if isinstance(sz, QSize) and sz.isValid():
                w = max(940, min(sz.width(), scr.width()))
                h = max(600, min(sz.height(), scr.height()))
            else:
                w, h = self.DEFAULT_SIZE.width(), self.DEFAULT_SIZE.height()
            self.resize(min(w, scr.width()), min(h, scr.height()))

            pos = self._settings.value("pos")
            if isinstance(pos, QPoint) and not pos.isNull():
                if scr.intersects(QRect(pos, self.size())):
                    self.move(pos)
                    self._restored_pos = True
            if str(self._settings.value("maximized", "false")) == "true":
                self._pending_max = True
        except Exception:
            self.resize(self.DEFAULT_SIZE)

    def _save_geometry(self):
        try:
            self._settings.setValue("size", self.size())
            if not self._is_max:
                self._settings.setValue("pos", self.pos())
            self._settings.setValue("maximized",
                                    "true" if self._is_max else "false")
        except Exception:
            pass

    def _toggle_max(self):
        self._set_max_state(not self._is_max)

    def _set_max_state(self, on):
        if on == self._is_max:
            return
        if on:
            self._pre_max_geo = self.geometry()
            scr = QApplication.primaryScreen().availableGeometry()
            self.setGeometry(scr)
        else:
            if self._pre_max_geo is not None:
                self.setGeometry(self._pre_max_geo)
        self._is_max = on
        self.max_btn.kind = "restore" if on else "max"
        self.max_btn.update()
        # 最大化时贴合屏幕边缘,不再保留圆角
        self._root.set_radius(0 if on else 20)

    # ---------- 背景材质 ----------
    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_backdrop_done", False):
            self._backdrop_done = True
            self._backdrop = apply_backdrop(int(self.winId()), dark=True)
            if getattr(self, "_pending_max", False):
                self._pending_max = False
                self._set_max_state(True)
            self._start_splash()

    # ---------- 启动流程:闪屏 → 主界面入场 ----------
    def _start_splash(self):
        """窗口淡入 + 上浮落位,同时播放 Logo 闪屏"""
        self._fade.start()

        if self._restored_pos or self._is_max:
            pass                    # 有记忆位置 / 最大化:不再居中上浮
        else:
            try:
                scr = QApplication.primaryScreen().availableGeometry()
                cx = scr.center().x() - self.width() // 2
                cy = scr.center().y() - self.height() // 2
                if scr.contains(QPoint(cx, cy + 18)):
                    self.move(cx, cy + 18)
                    a_pos = QPropertyAnimation(self, b"pos")
                    a_pos.setDuration(620)
                    a_pos.setStartValue(QPoint(cx, cy + 18))
                    a_pos.setEndValue(QPoint(cx, cy))
                    a_pos.setEasingCurve(QEasingCurve.Type.OutCubic)
                    a_pos.start()
                    self._intro_anims.append(a_pos)
            except Exception:
                pass

        # 闪屏期间先把内容块按住(全透明),等闪屏退场再逐个放出来
        QTimer.singleShot(0, self._hold_blocks)

        self.splash.finished.connect(self._on_splash_done)
        # 遮罩一开始退场就把壁纸从纯黑里淡出来 —— 两段动画叠在一起,
        # 黑场→壁纸是一次连续过渡,不会先黑屏再"啪"地跳出一张照片。
        self.splash.fading.connect(self._reveal_wallpaper)
        self.splash.play(duration=SPLASH_MS)
        QTimer.singleShot(SPLASH_MS + 2000, self._clear_intro_refs)

    def _reveal_wallpaper(self):
        if getattr(self, "_root", None) is not None:
            self._root.reveal_bg(660)

    def _hold_blocks(self):
        """闪屏期间把内容块设为全透明。

        关键:effect 必须存到 self 上。setGraphicsEffect 之后如果 Python 侧
        没有引用，wrapper 会被 GC 并连带删掉 C++ 对象，特效会静默消失
        （读回 graphicsEffect() 得到 None，且没有任何报错）。
        """
        self._hold_effs = []
        for blk in self._intro_blocks:
            if blk.graphicsEffect() is None:
                eff = RiseFade()
                eff.setOpacity(0.0)
                eff.set_dy(24.0)
                blk.setGraphicsEffect(eff)
                self._hold_effs.append(eff)

    def _clear_intro_refs(self):
        self._intro_anims.clear()
        self._hold_effs.clear()

    def _on_splash_done(self):
        self.splash.hide()
        self._reveal_wallpaper()      # 兜底:万一时序错开,这里也保证壁纸会出来
        self._blocks_in()

    def _blocks_in(self):
        """内容块自上而下错落上浮 + 淡入"""
        for i, blk in enumerate(self._intro_blocks):
            eff = blk.graphicsEffect()
            if eff is None:
                continue
            QTimer.singleShot(40 + i * 48,
                              lambda b=blk, e=eff: self._rise_in(b, e))

    def _rise_in(self, blk, eff):
        if not self.isVisible():
            return
        try:
            a_op = QPropertyAnimation(eff, b"opacity")
            a_dy = QPropertyAnimation(eff, b"dy")
        except RuntimeError:
            return
        # 两个动画必须等长 —— 若清理时还有一个在跑,删掉 effect 会崩
        for a in (a_op, a_dy):
            a.setDuration(430)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a_op.setStartValue(0.0)
        a_op.setEndValue(1.0)
        a_dy.setStartValue(24.0)
        a_dy.setEndValue(0.0)
        a_op.finished.connect(lambda b=blk: self._drop_effect(b))
        a_op.start()
        a_dy.start()
        self._intro_anims.extend([a_op, a_dy])

    @staticmethod
    def _drop_effect(blk):
        """动画结束移除图形特效,恢复控件原生渲染(带特效层时文字会略糊)"""
        try:
            blk.setGraphicsEffect(None)
        except RuntimeError:
            pass

    def _update_glow(self):
        if not self.isVisible():
            return
        gp = QCursor.pos()
        if gp == self._last_cursor:
            return                     # 鼠标静止,无需重绘
        self._last_cursor = gp
        for panel in self._panels:
            if not panel.isVisible():
                continue               # 其他页面的面板不必重绘
            panel.set_cursor_glow(gp)

    # ---------- UI ----------
    def _panel(self, spacing=10, margins=(16, 14, 16, 16)):
        p = GlassPanel()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)
        self._panels.append(p)
        return p, lay

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._root = AuroraRoot()
        # 启动就是纯黑场:壁纸等闪屏退场时才淡出来(见 _reveal_wallpaper)
        self._root.set_blackout(True)
        outer.addWidget(self._root)

        root = QVBoxLayout(self._root)
        root.setContentsMargins(22, 13, 22, 13)
        root.setSpacing(12)

        bar_w = self._build_titlebar()
        root.addWidget(bar_w)

        # ===== 页面容器 =====
        # 页面由 apps\ 里装载成功的功能模块自己构建。任何一个模块缺失、
        # 装载失败、或者构建时抛异常，都只影响它自己：这里跳过它继续建下一个。
        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        self._feature_pages = {}       # 功能 id -> 页面控件
        self._feature_metas = {}       # 功能 id -> META
        for feat in FEATURES:
            meta = feat.META
            builder = getattr(self, meta["builder"] or "", None)
            if builder is None:
                continue               # 例如"更多工具"：只有卡片，没有页面
            try:
                pg = builder()
                if not isinstance(pg, QWidget):
                    raise TypeError("builder 没返回 QWidget")
            except Exception as e:     # noqa: BLE001
                print(f"[apps] {meta['module']} 构建页面失败: "
                      f"{type(e).__name__}: {e}", file=sys.stderr)
                pg = self._broken_page(meta, e)
            self._feature_pages[meta["id"]] = pg
            self._feature_metas[meta["id"]] = meta
            if meta["state"]:
                setattr(self, meta["state"], pg)   # 兼容旧引用 self.page_xxx
            self.stack.addWidget(pg)
        if not self._feature_pages:
            self.stack.addWidget(self._empty_page())

        root.addWidget(self.stack, 1)

        bottom_w = self._build_bottombar()
        root.addWidget(bottom_w)

        # 覆盖层:倒计时遮罩 -> 闪屏(z 序最上层,盖住一切)
        self.countdown = CountdownOverlay(self._root)
        self.splash = SplashOverlay(self._root)

        # 入场动画的编排顺序(标题栏 -> 落地页内容 -> 底栏)
        first = self._default_key()
        self._intro_blocks = [bar_w,
                              *getattr(self._feature_pages.get(first),
                                       "_blocks", []),
                              bottom_w]
        self._intro_anims = []
        self._page_effs = []
        self._page = None
        self._goto_default()
        for k, t in self.nav_tabs.items():
            t.set_selected(k == first)

        # 所有页面都建好了,再统一同步一次(外观页构建时设置页还不存在)
        sync = getattr(self, "_sync_wallpaper_ui", None)
        if sync is not None:
            sync()

        self._sync_apps_state()

    def _sync_apps_state(self):
        """记下「这一版程序应该装有哪些功能文件」。

        只在本版第一次运行时写（或版本号变了时重写）。此后用户手动删掉的
        文件，就是这份记录与 apps\\ 现状的差集 —— 更新时据此避免把他删掉的
        功能又装回来，同时不会挡住本版新增的功能（那两者在文件系统上长得
        一模一样，只能靠这份记录区分）。

        源码模式不写：那是给"替换文件"用的记录，跑源码时没有意义，
        还会把工作目录弄脏。
        """
        try:
            if not updater_core.is_frozen():
                return
            target = updater_core.app_dir()
            state = updater_core.read_apps_state(target)
            if state and state.get("version") == APP_VER:
                return
            apps_dir = None
            for path in _apps_dirs():
                if os.path.isdir(path):
                    apps_dir = path
                    break
            if not apps_dir:
                return
            names = [n for n in os.listdir(apps_dir)
                     if n.lower().endswith(".py")]
            updater_core.write_apps_state(target, APP_VER, names)
        except Exception:                                   # noqa: BLE001
            pass

    # ---------- 缺功能时的兜底页面 ----------
    def _default_key(self):
        """落地页:优先"主页",否则第一个能导航的功能"""
        if "home" in self._feature_pages:
            return "home"
        for fid, meta in self._feature_metas.items():
            if meta["nav"]:
                return fid
        return next(iter(self._feature_pages), None)

    def _goto_default(self):
        key = self._default_key()
        if key is None:
            return
        self._page = key
        self.stack.setCurrentWidget(self._feature_pages[key])

    @staticmethod
    def _empty_page():
        """一个功能都没装载上时的占位页：不崩、可读、能关"""
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel("没有可用功能\n\napps\\ 目录是空的，或全部功能模块都没能装载。\n"
                     "往 apps\\ 里放回 .py 功能文件，重启即可恢复。")
        lab.setObjectName("pageHint")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        pg._blocks = []
        return pg

    @staticmethod
    def _broken_page(meta, err):
        """某个功能构建失败时的占位页：其余功能不受影响"""
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(f"「{meta.get('name', meta['id'])}」这个功能没能加载\n\n"
                     f"{type(err).__name__}: {err}\n\n"
                     "其余功能不受影响。修好 apps\\ 里对应的 .py 后重启即可。")
        lab.setObjectName("pageHint")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        pg._blocks = []
        return pg

    # ---------- 标题栏 ----------
    def _build_titlebar(self):
        bar = QHBoxLayout()
        bar.setSpacing(9)
        title = QLabel(APP_NAME)
        title.setObjectName("windowTitle")
        bar.addWidget(title)
        brand = QLabel(APP_NAME_EN)
        brand.setObjectName("brandSub")
        bar.addWidget(brand, 0, Qt.AlignmentFlag.AlignVCenter)
        bar.addStretch()
        min_btn = WinBtn("min")
        min_btn.clicked.connect(self.showMinimized)
        bar.addWidget(min_btn)
        self.max_btn = WinBtn("max")
        self.max_btn.clicked.connect(self._toggle_max)
        bar.addWidget(self.max_btn)
        close_btn = WinBtn("close")
        close_btn.clicked.connect(self.close)
        bar.addWidget(close_btn)
        w = QWidget()
        w.setLayout(bar)
        return w

    # ---------- 底栏:版本 + 导航 + 出品方标记 ----------
    def _build_bottombar(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(6)
        ver = QLabel(f"v{self._disp_ver}")
        ver.setObjectName("verSmall")
        self.ver_label = ver
        lay.addWidget(ver)
        lay.addSpacing(10)
        self.nav_tabs = {}
        # 导航项完全由功能模块决定：谁声明了 nav 谁就在底栏出现，顺序看 order。
        # 所以删掉一个功能模块，底栏那一项自动消失——这里不需要跟着改。
        for fid, meta in self._feature_metas.items():
            if not meta["nav"] or fid not in self._feature_pages:
                continue
            t = NavTab(meta["nav"], fid)
            t.clicked.connect(self.go)
            lay.addWidget(t)
            self.nav_tabs[fid] = t
        lay.addStretch()
        # 出品方标记(取代了原来的用户胶囊)。1.2.4 起加大一档,
        # 并兼任 SER 更新通道入口:连点 EGG_CLICKS 次 → 弹出更新控制台
        self.studio_mark = StudioMark(FOOTER_MARK_H, 150)
        self.studio_mark.setToolTip(
            f"Made by {STUDIO_NAME}\n(它似乎对连点很有兴趣…)")
        self.studio_mark.egg_activated.connect(self._open_terminal)
        lay.addWidget(self.studio_mark, 0, Qt.AlignmentFlag.AlignVCenter)
        self._bottom_lay = lay
        return w

    @staticmethod
    def _glass_scroll(scroll):
        """让 QScrollArea 的 viewport 透明。

        QAbstractScrollArea 的 viewport 默认 autoFillBackground=True 且用
        QPalette::Base 填底,在深色玻璃上就是一大块浅色白板。QSS 里那条
        #wpViewport 一直是死规则(没人给 viewport 挂过 objectName),
        外观页靠 host 自己铺满才没露馅;这里按名字挂上再关掉自动填充。
        """
        vp = scroll.viewport()
        vp.setObjectName("wpViewport")
        vp.setAutoFillBackground(False)
        vp.setStyleSheet("background: transparent;")
        vp.style().unpolish(vp)
        vp.style().polish(vp)

    # ---------- SER 更新通道彩蛋(1.2.4) ----------
    def _open_terminal(self):
        """底栏标记连点达标:弹出命令提示符风格的更新控制台(非模态)"""
        w = getattr(self, "_term", None)
        if w is None:
            w = TermWindow(self, already_ser=self._ser)
            w.updated.connect(self._on_ser_updated)
            self._term = w
        w.show()
        w.raise_()
        w.activateWindow()

    def _on_ser_updated(self):
        """控制台更新完成:切到 SER 通道(版本标识 + 纯黑底图标),重启保留"""
        if not self._ser:
            self._ser = True
            self._disp_ver = SER_VER
            try:
                self._settings.setValue("ser_updated", "true")
            except Exception:
                pass
        self._apply_ser_mode()

    def _apply_ser_mode(self):
        """SER 通道外观:窗口/任务栏图标换纯黑底变体,三处版本标识同步"""
        ico = _res_path(os.path.join("icon", "app_ser.ico"))
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))
        for attr, fmt in (("ver_label", "v{}"),
                          ("_home_ver_lbl", "{}"),
                          ("_about_ver_lbl", "{}")):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                w.setText(fmt.format(SER_VER))
            except RuntimeError:
                pass

    # ---------- SER 本体图标自维护 ----------
    def _ser_icon_housekeeping(self):
        """已是 1.2.ser 时的本体图标收尾(后台,不卡启动)。

        1) 清理上次自替换留下的 <exe>.old 备份 —— 能走到这一步说明
           当前(改写后的)本体已成功启动,旧备份没有保留价值。
        2) 本体文件图标和当前 ser 状态不一致时(老构建、图标被换回过、
           上次改写中途失败……)静默补一次替换。判断依据是**实际资源
           字节**(_exe_icon_is_ser),不是注册表标志 —— 标志会说谎:
           exe 被还原成 1.2.4 了,icon_patched 还留着一个 true。
           改写/换名是纯 OS 调用,放到后台线程不冻结界面。
        """
        if not getattr(sys, "frozen", False):
            return
        exe = sys.executable
        old = exe + ".old"
        if os.path.exists(old):
            try:
                os.remove(old)
            except OSError:
                pass                      # 被占用就留下,下次再清

        def _worker():
            st, _msg = swap_exe_icon_to_ser()
            if st in ("ok", "skip"):
                try:
                    # 后台线程用独立实例(QSettings 可重入,但不共享对象)
                    settings_store().setValue("icon_patched", "true")
                except Exception:
                    pass
        threading.Thread(target=_worker, daemon=True).start()
    # ---------- 页面切换 ----------
    def go(self, key):
        pg = self._feature_pages.get(key)
        if pg is None or getattr(self, "_page", None) == key:
            return                         # 功能被删掉了就当作没这一页
        self._page = key
        for k, t in self.nav_tabs.items():
            t.set_selected(k == key)
        self.stack.setCurrentWidget(pg)
        self._animate_page(getattr(pg, "_blocks", []))

    # ---------- 外壳给功能模块用的小工具（都容忍"功能不存在"） ----------
    def _card(self, tool_id):
        """取主页上那张工具卡片；home 模块被删掉时返回 None"""
        return getattr(self, "tool_cards", {}).get(tool_id)

    def _set_card_running(self, tool_id, on):
        card = self._card(tool_id)
        if card is not None:
            card.set_running(on)

    def _engine_running(self, name):
        """引擎是否在跑。引擎归功能模块所有，模块不在就没有引擎"""
        eng = getattr(self, name, None)
        return bool(eng is not None and eng.running)

    def _animate_page(self, blocks, base=40, step=46):
        """页面内容的错落入场。effect 必须存到 self 上,否则被 GC。"""
        self._page_effs.clear()
        for i, blk in enumerate(blocks):
            try:
                blk.setGraphicsEffect(None)
            except RuntimeError:
                continue
            eff = RiseFade()
            eff.setOpacity(0.0)
            eff.set_dy(18.0)
            blk.setGraphicsEffect(eff)
            self._page_effs.append(eff)
            QTimer.singleShot(base + i * step,
                              lambda b=blk, e=eff: self._rise_in(b, e))

    def _on_tool(self, tool_id):
        # 有页面就翻过去；只有卡片没有页面的（如"更多工具"）点了不动
        if tool_id in self._feature_pages:
            self.go(tool_id)

    @staticmethod
    def _kv(key, value, key_style=False):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        k = QLabel(key)
        k.setObjectName("kbd" if key_style else "kvKey")
        k.setFixedWidth(84 if not key_style else 66)
        k.setAlignment(Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(k)
        v = QLabel(value)
        v.setObjectName("kvVal")
        v.setWordWrap(True)
        lay.addWidget(v, 1)
        return w

    def resizeEvent(self, e):
        super().resizeEvent(e)
        r = self._root.rect()
        for name in ("countdown", "splash"):
            ov = getattr(self, name, None)
            if ov is not None:
                ov.setGeometry(r)

    @staticmethod
    def _field(text):
        l = QLabel(text)
        l.setObjectName("fieldLabel")
        return l

    @staticmethod
    def _title(text):
        l = QLabel(text)
        l.setObjectName("cardTitle")
        return l

    # ---------- 窗口拖动 / 边缘缩放(无边框窗口需自己实现) ----------
    RESIZE_MARGIN = 7
    TITLE_H = 48

    def _edge_at(self, pos):
        w, h = self.width(), self.height()
        m = self.RESIZE_MARGIN
        e = None
        if pos.x() <= m:
            e = Qt.Edge.LeftEdge
        elif pos.x() >= w - m:
            e = Qt.Edge.RightEdge
        if pos.y() <= m:
            e = Qt.Edge.TopEdge if e is None else e | Qt.Edge.TopEdge
        elif pos.y() >= h - m:
            e = Qt.Edge.BottomEdge if e is None else e | Qt.Edge.BottomEdge
        return e

    # ---------- 边缘缩放:交给系统命中测试(自带缩放光标) ----------
    def hit_test_code(self, lparam):
        """由 WM_NCHITTEST 的 lParam(屏幕坐标)算出 HTxxx;非边缘返回 0"""
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        g = self.geometry()
        m = self.RESIZE_MARGIN
        left = x < g.left() + m
        right = x >= g.right() - m + 1
        top = y < g.top() + m
        bottom = y >= g.bottom() - m + 1
        if top and left:
            return _HT["topleft"]
        if top and right:
            return _HT["topright"]
        if bottom and left:
            return _HT["bottomleft"]
        if bottom and right:
            return _HT["bottomright"]
        if left:
            return _HT["left"]
        if right:
            return _HT["right"]
        if top:
            return _HT["top"]
        if bottom:
            return _HT["bottom"]
        return 0

    def nativeEvent(self, eventType, message):
        try:
            if (eventType == b"windows_generic_MSG" and not self._is_max
                    and self.isVisible()):
                msg = ctypes.cast(int(message),
                                  ctypes.POINTER(_MSG)).contents
                if msg.message == WM_NCHITTEST:
                    code = self.hit_test_code(msg.lParam)
                    if code:
                        return True, code
        except Exception:
            pass
        try:
            return super().nativeEvent(eventType, message)
        except Exception:
            return False, 0

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self._is_max:
            wh = self.windowHandle()
            edges = self._edge_at(e.position().toPoint())
            if edges is not None and wh is not None:
                try:
                    wh.startSystemResize(edges)
                    return
                except Exception:
                    pass
            if e.position().y() < self.TITLE_H and wh is not None:
                wh.startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton
                and e.position().y() < self.TITLE_H):
            self._toggle_max()
            return
        super().mouseDoubleClickEvent(e)

    # ---------- 热键 ----------
    def _apply_hotkeys(self):
        """按当前设置(重新)注册全局热键。

        注意:keyboard 的回调跑在它自己的监听线程里,不是 Qt 主线程 ——
        所以不能在里面用 QTimer.singleShot,必须 emit 跨线程信号让 Qt 排队。
        """
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:  # noqa: BLE001
            pass
        for what, name in (("start", self._hk_start), ("stop", self._hk_stop)):
            try:
                keyboard.add_hotkey(name,
                                    lambda w=what: self.sig_hotkey.emit(w))
            except Exception as e:  # noqa: BLE001
                print(f"[hotkey] {name} 注册失败: {e}")

    def _on_hotkey(self, what):
        """主线程槽:执行热键动作。

        F6/F7 是「当前这一页工具」的起停键 —— 谁来响应由功能模块自己在
        META["hotkeys"] 里声明（键盘连按页 -> 驱动键盘连按，其余 -> 连点器）。
        功能模块被删掉时对应的处理函数就不存在，这时退回到连点器；
        连点器也没了就当没按，只提示一句，绝不抛异常。
        按键改绑是开关式的，不需要热键。
        """
        slot = _PAGE_HOTKEYS.get(getattr(self, "_page", None), {}).get(what)
        fn = getattr(self, slot, None) if slot else None
        if fn is None:
            fn = getattr(self, f"on_{what}", None)   # 退回鼠标连点器
        if fn is None:
            self._set_status("这个功能不在（apps\\ 里被删了？）", "#ffd43b")
            return
        fn()

    @staticmethod
    def _to_int(s, default=0, lo=None, hi=None):
        try:
            v = int(str(s).strip())
            if lo is not None and v < lo:
                v = lo
            if hi is not None and v > hi:
                v = hi
            return v
        except Exception:
            return default

    def _set_status(self, text, color=None):
        """外壳级别的提示行。

        状态标签由连点器页提供，所以连点器模块被删掉时这里就没人接 ——
        直接静默丢掉，不能因为"少了个标签"把别的功能一起拖崩。
        """
        lab = getattr(self, "status_label", None)
        if lab is None:
            return
        try:
            lab.setText(text)
            lab.setStyleSheet(f"color:{color};" if color else "")
        except RuntimeError:               # 控件已被销毁
            pass

    def closeEvent(self, e):
        try:
            self._save_geometry()
            for name in ("macro", "kbrep"):     # 引擎归功能模块所有，可能在
                eng = getattr(self, name, None)  # 模块被删掉后就是 None
                if eng is not None:
                    eng.stop()
            unhook = getattr(self, "_unhook_remaps", None)
            if unhook is not None:
                unhook()                   # 退出前摘掉全局改键,别留下幽灵映射
            keyboard.unhook_all_hotkeys()
        finally:
            super().closeEvent(e)


def main():
    report_load_errors()          # 装载失败的功能打到 stderr,不影响启动
    _migrate_legacy_settings()    # 1.2.x 的配置搬到 Pivot 键下(只搬一次)
    _migrate_wallpaper_dir()      # 壁纸目录同步搬一份
    app = QApplication(sys.argv)
    app.setFont(QFont(_pick_font(), 9))
    app.setStyleSheet(QSS)

    ico = _res_path(os.path.join("icon", "app.ico"))
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))

    w = App()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
