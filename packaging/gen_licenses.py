"""Genera docs/LICENCIAS_TERCEROS.html con la licencia de cada componente distribuido.

Lee los metadatos y los archivos de licencia de los paquetes instalados (importlib.metadata),
de modo que la relación refleja exactamente lo que se empaqueta.
"""
import html
import importlib.metadata as md
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (distribución, componente, licencia declarada, notas)
COMPONENTS = [
    ("PySide6-Essentials", "Qt for Python (PySide6) y Qt 6", "LGPL-3.0-only", "Enlazado dinámicamente (DLL separadas, reemplazables)."),
    ("shiboken6", "Shiboken6", "LGPL-3.0-only", ""),
    ("cadquery-ocp", "OCP (bindings de Open CASCADE)", "Apache-2.0", "Incluye las DLL de Open CASCADE Technology (OCCT), licencia LGPL-2.1 con excepción adicional de Open CASCADE."),
    ("vtk", "VTK — Visualization Toolkit", "BSD-3-Clause", "Visor 3D; también requerido por OCP."),
    ("ifcopenshell", "IfcOpenShell", "LGPL-3.0-or-later", "Motor BIM/IFC; incluye su propia compilación de OCCT (LGPL-2.1)."),
    ("numpy", "NumPy", "BSD-3-Clause", ""),
    ("trimesh", "trimesh", "MIT", "Lectura glTF/GLB."),
    ("ufbx", "ufbx (binding Python)", "MIT / dominio público (biblioteca ufbx)", "Lectura FBX y OBJ. El paquete PyPI 0.0.5 no declara licencia en sus metadatos; la biblioteca ufbx (github.com/ufbx/ufbx) es MIT o dominio público. Verificar el binding antes de redistribuir comercialmente."),
    ("assimp-py", "assimp-py + Open Asset Import Library", "MIT (binding) / BSD-3-Clause (assimp)", "Validación independiente de mallas."),
    ("pillow", "Pillow", "MIT-CMU (HPND)", "Texturas."),
    ("shapely", "Shapely", "BSD-3-Clause", "Dependencia de IfcOpenShell."),
    ("lark", "Lark", "MIT", "Dependencia de IfcOpenShell."),
    ("isodate", "isodate", "BSD-3-Clause", "Dependencia de IfcOpenShell."),
    ("python-dateutil", "python-dateutil", "Apache-2.0 / BSD-3-Clause", "Dependencia de IfcOpenShell."),
    ("typing_extensions", "typing_extensions", "PSF-2.0", ""),
    ("packaging", "packaging", "Apache-2.0 / BSD-2-Clause", ""),
    ("pyinstaller", "PyInstaller (cargador de arranque)", "GPL-2.0 con excepción de cargador", "La excepción permite distribuir aplicaciones bajo cualquier licencia."),
]


def license_text(dist: str) -> str:
    try:
        d = md.distribution(dist)
    except md.PackageNotFoundError:
        return ""
    texts = []
    for f in d.files or []:
        name = os.path.basename(str(f)).upper()
        if name.startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE")) and "dist-info" in str(f).lower() or \
                (name.startswith(("LICENSE", "COPYING")) and str(f).count("/") <= 2):
            try:
                t = f.read_text(encoding="utf-8", errors="replace")
                if t and t not in texts:
                    texts.append(t)
            except Exception:
                pass
    return "\n\n".join(texts)[:60000]


def main():
    rows, details = [], []
    for dist, comp, lic, note in COMPONENTS:
        try:
            ver = md.version(dist)
        except md.PackageNotFoundError:
            continue
        rows.append(f"<tr><td>{html.escape(comp)}</td><td>{ver}</td><td>{html.escape(lic)}</td><td>{html.escape(note)}</td></tr>")
        txt = license_text(dist)
        if txt:
            details.append(f"<h3>{html.escape(comp)} {ver}</h3><pre>{html.escape(txt)}</pre>")
    py = sys.version.split()[0]
    page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Licencias de terceros</title>
<style>body{{font-family:Segoe UI,Arial;max-width:1100px;margin:24px auto;padding:0 16px;color:#1d2733}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d9e0ea;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f6fa}}pre{{white-space:pre-wrap;background:#f7f9fc;border:1px solid #e3e9f1;padding:10px;font-size:12px;max-height:420px;overflow:auto}}</style></head><body>
<h1>Licencias de componentes de terceros</h1>
<p>NEXOVAX 3D Converter incluye los siguientes componentes. Todos se distribuyen como bibliotecas
independientes (DLL / módulos de extensión) enlazadas dinámicamente; pueden sustituirse por versiones
modificadas reemplazando los archivos correspondientes en la carpeta <code>_internal</code> de la instalación,
tal como exigen las licencias LGPL.</p>
<table><tr><th>Componente</th><th>Versión</th><th>Licencia</th><th>Notas</th></tr>
<tr><td>Python (intérprete)</td><td>{py}</td><td>PSF-2.0</td><td>Incluido por PyInstaller.</td></tr>
{''.join(rows)}
<tr><td>Open CASCADE Technology</td><td>incluido en OCP / IfcOpenShell</td><td>LGPL-2.1 + excepción Open CASCADE</td><td>https://dev.opencascade.org</td></tr>
<tr><td>Inno Setup (solo instalador)</td><td>6.7</td><td>Licencia Inno Setup (gratuita)</td><td>Usado para generar el instalador; no forma parte de la aplicación.</td></tr>
</table>
<h2>Código fuente de componentes LGPL</h2>
<p>Qt / PySide6: https://code.qt.io · IfcOpenShell: https://github.com/IfcOpenShell/IfcOpenShell ·
Open CASCADE: https://github.com/Open-Cascade-SAS/OCCT · OCP: https://github.com/CadQuery/OCP.
Las versiones exactas utilizadas figuran en la tabla anterior.</p>
<h2>Componentes evaluados y no incluidos</h2>
<p><b>Blender</b> (GPL-2.0-or-later) se evaluó como motor de mallas en segundo plano. Se descartó porque añade
≈1 GB a la instalación y su función (FBX) se cubre con ufbx (lectura, MIT) + un escritor FBX binario propio,
validado con dos lectores independientes (ufbx y Assimp). No se distribuye Blender.</p>
<h2>Textos de licencia</h2>
{''.join(details)}
</body></html>"""
    out = os.path.join(ROOT, "docs", "LICENCIAS_TERCEROS.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("Generado", out, f"({len(rows)} componentes)")


if __name__ == "__main__":
    main()
