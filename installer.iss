; ============================================================
;  枢 Pivot —— Inno Setup 安装脚本
;  编译: ISCC.exe installer.iss
;  产物: ..\安装包\Pivot_Setup_<version>.exe
;
;  多语言: 安装前先弹「选择安装语言」对话框
;          - English  -> compiler:Default.isl
;          - 简体中文 -> lang\ChineseSimplified.isl
;  注意: 语言文本一律放在 .isl 里，不要在脚本里用 [Messages] 覆盖 ——
;        [Messages] 会作用于【所有】语言，会导致英文界面也显示中文。
;
;  注: 1.3.0 改名（工具盒子/ToolBox -> 枢/Pivot），AppId 随之更换 ——
;      新 AppId 让新版成为一个"独立产品"：装到独立目录、独立卸载项，
;      不会和 1.2.x 的 MouseMacro 目录互相覆盖或互相卸载。
;      代价是老版本要手动卸载一次（见 README 的升级说明）。
;
;  目录结构(本 .iss 与源码同级):
;      dist\        产物输出目录(绿色版 + 安装包)，已在 .gitignore 里
;      docs\        用户协议.txt(安装时作为 LicenseFile 展示并随装进 {app})
;      README.md    随装进 {app} 的说明文件
;      icon\, lang\, assets\  资源随本文件同级，路径不用改
; ============================================================

#define MyAppName       "枢"
#define MyAppNameEn     "Pivot"
; ★ 版本号由 build_installer.ps1 从 pivot_kit.py 的 APP_VER 读出后
;   用 /DMyAppVersion=1.2.7 传进来；这里的值只是**直接双击 ISCC 编译**时的兜底。
;   不要在两处各维护一份 —— 那正是自动更新会误判的根源。
#ifndef MyAppVersion
  #define MyAppVersion  "1.2.7"
#endif
#define MyAppPublisher  "CHStudios"
#define MyAppExeName    "pivot.exe"
#define ProdDir         "dist"
#define DocDir          "docs"

[Setup]
AppId={{35A1B8A4-5B4F-438D-B173-6BA3419E8B86}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
OutputDir={#ProdDir}
OutputBaseFilename=Pivot_Setup_{#MyAppVersion}
SetupIconFile=icon\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 用户级安装(装到 %LOCALAPPDATA%\Programs),全程免 UAC。
; 不启用 PrivilegesRequiredOverridesAllowed=dialog ——
; 那个「安装模式」选择框在语言资源加载前弹出,只能显示英文。
; 全局热键需要管理员权限的问题,改由「以管理员身份运行」任务解决。
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
DisableWelcomePage=no
AllowNoIcons=yes
; ★ 安装向导左侧品牌图 —— 上部应用图标,下部出品标记 CHStudios。
;   底色刻意取成 #E8F3F9(与 Inno 左面板同色),拼上去看不到接缝。
;   两张图给 Inno 按 DPI 自选,避免高 DPI 下把 1x 图拉糊。
WizardImageFile=assets\wizard_image.bmp,assets\wizard_image_2x.bmp
; ★ 用户协议页 —— 协议文本必须 UTF-8 带 BOM,否则 ISCC 会按 ANSI 解码,中文全乱
LicenseFile={#DocDir}\用户协议.txt
; ★ 安装前先让用户选语言
; 用 yes 而不是 auto —— auto 在实测中会被跳过（Inno 似乎记住了上次的语言选择），
; yes 可确保每次安装都弹出语言选择框。
ShowLanguageDialog=yes

[Languages]
; 顺序有讲究: 第一个语言被用作「语言选择对话框」自身的显示语言与默认选中项。
; 所以把简体中文放前面 —— 选择框标题就是中文，且默认选中中文。
Name: "zh"; MessagesFile: "lang\ChineseSimplified.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "runasadmin";  Description: "以管理员身份运行 / Run as administrator（推荐，全局热键 F6 / F7 需要管理员权限）"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; ★ onedir 布局：主程序打包产物是 ..\安装包\pivot\ 整个目录，
;      pivot.exe         主程序
;      _internal\        Python 运行时与全部依赖（必须一起装，缺了起不来）
;      apps\             外置功能模块
;   1.3.0 换了 AppId 与目录，所以不会和旧版的 MouseMacro 目录搅在一起。
Source: "{#ProdDir}\pivot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; ★ 功能模块作为**外置目录**装到 exe 同级：程序运行时优先加载这一份，
;   所以装完以后用户可以直接删 {app}\apps\ 里的 .py 来裁掉不想要的功能，
;   删掉的功能只是从底栏/主页卡片消失，其余照常。
;   本目录不存在时会回退到打包进 _internal\ 的那份。
Source: "README.md";              DestDir: "{app}"; Flags: ignoreversion
Source: "{#DocDir}\用户协议.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon\app.ico";          DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 「以管理员身份运行」兼容性标志(仅对当前用户生效)
Root: HKCU; Subkey: "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; \
    ValueType: string; ValueName: "{app}\{#MyAppExeName}"; ValueData: "RUNASADMIN"; \
    Flags: uninsdeletevalue; Tasks: runasadmin

[Run]
; ★ shellexec 不能去掉 —— 去掉就会在勾了「以管理员身份运行」任务时弹
;   「CreateProcess 失败；代码 740。请求的操作需要提升。」(实测报错)
;   原因链: [Registry] 写下的 RUNASADMIN 兼容性标志让这个 exe 变成"必须提权才能启动",
;           而不带 shellexec 的 [Run] 走的是 CreateProcess。带 postinstall 的条目
;           默认按 runasoriginaluser(非提权令牌)启动,非提权进程去启一个需提权的程序,
;           Windows 直接拒绝 -> ERROR_ELEVATION_REQUIRED(740)。
;   加上 shellexec 后改用 ShellExecuteEx,和资源管理器双击同一条路:
;   勾了任务 -> 弹 UAC 正常提权启动;没勾 -> 不弹 UAC 直接启动。
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent shellexec

; ============================================================
;  自定义逻辑
; ============================================================
[Code]
const
  AppCompatKey = 'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers';

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExePath: String;
begin
  if CurStep = ssPostInstall then
  begin
    ExePath := ExpandConstant('{app}\{#MyAppExeName}');
    if not WizardIsTaskSelected('runasadmin') then
    begin
      { 用户取消了「以管理员身份运行」—— 清掉可能残留的旧标志 }
      RegDeleteValue(HKCU, AppCompatKey, ExePath);
    end;
  end;
end;
