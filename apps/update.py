# -*- coding: utf-8 -*-
"""枢功能模块 · 更新

契约（外壳靠这些约定装载本模块）：
  META     功能元信息：id / name / nav(底栏文案) / card(主页是否出卡片) /
           order(排序) / builder(构建页面的方法名) / state(页面挂在哪个属性)
  Feature  混入 App 的类。方法里的 self 就是 App 实例。

删除本文件后：底栏与主页少了「更新」这一项，启动时的静默检测仍然照常
（那部分在 updater_core.py 里，不依赖本文件），只是没有手动入口。

真正干活的逻辑全在 updater_core.py —— 这样"能不能更新"不取决于某个
可选功能模块在不在。
"""

import os
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

import updater_core as U
from pivot_kit import APP_VER, PillButton


META = {
    'id': 'update',
    'name': '更新',
    'nav': '更新',
    'order': 70,
    'card': False,
    'desc': '',
    'icon': 'update',
    'accent': '#37b24d',
    'ready': True,
    'builder': '_build_update',
    'state': 'page_update',
}


class _Bridge(QObject):
    """把工作线程的结果送回主线程。

    跨线程直接碰 Qt 控件是不允许的，但 emit 一个信号是安全的
    （接收方会自动排回住线程的事件循环）。
    """

    checked = Signal(object, str)        # info|None, 错误说明
    progress = Signal(int, int)          # 已下载字节, 总字节
    fetched = Signal(bool, str)          # 下载是否成功, 错误
    staged = Signal(bool, str, str)      # 解压是否成功, 说明, payload 目录


def _human(n):
    return U._fmt_size(n)                # noqa: SLF001  同一套格式化，别写两遍


class Feature:
    """更新功能页（混入 App：方法里的 self 就是 App 实例）。"""

    # ---------- 构建 ----------
    def _build_update(self):
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)

        # 状态
        self._upd_state = "idle"
        self._upd_info = None
        self._upd_work = None
        self._upd_payload = None
        self._upd_cancel = False

        self._upd_bridge = _Bridge()
        self._upd_bridge.checked.connect(self._on_upd_checked)
        self._upd_bridge.progress.connect(self._on_upd_progress)
        self._upd_bridge.fetched.connect(self._on_upd_fetched)
        self._upd_bridge.staged.connect(self._on_upd_staged)

        panel, pl = self._panel(spacing=12, margins=(20, 16, 20, 18))
        head = QHBoxLayout()
        head.addWidget(self._title("更新"))
        head.addStretch()
        src = QLabel("更新源：" + ("已配置" if self._upd_source_ready()
                                   else "未配置"))
        src.setObjectName("pageHint")
        head.addWidget(src)
        pl.addLayout(head)

        pl.addWidget(self._kv("当前版本", APP_VER))
        pl.addWidget(self._kv(
            "打包方式",
            "目录版（支持自动替换）" if U.is_frozen() else "源码模式（只能检测）"))

        row = QHBoxLayout()
        row.setSpacing(12)
        self.upd_btn = PillButton("检查更新", "primary")
        self.upd_btn.setFixedSize(112, 34)
        self.upd_btn.clicked.connect(self._on_upd_check)
        row.addWidget(self.upd_btn, 0)
        self.upd_hint = QLabel("启动时会自动检查一次；也可以随时手动检查。")
        self.upd_hint.setObjectName("pageHint")
        self.upd_hint.setWordWrap(True)
        row.addWidget(self.upd_hint, 1)
        pl.addLayout(row)

        # ---- 新版本信息（默认隐藏）----
        self.upd_box = QWidget()
        bl = QVBoxLayout(self.upd_box)
        bl.setContentsMargins(0, 4, 0, 0)
        bl.setSpacing(9)

        self.upd_title = QLabel()
        self.upd_title.setObjectName("toolName")
        bl.addWidget(self.upd_title)

        self.upd_notes = QLabel()
        self.upd_notes.setObjectName("pageHint")
        self.upd_notes.setWordWrap(True)
        bl.addWidget(self.upd_notes)

        self.upd_bar = QProgressBar()
        self.upd_bar.setRange(0, 100)
        self.upd_bar.setValue(0)
        self.upd_bar.setTextVisible(False)
        self.upd_bar.setFixedHeight(6)
        self.upd_bar.setStyleSheet(
            "QProgressBar{background:rgba(0,0,0,26);border:none;"
            "border-radius:3px}"
            "QProgressBar::chunk{background:#4da3ff;border-radius:3px}")
        self.upd_bar.setVisible(False)
        bl.addWidget(self.upd_bar)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.upd_action = PillButton("立即更新", "primary")
        self.upd_action.setFixedSize(150, 34)
        self.upd_action.clicked.connect(self._on_upd_action)
        bottom.addWidget(self.upd_action, 0)
        self.upd_note2 = QLabel("")
        self.upd_note2.setObjectName("pageHint")
        self.upd_note2.setWordWrap(True)
        bottom.addWidget(self.upd_note2, 1)
        bl.addLayout(bottom)

        self.upd_box.setVisible(False)
        pl.addWidget(self.upd_box)

        lay.addWidget(panel)
        lay.addStretch(1)
        pg._blocks = [panel]
        return pg

    # ---------- 小工具 ----------
    @staticmethod
    def _upd_source_ready():
        url = U.manifest_url()
        return bool(url) and "REPLACE_ME" not in url

    def _upd_set_hint(self, text, color=None):
        self.upd_hint.setText(text)
        self.upd_hint.setStyleSheet(f"color:{color}" if color else "")

    # ---------- 检查 ----------
    def _on_upd_check(self):
        if self._upd_state in ("checking", "downloading", "staging"):
            return
        self._upd_state = "checking"
        self.upd_btn.setEnabled(False)
        self.upd_box.setVisible(False)
        self._upd_set_hint("正在连接更新服务器…", "#4da3ff")
        threading.Thread(target=self._upd_do_check, daemon=True).start()

    def _upd_do_check(self):
        info, err = U.check_for_update(APP_VER)
        self._upd_bridge.checked.emit(info, err)

    def _on_upd_checked(self, info, err):
        self._upd_state = "idle"
        self.upd_btn.setEnabled(True)
        if err:
            self._upd_set_hint(err, "#c92a2a")
            self._set_status("检查更新失败：" + err, "#ffd43b")
            return
        if not info:
            self._upd_set_hint(f"已是最新版本（{APP_VER}）", "#2b8a3e")
            self._set_status("已是最新版本", "#4da3ff")
            return

        self._upd_info = info
        self.upd_box.setVisible(True)
        self.upd_title.setText(f"新版本 {info['version']} 可用")

        bits = [f"当前 {APP_VER}"]
        if info.get("date"):
            bits.append(info["date"])
        bits.append(_human(info["size"]) if info["size"] else "大小未知")
        if info.get("mandatory"):
            bits.append("此版本要求必须更新")
        self._upd_set_hint(" · ".join(bits), "#1c7ed6")

        notes = info.get("notes") or "（本次更新没有附带说明）"
        self.upd_notes.setText(notes)

        self.upd_bar.setVisible(False)
        self.upd_bar.setValue(0)
        self.upd_action.setText(f"立即更新（{_human(info['size'])}）"
                                if info["size"] else "立即更新")
        self.upd_note2.setText(
            "" if U.is_frozen()
            else "源码模式下只做检测，不会替换文件。")
        self._set_status(f"发现新版本 {info['version']}", "#4da3ff")

    # ---------- 下载 / 解压 / 重启 ----------
    def _on_upd_action(self):
        if self._upd_state == "downloading":
            self._upd_cancel = True
            self.upd_action.setEnabled(False)
            self._upd_set_hint("正在取消…")
            return
        if self._upd_state == "ready":
            self._on_upd_restart()
            return
        if self._upd_state in ("checking", "staging") or not self._upd_info:
            return
        self._upd_start_download()

    def _upd_start_download(self):
        info = self._upd_info
        self._upd_cancel = False
        self._upd_state = "downloading"
        self._upd_work = U.work_dir_for(info["version"])
        zip_path = os.path.join(self._upd_work, "pkg.zip")
        self.upd_bar.setVisible(True)
        self.upd_bar.setValue(0)
        self.upd_action.setText("取消")
        self.upd_action.setEnabled(True)
        self._upd_set_hint("准备下载…", "#4da3ff")
        threading.Thread(target=self._upd_do_fetch,
                         args=(info, zip_path), daemon=True).start()

    def _upd_do_fetch(self, info, zip_path):
        ok, err = U.download(
            info["url"], zip_path,
            sha256=info.get("sha256") or None,
            size=info.get("size") or None,
            on_progress=lambda d, t: self._upd_bridge.progress.emit(d, t),
            cancel=lambda: self._upd_cancel)
        self._upd_bridge.fetched.emit(ok, err)

    def _on_upd_progress(self, done, total):
        if self._upd_state != "downloading":
            return
        if total:
            self.upd_bar.setValue(min(100, int(done * 100 / total)))
            self._upd_set_hint(
                f"下载中 {_human(done)} / {_human(total)}", "#4da3ff")
        else:
            self._upd_set_hint(f"下载中 {_human(done)}", "#4da3ff")

    def _on_upd_fetched(self, ok, err):
        if not ok:
            self._upd_state = "idle"
            self.upd_action.setEnabled(True)
            self.upd_action.setText("重新下载")
            self.upd_bar.setVisible(False)
            self._upd_set_hint(err, "#c92a2a")
            self._set_status("更新包下载失败", "#ffd43b")
            return
        self._upd_state = "staging"
        self.upd_action.setEnabled(False)
        self._upd_set_hint("校验通过，正在解压…", "#4da3ff")
        threading.Thread(target=self._upd_do_stage, daemon=True).start()

    def _upd_do_stage(self):
        work = self._upd_work
        target = U.app_dir()
        live = os.path.join(target, "apps")
        state = U.read_apps_state(target)
        installed = state["files"] if state else None
        try:
            payload, count, removed, trimmed = U.stage_payload(
                os.path.join(work, "pkg.zip"), work, live, installed)
        except Exception as e:                              # noqa: BLE001
            self._upd_bridge.staged.emit(
                False, f"解压失败：{type(e).__name__}: {e}", "")
            return
        msg = f"已解出 {count} 个文件"
        if removed:
            msg += f"；你删过 {len(removed)} 个功能，本次不会装回来"
        elif trimmed:
            msg += "；保留了你的功能裁剪"
        self._upd_bridge.staged.emit(True, msg, payload)

    def _on_upd_staged(self, ok, msg, payload):
        self.upd_action.setEnabled(True)
        if not ok:
            self._upd_state = "idle"
            self.upd_action.setText("重新下载")
            self._upd_set_hint(msg, "#c92a2a")
            return
        self._upd_state = "ready"
        self._upd_payload = payload
        self.upd_bar.setValue(100)
        self._upd_set_hint(msg + "。点下面按钮重启完成更新。", "#2b8a3e")
        self.upd_action.setText("重启并完成更新")

    def _on_upd_restart(self):
        if not self._upd_payload:
            return
        if not U.is_frozen():
            self._set_status("源码模式不执行自动替换", "#ffd43b")
            return
        target = U.app_dir()
        exe = os.path.basename(os.path.abspath(sys.executable))
        work = self._upd_work
        try:
            bat, log = U.make_update_script(
                work, target, self._upd_payload, exe,
                wait_pid=os.getpid(), restart=True)
            U.launch_update_script(
                bat, target, self._upd_payload, exe,
                wait_pid=os.getpid(), restart=True, log_path=log)
        except Exception as e:                              # noqa: BLE001
            self._set_status(f"启动更新脚本失败：{e}", "#ffd43b")
            return
        self._set_status("正在重启完成更新…（约 3 秒后自动打开）", "#4da3ff")
        self._upd_state = "restarting"
        self.upd_action.setEnabled(False)
        QTimer.singleShot(400, self.close)
