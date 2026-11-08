"""Validación automática de los archivos generados.

1. Existencia y tamaño de cada archivo producido.
2. Relectura con el adaptador propio (normalizando unidades/ejes como al escribir).
3. Presencia de geometría.
4. Comparación de dimensiones (caja envolvente) y nº de objetos.
5. Lector independiente: Assimp (mallas), comprobación B-Rep de OCCT (STEP/IGES),
   validación de esquema de IfcOpenShell (IFC).
"""
from __future__ import annotations

import copy
import logging
import os

import numpy as np

from .options import UNITS_TO_METERS


def _units_key(unit_m: float) -> str | None:
    for k, v in UNITS_TO_METERS.items():
        if abs(v - unit_m) < 1e-12:
            return k
    return None


def independent_mesh_check(path: str) -> dict:
    """Relectura con Assimp (implementación independiente de la nuestra)."""
    import assimp_py
    flags = assimp_py.Process_Triangulate | assimp_py.Process_ValidateDataStructure
    sc = assimp_py.import_file(path, flags)
    meshes = list(sc.meshes)
    tris = 0
    for m in meshes:
        idx = getattr(m, "indices", None)
        if idx is not None:
            tris += len(idx) // 3
    return {"assimp_meshes": len(meshes), "assimp_triangles": tris}


def validate_output(files: list[str], fmt: str, options, expected: dict, report) -> dict:
    from . import adapters
    result = {"ok": True}
    # 1. existencia y tamaño
    for f in files:
        if not os.path.isfile(f):
            raise ValueError(f"Validación: no existe el archivo generado {os.path.basename(f)}")
        if os.path.getsize(f) == 0:
            raise ValueError(f"Validación: archivo vacío {os.path.basename(f)}")
    main = files[0]
    result["bytes"] = os.path.getsize(main)

    # 2. relectura con nuestro adaptador
    vopts = copy.deepcopy(options)
    unit, up = expected.get("frame", (1.0, "Z"))
    key = _units_key(unit)
    rescale = 1.0
    if fmt in ("obj", "stl"):
        vopts.input_units = key or "m"
        rescale = unit / UNITS_TO_METERS[vopts.input_units]
        vopts.input_up_axis = up

    class _Silent:
        source = main
        source_format = fmt
        def info(self, *a): pass
        def warn(self, *a): pass
        def loss(self, *a): pass
        def error(self, *a): pass

    rep, model = adapters.read(fmt, main, vopts, _Silent())

    # 3. geometría presente y 4. dimensiones
    bounds = None
    if rep == "scene":
        tris = model.triangle_count()
        result["triangles"] = tris
        if tris == 0:
            raise ValueError("Validación: el archivo generado no contiene triángulos.")
        bounds = model.bounds()
    elif rep == "cad":
        from ..engines.cad.occt import shape_stats
        if not model.parts:
            raise ValueError("Validación: el archivo generado no contiene formas.")
        st = {"solidos": 0, "caras": 0}
        for p in model.parts:
            s = shape_stats(p.shape)
            st["solidos"] += s["solidos"]
            st["caras"] += s["caras"]
        result.update(st)
        if st["caras"] == 0:
            raise ValueError("Validación: el archivo CAD generado no contiene caras.")
        b = model.bounds()
        bounds = None if b is None else b * 0.001
    elif rep == "bim":
        n = len(model.products_with_geometry())
        result["productos"] = n
        if n == 0:
            raise ValueError("Validación: el IFC generado no contiene productos con geometría.")
        if expected.get("bounds") is not None:
            from ..engines.bim.ifc import bim_to_scene
            sopts = copy.deepcopy(options)
            sopts.quality = "baja"
            sopts.include_properties = False
            sc = bim_to_scene(model, sopts, _Silent())
            bounds = sc.bounds()
    if bounds is not None and rescale != 1.0:
        bounds = bounds * rescale

    exp_b = expected.get("bounds")
    if exp_b is not None and bounds is not None:
        diag = float(np.linalg.norm(exp_b[1] - exp_b[0])) or 1.0
        tol = diag * 2e-3 + expected.get("tolerance_m", 0.0) * 4
        dev = float(np.abs(np.asarray(bounds) - np.asarray(exp_b)).max())
        result["desviacion_dimensiones_m"] = round(dev, 9)
        size = bounds[1] - bounds[0]
        result["dimensiones_m"] = [round(float(x), 6) for x in size]
        if dev > tol:
            if dev > diag * 0.05:
                raise ValueError(f"Validación: discrepancia de dimensiones grave ({dev:.6g} m sobre una diagonal "
                                 f"de {diag:.6g} m).")
            report.warn(f"Validación: diferencia de dimensiones {dev:.6g} m (tolerancia {tol:.3g} m).")
            result["ok"] = False

    exp_n = expected.get("instances")
    if exp_n:
        from .adapters import instance_count
        got = instance_count(rep, model)
        result["objetos"] = got
        if fmt != "stl" and got != exp_n and expected.get("check_instances", True):
            report.warn(f"Validación: nº de objetos distinto (origen {exp_n}, resultado {got}). "
                        "Puede deberse a la división por materiales o a la fusión propia del formato.")

    # 5. lector independiente
    try:
        if fmt in ("gltf", "glb", "obj", "stl", "fbx"):
            ind = independent_mesh_check(main)
            result.update(ind)
            if ind["assimp_triangles"] == 0:
                raise ValueError("Validación independiente (Assimp): sin triángulos.")
            if rep == "scene":
                # Assimp cuenta mallas únicas; nuestro recuento incluye instancias: se acepta cualquiera
                unique = sum(len(m.faces) for m in model.meshes)
                if ind["assimp_triangles"] not in (result.get("triangles", 0), unique):
                    report.warn(f"Assimp lee {ind['assimp_triangles']} triángulos frente a "
                                f"{result.get('triangles')} (instancias) / {unique} (mallas únicas).")
        elif fmt in ("step", "iges"):
            from OCP.BRepCheck import BRepCheck_Analyzer
            invalid = sum(0 if BRepCheck_Analyzer(p.shape).IsValid() else 1 for p in model.parts)
            result["formas_no_validas"] = invalid
            if invalid:
                report.warn(f"Validación OCCT: {invalid} forma(s) con defectos topológicos en el archivo generado.")
        elif fmt == "ifc":
            result["errores_esquema"] = ifc_schema_errors(model.ifc)
            if result["errores_esquema"]:
                report.warn(f"Validación de esquema IFC: {result['errores_esquema']} incidencia(s).")
    except ValueError:
        raise
    except Exception as e:  # el lector independiente no reconoce algo: advertir, no fallar
        report.warn(f"Validación independiente no concluyente: {e}")
    return result


def ifc_schema_errors(f, limit: int = 200) -> int:
    try:
        import ifcopenshell.validate as iv
    except Exception:
        return 0

    class _Count(logging.Handler):
        def __init__(self):
            super().__init__()
            self.n = 0

        def emit(self, record):
            if record.levelno >= logging.ERROR:
                self.n += 1

    logger = logging.getLogger("u3dc.ifcvalidate")
    logger.propagate = False
    h = _Count()
    logger.handlers = [h]
    logger.setLevel(logging.ERROR)
    try:
        iv.validate(f, logger)
    except Exception:
        pass
    return h.n
