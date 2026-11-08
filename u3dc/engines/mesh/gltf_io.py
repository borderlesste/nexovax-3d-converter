"""glTF 2.0 / GLB: lectura (trimesh) y escritura (implementación propia).

La escritura propia permite controlar instancias, jerarquía, extras (metadatos IFC),
materiales PBR y texturas, tanto en .gltf (+ .bin + imágenes) como en .glb.
"""
from __future__ import annotations

import base64
import io
import json
import os
import struct

import numpy as np

from ... import APP_NAME, __version__
from ...models.scene import SceneModel, SceneNode, Mesh, Material, Texture

GLB_MAGIC = b"glTF"


# ============================================================================ lectura

def read_gltf_json(path: str) -> dict:
    with open(path, "rb") as fh:
        head = fh.read(12)
        if head[:4] == GLB_MAGIC:
            length = struct.unpack("<I", fh.read(4))[0]
            ctype = fh.read(4)
            if ctype != b"JSON":
                raise ValueError("GLB sin fragmento JSON inicial")
            return json.loads(fh.read(length).decode("utf-8"))
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def check_external_resources(path: str, doc: dict, report) -> None:
    """Verifica recursos externos (buffers, imágenes) y que no salgan de la carpeta del modelo."""
    base = os.path.dirname(os.path.abspath(path))
    for kind in ("buffers", "images"):
        for item in doc.get(kind, []):
            uri = item.get("uri")
            if not uri or uri.startswith("data:"):
                continue
            from urllib.parse import unquote
            if "://" in uri:
                raise ValueError(f"Referencia externa no permitida ({kind}): {uri}")
            target = os.path.abspath(os.path.join(base, unquote(uri)))
            if os.path.commonpath([base, target]) != base:
                raise ValueError(f"Referencia fuera de la carpeta del modelo bloqueada: {uri}")
            if not os.path.isfile(target):
                if kind == "buffers":
                    raise FileNotFoundError(f"Falta el archivo auxiliar de geometría: {uri}")
                report.warn(f"Falta la textura externa '{uri}'; el material se exporta sin ella.")


def read_gltf(path: str, report) -> SceneModel:
    import trimesh

    doc = read_gltf_json(path)
    check_external_resources(path, doc, report)
    if doc.get("animations"):
        report.loss(f"{len(doc['animations'])} animación(es) glTF no se convierten (solo geometría estática).")
    if doc.get("skins"):
        report.loss("Esqueletos/skinning glTF ignorados: se exporta la pose de reposo.")
    if doc.get("extensionsRequired"):
        report.warn("Extensiones glTF requeridas: " + ", ".join(doc["extensionsRequired"]))
    if any(p.get("mode", 4) != 4 for m in doc.get("meshes", []) for p in m.get("primitives", [])):
        report.loss("Primitivas de puntos/líneas glTF ignoradas (solo se convierten triángulos).")

    loaded = trimesh.load(path, force="scene", process=False, maintain_order=True)
    scene = SceneModel(name=os.path.splitext(os.path.basename(path))[0])
    scene.metadata.update({"unit_m": 1.0, "up": "Y", "uv_origin": "bottom"})
    _trimesh_scene_to_model(loaded, scene, report)
    # extras de nodos (metadatos) desde el JSON original
    extras_by_name = {n.get("name"): n.get("extras") for n in doc.get("nodes", []) if n.get("extras")}
    for node in scene.nodes:
        ex = extras_by_name.get(node.name)
        if isinstance(ex, dict):
            node.properties.update(ex)
    return scene


def _trimesh_scene_to_model(tscene, scene: SceneModel, report) -> None:
    import trimesh
    from PIL import Image

    graph = tscene.graph
    base = graph.base_frame
    mat_cache: dict[int, int] = {}
    tex_cache: dict[int, int] = {}
    geom_cache: dict[str, int] = {}

    def material_index(visual) -> int | None:
        mat = getattr(visual, "material", None)
        if mat is None:
            if isinstance(visual, trimesh.visual.ColorVisuals) and visual.kind is not None:
                c = np.asarray(visual.main_color, dtype=float) / 255.0
                return scene.add_material(Material(name=f"color_{len(scene.materials)}", base_color=tuple(c)))
            return None
        key = id(mat)
        if key in mat_cache:
            return mat_cache[key]
        if hasattr(mat, "to_pbr"):
            pbr = mat if isinstance(mat, trimesh.visual.material.PBRMaterial) else mat.to_pbr()
        else:
            pbr = mat
        color = getattr(pbr, "baseColorFactor", None)
        color = (np.asarray(color, dtype=float) / (255.0 if np.asarray(color).dtype.kind in "ui" else 1.0)
                 if color is not None else np.array([0.8, 0.8, 0.8, 1.0]))
        if len(color) == 3:
            color = np.append(color, 1.0)
        tex_idx = None
        img = getattr(pbr, "baseColorTexture", None)
        if isinstance(img, Image.Image):
            if id(img) not in tex_cache:
                buf = io.BytesIO()
                fmt = "JPEG" if (img.format == "JPEG" and img.mode == "RGB") else "PNG"
                img.save(buf, format=fmt)
                scene.textures.append(Texture(name=getattr(pbr, "name", None) or f"tex{len(scene.textures)}",
                                              data=buf.getvalue(),
                                              mime="image/jpeg" if fmt == "JPEG" else "image/png"))
                tex_cache[id(img)] = len(scene.textures) - 1
            tex_idx = tex_cache[id(img)]
        m = Material(name=getattr(pbr, "name", None) or f"material_{len(scene.materials)}",
                     base_color=tuple(float(x) for x in color),
                     metallic=float(getattr(pbr, "metallicFactor", None) or 0.0),
                     roughness=float(getattr(pbr, "roughnessFactor", None) if getattr(pbr, "roughnessFactor", None) is not None else 1.0),
                     base_color_texture=tex_idx,
                     double_sided=bool(getattr(pbr, "doubleSided", False)))
        idx = scene.add_material(m)
        mat_cache[key] = idx
        return idx

    def mesh_index(gname: str) -> int | None:
        if gname in geom_cache:
            return geom_cache[gname]
        g = tscene.geometry.get(gname)
        if g is None or not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            if g is not None and not isinstance(g, trimesh.Trimesh):
                report.loss(f"Geometría no triangular ignorada: {gname} ({type(g).__name__})")
            geom_cache[gname] = None
            return None
        uv = None
        vis = g.visual
        if isinstance(vis, trimesh.visual.TextureVisuals) and vis.uv is not None and len(vis.uv) == len(g.vertices):
            uv = np.asarray(vis.uv, dtype=float)
        normals = None
        try:
            cached = g._cache.cache.get("vertex_normals")
        except Exception:
            cached = None
        if cached is not None and len(cached) == len(g.vertices):
            normals = np.asarray(cached, dtype=float)
        mesh = Mesh(name=gname, vertices=np.asarray(g.vertices, dtype=float), faces=np.asarray(g.faces),
                    normals=normals, uvs=uv, material=material_index(vis))
        geom_cache[gname] = scene.add_mesh(mesh)
        return geom_cache[gname]

    # construir jerarquía a partir del grafo de trimesh
    children: dict[str, list[str]] = {}
    edge_data = {}
    for e in graph.to_edgelist():
        children.setdefault(e[0], []).append(e[1])
        edge_data[(e[0], e[1])] = e[2]

    def build(name: str, parent_idx: int | None):
        for child in children.get(name, []):
            data = edge_data.get((name, child), {})
            node = SceneNode(name=str(child), matrix=np.asarray(data.get("matrix", np.eye(4)), dtype=float))
            gname = data.get("geometry")
            if gname is not None:
                mi = mesh_index(gname)
                if mi is not None:
                    node.meshes.append(mi)
            idx = scene.add_node(node, parent_idx)
            build(child, idx)

    build(base, None)
