# -*- coding: utf-8 -*-
"""验证打包后的 exe:窗口是否出现 / stderr 是否干净 / 截图确认资源真的加载了

windowed 模式下"背景图加载失败"只会静默退化成光斑背景,光看进程活着不够 ——
所以要用窗口定位 + 截窗口内容 + 检查 stderr 字节数。

截图优先用 PrintWindow(PW_RENDERFULLCONTENT) 直接取窗口自身内容:
屏幕截图 grabWindow(0) 抓的是合成结果,窗口被别人压住时截到的是别人的界面 ——
实测被 B 站/电脑管家挡过好几次,而 SetForegroundWindow 会被系统限制、不总生效。
PrintWindow 不看遮挡,谁在上面都不影响。

⚠ 三个曾经的假阳性来源,现在都堵上了(1.2.4 踩过,详见 _fix_verify 注释):
  1) "进程存活" != "启动成功" —— 引导器弹模态错误框时进程照样存活;
     现在要求出现**可见主窗口**。
  2) 按标题找窗口会匹配到上轮遗留的僵尸窗口 —— PyInstaller onefile 会
     fork 子进程跑真程序,kill 父进程会留下带可见窗口的子进程。现在
     启动前先断言"系统内无同名窗口",找到后再核对窗口宿主进程映像名。
  3) 只比"进程活着",不看文件本身有没有被改坏 —— 现在第二阶段会断言
     附加归档(cookie/字节)与体积,再真机启动。
"""
import ctypes, os, shutil, struct, subprocess, sys, time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))            # 测试\
ROOT = os.path.dirname(HERE)                                  # D:\枢
from _paths import app_dir as _app_dir        # 1.2.7 起产物是 onedir 目录

EXE = os.path.join(_app_dir(), "pivot.exe")   # 产物目录里的主程序
APP_DIR_SRC = _app_dir()
ICO = os.path.join(ROOT, "icon", "app_ser.ico")
ERR = os.path.join(HERE, "_exe_stderr.txt")                   # 日志留在 测试\
OUT = os.path.join(ROOT, "截图", "preview_exe.png")            # 截图归到 截图\
os.makedirs(os.path.dirname(OUT), exist_ok=True)
TITLE = "枢"
MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
# 所有可能残留的 exe 映像名(引导器 fork 出的子进程也会带这些名字)
IMAGES = ["pivot.exe", "_exe_patched.exe", "_fix_probe.exe",
          "_egg_patch_probe.exe", "_patch_probe.exe", "_iconprobe.exe"]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()

fails = []


def ck(cond, msg):
    print(("  [OK] " if cond else "  [!!] ") + msg)
    if not cond:
        fails.append(msg)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def kill_all():
    """按映像名强杀 —— 必须覆盖所有探针名,否则子进程会漏成僵尸窗口"""
    for n in IMAGES:
        subprocess.run(["taskkill", "/F", "/IM", n], capture_output=True)
    time.sleep(1.0)


def app_windows():
    """系统内所有标题为 TITLE 的顶层窗口 [(hwnd, pid, visible)]"""
    out = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _lp):
        t = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(h, t, 512)
        if t.value == TITLE:
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            out.append((h, p.value, bool(user32.IsWindowVisible(h))))
        return True

    user32.EnumWindows(proc(cb), 0)
    return out


def wait_app_window(timeout):
    """等一个可见的 TITLE 窗口,返回 (hwnd, 宿主进程 pid)"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        for h, pid, vis in app_windows():
            if vis:
                return h, pid
        time.sleep(0.25)
    return 0, 0


def image_of(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV",
                        "/NH"], capture_output=True)
    txt = r.stdout.decode("gbk", "replace").strip().strip('"')
    return txt.split('","')[0].lower() if txt else ""


def _sections_of(raw):
    """{节名: 该节的文件字节} —— 用来比对"只有资源段变了" """
    e = struct.unpack_from("<I", raw, 0x3C)[0]
    nsec = struct.unpack_from("<H", raw, e + 6)[0]
    optsz = struct.unpack_from("<H", raw, e + 20)[0]
    base = e + 24 + optsz
    out = {}
    for i in range(nsec):
        o = base + i * 40
        name = raw[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        prs = struct.unpack_from("<I", raw, o + 16)[0]
        pra = struct.unpack_from("<I", raw, o + 20)[0]
        out[name] = raw[pra:pra + prs]
    return out


def print_window(hwnd, w, h):
    """把窗口自身内容画进内存位图,返回 (是否成功, BGRA 缓冲)"""
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)      # 2 = PW_RENDERFULLCONTENT
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h                 # 负数 = 自顶向下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0             # BI_RGB
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return ok, buf


def launch_and_shot(exe, tag, err_path, shot_path):
    """启动 → 等主窗口 → 截窗口内容 → 收尾,返回 (主窗口, 宿主映像, 存活)"""
    err_f = open(err_path, "wb")
    proc = subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=err_f)
    print(f"  启动 {tag} pid={proc.pid}")
    hwnd, wpid = wait_app_window(90)
    ck(bool(hwnd), f"{tag}: 90s 内出现可见主窗口"
       if hwnd else f"{tag}: 90s 内没出现可见主窗口")
    img = image_of(wpid) if hwnd else ""
    if hwnd:
        print(f"      hwnd={hwnd:#x} 宿主 pid={wpid} 映像={img!r}")
        ck(img == os.path.basename(exe).lower(),
           f"{tag}: 窗口确实属于被启动的 exe")
    time.sleep(5.0)                            # 等闪屏 + 入场动画走完
    if hwnd:
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        print(f"      窗口矩形 {w}x{h}")
        ok, buf = print_window(hwnd, w, h)
        raw = bytes(buf)
        step = 4 * 97
        sampled = len(range(0, len(raw) - 4, step))
        nonblack = sum(1 for i in range(0, len(raw) - 4, step)
                       if raw[i] or raw[i + 1] or raw[i + 2])
        ratio = nonblack / max(1, sampled)
        print(f"      PrintWindow ok={ok} 非黑像素占比={ratio:.1%}")
        if ratio > 0.02:
            _q().save_shot(buf, w, h, shot_path)
            print(f"      截图 {os.path.basename(shot_path)} {w}x{h}")
        else:
            ck(False, f"{tag}: PrintWindow 拿到的是空白")
    alive = proc.poll() is None
    kill_all()                                 # 连子进程一起清,不留僵尸窗口
    try:
        proc.wait(timeout=8)
    except Exception:                                          # noqa: BLE001
        try:
            proc.kill()
        except Exception:                                      # noqa: BLE001
            pass
    err_f.flush()
    err_f.close()
    esz = os.path.getsize(err_path)
    ck(esz == 0, f"{tag}: stderr 干净({esz} 字节)")
    if esz:
        print(open(err_path, "r", encoding="utf-8", errors="replace").read()[:800])
    ck(not app_windows(), f"{tag}: 收尾后无残留窗口")
    return hwnd, img, alive


def _q():
    """惰性拿到 QApplication 与截图封装(PySide6 只在需要时导入)"""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    class _Q:
        app = QApplication.instance() or QApplication(sys.argv)

        @staticmethod
        def save_shot(buf, w, h, path):
            QImage(buf, w, h, QImage.Format.Format_RGB32).copy().save(path)

    return _Q


# ================= 注册表隔离(必须在启动本体之前) =================
# ★ 这条是血泪教训:注册表里 ser_updated=true 时,本体会执行"已 ser 机器
#   补换文件图标"的自维护逻辑 —— 那是真的改写 + 改名交付产物。曾经测试
#   脚本先启动本体再隔离注册表,结果本体用**旧版有 bug 的补换逻辑**把
#   自己截断成 336KB。所以隔离要在任何一次启动之前做完。
from PySide6.QtCore import QSettings                   # noqa: E402
_qs = QSettings("Pivot", "Pivot")
_snap = {}
for k in ("ser_updated", "icon_patched"):
    _snap[k] = (_qs.contains(k), _qs.value(k) if _qs.contains(k) else None)
    _qs.remove(k)
_qs.sync()


def _restore_qs():
    """atexit 兜底:中途崩了也要把注册表还原,不替用户改状态"""
    for k, (had, val) in _snap.items():
        _qs.remove(k)
        if had:
            _qs.setValue(k, val)
    _qs.sync()


import atexit                                            # noqa: E402
atexit.register(_restore_qs)

# ================= 第一阶段:新构建的 exe 能正常起界面 =================
print("=== 第一阶段:新建的 exe ===")
kill_all()
ck(not app_windows(), "启动前系统内无残留「枢」窗口(否则窗口断言会假阳性)")
launch_and_shot(EXE, "新 exe", ERR, OUT)

# ================= 第二阶段:onefile 图标改写后仍可启动 =================
# SER 更新的核心风险点 —— UpdateResourceW 只写回 PE 映像,尾部附加数据
# (onefile 自解压载荷)会被整块丢掉,丢掉之后 exe 再也起不来。所以这里
# 改写一份副本,既验文件完整性,又真机启动。
print()
print("=== 第二阶段:onefile 图标改写后仍完好可启动 ===")
sys.path.insert(0, ROOT)
import pivot as M                                # noqa: E402

PATCHED = os.path.join(HERE, "_exe_patched.exe")
PATCHED_DIR = os.path.join(HERE, "_exe_patched_dir")
ERR2 = os.path.join(HERE, "_exe_patched_stderr.txt")

kill_all()
ck(not app_windows(), "改写前系统内无残留「枢」窗口")
# onedir 下 exe 单独拿走跑不起来（缺 _internal\），必须整目录复制。
# 改写仍然只针对副本里的那一个 exe 文件，末尾的体积/字节断言照旧成立。
shutil.rmtree(PATCHED_DIR, ignore_errors=True)
shutil.copytree(APP_DIR_SRC, PATCHED_DIR)
PATCHED = os.path.join(PATCHED_DIR, "pivot.exe")
for p in (PATCHED + ".old", PATCHED + ".ser_new"):
    if os.path.exists(p):
        os.remove(p)
_orig = open(PATCHED, "rb").read()
_img_end = M._pe_image_end(_orig)
_overlay = _orig[_img_end:]
_sect = _sections_of(_orig)

n = M.patch_exe_icon(PATCHED, ICO)
_new = open(PATCHED, "rb").read()
print(f"  patch_exe_icon 写入帧数 = {n}")
print(f"  体积 {len(_orig):,} -> {len(_new):,} (差 {len(_new) - len(_orig):+,})")
ck(n == 7, "写入 7 帧图标")
ck(len(_new) > len(_orig) * 0.9, "改写后体积未塌陷(附加归档没被丢)")
ck(MAGIC in _new, "改写后 PyInstaller cookie 仍在")
ck(_new[M._pe_image_end(_new):] == _overlay,
   "附加归档字节完全一致(自解压载荷原样保留)")
ck(_sections_of(_new)[".text"] == _sect[".text"], ".text 代码段字节完全一致")
_e, _frames = M._parse_ico(open(ICO, "rb").read())
ck(all(M._read_icon_resource(PATCHED, i) == fr
       for i, fr in enumerate(_frames, start=1)),
   f"{len(_frames)} 个 RT_ICON 资源逐帧与 app_ser.ico 一致")
ck(M._exe_icon_is_ser(PATCHED, ICO), "_exe_icon_is_ser 认得出改写后的图标")
ck(M._exe_icon_is_ser(EXE, ICO),
   "新包本体出厂即 SER(主图标纯黑底 -> 图标资源与 app_ser.ico 一致)")

launch_and_shot(PATCHED, "改写后副本", ERR2, os.path.join(
    ROOT, "截图", "preview_exe_patched.png"))

for p in (PATCHED + ".old", PATCHED + ".ser_new", ERR2):
    try:
        os.remove(p)
    except OSError:
        pass
shutil.rmtree(PATCHED_DIR, ignore_errors=True)

# ============ 第三阶段:真实用户路径(两条) ============
# 3a) 装的是新包(图标出厂即纯黑底)+ 机器上 ser_updated=true
#     → housekeeping 比对图标资源字节后发现"已是 SER",直接跳过,
#       **零文件改动**。这正是本次交付后用户机器上的实际情形,
#       必须验证它绝不会去碰本体文件(当初炸掉的就是这条路径)。
# 3b) 本体图标处于非 SER 状态(更早的紫底构建 / 图标被换回过)
#     → housekeeping 真正补换:改写副本 + 换名 + 留 .old 备份。
# 两条都在沙箱副本上跑,交付产物一点都不碰。
print()
print("=== 第三阶段 A:新包 + 已 ser -> 应跳过改写、不动本体 ===")
SANDBOX = os.path.join(HERE, "_serbox")
COPY = os.path.join(SANDBOX, "pivot", "pivot.exe")
ERR3 = os.path.join(HERE, "_exe_serbox_stderr.txt")
BOLT = os.path.join(ROOT, "icon", "bolt.ico")


def _launch_wait(exe, stderr_path, wait=90):
    """启动 + 等主窗口,返回 (进程, 窗口句柄, 宿主窗口, stderr 句柄)"""
    _ef = open(stderr_path, "wb")
    _p = subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=_ef)
    _h, _w = wait_app_window(wait)
    return _p, _h, _w, _ef


def _stop(_p, _ef):
    """清干净进程(连子进程)并关闭 stderr 句柄"""
    kill_all()
    _ef.flush()
    _ef.close()
    try:
        _p.wait(timeout=8)
    except Exception:                                      # noqa: BLE001
        try:
            _p.kill()
        except Exception:                                  # noqa: BLE001
            pass


shutil.rmtree(SANDBOX, ignore_errors=True)
shutil.copytree(APP_DIR_SRC, os.path.join(SANDBOX, "pivot"))
_sz0 = os.path.getsize(COPY)
_qs.setValue("ser_updated", "true")
_qs.remove("icon_patched")
_qs.sync()

kill_all()
ck(not app_windows(), "3a:启动前无残留窗口")
_p3, _h3, _wp3, _ef3 = _launch_wait(COPY, ERR3)
ck(bool(_h3), "3a:本体弹出主窗口")
if _h3:
    ck(image_of(_wp3) == "pivot.exe", "3a:窗口属于沙箱副本")
_t0 = time.time()                       # 给后台 housekeeping 留出跑完的时间
while time.time() - _t0 < 8:
    time.sleep(0.5)
ck(M._exe_icon_is_ser(COPY, ICO), "3a:副本图标本就是 SER")
ck(not os.path.exists(COPY + ".old"), "3a:无需改写 -> 没有产生 .old 备份")
ck(os.path.getsize(COPY) == _sz0, "3a:本体文件字节数一字未变(零改写)")
_stop(_p3, _ef3)

print()
print("=== 第三阶段 B:本体图标非 SER -> 真机补换 + .old 备份 ===")
shutil.rmtree(SANDBOX, ignore_errors=True)
shutil.copytree(APP_DIR_SRC, os.path.join(SANDBOX, "pivot"))
_nb = M.patch_exe_icon(COPY, BOLT)      # 预置一个非 SER 图标(黑底闪电)当作"旧图标"
ck(_nb == 7, "3b:预置非 SER 图标(7 帧)")
ck(not M._exe_icon_is_ser(COPY, ICO), "3b:预置图标确实不是 SER")
_sz1 = os.path.getsize(COPY)
_qs.setValue("ser_updated", "true")
_qs.remove("icon_patched")
_qs.sync()

kill_all()
ck(not app_windows(), "3b:启动前无残留窗口")
_p5, _h5, _wp5, _ef5 = _launch_wait(COPY, ERR3)
ck(bool(_h5), "3b:本体弹出主窗口")
if _h5:
    ck(image_of(_wp5) == "pivot.exe", "3b:窗口属于沙箱副本")

_matched = False
_t0 = time.time()
while time.time() - _t0 < 45:
    try:
        if os.path.exists(COPY + ".old") and M._exe_icon_is_ser(COPY, ICO):
            _matched = True
            break
    except OSError:
        pass
    time.sleep(0.5)
ck(_matched, "3b:后台自动补换完成(图标变 SER + 留下 .old 备份)")
if _matched:
    _raw5 = open(COPY, "rb").read()
    print(f"      副本体积 {_sz1:,} -> {len(_raw5):,}")
    ck(len(_raw5) > _sz1 * 0.9, "3b:补换后本体体积未塌陷")
    ck(MAGIC in _raw5, "3b:补换后 PyInstaller cookie 仍在")
_stop(_p5, _ef5)

_p6, _h6, _wp6, _ef6 = _launch_wait(COPY, ERR3)      # 再启动一次
ck(bool(_h6), "3b:补换后的副本仍能正常启动(第二次)")
_old_gone = False
_t0 = time.time()
while time.time() - _t0 < 30:
    if not os.path.exists(COPY + ".old"):
        _old_gone = True
        break
    time.sleep(0.5)
ck(_old_gone, "3b:成功启动后 .old 备份被自动清理")
_stop(_p6, _ef6)

shutil.rmtree(SANDBOX, ignore_errors=True)
# 还原注册表
for k, (had, val) in _snap.items():
    _qs.remove(k)
    if had:
        _qs.setValue(k, val)
_qs.sync()

print()
print(f"总体:{'全部通过 ✓' if not fails else f'失败 {len(fails)} 项 ✗'}")
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(0 if not fails else 1)
