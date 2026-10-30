# update/ —— 自动更新的清单目录

客户端启动后会读这个目录里的 `version.json`（通过 raw 直链），
所以**它必须随仓库提交**，不能放 `.gitignore`。

发布一版新版时：

```powershell
.\build_installer.ps1
Copy-Item dist\update\version.json update\version.json
git add update\version.json
git commit -m "release: x.y.z"
git push
```

提交之后，已安装的旧版本才会看到新版本。

完整流程见 [../docs/PUBLISH.md](../docs/PUBLISH.md)。

---

这个仓库**还没有配置更新源**，所以目录里暂时没有 `version.json`。
配好 `updater_core.py` 里的两处 `REPLACE_ME` 之后，第一次发版会生成它。
在那之前，软件的更新页会显示「更新源尚未配置」—— 这是预期行为，
不会假装"已是最新"，也不会反复重试。
