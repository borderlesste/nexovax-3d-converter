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

# Coste medido (OCCT 7.8/8.0, Windows 11, esfera cerrada): por triángulo de B-Rep facetado
MEM_MB_PER_TRI = 0.0135          # memoria máxima del proceso (≈2,15 GB para 150 000 triángulos)
STEP_KB_PER_TRI = 2.5            # tamaño del STEP resultante
MS_PER_TRI = 1.2                 # construcción + transferencia + escritura + relectura de validación
BASE_MEM_MB = 350.0


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
    """Etiqueta de componente conectado (por vértices compartidos) de cada triángulo."""
    if len(f) == 0:
        return np.zeros(0, np.int64)
    lab = np.arange(n_vertices, dtype=np.int64)
    for _ in range(10_000):
        m = np.minimum(np.minimum(lab[f[:, 0]], lab[f[:, 1]]), lab[f[:, 2]])
        new = lab.copy()
        for k in range(3):
            np.minimum.at(new, f[:, k], m)
        new = new[new]                     # salto de punteros
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    _, comp = np.unique(lab[f[:, 0]], return_inverse=True)
    return comp.reshape(-1)


def _edge_stats(f: np.ndarray) -> tuple[int, int, int]:
    """(aristas abiertas, aristas no manifold, aristas manifold con orientación incoherente)."""
    if len(f) == 0:
        return 0, 0, 0
    d = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    und = np.sort(d, axis=1)
    _, inv, cnt = np.unique(und, axis=0, return_inverse=True, return_counts=True)
    open_e = int(np.count_nonzero(cnt == 1))
    nonman = int(np.count_nonzero(cnt > 2))
    # en una arista manifold coherente, las dos apariciones van en sentidos opuestos
    _, dcnt = np.unique(d, axis=0, return_counts=True)
    inconsistent = int(np.count_nonzero(dcnt == 2))
    return open_e, nonman, inconsistent


def _signed_volume(v: np.ndarray, f: np.ndarray) -> float:
    tri = v[f]
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def analyze(v: np.ndarray, f: np.ndarray, raw_vertex_count: int | None = None) -> MeshDiagnostics:
    d = MeshDiagnostics(vertices=int(len(v)), triangles=int(len(f)))
    if raw_vertex_count is not None:
        d.duplicate_vertices = max(0, int(raw_vertex_count - len(v)))
    if len(f) == 0:
        return d
    ext = float(np.ptp(v, axis=0).max()) or 1.0
    d.bbox_mm = [v.min(axis=0).round(6).tolist(), v.max(axis=0).round(6).tolist()]
    d.degenerate_triangles = int(degenerate_mask(v, f, (ext * 1e-9) ** 2).sum())
    d.duplicate_triangles = int(len(f) - len(np.unique(np.sort(f, axis=1), axis=0)))
    comp = face_components(f, len(v))
    for c in range(int(comp.max()) + 1 if len(comp) else 0):
        fc = f[comp == c]
        o, n, i = _edge_stats(fc)
        d.components.append(ComponentInfo(triangles=int(len(fc)), closed=(o == 0 and n == 0), open_edges=o,
                                          nonmanifold_edges=n, inconsistent_edges=i,
                                          signed_volume=round(_signed_volume(v, fc), 6)))
    return d


# ============================================================================ reparación

def _orient_consistently(f: np.ndarray) -> tuple[np.ndarray, int]:
    """Invierte triángulos para que cada arista manifold se recorra en sentidos opuestos (BFS)."""
    nf = len(f)
    d = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    owner = np.tile(np.arange(nf), 3)
    und = np.sort(d, axis=1)
    order = np.lexsort((und[:, 1], und[:, 0]))
    und_s, d_s, own_s = und[order], d[order], owner[order]
    same_next = np.all(und_s[1:] == und_s[:-1], axis=1)
    # solo aristas con exactamente dos apariciones
    idx = np.nonzero(same_next)[0]
    if len(idx):
        prev_same = np.concatenate([[False], same_next[:-1]])
        next2 = np.concatenate([same_next[1:], [False]])
        idx = idx[~prev_same[idx] & ~next2[idx]]
    fa, fb = own_s[idx], own_s[idx + 1]
    concordant = np.all(d_s[idx] == d_s[idx + 1], axis=1)        # mismo sentido ⇒ hay que invertir uno
    adj: list[list[tuple[int, bool]]] = [[] for _ in range(nf)]
    for a, b, cflag in zip(fa.tolist(), fb.tolist(), concordant.tolist()):
        adj[a].append((b, cflag))
        adj[b].append((a, cflag))
    flip = np.zeros(nf, bool)
    seen = np.zeros(nf, bool)
    for s in range(nf):
        if seen[s]:
            continue
        seen[s] = True
        stack = [s]
        while stack:
            x = stack.pop()
            for y, cflag in adj[x]:
                if not seen[y]:
                    seen[y] = True
                    flip[y] = flip[x] ^ cflag
                    stack.append(y)
    out = f.copy()
    out[flip] = out[flip][:, ::-1]
    return out, int(flip.sum())


def repair(v: np.ndarray, f: np.ndarray, report) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Reparación controlada y registrada. No inventa geometría: no rellena agujeros."""
    actions = []
    ext = float(np.ptp(v, axis=0).max()) or 1.0
    v, f, merged = weld(v, f, ext * 1e-7)
    if merged:
        actions.append(f"{merged} vértice(s) casi coincidentes soldados (tolerancia {ext * 1e-7:.3g} mm).")
    bad = degenerate_mask(v, f, (ext * 1e-9) ** 2)
    if bad.any():
        f = f[~bad]
        actions.append(f"{int(bad.sum())} triángulo(s) degenerado(s) eliminados.")
    _, keep = np.unique(np.sort(f, axis=1), axis=0, return_index=True)
    if len(keep) < len(f):
        actions.append(f"{len(f) - len(keep)} triángulo(s) duplicado(s) eliminados.")
        f = f[np.sort(keep)]
    if _edge_stats(f)[2]:
        f, flipped = _orient_consistently(f)
        if flipped:
            actions.append(f"{flipped} triángulo(s) reorientados para obtener normales coherentes.")
    comp = face_components(f, len(v))
    outward = 0
    for c in range(int(comp.max()) + 1 if len(comp) else 0):
        sel = comp == c
        o, n, _ = _edge_stats(f[sel])
        if o == 0 and n == 0 and _signed_volume(v, f[sel]) < 0:
            f[sel] = f[sel][:, ::-1]
            outward += 1
    if outward:
        actions.append(f"{outward} componente(s) cerrado(s) con normales hacia dentro invertidos.")
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


def estimate(triangles: int) -> dict:
    return {"memoria_mb": round(BASE_MEM_MB + triangles * MEM_MB_PER_TRI),
            "step_mb": round(triangles * STEP_KB_PER_TRI / 1024, 1),
            "tiempo_s": round(triangles * MS_PER_TRI / 1000, 1)}


def max_affordable_triangles(avail_mb: float, timeout_s: float, mem_factor: float = 0.7) -> int:
    by_mem = (mem_factor * avail_mb - BASE_MEM_MB) / MEM_MB_PER_TRI
    by_time = 0.6 * timeout_s * 1000 / MS_PER_TRI
    return int(max(1000, min(by_mem, by_time)))


def simplify(v: np.ndarray, f: np.ndarray, target: int, report) -> tuple[np.ndarray, np.ndarray, dict]:
    """Reduce la malla a ≈target triángulos conservando la forma (decimación cuadrática)."""
    n0 = len(f)
    info = {"triangulos_antes": int(n0), "metodo": "fast-simplification (cuadrática)"}
    reduction = float(np.clip(1.0 - target / max(n0, 1), 0.0, 0.99))
    try:
        import fast_simplification
        v2, f2 = fast_simplification.simplify(np.ascontiguousarray(v, np.float64),
                                              np.ascontiguousarray(f, np.int64), target_reduction=reduction,
                                              agg=7, verbose=False)
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
    d0 = analyze(v_mm, f, raw_vertices)
    tech["malla_original"] = d0.to_dict()
    tech["analisis_s"] = round(time.time() - t0, 2)
    report.info(f"Malla '{name}': {d0.vertices:,} vértices, {d0.triangles:,} triángulos, "
                f"{len(d0.components)} componente(s), estado: {d0.state}.")
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
        v_mm, f, sinfo = simplify(v_mm, f, target, report)
        sinfo.update({"objetivo": target, "motivo_objetivo": reason, "objetivo_usuario": user_target,
                      "limite_recursos": budget})
        tech["simplificacion"] = sinfo
        report.warn(f"Malla '{name}' simplificada de {sinfo['triangulos_antes']:,} a {sinfo['triangulos_despues']:,} "
                    f"triángulos (objetivo {target:,}, {reason}); desviación de la caja: "
                    f"{sinfo['desviacion_caja_mm']:.3g} mm.")
        report.loss("Detalle geométrico reducido por simplificación de la malla (opción configurable).")
        if getattr(options, "mesh_repair", True):
            v_mm, f, _ = repair(v_mm, f, report)
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
