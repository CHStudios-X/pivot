# -*- coding: utf-8 -*-
"""枢 Pivot · 更新内核（检测 / 下载 / 校验 / 应用）。

★ 这个文件**不 import PySide6**，所以可以在无界面环境里单独测。
  界面与入口在 apps/update.py，启动时的静默检测由外壳调用这里。

它是基础设施，和 pivot_kit.py 一样**不要删**：删了外壳就起不来。
放在 apps/ 外面是有意的 —— 用户可能把 apps/ 里删空，但"检查更新"这件事
属于程序自身，不该跟着某个可选功能一起消失。

---- 更新源 --------------------------------------------------------------
指向 GitHub 上的 CHStudios-X/pivot 仓库。**fork 或换仓库时改下面两处**即可
（留占位符也不会崩：检测时会明确提示"更新源尚未配置"，而不是假装"已是最新"）：

    UPDATE_MANIFEST_URLS  version.json 的多个地址，按顺序尝试，第一个成功即用
    UPDATE_BASE_URLS      Release 附件的下载前缀，同样按顺序回退

**为什么清单要多个地址**：`raw.githubusercontent.com` 在中国大陆不可达，
而 GitHub 内容在国内只能靠 CDN 绕过去。所以清单优先走 jsDelivr
（`fastly` 节点实测国内可连，0.4 s 左右），raw 只作海外兜底。

**jsDelivr 有约 12 小时缓存**，发版后新清单不会立刻生效。要马上生效，
用浏览器打开下面这个地址触发刷新（命令行里 purge.jsdelivr.net 有时不通）：

    https://purge.jsdelivr.net/gh/CHStudios-X/pivot@main/update/version.json

步骤：仓库根建 update/ 目录放 version.json（随提交走 CDN/raw），
      每次发版把它指向新的 Release 附件，见 docs/PUBLISH.md。

也可以在**不重新打包**的前提下用环境变量覆盖（测试/内网分发用）：

    set PIVOT_UPDATE_URL=http://127.0.0.1:8000/version.json
    （1.2.x 的旧名 TOOLBOX_UPDATE_URL 仍然认，新名优先）

---- 清单格式（version.json）---------------------------------------------
{
  "latest": "1.2.7",
  "min":    "1.2.0",          # 可选：低于它则强制更新
  "date":   "2026-10-30",
  "notes":  "修复了……",
  "packages": {
    "full": {"url": "v1.3.0/Pivot_1.3.0_win64.zip",
             "size": 38274816, "sha256": "……"}
  },
  "apps": ["appearance.py", "clicker.py", ...]   # 本版全量的功能模块
}

---- 为什么更新要靠一个 .bat ---------------------------------------------
Windows 锁住正在运行的 exe 与已映射的 DLL（python313.dll / Qt6*.dll），
主程序**无法**覆盖自己。所以：主程序生成脚本 → 启动脚本 → 立刻退出；
脚本等 PID 消失后再 robocopy 覆盖 → 重新拉起新版本 → 自删。
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

IS_WIN = os.name == "nt"

# ---- 更新源（fork 后改成你自己的账号/仓库） ---------------------------
# 清单：按顺序尝试，第一个拿到合法 JSON 的就用。
# jsDelivr 的 fastly 节点在国内实测可达（~0.4 s）；raw 直连国内不通，只当海外兜底。
UPDATE_MANIFEST_URLS = (
    "https://fastly.jsdelivr.net/gh/CHStudios-X/pivot@main/update/version.json",
    "https://jsdelivr.b-cdn.net/gh/CHStudios-X/pivot@main/update/version.json",
    "https://raw.githubusercontent.com/CHStudios-X/pivot/main/update/version.json",
)

# 更新包：按顺序尝试。目前只有 GitHub Releases 一处 ——
# 第三方下载加速站在 2026-10 实测全部失效（404/000），加进去只会拖慢失败。
# 将来接了 Gitee / 自建镜像，往这个元组里加一行就行，其余代码不用动。
UPDATE_BASE_URLS = (
    "https://github.com/CHStudios-X/pivot/releases/download",
)

# 兼容旧名：外部脚本或 fork 可能只改这两个单值常量。
# 只要它们被改成了别的地址，就以单值为准（见 _manifest_candidates / _base_candidates）。
UPDATE_MANIFEST_URL = UPDATE_MANIFEST_URLS[0]
UPDATE_BASE_URL = UPDATE_BASE_URLS[0]

MANIFEST_ENV = "PIVOT_UPDATE_URL"       # 覆盖清单地址（测试用）
# 1.2.x 叫 TOOLBOX_UPDATE_URL，旧脚本/旧批处理还认它（新名优先）
LEGACY_MANIFEST_ENV = "TOOLBOX_UPDATE_URL"
CHUNK = 64 * 1024
UA = "Pivot-Updater"


class UpdateCancelled(Exception):
    """用户中途取消下载。"""


# ---------------------------------------------------------------- 版本号 --
_VER_RE = re.compile(r"^\d+(?:\.\d+)*$")


def parse_ver(text):
    """'1.2.10' -> (1, 2, 10)；不合法返回 None。

    注意：**不要**直接比较字符串 —— "1.2.10" < "1.2.9" 在字符串语义下成立，
    但版本语义相反，照着写会让 1.2.10 永远推不下去。
    """
    s = str(text or "").strip().lstrip("vV")
    if not _VER_RE.match(s):
        return None
    return tuple(int(x) for x in s.split("."))


def compare_ver(a, b):
    """a>b 返回 1，相等 0，a<b 返回 -1；任一不合法抛 ValueError。"""
    pa, pb = parse_ver(a), parse_ver(b)
    if pa is None:
        raise ValueError(f"版本号不合法: {a!r}")
    if pb is None:
        raise ValueError(f"版本号不合法: {b!r}")
    n = max(len(pa), len(pb))
    pa = pa + (0,) * (n - len(pa))       # 1.2 == 1.2.0
    pb = pb + (0,) * (n - len(pb))
    return (pa > pb) - (pa < pb)


def is_newer(remote, local):
    """remote 是否比 local 新；版本号有问题时一律当"不是"。"""
    try:
        return compare_ver(remote, local) > 0
    except ValueError:
        return False


# ------------------------------------------------------------ 运行位置 --
def is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """程序所在目录（onedir 下就是 exe 那层，含 _internal\\）。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _manifest_candidates():
    """清单地址候选，按优先级排列。环境变量覆盖时只保留那一个。"""
    env = (os.environ.get(MANIFEST_ENV)
           or os.environ.get(LEGACY_MANIFEST_ENV) or "").strip()
    if env:
        return [env]
    urls = UPDATE_MANIFEST_URLS
    if isinstance(urls, str):
        urls = (urls,)
    out = [u.strip() for u in (urls or ()) if (u or "").strip()]
    # fork 的人可能只改了单值常量 UPDATE_MANIFEST_URL，那就把它排到最前面
    single = (UPDATE_MANIFEST_URL or "").strip()
    if single and single not in out:
        out.insert(0, single)
    return out


def manifest_urls():
    """全部候选清单地址（第一个是最优选择）。"""
    return _manifest_candidates()


def manifest_url():
    """首个候选地址 —— 界面与日志只需要展示一个。"""
    urls = manifest_urls()
    return urls[0] if urls else ""


def _base_candidates():
    """更新包下载前缀候选。"""
    bs = UPDATE_BASE_URLS
    if isinstance(bs, str):
        bs = (bs,)
    out = [b.strip().rstrip("/") for b in (bs or ()) if (b or "").strip()]
    single = (UPDATE_BASE_URL or "").strip().rstrip("/")
    if single and single not in out:
        out.insert(0, single)
    return out


def _download_urls(rel):
    """清单里允许写相对路径；返回该包所有可尝试的完整地址。"""
    rel = (rel or "").strip()
    if not rel:
        return []
    if rel.startswith(("http://", "https://")):
        return [rel]
    tail = rel.lstrip("/")
    return [b + "/" + tail for b in _base_candidates()]


def _abs_url(url):
    """首个候选地址（保留给旧调用，等价于 _download_urls(url)[0]）。"""
    urls = _download_urls(url)
    return urls[0] if urls else ""


# ---------------------------------------------------------------- 清单 --
def _fetch_manifest_one(url, timeout=8):
    """单个地址拉清单。返回 (dict, "") 或 (None, 错误说明)。"""
    if "REPLACE_ME" in url:
        # 还没换成自己的仓库 —— 别把 404 当成"已是最新"
        return None, "更新源尚未配置（updater_core.UPDATE_MANIFEST_URLS）"

    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Cache-Control": "no-cache",
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        return None, f"清单返回 HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"连不上更新服务器：{e.reason}"
    except Exception as e:                                  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"

    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:                                  # noqa: BLE001
        return None, f"清单不是合法 JSON：{e}"
    if not isinstance(data, dict):
        return None, "清单格式不对：根节点应为对象"
    return data, ""


def fetch_manifest(url=None, timeout=8):
    """按优先级依次尝试各清单地址，第一个成功的就用。

    返回 (dict, "") 或 (None, 错误说明)。错误说明只保留最后一条，
    避免把三个节点的失败原因全糊在界面上。
    """
    if url:
        urls = [url.strip()]
    else:
        urls = manifest_urls()
    if not urls:
        return None, "没有配置更新源"

    last = ""
    for i, u in enumerate(urls):
        # 备用源不必等满 timeout：主源已花掉一次，后面的尽快失败
        data, err = _fetch_manifest_one(u, timeout if i == 0 else min(timeout, 5))
        if data is not None:
            return data, ""
        last = err
    return None, last


def parse_manifest(data, local_ver):
    """把清单整理成 UpdateInfo；没有可用更新时返回 (None, 原因)。"""
    if not data:
        return None, "清单为空"
    latest = data.get("latest")
    if parse_ver(latest) is None:
        return None, f"清单里的 latest 不合法：{latest!r}"
    if not is_newer(latest, local_ver):
        return None, ""

    pkg = (data.get("packages") or {}).get("full") or {}
    urls = _download_urls(pkg.get("url"))
    if not urls:
        return None, "清单里没有 full 包的下载地址"

    sha = str(pkg.get("sha256") or "").strip().lower()
    if sha and not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None, "清单里的 sha256 格式不对"

    try:
        size = int(pkg.get("size") or 0)
    except (TypeError, ValueError):
        size = 0

    apps = data.get("apps")
    if not isinstance(apps, list):
        apps = None
    else:
        apps = [str(x) for x in apps if str(x).lower().endswith(".py")]

    need = False
    try:
        need = compare_ver(local_ver, data.get("min") or "0") < 0
    except ValueError:
        need = False

    return {
        "version": str(latest).lstrip("vV"),
        "notes": str(data.get("notes") or "").strip(),
        "date": str(data.get("date") or "").strip(),
        "url": urls[0],
        "urls": urls,
        "size": size,
        "sha256": sha,
        "apps": apps,
        "mandatory": need,
        "raw": data,
    }, ""


def check_for_update(local_ver, url=None, timeout=8):
    """一步到位：拉清单 + 比对。返回 (info|None, 错误说明)。

    没有新版本时 info 为 None 且 err 为空串 —— 调用方不必区分"没网"和"最新"，
    但想区分时看 err 即可。
    """
    data, err = fetch_manifest(url, timeout=timeout)
    if data is None:
        return None, err
    return parse_manifest(data, local_ver)


# ---------------------------------------------------------------- 下载 --
def _fmt_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def download(url, dest, sha256=None, size=None, on_progress=None,
             cancel=None, timeout=20):
    """流式下载到 dest，边下边算 SHA256。

    url 可以是单个地址，也可以是候选地址列表；按顺序尝试，任一成功即返回。
    返回 (True, "") 或 (False, 错误说明)。失败会把半截文件删掉 ——
    留着半截文件最危险，下次可能被当成"已下载好"。
    """
    urls = [url] if isinstance(url, str) else [u for u in (url or []) if u]
    if not urls:
        return False, "没有下载地址"
    last = ""
    for u in urls:
        ok, err = _download_one(u, dest, sha256=sha256, size=size,
                                on_progress=on_progress, cancel=cancel,
                                timeout=timeout)
        if ok:
            return True, ""
        if err == "已取消":
            return False, err
        last = err
    return False, last


def _download_one(url, dest, sha256=None, size=None, on_progress=None,
                  cancel=None, timeout=20):
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    digest = hashlib.sha256()
    done = 0
    total = int(size or 0)

    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                total = int(resp.headers.get("Content-Length") or 0) or total
            except (TypeError, ValueError):
                pass
            with open(dest, "wb") as fh:
                while True:
                    if cancel is not None and cancel():
                        raise UpdateCancelled()
                    buf = resp.read(CHUNK)
                    if not buf:
                        break
                    fh.write(buf)
                    digest.update(buf)
                    done += len(buf)
                    if on_progress is not None:
                        on_progress(done, total)
    except UpdateCancelled:
        _quiet_remove(dest)
        return False, "已取消"
    except urllib.error.HTTPError as e:
        _quiet_remove(dest)
        return False, f"下载失败：HTTP {e.code}"
    except Exception as e:                                  # noqa: BLE001
        _quiet_remove(dest)
        return False, f"下载中断：{type(e).__name__}: {e}"

    if size and done != int(size):
        _quiet_remove(dest)
        return False, f"大小不符（应为 {_fmt_size(size)}，实收 {_fmt_size(done)}）"
    if sha256:
        got = digest.hexdigest()
        if got.lower() != sha256.lower():
            _quiet_remove(dest)
            return False, f"SHA256 校验失败（收到 {got[:12]}…）"
    return True, ""


def _quiet_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------- 解压 --
def safe_extract(zip_path, dest):
    """解压并拒绝越界路径（zip slip）。返回解出的文件数。"""
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"压缩包含有越界路径：{info.filename}")
            target = os.path.abspath(os.path.join(dest, name))
            if target != dest and not target.startswith(dest + os.sep):
                raise ValueError(f"压缩包含有越界路径：{info.filename}")
            if info.is_dir():
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, CHUNK)
            count += 1
    return count


# --------------------------------------------------- 尊重用户的功能裁剪 --
STATE_FILE = "_apps_state.json"


def read_apps_state(target_dir):
    """读「上次更新时程序写下了哪些功能」这一记录。

    没有它的话，「用户删了 keys.py」和「本版新增了 update.py」在文件系统
    上长得一模一样 —— 都表现为 live 里少一个文件。分不清就会二选一犯错：
    要么把用户删掉的功能装回来，要么把新功能永远挡住。
    """
    path = os.path.join(target_dir, STATE_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    files = data.get("files")
    if not isinstance(files, list):
        return None
    return {
        "version": str(data.get("version") or ""),
        "files": [str(x) for x in files if str(x).lower().endswith(".py")],
    }


def write_apps_state(target_dir, version, names):
    """记下当前版本"应该有哪些功能文件"。用户之后删掉的，就是这个列表的差集。"""
    path = os.path.join(target_dir, STATE_FILE)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"version": str(version),
                       "files": sorted(str(n) for n in names)},
                      fh, ensure_ascii=False, indent=1)
        return True
    except OSError:
        return False


def prune_payload_apps(payload_dir, live_apps_dir, installed_apps=None):
    """把 payload\\apps 里"用户已经删掉的功能"剔掉，别给他装回来。

      * live 目录不存在        → 首次安装，全装
      * live 存在但是空的      → 用户把功能全删了，一个都不装回
      * 有上次的安装记录       → 只剔掉「记录里有、现在没有」的那些，
                                 本版新增的文件照常装上
      * 没有记录（首次升级）   → 无从判断，全装
                                 （宁可复活一次，也不能让新功能永远到不了
                                  老用户手上；此后有了记录就精确了）

    返回 (被剔掉的文件名列表, 是否判定为"裁剪过的用户")。
    """
    src = os.path.join(payload_dir, "apps")
    if not os.path.isdir(src):
        return [], False

    def _pys(d):
        try:
            return {n.lower(): n for n in os.listdir(d)
                    if n.lower().endswith(".py")}
        except OSError:
            return {}

    payload = _pys(src)
    if not os.path.isdir(live_apps_dir):
        return [], False                       # 全新安装，原样给
    live = _pys(live_apps_dir)

    if not live:
        doomed = payload
        trimmed = True
    elif installed_apps:
        known = {str(n).lower() for n in installed_apps}
        doomed = {n: real for n, real in payload.items()
                  if n in known and n not in live}
        trimmed = bool(doomed)
    else:
        doomed = {}
        trimmed = False

    removed = []
    for real in doomed.values():
        try:
            os.remove(os.path.join(src, real))
            removed.append(real)
        except OSError:
            pass
    return sorted(removed), trimmed


# --------------------------------------------------------- 延迟替换脚本 --
def _short_path(path):
    """取 8.3 短路径。

    .bat 是用当前 ANSI 代码页读的，路径里带中文（D:\\工具盒子\\…）时
    cmd 解释会走样。短路径是纯 ASCII，最稳。取不到就原样返回，
    由 _write_bat 用 mbcs 编码兜底。
    """
    if not IS_WIN:
        return path
    path = os.path.normpath(str(path))
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 1024)
        if 0 < n < 1024:
            return buf.value
    except Exception:                                       # noqa: BLE001
        pass
    return path


_BAT = r"""@echo off
setlocal enableextensions
set "TGT=%~1"
set "SRC=%~2"
set "EXE=%~3"
set "WAITPID=%~4"
set "LOG=%~5"
set "RESTART=%~6"
set /a TICK=0
:wait
if "%WAITPID%"=="0" goto apply
"%SystemRoot%\System32\tasklist.exe" /FI "PID eq %WAITPID%" /NH | "%SystemRoot%\System32\find.exe" "%WAITPID%" >nul
if errorlevel 1 goto apply
set /a TICK+=1
if %TICK% GEQ 120 goto apply
"%SystemRoot%\System32\ping.exe" -n 2 127.0.0.1 >nul
goto wait
:apply
>>"%LOG%" echo [%DATE% %TIME%] replacing "%SRC%" -^> "%TGT%"
"%SystemRoot%\System32\robocopy.exe" "%SRC%" "%TGT%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >>"%LOG%" 2>&1
set RC=%ERRORLEVEL%
>>"%LOG%" echo [%DATE% %TIME%] robocopy exit=%RC%
if %RC% GEQ 8 goto fail
if not "%RESTART%"=="1" goto done
start "" "%TGT%\%EXE%"
goto done
:fail
>>"%LOG%" echo [%DATE% %TIME%] FAILED, old files left in place
if not "%RESTART%"=="1" goto done
start "" "%TGT%\%EXE%"
:done
(goto) 2>nul & del "%~f0"
"""


def _write_bat(path, text):
    """bat 用系统 ANSI 代码页写（中文 Windows 上是 936）。"""
    enc = "mbcs" if IS_WIN else "utf-8"
    try:
        raw = text.encode(enc, "replace")
    except LookupError:
        raw = text.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(raw)


def make_update_script(work_dir, target_dir, payload_dir, exe_name,
                       wait_pid=0, restart=True, log_path=None):
    """生成替换脚本并返回 (bat 路径, 日志路径)。不启动它。"""
    os.makedirs(work_dir, exist_ok=True)
    bat = os.path.join(work_dir, "apply_update.bat")
    log = log_path or os.path.join(work_dir, "update.log")
    _write_bat(bat, _BAT)
    return bat, log


def _cmd_line(bat, args):
    """拼一条 cmd 命令行。

    注意外层那对多出来的引号：`cmd /c` 后面**第一个字符是引号**时，cmd 会
    把最外层的一对引号剥掉。如果直接写 `cmd /c "C:\\a b\\x.bat" "arg"`，
    它会把 `C:\\a b\\x.bat" "arg` 整段当成命令，参数全部错位 —— 表现就是
    脚本根本没跑起来、日志一片空白。多包一层才是稳定写法。
    """
    inner = " ".join(f'"{str(p)}"' for p in [bat] + list(args))
    return f'cmd /c "{inner}"'


def launch_update_script(bat, target_dir, payload_dir, exe_name,
                         wait_pid=0, restart=True, log_path=None):
    """以隐藏窗口启动替换脚本；调用方紧接着要退出主程序。

    必须用 CREATE_NO_WINDOW：否则用户会看到一个 cmd 黑框一闪而过。
    """
    cmdline = _cmd_line(bat, [
        _short_path(target_dir),
        _short_path(payload_dir),
        exe_name,
        str(wait_pid or 0),
        _short_path(log_path or ""),
        "1" if restart else "0",
    ])
    flags = 0
    if IS_WIN:
        flags = 0x08000000 | 0x00000200      # CREATE_NO_WINDOW | NEW_PROCESS_GROUP
    proc = subprocess.Popen(cmdline,
                            creationflags=flags, close_fds=True,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    return proc


def stage_payload(zip_path, work_dir, live_apps_dir=None, installed_apps=None):
    """解压到 work_dir\\payload，并按用户的裁剪剔掉不该装的功能模块。"""
    payload = os.path.join(work_dir, "payload")
    if os.path.isdir(payload):
        shutil.rmtree(payload, ignore_errors=True)
    count = safe_extract(zip_path, payload)
    removed, trimmed = [], False
    if live_apps_dir:
        removed, trimmed = prune_payload_apps(payload, live_apps_dir,
                                              installed_apps)
    return payload, count, removed, trimmed


def work_dir_for(version):
    """临时工作目录（放下载包与脚本）。"""
    tag = re.sub(r"[^0-9A-Za-z._-]", "_", str(version or "0"))
    return os.path.join(tempfile.gettempdir(), f"pivot_update_{tag}")
