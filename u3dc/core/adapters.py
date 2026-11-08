"""Adaptadores: importación, transformación entre representaciones y exportación.

Cada importador devuelve la representación adecuada en su convención canónica:
  * scene: metros, Z arriba (metadata['source_unit_m'] = unidad nativa del archivo)
  * cad:   milímetros, Z arriba
  * bim:   modelo IFC (IfcOpenShell genera geometría en metros, Z arriba)
"""
from __future__ import annotations

import os

import numpy as np

from .formats import FORMATS
from .options import UNITS_TO_METERS
from ..models.scene import SceneModel, axis_matrix, scale_matrix

UNIT_NAMES = {0.001: "mm", 0.01: "cm", 1.0: "m", 0.0254: "in", 0.3048: "ft"}


def unit_label(unit_m: float) -> str:
    for k, v in UNIT_NAMES.items():
        if abs(k - unit_m) < 1e-9 * max(1.0, k):
            return v
    return f"{unit_m:g} m"


def _unit_from_string(s: str) -> float | None:
    s = (s or "").strip().lower()
    table = {"mm": 0.001, "millimetre": 0.001, "millimeter": 0.001, "cm": 0.01, "centimetre": 0.01,
             "m": 1.0, "metre": 1.0, "meter": 1.0, "in": 0.0254, "inch": 0.0254, "ft": 0.3048, "foot": 0.3048,
             "km": 1000.0, "um": 1e-6, "micron": 1e-6}
    return table.get(s)


# ============================================================================ importación

def input_assumptions(fmt: str, options) -> tuple[float, str]:
    """Unidad y eje supuestos para formatos que no los declaran (OBJ/STL)."""
    if options.input_units != "auto":
        unit = UNITS_TO_METERS[options.input_units]
    else:
        unit = 0.001 if fmt == "stl" else 1.0
    if options.input_up_axis != "auto":
        up = options.input_up_axis
    else:
        up = "Z" if fmt == "stl" else "Y"
    return unit, up


def read(fmt: str, path: str, options, report, progress=None):
    """Devuelve (representación, modelo)."""
    info = FORMATS[fmt]
    if fmt in ("gltf", "glb"):
        from ..engines.mesh.gltf_io import read_gltf
        scene = read_gltf(path, report)
        scene.apply_root_transform(axis_matrix("Y", "Z"))
        scene.metadata["source_unit_m"] = 1.0
        report.info("glTF: metros, Y arriba → convertido a Z arriba interno.")
        return "scene", scene
    if fmt == "stl":
        from ..engines.mesh.stl_io import read_stl
        scene = read_stl(path, report)
        unit, up = input_assumptions(fmt, options)
        scene.apply_root_transform(axis_matrix(up, "Z") @ scale_matrix(unit))
        scene.metadata["source_unit_m"] = unit
        report.warn(f"STL no declara unidades ni ejes: se asume {unit_label(unit)} y {up} arriba "
                    "(configurable en Opciones).")
        return "scene", scene
    if fmt == "obj":
        from ..engines.mesh.ufbx_reader import read_with_ufbx
        unit, up = input_assumptions(fmt, options)
        scene = read_with_ufbx(path, report, is_obj=True, obj_unit_m=unit, obj_up=up)
        scene.metadata["source_unit_m"] = unit
        report.warn(f"OBJ no declara unidades ni ejes: se asume {unit_label(unit)} y {up} arriba "
                    "(configurable en Opciones).")
        return "scene", scene
    if fmt == "fbx":
        from ..engines.mesh.ufbx_reader import read_with_ufbx
        scene = read_with_ufbx(path, report)
        src_u = float(scene.metadata.get("original_unit_m") or 0.01)
        scene.metadata["source_unit_m"] = src_u
        report.info(f"FBX: unidad del archivo {unit_label(src_u)}; convertido a metros y Z arriba internos.")
        return "scene", scene
    if fmt in ("step", "iges"):
        from ..engines.cad.occt import read_cad
        cad = read_cad(path, fmt, report)
        cad.metadata["source_unit_m"] = _unit_from_string(cad.source_unit) or 0.001
        return "cad", cad
    if fmt == "ifc":
        from ..engines.bim.ifc import read_ifc
        bim = read_ifc(path, report)
        try:
            import ifcopenshell.util.unit as uu
            bim.metadata["source_unit_m"] = float(uu.calculate_unit_scale(bim.ifc))
        except Exception:
            bim.metadata["source_unit_m"] = 1.0
        return "bim", bim
    raise ValueError(f"Formato de entrada no soportado: {info.name}")


# ============================================================================ transformaciones

def transform(src_rep: str, dst_rep: str, model, options, report, progress=None):
    if src_rep == "cad" and dst_rep == "scene":
        from ..engines.cad.occt import tessellate
        scene = tessellate(model, options, report, progress)
        scene.metadata["source_unit_m"] = model.metadata.get("source_unit_m", 0.001)
        return scene
    if src_rep == "bim" and dst_rep == "scene":
        from ..engines.bim.ifc import bim_to_scene
        scene = bim_to_scene(model, options, report, progress)
        scene.metadata["source_unit_m"] = model.metadata.get("source_unit_m", 1.0)
        return scene
    if src_rep == "bim" and dst_rep == "cad":
        from ..engines.bim.ifc import bim_to_cad
        cad = bim_to_cad(model, options, report, progress)
        cad.metadata["source_unit_m"] = model.metadata.get("source_unit_m", 1.0)
        return cad
    if src_rep == "scene" and dst_rep == "cad":
        from ..engines.cad.occt import scene_to_cad
        cad = scene_to_cad(model, options, report, progress)
        cad.metadata["source_unit_m"] = model.metadata.get("source_unit_m", 1.0)
        return cad
    if src_rep == "scene" and dst_rep == "bim":
        from ..engines.bim.ifc import scene_to_bim
        bim = scene_to_bim(model, options, report, source_name=report.source and os.path.basename(report.source),
                           source_format=report.source_format, progress=progress)
        bim.metadata["source_unit_m"] = model.metadata.get("source_unit_m", 1.0)
        return bim
    raise ValueError(f"Transformación no soportada: {src_rep} → {dst_rep}")


# ============================================================================ exportación

def output_frame(fmt: str, model, options) -> tuple[float, str]:
    """Unidad (m por unidad) y eje vertical con los que se escriben los datos de salida."""
    if fmt in ("gltf", "glb", "fbx"):
        return 1.0, "Y"
    if fmt in ("obj", "stl"):
        if options.output_units != "auto":
            unit = UNITS_TO_METERS[options.output_units]
        else:
            unit = float(getattr(model, "metadata", {}).get("source_unit_m", 1.0 if fmt == "obj" else 0.001))
        if options.output_up_axis != "auto":
            up = options.output_up_axis
        else:
            up = "Y" if fmt == "obj" else "Z"
        return unit, up
    return 1.0, "Z"


def prepare_scene_for_output(scene: SceneModel, fmt: str, options, report) -> tuple[float, str]:
    unit, up = output_frame(fmt, scene, options)
    m = axis_matrix("Z", up) @ scale_matrix(1.0 / unit)
    scene.apply_root_transform(m)
    if fmt in ("obj", "stl"):
        report.warn(f"{FORMATS[fmt].name} no declara unidades: coordenadas escritas en {unit_label(unit)}, "
                    f"{up} arriba.")
    else:
        report.info(f"{FORMATS[fmt].name}: escrito en metros, Y arriba (convención del formato).")
    return unit, up


def apply_user_scale(rep: str, model, scale: float, report):
    if abs(scale - 1.0) < 1e-12:
        return model
    if rep == "scene":
        model.apply_root_transform(scale_matrix(scale))
    elif rep == "cad":
        from OCP.gp import gp_Trsf
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        t = gp_Trsf()
        t.SetScaleFactor(float(scale))
        for p in model.parts:
            p.shape = BRepBuilderAPI_Transform(p.shape, t, True).Shape()
    elif rep == "bim":
        report.warn("La escala adicional no se aplica a una conversión IFC → IFC directa (se conserva el modelo).")
        return model
    report.warn(f"Escala adicional aplicada: ×{scale:g}.")
    return model


def write(fmt: str, rep: str, model, path: str, options, report) -> list[str]:
    if rep == "scene":
        prepare_scene_for_output(model, fmt, options, report)
        if fmt in ("gltf", "glb"):
            from ..engines.mesh.gltf_writer import write_gltf
            return write_gltf(model, path, fmt == "glb", report, embed=options.gltf_embed,
                              keep_materials=options.keep_materials, include_properties=options.include_properties)
        if fmt == "obj":
            from ..engines.mesh.obj_writer import write_obj
            return write_obj(model, path, report, keep_materials=options.keep_materials)
        if fmt == "stl":
            from ..engines.mesh.stl_io import write_stl
            return write_stl(model, path, report, ascii_mode=options.stl_ascii)
        if fmt == "fbx":
            from ..engines.mesh.fbx_writer import write_fbx
            return write_fbx(model, path, report, keep_materials=options.keep_materials)
    if rep == "cad" and fmt in ("step", "iges"):
        from ..engines.cad.occt import write_cad
        return write_cad(model, path, fmt, report, step_schema=options.step_schema,
                         keep_structure=options.keep_structure)
    if rep == "bim" and fmt == "ifc":
        from ..engines.bim.ifc import write_ifc
        return write_ifc(model, path, report)
    raise ValueError(f"No hay exportador {rep} → {fmt}")


def canonical_bounds(rep: str, model) -> np.ndarray | None:
    """Caja envolvente en metros (Z arriba)."""
    if rep == "scene":
        return model.bounds()
    if rep == "cad":
        b = model.bounds()
        return None if b is None else b * 0.001
    return None


def instance_count(rep: str, model) -> int:
    if rep == "scene":
        return sum(1 for _ in model.iter_world_meshes())
    if rep == "cad":
        return len(model.parts)
    if rep == "bim":
        return len(model.products_with_geometry())
    return 0
