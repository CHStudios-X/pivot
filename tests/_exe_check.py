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
"""
import ctypes, os, shutil, struct, subprocess, sys, time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))            # 测试\
ROOT = os.path.dirname(HERE)                                  # D:\枢
from _paths import app_dir as _app_dir        # 1.2.7 起产物是 onedir 目录

EXE = os.path.join(_app_dir(), "pivot.exe")   # 产物目录里的主程序
APP_DIR_SRC = _app_dir()
ERR = os.path.join(HERE, "_exe_stderr.txt")                   # 日志留在 tests\
OUT = os.path.join(ROOT, "tests", "_shots", "preview_exe.png")  # 截图归到 tests\_shots\
os.makedirs(os.path.dirname(OUT), exist_ok=True)
TITLE = "枢"
MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
# 所有可能残留的 exe 映像名(引导器 fork 出的子进程也会带这些名字)
IMAGES = ["pivot.exe", "_exe_patched.exe", "_fix_probe.exe",
          "_patch_probe.exe", "_iconprobe.exe"]

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


# ================= 第一阶段:新构建的 exe 能正常起界面 =================
print("=== 第一阶段:新建的 exe ===")
kill_all()
ck(not app_windows(), "启动前系统内无残留「枢」窗口(否则窗口断言会假阳性)")
launch_and_shot(EXE, "新 exe", ERR, OUT)

print()
print(f"总体:{'全部通过 ✓' if not fails else f'失败 {len(fails)} 项 ✗'}")
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(0 if not fails else 1)
