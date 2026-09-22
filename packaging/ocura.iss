; Ocura installer, for Inno Setup 6.
;
; Built through scripts/build_release.py --installer, which packages the
; application first and then passes the version in:
;
;     ISCC.exe /DAppVersion=<the version> packaging\ocura.iss
;
; The version is never written here. It has one home, src/ocura/__init__.py,
; and everything that needs it reads from there — see that file.
;
; Per-user, not machine-wide. Ocura's "start with Windows" is a value under
; HKEY_CURRENT_USER, because arranging your own start-up should not need an
; administrator; installing under {localappdata}\Programs keeps the whole
; product consistent with that, asks for no elevation at all, and uninstalls
; for exactly the person who installed it. The cost is that a second user on
; the same machine installs their own copy, which for a single-user desktop
; utility is the right trade.

#ifndef AppVersion
  #error Compile this through scripts/build_release.py, which supplies /DAppVersion
#endif

#define AppName "Ocura"
#define AppPublisher "Abdulrahim Ramadan"
#define AppURL "https://github.com/abdulrahim-ramadan/ocura"
#define AppExe "Ocura.exe"
#define SourceFolder "..\dist\Ocura"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
; Never change this. It is what Windows uses to recognise an existing
; installation and upgrade it in place instead of stacking a second one.
AppId={{8E4C2F21-9A3D-4E57-B0C6-1D9F7A5E3B42}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppCopyright=Copyright (c) 2026 {#AppPublisher}

DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=..\LICENSE

OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-Setup
SetupIconFile=..\src\ocura\ui\assets\ocura.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes

; Windows 10 and later. The context detection is built on APIs that are older
; than that, but nothing earlier has been run against.
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Ocura lives in the tray, so an upgrade will usually find it running and
; holding its own folder open. The restart manager asks to close it rather
; than failing halfway through with a file-in-use error. It is not restarted
; afterwards: the [Run] entry below does that, and only if the user asks.
CloseApplications=yes
RestartApplications=no

[Languages]
; English only, and deliberately. Inno ships no Arabic message file, so a
; localised installer would cover two of Ocura's three languages and leave the
; right-to-left one — the one where a wrong-way-round wizard would be most
; jarring — in English anyway. The installer is one screen for twenty seconds;
; the application is where the language matters, and it has all three.
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; The first page says what the warning was, before the user has to decide what
; to think about it. Somebody who has been told what "unknown publisher" means
; is not alarmed by it; somebody who has not been told is right to be.
WelcomeLabel2=This will install [name/ver] on your computer.%n%nOcura is not code-signed, so Windows may have shown a blue "Windows protected your PC" screen before this window appeared, and may show it once more the first time Ocura runs. That warning means only that the publisher has not paid for a certificate — it is not a report about the file. The source is public at {#AppURL} and you can build it yourself.%n%nOcura keeps everything on this machine: no account, no cloud, no telemetry.

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
; Unchecked, and Ocura asks the same question on its first run. The two agree
; because both read the registry value rather than a setting of their own: tick
; it here and the first-run screen opens on "Yes"; answer "No" there and the
; value goes away again.
Name: "autostart"; Description: "Start {#AppName} when I &sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; The whole --onedir folder. PySide6 ships Qt under the LGPL v3, which requires
; that the recipient can replace the Qt libraries with their own build, so the
; DLLs stay as separate files rather than being packed into one executable.
Source: "{#SourceFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; The same key, the same value name and the same quoting Ocura itself writes,
; so its Settings checkbox reads back exactly what the installer did. Anything
; else would leave the application disagreeing with the machine about whether
; it starts at sign-in.
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "{#AppName}"; \
    ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[Code]
var
  RemoveHistory: Boolean;

function HistoryFolder(): String;
begin
  // %LOCALAPPDATA%\Ocura — where the database and the settings live. It is
  // deliberately not inside the installation folder: it is the user's data,
  // and data deleted by uninstalling the program that happened to write it is
  // data nobody can trust.
  //
  // Comments in this section are // and never the Pascal { }, because a brace
  // comment ends at the first closing brace — and every path worth writing in
  // a comment here contains one. The first version of this function was one
  // long "Identifier expected" because of it.
  Result := ExpandConstant('{localappdata}\{#AppName}');
end;

function InitializeUninstall(): Boolean;
var
  Form: TSetupForm;
  Question: TNewStaticText;
  Detail: TNewStaticText;
  Keep: TNewCheckBox;
  RemoveButton, CancelButton: TNewButton;
begin
  RemoveHistory := False;
  if not DirExists(HistoryFolder()) then
  begin
    Result := True;
    Exit;
  end;

  // A silent uninstall asks nothing and therefore deletes nothing: a modal
  // dialog in a deployment script is a hung machine, and silence is not
  // consent to throw away someone's history. An administrator who does want
  // it gone says so explicitly:
  //
  //     unins000.exe /VERYSILENT /DELETEDATA=1
  if UninstallSilent() then
  begin
    RemoveHistory := ExpandConstant('{param:DELETEDATA|0}') = '1';
    Result := True;
    Exit;
  end;

  // A checkbox rather than a Yes/No box, because the two answers are not
  // equally weighted: keeping the history is the default and the safe one,
  // and deleting it is the thing the user reaches for deliberately.
  //
  // The form is given its size here rather than assigned one afterwards:
  // CreateCustomForm takes the client size and whether it may grow, and the
  // last argument is False because nothing on it sizes vertically.
  Form := CreateCustomForm(ScaleX(430), ScaleY(180), False, False);
  try
    Form.Caption := 'Uninstall {#AppName}';

    Question := TNewStaticText.Create(Form);
    Question.Parent := Form;
    Question.Left := ScaleX(16);
    Question.Top := ScaleY(16);
    Question.Width := Form.ClientWidth - ScaleX(32);
    Question.AutoSize := False;
    Question.Height := ScaleY(34);
    Question.WordWrap := True;
    Question.Caption := 'Ocura is about to be removed. Your history and settings will be left where they are.';

    Detail := TNewStaticText.Create(Form);
    Detail.Parent := Form;
    Detail.Left := ScaleX(16);
    Detail.Top := ScaleY(58);
    Detail.Width := Form.ClientWidth - ScaleX(32);
    Detail.AutoSize := False;
    Detail.Height := ScaleY(30);
    Detail.WordWrap := True;
    Detail.Caption := HistoryFolder();

    Keep := TNewCheckBox.Create(Form);
    Keep.Parent := Form;
    Keep.Left := ScaleX(16);
    Keep.Top := ScaleY(96);
    Keep.Width := Form.ClientWidth - ScaleX(32);
    Keep.Height := ScaleY(17);
    Keep.Caption := 'Also delete my history and settings';
    Keep.Checked := False;

    RemoveButton := TNewButton.Create(Form);
    RemoveButton.Parent := Form;
    RemoveButton.Width := ScaleX(90);
    RemoveButton.Height := ScaleY(25);
    RemoveButton.Left := Form.ClientWidth - ScaleX(196);
    RemoveButton.Top := Form.ClientHeight - ScaleY(41);
    RemoveButton.Caption := 'Uninstall';
    RemoveButton.ModalResult := mrOk;
    RemoveButton.Default := True;

    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Width := ScaleX(90);
    CancelButton.Height := ScaleY(25);
    CancelButton.Left := Form.ClientWidth - ScaleX(100);
    CancelButton.Top := Form.ClientHeight - ScaleY(41);
    CancelButton.Caption := 'Cancel';
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;

    Result := Form.ShowModal() = mrOk;
    RemoveHistory := Result and Keep.Checked;
  finally
    Form.Free();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // The startup entry goes whether the installer wrote it or Ocura did.
    // uninsdeletevalue only covers the first case, and a Run value left
    // pointing at a deleted executable is a sign-in error every morning for
    // somebody who thinks they have removed the program. Only this value, and
    // only when it points into the folder being uninstalled.
    if RegQueryStringValue(HKEY_CURRENT_USER, '{#RunKey}', '{#AppName}', Command) then
      if Pos(LowerCase(ExpandConstant('{app}')), LowerCase(Command)) > 0 then
        RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', '{#AppName}');
  end;

  if (CurUninstallStep = usPostUninstall) and RemoveHistory then
    DelTree(HistoryFolder(), True, True, True);
end;
