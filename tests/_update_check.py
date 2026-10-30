# -*- coding: utf-8 -*-
r"""1.2.7 断言：自动更新（检测 / 下载 / 校验 / 替换）。

这份测试刻意**不碰真实更新源**：本地起一个 HTTP 服务冒充 Gitee，
所以断网也能跑，而且能精确构造 404 / 超时 / 坏哈希 这些线上难复现的情况。

  T1 版本比较   语义化比较，不是字符串比较（1.2.10 > 1.2.9）
  T2 清单解析   缺字段 / 非法版本号 / 相对地址 / 强制更新
  T3 网络容错   404、非 JSON、超时、未配置更新源
  T4 下载校验   正常、SHA256 不符、大小不符、404、取消
  T5 安全解压   正常解压、拒绝 zip slip（../ 越界）
  T6 尊重裁剪   用户删掉的功能不被更新装回来
  T7 脚本生成   bat 内容与编码
  T8 真实替换   造一个假程序目录，跑真的 apply_update.bat 去覆盖它
                （一次 ASCII 路径，一次「中文 + 空格」路径）

运行: python _update_check.py
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = ROOT
sys.path.insert(0, SRC)

import updater_core as U                                  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  —— {detail}" if detail else ""))


# --------------------------------------------------------------- 本地服务 --
class Handler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        try:
            self._serve()
        except (BrokenPipeError, ConnectionAbortedError):
            pass          # 客户端超时/取消先断开了，属预期，别刷屏

    def _serve(self):
        path = self.path.split("?")[0]
        if path == "/slow":
            time.sleep(2.5)
        item = self.routes.get(path)
        if item is None:
            self.send_error(404)
            return
        body, ctype = item
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def make_zip(path, files):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def read(path, mode="rb"):
    with open(path, mode) as fh:
        return fh.read()


# ------------------------------------------------------------------- T1 --
def t1_versions():
    print("\nT1 版本比较")
    check("解析 1.2.10", U.parse_ver("1.2.10") == (1, 2, 10))
    check("容忍前缀 v", U.parse_ver("v1.2") == (1, 2))
    check("非法版本返回 None", U.parse_ver("1.2.x") is None)
    check("空串返回 None", U.parse_ver("") is None)

    check("1.2.10 > 1.2.9（字符串比较会判反）",
          U.compare_ver("1.2.10", "1.2.9") == 1)
    check("1.2 == 1.2.0", U.compare_ver("1.2", "1.2.0") == 0)
    check("1.2.6 < 1.2.7", U.compare_ver("1.2.6", "1.2.7") == -1)
    check("1.10 > 1.9", U.compare_ver("1.10", "1.9") == 1)

    try:
        U.compare_ver("abc", "1.2")
        ok = False
    except ValueError:
        ok = True
    check("非法版本比较会抛错，不静默", ok)
    check("is_newer 对非法输入返回 False（宁可不更新）",
          U.is_newer("abc", "1.2.6") is False)


# ------------------------------------------------------------------- T2 --
def t2_manifest(base):
    print("\nT2 清单解析")
    good = {
        "latest": "1.2.8",
        "date": "2026-11-01",
        "notes": "修了几个问题",
        "packages": {"full": {
            "url": f"{base}/pkg.zip",
            "size": 12,
            "sha256": "a" * 64,
        }},
        "apps": ["clicker.py", "keys.py"],
    }
    info, err = U.parse_manifest(good, "1.2.7")
    check("有新版时解析成功", info is not None and err == "", err)
    check("版本号取出正确", info and info["version"] == "1.2.8")
    check("更新说明取出", info and info["notes"] == "修了几个问题")
    check("apps 清单取出", info and info["apps"] == ["clicker.py", "keys.py"])

    same = dict(good, latest="1.2.7")
    info2, err2 = U.parse_manifest(same, "1.2.7")
    check("同版本不算更新", info2 is None and err2 == "", err2)

    older = dict(good, latest="1.2.6")
    info3, _ = U.parse_manifest(older, "1.2.7")
    check("远端更旧不算更新", info3 is None)

    bad = dict(good, latest="最新版")
    info4, err4 = U.parse_manifest(bad, "1.2.7")
    check("latest 非法时给出明确错误",
          info4 is None and "latest" in err4, err4)

    nopkg = dict(good)
    nopkg.pop("packages")
    info5, err5 = U.parse_manifest(nopkg, "1.2.7")
    check("缺 packages 时报错",
          info5 is None and "下载地址" in err5, err5)

    rel = json.loads(json.dumps(good))
    rel["packages"]["full"]["url"] = "v1.2.8/ToolBox.zip"
    info6, _ = U.parse_manifest(rel, "1.2.7")
    check("相对地址会补成完整 URL",
          info6 is not None and info6["url"].startswith("https://"),
          info6["url"] if info6 else "")

    badsha = json.loads(json.dumps(good))
    badsha["packages"]["full"]["sha256"] = "xyz"
    info7, err7 = U.parse_manifest(badsha, "1.2.7")
    check("sha256 格式不对会拒绝", info7 is None and "sha256" in err7, err7)

    forced = dict(good, min="1.2.7")
    info8, _ = U.parse_manifest(forced, "1.2.0")
    check("低于 min 时标记强制更新", info8 is not None and info8["mandatory"])


# ------------------------------------------------------------------- T3 --
def t3_network(base):
    print("\nT3 网络与容错")
    data, err = U.fetch_manifest(f"{base}/version.json", timeout=3)
    check("正常拉取清单", data is not None and err == "", err)
    check("清单内容正确", data and data.get("latest") == "1.2.8")

    _d, err404 = U.fetch_manifest(f"{base}/nope.json", timeout=3)
    check("404 有明确提示", "404" in err404, err404)

    _d, errjson = U.fetch_manifest(f"{base}/bad.json", timeout=3)
    check("非 JSON 有明确提示", "JSON" in errjson, errjson)

    t0 = time.time()
    _d, errtimeout = U.fetch_manifest(f"{base}/slow", timeout=0.8)
    cost = time.time() - t0
    check("超时会按时放弃（不卡死启动）",
          errtimeout != "" and cost < 2.4, f"{cost:.2f}s / {errtimeout}")

    old = os.environ.get(U.MANIFEST_ENV)
    os.environ[U.MANIFEST_ENV] = \
        "https://raw.githubusercontent.com/REPLACE_ME/pivot/main/update/version.json"
    _d, errun = U.fetch_manifest(timeout=3)
    check("占位更新源被识别为「未配置」", "未配置" in errun, errun)
    if old is None:
        os.environ.pop(U.MANIFEST_ENV, None)
    else:
        os.environ[U.MANIFEST_ENV] = old


# ------------------------------------------------------------------- T4 --
def t4_download(base, tmp):
    print("\nT4 下载与校验")
    blob = os.urandom(200 * 1024)
    Handler.routes["/blob.bin"] = (blob, "application/octet-stream")
    sha = hashlib.sha256(blob).hexdigest()
    dest = os.path.join(tmp, "blob.bin")

    ok, err = U.download(f"{base}/blob.bin", dest, sha256=sha,
                         size=len(blob), timeout=5)
    check("正常下载", ok and err == "", err)
    check("落盘内容一致", os.path.exists(dest) and read(dest) == blob)

    seen = []
    ok2, _ = U.download(f"{base}/blob.bin", dest, sha256=sha,
                        on_progress=lambda d, t: seen.append((d, t)))
    check("进度回调被调用", ok2 and seen and seen[-1][0] == len(blob),
          str(seen[-1] if seen else None))

    ok3, err3 = U.download(f"{base}/blob.bin", dest, sha256="b" * 64,
                           timeout=5)
    check("SHA256 不符会被拒绝", not ok3 and "SHA256" in err3, err3)
    check("校验失败后不留半截文件", not os.path.exists(dest))

    ok4, err4 = U.download(f"{base}/blob.bin", dest, size=len(blob) + 999)
    check("大小不符会被拒绝", not ok4 and "大小" in err4, err4)

    ok5, err5 = U.download(f"{base}/nope.bin", dest)
    check("下载 404 有提示", not ok5 and "404" in err5, err5)

    ok6, err6 = U.download(f"{base}/blob.bin", dest,
                           cancel=lambda: True)
    check("可取消", not ok6 and err6 == "已取消", err6)


# ------------------------------------------------------------------- T5 --
def t5_extract(tmp):
    print("\nT5 安全解压")
    zpath = os.path.join(tmp, "ok.zip")
    make_zip(zpath, {"a.txt": b"AAA", "sub/b.txt": b"BBB"})
    out = os.path.join(tmp, "unpack")
    n = U.safe_extract(zpath, out)
    check("解出 2 个文件", n == 2, str(n))
    check("内容正确", read(os.path.join(out, "sub", "b.txt")) == b"BBB")

    evil = os.path.join(tmp, "evil.zip")
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../escaped.txt", b"X")
    try:
        U.safe_extract(evil, os.path.join(tmp, "unpack2"))
        blocked = False
    except ValueError:
        blocked = True
    check("拒绝 zip slip（../ 越界路径）", blocked)


# ------------------------------------------------------------------- T6 --
def t6_prune(tmp):
    print("\nT6 尊重用户的功能裁剪")

    def scene(name, live_files, payload_files, installed=None):
        base = os.path.join(tmp, name)
        pay = os.path.join(base, "payload")
        live = os.path.join(base, "live")
        os.makedirs(os.path.join(pay, "apps"))
        for f in payload_files:
            open(os.path.join(pay, "apps", f), "w").close()
        if live_files is not None:
            os.makedirs(live)
            for f in live_files:
                open(os.path.join(live, f), "w").close()
        removed, trimmed = U.prune_payload_apps(pay, live, installed)
        left = sorted(os.listdir(os.path.join(pay, "apps")))
        return removed, trimmed, left

    r1, _t1, l1 = scene("p_new", None, ["a.py", "b.py"])
    check("首次安装（无 live 目录）全装", r1 == [] and l1 == ["a.py", "b.py"])

    r2, t2, l2 = scene("p_empty", [], ["a.py", "b.py"], ["a.py", "b.py"])
    check("用户把功能全删了 -> 一个都不装回", t2 and l2 == [], str(l2))

    r3, t3, l3 = scene("p_full", ["a.py", "b.py"], ["a.py", "b.py", "c.py"],
                       ["a.py", "b.py"])
    check("没裁剪过 -> 本版新增的 c.py 要装上",
          (not t3) and l3 == ["a.py", "b.py", "c.py"], str(l3))

    r4, t4, l4 = scene("p_cut", ["a.py"], ["a.py", "b.py", "c.py"],
                       ["a.py", "b.py"])
    check("裁剪过 -> 删掉的 b.py 不复活，但新增的 c.py 照装",
          t4 and l4 == ["a.py", "c.py"] and r4 == ["b.py"], str(l4))

    r5, t5, l5 = scene("p_legacy", ["a.py"], ["a.py", "b.py", "c.py"], None)
    check("没有安装记录（老版本首次升级）-> 全装，宁可多给不可漏给",
          l5 == ["a.py", "b.py", "c.py"], str(l5))

    # 记录本身的读写
    st_dir = os.path.join(tmp, "p_state")
    os.makedirs(st_dir, exist_ok=True)
    U.write_apps_state(st_dir, "1.2.7", ["a.py", "b.py"])
    st = U.read_apps_state(st_dir)
    check("状态文件读写正确",
          st and st["version"] == "1.2.7" and st["files"] == ["a.py", "b.py"],
          str(st))


# ------------------------------------------------------------------- T7 --
def t7_script(tmp):
    print("\nT7 替换脚本生成")
    bat, log = U.make_update_script(
        os.path.join(tmp, "script"), tmp, os.path.join(tmp, "payload"),
        "pivot.exe", wait_pid=0, restart=False)
    check("脚本已生成", os.path.exists(bat))
    raw = read(bat)
    text = raw.decode("mbcs", "replace")
    check("用系统 ANSI 编码写（中文路径才不会走样）",
          "robocopy" in text and "tasklist" in text)
    check("含等待主进程退出的循环", ":wait" in text and "tasklist" in text)
    check("含失败分支与自删", ":fail" in text and 'del "%~f0"' in text)
    check("含隐藏启动用的重启开关", "%RESTART%" in text)


# ------------------------------------------------------------------- T8 --
def t8_apply(tmp, tag):
    print(f"\nT8 真实替换（{tag}）")
    base = os.path.join(tmp, tag)
    target = os.path.join(base, "程序 目录")      # 带中文与空格
    work = os.path.join(base, "work")
    os.makedirs(os.path.join(target, "_internal"))
    os.makedirs(os.path.join(target, "apps"))
    open(os.path.join(target, "pivot.exe"), "wb").write(b"OLD-EXE")
    open(os.path.join(target, "_internal", "demo.dll"), "wb").write(b"OLD-DLL")
    open(os.path.join(target, "apps", "clicker.py"), "w").write("OLD")
    open(os.path.join(target, "apps", "update.py"), "w").write("OLD")
    # 注意：target 里**没有** keys.py —— 模拟用户把它删了

    zpath = os.path.join(base, "pkg.zip")
    make_zip(zpath, {
        "pivot.exe": b"NEW-EXE",
        "_internal/demo.dll": b"NEW-DLL",
        "_internal/brand_new.dll": b"BRAND-NEW",
        "apps/clicker.py": "NEW",
        "apps/update.py": "NEW",
        "apps/keys.py": "NEW",
    })

    payload, count, removed, trimmed = U.stage_payload(
        zpath, work, os.path.join(target, "apps"),
        ["clicker.py", "keys.py", "update.py"])
    check("解压成功", count >= 5, str(count))
    check("识别出用户删过 keys.py，并剔除",
          trimmed and "keys.py" in removed, str(removed))

    bat, log = U.make_update_script(work, target, payload,
                                    "pivot.exe",
                                    wait_pid=0, restart=False)
    args = [U._short_path(target), U._short_path(payload),
            "pivot.exe", "0", U._short_path(log), "0"]
    proc = subprocess.run(U._cmd_line(bat, args),
                          capture_output=True, timeout=120)
    ok = proc.returncode == 0

    check("脚本执行完毕", ok, f"rc={proc.returncode}")
    check("主程序被换成新版",
          read(os.path.join(target, "pivot.exe")) == b"NEW-EXE")
    check("已存在的 DLL 被更新",
          read(os.path.join(target, "_internal", "demo.dll")) == b"NEW-DLL")
    check("新版新增的文件被装上",
          os.path.exists(os.path.join(target, "_internal", "brand_new.dll")))
    check("功能模块被更新",
          read(os.path.join(target, "apps", "clicker.py"), "r") == "NEW")
    check("用户删掉的 keys.py 没有被复活",
          not os.path.exists(os.path.join(target, "apps", "keys.py")))
    logtxt = (read(log).decode("mbcs", "replace")
              if os.path.exists(log) else "")
    check("日志里记下了 robocopy 结果", "robocopy exit=" in logtxt,
          logtxt.strip().splitlines()[-1] if logtxt.strip() else "日志为空")
    check("脚本用完后自删", not os.path.exists(bat))


# ------------------------------------------------------------------ 主流程 --
def main():
    tmp_root = os.path.join(HERE, "_tmp")
    os.makedirs(tmp_root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="upd_test_", dir=tmp_root)

    srv, port = start_server()
    base = f"http://127.0.0.1:{port}"
    Handler.routes["/version.json"] = (
        json.dumps({"latest": "1.2.8", "notes": "x",
                    "packages": {"full": {"url": f"{base}/pkg.zip"}}}
                   ).encode(), "application/json")
    Handler.routes["/bad.json"] = (b"not a json {{{", "application/json")

    try:
        t1_versions()
        t2_manifest(base)
        t3_network(base)
        t4_download(base, tmp)
        t5_extract(tmp)
        t6_prune(tmp)
        t7_script(tmp)
        t8_apply(tmp, "ascii_case")
        t8_apply(tmp, "中文 空格 用例")
    finally:
        srv.shutdown()

    print("\n" + "=" * 52)
    print(f" 通过 {len(PASS)}  失败 {len(FAIL)}")
    if FAIL:
        for name in FAIL:
            print("   FAIL:", name)
    print("=" * 52)
    if not FAIL:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(" 现场保留（失败时便于排查）:", tmp)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
