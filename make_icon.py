# -*- coding: utf-8 -*-
"""
生成应用图标:多尺寸 ICO(16/24/32/48/64/128/256) + 方案对比预览

底座统一为**纯黑**(#000000)+ 白色符号,小尺寸自动简化细节 ——
黑底在深色任务栏 / 资源管理器里辨识度最高。
不依赖 Pillow —— ICO 用 PNG payload 自己拼(Windows Vista+ 支持)。
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray  # noqa: E402
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QBrush,   # noqa: E402
                           QLinearGradient, QPainterPath, QPolygonF)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icon")
os.makedirs(OUT, exist_ok=True)

SIZES = [16, 24, 32, 48, 64, 128, 256]

# 品牌渐变 —— 1.2.4 起仅作备选(black=False 才用),主图标已改纯黑底
C1 = QColor("#6FB4FF")
C2 = QColor("#7D5CFF")

# 底座是否用纯黑(False 则回到上面的蓝紫渐变)
PLATE_BLACK = True


# ============================================================================
# 绘制
# ============================================================================

def _base_plate(p, s, black=False):
    """圆角方块底座 + 渐变 + 顶部高光,返回 path

    白盒符号 + 描边在纯黑底上仍然清晰,这是选黑底的原因。
    """
    pad = s * 0.035
    rect = QRectF(pad, pad, s - 2 * pad, s - 2 * pad)
    rad = rect.width() * 0.285
    path = QPainterPath()
    path.addRoundedRect(rect, rad, rad)

    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    if black:
        g.setColorAt(0.0, QColor("#000000"))
        g.setColorAt(1.0, QColor("#000000"))
    else:
        g.setColorAt(0.0, C1)
        g.setColorAt(1.0, C2)
    p.fillPath(path, QBrush(g))

    p.save()
    p.setClipPath(path)
    tg = QLinearGradient(0, rect.top(), 0, rect.top() + s * 0.58)
    tg.setColorAt(0.0, QColor(255, 255, 255, 108 if not black else 46))
    tg.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(rect.left(), rect.top(), s, s * 0.58), QBrush(tg))
    p.restore()

    # 描边
    pg = QLinearGradient(rect.topLeft(), rect.bottomRight())
    pg.setColorAt(0.0, QColor(255, 255, 255, 170 if not black else 120))
    pg.setColorAt(1.0, QColor(255, 255, 255, 40 if not black else 26))
    p.setPen(QPen(QBrush(pg), max(0.7, s * 0.012)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    return path


def _ripple(p, s):
    """点击波纹:中心点 + 实环 + 断续外环(小尺寸逐级简化)"""
    cx = cy = s / 2.0
    if s <= 20:
        # 16px:只有一个点和一圈,线加粗才看得见
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 252))
        p.drawEllipse(QPointF(cx, cy), s * 0.115, s * 0.115)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 225), max(1.0, s * 0.088)))
        p.drawEllipse(QPointF(cx, cy), s * 0.275, s * 0.275)
        return

    pen_w = max(1.0, s * 0.055)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 252))
    p.drawEllipse(QPointF(cx, cy), s * 0.088, s * 0.088)

    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 220), pen_w))
    p.drawEllipse(QPointF(cx, cy), s * 0.190, s * 0.190)

    if s >= 32:
        p.setPen(QPen(QColor(255, 255, 255, 152), pen_w * 0.92))
        ar = s * 0.290
        arc = QRectF(cx - ar, cy - ar, ar * 2, ar * 2)
        for a0 in (18, 108, 198, 288):
            p.drawArc(arc, int(a0 * 16), int(62 * 16))


def _bolt(p, s):
    """闪电(呼应标题栏的 ⚡),6 点经典折线"""
    cx = cy = s / 2.0
    pts = [
        (0.115, -0.375),
        (-0.245, 0.045),
        (-0.040, 0.045),
        (-0.130, 0.375),
        (0.245, -0.055),
        (0.040, -0.055),
    ]
    poly = QPolygonF([QPointF(cx + x * s, cy + y * s) for x, y in pts])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 250))
    p.drawPolygon(poly)


def _mouse(p, s):
    """鼠标:圆角矩形机身 + 滚轮线"""
    cx = cy = s / 2.0
    mw = s * 0.365
    mh = s * 0.520
    mr = QRectF(cx - mw / 2, cy - mh / 2, mw, mh)
    pen_w = max(1.0, s * 0.058)
    p.setPen(QPen(QColor(255, 255, 255, 238), pen_w))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(mr, mw * 0.48, mw * 0.48)
    if s >= 24:
        p.setPen(QPen(QColor(255, 255, 255, 238), pen_w))
        p.drawLine(QPointF(cx, cy - mh * 0.33), QPointF(cx, cy - mh * 0.06))


def _box(p, s):
    """敞开的「盒子」:等距立方体 + 顶面箱口 —— 原软件名「工具盒子」的具象。
    1.3.0 改名为「枢 / Pivot」后图标按要求**保留未换**，所以这个盒子
    现在只是品牌图形，不再与名字字面呼应。

    只有三个面,没有多余笔画 —— 缩到 16px 也不会糊成一团。
    小尺寸把箱口挖空省掉,保住白块的形状辨识度。
    """
    k = s / 100.0
    cx, cy = 50 * k, 50 * k
    hw, dv = 30 * k, 16.5 * k
    T = QPointF(cx, cy - dv * 2)
    R = QPointF(cx + hw, cy - dv)
    L = QPointF(cx - hw, cy - dv)
    M = QPointF(cx, cy)
    BL = QPointF(cx - hw, cy + dv)
    BM = QPointF(cx, cy + dv * 2)
    BR = QPointF(cx + hw, cy + dv)

    p.setPen(Qt.PenStyle.NoPen)
    for pts, a in (((T, R, M, L), 252), ((L, M, BM, BL), 170),
                   ((R, M, BM, BR), 108)):
        p.setBrush(QColor(255, 255, 255, a))
        p.drawPolygon(QPolygonF(list(pts)))

    if s >= 24:
        iw = 15.0 * k
        y0 = T.y() + 6.0 * k
        p.setBrush(QColor(24, 30, 62, 96))
        p.drawPolygon(QPolygonF([
            QPointF(T.x(), y0),
            QPointF(T.x() + iw, y0 + 8.25 * k),
            QPointF(T.x(), y0 + 16.5 * k),
            QPointF(T.x() - iw, y0 + 8.25 * k),
        ]))


VARIANTS = [
    ("box", "敞开盒子", _box),
    ("ripple", "点击波纹", _ripple),
    ("bolt", "闪电", _bolt),
    ("mouse", "鼠标", _mouse),
]


def draw_icon(p, s, variant, black=PLATE_BLACK):
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _base_plate(p, s, black=black)
    for key, _label, fn in VARIANTS:
        if key == variant:
            fn(p, s)
            return


def make_image(size, variant, black=PLATE_BLACK):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    draw_icon(p, size, variant, black=black)
    p.end()
    return img


# ============================================================================
# ICO 打包(PNG payload,Windows Vista+ 支持)
# ============================================================================

def to_png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def build_ico(images):
    blobs = [to_png_bytes(im) for im in images]
    n = len(blobs)
    out = struct.pack("<HHH", 0, 1, n)          # reserved, type=icon, count
    offset = 6 + 16 * n
    for im, blob in zip(images, blobs):
        w, h = im.width(), im.height()
        out += struct.pack(
            "<BBBBHHII",
            0 if w >= 256 else w,               # 256 记作 0
            0 if h >= 256 else h,
            0, 0, 1, 32,
            len(blob), offset,
        )
        offset += len(blob)
    return out + b"".join(blobs)


# ============================================================================
# 方案对比预览
# ============================================================================

def make_preview():
    big = 150               # 大图边长
    smalls = [64, 40, 24, 16]
    gap = 16
    pad = 24
    row_h = big + 34
    width = pad * 2 + big + 44 + sum(smalls) + gap * len(smalls) + 20
    height = pad * 2 + row_h * len(VARIANTS)

    canvas = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    # 底色用浅色 —— 图标底座已是纯黑,深灰底上黑方块会糊成一片看不清边界
    canvas.fill(QColor(232, 243, 249))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    for r, (key, label, _fn) in enumerate(VARIANTS):
        y = pad + r * row_h
        # 大图
        big_img = make_image(big, key)
        p.drawImage(pad, y + 12, big_img)
        # 小尺寸实际效果
        x = pad + big + 44
        for ss in smalls:
            im = make_image(ss, key)
            p.drawImage(int(x), int(y + 12 + (big - ss) / 2), im)
            x += ss + gap

    p.end()
    canvas.save(os.path.join(OUT, "preview.png"))
    print(f"[preview] {width}x{height}")


# ============================================================================

def main():
    make_preview()
    for key, label, _fn in VARIANTS:
        imgs = [make_image(s, key) for s in SIZES]
        data = build_ico(imgs)
        path = os.path.join(OUT, f"{key}.ico")
        with open(path, "wb") as f:
            f.write(data)
        print(f"[{key:<7}] {label:<6} {len(data):>7} bytes  -> {path}")

    # 主图标 = 敞开盒子(旧版「工具盒子」的具象;改名后保留为品牌图形)
    # 底座是纯黑,box.ico 自身即黑底,直接拿来当主图标
    with open(os.path.join(OUT, "box.ico"), "rb") as f:
        main_data = f.read()
    with open(os.path.join(OUT, "app.ico"), "wb") as f:
        f.write(main_data)
    print(f"[app.ico] 主图标已就位 ({len(main_data)} bytes · 纯黑底)")


if __name__ == "__main__":
    main()
