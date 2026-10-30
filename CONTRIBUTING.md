# 参与开发

## 提 Issue

- **Bug**：请写清 Windows 版本、是否管理员运行、复现步骤。界面问题最好带截图。
- **功能建议**：说明使用场景比说明实现方式更有用。
- **不要**贴自动点击用在哪个游戏上 —— 那类请求一律不受理，见 README 的免责说明。

## 提 PR

跑一遍能跑的部分，再提交：

```powershell
python tests\_apps_check.py      # 功能模块契约 —— 改 apps\ 必跑
python tests\_names_check.py     # 静态检查：有没有用了但没定义的名字
python tests\_kb_check.py        # 改了连按
python tests\_remap_ui_check.py  # 改了改绑
python tests\_update_check.py    # 改了更新
```

出包相关的（`_exe_*.py`、`_install_test.py`）需要先 `.\build.ps1` 出产物，CI 里跑不动，
本地改动了打包逻辑时再跑。

## 加一个功能模块

`apps\` 里的契约写在 [`apps\说明.txt`](apps/说明.txt)，照着一个现有文件抄结构即可：

```python
META = {
    "id": "myfeat",
    "name": "我的功能",
    "nav": "我的功能",          # 填 None 就不进底栏
    "order": 80,
    "card": True,               # 是否在主页出卡片
    "builder": "_build_myfeat",
    "state": "page_myfeat",
}

class Feature:                  # 混入 App —— 方法里的 self 就是 App 实例
    def _build_myfeat(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
        pg = QWidget()
        QVBoxLayout(pg).addWidget(QLabel("hello"))
        return pg               # 必须返回页面控件
```

三条硬性约定：

1. **不要 `from pivot import ...`**。`apps\` 里的模块由外壳动态装载，
   反向依赖外壳会形成循环导入。要公共件就 `from pivot_kit import ...`。
2. **一个文件不要塞两个功能**。删一个文件 = 裁一个功能，这是整个设计的立足点。
3. **`META` 必须完整**。缺字段会被装载器判为契约非法而跳过 —— 这不会崩，
   但你的功能在界面上就是不出现，而且只在 stderr 留一行日志，很难发现。

改完跑 `python tests\_apps_check.py`，它会逐个模块检查契约与装载。

## 代码风格

没有强制 linter，跟着现有代码走：

- 4 空格缩进，行宽大致 90。
- 文件头 `# -*- coding: utf-8 -*-`，模块 docstring 写"为什么这么做"，不写"做了什么"。
- 注释用中文，讲踩过的坑。已有的注释里那些「实测」「踩过」都是真事，别删。
- 不引入新的第三方依赖，除非在 PR 里说明必要性并更新 `requirements.txt`。

## 不要做的事

- **不要在 `installer.iss` 里写版本号**。`pivot_kit.py` 的 `APP_VER` 是唯一来源。
- **不要把 `dist\`、`build\`、`.venv\` 提交上来**（`.gitignore` 已覆盖）。
- **不要提交 `_apps_state.json`**。那是运行痕迹，会泄露你本机删过哪些功能。
- **不要在 `apps\` 里读写绝对路径**。用户可能装在任意目录。
