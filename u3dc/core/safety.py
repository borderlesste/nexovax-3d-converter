"""Seguridad de rutas, nombres de salida, preparación temporal y escritura atómica."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid

TEMP_PREFIX = "u3dc_"
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def long_path(p: str) -> str:
    """Prefijo \\\\?\\ para rutas largas en Windows (operaciones de archivo de Python)."""
    p = os.path.abspath(p)
    if os.name == "nt" and len(p) >= 240 and not p.startswith("\\\\?\\"):
        return "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p
    return p


def safe_filename(name: str, max_len: int = 150) -> str:
    name = _INVALID.sub("_", name).strip(" .")
    if not name:
        name = "modelo"
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name[:max_len]


def needs_short_copy(path: str) -> bool:
    """Los motores C++ (OCCT, IfcOpenShell) pueden fallar con rutas largas o no ASCII."""
    p = os.path.abspath(path)
    return len(p) > 200 or not p.isascii()


def make_staging_dir() -> str:
    base = os.path.join(tempfile.gettempdir(), "u3dc")
    os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=base)


def cleanup_dir(path: str | None) -> None:
    if path and os.path.isdir(path):
        shutil.rmtree(long_path(path), ignore_errors=True)


def cleanup_stale_temp(max_age_s: float = 24 * 3600) -> int:
    """Elimina carpetas temporales huérfanas de ejecuciones anteriores interrumpidas."""
    import time
    base = os.path.join(tempfile.gettempdir(), "u3dc")
    n = 0
    if not os.path.isdir(base):
        return 0
    for d in os.listdir(base):
        full = os.path.join(base, d)
        try:
            if d.startswith(TEMP_PREFIX) and time.time() - os.path.getmtime(full) > max_age_s:
                shutil.rmtree(full, ignore_errors=True)
                n += 1
        except OSError:
            pass
    return n


def unique_output_names(out_dir: str, stem: str, ext: str, aux_suffixes: list[str], overwrite: bool) -> str:
    """Devuelve un 'stem' libre: ni el archivo principal ni sus auxiliares sobrescriben nada."""
    if overwrite:
        return stem
    candidate = stem
    k = 1
    while True:
        names = [candidate + ext] + [candidate + s for s in aux_suffixes]
        if not any(os.path.exists(long_path(os.path.join(out_dir, n))) for n in names):
            return candidate
        candidate = f"{stem} ({k})"
        k += 1


def atomic_move(src: str, dst: str, overwrite: bool) -> str:
    """Mueve src a dst de forma atómica (copia temporal en el destino + os.replace)."""
    dst_l = long_path(dst)
    if os.path.exists(dst_l) and not overwrite:
        raise FileExistsError(f"Ya existe: {dst}")
    tmp = long_path(os.path.join(os.path.dirname(dst), f".{uuid.uuid4().hex[:8]}.u3dc-partial"))
    try:
        shutil.copyfile(long_path(src), tmp)
        os.replace(tmp, dst_l)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return dst


def copy_for_engine(path: str, staging: str, fmt: str) -> str:
    """Copia el archivo de entrada a una ruta corta ASCII dentro de la carpeta temporal."""
    ext = os.path.splitext(path)[1].lower() or "." + fmt
    dst = os.path.join(staging, "input" + ext)
    shutil.copyfile(long_path(path), dst)
    return dst
