# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera build/dist/NEXOVAX3DConverter/ con dos ejecutables que comparten bibliotecas:
#   NEXOVAX3DConverter.exe  (interfaz gráfica, sin consola)
#   nexovax3d-cli.exe              (línea de comandos)
import glob
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(SPEC_DIR)
SP = next(p for p in sys.path if p.endswith("site-packages") and os.path.isdir(os.path.join(p, "OCP")))

binaries = []
datas = []
hiddenimports = []

# --- Open CASCADE (OCP): extensión monolítica + DLL de OCCT y VTK en carpetas hermanas (delvewheel)
for libdir in ("cadquery_ocp.libs", "vtk.libs"):
    for dll in glob.glob(os.path.join(SP, libdir, "*.dll")):
        binaries.append((dll, libdir))
binaries += collect_dynamic_libs("OCP")
hiddenimports += ["OCP", "OCP.OCP"]

# --- IfcOpenShell: DLL, esquemas y submódulos cargados dinámicamente
binaries += collect_dynamic_libs("ifcopenshell")
datas += collect_data_files("ifcopenshell", excludes=["**/*.pyc", "**/test/**", "**/tests/**"])
for pkg in ("ifcopenshell.api", "ifcopenshell.util", "ifcopenshell.geom", "ifcopenshell.express"):
    hiddenimports += collect_submodules(pkg, filter=lambda n: ".test" not in n)
hiddenimports += ["ifcopenshell.validate", "ifcopenshell.ifcopenshell_wrapper"]
# ifcopenshell.express comprueba que express_parser.py exista como archivo; si no, intenta regenerarlo
# lanzando sys.executable (que en la app congelada es nuestro .exe). Se incluye el archivo fuente.
datas.append((os.path.join(SP, "ifcopenshell", "express", "express_parser.py"), "ifcopenshell/express"))

# --- mallas
datas += collect_data_files("trimesh")
binaries += collect_dynamic_libs("assimp_py") + collect_dynamic_libs("ufbx")
hiddenimports += ["fast_simplification"] + collect_submodules("fast_simplification")
binaries += collect_dynamic_libs("fast_simplification")
hiddenimports += ["ufbx", "ufbx._native", "assimp_py", "PIL.PngImagePlugin", "PIL.JpegImagePlugin",
                  "PIL.TgaImagePlugin", "PIL.BmpImagePlugin", "PIL.DdsImagePlugin"]

# --- visor VTK
hiddenimports += ["vtkmodules", "vtkmodules.all", "vtkmodules.qt.QVTKRenderWindowInteractor",
                  "vtkmodules.vtkRenderingOpenGL2", "vtkmodules.vtkInteractionStyle", "vtkmodules.util.numpy_support",
                  "vtkmodules.vtkRenderingAnnotation", "vtkmodules.vtkInteractionWidgets", "vtkmodules.vtkFiltersSources",
                  "vtkmodules.vtkFiltersCore", "vtkmodules.vtkRenderingCore", "vtkmodules.vtkCommonCore",
                  "vtkmodules.vtkCommonDataModel"]
hiddenimports += collect_submodules("u3dc")
datas.append((os.path.join(ROOT, "u3dc", "ui", "resources", "logo.png"), "u3dc/ui/resources"))

excludes = ["tkinter", "matplotlib", "IPython", "pandas", "scipy", "pytest", "PyQt5", "PyQt6",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
            "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.QtQuick", "PySide6.QtQml",
            "PySide6.QtQuickWidgets", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
            "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtBluetooth",
            "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtLocation", "PySide6.QtPositioning",
            "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
            "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtHelp", "PySide6.QtNetworkAuth",
            "vtkmodules.web", "vtkmodules.wx", "vtkmodules.tk", "vtkmodules.gtk"]

a = Analysis(
    [os.path.join(SPEC_DIR, "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)

# Eliminar módulos Qt pesados que no se usan aunque los arrastre alguna dependencia
DROP = ("Qt6WebEngine", "Qt6Quick", "Qt6Qml", "Qt63D", "Qt6Multimedia", "Qt6Pdf", "Qt6Designer", "Qt6Charts",
        "Qt6DataVisualization", "Qt6Graphs", "QtWebEngineProcess", "qtwebengine", "Qt6ShaderTools", "Qt6Location",
        "Qt6VirtualKeyboard", "Qt6Positioning")
a.binaries = [b for b in a.binaries if not any(k.lower() in b[0].lower() for k in DROP)]
def _keep_data(dest: str) -> bool:
    d = dest.lower().replace("\\", "/")
    if any(k.lower() in d for k in DROP):
        return False
    if d.startswith("pyside6/translations/") and not any(k in d for k in ("qtbase_es", "qt_es", "qtbase_fr", "qt_fr")):
        return False       # solo traducciones de Qt al español y francés
    return True


a.datas = [d for d in a.datas if _keep_data(d[0])]

pyz = PYZ(a.pure)
icon = os.path.join(SPEC_DIR, "app.ico")
version = os.path.join(SPEC_DIR, "version_info.txt")

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NEXOVAX3DConverter", console=False,
          icon=icon, version=version, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="nexovax3d-cli", console=True,
          icon=icon, version=version, upx=False)
coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="NEXOVAX3DConverter")
