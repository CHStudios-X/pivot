<div align="center">

# 枢 · Pivot

**Windows 桌面小工具箱**：鼠标连点、键盘连按、按键改绑。<br>
深色磨砂玻璃界面，功能是一个个独立文件 —— 删掉哪个，哪个功能就没了，程序照常跑。

![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4?style=flat-square)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-3DA639?style=flat-square)
![Version](https://img.shields.io/badge/version-1.3.0-black?style=flat-square)

</div>

<table>
<tr>
<td width="50%"><img src="docs/screenshots/home.png" alt="主页"></td>
<td width="50%"><img src="docs/screenshots/clicker.png" alt="连点器"></td>
</tr>
<tr>
<td><img src="docs/screenshots/keys.png" alt="键盘连按"></td>
<td><img src="docs/screenshots/appearance.png" alt="外观"></td>
</tr>
</table>

---

## 它能做什么

| 工具 | 说明 |
|---|---|
| **连点器** | 左键 / 双击 / 右键，毫秒级间隔，固定坐标或跟随鼠标，可设次数或无限循环。`F6` 开始（3 秒倒计时）、`F7` 停止。 |
| **键盘连按** | 在虚拟键盘上点选要连按的键，每个键单独设次数与间隔，同时驱动多个键。 |
| **按键改绑** | 全局把 A 键映射成 B 键，支持多组；录制框按一下新键即可，`Esc` 取消。 |
| **外观** | 换壁纸、调玻璃透明度与模糊强度、开关动效，设置即时生效并持久化。 |
| **自动更新** | 启动后台静默检查，也可手动点「检查更新」。下载 → 校验 SHA256 → 替换 → 自动重启。 |
| **设置** | 全局热键改绑（支持 `F1`–`F24` 与组合键）、安全中止、开机启动。 |

> **安全中止**：连点过程中把鼠标快速甩到屏幕左上角即停（可在设置里关闭）。
> 关掉之后就没有撤销手段了，请谨慎。

## 下载

到 **[Releases](https://github.com/你的账号/pivot/releases)** 页下载最新版：

- **安装包** `Pivot_Setup_x.y.z.exe` —— 推荐。约 35 MB，用户级安装（装到 `%LOCALAPPDATA%\Programs\Pivot`），**不需要管理员权限**。
  安装时可勾选「以管理员身份运行运行」，全局热键需要它。
- **绿色版** `Pivot_x.y.z_win64.zip` —— 解压双击 `pivot.exe` 即可，不写注册表（设置仍存在 `HKCU\Software\Pivot`）。

系统要求：Windows 10 / 11（64 位）。

## 从源码运行

```powershell
git clone https://github.com/你的账号/pivot.git
cd pivot

python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

python pivot.py
```

全局热键（`keyboard` 库）需要管理员权限，否则只能改绑、无法真正生效。

## 构建

需要 Python 3.9+；打安装包还要 [Inno Setup 6](https://jrsoftware.org/isinfo.php)
（`winget install --id JRSoftware.InnoSetup`）。

```powershell
# 只出绿色版：dist\pivot\pivot.exe（onedir，含 _internal\ 与 apps\）
.\build.ps1

# 一键出包：绿色版 + 安装包 + 更新包
.\build_installer.ps1
```

产物都在 `dist\`：

```
dist\pivot\pivot.exe          绿色版主程序（onedir）
dist\pivot\apps\              外置功能目录
dist\Pivot_Setup_1.3.0.exe    安装包
dist\update\                  更新包 + version.json
```

> 构建脚本**不写死任何绝对路径**，`clone` 到哪台机器都能直接跑；
> 会自己找 `py -3` 或 PATH 里的 `python` 来建 venv。

## 目录结构

```
pivot\
├── pivot.py            外壳：窗口骨架、闪屏、标题栏、底栏、热键、功能装载器
├── pivot_kit.py        公共件：主题常量、玻璃面板、按钮、开关、虚拟键盘
├── updater_core.py     更新内核：检测 / 下载 / 校验 / 生成替换脚本（不依赖 Qt）
├── apps\               功能模块 —— 一个文件一个功能
│   ├── home.py         主页
│   ├── clicker.py      连点器
│   ├── keys.py         键盘连按
│   ├── remap.py        按键改绑
│   ├── appearance.py   外观
│   ├── settings.py     设置
│   └── update.py       更新页
├── tests\              断言式回归脚本（见下）
├── docs\               协议、发布流程、截图
├── assets\ icon\ lang\ 资源
├── build.ps1           PyInstaller 打包
├── build_installer.ps1 一键出包（调用 build.ps1 + ISCC）
├── installer.iss       Inno Setup 安装脚本
└── make_update.py      打更新包并生成 version.json
```

## 三个值得说的设计

### 1. 功能是文件，不是开关

每个 `apps\*.py` 导出 `META` 与 `Feature`，外壳启动时扫描目录动态装载：

```python
META = {
    'id': 'clicker', 'name': '连点器', 'nav': '连点器',
    'order': 20, 'icon': 'mouse', 'builder': '_build_clicker',
}
```

装载是四层容错的：文件不存在跳过 → 导入报错跳过 → 构建异常显示占位页 →
契约不合法跳过。任何一步失败都只影响那一个功能，**外壳照常启动**。

所以用户想裁功能，直接删 `apps\` 里的文件就行；想加功能，丢一个新 `.py` 进去
（照着 `apps\说明.txt` 的契约写），底栏和主页会自动多一项。
更新时也不会把你删掉的功能装回来 —— 程序用 `_apps_state.json` 记录过「哪些是你删的」。

### 2. Windows 上没法自己覆盖自己

运行中的 exe 被系统锁着，`_internal\` 里的 DLL 已映射进内存，主程序**改不了自己**。
所以更新的最后一步是：解压新版本到临时目录 → 生成一个 `.bat` → 拉起它 → 主程序退出 →
脚本等进程消失 → `robocopy` 覆盖 → 重新启动 → 自删。

这段脚本有几个坑（`cmd /c` 会吃掉最外层引号、中文路径要 ANSI 编码、8.3 短名），
都写在 `updater_core.py` 的注释里了。

### 3. 版本号只有一个地方

`pivot_kit.py` 的 `APP_VER` 是唯一来源。`build.ps1` 用正则读它，
再以 `/DMyAppVersion=` 传给 ISCC。两处各写一份版本号，是自动更新误判的头号来源。

## 测试

`tests\` 里是断言式脚本，不是 pytest —— 每个都直接跑，失败会打印具体是哪一条：

```powershell
python tests\_apps_check.py        # 功能模块契约（不用起界面）
python tests\_kb_check.py          # 键盘连按引擎
python tests\_remap_ui_check.py    # 改绑录制框（真发 QKeyEvent）
python tests\_update_check.py      # 更新链路（本地起 HTTP 服务，含真实替换两轮）
```

出包之后再跑这几个（会启动 `dist\pivot\pivot.exe` 并截图断言）：

```powershell
python tests\_exe_pages_check.py   # 逐页切换 + 像素级稳定性
python tests\_exe_apps_check.py    # 删功能/加功能/空目录/无目录
python tests\_install_test.py      # 静默安装 → 校验 → 卸载 → 查残留
```

## 已知限制

- **只在 Windows 10 / 11 上测过**。Windows 10 的亚克力依赖未公开 API，个别版本不生效，
  此时界面自动降级为不透明深色，功能不受影响。
- 拖动窗口时亚克力可能轻微掉帧（Win10 已知表现）。
- `keyboard` 库做全局钩子，部分杀软会误报。
- **自动点击可能违反目标软件或游戏的服务条款，也可能被反作弊判定。** 自担风险。
- 更新源默认是占位地址，不配置也能用，只是更新页会显示「更新源尚未配置」。
  配置方法见 [docs/PUBLISH.md](docs/PUBLISH.md)。

## 参与

Issue 和 PR 都欢迎。改代码前建议先看一眼 `apps\说明.txt`（功能模块契约），
以及跑一遍 `tests\_apps_check.py` 确认没破坏装载机制。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE) © 2026 CHStudios

第三方依赖各自遵循其许可证：PySide6（LGPLv3）、pyautogui（BSD-3）、keyboard（MIT）。
图标与背景图为项目自带资源。
