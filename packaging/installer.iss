; Instalador de NEXOVAX 3D Converter (Inno Setup 6)
; Compilar con:  ISCC.exe packaging\installer.iss   (lo hace build.ps1)

#define AppName "NEXOVAX 3D Converter"
#define AppVersion "1.0.1"
#define AppExe "NEXOVAX3DConverter.exe"
#define DistDir "..\build\dist\NEXOVAX3DConverter"

[Setup]
AppId={{EDEA72AB-C63B-4585-9C62-CF9078B661C4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=NEXOVAX 3D Converter
DefaultDirName={autopf}\NEXOVAX 3D Converter
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Instalación por usuario sin administrador; el usuario puede elegir "para todos" (requiere elevación)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\build\installer
OutputBaseFilename=NEXOVAX3DConverter-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
WizardStyle=modern
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
CloseApplications=yes
VersionInfoVersion=1.0.1.0
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "ht"; MessagesFile: "HaitianCreole.isl"

[CustomMessages]
es.Shortcuts=Accesos directos:
fr.Shortcuts=Raccourcis :
ht.Shortcuts=Rakousi:
es.DesktopIcon=Crear un acceso directo en el escritorio
fr.DesktopIcon=Créer un raccourci sur le bureau
ht.DesktopIcon=Kreye yon rakousi sou biwo a
es.WinIntegration=Integración con Windows:
fr.WinIntegration=Intégration à Windows :
ht.WinIntegration=Entegrasyon ak Windows:
es.OpenWith=Añadir «{#AppName}» al menú «Abrir con» de los modelos 3D
fr.OpenWith=Ajouter « {#AppName} » au menu « Ouvrir avec » des modèles 3D
ht.OpenWith=Mete «{#AppName}» nan meni «Louvri avèk» modèl 3D yo
es.ManualName=Manual de usuario
fr.ManualName=Manuel d'utilisation
ht.ManualName=Manyèl itilizatè
es.ManualFile=Manual_de_usuario.html
fr.ManualFile=Manuel_utilisateur.html
ht.ManualFile=Manyel_itilizate.html
es.CliName=Consola de conversión (nexovax3d-cli)
fr.CliName=Console de conversion (nexovax3d-cli)
ht.CliName=Konsòl konvèsyon (nexovax3d-cli)
es.UninstallName=Desinstalar {#AppName}
fr.UninstallName=Désinstaller {#AppName}
ht.UninstallName=Dezenstale {#AppName}
es.RunApp=Iniciar {#AppName}
fr.RunApp=Lancer {#AppName}
ht.RunApp=Lanse {#AppName}

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:Shortcuts}"
Name: "openwith"; Description: "{cm:OpenWith}"; GroupDescription: "{cm:WinIntegration}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\Manual_de_usuario.html"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\Manuel_utilisateur.html"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\Manyel_itilizate.html"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\LICENCIAS_TERCEROS.html"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\Matriz_de_compatibilidad.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\Limitaciones.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{cm:ManualName}"; Filename: "{app}\docs\{cm:ManualFile}"
Name: "{group}\{cm:CliName}"; Filename: "{cmd}"; Parameters: "/k ""{app}\nexovax3d-cli.exe"" --lang {language} --help"; WorkingDir: "{userdocs}"
Name: "{group}\{cm:UninstallName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
; preferencias de la aplicación (QSettings): se eliminan al desinstalar
Root: HKCU; Subkey: "Software\NEXOVAX3DConverter"; Flags: uninsdeletekey
; idioma inicial de la aplicación = idioma elegido en el instalador (no sobrescribe una elección posterior)
Root: HKCU; Subkey: "Software\NEXOVAX3DConverter\NEXOVAX3DConverter"; ValueType: string; ValueName: "language"; ValueData: "{language}"; Flags: createvalueifdoesntexist
; "Abrir con" (opcional): solo registra la aplicación como candidata, no cambia los programas predeterminados
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".gltf"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".glb"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".obj"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".fbx"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".stl"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".ifc"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".step"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".stp"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".igs"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".iges"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.step\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ifc\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.stl\OpenWithList\{#AppExe}"; ValueType: none; Flags: uninsdeletekey; Tasks: openwith

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:RunApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; restos que la aplicación pueda haber creado dentro de su carpeta (cachés de Python)
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
Type: dirifempty; Name: "{app}"
