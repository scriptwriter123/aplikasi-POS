#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

#ifndef SourceDir
  #define SourceDir "..\dist\POS"
#endif

#ifndef OutputDir
  #define OutputDir "..\build\installer"
#endif

[Setup]
AppId={{C165BFD9-1C37-4255-BF6C-882EDE4C4E75}
AppName=POS Retail
AppVersion={#AppVersion}
AppPublisher=POS Retail
DefaultDirName={localappdata}\Programs\POS Retail
DefaultGroupName=POS Retail
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir="{#OutputDir}"
OutputBaseFilename=AnjayRetailSoft
UninstallDisplayIcon={app}\POS.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Shortcut tambahan:"

[Dirs]
Name: "{localappdata}\POSApp\data"; Flags: uninsneveruninstall

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\POS Retail"; Filename: "{app}\POS.exe"; WorkingDir: "{app}"
Name: "{group}\Folder Data POS"; Filename: "{localappdata}\POSApp\data"
Name: "{autodesktop}\POS Retail"; Filename: "{app}\POS.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autodesktop}\Folder Data POS"; Filename: "{localappdata}\POSApp\data"

[Run]
Filename: "{app}\POS.exe"; Description: "Jalankan POS Retail"; Flags: postinstall nowait skipifsilent
