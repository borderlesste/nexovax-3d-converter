"""Registro de formatos y detección por contenido real (no solo por extensión)."""
from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class FormatInfo:
    id: str
    name: str
    long_name: str
    extensions: tuple
    family: str            # "mesh" | "cad" | "bim"
    representation: str    # "scene" | "cad" | "bim"
    has_units: bool        # ¿el archivo declara unidades?
    up_axis: str | None    # convención de ejes del formato, None = sin convención fija


FORMATS: dict[str, FormatInfo] = {
    "gltf": FormatInfo("gltf", "glTF", "glTF 2.0 (JSON + recursos)", (".gltf",), "mesh", "scene", True, "Y"),
    "glb": FormatInfo("glb", "GLB", "GLB (glTF binario)", (".glb",), "mesh", "scene", True, "Y"),
    "obj": FormatInfo("obj", "OBJ", "Wavefront OBJ", (".obj",), "mesh", "scene", False, None),
    "fbx": FormatInfo("fbx", "FBX", "Autodesk FBX (binario 7.4)", (".fbx",), "mesh", "scene", True, "Y"),
    "stl": FormatInfo("stl", "STL", "STL (estereolitografía)", (".stl",), "mesh", "scene", False, None),
    "ifc": FormatInfo("ifc", "IFC", "IFC (Industry Foundation Classes)", (".ifc",), "bim", "bim", True, "Z"),
    "step": FormatInfo("step", "STEP", "STEP AP203/AP214/AP242", (".step", ".stp"), "cad", "cad", True, "Z"),
    "iges": FormatInfo("iges", "IGES", "IGES 5.3", (".igs", ".iges"), "cad", "cad", True, "Z"),
}

FORMAT_ORDER = ["gltf", "glb", "obj", "fbx", "stl", "ifc", "step", "iges"]

EXT_TO_FORMAT = {ext: f.id for f in FORMATS.values() for ext in f.extensions}

ALL_EXTENSIONS = tuple(sorted(EXT_TO_FORMAT))


class DetectionError(Exception):
    pass


def format_from_extension(path: str) -> str | None:
    return EXT_TO_FORMAT.get(os.path.splitext(path)[1].lower())


def _read_head(path: str, n: int = 65536) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def sniff_format(path: str) -> str | None:
    """Determina el formato a partir del contenido del archivo."""
    size = os.path.getsize(path)
    head = _read_head(path)
    if not head:
        return None
    if head[:4] == b"glTF":
        return "glb"
    if head.startswith(b"Kaydara FBX Binary"):
        return "fbx"
    text = head.decode("latin-1", errors="replace")
    stripped = text.lstrip("﻿ \t\r\n")
    if stripped.startswith("ISO-10303-21"):
        m = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", text, re.IGNORECASE)
        schema = (m.group(1) if m else "").upper()
        return "ifc" if schema.startswith("IFC") else "step"
    # STL binario: 80 bytes cabecera + nº triángulos
    if size >= 84:
        (count,) = struct.unpack("<I", head[80:84])
        if 84 + count * 50 == size:
            return "stl"
    low = stripped[:4096].lower()
    if low.startswith("solid") and ("facet" in low or "endsolid" in low or size < 4096):
        return "stl"
    if stripped.startswith("{") and '"asset"' in text:
        return "gltf"
    if stripped.startswith("; FBX") or "FBXHeaderExtension" in text[:4096]:
        return "fbx"
    # IGES: registros de 80 columnas con letra de sección en la columna 73
    lines = text.splitlines()[:5]
    if lines and all(len(l) >= 73 and l[72] in "SGDPT" for l in lines if l.strip()):
        return "iges"
    # OBJ: líneas con palabras clave conocidas
    obj_kw = ("v ", "vt ", "vn ", "f ", "o ", "g ", "mtllib ", "usemtl ", "s ", "#", "vp ", "l ")
    content_lines = [l.strip() for l in text.splitlines()[:200] if l.strip()]
    if content_lines and sum(1 for l in content_lines if l.startswith(obj_kw)) >= 0.9 * len(content_lines) \
            and any(l.startswith("v ") for l in content_lines):
        return "obj"
    return None


def detect(path: str) -> tuple[str, list[str]]:
    """Devuelve (formato, advertencias). Lanza DetectionError si no es reconocible."""
    warnings = []
    if not os.path.isfile(path):
        raise DetectionError(f"El archivo no existe: {path}")
    if os.path.getsize(path) == 0:
        raise DetectionError("El archivo está vacío (0 bytes).")
    by_ext = format_from_extension(path)
    by_content = sniff_format(path)
    if by_content is None and by_ext is None:
        raise DetectionError("Formato no reconocido por extensión ni por contenido.")
    if by_content is None:
        # Contenido no concluyente (p. ej. OBJ con cabecera inusual): confiar en la extensión
        warnings.append(f"No se pudo confirmar el formato por contenido; se usa la extensión ({FORMATS[by_ext].name}).")
        return by_ext, warnings
    if by_ext and by_ext != by_content:
        warnings.append(f"La extensión indica {FORMATS[by_ext].name} pero el contenido es "
                        f"{FORMATS[by_content].name}; se usa el contenido real.")
    return by_content, warnings
