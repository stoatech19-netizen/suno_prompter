; Inno Setup script for Suno Prompt Generator.
;
; Build with (from the repo root):
;   "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" /DSourceDir="<path to a clean git clone>" installer\suno_installer.iss
;
; SourceDir must be a *fresh* `git clone` of this repo (not the working copy),
; so the bundled payload has a clean .git pointed at origin/main and none of
; the working copy's .venv/uploads/build clutter - run.bat's own update
; check (`git fetch` + `git pull --ff-only`) then keeps it current after
; install without this installer ever needing to be rebuilt for routine
; updates.
#ifndef SourceDir
  #error "Pass /DSourceDir=<path to a clean git clone of the repo> on the ISCC command line"
#endif

#define MyAppName "Suno Prompt Generator"
#define MyAppVersion "1.0"
#define MyAppPublisher "stoatech"

[Setup]
AppId={{94A77043-4CA0-4875-B22D-20FE2736A51A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SunoPromptGenerator
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\
OutputBaseFilename=SunoPromptGenerator_Setup
SetupIconFile={#SourceDir}\static\app.ico
UninstallDisplayIcon={app}\static\app.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: ".venv,uploads\*"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#SourceDir}\uploads\.gitkeep"; DestDir: "{app}\uploads"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; IconFilename: "{app}\static\app.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; IconFilename: "{app}\static\app.ico"; Tasks: desktopicon

[Run]
Filename: "{cmd}"; Parameters: "/c setup.bat < nul"; WorkingDir: "{app}"; StatusMsg: "Python 환경을 설치하는 중입니다 (몇 분 정도 걸릴 수 있습니다)..."; Flags: waituntilterminated
Filename: "{app}\run.bat"; Description: "지금 바로 실행하기"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent shellexec

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
