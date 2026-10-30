# -*- coding: utf-8 -*-
"""枢功能模块 · 连点器

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
    AnimatedCounter,
    PillButton,
    PulseDot,
    SegmentedControl,
    ToggleSwitch,
)

class AutoClicker:
    def __init__(self):
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        self.click_count = 0
        self.start_count = 0
        self._last_notify = 0.0

    def start(self, mode, interval_ms, total_clicks,
              use_fixed_pos, fixed_x, fixed_y, countdown_sec=3,
              on_count_update=None, on_status_update=None):
        if self.running:
            return False
        self.stop_event.clear()
        self.click_count = 0
        self.start_count = total_clicks
        self.running = True
        self._last_notify = 0.0
        self._on_count_update = on_count_update
        self._on_status_update = on_status_update

        self.thread = threading.Thread(
            target=self._run,
            args=(mode, interval_ms, use_fixed_pos, fixed_x, fixed_y,
                  countdown_sec),
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

    def _run(self, mode, interval_ms, use_fixed_pos, fx, fy, countdown_sec):
        for i in range(countdown_sec, 0, -1):
            if self.stop_event.is_set():
                return
            if self._on_status_update:
                self._on_status_update(f"countdown:{i}")
            time.sleep(1)

        if self._on_status_update:
            self._on_status_update("running")
        interval_sec = max(0.001, interval_ms / 1000.0)

        while not self.stop_event.is_set():
            try:
                if use_fixed_pos:
                    pyautogui.moveTo(fx, fy, duration=0)
                if mode == "double":
                    pyautogui.doubleClick(button="left")
                elif mode == "right":
                    pyautogui.click(button="right")
                else:
                    pyautogui.click(button="left")

                self.click_count += 1
                # 节流:间隔可低至 1ms(1000 次/秒),不能每次都推 UI 事件
                if self._on_count_update:
                    now = time.monotonic()
                    if now - self._last_notify >= 0.05:
                        self._last_notify = now
                        self._on_count_update(self.click_count)

                if self.start_count > 0 and self.click_count >= self.start_count:
                    if self._on_count_update:
                        self._on_count_update(self.click_count)
                    if self._on_status_update:
                        self._on_status_update("done")
                    self.running = False
                    return

                slept = 0.0
                while slept < interval_sec and not self.stop_event.is_set():
                    time.sleep(min(0.02, interval_sec - slept))
                    slept += 0.02
            except pyautogui.FailSafeException:
                if self._on_status_update:
                    self._on_status_update("failsafe")
                self.running = False
                return
            except Exception as e:  # noqa: BLE001
                if self._on_status_update:
                    self._on_status_update(f"error:{e}")
                self.running = False
                return
        self.running = False


META = {
    'id': 'clicker',
    'name': '连点器',
    'nav': '连点器',
    'order': 20,
    'card': True,
    'desc': '自动点击 · 自定义间隔与次数 · 支持固定坐标',
    'icon': 'click',
    'accent': '#4da3ff',
    'ready': True,
    'builder': '_build_clicker',
    'state': 'page_clicker',
    'hotkeys': {'start': 'on_start', 'stop': 'on_stop'},
}


class Feature:
    """连点器功能页（混入 App：方法里的 self 就是 App 实例）。"""

    def _build_clicker(self):
        # 引擎跟着功能走:这个文件被删掉,外壳就不会有 macro 引擎
        self.macro = AutoClicker()
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)

        # 主体:左「配置」+ 右「控制台」,横屏双栏
        body = QHBoxLayout()
        body.setSpacing(14)

        # ---------------- 左栏:配置 ----------------
        left = QVBoxLayout()
        left.setSpacing(11)

        # --- 点击模式 ---
        mode_p, mode_lay = self._panel(spacing=10)
        mode_lay.addWidget(self._title("点击模式"))
        self.seg = SegmentedControl([
            ("左键单击", "left"),
            ("左键双击", "double"),
            ("右键单击", "right"),
        ])
        self.seg.changed.connect(self._set_mode)
        mode_lay.addWidget(self.seg)
        left.addWidget(mode_p)

        # --- 间隔 / 次数 ---
        param_p, param_lay = self._panel(spacing=10)
        param_lay.addWidget(self._title("参数"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        grid.addWidget(self._field("点击间隔 (ms)"), 0, 0)
        grid.addWidget(self._field("点击次数 (0=无限)"), 0, 1)
        self.interval_edit = QLineEdit("100")
        self.count_edit = QLineEdit("0")
        grid.addWidget(self.interval_edit, 1, 0)
        grid.addWidget(self.count_edit, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        param_lay.addLayout(grid)
        left.addWidget(param_p)

        # --- 坐标 ---
        coord_p, coord_lay = self._panel(spacing=10)
        coord_lay.addWidget(self._title("坐标"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._field("使用固定坐标"))
        row.addStretch()
        self.use_fixed = ToggleSwitch()
        row.addWidget(self.use_fixed)
        coord_lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.x_edit = QLineEdit("0")
        self.y_edit = QLineEdit("0")
        self.x_edit.setFixedWidth(92)
        self.y_edit.setFixedWidth(92)
        row2.addWidget(self._field("X"))
        row2.addWidget(self.x_edit)
        row2.addSpacing(6)
        row2.addWidget(self._field("Y"))
        row2.addWidget(self.y_edit)
        row2.addStretch()
        cap = PillButton("获取坐标", "glass")
        cap.setObjectName("coordBtn")
        cap.setMinimumHeight(40)
        cap.setFixedWidth(116)     # 去掉 📍 后收窄,免得文字两侧太空
        cap.clicked.connect(self._capture_pos)
        row2.addWidget(cap)
        coord_lay.addLayout(row2)
        left.addWidget(coord_p)

        left.addStretch(1)

        # ---------------- 右栏:控制台 ----------------
        right = QVBoxLayout()
        right.setSpacing(11)

        console_p, console_lay = self._panel(spacing=12,
                                             margins=(20, 18, 20, 18))
        # 状态指示放在控制台里 —— 它是连点器自己的状态,不该占着标题栏
        crow = QHBoxLayout()
        crow.setSpacing(8)
        crow.addWidget(self._title("已点击"))
        crow.addStretch()
        self.status_dot = PulseDot("#63e6be", 7)
        crow.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusText")
        crow.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignVCenter)
        console_lay.addLayout(crow)
        self.counter = AnimatedCounter(58, Qt.AlignmentFlag.AlignCenter)
        console_lay.addWidget(self.counter, 1)

        self.progress = QProgressBar()
        self.progress.setObjectName("progress")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        console_lay.addWidget(self.progress)

        self.target_label = QLabel("就绪 · 按 F6 开始")
        self.target_label.setObjectName("ratioText")
        self.target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        console_lay.addWidget(self.target_label)
        right.addWidget(console_p, 1)

        # --- 开始 / 停止 ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(11)
        self.start_btn = PillButton("开始  (F6)", "primary")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(56)
        self.start_btn.clicked.connect(self.on_start)
        btn_row.addWidget(self.start_btn, 3)
        self.stop_btn = PillButton("停止  (F7)", "glass")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setMinimumHeight(56)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop)
        btn_row.addWidget(self.stop_btn, 2)
        btn_w = QWidget()
        btn_w.setLayout(btn_row)
        right.addWidget(btn_w)

        body.addLayout(left, 6)
        body.addLayout(right, 5)
        lay.addLayout(body, 1)

        tip = QLabel("F6 开始 · F7 停止 · 鼠标移到屏幕左上角可紧急中止")
        tip.setObjectName("tip")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tip)

        pg._blocks = [mode_p, param_p, coord_p, console_p, btn_w, tip]
        return pg

    def _set_mode(self, v):
        self._mode = v

    def _capture_pos(self):
        self._set_status("2 秒后获取坐标…")
        if getattr(self, "_cap_timer", None) is None:
            self._cap_timer = QTimer(self)
            self._cap_timer.setSingleShot(True)
            self._cap_timer.timeout.connect(self._do_capture)
        self._cap_timer.start(2000)

    def _do_capture(self):
        x, y = pyautogui.position()
        self.x_edit.setText(str(x))
        self.y_edit.setText(str(y))
        self._set_status(f"已记录 ({x}, {y})", "#4da3ff")

    def on_start(self):
        if self._engine_running("macro"):
            return
        if self._engine_running("kbrep"):
            self._set_status("键盘连按正在运行，先停掉它", "#ffd43b")
            return
        if getattr(self, "_page", None) != "clicker":
            self.go("clicker")         # 热键触发时先把连点器页翻出来

        interval = self._to_int(self.interval_edit.text(), 100, lo=1)
        total = self._to_int(self.count_edit.text(), 0, lo=0)
        use_fixed = self.use_fixed.isChecked()
        x = self._to_int(self.x_edit.text(), 0)
        y = self._to_int(self.y_edit.text(), 0)

        # 屏幕左上角是 pyautogui FAILSAFE 危险区,自动避让
        avoid = ""
        if use_fixed and x <= 1 and y <= 1:
            x, y = 2, 2
            self.x_edit.setText(str(x))
            self.y_edit.setText(str(y))
            avoid = "  ·  左上角为安全中止区,坐标已避让"

        ok = self.macro.start(
            mode=self._mode,
            interval_ms=interval,
            total_clicks=total,
            use_fixed_pos=use_fixed,
            fixed_x=x, fixed_y=y,
            on_count_update=self.sig_count.emit,
            on_status_update=self.sig_status.emit,
        )
        if not ok:
            return

        self._progress_total = total
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(0)
            self.target_label.setText(f"目标 {total} 次 · 0%")
        else:
            self.progress.setRange(0, 0)
            self.target_label.setText("无限模式 · 按 F7 停止")

        self._pending_count = 0
        self._count_scheduled = False
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.counter.set_value(0)
        self.status_dot.set_color("#4da3ff")
        self.status_dot.start_pulse()
        self._set_status("准备中…" + avoid)
        self._set_card_running("clicker", True)
        self.countdown.start(3)

    def on_stop(self):
        self.macro.stop()

    def _queue_count(self, c):
        """主线程槽(sig_count 跨线程投递):合并刷新,防事件洪水"""
        self._pending_count = c
        if not self._count_scheduled:
            self._count_scheduled = True
            QTimer.singleShot(0, self._flush_count)

    def _flush_count(self):
        self._count_scheduled = False
        v = self._pending_count
        self.counter.set_value(v)
        if self._progress_total > 0:
            done = min(v, self._progress_total)
            self.progress.setValue(done)
            pct = int(done * 100 / self._progress_total)
            self.target_label.setText(f"目标 {self._progress_total} 次 · {pct}%")

    def _handle_status(self, s):
        if s.startswith("countdown:"):
            n = self._to_int(s.split(":", 1)[1], 0)
            self._set_status(f"倒计时 {n} 秒")
            self.countdown.update_to(n)
        elif s == "running":
            self.countdown.finish()
            self._set_status("运行中…", "#4da3ff")
        elif s == "done":
            self._pending_count = self.macro.click_count
            self._flush_count()
            self._reset(f"完成 · 共 {self.macro.click_count} 次", "#63e6be")
        elif s == "failsafe":
            self._reset("已中止(鼠标到达左上角)", "#ffd43b")
        elif s.startswith("error"):
            self._reset(f"异常: {s.split(':', 1)[1]}", "#ff6b6b")
        elif s == "已停止":
            self._pending_count = self.macro.click_count
            self._flush_count()
            self._reset("已停止")

    def _reset(self, text, color=None):
        self._set_status(text, color)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # 进度条常驻显示(避免布局跳动),归位为空白轨道
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self._progress_total = 0
        done = self.macro.click_count
        self.target_label.setText(
            f"共完成 {done} 次" if done > 0 else "就绪 · 按 F6 开始")
        self.countdown.cancel()
        self.status_dot.stop_pulse()
        self.status_dot.set_color("#63e6be")
        self._set_card_running("clicker", False)
