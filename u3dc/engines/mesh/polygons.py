"""Triangulación de polígonos (vectorizada para triángulos/cuadriláteros, ear-clipping para n-gonos)."""
from __future__ import annotations

import numpy as np


def _ear_clip(points: np.ndarray) -> list[tuple[int, int, int]]:
    """Ear clipping sobre un polígono 3D plano (o casi plano). Devuelve índices locales."""
    n = len(points)
    if n < 3:
        return []
    # Normal de Newell y proyección al plano dominante
    normal = np.zeros(3)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        normal += [(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])]
    axis = int(np.argmax(np.abs(normal)))
    keep = [k for k in range(3) if k != axis]
    p2 = points[:, keep]
    if normal[axis] < 0:
        p2 = p2[:, ::-1]
    idx = list(range(n))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    guard = 0
    while len(idx) > 3 and guard < n * n:
        guard += 1
        found = False
        m = len(idx)
        for i in range(m):
            i0, i1, i2 = idx[(i - 1) % m], idx[i], idx[(i + 1) % m]
            a, b, c = p2[i0], p2[i1], p2[i2]
            if cross(a, b, c) <= 0:
                continue
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = p2[j]
                if cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0:
                    inside = True
                    break
            if inside:
                continue
            tris.append((i0, i1, i2))
            idx.pop(i)
            found = True
            break
        if not found:   # polígono degenerado o auto-intersectado: abanico de seguridad
            break
    for k in range(1, len(idx) - 1):
        tris.append((idx[0], idx[k], idx[k + 1]))
    return tris


def triangulate(starts: np.ndarray, counts: np.ndarray, corner_pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Triangula polígonos definidos por (inicio, nº de esquinas) sobre un array de esquinas.

    corner_pos: posiciones 3D por esquina (para el ear clipping de n-gonos).
    Devuelve (triángulos como índices de esquina (T,3), índice del polígono de cada triángulo (T,)).
    """
    starts = np.asarray(starts, dtype=np.int64)
    counts = np.asarray(counts, dtype=np.int64)
    out_tris, out_face = [], []
    tri_mask = counts == 3
    if tri_mask.any():
        s = starts[tri_mask]
        out_tris.append(np.stack([s, s + 1, s + 2], axis=1))
        out_face.append(np.nonzero(tri_mask)[0])
    quad_mask = counts == 4
    if quad_mask.any():
        s = starts[quad_mask]
        fidx = np.nonzero(quad_mask)[0]
        # dividir por la diagonal más corta
        p0, p1, p2, p3 = (corner_pos[s + k] for k in range(4))
        d02 = np.linalg.norm(p2 - p0, axis=1)
        d13 = np.linalg.norm(p3 - p1, axis=1)
        use02 = d02 <= d13
        t1 = np.where(use02[:, None], np.stack([s, s + 1, s + 2], 1), np.stack([s, s + 1, s + 3], 1))
        t2 = np.where(use02[:, None], np.stack([s, s + 2, s + 3], 1), np.stack([s + 1, s + 2, s + 3], 1))
        out_tris += [t1, t2]
        out_face += [fidx, fidx]
    big = np.nonzero(counts > 4)[0]
    if len(big):
        tl, fl = [], []
        for fi in big:
            s, c = int(starts[fi]), int(counts[fi])
            for a, b, cc in _ear_clip(corner_pos[s:s + c]):
                tl.append((s + a, s + b, s + cc))
                fl.append(fi)
        if tl:
            out_tris.append(np.array(tl, dtype=np.int64))
            out_face.append(np.array(fl, dtype=np.int64))
    if not out_tris:
        return np.zeros((0, 3), np.int64), np.zeros(0, np.int64)
    tris = np.concatenate(out_tris)
    faces = np.concatenate(out_face)
    order = np.argsort(faces, kind="stable")
    return tris[order], faces[order]


def compact_corners(keys: np.ndarray, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Deduplica esquinas con los mismos atributos.

    keys: (C,k) enteros que identifican atributos de cada esquina.
    Devuelve (índice de esquina representativa por vértice nuevo, triángulos reindexados).
    """
    used = np.unique(tris.reshape(-1))
    sub = keys[used]
    _, first, inv = np.unique(sub, axis=0, return_index=True, return_inverse=True)
    remap = np.full(len(keys), -1, dtype=np.int64)
    remap[used] = inv.reshape(-1)
    rep_corner = used[first]
    return rep_corner, remap[tris]
