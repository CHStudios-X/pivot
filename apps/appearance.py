# -*- coding: utf-8 -*-
"""枢功能模块 · 外观

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
    BUILTIN_WALLPAPER,
    C_ACCENT_1,
    PillButton,
    _resolve_bg,
    _res_path,
)

def _user_wallpaper_dir():
    """用户导入的壁纸存放目录(导入时会把大图规范化,避免原图被移走后失效)"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Pivot", "wallpapers")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def import_wallpaper(src):
    """导入一张壁纸:等比缩到不超过 2560 宽、压成 JPEG 存进用户目录"""
    pm = QPixmap(src)
    if pm.isNull():
        return None
    if pm.width() > 2560:
        pm = pm.scaledToWidth(2560, Qt.TransformationMode.SmoothTransformation)
    name = f"wp_{int(time.time())}_{abs(hash(src)) % 10000}.jpg"
    dst = os.path.join(_user_wallpaper_dir(), name)
    if not pm.save(dst, "JPG", 90):
        return None
    return dst


class WallpaperTile(QWidget):
    """壁纸缩略图卡片(选中时描边 + 右上角勾)"""

    picked = Signal(str)

    def __init__(self, path, title, subtitle="", parent=None):
        super().__init__(parent)
        self.path = path
        self._sel = False
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedSize(148, 116)
        self._pm = QPixmap(_resolve_bg(path) or "") if path else None
        self._title = title
        self._sub = subtitle

    def set_selected(self, on):
        if self._sel != on:
            self._sel = on
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.path)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        thumb_h = h - 26
        r = QRectF(0.5, 0.5, w - 1, thumb_h - 0.5)
        rad = 11.0
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)

        p.save()
        p.setClipPath(path)
        if self._pm is not None and not self._pm.isNull():
            # cover 裁切填满缩略图
            sw, sh = self._pm.width(), self._pm.height()
            k = max(r.width() / max(1, sw), r.height() / max(1, sh))
            tw, th = max(1, round(sw * k)), max(1, round(sh * k))
            sc = self._pm.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int(r.left() - (tw - r.width()) / 2),
                         int(r.top() - (th - r.height()) / 2), sc)
        else:
            p.fillRect(r, QColor(255, 255, 255, 16))
        p.fillRect(r, QColor(0, 0, 0, 40 if not self._hover else 10))
        p.restore()

        # 描边 / 选中态
        if self._sel:
            p.setPen(QPen(QColor(C_ACCENT_1), 2.0))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 46 if self._hover else 26), 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        if self._sel:
            cx, cy = r.right() - 15, r.top() + 15
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C_ACCENT_1))
            p.drawEllipse(QPointF(cx, cy), 9, 9)
            pen = QPen(QColor(6, 20, 32), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(cx - 4, cy), QPointF(cx - 1.2, cy + 3))
            p.drawLine(QPointF(cx - 1.2, cy + 3), QPointF(cx + 4.2, cy - 3.2))

        f = QFont(self.font().family(), 8)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 226 if self._sel else 170))
        p.drawText(QRectF(1, thumb_h + 2, w - 2, 15),
                   int(Qt.AlignmentFlag.AlignCenter), self._title)
        if self._sub:
            p.setPen(QColor(255, 255, 255, 96))
            p.drawText(QRectF(1, thumb_h + 14, w - 2, 12),
                       int(Qt.AlignmentFlag.AlignCenter), self._sub)


class AddWallpaperTile(QWidget):
    """「从文件选择」卡片:虚线框 + 加号"""

    picked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedSize(148, 116)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 27)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        pen = QPen(QColor(255, 255, 255, 70 if self._hover else 44), 1.4)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        p.setPen(pen)
        p.setBrush(QColor(255, 255, 255, 14 if self._hover else 6))
        p.drawPath(path)

        cx, cy = r.center().x(), r.center().y()
        p.setPen(QPen(QColor(255, 255, 255, 200 if self._hover else 150), 1.6))
        p.drawLine(QPointF(cx - 9, cy), QPointF(cx + 9, cy))
        p.drawLine(QPointF(cx, cy - 9), QPointF(cx, cy + 9))

        f = QFont(self.font().family(), 8)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(QRectF(1, h - 24, w - 2, 14),
                   int(Qt.AlignmentFlag.AlignCenter), "从文件选择")


class WallpaperPreview(QWidget):
    """右侧预览:与真实窗口背景同一套 cover 裁切"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm = None
        self.setMinimumHeight(150)

    def set_image(self, path):
        pm = QPixmap(path) if path else None
        self._pm = pm if (pm is not None and not pm.isNull()) else None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.save()
        p.setClipPath(path)
        if self._pm is None:
            p.fillRect(r, QColor(255, 255, 255, 14))
        else:
            sw, sh = self._pm.width(), self._pm.height()
            k = max(r.width() / max(1, sw), r.height() / max(1, sh))
            tw, th = max(1, round(sw * k)), max(1, round(sh * k))
            sc = self._pm.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int(r.left() - (tw - r.width()) / 2),
                         int(r.top() - (th - r.height()) / 2), sc)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 60), 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


META = {
    'id': 'appearance',
    'name': '外观',
    'nav': '外观',
    'order': 50,
    'card': False,
    'desc': '',
    'icon': 'appearance',
    'accent': '#b39ddb',
    'ready': True,
    'builder': '_build_appearance',
    'state': 'page_appearance',
}


class Feature:
    """外观功能页（混入 App：方法里的 self 就是 App 实例）。"""

    def _build_appearance(self):
        pg = QWidget()
        lay = QHBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)

        lib, ll = self._panel(spacing=11, margins=(20, 16, 20, 18))
        head = QHBoxLayout()
        head.addWidget(self._title("壁纸"))
        head.addStretch()
        hint = QLabel("点一下即应用")
        hint.setObjectName("pageHint")
        head.addWidget(hint)
        ll.addLayout(head)

        host = QWidget()
        host.setObjectName("wpHost")
        self.wp_grid = QGridLayout(host)
        self.wp_grid.setContentsMargins(0, 0, 0, 0)
        self.wp_grid.setSpacing(12)
        self.wp_grid.setAlignment(Qt.AlignmentFlag.AlignTop
                                  | Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setObjectName("wpScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(host)
        ll.addWidget(scroll, 1)
        lay.addWidget(lib, 3)

        pv, pl = self._panel(spacing=10, margins=(20, 16, 20, 18))
        pl.addWidget(self._title("预览"))
        self.wp_preview = WallpaperPreview()
        pl.addWidget(self.wp_preview, 1)
        self.wp_name = QLabel("内置壁纸")
        self.wp_name.setObjectName("kvVal")
        self.wp_name.setWordWrap(True)
        pl.addWidget(self.wp_name)

        self.alpha_slider, self.alpha_val = self._slider_row(
            "暗化", 0, 100, 59, self._on_alpha)
        pl.addWidget(self.alpha_slider)
        self.blur_slider, self.blur_val = self._slider_row(
            "柔化", 1, 6, 2, self._on_blur)
        pl.addWidget(self.blur_slider)

        rowa = QHBoxLayout()
        rowa.setSpacing(9)
        pick = PillButton("从文件选择…", "primary")
        pick.setObjectName("startBtn")
        pick.setFixedHeight(38)
        pick.clicked.connect(self._pick_wallpaper_file)
        rowa.addWidget(pick, 1)
        rst = PillButton("恢复默认", "glass")
        rst.setObjectName("coordBtn")
        rst.setFixedHeight(38)
        rst.clicked.connect(lambda: self._apply_wallpaper(BUILTIN_WALLPAPER))
        rowa.addWidget(rst, 0)
        pl.addLayout(rowa)
        lay.addWidget(pv, 2)

        # ★ 只让预览面板做入场动画:左边壁纸库里有 QScrollArea,
        #   给含 QScrollArea 的控件挂 QGraphicsEffect 会在绘制时崩
        #   (Windows 上 access violation,stack 落在 QGraphicsOpacityEffect.draw)
        pg._blocks = [pv]
        self._reload_wallpaper_tiles()
        return pg

    def _slider_row(self, title, lo, hi, val, on_change):
        """带标题与数值的滑块行 -> (容器, 数值标签)"""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        top = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("fieldLabel")
        top.addWidget(t)
        top.addStretch()
        num = QLabel(str(val))
        num.setObjectName("kvVal")
        top.addWidget(num)
        v.addLayout(top)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setObjectName("glassSlider")
        sl.setRange(lo, hi)
        sl.setValue(val)
        sl.valueChanged.connect(lambda x: (num.setText(str(int(x))),
                                           on_change(x)))
        v.addWidget(sl)
        box._slider = sl
        return box, num

    def _reload_wallpaper_tiles(self):
        while self.wp_grid.count():
            it = self.wp_grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.wp_tiles = {}
        items = [(BUILTIN_WALLPAPER, "内置壁纸", "预置")]
        try:
            for f in sorted(os.listdir(_user_wallpaper_dir())):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp",
                                       ".webp")):
                    items.append((os.path.join(_user_wallpaper_dir(), f),
                                  os.path.splitext(f)[0], "自定义"))
        except Exception:
            pass
        for i, (path, title, sub) in enumerate(items):
            tile = WallpaperTile(path, title, sub)
            tile.picked.connect(self._apply_wallpaper)
            self.wp_grid.addWidget(tile, i // 3, i % 3)
            self.wp_tiles[path] = tile
        n = len(items)
        add = AddWallpaperTile()
        add.picked.connect(self._pick_wallpaper_file)
        self.wp_grid.addWidget(add, n // 3, n % 3)
        self._sync_wallpaper_ui()

    def _sync_wallpaper_ui(self):
        cur = self._root.bg_path or BUILTIN_WALLPAPER
        for path, tile in getattr(self, "wp_tiles", {}).items():
            tile.set_selected(path == cur)
        if hasattr(self, "wp_preview"):
            self.wp_preview.set_image(_resolve_bg(cur))
        name = "内置壁纸" if cur == BUILTIN_WALLPAPER else os.path.basename(cur)
        if hasattr(self, "wp_name"):
            self.wp_name.setText(name if cur == BUILTIN_WALLPAPER
                                 else f"自定义 · {name}")
        if getattr(self, "bg_name_row", None) is not None:
            lbl = self.bg_name_row.findChild(QLabel, "kvVal")
            if lbl is not None:
                lbl.setText("内置壁纸" if cur == BUILTIN_WALLPAPER else name)
        if hasattr(self, "alpha_slider"):
            self.alpha_slider._slider.blockSignals(True)
            self.alpha_slider._slider.setValue(int(self._root.bg_alpha / 2.55))
            self.alpha_slider._slider.blockSignals(False)
            self.alpha_val.setText(str(int(self._root.bg_alpha)))
            self.blur_slider._slider.blockSignals(True)
            self.blur_slider._slider.setValue(int(self._root.bg_blur))
            self.blur_slider._slider.blockSignals(False)
            self.blur_val.setText(str(int(self._root.bg_blur)))

    def _apply_wallpaper(self, path):
        self._root.set_background(path)
        self._settings.setValue("bg_path",
                                self._root.bg_path or BUILTIN_WALLPAPER)
        self._sync_wallpaper_ui()
        self._set_status("壁纸已更换", "#4da3ff")

    def _pick_wallpaper_file(self):
        start = os.path.join(os.path.expanduser("~"), "Pictures")
        if not os.path.isdir(start):
            start = os.path.expanduser("~")
        path, _f = QFileDialog.getOpenFileName(
            self, "选择壁纸", start,
            "图片 (*.jpg *.jpeg *.png *.bmp *.webp);;所有文件 (*.*)")
        if not path:
            return
        dst = import_wallpaper(path)
        if not dst:
            self._set_status("这张图片读不出来", "#ff6b6b")
            return
        self._reload_wallpaper_tiles()
        self._apply_wallpaper(dst)

    def _on_alpha(self, v):
        self._root.bg_alpha = int(round(float(v) * 2.55))
        self._root.update()
        self._settings.setValue("bg_alpha", self._root.bg_alpha)

    def _on_blur(self, v):
        self._root.bg_blur = max(1, int(v))
        self._root._bg_key = None          # 缓存作废
        self._root.update()
        self._settings.setValue("bg_blur", self._root.bg_blur)
