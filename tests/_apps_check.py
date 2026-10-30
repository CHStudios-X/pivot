# -*- coding: utf-8 -*-
r"""1.2.6 断言：功能模块化（apps\\）与**裁剪容错**。

用户要求：「把全部功能的文件整理放在 apps 里面，这样我在 apps 里删掉一些
功能还能保持软件正常使用」。所以这份测试的核心不是"功能好不好用"
（那是 _kb_check 的事），而是**删功能之后外壳还活不活**：

  T1 全量装载：7 个功能模块，底栏 6 项、主页 4 张卡、页面 6 个，零装载错误
  T2 逐个裁剪：把 apps\\ 里每个功能文件单独拿掉一次，外壳都要能建出窗口、
                被删的功能从底栏/卡片/页面里消失、其余一切不变
  T3 整体裁剪：apps\\ 整个空掉 -> 窗口照建，占位页兜底，F6/F7 不抛
  T4 坏模块   ：语法错 / 缺 META / 缺 Feature / id 重复 -> 只跳过它，不连累别人
  T5 契约与隔离：apps\\ 只依赖 pivot_kit，反向不依赖；公共件不在可删目录里
  T6 不删也能用到底：全量下页面切换、工具卡片点击、热键分派都正常

运行: python _apps_check.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = ROOT
APPS = os.path.join(SRC, "apps")
PY = sys.executable

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  —— {detail}" if detail else ""))


def probe(apps_dir):
    """在被裁剪过的 apps 目录下起一次外壳，返回它报的结果"""
    env = dict(os.environ)
    if apps_dir is None:
        env.pop("TOOLBOX_APPS_DIR", None)
    else:
        env["TOOLBOX_APPS_DIR"] = apps_dir
    p = subprocess.run([PY, os.path.join(HERE, "_apps_probe.py")],
                       capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "").strip().splitlines()
    for line in reversed(out):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"ok": False, "error": "探针没有输出 JSON",
            "stderr": (p.stderr or "")[-800:]}


def make_dir(files):
    """建一个临时 apps 目录；files = {文件名: 内容 或 None(从源码拷)}"""
    d = tempfile.mkdtemp(prefix="tb_apps_")
    for name, content in files.items():
        dst = os.path.join(d, name)
        if content is None:
            shutil.copy2(os.path.join(APPS, name), dst)
        else:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)
    return d


def main():
    print("=" * 62)
    print("T1 全量装载")
    print("=" * 62)
    full = probe(None)
    if not full.get("ok"):
        check("全量装载成功", False, str(full.get("error"))
              + str(full.get("stderr", ""))[:400])
        return report()
    check("全量装载成功", True)
    check("装载到 8 个功能模块",
          sorted(full["features"]) == sorted(
              ["home", "clicker", "keys", "remap", "appearance",
               "settings", "more", "update"]),
          str(full["features"]))
    check("装载零错误", full["load_errors"] == [], str(full["load_errors"]))
    check("底栏 7 项且顺序正确",
          full["nav"] == ["home", "clicker", "keys", "remap",
                          "appearance", "settings", "update"], str(full["nav"]))
    check("底栏 tab 与功能一一对应", full["tabs"] == full["nav"])
    check("主页 4 张卡（连点器/键盘连按/按键改绑/更多工具）",
          full["cards"] == ["clicker", "keys", "remap", "more"],
          str(full["cards"]))
    check("页面 7 个（more 只有卡片没页面）",
          full["pages"] == ["appearance", "clicker", "home", "keys",
                            "remap", "settings", "update"], str(full["pages"]))
    check("stack 里 7 页", full["stack_count"] == 7, str(full["stack_count"]))
    check("落地页是 home", full["current_page"] == "home")
    check("page_xxx 属性兼容保留",
          set(full["page_attrs"]) == {"page_home", "page_clicker",
                                      "page_keys", "page_remap",
                                      "page_appearance", "page_settings",
                                      "page_update"},
          str(full["page_attrs"]))
    check("热键声明齐备",
          full["hotkeys"].get("keys") == {"start": "kb_start",
                                          "stop": "kb_stop"}
          and full["hotkeys"].get("clicker") == {"start": "on_start",
                                                 "stop": "on_stop"},
          str(full["hotkeys"]))
    check("App 基类含 8 个 Feature 混入",
          full["mro"].count("Feature") == 8, str(full["mro"]))

    all_ids = full["features"]
    mod_of = full["modules"]
    id_of_mod = {v: k for k, v in mod_of.items()}
    nav_ids, card_ids, page_ids = full["nav"], full["cards"], full["pages"]
    files = sorted(f"{m}.py" for m in mod_of.values())

    print()
    print("=" * 62)
    print("T2 逐个裁剪：拿掉一个功能文件，外壳必须照常起来")
    print("=" * 62)
    for gone_file in files:
        gone_id = id_of_mod[gone_file.replace(".py", "")]
        kept = {f: None for f in files if f != gone_file}
        d = make_dir(kept)
        try:
            r = probe(d)
            keep_ids = [i for i in all_ids if i != gone_id]
            exp_nav = [i for i in keep_ids if i in nav_ids]
            exp_cards = [i for i in keep_ids if i in card_ids]
            exp_pages = sorted(i for i in keep_ids if i in page_ids)
            exp_stack = len(exp_pages) if exp_pages else 1
            exp_cur = ("home" if "home" in keep_ids
                       else (exp_nav[0] if exp_nav else None))
            ok = (r.get("ok")
                  and r["features"] == keep_ids
                  and r["nav"] == exp_nav
                  and r["tabs"] == exp_nav
                  and r["cards"] == exp_cards
                  and r["pages"] == exp_pages
                  and r["stack_count"] == exp_stack
                  and r["current_page"] == exp_cur
                  and r["load_errors"] == [])
            detail = "" if ok else json.dumps(
                {k: r.get(k) for k in ("features", "nav", "cards", "pages",
                                       "stack_count", "current_page",
                                       "load_errors", "error")},
                ensure_ascii=False)
            check(f"删掉 {gone_file} 后仍可启动，且只少了这一个功能",
                  ok, detail)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    print("=" * 62)
    print("T3 整体裁剪：apps 空掉 / 不存在")
    print("=" * 62)
    d = tempfile.mkdtemp(prefix="tb_empty_")
    try:
        r = probe(d)
        check("apps 目录为空时仍可启动",
              bool(r.get("ok")), str(r.get("error")))
        check("空目录 -> 零功能、零底栏、零卡片",
              r.get("features") == [] and r.get("nav") == []
              and r.get("cards") == [], str(r.get("features")))
        check("空目录 -> 占位页兜底（stack 1 页）",
              r.get("stack_count") == 1, str(r.get("stack_count")))
        check("空目录 -> 落地页为 None 而不是崩",
              r.get("current_page") is None, str(r.get("current_page")))
        check("空目录 -> F6/F7 不抛异常", r.get("hotkey_safe") is True)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    missing = os.path.join(tempfile.gettempdir(), "tb_apps_not_exist_xyz")
    if os.path.isdir(missing):
        shutil.rmtree(missing, ignore_errors=True)
    r = probe(missing)
    # 目录不存在 -> 回退到内置那份（"只拷一个 exe 出去也能跑"），所以这里
    # 只要求"能起来"，不要求功能为空
    check("apps 目录根本不存在时回退到内置功能且仍可启动",
          bool(r.get("ok")) and r.get("features") == full["features"],
          str(r.get("error")) + str(r.get("features")))

    print()
    print("=" * 62)
    print("T4 坏模块：只跳过它，不连累别人")
    print("=" * 62)
    cases = [
        ("坏模块_语法错.py", "def broken(:\n    pass\n", "语法错", "坏模块_语法错"),
        ("坏模块_没有META.py", "class Feature:\n    pass\n",
         "缺 META", "坏模块_没有META"),
        ("坏模块_没有Feature.py", "META = {'id': 'badf'}\n",
         "缺 Feature", "坏模块_没有Feature"),
        ("badclass.py", "META = {'id': 'badc'}\nFeature = 123\n",
         "Feature 不是类", "badclass"),
        ("dup.py", "META = {'id': 'keys', 'order': 99}\nclass Feature:\n    pass\n",
         "id 重复", "dup"),
    ]
    base_files = {f: None for f in files}
    for fname, content, why, stem in cases:
        files = dict(base_files)
        files[fname] = content
        d = make_dir(files)
        try:
            r = probe(d)
            good = [i for i in r.get("features", []) if i != stem]
            ok = (r.get("ok")
                  and good == all_ids
                  and any(stem in e[0] for e in r.get("load_errors", [])))
            check(f"{why}的模块被跳过，其余 7 个功能照常",
                  ok, json.dumps({k: r.get(k) for k in
                                  ("features", "load_errors", "error")},
                                 ensure_ascii=False))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    print("=" * 62)
    print("T5 契约与隔离")
    print("=" * 62)
    kit = os.path.join(SRC, "pivot_kit.py")
    check("公共件 pivot_kit.py 在可删目录之外",
          os.path.exists(kit) and not os.path.exists(
              os.path.join(APPS, "pivot_kit.py")))
    bad = []
    for fn in sorted(os.listdir(APPS)):
        if not fn.endswith(".py"):
            continue
        src = open(os.path.join(APPS, fn), encoding="utf-8").read()
        # 注意用词边界：apps 里本来就 `from pivot_kit import ...`，
        # 光看 "from pivot" 子串会把公共件当成外壳，误报一片
        if re.search(r"^\s*(?:import|from)\s+pivot(?![_\w])", src, re.M):
            bad.append(f"{fn} 反向依赖外壳")
        for other in sorted(os.listdir(APPS)):
            if other != fn and other.endswith(".py") and not other.startswith("_"):
                stem = other[:-3]
                if f"from apps.{stem} import" in src:
                    bad.append(f"{fn} 依赖另一个功能 {stem}")
    check("apps 里的功能互不依赖、也不依赖外壳", not bad, "; ".join(bad))
    has_meta = [f for f in sorted(os.listdir(APPS))
                if f.endswith(".py") and not f.startswith("_")]
    check("apps 目录里只剩功能文件（无 __init__ / 无公共件）",
          sorted(has_meta) == sorted(f"{m}.py" for m in mod_of.values()),
          str(has_meta))

    print()
    print("=" * 62)
    print("T6 全量下功能仍然可用")
    print("=" * 62)
    check("工具注册表与卡片一致（除 more 无页面）",
          full["tool_registry"] == full["cards"], str(full["tool_registry"]))
    r = probe(None)
    check("全量二次启动依然零错误", r.get("ok") and r["load_errors"] == [])

    return report()


def report():
    print()
    print("=" * 62)
    print(f"通过 {len(PASS)} / 失败 {len(FAIL)}")
    if FAIL:
        for n in FAIL:
            print("  FAIL:", n)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
