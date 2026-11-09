"""Malla triangular → B-Rep facetado (STEP/IGES), con análisis, reparación controlada,
estimación de recursos, simplificación opcional y construcción nativa en Open CASCADE.

Etapas (cada una queda registrada en el informe y en el archivo de diagnóstico):
  1. análisis de malla      componentes, aristas abiertas/no manifold, orientación, degenerados, duplicados
  2. reparación de malla    soldadura con tolerancia, eliminación de degenerados/duplicados, orientación coherente
  3. estimación de recursos memoria, tiempo y tamaño del STEP frente a la memoria disponible
  4. simplificación         reducción de triángulos (fast-simplification, MIT) solo si procede
  5. construcción B-Rep     BRepBuilderAPI_MakeShapeOnMesh (C++) → shell → sólido si es cerrado y válido
  6. unión de caras         ShapeUpgrade_UnifySameDomain (caras coplanares) cuando el tamaño lo permite

No se reconstruye CAD paramétrico: el resultado es un B-Rep facetado (cada cara es plana).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict

import numpy as np

# Coste medido (OCCT 8.0, Windows 11) por triángulo de B-Rep facetado, como memoria ADICIONAL del
# proceso de trabajo (construcción + transferencia + escritura STEP):
#   esfera 150 000 triángulos sin unión de caras: ≈1,8 GB  → 0,0135 MB/triángulo
#   casco GLB 20 000 / 50 000 triángulos con unión de caras coplanares: +522 / +1 163 MB → ≈0,025 MB/triángulo
MEM_MB_PER_TRI = 0.0135          # sin unión de caras coplanares (mallas grandes)
MEM_MB_PER_TRI_UNIFY = 0.025     # con unión de caras coplanares (≤ unify_max_triangles)
STEP_KB_PER_TRI = 2.4            # tamaño del STEP resultante (45 MB para 20 000 triángulos)
MS_PER_TRI = 2.4                 # construcción + transferencia + escritura + relectura de validación
BASE_MEM_MB = 350.0              # proceso de trabajo con las bibliotecas cargadas (solo para la estimación total)


# ============================================================================ análisis

@dataclass
class ComponentInfo:
    triangles: int
    closed: bool
    open_edges: int
    nonmanifold_edges: int
    inconsistent_edges: int
    signed_volume: float

    @property
    def kind(self) -> str:
        if self.nonmanifold_edges:
            return "no manifold"
        if self.closed and not self.inconsistent_edges:
            return "cerrada"
        if self.closed:
            return "cerrada (orientación incoherente)"
        return "abierta"


@dataclass
class MeshDiagnostics:
    vertices: int = 0
    triangles: int = 0
    duplicate_vertices: int = 0
    degenerate_triangles: int = 0
    duplicate_triangles: int = 0
    components: list = field(default_factory=list)
    bbox_mm: list = field(default_factory=list)

    @property
    def open_edges(self) -> int:
        return sum(c.open_edges for c in self.components)

    @property
    def nonmanifold_edges(self) -> int:
        return sum(c.nonmanifold_edges for c in self.components)

    @property
    def inconsistent_edges(self) -> int:
        return sum(c.inconsistent_edges for c in self.components)

    @property
    def state(self) -> str:
        if not self.components:
            return "vacía"
        if self.nonmanifold_edges:
            return "no manifold"
        if self.open_edges:
            return "abierta"
        return "cerrada"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["componentes"] = len(self.components)
        d["estado"] = self.state
        d["aristas_abiertas"] = self.open_edges
        d["aristas_no_manifold"] = self.nonmanifold_edges
        d["aristas_orientacion_incoherente"] = self.inconsistent_edges
        d["componentes_cerrados"] = sum(1 for c in self.components if c.closed)
        d.pop("components")
        d["detalle_componentes"] = [dict(asdict(c), tipo=c.kind) for c in self.components[:50]]
        return d


def weld(vertices: np.ndarray, faces: np.ndarray, tol: float) -> tuple[np.ndarray, np.ndarray, int]:
    """Suelda vértices a distancia < tol (cuantización). Devuelve (v, f, nº de vértices fusionados)."""
    if len(vertices) == 0:
        return vertices, faces, 0
    q = np.round(vertices / max(tol, 1e-15)).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    return vertices[first], inv.reshape(-1)[faces], int(len(vertices) - len(first))


def degenerate_mask(v: np.ndarray, f: np.ndarray, tol_area: float) -> np.ndarray:
    same = (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])
    tri = v[f]
    area2 = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    return same | (area2 <= tol_area)


def face_components(f: np.ndarray, n_vertices: int) -> np.ndarray:
    """Etiqueta de componente conectado (por vértices compartidos) de cada triángulo (0..k-1)."""
    if len(f) == 0:
        return np.zeros(0, np.int64)
    lab = _union_labels(n_vertices, np.concatenate([f[:, 0], f[:, 1]]), np.concatenate([f[:, 1], f[:, 2]]))
    _, comp = np.unique(lab[f[:, 0]], return_inverse=True)
    return comp.reshape(-1)


def _edge_table(f: np.ndarray):
    """Tabla de aristas de una malla (todo vectorizado).

    Devuelve (d, eid, cnt, did, dcnt): aristas dirigidas por aparición (3·nf, 2) en el orden
    [aristas 0-1 de todas las caras, 1-2, 2-0]; id de la arista no dirigida de cada aparición;
    multiplicidad de cada arista no dirigida; id y multiplicidad de cada arista dirigida.
    """
    d = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]).astype(np.int64)
    n = int(d.max()) + 1 if len(d) else 1
    lo, hi = np.minimum(d[:, 0], d[:, 1]), np.maximum(d[:, 0], d[:, 1])
    _, eid, cnt = np.unique(lo * n + hi, return_inverse=True, return_counts=True)
    _, did, dcnt = np.unique(d[:, 0] * n + d[:, 1], return_inverse=True, return_counts=True)
    return d, eid.reshape(-1), cnt, did.reshape(-1), dcnt


def _edge_stats(f: np.ndarray) -> tuple[int, int, int]:
    """(aristas abiertas, aristas no manifold, aristas manifold con orientación incoherente)."""
    if len(f) == 0:
        return 0, 0, 0
    _, _, cnt, _, dcnt = _edge_table(f)
    # en una arista manifold coherente, las dos apariciones van en sentidos opuestos
    return int(np.count_nonzero(cnt == 1)), int(np.count_nonzero(cnt > 2)), int(np.count_nonzero(dcnt == 2))


def _face_volumes(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    tri = v[f]
    return np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0


def _signed_volume(v: np.ndarray, f: np.ndarray) -> float:
    return float(_face_volumes(v, f).sum())


def _component_stats(v: np.ndarray, f: np.ndarray, comp: np.ndarray) -> list[ComponentInfo]:
    """Estadísticas por componente en una sola pasada (sin bucles por componente)."""
    nc = int(comp.max()) + 1 if len(comp) else 0
    if nc == 0:
        return []
    owner = np.tile(np.arange(len(f)), 3)
    _, eid, cnt, did, dcnt = _edge_table(f)
    ecomp = np.empty(len(cnt), np.int64)
    ecomp[eid] = comp[owner]                      # todas las caras de una arista están en el mismo componente
    dcomp = np.empty(len(dcnt), np.int64)
    dcomp[did] = comp[owner]
    tris = np.bincount(comp, minlength=nc)
    opn = np.bincount(ecomp[cnt == 1], minlength=nc)
    nonm = np.bincount(ecomp[cnt > 2], minlength=nc)
    inc = np.bincount(dcomp[dcnt == 2], minlength=nc)
    vol = np.bincount(comp, weights=_face_volumes(v, f), minlength=nc)
    return [ComponentInfo(triangles=int(tris[c]), closed=bool(opn[c] == 0 and nonm[c] == 0),
                          open_edges=int(opn[c]), nonmanifold_edges=int(nonm[c]), inconsistent_edges=int(inc[c]),
                          signed_volume=round(float(vol[c]), 6)) for c in range(nc)]


def analyze(v: np.ndarray, f: np.ndarray, duplicate_vertices: int = 0) -> MeshDiagnostics:
    d = MeshDiagnostics(vertices=int(len(v)), triangles=int(len(f)), duplicate_vertices=int(duplicate_vertices))
    if len(f) == 0:
        return d
    ext = float(np.ptp(v, axis=0).max()) or 1.0
    d.bbox_mm = [v.min(axis=0).round(6).tolist(), v.max(axis=0).round(6).tolist()]
    d.degenerate_triangles = int(degenerate_mask(v, f, (ext * 1e-9) ** 2).sum())
    d.duplicate_triangles = int(len(f) - len(np.unique(np.sort(f, axis=1), axis=0)))
    d.components = _component_stats(v, f, face_components(f, len(v)))
    return d


# ============================================================================ reparación

def _union_labels(n: int, a: np.ndarray, b: np.ndarray, c: np.ndarray | None = None, parity: bool = False):
    """Componentes conectados de un grafo de n nodos con aristas (a, b), todo vectorizado.

    Union-find por rondas: se enganchan las raíces (la mayor apunta a la menor) y se comprimen los
    caminos por completo; converge en O(log n) rondas. Con parity=True mantiene además la paridad
    de cada nodo respecto a su raíz, con la restricción paridad(a) XOR paridad(b) = c (0/1 por arista).
    Devuelve la raíz de cada nodo, o (raíz, paridad) con parity=True.
    """
    lab = np.arange(n, dtype=np.int64)
    par = np.zeros(n, np.int64)
    a = np.asarray(a, np.int64)
    b = np.asarray(b, np.int64)
    c = np.zeros(len(a), np.int64) if c is None else np.asarray(c, np.int64)
    for _ in range(200):
        ra, rb = lab[a], lab[b]
        m = ra != rb
        if not m.any():
            break
        a, b, c, ra, rb = a[m], b[m], c[m], ra[m], rb[m]
        hi, lo = np.maximum(ra, rb), np.minimum(ra, rb)
        key = np.arange(n, dtype=np.int64) * 2
        np.minimum.at(key, hi, lo * 2 + (par[a] ^ par[b] ^ c))
        changed = key != np.arange(n, dtype=np.int64) * 2
        lab[changed] = key[changed] // 2
        par[changed] = key[changed] % 2
        while True:                                # compresión completa de caminos
            nxt = lab[lab]
            if np.array_equal(nxt, lab):
                break
            if parity:
                par = par ^ par[lab]
            lab = nxt
    return (lab, par) if parity else lab


def _manifold_pairs(f: np.ndarray):
    """Pares de apariciones (p, q) de las aristas con exactamente dos caras."""
    _, eid, cnt, _, _ = _edge_table(f)
    order = np.argsort(eid, kind="stable")
    keep = cnt[eid[order]] == 2
    pairs = order[keep].reshape(-1, 2)
    return pairs[:, 0], pairs[:, 1]


def _orient_consistently(f: np.ndarray) -> tuple[np.ndarray, int]:
    """Invierte triángulos para que cada arista manifold se recorra en sentidos opuestos.

    Union-find vectorizado con paridad (sin recorrido triángulo a triángulo): cada cara guarda
    (raíz, paridad respecto a la raíz). En cada parche se conserva la orientación de la mayoría.
    """
    nf = len(f)
    if nf == 0:
        return f, 0
    p, q = _manifold_pairs(f)
    fa, fb = p % nf, q % nf
    d = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    c = np.all(d[p] == d[q], axis=1).astype(np.int64)          # mismo sentido ⇒ paridades distintas
    lab, par = _union_labels(nf, fa, fb, c, parity=True)
    flips = np.bincount(lab, weights=par, minlength=nf)
    size = np.bincount(lab, minlength=nf)
    flip = (par == 1) ^ (flips[lab] * 2 > size[lab])          # conservar la orientación mayoritaria
    out = f.copy()
    out[flip] = out[flip][:, ::-1]
    return out, int(flip.sum())


def _remove_fins_and_flaps(f: np.ndarray) -> tuple[np.ndarray, int, int, int]:
    """Elimina defectos que impiden cerrar un sólido sin inventar geometría.

    - triángulos repetidos con la misma orientación: se conserva uno;
    - pares "espalda con espalda" (mismos vértices, orientación opuesta): aletas sin volumen, se eliminan;
    - solapas colgantes: triángulos con dos aristas libres apoyados en una arista no manifold.
    Devuelve (caras, duplicados, aletas, solapas).
    """
    s = np.sort(f, axis=1)
    _, first, grp, gcnt = np.unique(s, axis=0, return_index=True, return_inverse=True, return_counts=True)
    grp = grp.reshape(-1)
    dups = fins = flaps = 0
    if (gcnt > 1).any():
        even = ((f[:, 0] < f[:, 1]).astype(int) + (f[:, 1] < f[:, 2]) + (f[:, 2] < f[:, 0])) == 2
        npos = np.bincount(grp, weights=even, minlength=len(gcnt))
        mixed = (gcnt > 1) & (npos > 0) & (npos < gcnt)
        keep = np.zeros(len(f), bool)
        keep[first[~mixed]] = True
        fins = int(gcnt[mixed].sum())
        dups = int(len(f) - keep.sum() - fins)
        f = f[keep]
    for _ in range(50):
        if len(f) == 0:
            break
        _, eid, cnt, _, _ = _edge_table(f)
        ec = cnt[eid].reshape(3, -1).T
        flap = ((ec == 1).sum(axis=1) >= 2) & (ec > 2).any(axis=1)
        if not flap.any():
            break
        flaps += int(flap.sum())
        f = f[~flap]
    return f, dups, fins, flaps


def _split_nonmanifold(v: np.ndarray, f: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Separa vértices y aristas no manifold (piezas que solo se tocan en un punto o una arista).

    Las esquinas de los triángulos que comparten un vértice se agrupan si están unidas a través de
    aristas manifold; cada grupo distinto recibe su propio vértice (en la misma posición). Así dos
    cuerpos que se tocan a lo largo de una arista quedan como dos superficies cerradas.
    Devuelve (v, f, nº de vértices añadidos).
    """
    nf = len(f)
    if nf == 0:
        return v, f, 0
    p, q = _manifold_pairs(f)
    fi, ki = p % nf, p // nf                  # cara y ranura de arista (0: 0-1, 1: 1-2, 2: 2-0)
    fj, kj = q % nf, q // nf
    ai = f[fi, ki]
    aj = f[fj, kj]
    ci0, ci1 = fi * 3 + ki, fi * 3 + (ki + 1) % 3
    cj0, cj1 = fj * 3 + kj, fj * 3 + (kj + 1) % 3
    same = aj == ai
    u = np.concatenate([ci0, ci1])
    w = np.concatenate([np.where(same, cj0, cj1), np.where(same, cj1, cj0)])
    lab = _union_labels(nf * 3, u, w)
    keys, corner_new = np.unique(lab, return_inverse=True)
    corner_new = corner_new.reshape(-1)
    used = len(np.unique(f))
    if len(keys) <= used:
        return v, f, 0
    rep_corner = np.zeros(len(keys), np.int64)
    rep_corner[corner_new] = np.arange(nf * 3)
    nv = v[f.reshape(-1)[rep_corner]]
    nfaces = corner_new.reshape(nf, 3)
    return nv, nfaces, int(len(keys) - used)


def repair(v: np.ndarray, f: np.ndarray, report, post_simplify: bool = False) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Reparación controlada y registrada. No inventa geometría: no rellena agujeros.

    post_simplify=True: tras la simplificación por pieza no se sueldan vértices ni se separan pellizcos
    (unirían piezas vecinas que se tocan y deshacerían las comprobaciones hechas pieza a pieza).
    """
    actions = []
    ext = float(np.ptp(v, axis=0).max()) or 1.0
    merged = 0
    if not post_simplify:
        v, f, merged = weld(v, f, ext * 1e-7)
    if merged:
        actions.append(f"{merged} vértice(s) casi coincidentes soldados (tolerancia {ext * 1e-7:.3g} mm).")
    bad = degenerate_mask(v, f, (ext * 1e-9) ** 2)
    if bad.any():
        f = f[~bad]
        actions.append(f"{int(bad.sum())} triángulo(s) degenerado(s) eliminados.")
    f, dups, fins, flaps = _remove_fins_and_flaps(f)
    if dups:
        actions.append(f"{dups} triángulo(s) duplicado(s) eliminados.")
    if fins:
        actions.append(f"{fins} triángulo(s) superpuestos con orientación opuesta (aletas sin volumen) eliminados.")
    if flaps:
        actions.append(f"{flaps} triángulo(s) sueltos apoyados en aristas no manifold eliminados.")
    added = 0
    if not post_simplify:
        v, f, added = _split_nonmanifold(v, f)
    if added:
        actions.append(f"{added} vértice(s) no manifold separados (piezas que solo se tocaban en un punto o arista).")
    if len(f) and _edge_stats(f)[2]:
        f, flipped = _orient_consistently(f)
        if flipped:
            actions.append(f"{flipped} triángulo(s) reorientados para obtener normales coherentes.")
    if len(f):
        comp = face_components(f, len(v))
        info = _component_stats(v, f, comp)
        inward = np.array([c.closed and c.inconsistent_edges == 0 and c.signed_volume < 0 for c in info])
        if inward.any():
            sel = inward[comp]
            f[sel] = f[sel][:, ::-1]
            actions.append(f"{int(inward.sum())} componente(s) cerrado(s) con normales hacia dentro invertidos.")
    used = np.unique(f)
    if len(used) < len(v):
        remap = np.full(len(v), -1, np.int64)
        remap[used] = np.arange(len(used))
        v, f = v[used], remap[f]
    for a in actions:
        report.info(a)
    return v, f, actions


# ============================================================================ recursos y simplificación

def available_memory_mb() -> float:
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 2 ** 20
    except Exception:
        return 4096.0


def estimate(triangles: int, unify_max: int = 50_000) -> dict:
    per_tri = MEM_MB_PER_TRI_UNIFY if triangles <= unify_max else MEM_MB_PER_TRI
    return {"memoria_mb": round(BASE_MEM_MB + triangles * per_tri),
            "step_mb": round(triangles * STEP_KB_PER_TRI / 1024, 1),
            "tiempo_s": round(triangles * MS_PER_TRI / 1000, 1)}


def max_affordable_triangles(avail_mb: float, timeout_s: float, mem_factor: float = 0.7,
                             unify_max: int = 50_000) -> int:
    """Triángulos que caben en la memoria libre medida DENTRO del proceso de trabajo.

    La memoria base del proceso ya está ocupada (y descontada de la memoria libre) cuando se mide,
    así que solo se presupuesta el coste adicional por triángulo.
    """
    mem = mem_factor * avail_mb
    by_mem = mem / MEM_MB_PER_TRI_UNIFY
    if by_mem > unify_max:                     # por encima no se unen caras: coste por triángulo menor
        by_mem = max(unify_max, mem / MEM_MB_PER_TRI)
    by_time = 0.6 * timeout_s * 1000 / MS_PER_TRI
    return int(max(1000, min(by_mem, by_time)))


def simplify(v: np.ndarray, f: np.ndarray, target: int, report, agg: float = 7.0) -> tuple[np.ndarray, np.ndarray, dict]:
    """Reduce la malla a ≈target triángulos conservando la forma (decimación cuadrática)."""
    n0 = len(f)
    info = {"triangulos_antes": int(n0), "metodo": "fast-simplification (cuadrática)"}
    target = int(max(4, min(target, n0)))
    try:
        import fast_simplification
        # target_count (no una fracción recortada): el objetivo se respeta también por encima del 99 %
        v2, f2 = fast_simplification.simplify(np.ascontiguousarray(v, np.float64),
                                              np.ascontiguousarray(f, np.int64), target_count=target,
                                              agg=agg, verbose=False)
        v2, f2 = np.asarray(v2, np.float64), np.asarray(f2, np.int64)
    except Exception as e:  # sin la biblioteca: agrupación de vértices (menos fiel, siempre disponible)
        info["metodo"] = f"agrupación de vértices (fast-simplification no disponible: {e})"
        v2, f2 = _cluster_decimate(v, f, target)
    ext = float(np.ptp(v, axis=0).max()) or 1.0
    bb0 = np.array([v.min(0), v.max(0)])
    bb1 = np.array([v2.min(0), v2.max(0)]) if len(v2) else bb0
    vol0, vol1 = abs(_signed_volume(v, f)), abs(_signed_volume(v2, f2)) if len(f2) else 0.0
    info.update({"triangulos_despues": int(len(f2)),
                 "desviacion_caja_mm": round(float(np.abs(bb1 - bb0).max()), 6),
                 "desviacion_caja_relativa": round(float(np.abs(bb1 - bb0).max()) / ext, 6),
                 "cambio_volumen_pct": round(100 * (vol1 - vol0) / vol0, 3) if vol0 > 0 else None})
    return v2, f2, info


def _submesh(v: np.ndarray, f: np.ndarray, sel: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    fc = f[sel]
    used = np.unique(fc)                         # O(n log n) de la pieza, no del total de vértices
    return v[used], np.searchsorted(used, fc)


MAX_PIECES_AFTER_SPLIT = 4


def _simplify_checked(v: np.ndarray, f: np.ndarray, target: int, closed_in: bool, agg: float = 7.0) -> dict:
    """Simplifica una pieza y comprueba si conserva su topología.

    Válido: sin aristas no manifold, cerrada si lo era y como mucho MAX_PIECES_AFTER_SPLIT cuerpos
    (la decimación puede dejar dos cuerpos cerrados que se tocan en un vértice: se separan y siguen
    siendo sólidos).
    """
    v2, f2, _ = simplify(v, f, target, None, agg=agg)
    f2, _, fins, flaps = _remove_fins_and_flaps(f2)
    v2, f2, _ = _split_nonmanifold(v2, f2)
    o, nm, _ = _edge_stats(f2)
    pieces = len(np.unique(face_components(f2, len(v2)))) if len(f2) else 0
    good = (len(f2) > 0 and nm == 0 and (o == 0 or not closed_in)
            and pieces <= (MAX_PIECES_AFTER_SPLIT if closed_in else 1))
    return {"v": v2, "f": f2, "tris": int(len(f2)), "good": bool(good), "open": int(o), "nm": int(nm),
            "pieces": int(pieces), "fins": int(fins), "target": int(target), "agg": agg}


def simplify_by_component(v: np.ndarray, f: np.ndarray, target: int, cap: int,
                          report=None) -> tuple[np.ndarray, np.ndarray, dict]:
    """Simplifica cada pieza (componente conectado) por separado conservando su cierre.

    1. Reparto del objetivo entre piezas con peso n^0,75: las piezas pequeñas y finas (cables, placas)
       reciben proporcionalmente más triángulos, porque con muy pocos el decimador las aplasta en
       láminas dobles sin volumen.
    2. Cada pieza se simplifica y se comprueba: debe seguir siendo una sola pieza, sin aristas no
       manifold y cerrada si lo era.
    3. Las piezas que pierden el cierre se reintentan con el doble de triángulos mientras quepa en
       `cap` (límite duro de recursos). Si no es posible, se conserva el mejor intento y se informa.
    """
    t0 = time.time()
    n0 = len(f)
    comp = face_components(f, len(v))
    stats = _component_stats(v, f, comp)
    n = np.bincount(comp).astype(np.int64)
    k = len(n)
    cap = int(max(cap, target))
    w = n.astype(float) ** 0.75
    alloc = np.minimum(n, np.maximum(np.minimum(n, 64), np.floor(target * w / w.sum()))).astype(np.int64)
    order = np.argsort(comp, kind="stable")
    bounds = np.concatenate([[0], np.cumsum(n)])
    results: list[dict] = [{"v": v[:0], "f": f[:0], "tris": 0, "good": True, "target": 0} for _ in range(k)]
    keep = alloc >= n                            # piezas ya por debajo de su reparto: se copian en bloque
    if keep.any():
        kv, kf = _submesh(v, f, keep[comp])
        results[int(np.nonzero(keep)[0][0])] = {"v": kv, "f": kf, "tris": int(len(kf)), "good": True,
                                                "target": int(len(kf))}
    for c in np.nonzero(~keep)[0].tolist():
        vc, fc = _submesh(v, f, order[bounds[c]:bounds[c + 1]])
        r = _simplify_checked(vc, fc, int(alloc[c]), stats[c].closed)
        r["src"] = (vc, fc)
        results[c] = r
    used = sum(r["tris"] for r in results)
    retried = 0
    for c in sorted(range(k), key=lambda i: n[i]):          # primero las piezas baratas de salvar
        r = results[c]
        if r["good"] or "src" not in r:
            continue
        vc, fc = r["src"]
        # misma cantidad con otra agresividad, luego el doble, el cuádruple...; agg=5 se detiene sola
        # en el nivel que la forma admite (suele conservar el cierre de las piezas finas)
        plan = [(r["target"], 6.0)]
        t = r["target"] * 2
        while t < n[c]:
            plan += [(t, 7.0), (t, 6.0)]
            t *= 2
        plan.insert(min(len(plan), 3), (r["target"], 5.0))
        for t, agg in plan:
            if used - r["tris"] + min(t, n[c]) > cap:
                continue
            r2 = _simplify_checked(vc, fc, t, stats[c].closed, agg)
            retried += 1
            if r2["good"] and used - r["tris"] + r2["tris"] <= cap:
                r2["mas_triangulos"] = r2["tris"] > r["tris"]
                used += r2["tris"] - r["tris"]
                results[c] = r = r2
                break
    vs, fs_, off = [], [], 0
    for r in results:
        vs.append(r["v"])
        fs_.append(r["f"] + off)
        off += len(r["v"])
    v2 = np.concatenate(vs) if vs else v[:0]
    f2 = np.concatenate(fs_) if fs_ else f[:0]
    lost = [c for c, r in enumerate(results) if not r["good"]]
    extra = [c for c, r in enumerate(results) if r.get("mas_triangulos")]
    ext = float(np.ptp(v, axis=0).max()) or 1.0
    bb0 = np.array([v.min(0), v.max(0)])
    bb1 = np.array([v2.min(0), v2.max(0)]) if len(v2) else bb0
    vol0, vol1 = abs(_signed_volume(v, f)), (abs(_signed_volume(v2, f2)) if len(f2) else 0.0)
    method = "fast-simplification (cuadrática) por pieza"
    try:
        import fast_simplification  # noqa: F401
    except Exception as e:
        method = f"agrupación de vértices (fast-simplification no disponible: {e})"
    info = {"triangulos_antes": int(n0), "metodo": method, "piezas": int(k),
            "triangulos_despues": int(len(f2)), "limite_duro": int(cap),
            "piezas_con_mas_triangulos": len(extra), "piezas_sin_conservar_cierre": len(lost),
            "reintentos": retried, "tiempo_s": round(time.time() - t0, 2),
            "desviacion_caja_mm": round(float(np.abs(bb1 - bb0).max()), 6),
            "desviacion_caja_relativa": round(float(np.abs(bb1 - bb0).max()) / ext, 6),
            "cambio_volumen_pct": round(100 * (vol1 - vol0) / vol0, 3) if vol0 > 0 else None,
            "detalle_piezas": [{"triangulos_antes": int(n[c]), "reparto": int(alloc[c]),
                                "triangulos_despues": results[c]["tris"], "cerrada_antes": bool(stats[c].closed),
                                "topologia_conservada": bool(results[c]["good"]),
                                "cuerpos": results[c].get("pieces", 1),
                                "agresividad": results[c].get("agg")} for c in range(min(k, 50))]}
    return v2, f2, info


def _cluster_decimate(v, f, target):
    ext = np.ptp(v, axis=0)
    cells = max(4, int(np.sqrt(target / 2)))
    size = float(ext.max()) / cells or 1.0
    key = np.floor((v - v.min(0)) / size).astype(np.int64)
    _, rep, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    sums = np.zeros((len(rep), 3))
    np.add.at(sums, inv.reshape(-1), v)
    cnt = np.bincount(inv.reshape(-1))
    nv = sums / cnt[:, None]
    nf = inv.reshape(-1)[f]
    ok = (nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])
    nf = nf[ok]
    _, keep = np.unique(np.sort(nf, axis=1), axis=0, return_index=True)
    return nv, nf[np.sort(keep)]


# ============================================================================ construcción B-Rep

def _triangulation(v: np.ndarray, f: np.ndarray):
    from OCP.Poly import Poly_Triangulation, Poly_Triangle
    from OCP.gp import gp_Pnt
    pt = Poly_Triangulation(len(v), len(f), False)
    for i, p in enumerate(v.tolist(), 1):
        pt.SetNode(i, gp_Pnt(p[0], p[1], p[2]))
    for i, t in enumerate((f + 1).tolist(), 1):
        pt.SetTriangle(i, Poly_Triangle(t[0], t[1], t[2]))
    return pt


def build_component(v: np.ndarray, f: np.ndarray, info: ComponentInfo, name: str, options, report) -> tuple:
    """Devuelve (forma, tipo, detalle técnico). tipo ∈ {sólido, superficie, superficie no manifold}."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeShapeOnMesh, BRepBuilderAPI_MakeSolid
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Shell

    tech: dict = {"triangulos": int(len(f))}
    t0 = time.time()
    mk = BRepBuilderAPI_MakeShapeOnMesh(_triangulation(v, f))
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError(f"'{name}': BRepBuilderAPI_MakeShapeOnMesh no pudo construir las caras.")
    faces_shape = mk.Shape()
    builder = BRep_Builder()
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    exp = TopExp_Explorer(faces_shape, TopAbs_ShapeEnum.TopAbs_FACE)
    nfaces = 0
    while exp.More():
        builder.Add(shell, exp.Current())
        nfaces += 1
        exp.Next()
    if nfaces == 0:
        raise RuntimeError(f"'{name}': no se generó ninguna cara B-Rep.")
    tech["caras_construidas"] = nfaces
    tech["construccion_s"] = round(time.time() - t0, 2)

    want_solid = options.sew_mesh_to_solid and info.closed and not info.nonmanifold_edges and not info.inconsistent_edges
    shape, kind = shell, ("superficie no manifold" if info.nonmanifold_edges else "superficie")
    check_limit = getattr(options, "brep_check_max_faces", 60_000)
    if want_solid:
        shell.Closed(True)
        ms = BRepBuilderAPI_MakeSolid(shell)
        if ms.IsDone():
            solid = ms.Solid()
            if nfaces <= check_limit:
                fx = ShapeFix_Solid(solid)
                fx.Perform()
                solid = fx.Solid()
                valid = BRepCheck_Analyzer(solid).IsValid()
                tech["brepcheck_solido"] = bool(valid)
            else:
                valid = True        # topología ya verificada en la malla (cerrada, manifold, coherente)
                tech["brepcheck_solido"] = f"omitido (> {check_limit} caras); topología verificada en la malla"
            if valid:
                shape, kind = solid, "sólido"
            else:
                report.warn(f"'{name}': el sólido no supera la comprobación de OCCT; se exporta como superficie.")
        else:
            report.warn(f"'{name}': BRepBuilderAPI_MakeSolid falló; se exporta como superficie.")

    unify_max = getattr(options, "unify_max_triangles", 50_000)
    if getattr(options, "unify_coplanar", True) and len(f) <= unify_max:
        t1 = time.time()
        try:
            from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
            u = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
            u.Build()
            merged = u.Shape()
            n2 = _count(merged, TopAbs_ShapeEnum.TopAbs_FACE)
            if 0 < n2 < nfaces and BRepCheck_Analyzer(merged).IsValid():
                tech["caras_tras_unir_coplanares"] = n2
                shape = merged
            else:
                tech["caras_tras_unir_coplanares"] = nfaces
        except Exception as e:
            tech["union_coplanares_error"] = f"{type(e).__name__}: {e}"
        tech["union_coplanares_s"] = round(time.time() - t1, 2)
    elif getattr(options, "unify_coplanar", True):
        tech["union_coplanares"] = f"omitida (> {unify_max} triángulos)"
    tech["tipo"] = kind
    return shape, kind, tech


def _count(shape, kind) -> int:
    from OCP.TopExp import TopExp_Explorer
    exp = TopExp_Explorer(shape, kind)
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def mesh_to_parts(v_mm: np.ndarray, f: np.ndarray, name: str, options, report, budget: int,
                  progress=None, tech: dict | None = None) -> tuple[list, dict]:
    """Analiza, repara, simplifica (si procede) y construye las piezas B-Rep de una malla.

    Devuelve ([(nombre, forma, tipo)], diagnóstico técnico).
    """
    tech = tech if tech is not None else {}      # se rellena sobre la marcha: sobrevive a un fallo
    tech["nombre"] = name
    set_stage = getattr(report, "set_stage", lambda s: None)

    set_stage("análisis de malla")
    t0 = time.time()
    raw_vertices = len(v_mm)
    # Las costuras de UV/normales duplican vértices en la misma posición: sin soldarlos, cada isla de
    # textura parecería una pieza abierta. El diagnóstico describe la geometría real (ya soldada).
    ext = float(np.ptp(v_mm, axis=0).max()) if len(v_mm) else 1.0
    v_mm, f, merged = weld(v_mm, f, (ext or 1.0) * 1e-7)
    d0 = analyze(v_mm, f, merged)
    tech["vertices_leidos"] = int(raw_vertices)
    tech["malla_original"] = d0.to_dict()
    tech["analisis_s"] = round(time.time() - t0, 2)
    report.info(f"Malla '{name}': {d0.vertices:,} vértices, {d0.triangles:,} triángulos, "
                f"{len(d0.components)} componente(s), estado: {d0.state}.")
    if merged:
        report.info(f"'{name}': {merged:,} vértice(s) repetidos en costuras de textura o normales unidos "
                    f"(mismas coordenadas).")
    if d0.triangles == 0:
        raise ValueError(f"'{name}': la malla no contiene triángulos.")

    if getattr(options, "mesh_repair", True):
        set_stage("reparación de malla")
        v_mm, f, actions = repair(v_mm, f, report)
        tech["reparaciones"] = actions
    if len(f) == 0:
        raise ValueError(f"'{name}': tras eliminar triángulos degenerados no queda geometría.")

    set_stage("estimación de recursos")
    est = estimate(len(f))
    tech["estimacion_inicial"] = est
    mode = getattr(options, "mesh_simplify", "auto")
    user_target = int(getattr(options, "mesh_target_triangles", 100_000))
    target = min(user_target, budget)
    limited = getattr(options, "resource_limited_target", False) or target < user_target
    reason = (getattr(options, "resource_limit_reason", "limitado por la memoria libre y el tiempo máximo")
              if limited else "configurado en Opciones")
    if len(f) > target and mode != "off":
        set_stage("simplificación de malla")
        if progress:
            progress(0.0, f"Simplificando malla: {len(f):,} → {target:,} triángulos")
        cap = max(target, min(int(getattr(options, "hard_triangle_budget", 0) or target),
                              max(int(target * 1.5), target + 5_000)))
        v_mm, f, sinfo = simplify_by_component(v_mm, f, target, cap, report)
        sinfo.update({"objetivo": target, "motivo_objetivo": reason, "objetivo_usuario": user_target,
                      "limite_recursos": budget})
        tech["simplificacion"] = sinfo
        report.warn(f"Malla '{name}' simplificada de {sinfo['triangulos_antes']:,} a {sinfo['triangulos_despues']:,} "
                    f"triángulos (objetivo {target:,}, {reason}); desviación de la caja: "
                    f"{sinfo['desviacion_caja_mm']:.3g} mm.")
        report.loss("Detalle geométrico reducido por simplificación de la malla (opción configurable).")
        if sinfo["piezas_con_mas_triangulos"]:
            report.info(f"'{name}': {sinfo['piezas_con_mas_triangulos']} pieza(s) finas recibieron más triángulos "
                        f"para seguir cerradas.")
        if sinfo["piezas_sin_conservar_cierre"]:
            report.warn(f"'{name}': {sinfo['piezas_sin_conservar_cierre']} pieza(s) no se pudieron simplificar "
                        f"hasta {target:,} triángulos sin perder el cierre; se exportan como superficies. Con más "
                        f"memoria libre o un objetivo mayor se conservan como sólidos.")
        if getattr(options, "mesh_repair", True):
            # sin soldar ni separar: cada pieza ya está validada y no debe fusionarse con sus vecinas
            v_mm, f, _ = repair(v_mm, f, report, post_simplify=True)
    elif len(f) > budget and mode == "off" and len(f) <= getattr(options, "hard_triangle_budget", 0):
        e = estimate(len(f))
        report.warn(f"Malla '{name}': {len(f):,} triángulos sin simplificar (opción desactivada); uso de memoria elevado "
                    f"previsto (≈{e['memoria_mb']:,} MB). Cierre otras aplicaciones si la conversión se ralentiza.")
    elif len(f) > budget:
        e = estimate(len(f))
        raise ValueError(
            f"La malla '{name}' tiene {len(f):,} triángulos; un B-Rep facetado así necesitaría ≈{e['memoria_mb']:,} MB "
            f"de memoria, ≈{e['tiempo_s']:.0f} s y generaría un STEP de ≈{e['step_mb']:.0f} MB, por encima de los "
            f"recursos disponibles (límite actual {budget:,} triángulos). Active la simplificación de malla o "
            f"reduzca la malla antes de convertir.")

    set_stage("análisis de malla")
    d1 = analyze(v_mm, f)
    tech["malla_final"] = d1.to_dict()
    tech["estimacion_final"] = estimate(len(f))

    set_stage("construcción B-Rep")
    comp = face_components(f, len(v_mm))
    parts = []
    built = {"sólido": 0, "superficie": 0, "superficie no manifold": 0}
    tech["componentes"] = []
    ncomp = int(comp.max()) + 1 if len(comp) else 0
    for c in range(ncomp):
        sel = comp == c
        fc = f[sel]
        used = np.unique(fc)
        remap = np.full(len(v_mm), -1, np.int64)
        remap[used] = np.arange(len(used))
        vc, fcc = v_mm[used], remap[fc]
        info = d1.components[c]
        cname = name if ncomp == 1 else f"{name}_{c + 1}"
        if progress:
            progress(c / max(ncomp, 1), f"Construyendo B-Rep facetado: {cname}")
        shape, kind, ctech = build_component(vc, fcc, info, cname, options, report)
        ctech["nombre"] = cname
        tech["componentes"].append(ctech)
        built[kind] += 1
        parts.append((cname, shape, kind))
    tech["resultado"] = built
    report.info(f"B-Rep facetado de '{name}': {built['sólido']} sólido(s), {built['superficie']} superficie(s) abierta(s), "
                f"{built['superficie no manifold']} superficie(s) no manifold.")
    if built["superficie"] or built["superficie no manifold"]:
        report.warn(f"'{name}': {built['superficie'] + built['superficie no manifold']} componente(s) no cerrados o "
                    "no manifold se exportan como superficies (shell), no como sólidos.")
    return parts, tech
