"""Generación de datos de vista previa (se ejecuta en un proceso aislado).

Produce un archivo .npz con vértices/caras/colores por objeto en coordenadas mundo (metros,
Z arriba) y un diccionario con información del modelo (dimensiones, volumen, conteos).
"""
from __future__ import annotations

import copy
import os

import numpy as np

from .formats import detect, FORMATS
from .options import ConversionOptions
from .report import ConversionReport
from . import adapters

MAX_PREVIEW_TRIANGLES = 3_000_000


def build_preview(source: str, options: ConversionOptions, out_path: str) -> dict:
    fmt, warns = detect(source)
    rep_obj = ConversionReport(source=source, source_format=fmt)
    opts = copy.deepcopy(options)
    opts.quality = "media"
    opts.include_properties = False
    rep, model = adapters.read(fmt, source, opts, rep_obj)
    if rep == "cad":
        model = adapters.transform("cad", "scene", model, opts, rep_obj)
    elif rep == "bim":
        model = adapters.transform("bim", "scene", model, opts, rep_obj)
    scene = model
    arrays = {}
    names = []
    total = 0
    volume = 0.0
    closed_all = True
    from ..models.scene import mesh_quality
    for k, (node, mesh, world) in enumerate(scene.iter_world_meshes()):
        if len(mesh.faces) == 0:
            continue
        v = mesh.vertices @ world[:3, :3].T + world[:3, 3]
        f = mesh.faces if np.linalg.det(world[:3, :3]) >= 0 else mesh.faces[:, ::-1]
        total += len(f)
        if total > MAX_PREVIEW_TRIANGLES:
            rep_obj.warn("Vista previa simplificada: se muestran los primeros 3 millones de triángulos.")
            break
        color = (0.75, 0.77, 0.80, 1.0)
        if mesh.material is not None and mesh.material < len(scene.materials):
            color = scene.materials[mesh.material].base_color
        tri = v[f]
        vol = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
        if len(f) < 400_000:
            q = mesh_quality(v, f)
            closed_all &= q["closed"]
        else:
            closed_all = False
        volume += vol
        i = len(names)
        arrays[f"v{i}"] = v.astype(np.float32)
        arrays[f"f{i}"] = f.astype(np.int32)
        arrays[f"c{i}"] = np.asarray(color, dtype=np.float32)
        names.append(node.name)
    np.savez(out_path, count=np.array(len(names)), **arrays)
    b = scene.bounds()
    info = {
        "format": fmt, "format_name": FORMATS[fmt].long_name, "objects": len(names), "triangles": total,
        "bounds": None if b is None else b.tolist(), "names": names[:500],
        "volume_m3": abs(volume) if closed_all else None,
        "warnings": warns + rep_obj.warnings, "losses": rep_obj.losses,
        "materials": len(scene.materials), "textures": len(scene.textures),
    }
    return info
