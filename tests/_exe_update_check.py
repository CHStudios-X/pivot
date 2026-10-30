# -*- coding: utf-8 -*-
r"""1.2.7 出包后验证：exe 里的自动更新**真能跑通**。

为什么不能只测源码：
  更新链路在 exe 里跑的是 PyInstaller 打包后的 Python 环境（urllib 的证书、
  threading、临时目录），而且真正的入口是 Qt 的页面与信号槽 —— 源码侧用
  import 调函数是绕过这些的。

做法（不碰交付产物）：
  1. 把 onedir 产物整目录复制到临时目录 A（模拟用户装好的那一份）；
  2. 把 A\apps\home.py 写成 "# OLD"，用来确认更新包里的新版真的被取到；
  3. 给 A\apps\update.py **追加一段探针**：页面建好后自动触发「检查更新」
     → 等结果 → 自动点「立即更新」→ 等下载与解压完成 → 把状态写成 JSON；
  4. 本地起 HTTP 提供 version.json 与真更新包，用 TOOLBOX_UPDATE_URL
     指给 exe，然后启动 A 里的 exe；
  5. 读 JSON 断言：新版本号正确、说明已加载、更新包已解出、功能裁剪被识别。

真正「覆盖文件」那一步由 _update_check.py 的 T8 用真实 bat 验过，
这里只验 exe 里能不能把包拿到手、解对、认对，不重启（避免测试把临时目录
里的东西换成奇怪状态）。

运行: python _exe_update_check.py
"""
import hashlib
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from _paths import app_dir as _app_dir                     # noqa: E402

APP_DIR = _app_dir()
# 更新包名带版本号，别写死 —— 升版本时脚本会静默跑空（拿不到 zip 直接假失败）
_UPDATE_DIR = os.path.join(ROOT, "dist", "update")
_zips = sorted(glob.glob(os.path.join(_UPDATE_DIR, "Pivot_*_win64.zip")))
ZIP_SRC = _zips[-1] if _zips else os.path.join(_UPDATE_DIR, "Pivot_1.3.0_win64.zip")
NEW_VER = "1.4.0"          # 比产物里的 APP_VER 高，才会被判为"有更新"
# 环境变量故意用 1.2.x 的旧名 TOOLBOX_UPDATE_URL —— 顺带验证旧配置仍然生效

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  —— {detail}" if detail else ""))


PROBE = r'''

# ================= 测试探针（仅 _exe_update_check 使用）=================
# 追加在 update.py 末尾：页面建好后自己走一遍检查 -> 下载 -> 解压，
# 把状态写进 TB_PROBE_OUT 指定的 JSON，然后关窗。
import json as _pjson
import os as _pos
from PySide6.QtCore import QTimer as _pQTimer

_orig_build = Feature._build_update


def _probe_build(self):
    page = _orig_build(self)
    _pQTimer.singleShot(700, lambda: _probe_loop(self, 0))
    return page


def _probe_kick(self):
    if self._upd_state == "idle" and self._upd_info is None:
        self._on_upd_check()


def _probe_loop(self, tick):
    out = _pos.environ.get("TB_PROBE_OUT", "")
    if tick > 400:                       # 约 120 秒还没完，先把现状写下来
        _probe_write(self, "timeout")
        return
    state = self._upd_state
    if state == "idle" and self._upd_info is None:
        _probe_kick(self)
    elif state == "idle" and self._upd_info is not None:
        self._on_upd_action()            # 开始下载
    elif state == "ready":
        _probe_write(self, "ok")
        return
    _pQTimer.singleShot(300, lambda: _probe_loop(self, tick + 1))


def _probe_write(self, status):
    out = _pos.environ.get("TB_PROBE_OUT", "")
    try:
        info = self._upd_info or {}
        payload = self._upd_payload or ""
        files, home_head = 0, ""
        if payload and _pos.path.isdir(payload):
            for root, _dirs, names in _pos.walk(payload):
                files += len(names)
            hp = _pos.path.join(payload, "apps", "home.py")
            if _pos.path.exists(hp):
                with open(hp, "r", encoding="utf-8", errors="replace") as fh:
                    home_head = fh.read(40)
        data = {
            "status": status,
            "state": self._upd_state,
            "version": info.get("version"),
            "title": self.upd_title.text(),
            "hint": self.upd_hint.text(),
            "notes_len": len(self.upd_notes.text() or ""),
            "action": self.upd_action.text(),
            "payload": payload,
            "payload_files": files,
            "payload_home_head": home_head,
            "bar": self.upd_bar.value(),
        }
        # 先在内存里序列化：写文件时才失败的话，文件是 0 字节，什么线索都没有
        text = _pjson.dumps(data, ensure_ascii=False, default=str)
    except Exception as exc:
        import traceback
        text = _pjson.dumps({"status": "probe_error", "err": repr(exc),
                             "tb": traceback.format_exc()},
                            ensure_ascii=False)
    try:
        # 先写 .part 再原子替换：主进程可能正盯着这个文件，
        # 直接 open(out,"w") 会先截断，读方容易读到空文件。
        part = out + ".part"
        with open(part, "w", encoding="utf-8") as fh:
            fh.write(text)
        _pos.replace(part, out)
    except OSError:
        pass
    _pQTimer.singleShot(150, self.close)


Feature._build_update = _probe_build
'''


class Handler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        try:
            item = self.routes.get(self.path.split("?")[0])
            if item is None:
                self.send_error(404)
                return
            body, ctype = item
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass


def main():
    if not os.path.exists(ZIP_SRC):
        print("找不到更新包：", ZIP_SRC)
        print("先跑 build.ps1 或 make_update.py")
        return 2
    if not os.path.isdir(APP_DIR):
        print("找不到产物目录：", APP_DIR)
        return 2

    tmp_root = os.path.join(HERE, "_tmp")
    os.makedirs(tmp_root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="upd_exe_", dir=tmp_root)
    app = os.path.join(tmp, "pivot")
    out_json = os.path.join(tmp, "probe.json")
    proc = None

    try:
        print("=" * 62)
        print(" 出包后验证：exe 内自动更新链路")
        print("=" * 62)
        print(f"  产物 : {APP_DIR}")
        print(f"  更新包: {os.path.getsize(ZIP_SRC) / 1024 / 1024:.1f} MB")
        print("  正在复制产物到临时目录…")
        shutil.copytree(APP_DIR, app)

        # 旧内容标记：更新包里的 home.py 是新版，替换后应该看不到这行
        with open(os.path.join(app, "apps", "home.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("# OLD-MARK 这是旧版本的功能文件\n")
        with open(os.path.join(app, "apps", "update.py"), "a",
                  encoding="utf-8") as fh:
            fh.write(PROBE)
        for junk in ("_apps_state.json",):
            p = os.path.join(app, junk)
            if os.path.exists(p):
                os.remove(p)

        # 模拟"用户在 apps\ 里删掉过 keys.py"：先落一份安装记录（本版应有的
        # 清单），再把文件删掉。更新时必须认出来，不能把它装回来。
        apps_live = os.path.join(app, "apps")
        names = sorted(n for n in os.listdir(apps_live) if n.endswith(".py"))
        with open(os.path.join(app, "_apps_state.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"version": "1.3.0", "files": names}, fh,
                      ensure_ascii=False)
        os.remove(os.path.join(apps_live, "keys.py"))

        with open(ZIP_SRC, "rb") as fh:
            blob = fh.read()
        sha = hashlib.sha256(blob).hexdigest()

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = srv.server_address[1]
        base = f"http://127.0.0.1:{port}"
        Handler.routes["/pkg.zip"] = (blob, "application/zip")
        manifest = {
            "latest": NEW_VER,
            "date": "2026-12-01",
            "notes": "测试用更新说明",
            "packages": {"full": {
                "url": f"{base}/pkg.zip",
                "size": len(blob),
                "sha256": sha,
            }},
        }
        Handler.routes["/version.json"] = (
            json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            "application/json")
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        env = dict(os.environ)
        env["TOOLBOX_UPDATE_URL"] = f"{base}/version.json"
        env["TB_PROBE_OUT"] = out_json
        env["TEMP"] = tmp
        env["TMP"] = tmp

        exe = os.path.join(app, "pivot.exe")
        print("  启动 exe（后台自动检查并下载）…")
        proc = subprocess.Popen([exe], cwd=app, env=env)

        end = time.time() + 180
        while time.time() < end:
            if os.path.exists(out_json):
                break
            time.sleep(0.5)

        if not os.path.exists(out_json):
            check("探针写出结果", False, "180 秒内没有任何结果")
            return 1

        time.sleep(0.8)
        data = None
        for _ in range(6):
            try:
                with open(out_json, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                break
            except (ValueError, OSError):
                time.sleep(0.5)
        if data is None:
            check("探针结果可解析", False, "JSON 读不出来或一直是空的")
            return 1

        if data.get("status") not in ("ok", "timeout"):
            print("  探针异常:", data.get("err"))
            print((data.get("tb") or "")[:900])
        check("探针跑完", data.get("status") == "ok",
              f"status={data.get('status')} state={data.get('state')}")
        check("识别出新版本", data.get("version") == NEW_VER,
              str(data.get("version")))
        check("新版本标题已显示", NEW_VER in (data.get("title") or ""),
              str(data.get("title")))
        check("更新说明已加载", (data.get("notes_len") or 0) > 0,
              f"{data.get('notes_len')} 字")
        check("下载完成（进度条到 100）", data.get("bar") == 100,
              f"bar={data.get('bar')}")
        check("更新包已解压", (data.get("payload_files") or 0) > 100,
              f"{data.get('payload_files')} 个文件")
        check("解出的是新版功能文件（不是本地旧那份）",
              "OLD-MARK" not in (data.get("payload_home_head") or ""),
              (data.get("payload_home_head") or "").replace("\n", " ")
              [:40])
        check("按钮变成「重启并完成更新」",
              "重启" in (data.get("action") or ""), str(data.get("action")))
        check("提示里说明了保留功能裁剪",
              "删过" in (data.get("hint") or "")
              or "裁剪" in (data.get("hint") or ""),
              str(data.get("hint"))[:60])
        keys_gone = not os.path.exists(
            os.path.join(data.get("payload") or "\0", "apps", "keys.py"))
        check("用户删掉的 keys.py 没被重新装进更新包", keys_gone)
        srv.shutdown()
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        time.sleep(0.5)

    print()
    print("=" * 62)
    print(f" 通过 {len(PASS)} / 失败 {len(FAIL)}")
    for n in FAIL:
        print("   FAIL:", n)
    print("=" * 62)
    if not FAIL:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(" 现场保留：", tmp)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
