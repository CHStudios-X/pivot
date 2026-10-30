# -*- coding: utf-8 -*-
"""枢 Pivot · 公共件（UI 套件 + 主题常量 + 小工具函数）。

★ 这是**基础设施**，不是功能模块 —— 不要删，也不要搬进 apps/。

    apps/          放功能：一个文件就是一个功能页。删掉其中任何一个，
                   对应功能消失，外壳照常启动并跳过它。
    pivot_kit.py 放大家共用的东西：玻璃面板、胶囊按钮、开关、分段控件、
                   工具图标、键盘控件、热键录制框、主题常量、字体与资源定位。

依赖方向单向：apps/*.py  ->  pivot_kit.py  ->  PySide6。
公共件绝不反向引用 apps/ 或主程序，所以任何功能模块都能被安全删除。
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



C_ACCENT_1 = QColor(77, 163, 255)     # #4DA3FF


C_ACCENT_2 = QColor(10, 132, 255)     # #0A84FF (iOS 深色系统蓝)


C_TEXT = QColor(255, 255, 255)


C_TEXT_DIM = QColor(255, 255, 255, 158)


C_TEXT_FAINT = QColor(255, 255, 255, 105)


APP_NAME = "枢"


APP_NAME_EN = "PIVOT"


# ★ 全项目**唯一**的版本号来源。
#   安装脚本(installer.iss)与更新清单(version.json)都在构建时读这里，
#   不要在别处再写一遍 —— 两处版本号不一致，自动更新第一次就会误判。
APP_VER = "1.3.0"


STUDIO_NAME = "CHStudios"


SER_VER = "1.3.ser"       # 更新目标版本号


class GlassPanel(QFrame):
    """液态玻璃面板:上亮下暗 + 镜面高光描边 + 底部反光 + 光标光泽"""

    def __init__(self, radius=18, parent=None):
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self._radius = radius
        self._glow = None          # QPointF 局部坐标,None = 无高光
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_cursor_glow(self, global_pos):
        lp = self.mapFromGlobal(global_pos)
        new = QPointF(lp) if self.rect().contains(lp) else None
        if new is None and self._glow is None:
            return            # 光标不在本面板且此前也不在 —— 无需重绘
        self._glow = new
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        rad = self._radius

        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)

        # --- 玻璃体:上亮下暗 ---
        # 照片背景下要比光斑背景更"实"一点,否则面板边界会糊进画面里
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0.0, QColor(255, 255, 255, 34))
        g.setColorAt(0.55, QColor(255, 255, 255, 20))
        g.setColorAt(1.0, QColor(255, 255, 255, 12))
        p.fillPath(path, QBrush(g))

        p.save()
        p.setClipPath(path)

        # --- 顶部内高光(玻璃厚度感) ---
        # 高度必须封顶:按 h 的比例画的话,大面板(如右侧控制台)顶部会被
        # 大片白色渐变糊成浅灰,失去"深色玻璃"的观感。
        band_t = min(h * 0.42, 88.0)
        tg = QLinearGradient(0, r.top(), 0, r.top() + band_t)
        tg.setColorAt(0.0, QColor(255, 255, 255, 40))
        tg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(r.left(), r.top(), w, band_t), QBrush(tg))

        # --- 光标光泽:让玻璃"活"起来 ---
        # 半径取面板尺度的 0.55 并封顶 —— 面板越大,固定半径的渐变更会
        # 糊成一片灰白,失去"高光"的指向感。
        if self._glow is not None:
            gr = min(max(w, h) * 0.55, 230.0)
            rg = QRadialGradient(self._glow, gr)
            rg.setColorAt(0.0, QColor(255, 255, 255, 30))
            rg.setColorAt(0.5, QColor(255, 255, 255, 9))
            rg.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillPath(path, QBrush(rg))

        # --- 底部内侧反光 ---
        band_b = min(h * 0.16, 56.0)
        bg = QLinearGradient(0, r.bottom() - band_b, 0, r.bottom())
        bg.setColorAt(0.0, QColor(255, 255, 255, 0))
        bg.setColorAt(1.0, QColor(255, 255, 255, 18))
        p.fillRect(QRectF(r.left(), r.bottom() - band_b, w, band_b),
                   QBrush(bg))
        p.restore()

        # --- 镜面高光描边 ---
        pg = QLinearGradient(r.topLeft(), r.bottomRight())
        pg.setColorAt(0.0, QColor(255, 255, 255, 138))
        pg.setColorAt(0.32, QColor(255, 255, 255, 56))
        pg.setColorAt(1.0, QColor(255, 255, 255, 20))
        p.setPen(QPen(QBrush(pg), 1.15))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class RiseFade(QGraphicsOpacityEffect):
    """入场特效:透明度 + 垂直偏移(上浮)。

    重写 draw 在绘制前做位移 —— 控件几何始终由 layout 决定,
    只有"看起来"在上浮,因此不会和 layout 打架。
    动画结束后务必 setGraphicsEffect(None) 移除,恢复原生渲染清晰度。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dy = 0.0

    def get_dy(self):
        return self._dy

    def set_dy(self, v):
        self._dy = float(v)
        self.update()

    dy = Property(float, get_dy, set_dy)

    def boundingRectFor(self, rect):
        # 向下多留出偏移量,否则上浮过程会被裁掉
        return QRectF(rect).adjusted(0, 0, 0, 30)

    def draw(self, painter):
        painter.translate(0.0, self._dy)
        super().draw(painter)


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _ease_out_cubic(x):
    return 1.0 - (1.0 - x) ** 3


def _ease_out_back(x):
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


class PillButton(QPushButton):
    """胶囊按钮:primary = 强调色渐变,glass = 玻璃"""

    def __init__(self, text, kind="glass", parent=None):
        super().__init__(text, parent)
        self.kind = kind
        self._hover = False
        self._down = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(46)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._down = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._down = True
        self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._down = False
        self.update()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        rad = r.height() / 2.0

        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)

        enabled = self.isEnabled()

        if self.kind == "primary":
            text_col = QColor(255, 255, 255) if enabled else \
                QColor(255, 255, 255, 92)
            if enabled:
                k = 1.14 if self._hover else (0.9 if self._down else 1.0)
                c1 = QColor(min(255, int(C_ACCENT_1.red() * k)),
                            min(255, int(C_ACCENT_1.green() * k)),
                            min(255, int(C_ACCENT_1.blue() * k)))
                c2 = QColor(min(255, int(C_ACCENT_2.red() * k)),
                            min(255, int(C_ACCENT_2.green() * k)),
                            min(255, int(C_ACCENT_2.blue() * k)))
            else:
                c1 = QColor(255, 255, 255, 26)
                c2 = QColor(255, 255, 255, 14)
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            g.setColorAt(0.0, c1)
            g.setColorAt(1.0, c2)
            p.fillPath(path, QBrush(g))
        else:
            text_col = QColor(255, 255, 255, 236) if enabled else \
                QColor(255, 255, 255, 78)
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            if self._hover and enabled:
                g.setColorAt(0.0, QColor(255, 255, 255, 46))
                g.setColorAt(1.0, QColor(255, 255, 255, 22))
            elif self._down and enabled:
                g.setColorAt(0.0, QColor(255, 255, 255, 20))
                g.setColorAt(1.0, QColor(255, 255, 255, 10))
            else:
                g.setColorAt(0.0, QColor(255, 255, 255, 30))
                g.setColorAt(1.0, QColor(255, 255, 255, 14))
            p.fillPath(path, QBrush(g))

        # 顶部高光
        p.save()
        p.setClipPath(path)
        tg = QLinearGradient(0, r.top(), 0, r.top() + h * 0.5)
        tg.setColorAt(0.0, QColor(255, 255, 255, 62 if self.kind == "primary"
                                  else 52))
        tg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(r.left(), r.top(), w, h * 0.5), QBrush(tg))
        p.restore()

        # 描边
        pg = QLinearGradient(r.topLeft(), r.bottomRight())
        if self.kind == "primary" and enabled:
            pg.setColorAt(0.0, QColor(255, 255, 255, 120))
            pg.setColorAt(1.0, QColor(255, 255, 255, 30))
        else:
            pg.setColorAt(0.0, QColor(255, 255, 255, 96 if enabled else 40))
            pg.setColorAt(1.0, QColor(255, 255, 255, 22))
        p.setPen(QPen(QBrush(pg), 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # 文字
        p.setPen(text_col)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class PulseDot(QWidget):
    """呼吸灯状态指示"""

    def __init__(self, color="#63e6be", size=8, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._intensity = 1.0
        self._anim = None
        self._size = size
        self.setFixedSize(size + 20, size + 20)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def start_pulse(self):
        self.stop_pulse()
        self._anim = QPropertyAnimation(self, b"intensity")
        self._anim.setDuration(1300)
        self._anim.setStartValue(0.3)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def stop_pulse(self):
        if self._anim:
            self._anim.stop()
        self._intensity = 1.0
        self.update()

    def get_intensity(self):
        return self._intensity

    def set_intensity(self, v):
        self._intensity = v
        self.update()

    intensity = Property(float, get_intensity, set_intensity)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self.rect().center()
        for i, r in enumerate(range(self._size, self._size + 10, 2)):
            glow = QColor(self._color)
            glow.setAlpha(max(0, int(72 * self._intensity * (1 - i / 5))))
            p.setBrush(glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, r, r)
        c1 = QColor(self._color)
        c1.setAlphaF(self._intensity)
        p.setBrush(c1)
        p.drawEllipse(c, self._size // 2, self._size // 2)


class _ClickLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class SegmentedControl(QWidget):
    """iOS 分段控件:玻璃胶囊容器 + 白色滑块滑动"""

    changed = Signal(str)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setObjectName("segContainer")
        self._items = items
        self._current = 0
        self._value = items[0][1]

        self._indicator = QFrame(self)
        self._indicator.setObjectName("segIndicator")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(0)

        self._labels = []
        for i, (label, _v) in enumerate(items):
            lb = _ClickLabel(label)
            lb.setObjectName("segLabel")
            lb.setProperty("sel", "true" if i == 0 else "false")
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lb.setCursor(Qt.CursorShape.PointingHandCursor)
            lb.setMinimumHeight(30)
            lb.clicked.connect(lambda idx=i: self._select(idx))
            lay.addWidget(lb, 1)
            self._labels.append(lb)

        self.setFixedHeight(42)
        self._indicator.lower()

    def _select(self, idx):
        if idx == self._current:
            return
        self._current = idx
        self._value = self._items[idx][1]
        anim = QPropertyAnimation(self._indicator, b"geometry")
        anim.setDuration(260)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self._indicator.geometry())
        anim.setEndValue(self._labels[idx].geometry())
        anim.start()
        self._anim = anim
        for i, lb in enumerate(self._labels):
            lb.setProperty("sel", "true" if i == idx else "false")
            lb.style().unpolish(lb)
            lb.style().polish(lb)
        self.changed.emit(self._value)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._indicator.setGeometry(self._labels[self._current].geometry())

    def showEvent(self, e):
        super().showEvent(e)
        self._indicator.setGeometry(self._labels[self._current].geometry())

    def value(self):
        return self._value


class ToggleSwitch(QWidget):
    """iOS 开关"""

    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._pos = 0.0
        self._anim = None
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self):
        return self._checked

    def setChecked(self, b, animate=True):
        if b == self._checked:
            return
        self._checked = b
        if animate:
            anim = QPropertyAnimation(self, b"sliderPos")
            anim.setDuration(200)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(self._pos)
            anim.setEndValue(1.0 if b else 0.0)
            anim.start()
            self._anim = anim
        else:
            self._pos = 1.0 if b else 0.0
            self.update()
        self.toggled.emit(b)

    def get_pos(self):
        return self._pos

    def set_pos(self, v):
        self._pos = v
        self.update()

    sliderPos = Property(float, get_pos, set_pos)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        t = self._pos

        off = QColor(255, 255, 255, 46)
        on = QColor(C_ACCENT_1)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
            int(off.alpha() + (on.alpha() - off.alpha()) * t),
        )
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)

        d = h - 7
        x = 3.5 + t * (w - d - 7)
        g = int(168 + 87 * t)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(g, g, g))
        p.drawEllipse(QRectF(x, 3.5, d, d))


class AnimatedCounter(QWidget):
    """渐变数字计数(字号 / 对齐可调,横屏下的主仪表盘用大字号居中)"""

    def __init__(self, size=17, align=None, parent=None):
        super().__init__(parent)
        self._value = 0
        self._size = size
        self._align = align if align is not None \
            else Qt.AlignmentFlag.AlignRight
        self.setMinimumHeight(int(size * 1.55) + 6)
        self.setMinimumWidth(90)

    def set_value(self, v):
        self._value = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(self.font().family(), self._size)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0, QColor(224, 244, 255))
        grad.setColorAt(1, QColor(C_ACCENT_1))
        p.setPen(QPen(QBrush(grad), 1))
        p.drawText(self.rect(),
                   Qt.AlignmentFlag.AlignVCenter | self._align,
                   str(self._value))


class CountdownOverlay(QWidget):
    """居中大字倒计时:缩放 + 淡入淡出"""

    countdown_done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0
        self._scale = 1.0
        self._opacity = 0.0
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def start(self, seconds):
        self._count = seconds
        self._scale = 0.4
        self._opacity = 0.0
        self.show()
        self.raise_()
        self._a_op = QPropertyAnimation(self, b"opacity")
        self._a_op.setDuration(240)
        self._a_op.setStartValue(0.0)
        self._a_op.setEndValue(1.0)
        self._a_op.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a_op.start()
        self._a_sc = QPropertyAnimation(self, b"scale")
        self._a_sc.setDuration(320)
        self._a_sc.setStartValue(0.4)
        self._a_sc.setEndValue(1.0)
        self._a_sc.setEasingCurve(QEasingCurve.Type.OutBack)
        self._a_sc.start()
        self.update()

    def update_to(self, n):
        if n <= 0:
            self.finish()
            return
        if not self.isVisible():
            self.start(n)
            return
        if n == self._count:
            return
        self._count = n
        self._a_sc = QPropertyAnimation(self, b"scale")
        self._a_sc.setDuration(340)
        self._a_sc.setStartValue(1.42)
        self._a_sc.setEndValue(1.0)
        self._a_sc.setEasingCurve(QEasingCurve.Type.OutBack)
        self._a_sc.start()
        self.update()

    def finish(self):
        if not self.isVisible():
            return
        self._a_out = QPropertyAnimation(self, b"opacity")
        self._a_out.setDuration(280)
        self._a_out.setStartValue(self._opacity)
        self._a_out.setEndValue(0.0)
        self._a_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._a_out.finished.connect(self._on_faded)
        self._a_out.start()

    def _on_faded(self):
        self.hide()
        self._count = 0
        self.countdown_done.emit()

    def cancel(self):
        for attr in ("_a_op", "_a_sc", "_a_out"):
            a = getattr(self, attr, None)
            if a is not None:
                a.stop()
        self.hide()
        self._count = 0
        self._opacity = 0.0
        self.update()

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, v):
        self._opacity = v
        self.update()

    opacity = Property(float, get_opacity, set_opacity)

    def get_scale(self):
        return self._scale

    def set_scale(self, v):
        self._scale = v
        self.update()

    scale = Property(float, get_scale, set_scale)

    def paintEvent(self, _):
        if self._count <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)

        # 玻璃蒙层(留一点透明度,让照片背景透出来)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(12, 12, 18, 220))
        g.setColorAt(1.0, QColor(10, 10, 16, 235))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, QBrush(g))

        p.translate(self.rect().center())
        p.scale(self._scale, self._scale)
        p.translate(-self.rect().center())

        rect = self.rect()
        text = str(self._count)

        f = QFont(self.font().family(), 116)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        for off in range(12, 0, -2):
            c = QColor(C_ACCENT_1)
            c.setAlphaF(0.032)
            p.setPen(QPen(c, off))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
        grad.setColorAt(0, QColor(230, 246, 255))
        grad.setColorAt(1, QColor(C_ACCENT_1))
        p.setPen(QPen(QBrush(grad), 2))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        p.setFont(QFont(self.font().family(), 12))
        p.setPen(QColor(255, 255, 255, 172))
        p.drawText(self.rect().translated(0, 150),
                   Qt.AlignmentFlag.AlignCenter, "即将开始")


QSS = """
#root { background: transparent; border: none; }
#glassPanel { background: transparent; border: none; }

#windowTitle { color: rgba(255, 255, 255, 240); font-size: 13px;
               font-weight: 600; }
#brandSub   { color: rgba(255, 255, 255, 96); font-size: 9px;
              letter-spacing: 2px; }

#cardTitle { color: rgba(255, 255, 255, 160); font-size: 11px;
             letter-spacing: 0.6px; }
#fieldLabel{ color: rgba(255, 255, 255, 150); font-size: 12px; }
#tip       { color: rgba(255, 255, 255, 118); font-size: 11px; }
#statusText{ color: rgba(255, 255, 255, 172); font-size: 12px; }
#ratioText { color: rgba(255, 255, 255, 132); font-size: 11px; }

#segContainer {
    background: rgba(255, 255, 255, 12);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 21px;
}
#segIndicator {
    background: rgba(255, 255, 255, 62);
    border: 1px solid rgba(255, 255, 255, 60);
    border-radius: 17px;
}
#segLabel            { color: rgba(255, 255, 255, 178); font-size: 12px;
                       background: transparent; }
#segLabel[sel="true"]{ color: #ffffff; }

QLineEdit {
    background: rgba(255, 255, 255, 20);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 11px;
    padding: 8px 11px;
    color: #ffffff;
    selection-background-color: #4da3ff;
    selection-color: #ffffff;
}
QLineEdit:focus {
    background: rgba(255, 255, 255, 30);
    border: 1px solid rgba(120, 190, 255, 190);
}

#startBtn { font-size: 15px; font-weight: 600; }
#stopBtn  { font-size: 15px; font-weight: 600; }
#coordBtn { font-size: 12px; }

#progress {
    background: rgba(255, 255, 255, 24);
    border: none;
    border-radius: 4px;
    max-height: 8px;
    min-height: 8px;
}
#progress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4da3ff, stop:1 #7ee0ff);
    border-radius: 4px;
}

/* ---------- 枢 Pivot ---------- */
#heroTitle { color: rgba(255, 255, 255, 246); font-size: 30px;
             font-weight: 700; letter-spacing: 2px; background: transparent; }
#heroSub   { color: rgba(255, 255, 255, 130); font-size: 11px;
             letter-spacing: 1.6px; background: transparent; }
#heroNote  { color: rgba(255, 255, 255, 108); font-size: 11px;
             background: transparent; }
#verBig    { color: rgba(150, 205, 255, 232); font-size: 40px;
             font-weight: 700; background: transparent; }
#verSmall  { color: rgba(255, 255, 255, 118); font-size: 13px;
             font-weight: 600; background: transparent; }

#toolName  { color: rgba(255, 255, 255, 240); font-size: 13px;
             font-weight: 600; background: transparent; }
#toolDesc  { color: rgba(255, 255, 255, 138); font-size: 11px;
             background: transparent; }
#toolState { color: rgba(150, 205, 255, 200); font-size: 11px;
             background: transparent; }
#toolBadge { color: #06131f; background: rgba(120, 214, 255, 235);
             border-radius: 8px; padding: 2px 9px; font-size: 10px;
             font-weight: 600; }
#toolBadgeRun { color: #04210f; background: rgba(120, 240, 180, 240);
             border-radius: 8px; padding: 2px 9px; font-size: 10px;
             font-weight: 600; }
#toolBadgeSoon { color: rgba(255, 255, 255, 128);
             background: rgba(255, 255, 255, 26);
             border-radius: 8px; padding: 2px 9px; font-size: 10px; }

#navTab        { color: rgba(255, 255, 255, 140); font-size: 12px;
                 background: transparent; }
#navTab:hover  { color: rgba(255, 255, 255, 220); }
#navTab[sel="true"] { color: #ffffff; font-weight: 600; }

#userName { color: rgba(255, 255, 255, 226); font-size: 12px;
            font-weight: 600; background: transparent; }
#userRole { color: rgba(255, 255, 255, 108); font-size: 10px;
            background: transparent; }

#kvKey   { color: rgba(255, 255, 255, 138); font-size: 11px;
           background: transparent; }
#kvVal   { color: rgba(255, 255, 255, 226); font-size: 12px;
           background: transparent; }
#pageHint { color: rgba(255, 255, 255, 112); font-size: 11px;
            background: transparent; }
#kbd { color: rgba(255, 255, 255, 235); background: rgba(255, 255, 255, 30);
       border: 1px solid rgba(255, 255, 255, 46); border-radius: 6px;
       padding: 2px 8px; font-size: 11px; font-weight: 600; }

/* ---------- 热键录制按钮 ---------- */
#hotkeyBtn {
    background: rgba(255, 255, 255, 24);
    border: 1px solid rgba(255, 255, 255, 48);
    border-radius: 8px;
    color: rgba(255, 255, 255, 242);
    font-size: 12px;
    font-weight: 600;
}
#hotkeyBtn:hover   { background: rgba(255, 255, 255, 40); }
#hotkeyBtn[cap="true"] {
    background: rgba(77, 163, 255, 80);
    border: 1px solid rgba(150, 205, 255, 200);
    color: #ffffff;
}

/* ---------- 滑块 ---------- */
#glassSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 26);
    border-radius: 2px;
}
#glassSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4da3ff, stop:1 #7ee0ff);
    border-radius: 2px;
}
#glassSlider::handle:horizontal {
    background: #ffffff;
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 6px;
}
#glassSlider::handle:horizontal:hover { background: #eaf6ff; }

/* ---------- 滚动区(壁纸库) ---------- */
#wpScroll, #wpHost, #wpViewport { background: transparent; }
QScrollBar:vertical {
    background: transparent; width: 8px; margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 48);
    border-radius: 4px; min-height: 26px;
}
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 76); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
"""


class ToolIcon(QWidget):
    """工具矢量图标(不依赖字体,避免字形缺失显示成方框)"""

    def __init__(self, kind="click", size=34, color="#4da3ff", parent=None):
        super().__init__(parent)
        self.kind = kind
        self._c = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = min(self.width(), self.height())
        c = self._c
        pen = QPen(QColor(c.red(), c.green(), c.blue(), 235), max(1.3, s * 0.055))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        thin = QPen(QColor(c.red(), c.green(), c.blue(), 150),
                    max(1.0, s * 0.045))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = s * 0.5

        # 底座圆角方块(淡淡的色块,让图标有"底板")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 34))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1,
                                 self.height() - 1), s * 0.30, s * 0.30)

        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "click":
            # 点击波纹:中心点 + 实环 + 断续外环
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 240))
            p.drawEllipse(QPointF(cx, cy), r * 0.14, r * 0.14)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
            p.drawEllipse(QPointF(cx, cy), r * 0.36, r * 0.36)
            p.setPen(thin)
            ar = r * 0.60
            for a in (18, 108, 198, 288):
                p.drawArc(QRectF(cx - ar, cy - ar, ar * 2, ar * 2),
                          int(a * 16), int(62 * 16))
        elif self.kind == "keys":
            # 键盘:圆角矩形 + 三个键帽
            p.setPen(pen)
            p.drawRoundedRect(QRectF(cx - r * 0.66, cy - r * 0.42,
                                     r * 1.32, r * 0.84), r * 0.18, r * 0.18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 220))
            for i in (-1, 0, 1):
                p.drawRoundedRect(QRectF(cx + i * r * 0.34 - r * 0.10,
                                         cy - r * 0.12, r * 0.20, r * 0.24),
                                  r * 0.05, r * 0.05)
        elif self.kind == "remap":
            # 改键:左键帽 → 右键帽
            p.setPen(pen)
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 60))
            kw, kh = r * 0.50, r * 0.56
            p.drawRoundedRect(QRectF(cx - r * 0.92, cy - kh * 0.5,
                                     kw, kh), r * 0.12, r * 0.12)
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 205))
            p.drawRoundedRect(QRectF(cx + r * 0.42, cy - kh * 0.5,
                                     kw, kh), r * 0.12, r * 0.12)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(thin)
            p.drawLine(QPointF(cx - r * 0.32, cy), QPointF(cx + r * 0.26, cy))
            p.drawLine(QPointF(cx + r * 0.26, cy),
                       QPointF(cx + r * 0.10, cy - r * 0.15))
            p.drawLine(QPointF(cx + r * 0.26, cy),
                       QPointF(cx + r * 0.10, cy + r * 0.15))
        elif self.kind == "update":
            # 更新:向下的箭头 + 底部托盘(下载/落地)
            p.setPen(pen)
            p.drawLine(QPointF(cx, cy - r * 0.52), QPointF(cx, cy + r * 0.22))
            p.drawLine(QPointF(cx - r * 0.27, cy - r * 0.03),
                       QPointF(cx, cy + r * 0.22))
            p.drawLine(QPointF(cx + r * 0.27, cy - r * 0.03),
                       QPointF(cx, cy + r * 0.22))
            p.setPen(thin)
            p.drawLine(QPointF(cx - r * 0.42, cy + r * 0.50),
                       QPointF(cx + r * 0.42, cy + r * 0.50))
        else:
            # 更多:一个加号
            p.setPen(pen)
            p.drawLine(QPointF(cx - r * 0.42, cy), QPointF(cx + r * 0.42, cy))
            p.drawLine(QPointF(cx, cy - r * 0.42), QPointF(cx, cy + r * 0.42))


class ToolCard(GlassPanel):
    """主页的工具卡片:图标 + 名称 + 描述 + 状态"""

    activated = Signal(str)

    def __init__(self, tool, parent=None):
        super().__init__(radius=16, parent=parent)
        self.tool = tool
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor
                       if tool["ready"] else Qt.CursorShape.ArrowCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(9)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(ToolIcon(tool["icon"], 34, tool["accent"]))
        name = QLabel(tool["name"])
        name.setObjectName("toolName")
        top.addWidget(name, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch()
        self.badge = QLabel("可用" if tool["ready"] else "开发中")
        self.badge.setObjectName("toolBadge" if tool["ready"]
                                 else "toolBadgeSoon")
        top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(top)

        desc = QLabel(tool["desc"])
        desc.setObjectName("toolDesc")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        lay.addStretch(1)

        self.state = QLabel("打开  →" if tool["ready"] else "敬请期待")
        self.state.setObjectName("toolState")
        lay.addWidget(self.state)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def set_running(self, on):
        if not self.tool["ready"]:
            return
        self.badge.setText("运行中" if on else "可用")
        self.badge.setObjectName("toolBadgeRun" if on else "toolBadge")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def mouseReleaseEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton and self.tool["ready"]
                and self.rect().contains(e.position().toPoint())):
            self.activated.emit(self.tool["id"])
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        if self._hover and self.tool["ready"]:
            self._glow = QPointF(self.rect().center())
        super().paintEvent(_)


class NavTab(QLabel):
    """底部导航项:选中时高亮 + 下方短横线"""

    clicked = Signal(str)

    def __init__(self, text, key, parent=None):
        super().__init__(text, parent)
        self.key = key
        self._sel = False
        self.setObjectName("navTab")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(26)
        self.setMinimumWidth(58)
        self.setProperty("sel", "false")

    def set_selected(self, on):
        if self._sel == on:
            return
        self._sel = on
        self.setProperty("sel", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mouseReleaseEvent(e)


_QT_SPECIAL_KEY = {
    Qt.Key.Key_Space: "space", Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Insert: "insert", Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end", Qt.Key.Key_PageUp: "page up",
    Qt.Key.Key_PageDown: "page down", Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right", Qt.Key.Key_CapsLock: "caps lock",
}


_QT_MOD_KEY = (
    (Qt.KeyboardModifier.ControlModifier, "ctrl"),
    (Qt.KeyboardModifier.AltModifier, "alt"),
    (Qt.KeyboardModifier.ShiftModifier, "shift"),
    (Qt.KeyboardModifier.MetaModifier, "windows"),
)


_NAMED_KEYS = set(_QT_SPECIAL_KEY.values()) | {"f1", "f2", "f3", "f4", "f5",
                                               "f6", "f7", "f8", "f9", "f10",
                                               "f11", "f12", "space"}


def qt_key_to_name(ev):
    """QKeyEvent → keyboard 库的按键名;不支持返回 None"""
    k = ev.key()
    for i in range(1, 25):
        if k == getattr(Qt.Key, f"Key_F{i}", None):
            return f"f{i}"
    if Qt.Key.Key_A <= k <= Qt.Key.Key_Z:
        return chr(ord("a") + (k - Qt.Key.Key_A))
    if Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
        return chr(ord("0") + (k - Qt.Key.Key_0))
    return _QT_SPECIAL_KEY.get(k)


def fmt_hotkey(name):
    """'ctrl+shift+a' -> 'Ctrl+Shift+A'"""
    return "+".join(part.capitalize() if len(part) > 1 else part.upper()
                    for part in str(name).split("+"))


_KEY_DISPLAY = {
    "space": "Space", "tab": "Tab", "enter": "Enter", "caps lock": "Caps",
    "backspace": "Backspace", "delete": "Del", "insert": "Ins",
    "home": "Home", "end": "End", "page up": "PgUp", "page down": "PgDn",
    "up": "↑", "down": "↓", "left": "←", "right": "→", "esc": "Esc",
    "shift": "Shift", "ctrl": "Ctrl", "alt": "Alt", "windows": "Win",
    "menu": "Menu",
}


def fmt_key_name(name):
    """keyboard 库键名 -> 界面上好认的短名"""
    n = str(name)
    if n in _KEY_DISPLAY:
        return _KEY_DISPLAY[n]
    if len(n) == 1:
        return n.upper()
    return n.capitalize()


class HotkeyButton(QPushButton):
    """点一下进入录制态,再按一个键即完成绑定

    ⚠ 录到的键名由**本控件自己**存下来(见 keyPressEvent) ——
      不要依赖使用方去连 changed 再调 set_value()。早起版本只发信号不回写,
      结果"忘连 changed"的使用方会表现为**按钮永远停在构造时的默认值**:
      点进去、按键、显示闪一下又还原,怎么录都录不进去。
      changed 现在只用于"通知外部该重新注册热键了"。
    """

    changed = Signal(str)
    capturing = Signal(bool)       # True 进入录制 / False 退出

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self._name = name
        self._cap = False
        self.setObjectName("hotkeyBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(112, 30)
        self.setToolTip("点一下进入录制，再按一个新键即可（Esc 取消）")
        self.clicked.connect(self._begin)
        self._sync()

    def value(self):
        return self._name

    def set_value(self, name):
        self._name = name
        self._sync()

    def _sync(self):
        self.setText("按下按键…" if self._cap else fmt_hotkey(self._name))
        self.setProperty("cap", "true" if self._cap else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def _begin(self):
        if self._cap:
            return
        self._cap = True
        self._sync()
        try:
            self.grabKeyboard()
        except Exception:
            pass
        self.setFocus()
        self.capturing.emit(True)

    def _end(self):
        if not self._cap:
            return
        self._cap = False
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self._sync()
        self.capturing.emit(False)

    def keyPressEvent(self, e):
        if not self._cap:
            super().keyPressEvent(e)
            return
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self._end()
            return
        if k in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                 Qt.Key.Key_Meta):
            return                      # 只按修饰键不算,等主键
        name = qt_key_to_name(e)
        if name is None:
            self.setText("该键不支持")
            QTimer.singleShot(800, self._sync)
            return
        mods = [n for flag, n in _QT_MOD_KEY if e.modifiers() & flag]
        full = "+".join(mods + [name])
        # 先落存、再收尾:_end() 里的 _sync() 就会直接把新键显示出来。
        # 顺序反过来(先 _end 再赋值)会先刷回旧值,视觉上闪一下旧键。
        self._name = full
        self._end()
        self.changed.emit(full)

    def focusOutEvent(self, e):
        if self._cap:
            self._end()
        super().focusOutEvent(e)


def _pick_font() -> str:
    try:
        fams = set(QFontDatabase.families())
    except Exception:
        fams = set()
    for f in ("MiSans", "HarmonyOS Sans SC", "Microsoft YaHei UI",
              "Microsoft YaHei", "Segoe UI Variable Display", "Segoe UI"):
        if f in fams:
            return f
    return "Segoe UI"


def _res_path(rel):
    """定位随程序分发的资源(兼容 PyInstaller 单文件模式)"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# 内置壁纸 + 路径解析。这两样放在公共件而不是功能模块里，是因为
# 外壳的 AuroraRoot（背景层）自己就要用：壁纸是窗口背景的一部分，
# 外观页只是"编辑"它的界面 —— 外观功能被删掉，背景照样得能显示。
BUILTIN_WALLPAPER = os.path.join("assets", "bg.jpg")


def _resolve_bg(path):
    """把 QSettings 里存的路径解析成真实存在的文件;不存在则返回 None"""
    if not path:
        return None
    if os.path.exists(path):
        return path
    alt = _res_path(path)
    return alt if os.path.exists(alt) else None
