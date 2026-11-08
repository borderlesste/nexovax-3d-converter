<p align="center"><img src="u3dc/ui/resources/logo.png" width="96" alt="NEXOVAX"></p>

# NEXOVAX 3D Converter

**⬇ [Descargar · Télécharger · Telechaje — Windows 10/11 (64 bits)](https://github.com/borderlesste/nexovax-3d-converter/releases/latest/download/NEXOVAX3DConverter-Setup.exe)** · [Web](https://borderlesste.github.io/nexovax-3d-converter/)

**ES** · Aplicación de escritorio para **Windows 10/11 (64 bits)** que convierte modelos 3D entre
**glTF, GLB, OBJ, FBX, STL, IFC, STEP/STP e IGES/IGS** — las 64 combinaciones — **sin conexión a Internet**.
Interfaz, manual e instalador en **español, francés y criollo haitiano**.

**FR** · Application de bureau pour **Windows 10/11 (64 bits)** qui convertit des modèles 3D entre 8 formats
(glTF, GLB, OBJ, FBX, STL, IFC, STEP, IGES) **sans connexion Internet**. Interface en espagnol, français et créole haïtien.

**HT** · Aplikasyon pou **Windows 10/11 (64 bit)** ki konvèti modèl 3D ant 8 fòma (glTF, GLB, OBJ, FBX, STL, IFC,
STEP, IGES) **san entènèt**. Entèfas an panyòl, fransè ak kreyòl ayisyen.

* Motores integrados: Open CASCADE (CAD), IfcOpenShell (BIM), ufbx / trimesh / Assimp (mallas), escritores propios
  glTF/GLB, OBJ, STL y FBX binario.
* Distingue conversiones **directas**, por **teselación**, **aproximadas** (B-Rep facetado) y **limitadas**, e informa de
  cada pérdida de información.
* Valida cada archivo generado (relectura, dimensiones, lector independiente) antes de guardarlo de forma atómica.
* Conversión por lotes en procesos aislados, cancelable; vista previa 3D; línea de comandos (`nexovax3d-cli --lang es|fr|ht`).

## Entregables
| Elemento | Ubicación |
|---|---|
| Instalador offline (ES/FR/HT) | `build/installer/NEXOVAX3DConverter-Setup.exe` |
| Aplicación (carpeta portable) | `build/dist/NEXOVAX3DConverter/` |
| Código fuente | `u3dc/` (traducciones en `u3dc/locales/`) |
| Manuales | `docs/Manual_de_usuario.html` · `docs/Manuel_utilisateur.html` · `docs/Manyel_itilizate.html` |
| Cómo publicar y escalar | `docs/Publicacion.md` |
| Página de descarga (GitHub Pages) | `docs/index.html` |
| Compilación automática (GitHub Actions) | `.github/workflows/release.yml` |
| Matriz de compatibilidad | `docs/Matriz_de_compatibilidad.md` |
| Resultados de pruebas | `docs/resultados_pruebas.txt`, `docs/resultados_matriz.md` |
| Arquitectura y viabilidad | `docs/Arquitectura_y_viabilidad.md` |
| Compilación y empaquetado | `docs/Compilacion_y_empaquetado.md` |
| Licencias de terceros | `docs/LICENCIAS_TERCEROS.html` |
| Limitaciones conocidas | `docs/Limitaciones.md` |

## Inicio rápido (desarrollo)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python tests\make_assets.py
.\.venv\Scripts\python -m u3dc                       # GUI
.\.venv\Scripts\python -m u3dc convert test_assets\ensamblaje_mecanico.step -t stl
.\.venv\Scripts\python -m pytest -q
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # ejecutables + instalador
```

## Estructura
```
u3dc/            código (core, models, engines/{mesh,cad,bim}, ui, cli, i18n, locales)
tests/           pruebas pytest, generador de archivos de ejemplo, matriz completa, autoprueba GUI
test_assets/     modelos de ejemplo de los 8 formatos
tools/           utilidades de traducción (extracción y verificación de textos)
packaging/       PyInstaller (.spec), Inno Setup (.iss + criollo), build.ps1, icono, licencias
docs/            documentación
```
El paquete Python conserva el nombre interno `u3dc`; el nombre público es NEXOVAX 3D Converter.
