# 发布一版新版

以发布 `1.3.1` 为例，全程在仓库根目录执行。

## 0. 换成你自己的仓库（可选）

这份仓库默认指向 **`CHStudios-X/pivot`**，地址已经写进源码，开箱即用。

如果你 fork 到了别的账号，改这几处：

| 位置 | 内容 | 改成 |
|---|---|---|
| `README.md` | `CHStudios-X`（下载链接与 clone 命令，共 2 处） | 你的 GitHub 用户名 |
| `updater_core.py` | `CHStudios-X`（`UPDATE_MANIFEST_URLS` 里 3 个清单地址 + `UPDATE_BASE_URLS` 里 1 个下载前缀） | 账号名 |
| `build.ps1` | `CHStudios-X`（1 处） | 账号名 |
| `LICENSE` / `pivot_kit.py` / `installer.iss` | `CHStudios` | 你的名字或组织名 |
| `installer.iss` | `AppId` | 换一个新的 GUID，否则会和原版互相覆盖 |

```powershell
# 全局搜一遍还有没有漏的
git grep -n "CHStudios-X"
```

改完记得 `git commit`，并**重新打包一次** —— 地址是在打包时写进 exe 的。

> 留 `REPLACE_ME` 占位符时程序不会崩，更新页会显示「更新源尚未配置」，
> 而不会假装"已是最新"。

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

## 3. 出包

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

## 4. 发 Release

在 GitHub 上新建 Release，tag 用 `v1.3.1`，然后上传两个附件：

- `Pivot_Setup_1.3.1.exe`（安装包）
- `Pivot_1.3.1_win64.zip`（更新包，**必须传**，自动更新下载的就是它）

> 附件地址要和清单里的 `url` 拼得上。`make_update.py` 生成的是
> `v1.3.1/Pivot_1.3.1_win64.zip`，所以 tag 名必须是 `v1.3.1`。

## 5. 提交新清单

把 `dist\update\version.json` 复制到仓库的 `update\` 目录并提交：

```powershell
Copy-Item dist\update\version.json update\version.json
git add update\version.json
git commit -m "release: 1.3.1"
git push
```

客户端不再直连 raw：清单按 jsDelivr `fastly` → `jsdelivr.b-cdn.net` → raw 的顺序依次尝试，
所以**这一步提交后，已安装的旧版本才会看到新版本**。

jsDelivr 有约 12 小时缓存。想让新版立刻可见，提交后在浏览器打开一次：

```
https://purge.jsdelivr.net/gh/CHStudios-X/pivot@main/update/version.json
```

（`purge.jsdelivr.net` 在部分网络下命令行访问不通，用浏览器打开最省事。
返回 `{"status":"finished"}` 之类就算刷新成功。）

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
