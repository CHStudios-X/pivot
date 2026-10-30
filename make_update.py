# -*- coding: utf-8 -*-
"""把 onedir 产物打成更新包，并生成 version.json。

为什么要单独一个脚本而不是 Compress-Archive：
  * 需要算 SHA256 并写进清单，PowerShell 那条链容易半路失败；
  * 要排除 __pycache__ 与状态文件，否则用户装完会带上别人的缓存；
  * 清单的字段结构（apps / min / notes）必须和 updater_core 的一致，
    放在同一个仓库里改起来才不容易漂。

用法（build.ps1 会自动调用）：
    python make_update.py --app-dir dist\\pivot --version 1.3.0 \\
        --out-dir dist\\update --base-url https://github.com/你/仓库/releases/download \\
        --notes "修复了……"

产物 dist\\update\\ 里有两样：
    Pivot_<ver>_win64.zip   Release 附件，上传到 GitHub Releases
    version.json            清单，提交到仓库的 update/ 目录（客户端从这里读）
"""
import argparse
import hashlib
import json
import os
import sys
import time
import zipfile

EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_FILES = {"_apps_state.json", ".installed.json"}


def collect(app_dir):
    """遍历产物目录，返回 [(绝对路径, 包内相对路径)]，顺序稳定。"""
    items = []
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(files):
            if name in EXCLUDE_FILES or name.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, app_dir).replace("\\", "/")
            items.append((full, rel))
    return items


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-dir", required=True, help="onedir 产物目录")
    ap.add_argument("--out-dir", required=True, help="更新包输出目录")
    ap.add_argument("--version", required=True)
    ap.add_argument("--base-url", default="",
                    help="Release 下载前缀；给了就写绝对地址")
    ap.add_argument("--notes", default="")
    ap.add_argument("--notes-file", default="",
                    help="从 UTF-8 文件读更新说明（避免命令行传中文的编码坑）")
    ap.add_argument("--min", default="",
                    help="低于它的客户端强制更新；留空表示不强制")
    args = ap.parse_args()

    app_dir = os.path.abspath(args.app_dir)
    out_dir = os.path.abspath(args.out_dir)
    if not os.path.isdir(app_dir):
        print(f"找不到产物目录: {app_dir}")
        return 2

    items = collect(app_dir)
    if not items:
        print("产物目录是空的")
        return 2

    os.makedirs(out_dir, exist_ok=True)
    name = f"Pivot_{args.version}_win64.zip"
    zip_path = os.path.join(out_dir, name)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    t0 = time.time()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for full, rel in items:
            zf.write(full, rel)
    cost = time.time() - t0

    size = os.path.getsize(zip_path)
    digest = sha256_of(zip_path)

    apps = sorted(os.path.basename(p) for p, r in items
                  if r.startswith("apps/") and r.count("/") == 1
                  and r.endswith(".py"))

    url = name
    if args.base_url:
        url = args.base_url.rstrip("/") + f"/v{args.version}/{name}"

    notes = args.notes
    if args.notes_file and os.path.exists(args.notes_file):
        with open(args.notes_file, "r", encoding="utf-8-sig") as fh:
            notes = fh.read()

    manifest = {
        "latest": args.version,
        "date": time.strftime("%Y-%m-%d"),
        "notes": notes.strip(),
        "packages": {"full": {"url": url, "size": size, "sha256": digest}},
        "apps": apps,
    }
    if args.min.strip():
        manifest["min"] = args.min.strip()

    mpath = os.path.join(out_dir, "version.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f" 更新包 : {zip_path}")
    print(f"          {size / 1024 / 1024:.2f} MB，{len(items)} 个文件，"
          f"压缩耗时 {cost:.1f}s")
    print(f" SHA256 : {digest}")
    print(f" 清单   : {mpath}")
    print(f" 功能模块: {' / '.join(apps) if apps else '(无)'}")

    exe = os.path.join(app_dir, "pivot.exe")
    if os.path.exists(exe):
        print(f" 主程序 : {os.path.getsize(exe) / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
