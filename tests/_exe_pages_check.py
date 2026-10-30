# -*- coding: utf-8 -*-
r"""1.2.5 出包后实拍:驱动打包好的 exe 逐页切换并截图(带真实断言)。

背景(两次假阳性,都记录在此以免重犯):
  ① 第一版把导航项坐标写死成 "940x690 窗口实测" 的值,而实际窗口是
     1180x760,于是每次点击都落在玻璃内容区 —— 6 张截图全是主页,
     脚本却因为只检查"截图有没有产出"而报了成功。
  ② 第二版改成自动定位坐标后,基线位图是在壁纸淡入 + 入场动画还没
     结束时抓的,导致第一次点击被误判成"切页",后续文件名整体错位一格。

这一版的对策:
  1. 坐标不猜:在底部条带里扫描"亮字列簇"(导航文字浅色、背景深色),
     簇间隔 >16px 才断开(「外观」两个字中间只有 14px 空隙,阈值太小
     会把它拆成两簇而多出一个候选);
  2. 页面判定不靠"位图完全相等":PulseDot 是 LoopCount(-1) 的无限呼吸
     动画,极光背景也在缓慢漂移,整窗签名永远在抖。改用降采样亮度签名
     + 容差距离(dist = 相差 ≥2 个量化档的采样点数);
  3. 基线必须等画面稳定(连续两次抓图距离 < STABLE_TOL)才取;
  4. 最后做一次往返校验:把 6 个导航项再点一遍,确认落回同一页签名的
     距离 < SAME_TOL,否则整体 FAIL。

1.2.6 补的第三次教训(这次是**假失败**,不是假成功):
  往返校验在「键盘连按」页偶发报距离 1884(重跑又变 16),后来又出现过
  "整条页面对照错位一格"(clicker 的坐标变成了主页的坐标)。
  用 _exe_sig_drift.py 量出根因是**时间竞态**:键盘连按页点完约 0.8s 才最终
  落定(第 1 帧 vs 第 11 帧差 1857,之后完全静止);启动淡入同理。
  → 判据从"相邻两帧接近"改成**相隔 gap 秒的三帧两两接近**(窗口近 2.2 秒),
    并去掉"重下注主页"这个歧义点(落地页本来就是 home,不再点它)。
  教训:**"两帧一样"不等于"已经停了"**,缓动曲线尾段专门骗这条。

运行: python _exe_pages_check.py
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "截图")
from _paths import exe_path as _exe_path        # 1.2.7 起产物是 onedir 目录

EXE = _exe_path()

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32
u32.SetProcessDPIAware()
u32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]

WM_LBUTTONDOWN, WM_LBUTTONUP, WM_CLOSE = 0x0201, 0x0202, 0x0010

NAV_KEYS = ["home", "clicker", "keys", "remap", "appearance", "settings",
            "update"]

SIG_X, SIG_Y = 13, 11          # 签名采样步长
STABLE_TOL = 30                # 相邻两帧距离小于它 -> 认为画面已静止
# 同一页的噪声(极光漂移 + PulseDot 呼吸)实测 ≤65,而真正换页的距离
# 实测 ≥949,中间空档极大;阈值取空档中央比卡在噪声边缘稳。
SAME_TOL = 200                 # 与已知页签名的距离小于它 -> 同一页
CLUSTER_GAP = 16               # 亮字列簇间隔超过它才断开


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        time.sleep(0.02)


def find_window(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        h = u32.FindWindowW(None, "枢")
        if h:
            r = RECT()
            u32.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 100:
                return h
        time.sleep(0.3)
    return None


# ---------------------------------------------------------------- 抓位图
class BMIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BMI(ctypes.Structure):
    _fields_ = [("bmiHeader", BMIH), ("bmiColors", wintypes.DWORD * 3)]


def grab(hwnd):
    r = RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = u32.GetWindowDC(hwnd)
    mem = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(mem, bmp)
    u32.PrintWindow(hwnd, mem, 2)          # PW_RENDERFULLCONTENT
    bi = BMI()
    bi.bmiHeader.biSize = ctypes.sizeof(BMIH)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mem)
    u32.ReleaseDC(hwnd, hdc)

    from PySide6.QtGui import QImage
    return QImage(buf, w, h, QImage.Format.Format_RGB32).copy()


def lum(img, x, y):
    v = img.pixel(x, y)
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return (r * 299 + g * 587 + b * 114) // 1000


def signature(img):
    """降采样亮度签名(量化到 12 一档,抗轻微抖动)"""
    w, h = img.width(), img.height()
    out = []
    for y in range(int(h * 0.08), int(h * 0.86), SIG_Y):
        for x in range(int(w * 0.03), int(w * 0.97), SIG_X):
            v = img.pixel(x, y)
            r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
            out.append(((r * 299 + g * 587 + b * 114) // 1000) // 12)
    return out


def dist(a, b):
    n = 0
    for u, v in zip(a, b):
        if u - v >= 2 or v - u >= 2:
            n += 1
    return n


def wait_stable(hwnd, timeout=20.0, gap=0.3, need=3, settle=1.0):
    """等画面真正静止,返回 (最后一帧, 签名)。

    ⚠ **只比"相邻两帧"是不够的** —— 这条是踩出来的:
      入场动画是 ease-out,尾段每帧只挪一点点,相邻两帧早就 < STABLE_TOL 了,
      但整页还在往最终位置走。于是基线被抓在半路,往返校验偶尔报一个上千的
      距离(实测键盘连按页:点完 0.8s 才落定,第 1 帧 vs 第 11 帧差 1857,
      中间"上帧 vs 本帧"却出现过 0)。重跑又正常 —— 典型的时间竞态。
      现在要求**连续 need 帧彼此都在 STABLE_TOL 以内**(以窗口里最老那帧为
      基准,能挡住"缓慢漂移"和"最后突然落位"两种),并且先静置 settle 秒。
    """
    time.sleep(settle)
    end = time.time() + timeout
    img = grab(hwnd)
    win = [signature(img)]
    while time.time() < end:
        if len(win) >= need and all(dist(win[0], s) < STABLE_TOL
                                    for s in win[1:]):
            return img, win[-1]
        time.sleep(gap)
        img = grab(hwnd)
        win.append(signature(img))
        if len(win) > need:
            win.pop(0)
    print("  (警告:画面未在超时内静止,使用最后一帧)")
    return img, win[-1]


def settle_shot(hwnd, timeout=10.0, tries=5, gap=1.1):
    """抓一帧"确实已经落定"的图,返回 (帧, 签名)。

    ⚠ 判据**不能**是"相邻两帧接近" —— 缓动曲线尾段（ease-out）每帧只挪一点点,
      连续两帧永远都"接近",可整页还在往最终状态走。实测踩过两次:
        · 键盘连按页:点完 0.8s 才落定,相邻帧差分出现过 0,基线却抓在半路;
        · 启动淡入:基线抓在 reveal≈0.95,于是"再点一次主页"距离上千,
          整条页面对照整体错位一格(表现为 clicker 的坐标变成了主页的)。
      现在要求**相隔 gap 秒的三帧两两都在 SAME_TOL 以内** —— 窗口近 2.2 秒,
      任何形状的缓慢淡入/位移都藏不住。
    """
    a = b = c = grab(hwnd)
    sa = sb = sc = signature(c)
    for _ in range(tries):
        a = grab(hwnd)
        sa = signature(a)
        time.sleep(gap)
        b = grab(hwnd)
        sb = signature(b)
        if dist(sa, sb) > SAME_TOL:
            continue
        time.sleep(gap)
        c = grab(hwnd)
        sc = signature(c)
        if dist(sb, sc) <= SAME_TOL and dist(sa, sc) <= SAME_TOL:
            return c, sc
    print("  (警告:画面长时间未落定,使用最后一帧)")
    return c, sc


def locate_nav(img):
    """底部条带里找亮字列簇 -> 6 个导航项中心 x 列表 + 行中心 y"""
    w, h = img.width(), img.height()
    y0, y1 = int(h * 0.86), h - 1
    xa, xb = int(w * 0.06), int(w * 0.54)

    best = max(((sum(1 for x in range(xa, xb, 2) if lum(img, x, y) > 150), y)
                for y in range(y0, y1 + 1)))[1]
    ya, yb = max(y0, best - 12), min(y1, best + 12)
    bar_y = (ya + yb) // 2

    cols = [(x, any(lum(img, x, y) > 150 for y in range(ya, yb + 1, 2)))
            for x in range(0, int(w * 0.58), 2)]

    clusters, cur, gap = [], None, 0
    for x, hit in cols:
        if hit:
            cur = [x, x] if cur is None else [cur[0], x]
            gap = 0
        elif cur is not None:
            gap += 2
            if gap > CLUSTER_GAP:
                clusters.append(tuple(cur))
                cur = None
    if cur is not None:
        clusters.append(tuple(cur))
    return [(a + b) // 2 for a, b in clusters], bar_y, clusters


def click(hwnd, x, y):
    lp = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    u32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.06)
    u32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def kill_all():
    subprocess.run(["taskkill", "/F", "/IM", "pivot.exe"],
                   capture_output=True)


def main():
    kill_all()
    time.sleep(0.8)
    print("启动", EXE)
    p = subprocess.Popen([EXE])
    hwnd = find_window()
    if not hwnd:
        print("FAIL 没等到主窗口")
        kill_all()
        return 1
    print(f"  窗口 0x{hwnd:X}")

    wr, cr = RECT(), RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(wr))
    u32.GetClientRect(hwnd, ctypes.byref(cr))
    print(f"  窗口 {wr.right-wr.left}x{wr.bottom-wr.top}  "
          f"客户区 {cr.right-cr.left}x{cr.bottom-cr.top}")

    pump(3.0)                              # 闪屏 2400ms 先过去
    base, base_sig = settle_shot(hwnd)     # 再等入场/淡入动画**彻底**停
    print(f"  签名采样点 {len(base_sig)}  基线已稳定")

    cx, bar_y, clusters = locate_nav(base)
    print(f"  底部亮字列簇: {'  '.join(f'{a}~{b}' for a, b in clusters)}")
    print(f"  导航项 x: {cx}   行中心 y={bar_y}")
    if len(cx) != len(NAV_KEYS):
        print(f"FAIL 定位到 {len(cx)} 个候选,期望 {len(NAV_KEYS)}")
        u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        pump(1.0)
        kill_all()
        return 1

    # 逐项点击,靠"与已知页签名的距离"分類;新页按出现顺序映射到 NAV_KEYS
    base.save(os.path.join(OUT, "exe_home.png"))
    print(f"  截图 exe_home.png {base.width()}x{base.height()} (baseline)")

    pages = {"home": base_sig}             # 已确认的页面 -> 签名
    tab_x = {"home": cx[0]}
    order = ["home"]

    # 从第二个导航项开始 —— 落地页本来就是 home,再点它一次既没有信息量,
    # 又会把"基线是否可靠"这个问题混进分类里(基线一旦歪了,x=cx[0] 会被
    # 判成"新页",后面所有页面整体错位一格,现象极难看出真因)。
    for x in cx[1:]:
        click(hwnd, x, bar_y)
        pump(0.7)
        img, sig = settle_shot(hwnd)
        near = min(pages.items(), key=lambda kv: dist(kv[1], sig))
        d = dist(near[1], sig)
        if d <= SAME_TOL:
            print(f"  x={x:<4} 与原页 '{near[0]}' 距离 {d} -> 同一页,跳过")
            continue
        if len(order) >= len(NAV_KEYS):
            print(f"  x={x:<4} 距离 {d} -> 多出的页面,忽略")
            continue
        key = NAV_KEYS[len(order)]
        pages[key] = sig
        tab_x[key] = x
        order.append(key)
        path = os.path.join(OUT, f"exe_{key}.png")
        img.save(path)
        print(f"  x={x:<4} 距离 {d} -> 新页 <{key}>  截图 exe_{key}.png")

    # ---- 往返校验:再点一遍,确认每项都落回自己的页 ----
    # 先复核窗口几何:尺寸/位置变过的话,前面量到的导航坐标就失效了 ——
    # 那种情况下报出来的"距离很大"是坐标问题,不是页面问题,要分清楚。
    wr2 = RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(wr2))
    size_now = (wr2.right - wr2.left, wr2.bottom - wr2.top)
    print(f"  往返前窗口 {size_now[0]}x{size_now[1]}"
          f"(基线时 {base.width()}x{base.height()})"
          + ("  ⚠ 尺寸变过!" if size_now != (base.width(), base.height()) else ""))
    img_chk = grab(hwnd)
    cx2, bar_y2, _cl2 = locate_nav(img_chk)
    if len(cx2) == len(cx) and all(abs(a - b) <= 4 for a, b in zip(cx, cx2)):
        print("  导航项位置未变,坐标仍有效")
    else:
        print(f"  ⚠ 导航项位置变了: 前 {cx} / 后 {cx2}")

    print("  往返校验:")
    bad = []
    for key in NAV_KEYS[1:]:
        x = tab_x.get(key)
        if x is None:
            bad.append(key)
            print(f"    {key:<11} 未定位到导航项  FAIL")
            continue
        click(hwnd, x, bar_y)
        pump(0.7)
        img_rt, sig = settle_shot(hwnd)
        d = dist(pages[key], sig)
        ok = d <= SAME_TOL
        if not ok:
            bad.append(key)
            # 失败帧落盘:光看数字看不出"到底停到哪一页了",存图才能人眼判断
            img_rt.save(os.path.join(OUT, f"exe_rt_FAIL_{key}.png"))
        print(f"    {key:<11} x={x:<4} 距离 {d:<4} {'OK' if ok else 'FAIL'}"
              + (f"  存图 exe_rt_FAIL_{key}.png" if not ok else ""))

    u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    pump(1.2)
    kill_all()
    try:
        p.wait(timeout=10)
    except Exception:
        pass

    print(f"观察到页面: {' -> '.join(order)}  ({len(order)}/{len(NAV_KEYS)})")
    if len(order) != len(NAV_KEYS) or bad:
        print(f"FAIL 页数或往返校验不通过,缺失/异常: {bad or '页数不足'}")
        return 1
    print(f"PASS {len(NAV_KEYS)} 页全部真实切换、截图,且往返校验一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
