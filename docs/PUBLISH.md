# 发布一版新版

以发布 `1.3.1` 为例，全程在仓库根目录执行。

## 1. 改版本号（只改一处）

`pivot_kit.py`：

```python
APP_VER = "1.3.1"
```

`build.ps1` 会用正则读它，再传给 Inno Setup。**不要在 `installer.iss` 里也写一份** ——
两处各维护一份是自动更新误判的头号来源。

## 2. 写更新说明

改 `update_notes.txt`（纯文本，会原样进 `version.json` 的 `notes` 字段，客户端会显示）：

```
修：改绑页在 4K 屏下录制框偏移
加：连点器支持每分钟次数上限
```

## 3. 配好你的仓库地址（只做一次）

两处要改，都在 `updater_core.py` 顶部：

```python
UPDATE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/你的账号/pivot/main/update/version.json")
UPDATE_BASE_URL = "https://github.com/你的账号/pivot/releases/download"
```

`build.ps1` 里还有一个同样的地址（用于生成清单里的附件绝对地址）：

```powershell
$UpdateBaseUrl = "https://github.com/你的账号/pivot/releases/download"
```

改完之后**要重新打包一次**，地址才会写进 exe。留 `REPLACE_ME` 时更新页会显示
「更新源尚未配置」，不会假装"已是最新"。

## 4. 出包

```powershell
.\build_installer.ps1
```

产物：

```
dist\pivot\pivot.exe              绿色版目录
dist\Pivot_Setup_1.3.1.exe        安装包
dist\update\Pivot_1.3.1_win64.zip 更新包
dist\update\version.json          清单
```

## 5. 发 Release

在 GitHub 上新建 Release，tag 用 `v1.3.1`，然后上传两个附件：

- `Pivot_Setup_1.3.1.exe`（安装包）
- `Pivot_1.3.1_win64.zip`（更新包，**必须传**，自动更新下载的就是它）

> 附件地址要和清单里的 `url` 拼得上。`make_update.py` 生成的是
> `v1.3.1/Pivot_1.3.1_win64.zip`，所以 tag 名必须是 `v1.3.1`。

## 6. 提交新清单

把 `dist\update\version.json` 复制到仓库的 `update\` 目录并提交：

```powershell
Copy-Item dist\update\version.json update\version.json
git add update\version.json
git commit -m "release: 1.3.1"
git push
```

客户端的静默检查读的是 `raw.githubusercontent.com/.../update/version.json`，
所以**这一步提交后，已安装的旧版本才会看到新版本**。

## 清单长什么样

```json
{
  "latest": "1.3.1",
  "min": "1.3.0",
  "date": "2026-11-02",
  "notes": "修：改绑页在 4K 屏下录制框偏移\n加：连点器支持每分钟次数上限",
  "packages": {
    "full": {
      "url": "v1.3.1/Pivot_1.3.1_win64.zip",
      "size": 49079162,
      "sha256": "ca518931f3d51625af97cdc1d716cd141313f4d7cbb0e95ee418757a9daee2ff"
    }
  },
  "apps": ["appearance.py", "clicker.py", "home.py", "keys.py", "more.py",
           "remap.py", "settings.py", "update.py"]
}
```

- `min`（可选）：低于这个版本强制更新。
- `apps`：**本版全量的功能模块列表**。客户端拿它和自己记录的
  `_apps_state.json` 比对，判断哪些是用户删的、哪些是新版新增的。

## 本地验证更新链路

不用真的发 Release 也能测 —— 起一个静态服务器指向 `dist\update\`：

```powershell
python -m http.server 8000 --directory dist\update
# 另开一个窗口
$env:PIVOT_UPDATE_URL = "http://127.0.0.1:8000/version.json"
.\dist\pivot\pivot.exe
```

或者直接跑现成的回归：

```powershell
python tests\_update_check.py       # 内核逻辑 + 两轮真实替换
python tests\_exe_update_check.py   # 真 exe 走完整链路
```

## 注意事项

- **onedir 结构变更只能整包替换**。从 onefile 时代升级过来的用户，`_internal\`
  是新出现的，`robocopy` 会整体覆盖，不会冲突。
- 发布前跑一遍 `tests\_install_test.py` —— 它会比对「装出来的 README / 协议」
  与「当前源文件」的 MD5。文档改完忘了重出安装包，这条会直接抓出来。
- 测试脚本会在 `dist\pivot\` 里写 `_apps_state.json`（程序运行痕迹）。
  **重新编译安装包前要清掉**，否则会把本机的运行状态发给别人。
  `build.ps1` 已经自动清理，手动编译 `installer.iss` 时要自己注意。
