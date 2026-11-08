"""SceneModel: representación de escena basada en mallas.

Convenciones canónicas internas (todas las importaciones normalizan a ellas):
  * Unidades: metros.
  * Ejes: diestro, Z arriba (igual que IFC/STEP).
Los exportadores convierten a la convención del formato destino y lo registran.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import numpy as np


@dataclass
class Texture:
    name: str
    data: bytes                      # contenido del archivo de imagen (PNG/JPEG)
    mime: str = "image/png"

    @property
    def extension(self) -> str:
        return ".jpg" if self.mime in ("image/jpeg", "image/jpg") else ".png"


@dataclass
class Material:
    name: str
    base_color: tuple = (0.8, 0.8, 0.8, 1.0)   # RGBA lineal 0..1
    metallic: float = 0.0
    roughness: float = 0.8
    base_color_texture: int | None = None     # índice en SceneModel.textures
    double_sided: bool = False


@dataclass
class Mesh:
    name: str
    vertices: np.ndarray                     # (N,3) float64
    faces: np.ndarray                        # (M,3) int64 — triángulos
    normals: np.ndarray | None = None        # (N,3) por vértice
    uvs: np.ndarray | None = None            # (N,2)
    material: int | None = None              # índice en SceneModel.materials

    def __post_init__(self):
        self.vertices = np.ascontiguousarray(self.vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.ascontiguousarray(self.faces, dtype=np.int64).reshape(-1, 3)
        if self.normals is not None:
            self.normals = np.ascontiguousarray(self.normals, dtype=np.float64).reshape(-1, 3)
            if len(self.normals) != len(self.vertices):
                self.normals = None
        if self.uvs is not None:
            self.uvs = np.ascontiguousarray(self.uvs, dtype=np.float64).reshape(-1, 2)
            if len(self.uvs) != len(self.vertices):
                self.uvs = None

    @property
    def triangle_count(self) -> int:
        return int(len(self.faces))

    def copy(self) -> "Mesh":
        return Mesh(self.name, self.vertices.copy(), self.faces.copy(),
                    None if self.normals is None else self.normals.copy(),
                    None if self.uvs is None else self.uvs.copy(), self.material)


@dataclass
class SceneNode:
    name: str
    matrix: np.ndarray = field(default_factory=lambda: np.eye(4))   # local → padre
    meshes: list = field(default_factory=list)                       # índices en SceneModel.meshes
    children: list = field(default_factory=list)                     # índices en SceneModel.nodes
    properties: dict = field(default_factory=dict)                   # metadatos (p. ej. psets IFC)
    kind: str = ""                                                   # p. ej. clase IFC

    def __post_init__(self):
        self.matrix = np.asarray(self.matrix, dtype=np.float64).reshape(4, 4)


@dataclass
class SceneModel:
    nodes: list = field(default_factory=list)
    roots: list = field(default_factory=list)
    meshes: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    textures: list = field(default_factory=list)
    name: str = "Escena"
    metadata: dict = field(default_factory=dict)
    # información de lo que se ignoró o no pudo representarse al importar
    ignored: list = field(default_factory=list)

    # ------------------------------------------------------------ construcción
    def add_node(self, node: SceneNode, parent: int | None = None) -> int:
        self.nodes.append(node)
        idx = len(self.nodes) - 1
        if parent is None:
            self.roots.append(idx)
        else:
            self.nodes[parent].children.append(idx)
        return idx

    def add_mesh(self, mesh: Mesh) -> int:
        self.meshes.append(mesh)
        return len(self.meshes) - 1

    def add_material(self, mat: Material) -> int:
        self.materials.append(mat)
        return len(self.materials) - 1

    # ---------------------------------------------------------------- consulta
    def iter_nodes(self) -> Iterator[tuple[int, np.ndarray, int | None]]:
        """Recorre (índice, matriz mundial, padre) en profundidad."""
        stack = [(r, np.eye(4), None) for r in reversed(self.roots)]
        seen = set()
        while stack:
            idx, parent_m, parent = stack.pop()
            if idx in seen:          # protección ante ciclos
                continue
            seen.add(idx)
            node = self.nodes[idx]
            world = parent_m @ node.matrix
            yield idx, world, parent
            for c in reversed(node.children):
                stack.append((c, world, idx))

    def iter_world_meshes(self) -> Iterator[tuple[SceneNode, Mesh, np.ndarray]]:
        for idx, world, _ in self.iter_nodes():
            node = self.nodes[idx]
            for mi in node.meshes:
                yield node, self.meshes[mi], world

    def triangle_count(self) -> int:
        return sum(m.triangle_count for _, m, _ in self.iter_world_meshes())

    def mesh_node_count(self) -> int:
        return sum(1 for i, _, _ in self.iter_nodes() if self.nodes[i].meshes)

    def bounds(self) -> np.ndarray | None:
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        found = False
        for _, mesh, world in self.iter_world_meshes():
            if len(mesh.vertices) == 0:
                continue
            v = transform_points(mesh.vertices, world)
            lo = np.minimum(lo, v.min(axis=0))
            hi = np.maximum(hi, v.max(axis=0))
            found = True
        return np.array([lo, hi]) if found else None

    # ------------------------------------------------------------ transformar
    def apply_root_transform(self, m: np.ndarray) -> None:
        for r in self.roots:
            self.nodes[r].matrix = m @ self.nodes[r].matrix

    def scaled_copy_flat(self) -> list[tuple[str, np.ndarray, np.ndarray, int | None, np.ndarray | None, np.ndarray | None]]:
        """Lista (nombre, vértices mundo, caras, material, normales mundo, uvs) por instancia de malla."""
        out = []
        for node, mesh, world in self.iter_world_meshes():
            v = transform_points(mesh.vertices, world)
            n = None
            if mesh.normals is not None:
                n = transform_normals(mesh.normals, world)
            f = mesh.faces
            if np.linalg.det(world[:3, :3]) < 0:   # transformación espejo: invertir orden
                f = f[:, ::-1]
            name = node.name if len(node.meshes) == 1 else f"{node.name}_{mesh.name}"
            out.append((name, v, f, mesh.material, n, mesh.uvs))
        return out


# --------------------------------------------------------------------- utilidades

def transform_points(v: np.ndarray, m: np.ndarray) -> np.ndarray:
    if np.allclose(m, np.eye(4)):
        return v.copy()
    return v @ m[:3, :3].T + m[:3, 3]


def transform_normals(n: np.ndarray, m: np.ndarray) -> np.ndarray:
    a = m[:3, :3]
    try:
        nm = np.linalg.inv(a).T
    except np.linalg.LinAlgError:
        return n.copy()
    r = n @ nm.T
    ln = np.linalg.norm(r, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    return r / ln


def axis_matrix(src_up: str, dst_up: str) -> np.ndarray:
    """Matriz de rotación para pasar de un sistema 'Y' arriba a 'Z' arriba o viceversa (diestro)."""
    m = np.eye(4)
    if src_up == dst_up:
        return m
    if src_up == "Y" and dst_up == "Z":
        # (x, y, z) -> (x, -z, y)
        m[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    elif src_up == "Z" and dst_up == "Y":
        # (x, y, z) -> (x, z, -y)
        m[:3, :3] = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]
    else:
        raise ValueError(f"Ejes no soportados: {src_up}->{dst_up}")
    return m


def scale_matrix(s: float) -> np.ndarray:
    m = np.eye(4)
    m[0, 0] = m[1, 1] = m[2, 2] = s
    return m


def compute_vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    n = np.zeros_like(vertices)
    if len(faces) == 0:
        return n
    tri = vertices[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(n, faces[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    return n / ln


def mesh_quality(vertices: np.ndarray, faces: np.ndarray) -> dict:
    """Estadísticas de calidad: triángulos degenerados y aristas abiertas/no manifold."""
    if len(faces) == 0:
        return {"degenerate": 0, "open_edges": 0, "nonmanifold_edges": 0, "closed": False}
    tri = vertices[faces]
    area2 = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    scale = float(np.ptp(vertices, axis=0).max()) if len(vertices) else 1.0
    degenerate = int(np.count_nonzero(area2 <= (scale * 1e-9) ** 2))
    # soldar vértices coincidentes para analizar la topología
    q = np.round(vertices / max(scale * 1e-7, 1e-12)).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    f = inv.reshape(-1)[faces]
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    open_edges = int(np.count_nonzero(counts == 1))
    nonmanifold = int(np.count_nonzero(counts > 2))
    return {"degenerate": degenerate, "open_edges": open_edges,
            "nonmanifold_edges": nonmanifold, "closed": open_edges == 0 and nonmanifold == 0}


def merge_by_material(scene: "SceneModel") -> "SceneModel":
    """Fusiona todas las instancias que comparten material en un único objeto (coordenadas mundo).
    Reduce el número de objetos/draw calls; se pierde la jerarquía y los nombres individuales."""
    out = SceneModel(name=scene.name, materials=list(scene.materials), textures=list(scene.textures),
                     metadata=dict(scene.metadata))
    groups: dict = {}
    for node, mesh, world in scene.iter_world_meshes():
        groups.setdefault(mesh.material, []).append((mesh, world))
    for mat, items in groups.items():
        vs, fs, ns, uvs = [], [], [], []
        off = 0
        has_n = all(m.normals is not None for m, _ in items)
        has_uv = all(m.uvs is not None for m, _ in items)
        for mesh, world in items:
            v = transform_points(mesh.vertices, world)
            f = mesh.faces[:, ::-1] if np.linalg.det(world[:3, :3]) < 0 else mesh.faces
            vs.append(v)
            fs.append(f + off)
            if has_n:
                ns.append(transform_normals(mesh.normals, world))
            if has_uv:
                uvs.append(mesh.uvs)
            off += len(v)
        name = scene.materials[mat].name if mat is not None and mat < len(scene.materials) else "sin_material"
        mi = out.add_mesh(Mesh(name=name, vertices=np.concatenate(vs), faces=np.concatenate(fs),
                               normals=np.concatenate(ns) if has_n else None,
                               uvs=np.concatenate(uvs) if has_uv else None, material=mat))
        out.add_node(SceneNode(name=name, meshes=[mi]))
    return out
