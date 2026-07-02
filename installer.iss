[Setup]
AppName=Blicsa
AppVersion=1.0.0
DefaultDirName={autopf}\Blicsa
DefaultGroupName=Blicsa
OutputDir=dist
OutputBaseFilename=Blicsa_Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes

[Files]
Source: "dist\Blicsa-dir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Blicsa"; Filename: "{app}\Blicsa.exe"
Name: "{autodesktop}\Blicsa"; Filename: "{app}\Blicsa.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
