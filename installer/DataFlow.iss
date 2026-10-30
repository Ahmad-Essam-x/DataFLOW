; Antigravity DataFlow - per-user Windows installer (Inno Setup 6).
;
; Build:  ISCC.exe /DAppVersion=2.1.0 installer\DataFlow.iss     (run build_desktop.py first)
; Output: dist\installer\AntigravityDataFlow_Setup_<version>.exe
;
; Installs under %LOCALAPPDATA%\Programs - no administrator rights needed. User data (workflows, settings, logs)
; lives in %LOCALAPPDATA%\AntigravityDataFlow and is kept on uninstall unless the user asks to remove it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Antigravity DataFlow"
#define AppExe "AntigravityDataFlow.exe"
#define SourceDir "..\dist\AntigravityDataFlow"

[Setup]
; Fixed GUID: identifies this product so new installers upgrade the old one in place. Never change it.
AppId={{6F1D2B7A-3C54-4E8A-9B0E-5A1C7D2E9F43}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Siemens
DefaultDirName={localappdata}\Programs\AntigravityDataFlow
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
OutputDir=..\dist\installer
OutputBaseFilename=AntigravityDataFlow_Setup_{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
; Uncomment once a code-signing certificate is available:
; SignTool=signtool $f

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Name: "webview2"; Description: "Install Microsoft Edge WebView2 Runtime (required)"; Filename: "https://developer.microsoft.com/microsoft-edge/webview2/"; Flags: shellexec postinstall skipifsilent unchecked; Check: not WebView2Installed
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not WebView2Installed then
    MsgBox('Microsoft Edge WebView2 Runtime was not found.' + #13#10 + #13#10 +
           'It is included with current Windows 10/11 and Microsoft Edge. If DataFlow does not open after installation, ' +
           'install the runtime from https://developer.microsoft.com/microsoft-edge/webview2/ and start DataFlow again.',
           mbInformation, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\AntigravityDataFlow');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('Also delete your DataFlow data (saved workflows, settings and logs)?' + #13#10 + #13#10 + DataDir + #13#10 + #13#10 +
                'Choose No to keep it for a future installation.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
