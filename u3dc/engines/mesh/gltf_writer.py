"""Escritor glTF 2.0 / GLB propio (sin dependencias externas salvo numpy)."""
from __future__ import annotations

import base64
import json
import os
import struct

import numpy as np

from ... import APP_NAME, __version__
from ...models.scene import SceneModel

GLB_MAGIC = b"glTF"


class _BufferBuilder:
    def __init__(self):
        self.chunks: list[bytes] = []
        self.length = 0
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def add_view(self, data: bytes, target: int | None = None) -> int:
        pad = (-self.length) % 4
        if pad:
            self.chunks.append(b"\x00" * pad)
            self.length += pad
        view = {"buffer": 0, "byteOffset": self.length, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.chunks.append(data)
        self.length += len(data)
        self.views.append(view)
        return len(self.views) - 1

    def add_accessor(self, arr: np.ndarray, kind: str, target: int | None, minmax: bool = False) -> int:
        comp = {np.float32: 5126, np.uint32: 5125, np.uint16: 5123}[arr.dtype.type]
        view = self.add_view(np.ascontiguousarray(arr).tobytes(), target)
        acc = {"bufferView": view, "componentType": comp, "count": int(arr.shape[0]), "type": kind}
        if minmax:
            acc["min"] = [float(x) for x in arr.min(axis=0)]
            acc["max"] = [float(x) for x in arr.max(axis=0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def data(self) -> bytes:
        return b"".join(self.chunks)


def _safe_extras(props):
    if isinstance(props, (str, int, float, bool)) or props is None:
        return props
    if isinstance(props, dict):
        return {str(k): _safe_extras(x) for k, x in props.items()}
    if isinstance(props, (list, tuple)):
        return [_safe_extras(x) for x in props]
    if isinstance(props, (np.integer,)):
        return int(props)
    if isinstance(props, (np.floating,)):
        return float(props)
    return str(props)


def write_gltf(scene: SceneModel, path: str, binary: bool, report, embed: bool = False,
               keep_materials: bool = True, include_properties: bool = True) -> list[str]:
    """Escribe glTF/GLB. La escena debe estar ya en coordenadas glTF (metros, Y arriba).

    Devuelve la lista de archivos escritos (el principal primero).
    """
    buf = _BufferBuilder()
    doc: dict = {"asset": {"version": "2.0", "generator": f"{APP_NAME} {__version__}"},
                 "scene": 0, "scenes": [{"name": scene.name, "nodes": []}],
                 "nodes": [], "meshes": []}
    written = [path]
    stem = os.path.splitext(os.path.basename(path))[0]
    out_dir = os.path.dirname(path)

    # ---- texturas e imágenes
    tex_map: dict[int, int] = {}
    if keep_materials and scene.textures:
        used = sorted({m.base_color_texture for m in scene.materials if m.base_color_texture is not None})
        if used:
            doc["images"], doc["textures"] = [], []
            doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
        for ti in used:
            tex = scene.textures[ti]
            img: dict = {"name": tex.name}
            if binary:
                img["bufferView"] = buf.add_view(tex.data)
                img["mimeType"] = tex.mime
            elif embed:
                img["uri"] = f"data:{tex.mime};base64," + base64.b64encode(tex.data).decode("ascii")
            else:
                fname = f"{stem}_tex{ti}{tex.extension}"
                with open(os.path.join(out_dir, fname), "wb") as fh:
                    fh.write(tex.data)
                written.append(os.path.join(out_dir, fname))
                img["uri"] = fname
            doc["images"].append(img)
            doc["textures"].append({"sampler": 0, "source": len(doc["images"]) - 1})
            tex_map[ti] = len(doc["textures"]) - 1

    # ---- materiales
    mat_map: dict[int, int] = {}
    if keep_materials and scene.materials:
        doc["materials"] = []
        for i, m in enumerate(scene.materials):
            pbr = {"baseColorFactor": [float(np.clip(c, 0, 1)) for c in m.base_color],
                   "metallicFactor": float(np.clip(m.metallic, 0, 1)),
                   "roughnessFactor": float(np.clip(m.roughness, 0, 1))}
            if m.base_color_texture is not None and m.base_color_texture in tex_map:
                pbr["baseColorTexture"] = {"index": tex_map[m.base_color_texture]}
            gm = {"name": m.name, "pbrMetallicRoughness": pbr}
            if m.base_color[3] < 0.999:
                gm["alphaMode"] = "BLEND"
            if m.double_sided:
                gm["doubleSided"] = True
            doc["materials"].append(gm)
            mat_map[i] = len(doc["materials"]) - 1

    # ---- mallas: una malla glTF por combinación única de mallas → se conservan las instancias
    prim_cache: dict[int, dict] = {}
    gmesh_cache: dict[tuple, int] = {}
    far = 0.0

    def primitive(mi: int) -> dict:
        if mi in prim_cache:
            return prim_cache[mi]
        mesh = scene.meshes[mi]
        v = mesh.vertices.astype(np.float32)
        attrs = {"POSITION": buf.add_accessor(v, "VEC3", 34962, minmax=True)}
        if mesh.normals is not None:
            attrs["NORMAL"] = buf.add_accessor(mesh.normals.astype(np.float32), "VEC3", 34962)
        if mesh.uvs is not None and keep_materials:
            uv = mesh.uvs.astype(np.float32).copy()
            uv[:, 1] = 1.0 - uv[:, 1]       # glTF: origen de UV arriba-izquierda
            attrs["TEXCOORD_0"] = buf.add_accessor(uv, "VEC2", 34962)
        idx_dtype = np.uint16 if len(v) < 65536 else np.uint32
        prim = {"attributes": attrs,
                "indices": buf.add_accessor(mesh.faces.astype(idx_dtype).reshape(-1), "SCALAR", 34963),
                "mode": 4}
        if mesh.material is not None and mesh.material in mat_map:
            prim["material"] = mat_map[mesh.material]
        prim_cache[mi] = prim
        return prim

    node_map: dict[int, int] = {}
    for idx, world, parent in scene.iter_nodes():
        node = scene.nodes[idx]
        gnode: dict = {"name": node.name}
        if not np.allclose(node.matrix, np.eye(4), atol=1e-12):
            gnode["matrix"] = [float(x) for x in node.matrix.T.reshape(-1)]   # orden por columnas
        meshes = [mi for mi in node.meshes if len(scene.meshes[mi].faces)]
        if meshes:
            key = tuple(meshes)
            if key not in gmesh_cache:
                doc["meshes"].append({"name": scene.meshes[meshes[0]].name if len(meshes) == 1 else node.name,
                                      "primitives": [primitive(mi) for mi in meshes]})
                gmesh_cache[key] = len(doc["meshes"]) - 1
            gnode["mesh"] = gmesh_cache[key]
            for mi in meshes:
                vw = scene.meshes[mi].vertices
                if len(vw):
                    far = max(far, float(np.abs(world[:3, 3]).max() + np.abs(vw).max()))
        extras = {}
        if include_properties and node.properties:
            extras.update(_safe_extras(node.properties))
        if node.kind and include_properties:
            extras.setdefault("type", node.kind)
        if extras:
            gnode["extras"] = extras
        doc["nodes"].append(gnode)
        node_map[idx] = len(doc["nodes"]) - 1
        if parent is None:
            doc["scenes"][0]["nodes"].append(node_map[idx])
        else:
            doc["nodes"][node_map[parent]].setdefault("children", []).append(node_map[idx])

    if far > 1e5:
        report.warn("Coordenadas muy alejadas del origen (>100 km): glTF almacena vértices en float32; "
                    "puede perderse precisión submilimétrica.")
    if not doc["meshes"]:
        raise ValueError("La escena no contiene geometría triangular exportable.")

    bin_data = buf.data()
    doc["bufferViews"] = buf.views
    doc["accessors"] = buf.accessors
    if binary:
        doc["buffers"] = [{"byteLength": len(bin_data)}]
        js = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        js += b" " * ((-len(js)) % 4)
        bin_pad = bin_data + b"\x00" * ((-len(bin_data)) % 4)
        total = 12 + 8 + len(js) + 8 + len(bin_pad)
        with open(path, "wb") as fh:
            fh.write(GLB_MAGIC + struct.pack("<II", 2, total))
            fh.write(struct.pack("<I", len(js)) + b"JSON" + js)
            fh.write(struct.pack("<I", len(bin_pad)) + b"BIN\x00" + bin_pad)
    else:
        if embed:
            doc["buffers"] = [{"byteLength": len(bin_data),
                               "uri": "data:application/octet-stream;base64," + base64.b64encode(bin_data).decode("ascii")}]
        else:
            bin_name = stem + ".bin"
            with open(os.path.join(out_dir, bin_name), "wb") as fh:
                fh.write(bin_data)
            written.append(os.path.join(out_dir, bin_name))
            doc["buffers"] = [{"byteLength": len(bin_data), "uri": bin_name}]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
    return written
