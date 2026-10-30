# -*- coding: utf-8 -*-
"""枢功能模块 · 主页

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
    ToolCard,
)



META = {
    'id': 'home',
    'name': '主页',
    'nav': '主页',
    'order': 10,
    'card': False,
    'desc': '',
    'icon': 'home',
    'accent': '#4da3ff',
    'ready': True,
    'builder': '_build_home',
    'state': 'page_home',
    'alias': 'home',
}


class Feature:
    """主页功能页（混入 App：方法里的 self 就是 App 实例）。"""

    def _build_home(self):
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)

        # --- Hero ---
        hero, hl = self._panel(spacing=0, margins=(24, 18, 24, 18))
        hrow = QHBoxLayout()
        hrow.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(3)
        t = QLabel(APP_NAME)
        t.setObjectName("heroTitle")
        left.addWidget(t)
        s = QLabel(f"{APP_NAME_EN}  ·  一站式小工具合集")
        s.setObjectName("heroSub")
        left.addWidget(s)
        left.addSpacing(7)
        note = QLabel("连点器支持自定义间隔、次数与固定坐标；"
                      "全局热键 F6 开始、F7 停止，运行中随时可中止。")
        note.setObjectName("heroNote")
        note.setWordWrap(True)
        left.addWidget(note)
        left.addStretch(1)
        hrow.addLayout(left, 1)

        vr = QVBoxLayout()
        vr.setSpacing(0)
        vr.addStretch(1)
        vlab = QLabel(self._disp_ver)
        vlab.setObjectName("verBig")
        self._home_ver_lbl = vlab
        vlab.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)
        vr.addWidget(vlab)
        vtag = QLabel("当前版本")
        vtag.setObjectName("userRole")
        vtag.setAlignment(Qt.AlignmentFlag.AlignRight)
        vr.addWidget(vtag)
        vr.addStretch(1)
        hrow.addLayout(vr, 0)
        hl.addLayout(hrow)
        lay.addWidget(hero)

        # --- 工具网格 ---
        tools_p, tl = self._panel(spacing=12, margins=(20, 16, 20, 18))
        head = QHBoxLayout()
        head.addWidget(self._title("工具"))
        head.addStretch()
        ready_n = sum(1 for t in self.tool_registry if t["ready"])
        hint = QLabel(f"{ready_n} / {len(self.tool_registry)} 可用")
        hint.setObjectName("pageHint")
        head.addWidget(hint)
        tl.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.tool_cards = {}
        for i, tool in enumerate(self.tool_registry):
            card = ToolCard(tool)
            card.activated.connect(self._on_tool)
            grid.addWidget(card, i // 2, i % 2)
            self.tool_cards[tool["id"]] = card
        tl.addLayout(grid)
        tl.addStretch(1)
        lay.addWidget(tools_p, 1)

        pg._blocks = [hero, tools_p]
        return pg
