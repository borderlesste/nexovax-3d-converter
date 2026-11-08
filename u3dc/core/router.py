"""Selección dinámica de rutas de conversión y matriz de compatibilidad.

El grafo tiene como nodos los formatos y las tres representaciones intermedias
(scene, cad, bim). Cada arista declara su fidelidad geométrica y las pérdidas que
introduce. La ruta elegida minimiza primero la pérdida geométrica y después el
número de pasos, de modo que nunca se pasa por una malla si existe una ruta B-Rep.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .formats import FORMATS, FORMAT_ORDER
from .report import Fidelity


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str                 # read | write | transform
    fidelity: Fidelity
    description: str
    losses: tuple = ()


def _r(fmt, rep):
    return Edge(fmt, rep, "read", Fidelity.DIRECT, f"Importar {FORMATS[fmt].name}")


EDGES: list[Edge] = [
    _r("gltf", "scene"), _r("glb", "scene"), _r("obj", "scene"), _r("fbx", "scene"), _r("stl", "scene"),
    _r("step", "cad"), _r("iges", "cad"), _r("ifc", "bim"),
    # escritura
    Edge("scene", "gltf", "write", Fidelity.DIRECT, "Exportar glTF"),
    Edge("scene", "glb", "write", Fidelity.DIRECT, "Exportar GLB"),
    Edge("scene", "fbx", "write", Fidelity.DIRECT, "Exportar FBX binario 7.4",
         ("Materiales PBR convertidos a modelo Phong de FBX (aproximación visual)",)),
    Edge("scene", "obj", "write", Fidelity.DIRECT, "Exportar OBJ + MTL",
         ("Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas",)),
    Edge("scene", "stl", "write", Fidelity.DIRECT, "Exportar STL",
         ("STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía",)),
    Edge("cad", "step", "write", Fidelity.DIRECT, "Exportar STEP (B-Rep)"),
    Edge("cad", "iges", "write", Fidelity.DIRECT, "Exportar IGES (B-Rep, entidades 186/514)",
         ("IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes",)),
    Edge("bim", "ifc", "write", Fidelity.DIRECT, "Exportar IFC"),
    # transformaciones entre representaciones
    Edge("cad", "scene", "transform", Fidelity.TESSELLATED, "Teselación B-Rep → triángulos (OCCT BRepMesh)",
         ("Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada",)),
    Edge("bim", "scene", "transform", Fidelity.TESSELLATED, "Teselación IFC → triángulos (IfcOpenShell)",
         ("Geometría IFC aproximada por triángulos",
          "Relaciones IFC (conexiones, sistemas, fases, aberturas como entidades) no representables en mallas")),
    Edge("bim", "cad", "transform", Fidelity.DIRECT, "Geometría IFC → B-Rep exacto (IfcOpenShell + OCCT)",
         ("Datos BIM (propiedades, clasificación, relaciones, estructura espacial) no representables en CAD",)),
    Edge("scene", "cad", "transform", Fidelity.APPROXIMATE, "Malla → B-Rep facetado (OCCT, cosido de caras)",
         ("Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico",)),
    Edge("scene", "bim", "transform", Fidelity.LIMITED, "Malla → IFC genérico (IfcBuildingElementProxy)",
         ("No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy "
          "dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta)",)),
]

# Capacidades semánticas por formato (qué información puede transportar)
CAPS = {
    "gltf": {"Nombres", "Jerarquía", "Materiales", "Texturas", "UV", "Metadatos", "Unidades", "Instancias"},
    "glb": {"Nombres", "Jerarquía", "Materiales", "Texturas", "UV", "Metadatos", "Unidades", "Instancias"},
    "fbx": {"Nombres", "Jerarquía", "Materiales", "Texturas", "UV", "Unidades", "Instancias"},
    "obj": {"Nombres", "Materiales", "Texturas", "UV"},
    "stl": set(),
    "step": {"Nombres", "Colores", "Unidades", "B-Rep exacto", "Jerarquía"},
    "iges": {"Nombres", "Colores", "Unidades", "B-Rep exacto"},
    "ifc": {"Nombres", "Jerarquía", "Materiales", "Metadatos", "Unidades", "Semántica BIM", "B-Rep exacto"},
}
# "Materiales" en CAD se expresa como colores
_ALIASES = {"Materiales": {"Colores"}, "Colores": {"Materiales"}}
# Pérdidas semánticas que se notifican siempre en la conversión (el resto se detecta al leer)
ALWAYS_REPORTED = {"Semántica BIM", "Metadatos", "Texturas", "UV"}


@dataclass
class Route:
    source: str
    target: str
    edges: list = field(default_factory=list)

    @property
    def fidelity(self) -> Fidelity:
        return max((e.fidelity for e in self.edges), default=Fidelity.UNSUPPORTED)

    @property
    def steps(self) -> list[str]:
        return [e.description for e in self.edges]

    @property
    def representations(self) -> list[str]:
        return [e.dst for e in self.edges[:-1]]

    def losses(self) -> list[str]:
        out = []
        for e in self.edges:
            for l in e.losses:
                if l not in out:
                    out.append(l)
        for l in semantic_losses(self.source, self.target):
            if l not in out:
                out.append(l)
        return out


def semantic_losses(src: str, dst: str) -> list[str]:
    s, d = CAPS[src], CAPS[dst]
    lost = []
    for cap in sorted(s):
        if cap in d or any(a in d for a in _ALIASES.get(cap, ())):
            continue
        if cap == "B-Rep exacto":
            continue          # cubierto por la fidelidad geométrica de la ruta
        if cap == "unidades":
            lost.append(f"{FORMATS[dst].name} no declara unidades: se escriben en la unidad indicada en las opciones")
            continue
        lost.append(f"{cap} de {FORMATS[src].name}: no representable en {FORMATS[dst].name}")
    return lost


def runtime_losses(route: "Route") -> list[str]:
    """Pérdidas a notificar en una conversión concreta: inherentes a la ruta + semánticas relevantes."""
    out = []
    for e in route.edges:
        for l in e.losses:
            if l not in out:
                out.append(l)
    s, d = CAPS[route.source], CAPS[route.target]
    for cap in sorted(s & ALWAYS_REPORTED) if route.target != "stl" else []:
        if cap in d or any(a in d for a in _ALIASES.get(cap, ())):
            continue
        msg = f"{cap} de {FORMATS[route.source].name}: no representable en {FORMATS[route.target].name}"
        if msg not in out:
            out.append(msg)
    return out


def semantic_level(src: str, dst: str) -> str:
    s, d = CAPS[src], CAPS[dst]
    relevant = {c for c in s if c not in ("B-Rep exacto",)}
    kept = {c for c in relevant if c in d or any(a in d for a in _ALIASES.get(c, ()))}
    if not relevant or kept == relevant:
        return "Completa"
    if not kept or kept <= {"unidades"}:
        return "Solo geometría"
    return "Parcial"


def find_route(src: str, dst: str) -> Route | None:
    """Dijkstra: coste = (fidelidad máxima, nº de pasos)."""
    adj: dict[str, list[Edge]] = {}
    for e in EDGES:
        adj.setdefault(e.src, []).append(e)
    # estado: (peor fidelidad, pasos, nodo, aristas)
    heap = [(0, 0, src, [])]
    best: dict[str, tuple] = {}
    while heap:
        worst, steps, node, path = heapq.heappop(heap)
        if node == dst and path:
            return Route(src, dst, path)
        key = node
        if key in best and best[key] <= (worst, steps):
            continue
        best[key] = (worst, steps)
        for e in adj.get(node, []):
            # no atravesar formatos de archivo intermedios: solo representaciones
            if e.kind == "write" and e.dst != dst:
                continue
            if any(p.dst == e.dst for p in path):
                continue
            heapq.heappush(heap, (max(worst, int(e.fidelity)), steps + 1, e.dst, path + [e]))
    return None


@dataclass
class MatrixCell:
    source: str
    target: str
    fidelity: Fidelity
    semantic: str
    route: list
    losses: list
    note: str = ""


NOTES = {
    ("stl", "step"): "Válida como B-Rep facetado. No recomendable para mallas de más de ~200.000 triángulos (límite configurable).",
    ("stl", "iges"): "Válida como superficies facetadas. No recomendable para mallas muy densas.",
    ("obj", "step"): "Válida como B-Rep facetado; se pierden texturas y UV.",
    ("obj", "iges"): "Válida como superficies facetadas; se pierden texturas y UV.",
    ("fbx", "step"): "Solo geometría estática; animaciones, huesos y deformaciones se ignoran.",
    ("glb", "step"): "Válida como B-Rep facetado.",
    ("gltf", "step"): "Válida como B-Rep facetado.",
    ("step", "ifc"): "La geometría se tesela y se crean entidades genéricas IfcBuildingElementProxy.",
    ("iges", "ifc"): "La geometría se tesela y se crean entidades genéricas IfcBuildingElementProxy.",
    ("ifc", "step"): "Geometría B-Rep exacta cuando la define IFC (extrusiones, B-Rep); la información BIM se pierde.",
    ("ifc", "iges"): "Geometría B-Rep exacta; la información BIM se pierde.",
    ("iges", "step"): "Conversión B-Rep directa; superficies sueltas se exportan como tales.",
    ("step", "iges"): "Conversión B-Rep directa.",
}


def compatibility_matrix() -> list[MatrixCell]:
    cells = []
    for s in FORMAT_ORDER:
        for d in FORMAT_ORDER:
            r = find_route(s, d)
            if r is None:
                cells.append(MatrixCell(s, d, Fidelity.UNSUPPORTED, "—", [], [], "Sin ruta técnica válida"))
                continue
            cells.append(MatrixCell(s, d, r.fidelity, semantic_level(s, d), r.steps, r.losses(),
                                    NOTES.get((s, d), "")))
    return cells
