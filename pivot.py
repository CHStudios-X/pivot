# -*- coding: utf-8 -*-
r"""
枢 Pivot —— 外壳（Liquid Glass / iOS 26 风格）

  源码\pivot.py         外壳：窗口骨架、闪屏、标题栏、底栏、热键，
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
import time
from ctypes import wintypes

import pyautogui
import keyboard  # 全局热键

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, Signal,
    QPointF, QPoint, QRectF, QRect, QSize, QSettings,
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient,
    QConicalGradient,
    QFontDatabase, QFontMetricsF, QPainterPath, QCursor, QIcon, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QProgressBar,
    QGraphicsOpacityEffect, QStackedWidget, QSlider, QScrollArea,
)

from pivot_kit import (  # noqa: F401  (一批名字只为兼容旧引用与测试脚本)
    APP_NAME, APP_NAME_EN, APP_VER, STUDIO_NAME, QSS,
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

FOOTER_MARK_H = 16        # 底栏标记主字高(1.2.3 为 12,用户要求加大)


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
    """固定尺寸的出品方标记(底栏 / 设置页用)。

    纯展示控件:不响应鼠标,没有点击反馈 —— 它只是署名,不是按钮。
    """

    def __init__(self, height=12, alpha=150, parent=None):
        super().__init__(parent)
        self._h = height
        self._a = alpha
        self.setFixedHeight(int(height * 1.9) + 2)
        self.setFixedWidth(studio_mark_widget_width(height))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        draw_studio_mark(p, self.width() / 2.0, self.height() / 2.0, self._h,
                         max_width=self.width() - 8.0,
                         # 副字比传入值略亮一档 —— 12px 下再按比例压暗就糊成灰条了
                         letter_alpha=min(255, int(self._a * 1.08)),
                         mark_alpha=min(255, int(self._a * 1.75)))


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
    """启动闪屏:纯字母 wordmark 的入场 —— 主字弹出 + 副字擦出 + 柔光脉冲 + 圆环 spinner。

    只用一个 0→1 的 progress 动画驱动,paintEvent 内按时间段自己算缓动 ——
    比堆十几个并行动画好调，也不会出现"删 effect 时还在跑"的时序问题。

    时间轴(占总时长的比例):
      0.00 背景蒙层淡入
      0.10 主字 CH 带一点回弹弹出
      0.30 副字 Studios 从主字右侧擦出(两段间距同时展开)
      0.46 主字亮起一圈柔光脉冲
      0.54 底部圆环 spinner 开始转(顺时针,一直转到淡出结束)
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

        # ---- 加载指示:圆环 spinner ----
        # 这里原来是条走到底就停住的横向光带,看着像"下载进度";改成圆环后
        # 语义更准(只是在等启动,不是有确定进度)。仍然只由 _t 驱动,不新建
        # 动画对象 —— 和这套闪屏"单进度 + 绘制内算缓动"的做法一致。
        bp = _clamp01((t - 0.54) / 0.46)
        if bp > 0.0:
            a_in = _ease_out_cubic(min(1.0, bp / 0.22))    # 前段淡入,别硬出现
            rr = max(9.0, mh * 0.62)
            th = max(1.9, rr * 0.28)
            bin_cy = cy + mh * 1.78 + rr                   # 顶上贴着原光带位置
            box = QRectF(cx - rr, bin_cy - rr, rr * 2.0, rr * 2.0)
            p.setBrush(Qt.BrushStyle.NoBrush)

            # 底环:一圈很淡的白,给圆环一条「轨道」,转起来才看得出在转
            p.setPen(QPen(QColor(255, 255, 255, int(34 * a_in)), th,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawEllipse(box)

            # 弧段:锥形渐变让尾端透明、头部最亮。head 角度随时间递减,
            # 所以视觉上是**顺时针**转(load 图标的通行方向)。
            # 色标按角度比例布点,别把亮点全挤在最后 10% —— 那样看着只是一小截。
            span = 140.0
            # 速度:闪屏 0.54→1.0 约 1.1 秒转 0.46*3.6 ≈ 1.7 圈 -> 每圈约 0.66 秒。
            # 试过 7.0(3 圈/秒),太快,看着像在闪;这个档位是慢慢悠悠转完。
            head = -90.0 - 360.0 * 3.6 * t
            tail = head - span
            cg = QConicalGradient(QPointF(box.center()), tail)
            cg.setColorAt(0.000, QColor(167, 139, 250, int(58 * a_in)))   # 尾:压暗但不消失
            cg.setColorAt(0.060, QColor(150, 160, 252, int(112 * a_in)))
            cg.setColorAt(0.150, QColor(122, 178, 255, int(188 * a_in)))
            cg.setColorAt(0.240, QColor(126, 176, 255, int(234 * a_in)))
            cg.setColorAt(0.270, QColor(126, 176, 255, int(250 * a_in)))  # 头最亮
            cg.setColorAt(0.276, QColor(126, 176, 255, 0))
            p.setPen(QPen(QBrush(cg), th, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(box, int(tail * 16), int(span * 16))


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
        ver = QLabel(f"v{APP_VER}")
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
        # 出品方标记(取代了原来的用户胶囊)。1.2.4 起加大一档。
        self.studio_mark = StudioMark(FOOTER_MARK_H, 150)
        self.studio_mark.setToolTip(f"Made by {STUDIO_NAME}")
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
