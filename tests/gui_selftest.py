"""Autoprueba de la interfaz gráfica con capturas de pantalla reales.

Uso:  python tests/gui_selftest.py <carpeta_capturas> <carpeta_salida>
Abre la aplicación con varios archivos de prueba, genera la vista previa del IFC,
convierte el lote a GLB y guarda capturas + registro en <carpeta_capturas>.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    shots, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    os.environ["U3DC_SELFTEST"] = shots
    from PySide6.QtCore import QSettings
    from u3dc.core.options import ConversionOptions
    s = QSettings("NEXOVAX3DConverter", "NEXOVAX3DConverter")
    s.clear()
    if len(sys.argv) > 3:
        s.setValue("language", sys.argv[3])
    # Variables opcionales: U3DC_SELFTEST_TARGET (formato), U3DC_SELFTEST_OPTS (JSON), U3DC_SELFTEST_FILES (rutas)
    extra = json.loads(os.environ.get("U3DC_SELFTEST_OPTS", "{}"))
    opts = ConversionOptions(target_format=os.environ.get("U3DC_SELFTEST_TARGET", "glb"), output_dir=out,
                             overwrite=True, **extra)
    s.setValue("options", json.dumps(opts.to_dict()))
    s.sync()
    from u3dc.ui.app import run
    a = os.path.join(ROOT, "test_assets")
    files = [os.path.join(a, n) for n in ("edificio_ifc4.ifc", "ensamblaje_mecanico.step", "mueble.obj",
                                          "cubo_ascii.fbx", "soporte_binario.stl", "escena_jerarquia.glb",
                                          "ensamblaje_mecanico.igs", "almacen_ifc2x3.ifc")]
    if os.environ.get("U3DC_SELFTEST_FILES"):
        files = os.environ["U3DC_SELFTEST_FILES"].split(os.pathsep)
    return run(files)


if __name__ == "__main__":
    sys.exit(main())
