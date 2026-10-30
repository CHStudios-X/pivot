# -*- coding: utf-8 -*-
"""容错探针：在**指定的 apps 目录**下把外壳窗口起起来，结果打成 JSON。

由 _apps_check.py 用各种"被裁剪过 / 被改坏过"的 apps 目录反复调用。
外壳必须每次都能把窗口建出来、并且能正常关闭 —— 这就是
「在 apps\\ 里删掉一些功能，软件还能正常用」的机器可验证形式。

只用环境变量 TOOLBOX_APPS_DIR 指定目录，不碰真实项目文件。

运行: python _apps_probe.py
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

res = {"ok": False}
try:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    import pivot as M

    qapp = QApplication(sys.argv)
    qapp.setFont(QFont(M._pick_font(), 9))
    qapp.setStyleSheet(M.QSS)

    win = M.App()
    metas = {m.META["id"]: dict(m.META) for m in M.FEATURES}
    res.update({
        "features": [m.META["id"] for m in M.FEATURES],
        "modules": {m.META["id"]: m.META["module"] for m in M.FEATURES},
        "nav": [i for i, m in metas.items() if m["nav"]],
        "cards": [t["id"] for t in M.TOOLS],
        "pages": sorted(win._feature_pages.keys()),
        "page_attrs": sorted(
            m["state"] for m in metas.values()
            if m["state"] and hasattr(win, m["state"])),
        "tabs": list(win.nav_tabs.keys()),
        "load_errors": [[a, b] for a, b in M.LOAD_ERRORS],
        "stack_count": win.stack.count(),
        "current_page": win._page,
        "hotkeys": {k: dict(v) for k, v in M._PAGE_HOTKEYS.items()},
        "mro": [c.__name__ for c in M.App.__mro__],
        "tool_registry": [t["id"] for t in win.tool_registry],
        "ok": True,
    })

    # 一个功能都没有时，F6/F7 不能抛异常（这时不可能有引擎被真的启动）
    if "clicker" not in res["features"]:
        win._on_hotkey("start")
        win._on_hotkey("stop")
        res["hotkey_safe"] = True

    win.close()                     # closeEvent 也必须容忍缺功能
    qapp.processEvents()
except Exception as e:              # noqa: BLE001
    res["error"] = f"{type(e).__name__}: {e}"
    res["trace"] = traceback.format_exc()

print(json.dumps(res, ensure_ascii=False))
