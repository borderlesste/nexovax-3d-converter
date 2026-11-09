"""STL ASCII/binario: lector y escritor propios (rápidos, con numpy)."""
from __future__ import annotations

import os
import re
import struct

import numpy as np

from ...models.scene import SceneModel, SceneNode, Mesh


def weld(tri_vertices: np.ndarray, tol_rel: float = 1e-9) -> tuple[np.ndarray, np.ndarray]:
    """Suelda vértices coincidentes de una sopa de triángulos (T,3,3) → (V,3), (T,3)."""
    flat = tri_vertices.reshape(-1, 3)
    if len(flat) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    ext = float(np.ptp(flat, axis=0).max()) or 1.0
    q = np.round(flat / (ext * tol_rel)).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    return flat[first], inv.reshape(-1, 3)


def read_stl(path: str, report) -> SceneModel:
    size = os.path.getsize(path)
    solids: list[tuple[str, np.ndarray]] = []
    with open(path, "rb") as fh:
        header = fh.read(84)
    is_binary = False
    if len(header) >= 84:
        (count,) = struct.unpack("<I", header[80:84])
        is_binary = 84 + count * 50 == size
    if is_binary:
        dtype = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
        data = np.fromfile(path, dtype=dtype, count=count, offset=84)
        # La cabecera binaria es un comentario libre (texto del exportador o basura), no un nombre de objeto
        stl_header = header[:80].split(b"\x00")[0].decode("latin-1", "replace").strip()
        solids.append((os.path.splitext(os.path.basename(path))[0], data["v"].astype(np.float64)))
        if np.any(data["attr"] != 0):
            report.loss("Atributos de color por faceta del STL binario (no estándar) ignorados.")
    else:
        text = open(path, "r", encoding="latin-1").read()
        pattern = re.compile(r"solid\s*([^\r\n]*)(.*?)endsolid", re.S | re.I)
        num = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
        vre = re.compile(r"vertex\s+(" + num + r")\s+(" + num + r")\s+(" + num + r")", re.I)
        blocks = pattern.findall(text)
        if not blocks:
            raise ValueError("STL ASCII sin bloques 'solid ... endsolid' válidos.")
        for bname, body in blocks:
            vs = np.array(vre.findall(body), dtype=np.float64)
            if len(vs) % 3:
                raise ValueError("STL ASCII corrupto: número de vértices no múltiplo de 3.")
            solids.append((bname.strip() or f"solid{len(solids)}", vs.reshape(-1, 3, 3)))
    scene = SceneModel(name=os.path.splitext(os.path.basename(path))[0])
    if is_binary:
        scene.metadata["stl_header"] = stl_header
    total = 0
    for name, tris in solids:
        if not np.all(np.isfinite(tris)):
            bad = ~np.all(np.isfinite(tris.reshape(len(tris), -1)), axis=1)
            report.warn(f"{int(bad.sum())} triángulos con coordenadas no válidas (NaN/inf) eliminados.")
            tris = tris[~bad]
        if len(tris) == 0:
            continue
        v, f = weld(tris)
        mi = scene.add_mesh(Mesh(name=name, vertices=v, faces=f))
        scene.add_node(SceneNode(name=name, meshes=[mi]))
        total += len(f)
    if total == 0:
        raise ValueError("El STL no contiene triángulos.")
    return scene


def write_stl(scene: SceneModel, path: str, report, ascii_mode: bool = False) -> list[str]:
    parts = scene.scaled_copy_flat()
    if not parts:
        raise ValueError("No hay geometría para exportar a STL.")
    if ascii_mode:
        with open(path, "w", encoding="ascii", errors="replace", newline="\n") as fh:
            for name, v, f, *_ in parts:
                safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "objeto"
                tri = v[f]
                n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
                ln = np.linalg.norm(n, axis=1, keepdims=True)
                ln[ln == 0] = 1
                n = n / ln
                fh.write(f"solid {safe}\n")
                for k in range(len(tri)):
                    a, b, c = tri[k]
                    fh.write(f" facet normal {n[k,0]:.7e} {n[k,1]:.7e} {n[k,2]:.7e}\n  outer loop\n"
                             f"   vertex {a[0]:.9e} {a[1]:.9e} {a[2]:.9e}\n"
                             f"   vertex {b[0]:.9e} {b[1]:.9e} {b[2]:.9e}\n"
                             f"   vertex {c[0]:.9e} {c[1]:.9e} {c[2]:.9e}\n  endloop\n endfacet\n")
                fh.write(f"endsolid {safe}\n")
    else:
        tris = np.concatenate([v[f] for _, v, f, *_ in parts])
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        ln[ln == 0] = 1
        n = n / ln
        dtype = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
        data = np.zeros(len(tris), dtype=dtype)
        data["n"] = n
        data["v"] = tris
        header = f"NEXOVAX 3D Converter STL - {scene.name}".encode("ascii", "replace")[:80].ljust(80, b" ")
        if header.lower().startswith(b"solid"):
            header = b"_" + header[1:]
        with open(path, "wb") as fh:
            fh.write(header)
            fh.write(struct.pack("<I", len(tris)))
            data.tofile(fh)
        if np.abs(tris).max() > 1e6:
            report.warn("STL binario usa float32: coordenadas > 1e6 pierden precisión.")
    return [path]
