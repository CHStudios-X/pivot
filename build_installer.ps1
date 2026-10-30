# ============================================================
#  一键出包: 打包 exe  ->  编译安装包
#
#  前置: 需要 Inno Setup 6 (ISCC.exe)
#        未安装时执行:
#        winget install --id JRSoftware.InnoSetup --source winget
#        或用 winget download 下载后静默安装 (/VERYSILENT /CURRENTUSER)
#
#  产物: dist\pivot\                        (绿色版主程序目录, onedir 含 _internal\)
#        dist\pivot\pivot.exe               (主程序)
#        dist\Pivot_Setup_x.y.z.exe         (安装包)
# ============================================================
$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir     = Join-Path $projectDir "dist"        # 与 build.ps1 同一个产物目录
$iss        = Join-Path $projectDir "installer.iss"

# 查找 ISCC.exe(用户级安装 / 全局安装都试一遍)
$candidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw ("未找到 ISCC.exe。请先安装 Inno Setup 6:`n" +
           "  winget install --id JRSoftware.InnoSetup --source winget")
}
Write-Host "使用编译器: $iscc" -ForegroundColor DarkGray

# ---------- 1/2 打包主程序 ----------
Write-Host "[1/2] 打包主程序..." -ForegroundColor Cyan
& (Join-Path $projectDir "build.ps1")
if ($LASTEXITCODE -ne 0) { throw "主程序打包失败" }

$exe = Join-Path $outDir "pivot\pivot.exe"               # onedir 产物目录内的主程序
if (-not (Test-Path $exe)) { throw "未找到 $exe" }

# ---------- 版本号同样从 pivot_kit.py 读，不在这里再写一份 ----------
# 两处各维护一份版本号是自动更新的头号事故来源：客户端拿 1.2.6 去比 1.2.7，
# 会以为自己"该更新"而反复下载同一个包。
$kitFile = Join-Path $projectDir "pivot_kit.py"
$verMatch = Select-String -Path $kitFile -Pattern '^APP_VER\s*=\s*"([0-9][0-9.]*)"' -Encoding utf8
if (-not $verMatch) { throw "读不到 APP_VER（pivot_kit.py）" }
$appVer = $verMatch.Matches[0].Groups[1].Value
Write-Host "安装包版本: $appVer" -ForegroundColor DarkGray

# ---------- 2/2 编译安装包 ----------
Write-Host "[2/2] 编译安装包..." -ForegroundColor Cyan
Set-Location $projectDir
# ISCC 的进度行有一部分走 stderr,而脚本开头设了 $ErrorActionPreference = "Stop"
# —— 原生命令的 stderr 会被当成错误记录直接中断整条构建(表现为
#   "PyInstaller 成功、安装包那步莫名其妙 exit 1")。这里临时放宽。
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $iscc "/DMyAppVersion=$appVer" $iss 2>&1 | ForEach-Object { Write-Host $_ }
$isccCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($isccCode -ne 0) { throw "安装包编译失败 (ISCC exit $isccCode)" }

$setup = Get-ChildItem $outDir -Filter "Pivot_Setup_*.exe" |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
$appDir = Split-Path -Parent $exe
$foldSize = (Get-ChildItem -Recurse -File $appDir |
             Measure-Object -Property Length -Sum).Sum
Write-Host " 绿色版 : $appDir"
Write-Host "         主程序 $exe"
Write-Host "         整包 $([math]::Round($foldSize / 1MB, 2)) MB (含 _internal\)"
Write-Host " 安装包 : $($setup.FullName)"
Write-Host "         $([math]::Round($setup.Length / 1MB, 2)) MB"
Write-Host "============================================" -ForegroundColor Green
Write-Host " 安装/卸载自测:"
Write-Host "   安装 $($setup.Name) /VERYSILENT /DIR=<临时目录> /TASKS=`"`""
Write-Host "   卸载 <临时目录>\unins000.exe /VERYSILENT"
