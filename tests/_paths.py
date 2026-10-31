# -*- coding: utf-8 -*-
"""统一的产物路径解析。

产物都在 dist\\ 下（build.ps1 的输出目录）：

    dist\\pivot\\pivot.exe    主程序（onedir，同级还有 _internal\\ 与 apps\\）

测试脚本里散落着二十来处硬编码路径，与其逐个改、不如都来这里取 ——
换布局时只改这一个文件，也不会漏掉某个脚本让它悄悄跑空。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def exe_path():
    """产物主程序的路径。"""
    return os.path.join(ROOT, "dist", "pivot", "pivot.exe")


def apps_dir():
    """exe 同级的外置 apps\\（用户可裁剪的那份）。"""
    beside = os.path.join(os.path.dirname(exe_path()), "apps")
    if os.path.isdir(beside):
        return beside
    return os.path.join(ROOT, "apps")


def app_dir():
    """程序目录（onedir 下是含 _internal\\ 的那层）。"""
    return os.path.dirname(exe_path())


def shots_dir():
    """测试截图输出目录（tests\\_shots\\，已在 .gitignore 里）。"""
    d = os.path.join(ROOT, "tests", "_shots")
    os.makedirs(d, exist_ok=True)
    return d
