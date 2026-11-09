# Compilación, pruebas y empaquetado

## Requisitos de la máquina de compilación
* Windows 10/11 x64.
* Python 3.12 x64 (python.org).
* Inno Setup 6 (`winget install JRSoftware.InnoSetup --scope user`).
* Conexión a Internet **solo** para instalar las dependencias de Python la primera vez. La aplicación y el instalador
  resultantes funcionan sin conexión.

## Compilación completa (un comando)
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```
Pasos que ejecuta:
1. Crea `.venv` e instala `requirements.txt` + `requirements-dev.txt` (versiones fijadas y verificadas).
2. Genera los archivos de prueba (`tests/make_assets.py`) y ejecuta toda la batería `pytest`.
3. Regenera `docs/LICENCIAS_TERCEROS.html` (desde los metadatos reales), `docs/Matriz_de_compatibilidad.md` y el icono.
4. PyInstaller (`packaging/u3dc.spec`) → `build/dist/NEXOVAX3DConverter/` con
   `NEXOVAX3DConverter.exe` (GUI) y `nexovax3d-cli.exe` (consola) compartiendo `_internal/`.
5. Prueba de humo del ejecutable congelado (3 conversiones reales).
6. Inno Setup (`packaging/installer.iss`) → `build/installer/NEXOVAX3DConverter-Setup.exe`.

## Desarrollo
```powershell
.\.venv\Scripts\python -m u3dc                     # interfaz gráfica
.\.venv\Scripts\python -m u3dc convert a.step -t glb
.\.venv\Scripts\python -m pytest -q                # 146 pruebas
.\.venv\Scripts\python tests\run_matrix.py          # 88 conversiones → docs/resultados_matriz.md
.\.venv\Scripts\python tests\gui_selftest.py <capturas> <salida>   # autoprueba de la GUI con capturas
```

## Detalles del empaquetado
* **OCP** es una extensión monolítica que carga las DLL de OCCT (`cadquery_ocp.libs`) y de VTK (`vtk.libs`) desde
  carpetas hermanas; el `.spec` las copia con esos mismos nombres para que funcione el `os.add_dll_directory` del paquete.
* **IfcOpenShell** incluye su propia compilación de OCCT; no hay conflicto porque las DLL de OCP llevan nombres
  únicos (delvewheel).
* `ifcopenshell/express/express_parser.py` se incluye como archivo: si falta, IfcOpenShell intenta regenerarlo
  ejecutando `sys.executable`, que en la app congelada es el propio `.exe`. Además `launcher.py` ignora cualquier
  intento de usar el ejecutable como intérprete (`*.py`, `-m`, `-c`).
* Se excluyen módulos Qt no usados (WebEngine, Quick/QML, 3D, Multimedia, PDF…) y traducciones salvo español.
* Las conversiones usan `multiprocessing` (spawn): `freeze_support()` en `launcher.py` es imprescindible.

## Instalador
* Instalación por usuario sin permisos de administrador (`%LOCALAPPDATA%\Programs\NEXOVAX 3D Converter`);
  el diálogo permite instalar para todos los usuarios (con elevación).
* Acceso directo en escritorio (tarea marcada por defecto) y entradas en el menú Inicio: aplicación, manual,
  consola `nexovax3d-cli` y desinstalador.
* Integración opcional «Abrir con» para las 10 extensiones (no cambia programas predeterminados).
* Desinstalación completa desde *Configuración → Aplicaciones* o el menú Inicio.
* El instalador no descarga nada: todo el contenido está dentro del `.exe`.

## Verificación realizada
| Prueba (2026-11-08, Windows 11 Pro 26200) | Resultado |
|---|---|
| `pytest` (detección, rutas, 14 conversiones obligatorias, 64 combinaciones, robustez, CLI, 1 M de triángulos) | **153/153**, incluidas las pruebas de traducción FR/HT (`docs/resultados_pruebas.txt`) |
| Matriz de 88 conversiones en procesos aislados | **88/88**, desviación máx. de dimensiones < 0,05 µm (`docs/resultados_matriz.md`) |
| Autoprueba de la GUI (fuente, congelada e instalada) con capturas | 8/8, 5/5 y 6/6 lotes correctos (`docs/capturas/`) |
| Instalador `/VERYSILENT /CURRENTUSER` | instalado en 43 s, 766 MB; acceso directo de escritorio, menú Inicio y entrada de desinstalación creados |
| App instalada: 13 archivos × 8 formatos destino (CLI) | **104/104** correctas; ningún proceso de la app abrió conexiones TCP/UDP durante las conversiones |
| Desinstalación silenciosa | carpeta, accesos directos, menú Inicio y clave de desinstalación eliminados |
| Instalador trilingüe ES/FR/HT (instalado con `/LANG=ht`) | 140,8 MB, SHA-256 `0253AE59…F55F103` (versión publicada en GitHub); accesos directos en criollo; la app arranca en el idioma elegido en el instalador; desinstalación limpia, incluidas las preferencias |

## Verificación pendiente (requiere otra máquina)
* Instalar en un **Windows 10/11 limpio** (sin Python) y con **la red desactivada**, y ejecutar:
  `nexovax3d-cli.exe convert <carpeta test_assets> -t glb` y lo mismo con `-t step`, `-t ifc`.
  En el equipo de desarrollo no se pudo desconectar la red ni disponer de una máquina limpia.
