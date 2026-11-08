# Compila NEXOVAX 3D Converter y genera el instalador offline.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-SkipTests]
# Requisitos (solo en la máquina de compilación): Python 3.12 x64 e Inno Setup 6.
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 1. Entorno virtual con dependencias fijadas
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
    .\.venv\Scripts\python -m pip install --upgrade pip
}
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt

# 2. Recursos de prueba, pruebas y documentación generada
.\.venv\Scripts\python -X utf8 tests\make_assets.py
if (-not $SkipTests) {
    .\.venv\Scripts\python -X utf8 -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Las pruebas automáticas han fallado" }
}
.\.venv\Scripts\python -X utf8 packaging\gen_licenses.py
.\.venv\Scripts\python -X utf8 packaging\gen_matrix_doc.py
.\.venv\Scripts\python -X utf8 packaging\make_icon.py

# 3. Ejecutables (PyInstaller, carpeta única con GUI + CLI)
.\.venv\Scripts\python -m PyInstaller packaging\u3dc.spec --noconfirm --clean --distpath build\dist --workpath build\work --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ha fallado" }
New-Item -ItemType Directory -Force build\dist\NEXOVAX3DConverter\docs | Out-Null
Copy-Item docs\Manual_de_usuario.html, docs\Manuel_utilisateur.html, docs\Manyel_itilizate.html, docs\LICENCIAS_TERCEROS.html, docs\Matriz_de_compatibilidad.md, docs\Limitaciones.md build\dist\NEXOVAX3DConverter\docs -Force

# 4. Prueba de humo del ejecutable congelado
$smoke = Join-Path $env:TEMP "u3dc_smoke"
& build\dist\NEXOVAX3DConverter\nexovax3d-cli.exe convert test_assets\ensamblaje_mecanico.step test_assets\edificio_ifc4.ifc test_assets\mueble.obj -t glb -o $smoke --overwrite
if ($LASTEXITCODE -ne 0) { throw "La prueba de humo del ejecutable ha fallado" }

# 5. Instalador
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No se encontró Inno Setup 6 (ISCC.exe)" }
& $iscc packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup ha fallado" }
Get-Item build\installer\NEXOVAX3DConverter-Setup.exe | Select-Object FullName, @{n="MB";e={[math]::Round($_.Length/1MB,1)}}
