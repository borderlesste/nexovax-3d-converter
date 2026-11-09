"""Generadores de STL de prueba para la ruta STL → STEP (casos patológicos reales de mallas descargadas).

Todos escriben STL binario en milímetros. Se usan en tests/test_stl_to_step.py y en tools/repro_stl_step.py.
"""
from __future__ import annotations

import numpy as np

_DT = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])


def write_stl(path: str, tris: np.ndarray, header: bytes = b"caso de prueba") -> str:
    tris = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3)
    data = np.zeros(len(tris), _DT)
    data["v"] = tris
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    data["n"] = n / ln
    with open(path, "wb") as fh:
        fh.write(header[:80].ljust(80, b" "))
        fh.write(np.uint32(len(tris)).tobytes())
        data.tofile(fh)
    return path


def box(x0, y0, z0, x1, y1, z1) -> np.ndarray:
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    f = [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
         [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]   # normales hacia fuera
    return v[np.array(f)]


def sphere_fast(r, n, center=(0, 0, 0)) -> np.ndarray:
    """Esfera UV cerrada y manifold (casquetes en abanico en los polos): 2·n·(n-1) triángulos."""
    c = np.asarray(center, float)
    th = np.linspace(0, np.pi, n + 1)[1:-1]                    # anillos interiores (sin polos)
    ph = np.linspace(0, 2 * np.pi, n, endpoint=False)
    T, P = np.meshgrid(th, ph, indexing="ij")
    ring = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P), np.cos(T)], -1) * r + c   # (n-1, n, 3)
    nxt = np.roll(ring, -1, axis=1)
    top, bot = c + [0, 0, r], c - [0, 0, r]
    cap_t = np.stack([np.broadcast_to(top, ring[0].shape), ring[0], nxt[0]], 1)
    cap_b = np.stack([np.broadcast_to(bot, ring[-1].shape), nxt[-1], ring[-1]], 1)
    a, b2, cc, d = ring[:-1], ring[1:], nxt[1:], nxt[:-1]
    q1 = np.stack([a, b2, cc], -2).reshape(-1, 3, 3)
    q2 = np.stack([a, cc, d], -2).reshape(-1, 3, 3)
    return np.concatenate([cap_t, q1, q2, cap_b])


def grid(nx, ny, size=100.0, z=lambda x, y: 0 * x) -> np.ndarray:
    """Superficie abierta (relieve) de 2·nx·ny triángulos."""
    xs = np.linspace(0, size, nx + 1)
    ys = np.linspace(0, size, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    Z = z(X, Y)
    P = np.stack([X, Y, Z], -1)
    a, b, c, d = P[:-1, :-1], P[1:, :-1], P[1:, 1:], P[:-1, 1:]
    return np.concatenate([np.stack([a, b, c], -2).reshape(-1, 3, 3), np.stack([a, c, d], -2).reshape(-1, 3, 3)])


def lipo_battery(density: int = 120) -> np.ndarray:
    """Modelo tipo «batería LiPo» como los que se descargan de repositorios 3D y pasan por conversores
    en línea: cuerpo, etiqueta en relieve (pieza separada que interseca), 2 cables, conector, con
    defectos típicos: componentes múltiples, triángulos duplicados, degenerados y orientación mezclada."""
    parts = [box(0, 0, 0, 105, 34, 24),                       # cuerpo
             box(10, -0.2, 4, 95, 0.0, 20)]                    # etiqueta pegada a una cara (geometría coplanar)
    for k, y in enumerate((10.0, 24.0)):                       # cables (cilindros cerrados)
        th = np.linspace(0, 2 * np.pi, density + 1)
        r, L = 1.6, 60.0
        cy, cz = y, 12.0
        ring = lambda x: np.stack([np.full_like(th, x), cy + r * np.cos(th), cz + r * np.sin(th)], -1)  # noqa: E731
        p0, p1 = ring(105.0), ring(105.0 + L)
        side = np.concatenate([np.stack([p0[:-1], p1[:-1], p1[1:]], 1), np.stack([p0[:-1], p1[1:], p0[1:]], 1)])
        c0 = np.array([105.0, cy, cz])
        c1 = np.array([105.0 + L, cy, cz])
        cap0 = np.stack([np.repeat(c0[None], density, 0), p0[1:], p0[:-1]], 1)
        cap1 = np.stack([np.repeat(c1[None], density, 0), p1[:-1], p1[1:]], 1)
        parts.append(np.concatenate([side, cap0, cap1]))
    parts.append(sphere_fast(6.0, density // 2, center=(170.0, 17.0, 12.0)))   # conector redondeado
    tris = np.concatenate(parts)
    rng = np.random.default_rng(7)
    flip = rng.random(len(tris)) < 0.03                           # 3 % de triángulos con orientación invertida
    tris[flip] = tris[flip][:, ::-1]
    dup = tris[rng.choice(len(tris), max(1, len(tris) // 200), replace=False)]   # 0,5 % duplicados
    degen = tris[:20].copy()
    degen[:, 2] = degen[:, 1]                                     # 20 triángulos degenerados
    return np.concatenate([tris, dup, degen])
