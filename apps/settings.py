# -*- coding: utf-8 -*-
"""枢功能模块 · 设置

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

import pyautogui

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
    APP_NAME,
    APP_NAME_EN,
    APP_VER,
    HotkeyButton,
    PillButton,
    STUDIO_NAME,
    ToggleSwitch,
    fmt_hotkey,
)



META = {
    'id': 'settings',
    'name': '设置',
    'nav': '设置',
    'order': 60,
    'card': False,
    'desc': '',
    'icon': 'settings',
    'accent': '#8a93a8',
    'ready': True,
    'builder': '_build_settings',
    'state': 'page_settings',
}


class Feature:
    """设置功能页（混入 App：方法里的 self 就是 App 实例）。"""

    def _build_settings(self):
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)

        about, al = self._panel(spacing=11, margins=(20, 16, 20, 18))
        al.addWidget(self._title("关于"))
        for k, v in (("名称", f"{APP_NAME} {APP_NAME_EN}"),
                     ("版本", APP_VER),
                     ("出品", STUDIO_NAME)):
            al.addWidget(self._kv(k, v))
        lay.addWidget(about)

        hk, hkl = self._panel(spacing=10, margins=(20, 16, 20, 18))
        head = QHBoxLayout()
        head.addWidget(self._title("热键"))
        head.addStretch()
        tip = QLabel("点一下按键框 → 再按新键即可改绑（Esc 取消）")
        tip.setObjectName("pageHint")
        head.addWidget(tip)
        hkl.addLayout(head)

        self.hotkey_btns = {}
        for key, label, default in (("start", "开始（连点 / 连按）", "f6"),
                                    ("stop", "停止（连点 / 连按）", "f7")):
            row = QHBoxLayout()
            row.setSpacing(12)
            btn = HotkeyButton(default)
            btn.changed.connect(lambda n, k=key: self._on_hotkey_changed(k, n))
            self.hotkey_btns[key] = btn
            row.addWidget(btn, 0)
            txt = QLabel(f"{label}{'（含 3 秒倒计时）' if key == 'start' else ''}")
            txt.setObjectName("kvVal")
            row.addWidget(txt, 1)
            hkl.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(12)
        lock = QLabel("左上角")
        lock.setObjectName("kbd")
        lock.setFixedWidth(112)
        lock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(lock, 0)
        self.failsafe_sw = ToggleSwitch()
        self.failsafe_sw.setChecked(bool(pyautogui.FAILSAFE), animate=False)
        self.failsafe_sw.toggled.connect(self._on_failsafe)
        row.addWidget(self.failsafe_sw)
        note2 = QLabel("把鼠标甩到屏幕左上角紧急中止（关掉就没有撤销手段了）")
        note2.setObjectName("pageHint")
        row.addWidget(note2, 1)
        hkl.addLayout(row)

        note = QLabel("全局热键需要管理员权限才能生效；"
                      "安装时勾选「以管理员身份运行」即可。")
        note.setObjectName("pageHint")
        note.setWordWrap(True)
        hkl.addWidget(note)
        lay.addWidget(hk)

        bg, bl = self._panel(spacing=11, margins=(20, 16, 20, 18))
        brow = QHBoxLayout()
        brow.addWidget(self._title("外观"))
        brow.addStretch()
        go_btn = PillButton("壁纸设置  →", "glass")
        go_btn.setObjectName("coordBtn")
        go_btn.setFixedSize(126, 34)
        go_btn.clicked.connect(lambda: self.go("appearance"))
        brow.addWidget(go_btn)
        bl.addLayout(brow)
        self.bg_name_row = self._kv("当前壁纸", "-")
        bl.addWidget(self.bg_name_row)
        lay.addWidget(bg)
        lay.addStretch(1)

        pg._blocks = [about, hk, bg]
        return pg

    def _on_hotkey_changed(self, which, name):
        """录制完成:写设置、必要时与另一个热键互换、重新注册"""
        other = "stop" if which == "start" else "start"
        if name == getattr(self, f"_hk_{other}"):
            # 撞车就互换,不让两个功能共用一个键
            getattr(self, f"hotkey_btns")[other].set_value(
                getattr(self, f"_hk_{which}"))
            setattr(self, f"_hk_{other}", getattr(self, f"_hk_{which}"))
            self._settings.setValue(f"hotkey_{other}",
                                    getattr(self, f"_hk_{other}"))
        setattr(self, f"_hk_{which}", name)
        self._settings.setValue(f"hotkey_{which}", name)
        # 按钮也要跟着显示新键 —— 录制结束时它先把文字还原成了旧值
        btn = getattr(self, "hotkey_btns", {}).get(which)
        if btn is not None:
            btn.set_value(name)
        self._apply_hotkeys()
        self._set_status(f"热键已改为 {fmt_hotkey(name)}", "#4da3ff")

    def _on_failsafe(self, on):
        pyautogui.FAILSAFE = bool(on)
        self._settings.setValue("failsafe", "true" if on else "false")
        self._set_status("左上角紧急中止已" + ("开启" if on else "关闭"),
                         None if on else "#ffd43b")
