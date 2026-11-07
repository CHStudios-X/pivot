# Build pivot.exe with PyInstaller (PowerShell, ASCII-safe)
$ErrorActionPreference = "Stop"

# 项目根 = 本脚本所在目录(不写死绝对路径, clone 到哪都能跑)
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir     = Join-Path $projectDir "dist"        # 构建产物(已在 .gitignore 里)
$venvDir    = Join-Path $projectDir ".venv"
$venvPy     = Join-Path $venvDir "Scripts\python.exe"

# ---------- 用来创建 venv 的 Python ----------
# 不写死路径:先试 py 启动器,再试 PATH 里的 python。
# (原来的版本写死了某台机器上的 python.exe,换台机器 clone 下来直接构建失败)
# 注意:只有在 .venv 不存在时才需要它 —— 检查放到下面创建分支里做,
#       否则已经有 venv 的机器也会因为找不到 py 启动器而直接退出。
$pyCmd  = $null
$pyArgs = @()
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $pyCmd  = "py.exe"
    $pyArgs = @("-3")
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    $pyCmd = "python.exe"
}

# ---------- 自动更新：发布参数 ----------
# Release 附件的下载前缀（拼 version.json 里的绝对地址）。
# fork 后换成你自己的仓库；留占位符则只出包不发布。
$UpdateBaseUrl = "https://github.com/CHStudios-X/pivot/releases/download"

Set-Location $projectDir

# ---------- 版本号：唯一来源是 pivot_kit.py 的 APP_VER ----------
$kitFile = Join-Path $projectDir "pivot_kit.py"
$verMatch = Select-String -Path $kitFile -Pattern '^APP_VER\s*=\s*"([0-9][0-9.]*)"' -Encoding utf8
if (-not $verMatch) { throw "读不到 APP_VER（pivot_kit.py 第 62 行附近）" }
$appVer = $verMatch.Matches[0].Groups[1].Value
Write-Host "版本号: $appVer (来自 pivot_kit.py)"

Write-Host "[1/4] Creating venv..."
if (!(Test-Path $venvDir)) {
    if (-not $pyCmd) {
        throw "未找到 Python。请安装 Python 3.9+ 并勾选 Add to PATH，" +
              "或用 winget install Python.Python.3.12"
    }
    & $pyCmd @pyArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "venv 创建失败（$pyCmd @pyArgs）" }
} else {
    Write-Host "    venv exists, skip"
}

Write-Host "[2/4] Installing deps..."
# 不接 | Out-Null：某些受限环境下 PowerShell 会把管道里的 exe 当成"文档"
# 去 ShellExecute，报 CantActivateDocumentInPipeline 而整个构建中断。
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r (Join-Path $projectDir "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "[3/4] Cleaning previous output..."
# 先杀掉可能还在运行的旧 exe(占用 exe/_internal 会导致
# "对路径 pivot.exe 的访问被拒绝")
Get-Process pivot -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 800
foreach ($p in @("build", "pivot.spec")) {
    $full = Join-Path $projectDir $p
    if (Test-Path $full) { Remove-Item -Recurse -Force $full }
}
# 产物目录里只清自己的输出;安装包由 build_installer.ps1 编译时覆盖
if (!(Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
# onedir 产物是一个目录(含 _internal\)，旧的单文件 exe 与旧目录都要清掉，
# 否则新老两种布局会混在一起，装出来的包体积与内容都不对。
$oldExe = Join-Path $outDir "pivot.exe"
if (Test-Path $oldExe) { Remove-Item -Force $oldExe }
$oldAppDir = Join-Path $outDir "pivot"
if (Test-Path $oldAppDir) { Remove-Item -Recurse -Force $oldAppDir }

Write-Host "[4/4] Running PyInstaller..."

# ---------- exe 版本资源 ----------
# 资源管理器「属性 → 详细信息」里的公司/产品/版权/文件说明来自这段。
# 不设的话四个字段全空，任务管理器里只会显示一个没描述的 pivot.exe。
# 版本号从上面读到的 $appVer 现拆现填，不在这里维护第二份。
$viDir  = Join-Path $projectDir "build"
if (!(Test-Path $viDir)) { New-Item -ItemType Directory -Force -Path $viDir | Out-Null }
$viPath = Join-Path $viDir "version_info.txt"
$vp = @($appVer -split '\.' | ForEach-Object { [int]$_ })
while ($vp.Count -lt 4) { $vp += 0 }
$vTuple = ($vp[0..3] -join ", ")
$viText = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($vTuple),
    prodvers=($vTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404b0', [
        StringStruct('CompanyName', 'CHStudios'),
        StringStruct('FileDescription', '枢 Pivot'),
        StringStruct('FileVersion', '$($appVer).0'),
        StringStruct('InternalName', 'pivot'),
        StringStruct('LegalCopyright', 'Copyright (C) 2026 CHStudios. All rights reserved.'),
        StringStruct('OriginalFilename', 'pivot.exe'),
        StringStruct('ProductName', '枢'),
        StringStruct('ProductVersion', '$appVer')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"@
# 必须 UTF-8 无 BOM：PyInstaller 用 utf-8 解码这段文本，BOM 会留在首行
[System.IO.File]::WriteAllText($viPath, $viText, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "    版本资源 -> $viPath (v$appVer)"

# 注意: 不要加 --collect-all PySide6,会让体积从 ~46MB 暴增到 ~240MB
# --icon    : 写入 exe 自身的图标资源(资源管理器/任务栏)
# --version-file: 写入 exe 的版本资源(属性页的公司/产品/版权)
# --add-data: 把 ico / 背景图打进包内,运行时用 _res_path() 定位
$icoPath = Join-Path $projectDir "icon\app.ico"
$bgPath  = Join-Path $projectDir "assets\bg.jpg"
$appsDir = Join-Path $projectDir "apps"
if (!(Test-Path $bgPath)) { throw "missing background image: $bgPath" }
if (!(Test-Path $appsDir)) { throw "missing apps directory: $appsDir" }
# 顺手清掉 __pycache__（跑测试留下的），别把它打进包
$appsCache = Join-Path $appsDir "__pycache__"
if (Test-Path $appsCache) { Remove-Item -Recurse -Force $appsCache }
# 注意: apps\ 里的功能模块是运行时按文件路径动态装载的, PyInstaller 的静态
# 分析看不到它们 —— 必须用 --add-data 原样打进去。且保持 .py 原文件(不编译进
# PYZ),这样"exe 同级的 apps\ 覆盖内置那份"的机制才成立。
# ★ 必须用 --onedir 而不是 --onefile:
#   onefile 每次启动都会把整包解压到 %TEMP%\_MEIxxxxxx，正常退出才清理；
#   一旦被 taskkill / 崩溃退出，残留就永久留在 Temp。实测累积 112 个 _MEI*
#   目录共 12.5 GB，直接把 C 盘撑到 100%。onedir 原地运行，不解压、零残留。
& $venvPy -m PyInstaller `
    --noconfirm `
    --onedir `
    --windowed `
    --distpath "$outDir" `
    --name pivot `
    --icon $icoPath `
    --version-file $viPath `
    --add-data "$icoPath;icon" `
    --add-data "$bgPath;assets" `
    --add-data "$appsDir;apps" `
    --collect-all pyautogui `
    (Join-Path $projectDir "pivot.py")
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

$appDir = Join-Path $outDir "pivot"               # onedir 产物目录(含 _internal\)
$exe    = Join-Path $appDir "pivot.exe"

# 绿色版也带一份外置 apps\：用户可以直接删里面的文件来裁功能
# (onedir 下 apps\ 要放在 exe 同级，也就是产物目录里面)
$outApps = Join-Path $appDir "apps"
if (Test-Path $outApps) { Remove-Item -Recurse -Force $outApps }
Copy-Item -Recurse -Force $appsDir $outApps
$outCache = Join-Path $outApps "__pycache__"
if (Test-Path $outCache) { Remove-Item -Recurse -Force $outCache }
# 产物目录里可能留着上次跑测试时程序自己写的裁剪状态文件 ——
# 那是本机运行痕迹，不该跟着安装包发给别人（用户第一次启动会自己生成）。
$staleState = Join-Path $appDir "_apps_state.json"
if (Test-Path $staleState) { Remove-Item -Force $staleState }

Write-Host ""
Write-Host "[update] 打更新包并生成清单..."

# 更新包 = 整个 onedir 目录压成一个 zip。这样升级不用重装，覆盖文件即可。
# 注意这个 zip 会随版本号变化，旧的留在磁盘上便于回退。
$updateDir = Join-Path $outDir "update"
if (Test-Path $updateDir) { Remove-Item -Recurse -Force $updateDir }

$notesFile = Join-Path $projectDir "update_notes.txt"
$makeArgs = @(
    (Join-Path $projectDir "make_update.py"),
    "--app-dir", $appDir,
    "--out-dir", $updateDir,
    "--version", $appVer,
    "--base-url", $UpdateBaseUrl
)
# 更新说明从文件读：中文走命令行参数在 PowerShell 5.1 下容易被转成 ANSI
if (Test-Path $notesFile) { $makeArgs += @("--notes-file", $notesFile) }
& $venvPy @makeArgs
if ($LASTEXITCODE -ne 0) { throw "更新包生成失败" }

Write-Host ""
Write-Host "============================================"
Write-Host " Build done (onedir): $appDir"
Write-Host " 版本   : $appVer"
Write-Host " 主程序 : $exe"
Write-Host "         $([math]::Round((Get-Item $exe).Length / 1MB, 2)) MB"
$foldSize = (Get-ChildItem -Recurse -File $appDir |
             Measure-Object -Property Length -Sum).Sum
Write-Host " 整包   : $([math]::Round($foldSize / 1MB, 2)) MB (含 _internal\)"
Write-Host " 外置功能目录: $outApps"
Write-Host "   (删掉里面任何一个 .py,对应的功能就没了,其余照常)"
Write-Host " 更新包 : $updateDir"
Write-Host " Tip: run as Administrator for global hotkeys."
Write-Host "============================================"