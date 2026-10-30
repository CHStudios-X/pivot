# -*- coding: utf-8 -*-
"""枢功能模块 · 键盘连按

契约（外壳靠这些约定装载本模块）：
  META     功能元信息：id / name / nav(底栏文案) / card(主页是否出卡片) /
           order(排序) / builder(构建页面的方法名) / state(页面挂在哪个属性) /
           hotkeys(本页上 F6F7 该驱动谁)
  Feature  混入 App 的类。方法里的 self 就是 App 实例，所以这里不写
           __init__，只用 self.xxx 访问外壳能力（_panel / _title / _kv /
           _set_status / _glass_scroll / _to_int / go ...）。

删除本文件后：底栏与主页少了这一项、对应热键失效，其余功能照常工作。
"""

import ctypes
import json
import math
import os
import sys
import threading
import time
from ctypes import wintypes

import keyboard

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

from pivot_kit import (
    AnimatedCounter,
    PillButton,
    PulseDot,
    fmt_key_name,
)

class KeyRepeater:
    """键盘连按引擎:按顺序把序列里每个键发送 N 次。

    与 AutoClicker 分开实现 —— 鼠标侧走 pyautogui(带左上角 FAILSAFE),
    键盘侧走 keyboard.send(单键 press+release),中止条件、状态文案、
    失败模式都不一样,硬塞进一个类只会互相牵制。
    线程模型保持一致:后台 daemon 线程跑循环,通过回调把进度抛回调用方
    (调用方负责 emit 跨线程 Signal,由 Qt 排队到主线程)。
    """

    def __init__(self):
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        self.sent = 0
        self.total = 0
        self._last_notify = 0.0

    def start(self, sequence, interval_ms, countdown_sec=3,
              on_count_update=None, on_status_update=None):
        """sequence = [(键盘键名, 次数), ...];返回是否成功启动"""
        if self.running or not sequence:
            return False
        self.stop_event.clear()
        self.sent = 0
        self.total = sum(int(n) for _k, n in sequence)
        self.running = True
        self._last_notify = 0.0
        self._on_count_update = on_count_update
        self._on_status_update = on_status_update
        self.thread = threading.Thread(
            target=self._run,
            args=(list(sequence), interval_ms, countdown_sec),
            daemon=True,
        )
        self.thread.start()
        return True

    def stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.running = False
        if self._on_status_update:
            self._on_status_update("已停止")

    def _sleep(self, sec):
        """可被 stop() 打断的睡眠;返回 True 表示已收到停止请求"""
        end = time.monotonic() + max(0.0, sec)
        while True:
            if self.stop_event.is_set():
                return True
            left = end - time.monotonic()
            if left <= 0:
                return False
            time.sleep(min(0.02, left))

    def _run(self, sequence, interval_ms, countdown_sec):
        interval_sec = max(0.001, interval_ms / 1000.0)
        for i in range(countdown_sec, 0, -1):
            if self.stop_event.is_set():
                return
            if self._on_status_update:
                self._on_status_update(f"countdown:{i}")
            if self._sleep(1.0):
                return

        if self._on_status_update:
            self._on_status_update("running")

        for key, count in sequence:
            for _ in range(int(count)):
                if self.stop_event.is_set():
                    self.running = False
                    return
                try:
                    keyboard.send(key)      # 单键 press + release
                except Exception as e:  # noqa: BLE001
                    if self._on_status_update:
                        self._on_status_update(f"error:{e}")
                    self.running = False
                    return
                self.sent += 1
                if self._on_count_update:
                    now = time.monotonic()
                    # 与鼠标侧同样的节流:间隔可低至 1ms,不能每次都推 UI
                    if now - self._last_notify >= 0.05:
                        self._last_notify = now
                        self._on_count_update(self.sent)
                if self._sleep(interval_sec):
                    self.running = False
                    return

        if self._on_count_update:
            self._on_count_update(self.sent)
        if self._on_status_update:
            self._on_status_update("done")
        self.running = False


KB_LAYOUT = [
    [("F1", "f1", 1.25), ("F2", "f2", 1.25), ("F3", "f3", 1.25),
     ("F4", "f4", 1.25), ("F5", "f5", 1.25), ("F6", "f6", 1.25),
     ("F7", "f7", 1.25), ("F8", "f8", 1.25), ("F9", "f9", 1.25),
     ("F10", "f10", 1.25), ("F11", "f11", 1.25), ("F12", "f12", 1.25)],
    [("`", "`", 1), ("1", "1", 1), ("2", "2", 1), ("3", "3", 1),
     ("4", "4", 1), ("5", "5", 1), ("6", "6", 1), ("7", "7", 1),
     ("8", "8", 1), ("9", "9", 1), ("0", "0", 1), ("-", "-", 1),
     ("=", "=", 1), ("⌫", "backspace", 2)],
    [("Tab", "tab", 1.5), ("Q", "q", 1), ("W", "w", 1), ("E", "e", 1),
     ("R", "r", 1), ("T", "t", 1), ("Y", "y", 1), ("U", "u", 1),
     ("I", "i", 1), ("O", "o", 1), ("P", "p", 1), ("[", "[", 1),
     ("]", "]", 1), ("\\", "\\", 1.5)],
    [("Caps", "caps lock", 1.75), ("A", "a", 1), ("S", "s", 1),
     ("D", "d", 1), ("F", "f", 1), ("G", "g", 1), ("H", "h", 1),
     ("J", "j", 1), ("K", "k", 1), ("L", "l", 1), (";", ";", 1),
     ("'", "'", 1), ("Enter", "enter", 2.25)],
    [("Shift", "shift", 2.25), ("Z", "z", 1), ("X", "x", 1), ("C", "c", 1),
     ("V", "v", 1), ("B", "b", 1), ("N", "n", 1), ("M", "m", 1),
     (",", ",", 1), (".", ".", 1), ("/", "/", 1),
     ("Shift", "shift", 2.75)],
    [("Ctrl", "ctrl", 1.25), ("Win", "windows", 1.25), ("Alt", "alt", 1.25),
     ("Space", "space", 6.25), ("Alt", "alt", 1.25),
     ("Win", "windows", 1.25), ("Menu", "menu", 1.25), ("Ctrl", "ctrl", 1.25)],
    [("←", "left", 1.5), ("↑", "up", 1.5), ("↓", "down", 1.5),
     ("→", "right", 1.5), ("Ins", "insert", 1.5), ("Del", "delete", 1.5),
     ("Home", "home", 1.5), ("End", "end", 1.5), ("PgUp", "page up", 1.5),
     ("PgDn", "page down", 1.5)],
]


class VirtualKeyboard(QWidget):
    """可点选的虚拟键盘布局图。

    整块键盘按控件当前宽高**等比缩放后居中**:先分别按宽、高各算一个
    列宽 cw,取小的那个,于是窗口怎么拉都不会把键帽拉变形、也不会溢出。
    键位落在一条 15 列的等宽网格上(键宽 = 列数 × cw),所以每行右边缘
    严格对齐 —— 这也是为什么间隙用「键帽内缩」而不是「逐键加间距」:
    后者会因为每行键数不同而让行宽参差。
    """

    changed = Signal()             # 选中集合发生变化

    CW_UNITS = 15.0                # 每行总列数
    ROWS = len(KB_LAYOUT)
    KH_R = 1.16                    # 行高 / 列宽
    INSET_R = 0.055                # 键帽内缩 / 列宽
    MIN_CW = 11.0

    SEL_BG = QColor(126, 224, 255, 205)
    SEL_BD = QColor(190, 244, 255, 240)
    SEL_FG = QColor(6, 26, 36)
    SEL_SUB = QColor(10, 40, 55, 215)
    FG = QColor(255, 255, 255, 228)
    FG_DIM = QColor(255, 255, 255, 178)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(320, 150)
        self._sel = {}             # 键名 -> True(dict 保序,便于回传序列)
        self._counts = {}          # 键名 -> 次数(画在键帽上)
        self._hover = None         # (row, idx)

    # ---------- 选中集合 ----------
    def selected(self):
        """按布局顺序返回选中的键名(同名键去重)"""
        out, seen = [], set()
        for row in KB_LAYOUT:
            for _lbl, kname, _w in row:
                if kname in self._sel and kname not in seen:
                    seen.add(kname)
                    out.append(kname)
        return out

    def set_selected(self, names):
        self._sel = {n: True for n in names}
        self.update()

    def set_counts(self, counts):
        self._counts = dict(counts)
        self.update()

    def clear(self):
        self._sel.clear()
        self._counts.clear()
        self.update()
        self.changed.emit()

    def toggle(self, kname):
        if kname in self._sel:
            self._sel.pop(kname, None)
        else:
            self._sel[kname] = True
        self.update()
        self.changed.emit()

    # ---------- 几何 ----------
    def _layout_rects(self):
        """-> [(row, idx, 键名, 显示文字, QRectF, 列宽 cw)]"""
        w, h = float(self.width()), float(self.height())
        cw = min(w / self.CW_UNITS, h / (self.ROWS * self.KH_R))
        cw = max(self.MIN_CW, cw)
        kh = cw * self.KH_R
        inset = cw * self.INSET_R
        bw = self.CW_UNITS * cw
        bh = self.ROWS * kh
        ox, oy = (w - bw) / 2.0, (h - bh) / 2.0
        rects = []
        for r, row in enumerate(KB_LAYOUT):
            col = 0.0
            for i, (lbl, kname, units) in enumerate(row):
                rects.append((
                    r, i, kname, lbl,
                    QRectF(ox + col * cw + inset, oy + r * kh + inset,
                           units * cw - 2 * inset, kh - 2 * inset),
                    cw,
                ))
                col += units
        return rects

    @staticmethod
    def _hit(rects, pos):
        for r, i, kname, _lbl, rect, _cw in rects:
            if rect.contains(pos):
                return (r, i, kname)
        return None

    # ---------- 绘制 ----------
    def paintEvent(self, _):
        rects = self._layout_rects()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fam = self.font().family()
        for r, i, kname, lbl, rect, cw in rects:
            sel = kname in self._sel
            hov = self._hover == (r, i)
            rad = rect.height() * 0.22
            if sel:
                p.setBrush(self.SEL_BG)
                p.setPen(QPen(self.SEL_BD, max(1.0, cw * 0.03)))
            elif hov:
                p.setBrush(QColor(255, 255, 255, 52))
                p.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
            else:
                p.setBrush(QColor(255, 255, 255, 20))
                p.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
            p.drawRoundedRect(rect, rad, rad)

            cnt = self._counts.get(kname, 0) if sel else 0
            f = QFont(fam)
            f.setPixelSize(max(8, int(min(cw * 0.44, rect.height() * 0.46))))
            f.setWeight(QFont.Weight.DemiBold if sel else QFont.Weight.Medium)
            fm = QFontMetricsF(f)
            avail = rect.width() - max(4.0, cw * 0.16)
            while fm.horizontalAdvance(lbl) > avail and f.pixelSize() > 8:
                f.setPixelSize(f.pixelSize() - 1)
                fm = QFontMetricsF(f)
            p.setFont(f)

            wide = rect.width() > cw * 1.4        # 宽键(修饰键)用暗一档的字
            if cnt > 0:
                # 选中且设了次数:上行键名、下行 ×次数
                top = QRectF(rect.left(), rect.top() + rect.height() * 0.06,
                             rect.width(), rect.height() * 0.54)
                bot = QRectF(rect.left(), rect.top() + rect.height() * 0.52,
                             rect.width(), rect.height() * 0.44)
                p.setPen(QPen(self.SEL_FG, 1))
                p.drawText(top, Qt.AlignmentFlag.AlignCenter, lbl)
                fs = QFont(fam)
                fs.setPixelSize(max(7, int(f.pixelSize() * 0.72)))
                fs.setWeight(QFont.Weight.Bold)
                p.setFont(fs)
                p.setPen(QPen(self.SEL_SUB, 1))
                p.drawText(bot, Qt.AlignmentFlag.AlignCenter, f"×{cnt}")
            else:
                p.setPen(QPen(self.SEL_FG if sel
                              else (self.FG_DIM if wide else self.FG), 1))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, lbl)

    # ---------- 交互 ----------
    def mouseMoveEvent(self, e):
        h = self._hit(self._layout_rects(), e.position())
        k = None if h is None else (h[0], h[1])
        if k != self._hover:
            self._hover = k
            self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            h = self._hit(self._layout_rects(), e.position())
            if h is not None:
                self.toggle(h[2])
                return
        super().mousePressEvent(e)


META = {
    'id': 'keys',
    'name': '键盘连按',
    'nav': '键盘连按',
    'order': 30,
    'card': True,
    'desc': '虚拟键盘选键 · 逐个设定次数 · 一键连按',
    'icon': 'keys',
    'accent': '#7ee0ff',
    'ready': True,
    'builder': '_build_keys',
    'state': 'page_keys',
    'hotkeys': {'start': 'kb_start', 'stop': 'kb_stop'},
}


class Feature:
    """键盘连按功能页（混入 App：方法里的 self 就是 App 实例）。"""

    def _build_keys(self):
        # 引擎与 UI 状态都跟着功能走
        self.kbrep = KeyRepeater()
        self._kb_default = self._to_int(
            self._settings.value("kb_count", 20), 20,
            lo=1, hi=1000000)
        self._kb_counts = {}
        self._kb_total = 0
        self._kb_pending = 0
        self._kb_scheduled = False
        pg = QWidget()
        lay = QHBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)

        # ---------------- 左栏:虚拟键盘 ----------------
        kb_p, kl = self._panel(spacing=10, margins=(18, 14, 18, 14))
        head = QHBoxLayout()
        head.addWidget(self._title("虚拟键盘"))
        head.addStretch()
        hint = QLabel("点键帽选中 / 再点一次取消 · 键帽上会标出次数")
        hint.setObjectName("pageHint")
        head.addWidget(hint)
        kl.addLayout(head)
        self.vkbd = VirtualKeyboard()
        self.vkbd.changed.connect(self._on_kbd_changed)
        kl.addWidget(self.vkbd, 1)
        lay.addWidget(kb_p, 7)

        # ---------------- 右栏 ----------------
        right = QVBoxLayout()
        right.setSpacing(11)

        # --- 已选按键(键名 + 次数 + 移除) ---
        sel_p, sl = self._panel(spacing=9, margins=(18, 14, 18, 16))
        shead = QHBoxLayout()
        shead.setSpacing(8)
        shead.addWidget(self._title("已选按键"))
        shead.addStretch()
        self.kb_count_lbl = QLabel("0 个")
        self.kb_count_lbl.setObjectName("pageHint")
        shead.addWidget(self.kb_count_lbl)
        self.kb_clr_btn = PillButton("清空", "glass")
        self.kb_clr_btn.setObjectName("coordBtn")
        self.kb_clr_btn.setFixedSize(56, 26)
        self.kb_clr_btn.clicked.connect(lambda: self.vkbd.clear())
        shead.addWidget(self.kb_clr_btn)
        sl.addLayout(shead)

        self.kb_empty = QLabel("还没有选键\n点左边的键盘布局图试试")
        self.kb_empty.setObjectName("pageHint")
        self.kb_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.kb_empty)

        host = QWidget()
        host.setObjectName("kbListHost")
        self.kb_list = QVBoxLayout(host)
        self.kb_list.setContentsMargins(0, 0, 0, 0)
        self.kb_list.setSpacing(6)
        self.kb_list.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.kb_scroll = QScrollArea()
        self.kb_scroll.setObjectName("wpScroll")
        self.kb_scroll.setWidgetResizable(True)
        self.kb_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.kb_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.kb_scroll.setMinimumHeight(72)
        self.kb_scroll.setWidget(host)
        self._glass_scroll(self.kb_scroll)
        sl.addWidget(self.kb_scroll, 1)

        foot = QHBoxLayout()
        foot.setSpacing(7)
        foot.addWidget(self._field("全部设为"))
        self.kb_bulk = QLineEdit(str(self._kb_default))
        self.kb_bulk.setFixedSize(62, 30)
        self.kb_bulk.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.addWidget(self.kb_bulk)
        foot.addWidget(self._field("次"))
        bulk_btn = PillButton("应用", "glass")
        bulk_btn.setObjectName("coordBtn")
        bulk_btn.setFixedSize(54, 30)
        bulk_btn.clicked.connect(self._kb_apply_bulk)
        foot.addWidget(bulk_btn)
        foot.addStretch()
        sl.addLayout(foot)
        right.addWidget(sel_p, 1)

        # --- 参数 / 控制台 ---
        par_p, pl = self._panel(spacing=9, margins=(18, 14, 18, 16))
        prow = QHBoxLayout()
        prow.setSpacing(8)
        prow.addWidget(self._field("按下间隔 (ms)"))
        self.kb_interval = QLineEdit(str(self._to_int(
            self._settings.value("kb_interval", 80), 80, lo=1)))
        self.kb_interval.setFixedSize(72, 30)
        self.kb_interval.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prow.addWidget(self.kb_interval)
        prow.addStretch()
        cd = QLabel("起手 3 秒倒计时")
        cd.setObjectName("pageHint")
        prow.addWidget(cd)
        pl.addLayout(prow)

        srow = QHBoxLayout()
        srow.setSpacing(8)
        self.kb_status_dot = PulseDot("#63e6be", 7)
        srow.addWidget(self.kb_status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.kb_status = QLabel("就绪")
        self.kb_status.setObjectName("statusText")
        srow.addWidget(self.kb_status, 1, Qt.AlignmentFlag.AlignVCenter)
        pl.addLayout(srow)

        self.kb_counter = AnimatedCounter(30, Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(self.kb_counter)
        self.kb_progress = QProgressBar()
        self.kb_progress.setObjectName("progress")
        self.kb_progress.setRange(0, 1)
        self.kb_progress.setValue(0)
        self.kb_progress.setTextVisible(False)
        pl.addWidget(self.kb_progress)
        right.addWidget(par_p)

        # --- 开始 / 停止 ---
        kbtn = QHBoxLayout()
        kbtn.setSpacing(11)
        self.kb_start_btn = PillButton("开始  (F6)", "primary")
        self.kb_start_btn.setObjectName("startBtn")
        self.kb_start_btn.setMinimumHeight(46)
        self.kb_start_btn.clicked.connect(self.kb_start)
        kbtn.addWidget(self.kb_start_btn, 3)
        self.kb_stop_btn = PillButton("停止  (F7)", "glass")
        self.kb_stop_btn.setObjectName("stopBtn")
        self.kb_stop_btn.setMinimumHeight(46)
        self.kb_stop_btn.setEnabled(False)
        self.kb_stop_btn.clicked.connect(self.kb_stop)
        kbtn.addWidget(self.kb_stop_btn, 2)
        kbw = QWidget()
        kbw.setLayout(kbtn)
        right.addWidget(kbw)

        tip = QLabel("在本页按 F6 开始连按、F7 停止（热键可在设置页改）")
        tip.setObjectName("tip")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(tip)

        lay.addLayout(right, 4)

        # 含 QScrollArea 的面板不能挂入场动画(Windows 上会崩,见外观页注释)
        pg._blocks = [kb_p, par_p, kbw, tip]
        self._kb_rebuild_list()
        return pg

    def _on_kbd_changed(self):
        """键盘布局图上的选中集合变了:补默认次数、刷新键帽徽标与列表"""
        keys = self.vkbd.selected()
        self._kb_counts = {k: self._kb_counts.get(k, self._kb_default)
                           for k in keys}
        self.vkbd.set_counts(self._kb_counts)
        self._kb_rebuild_list()

    def _kb_rebuild_list(self):
        while self.kb_list.count():
            it = self.kb_list.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.kb_count_edits = {}
        keys = self.vkbd.selected()
        self.kb_count_lbl.setText(f"{len(keys)} 个")
        self.kb_empty.setVisible(not keys)
        self.kb_scroll.setVisible(bool(keys))
        for k in keys:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(7)
            tag = QLabel(fmt_key_name(k))
            tag.setObjectName("kbd")
            tag.setFixedSize(66, 30)
            tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(tag)
            ed = QLineEdit(str(self._kb_counts.get(k, self._kb_default)))
            ed.setFixedSize(62, 30)
            ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ed.textChanged.connect(
                lambda _t, kk=k: self._kb_on_count_changed(kk))
            rl.addWidget(ed)
            rl.addWidget(self._field("次"))
            rl.addStretch()
            rm = PillButton("移除", "glass")
            rm.setObjectName("coordBtn")
            rm.setFixedSize(52, 27)
            rm.clicked.connect(lambda _c=False, kk=k: self.vkbd.toggle(kk))
            rl.addWidget(rm)
            self.kb_list.addWidget(row)
            self.kb_count_edits[k] = ed

    def _kb_on_count_changed(self, k):
        ed = getattr(self, "kb_count_edits", {}).get(k)
        if ed is None:
            return
        v = self._to_int(ed.text(), self._kb_default, lo=1, hi=1000000)
        self._kb_counts[k] = v
        self.vkbd.set_counts(self._kb_counts)

    def _kb_apply_bulk(self):
        keys = self.vkbd.selected()
        if not keys:
            self._kb_set_status("先选键，再统一次数", "#ffd43b")
            return
        v = self._to_int(self.kb_bulk.text(), self._kb_default, lo=1,
                         hi=1000000)
        self._kb_default = v
        self._settings.setValue("kb_count", v)
        for k in keys:
            self._kb_counts[k] = v
        self.vkbd.set_counts(self._kb_counts)
        self._kb_rebuild_list()
        self._kb_set_status(f"{len(keys)} 个键已统一为 {v} 次", "#4da3ff")

    def kb_start(self):
        if self.kbrep.running:
            return
        if self._engine_running("macro"):
            self._kb_set_status("连点器正在运行，先停掉它", "#ffd43b")
            return
        if getattr(self, "_page", None) != "keys":
            self.go("keys")            # 热键触发时先把本页翻出来
        keys = self.vkbd.selected()
        if not keys:
            self._kb_set_status("先点键盘布局图，选至少一个键", "#ffd43b")
            return

        seq = []
        for k in keys:
            ed = self.kb_count_edits.get(k)
            n = self._to_int(ed.text() if ed is not None else "",
                             self._kb_default, lo=1, hi=1000000)
            self._kb_counts[k] = n
            seq.append((k, n))
        interval = self._to_int(self.kb_interval.text(), 80, lo=1, hi=600000)
        self.kb_interval.setText(str(interval))
        self._settings.setValue("kb_interval", interval)
        self._settings.setValue("kb_count", self._kb_default)

        ok = self.kbrep.start(
            seq, interval, countdown_sec=3,
            on_count_update=self.sig_kb_count.emit,
            on_status_update=self.sig_kb_status.emit)
        if not ok:
            return

        self._kb_total = self.kbrep.total
        self._kb_pending = 0
        self._kb_scheduled = False
        self.kb_progress.setRange(0, max(1, self._kb_total))
        self.kb_progress.setValue(0)
        self.kb_counter.set_value(0)
        self.kb_start_btn.setEnabled(False)
        self.kb_stop_btn.setEnabled(True)
        self.kb_status_dot.set_color("#7ee0ff")
        self.kb_status_dot.start_pulse()
        self._kb_set_status("准备中…")
        card = self._card("keys")
        if card is not None:
            card.set_running(True)
        self.countdown.start(3)

    def kb_stop(self):
        self.kbrep.stop()

    def _queue_kb_count(self, c):
        """主线程槽(sig_kb_count 跨线程投递):合并刷新,防事件洪水"""
        self._kb_pending = c
        if not self._kb_scheduled:
            self._kb_scheduled = True
            QTimer.singleShot(0, self._flush_kb_count)

    def _flush_kb_count(self):
        self._kb_scheduled = False
        v = self._kb_pending
        self.kb_counter.set_value(v)
        if self._kb_total > 0:
            self.kb_progress.setValue(min(v, self._kb_total))

    def _handle_kb_status(self, s):
        if s.startswith("countdown:"):
            n = self._to_int(s.split(":", 1)[1], 0)
            self._kb_set_status(f"倒计时 {n} 秒")
            self.countdown.update_to(n)
        elif s == "running":
            self.countdown.finish()
            self._kb_set_status("连按中…", "#7ee0ff")
        elif s == "done":
            self._kb_pending = self.kbrep.sent
            self._flush_kb_count()
            self._kb_reset(f"完成 · 共 {self.kbrep.sent} 次", "#63e6be")
        elif s.startswith("error"):
            self._kb_reset(f"异常: {s.split(':', 1)[1]}", "#ff6b6b")
        elif s == "已停止":
            self._kb_pending = self.kbrep.sent
            self._flush_kb_count()
            self._kb_reset("已停止")

    def _kb_set_status(self, text, color=None):
        self.kb_status.setText(text)
        self.kb_status.setStyleSheet(f"color:{color};" if color else "")

    def _kb_reset(self, text, color=None):
        self._kb_set_status(text, color)
        self.kb_start_btn.setEnabled(True)
        self.kb_stop_btn.setEnabled(False)
        # 进度条常驻显示(避免布局跳动),归位为空白轨道
        self.kb_progress.setRange(0, 1)
        self.kb_progress.setValue(0)
        self._kb_total = 0
        self.kb_status_dot.stop_pulse()
        self.kb_status_dot.set_color("#63e6be")
        card = self._card("keys")
        if card is not None:
            card.set_running(False)
        self.countdown.cancel()
