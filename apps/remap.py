# -*- coding: utf-8 -*-
"""枢功能模块 · 按键改绑

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
    HotkeyButton,
    PillButton,
    ToggleSwitch,
    fmt_key_name,
)



META = {
    'id': 'remap',
    'name': '按键改绑',
    'nav': '按键改绑',
    'order': 40,
    'card': True,
    'desc': '把 4 映射成 T · 全局按键重定向',
    'icon': 'remap',
    'accent': '#ffb86b',
    'ready': True,
    'builder': '_build_remap',
    'state': 'page_remap',
}


class Feature:
    """按键改绑功能页（混入 App：方法里的 self 就是 App 实例）。"""

    def _build_remap(self):
        # 状态与持久化都跟着功能走
        self._remap = {}
        self._remap_on = False
        self._remap_handles = {}
        self._load_remaps()
        pg = QWidget()
        outer = QVBoxLayout(pg)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(11)

        # ================= 上排:新增映射 + 开关 =================
        top = QHBoxLayout()
        top.setSpacing(11)

        add_p, al = self._panel(spacing=10, margins=(20, 14, 20, 16))
        al.addWidget(self._title("新增映射"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._field("源键"))
        self.rm_src = HotkeyButton("4")
        self.rm_src.capturing.connect(self._remap_capture)
        # 控件自己会存录到的键（见 HotkeyButton.keyPressEvent），这里再显式
        # 回写一次、顺手给个反馈。1.2.6 首版正是因为**没连 changed**（而当时
        # 控件也不自己存），两个框永远停在默认的 4 / T —— 用户以为"只能改 4 和 t"。
        self.rm_src.changed.connect(self._on_remap_captured)
        row.addWidget(self.rm_src)
        arrow = QLabel("→")
        arrow.setObjectName("kbd")
        arrow.setFixedSize(32, 30)
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(arrow)
        self.rm_dst = HotkeyButton("t")
        self.rm_dst.capturing.connect(self._remap_capture)
        self.rm_dst.changed.connect(self._on_remap_captured)
        row.addWidget(self.rm_dst)
        row.addStretch()
        self.rm_add_btn = PillButton("添加", "primary")
        self.rm_add_btn.setObjectName("startBtn")
        self.rm_add_btn.setFixedSize(84, 32)
        self.rm_add_btn.clicked.connect(self._remap_add)
        row.addWidget(self.rm_add_btn)
        al.addLayout(row)

        note = QLabel("点按键框进入录制，再按任意一个新键即可（Esc 取消）。"
                      "框里的 4 / T 只是默认示例，随便改。例：源键 4 → 目标键 T"
                      " —— 开启后按 4 等于按 T，按 T 仍然是 T。")
        note.setObjectName("pageHint")
        note.setWordWrap(True)
        al.addWidget(note)
        top.addWidget(add_p, 3)

        sw_p, wl = self._panel(spacing=10, margins=(20, 14, 20, 16))
        wl.addWidget(self._title("开关"))
        srow = QHBoxLayout()
        srow.setSpacing(9)
        srow.addWidget(self._field("启用按键改绑"))
        srow.addStretch()
        self.rm_sw = ToggleSwitch()
        self.rm_sw.setChecked(self._remap_on, animate=False)
        self.rm_sw.toggled.connect(self._on_remap_toggle)
        srow.addWidget(self.rm_sw)
        wl.addLayout(srow)
        self.rm_state = QLabel("")
        self.rm_state.setObjectName("kvVal")
        self.rm_state.setWordWrap(True)
        wl.addWidget(self.rm_state)
        warn = QLabel("映射是全局的，对所有程序生效。开启后本程序的输入框里"
                      "按 4 也会变成 T —— 填数字前建议先关掉；要作用在"
                      "管理员权限的窗口上，本程序也需以管理员运行。")
        warn.setObjectName("pageHint")
        warn.setWordWrap(True)
        wl.addWidget(warn)
        wl.addStretch(1)
        top.addWidget(sw_p, 2)
        outer.addLayout(top)

        # ================= 下排:映射表 =================
        map_p, ml = self._panel(spacing=9, margins=(20, 14, 20, 16))
        mhead = QHBoxLayout()
        mhead.addWidget(self._title("映射表"))
        mhead.addStretch()
        self.rm_hint = QLabel("")
        self.rm_hint.setObjectName("pageHint")
        mhead.addWidget(self.rm_hint)
        self.rm_clr_btn = PillButton("清空", "glass")
        self.rm_clr_btn.setObjectName("coordBtn")
        self.rm_clr_btn.setFixedSize(56, 26)
        self.rm_clr_btn.clicked.connect(self._remap_clear)
        mhead.addWidget(self.rm_clr_btn)
        ml.addLayout(mhead)

        self.rm_empty = QLabel("还没有映射 —— 在上面选好「源键 → 目标键」再点添加")
        self.rm_empty.setObjectName("pageHint")
        self.rm_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(self.rm_empty)

        rhost = QWidget()
        rhost.setObjectName("rmListHost")
        self.rm_list = QVBoxLayout(rhost)
        self.rm_list.setContentsMargins(0, 0, 0, 0)
        self.rm_list.setSpacing(6)
        self.rm_list.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rm_scroll = QScrollArea()
        self.rm_scroll.setObjectName("wpScroll")
        self.rm_scroll.setWidgetResizable(True)
        self.rm_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rm_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rm_scroll.setWidget(rhost)
        self._glass_scroll(self.rm_scroll)
        ml.addWidget(self.rm_scroll, 1)
        outer.addWidget(map_p, 1)

        # map_p 含 QScrollArea,只让右侧两栏做入场动画
        pg._blocks = [add_p, sw_p]
        self._remap_rebuild()
        self._sync_remap_state()
        return pg

    def _remap_rebuild(self):
        while self.rm_list.count():
            it = self.rm_list.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        items = list(self._remap.items())
        self.rm_empty.setVisible(not items)
        self.rm_scroll.setVisible(bool(items))
        hotkeys = (self._hk_start, self._hk_stop)
        for src, dst in items:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(7)
            s = QLabel(fmt_key_name(src))
            s.setObjectName("kbd")
            s.setFixedSize(74, 30)
            s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if src in hotkeys:
                s.setStyleSheet("color:#ffb86b;")
            rl.addWidget(s)
            ar = QLabel("→")
            ar.setObjectName("pageHint")
            ar.setFixedSize(24, 30)
            ar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(ar)
            d = QLabel(fmt_key_name(dst))
            d.setObjectName("kbd")
            d.setFixedSize(74, 30)
            d.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(d)
            rl.addSpacing(4)
            rm = PillButton("移除", "glass")
            rm.setObjectName("coordBtn")
            rm.setFixedSize(52, 27)
            rm.clicked.connect(lambda _c=False, kk=src: self._remap_remove(kk))
            rl.addWidget(rm)
            rl.addStretch()
            self.rm_list.addWidget(row)

    def _sync_remap_state(self):
        n = len(self._remap)
        if not n:
            self.rm_state.setText("未配置映射")
        elif self._remap_on:
            self.rm_state.setText(f"已启用 · 生效 {n} 条")
        else:
            self.rm_state.setText(f"已配置 {n} 条 · 未启用")
        if getattr(self, "rm_hint", None) is None:
            return
        clash = [s for s in self._remap if s in (self._hk_start, self._hk_stop)]
        if clash:
            names = "、".join(fmt_key_name(c) for c in clash)
            self.rm_hint.setText(f"⚠ 源键 {names} 与全局热键撞车，热键可能按不出来")
        else:
            self.rm_hint.setText("")

    def _load_remaps(self):
        raw = self._settings.value("remap_map", "")
        data = {}
        if raw:
            try:
                data = json.loads(raw)
            except Exception:  # noqa: BLE001
                data = {}
        if isinstance(data, dict):
            self._remap = {str(k): str(v) for k, v in data.items()
                           if isinstance(k, str) and isinstance(v, str)
                           and k and v}
        self._remap_on = str(
            self._settings.value("remap_on", "false")) == "true"

    def _save_remaps(self):
        self._settings.setValue("remap_map", json.dumps(self._remap,
                                                        ensure_ascii=False))
        self._settings.setValue("remap_on",
                                "true" if self._remap_on else "false")

    def _unhook_remaps(self):
        for src, handle in list(self._remap_handles.items()):
            try:
                keyboard.unhook(handle)
            except Exception:  # noqa: BLE001
                pass
            self._remap_handles.pop(src, None)

    def _apply_remaps(self):
        """按当前映射表 + 开关状态(重)注册全局改键。

        用 keyboard.remap_key:它在 src 的按下/抬起时改发 dst 并吞掉原键,
        只挂在 src 上 —— 所以按 dst 本身不受影响(按 T 仍然出 T)。
        注意 hook_key 走的是 _listener.blocking_keys,和 add_hotkey 的
        blocking_hotkeys 不是同一份状态,unhook_all_hotkeys() 不会误伤它。
        """
        self._unhook_remaps()
        if not self._remap_on:
            return
        for src, dst in self._remap.items():
            try:
                self._remap_handles[src] = keyboard.remap_key(src, dst)
            except Exception as e:  # noqa: BLE001
                print(f"[remap] {src} -> {dst} 注册失败: {e}")

    def _remap_capture(self, active):
        """录制源键/目标键期间临时摘掉全部映射 —— 否则要捕获的源键会被
        自己的映射吞掉,框里永远录不进去。"""
        if active:
            self._unhook_remaps()
        else:
            self._apply_remaps()

    def _on_remap_captured(self, name):
        """某个录制框录完了 —— 回写值并提示"待添加的是哪一对"。

        控件本身已经存好了录到的键,这里再 set_value 一次是显式契约:
        谁也别指望"使用方一定会连 changed",两处都写才不会再出现
        "框里录不进去"这种只有真人点一遍才会发现的问题。
        """
        b = self.sender()
        if b is not None:
            b.set_value(name)
        self._remap_feedback(
            f"待添加：{fmt_key_name(self.rm_src.value())} → "
            f"{fmt_key_name(self.rm_dst.value())}", "#4da3ff")

    def _remap_add(self):
        src = self.rm_src.value().strip().lower()
        dst = self.rm_dst.value().strip().lower()
        if not src or not dst:
            self._remap_feedback("源键与目标键都要先录一个键", "#ffd43b")
            return
        if "+" in src or "+" in dst:
            self._remap_feedback("只支持单键映射，不要带 Ctrl / Shift 等修饰键",
                                 "#ffd43b")
            return
        if src == dst:
            self._remap_feedback("源键和目标键是一样的，映射没有意义", "#ffd43b")
            return
        if src in self._remap and self._remap[src] == dst:
            self._remap_feedback(f"{fmt_key_name(src)} → "
                                 f"{fmt_key_name(dst)} 已经存在了", "#ffd43b")
            return
        self._remap[src] = dst
        self._save_remaps()
        self._apply_remaps()
        self._remap_rebuild()
        self._sync_remap_state()
        self._remap_feedback(f"已添加 {fmt_key_name(src)} → "
                             f"{fmt_key_name(dst)}", "#4da3ff")

    def _remap_remove(self, src):
        self._remap.pop(src, None)
        self._save_remaps()
        self._apply_remaps()
        self._remap_rebuild()
        self._sync_remap_state()
        self._remap_feedback(f"已移除 {fmt_key_name(src)} 的映射", "#4da3ff")

    def _remap_clear(self):
        if not self._remap:
            return
        self._remap.clear()
        self._save_remaps()
        self._apply_remaps()
        self._remap_rebuild()
        self._sync_remap_state()
        self._remap_feedback("映射表已清空", "#4da3ff")

    def _remap_feedback(self, text, color=None):
        if getattr(self, "rm_hint", None) is not None:
            self.rm_hint.setText(text)
            self.rm_hint.setStyleSheet(f"color:{color};" if color else "")

    def _on_remap_toggle(self, on):
        self._remap_on = bool(on)
        self._save_remaps()
        self._apply_remaps()
        self._sync_remap_state()
        if self._remap_on and not self._remap:
            self._remap_feedback("开关已开，但还没有任何映射", "#ffd43b")
        else:
            n = len(self._remap)
            self._remap_feedback(
                f"按键改绑已{'启用' if on else '关闭'}"
                + (f" · {n} 条映射生效中" if on else ""),
                "#4da3ff" if on else None)
