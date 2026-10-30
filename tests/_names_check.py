# -*- coding: utf-8 -*-
"""静态检查：源码里有没有"用了但从来没定义过"的全局名字。

为什么需要它：功能模块被切开之后，一个名字如果在搬家时落单（比如外壳还在
用 _resolve_bg，而它被搬进了 apps\\），编译期完全看不出来 —— 只有跑到那一行
才 NameError，而且可能藏在某条很少走的分支里。这个检查用最笨但可靠的办法
把它揪出来：收集模块里**所有被绑定过的名字**（赋值/def/class/参数/import/
except/comprehension 目标），再看哪些名字被读取过却不在其中。

不做的（避免误报）：不做真正的词法作用域分析，所以局部变量和全局变量一视平
同仁；这也意味着它抓不出"作用域用错"，但抓得出"这个名字在整个文件里从没出现过"。

运行: python _names_check.py
"""
import ast
import builtins
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)

BUILTIN = set(dir(builtins)) | {"__file__", "__name__", "__doc__",
                                "self", "cls", "__class__"}


def bound_names(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.alias):
            out.add((n.asname or n.name).split(".")[0])
        elif isinstance(n, ast.Global):
            out.update(n.names)
    return out


def used_names(tree):
    return {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def check(path, label):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    bound = bound_names(tree) | BUILTIN
    missing = sorted(used_names(tree) - bound)
    return label, missing


def main():
    targets = [("外壳", os.path.join(SRC, "pivot.py")),
               ("公共件", os.path.join(SRC, "pivot_kit.py")),
               ("更新内核", os.path.join(SRC, "updater_core.py")),
               ("更新包工具", os.path.join(SRC, "make_update.py"))]
    apps_dir = os.path.join(SRC, "apps")
    for fn in sorted(os.listdir(apps_dir)):
        if fn.endswith(".py"):
            targets.append((f"apps/{fn}", os.path.join(apps_dir, fn)))

    bad = 0
    for label, path in targets:
        label, missing = check(path, label)
        if missing:
            bad += len(missing)
            print(f"  [FAIL] {label}: 未定义的名字 -> {missing}")
        else:
            print(f"  [PASS] {label}: 没有未定义的名字")
    if bad:
        print(f"\n共 {bad} 处未定义名字")
        return 1
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
