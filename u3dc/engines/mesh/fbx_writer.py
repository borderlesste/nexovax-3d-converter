"""Escritor FBX binario 7.4 propio (sin FBX SDK).

Genera: jerarquía de nodos (Model Null/Mesh), geometría con normales y UV,
materiales Phong (aproximación de PBR) y texturas difusas embebidas.
Unidades: metros (UnitScaleFactor = 100). Ejes: Y arriba (convención FBX habitual).
"""
from __future__ import annotations

import math
import os
import struct
import time
import zlib

import numpy as np

from ... import APP_NAME, __version__
from ...models.scene import SceneModel

# Constantes de cabecera/pie usadas por exportadores FBX libres (pareja FileId/CreationTime coherente)
_HEAD_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
_FILE_ID = b"\x28\xb3\x2a\xeb\xb6\x24\xcc\xc2\xbf\xc8\xb0\x2a\xa9\x2b\xfc\xf1"
_TIME_ID = "1970-01-01 10:00:00:000"
_FOOT_ID = b"\xfa\xbc\xab\x09\xd0\xc8\xd4\x66\xb1\x76\xfb\x83\x1c\xf7\x26\x7e"
_FOOT_MAGIC = b"\xf8\x5a\x8c\x6a\xde\xf5\xd9\x7e\xec\xe9\x0c\xe3\x75\x8f\x29\x0b"
_VERSION = 7400
_NULL_RECORD = b"\x00" * 13


class Elem:
    __slots__ = ("name", "props", "children")

    def __init__(self, name: str, *props):
        self.name = name
        self.props = list(props)
        self.children: list[Elem] = []

    def add(self, name: str, *props) -> "Elem":
        e = Elem(name, *props)
        self.children.append(e)
        return e


class I32(int): pass
class I64(int): pass
class I16(int): pass
class F64(float): pass
class Raw(bytes): pass


def _encode_prop(p) -> bytes:
    if isinstance(p, bool):
        return b"C" + (b"\x01" if p else b"\x00")
    if isinstance(p, I16):
        return b"Y" + struct.pack("<h", p)
    if isinstance(p, I64):
        return b"L" + struct.pack("<q", p)
    if isinstance(p, I32) or isinstance(p, int):
        return b"I" + struct.pack("<i", p)
    if isinstance(p, float):
        return b"D" + struct.pack("<d", p)
    if isinstance(p, Raw):
        return b"R" + struct.pack("<I", len(p)) + bytes(p)
    if isinstance(p, (bytes, bytearray)):
        return b"S" + struct.pack("<I", len(p)) + bytes(p)
    if isinstance(p, str):
        b = p.encode("utf-8")
        return b"S" + struct.pack("<I", len(b)) + b
    if isinstance(p, np.ndarray):
        if p.dtype == np.float64:
            code, data = b"d", p.astype("<f8").tobytes()
        elif p.dtype == np.float32:
            code, data = b"f", p.astype("<f4").tobytes()
        elif p.dtype == np.int64:
            code, data = b"l", p.astype("<i8").tobytes()
        elif p.dtype == np.int32:
            code, data = b"i", p.astype("<i4").tobytes()
        elif p.dtype == np.bool_:
            code, data = b"b", p.astype(np.uint8).tobytes()
        else:
            raise TypeError(f"Tipo de array FBX no soportado: {p.dtype}")
        if len(data) > 128:
            comp = zlib.compress(data, 6)
            return code + struct.pack("<III", len(p), 1, len(comp)) + comp
        return code + struct.pack("<III", len(p), 0, len(data)) + data
    raise TypeError(f"Propiedad FBX no soportada: {type(p)}")


def _write_elem(out: bytearray, e: Elem) -> None:
    start = len(out)
    props = b"".join(_encode_prop(p) for p in e.props)
    name = e.name.encode("ascii")
    out += struct.pack("<III", 0, len(e.props), len(props))
    out += struct.pack("<B", len(name)) + name + props
    if e.children or not e.props:
        for c in e.children:
            _write_elem(out, c)
        out += _NULL_RECORD
    struct.pack_into("<I", out, start, len(out))


def _p70(parent: Elem) -> Elem:
    return parent.add("Properties70")


def _p(p70: Elem, name, ptype, label, flags, *vals):
    p70.add("P", name, ptype, label, flags, *vals)


def _decompose(m: np.ndarray):
    """Descompone en T, R (Euler XYZ en grados, R = Rz·Ry·Rx) y S. None si hay cizalla."""
    t = m[:3, 3].copy()
    a = m[:3, :3]
    s = np.linalg.norm(a, axis=0)
    if np.any(s < 1e-15):
        return None
    if np.linalg.det(a) < 0:
        s[0] = -s[0]
    r = a / s
    if not np.allclose(r.T @ r, np.eye(3), atol=1e-6):
        return None
    sy = -r[2, 0]
    sy = max(-1.0, min(1.0, sy))
    b = math.asin(sy)
    if abs(math.cos(b)) > 1e-9:
        ax = math.atan2(r[2, 1], r[2, 2])
        cz = math.atan2(r[1, 0], r[0, 0])
    else:
        ax = math.atan2(-r[1, 2], r[1, 1])
        cz = 0.0
    return t, np.degrees([ax, b, cz]), s


class _Ids:
    def __init__(self):
        self.n = 1_000_000

    def __call__(self) -> I64:
        self.n += 1
        return I64(self.n)


def write_fbx(scene: SceneModel, path: str, report, keep_materials: bool = True,
              embed_textures: bool = True) -> list[str]:
    """La escena debe estar en metros, Y arriba (convención de salida FBX)."""
    ids = _Ids()
    written = [path]
    out_dir = os.path.dirname(path)
    stem = os.path.splitext(os.path.basename(path))[0]

    objects = Elem("Objects")
    conns = Elem("Connections")
    counts = {"Model": 0, "Geometry": 0, "Material": 0, "Texture": 0, "Video": 0}

    # ------------------------------------------------------------ materiales
    mat_ids: dict[int, I64] = {}
    if keep_materials:
        tex_ids: dict[int, I64] = {}
        for i, m in enumerate(scene.materials):
            mid = ids()
            mat_ids[i] = mid
            me = objects.add("Material", mid, f"{m.name}\x00\x01Material", "")
            me.add("Version", I32(102))
            me.add("ShadingModel", "Phong")
            me.add("MultiLayer", I32(0))
            p70 = _p70(me)
            r, g, b, a = (float(x) for x in m.base_color)
            _p(p70, "DiffuseColor", "Color", "", "A", r, g, b)
            _p(p70, "DiffuseFactor", "Number", "", "A", 1.0)
            _p(p70, "AmbientColor", "Color", "", "A", 0.0, 0.0, 0.0)
            spec = 0.04 + 0.96 * float(m.metallic)
            _p(p70, "SpecularColor", "Color", "", "A", spec, spec, spec)
            _p(p70, "SpecularFactor", "Number", "", "A", 1.0 - 0.8 * float(m.roughness))
            _p(p70, "Shininess", "Number", "", "A", max(2.0, (1.0 - float(m.roughness)) * 100.0))
            _p(p70, "ShininessExponent", "Number", "", "A", max(2.0, (1.0 - float(m.roughness)) * 100.0))
            _p(p70, "TransparencyFactor", "Number", "", "A", 1.0 - a)
            _p(p70, "Opacity", "Number", "", "A", a)
            counts["Material"] += 1
            if m.base_color_texture is not None:
                ti = m.base_color_texture
                tex = scene.textures[ti]
                fname = f"{stem}_tex{ti}{tex.extension}"
                if ti not in tex_ids:
                    fpath = os.path.join(out_dir, fname)
                    with open(fpath, "wb") as fh:
                        fh.write(tex.data)
                    written.append(fpath)
                    vid, tid = ids(), ids()
                    ve = objects.add("Video", vid, f"{tex.name}\x00\x01Video", "Clip")
                    ve.add("Type", "Clip")
                    vp = _p70(ve)
                    _p(vp, "Path", "KString", "XRefUrl", "", fname)
                    ve.add("UseMipMap", I32(0))
                    ve.add("Filename", fname)
                    ve.add("RelativeFilename", fname)
                    if embed_textures:
                        ve.add("Content", Raw(tex.data))
                    te = objects.add("Texture", tid, f"{tex.name}\x00\x01Texture", "")
                    te.add("Type", "TextureVideoClip")
                    te.add("Version", I32(202))
                    te.add("TextureName", f"{tex.name}\x00\x01Texture")
                    tp = _p70(te)
                    _p(tp, "UseMaterial", "bool", "", "", I32(1))
                    te.add("Media", f"{tex.name}\x00\x01Video")
                    te.add("FileName", fname)
                    te.add("RelativeFilename", fname)
                    te.add("ModelUVTranslation", 0.0, 0.0)
                    te.add("ModelUVScaling", 1.0, 1.0)
                    te.add("Texture_Alpha_Source", "None")
                    te.add("Cropping", I32(0), I32(0), I32(0), I32(0))
                    conns.add("C", "OO", vid, tid)
                    tex_ids[ti] = tid
                    counts["Texture"] += 1
                    counts["Video"] += 1
                conns.add("C", "OP", tex_ids[ti], mid, "DiffuseColor")

    # ------------------------------------------------------------ geometría
    geom_cache: dict[tuple, I64] = {}

    def geometry(mesh_ids: list[int], bake: np.ndarray | None) -> tuple[I64, list[int]]:
        key = (tuple(mesh_ids), None if bake is None else bake.tobytes())
        if key in geom_cache:
            return geom_cache[key]
        verts, polys, normals, uvs, mats = [], [], [], [], []
        mat_list: list[int] = []
        off = 0
        any_uv = keep_materials and any(scene.meshes[i].uvs is not None for i in mesh_ids)
        for mi in mesh_ids:
            mesh = scene.meshes[mi]
            v = mesh.vertices
            n = mesh.normals
            f = mesh.faces
            if bake is not None:
                v = v @ bake[:3, :3].T + bake[:3, 3]
                if n is not None:
                    nm = np.linalg.inv(bake[:3, :3]).T
                    n = n @ nm.T
                    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
                if np.linalg.det(bake[:3, :3]) < 0:
                    f = f[:, ::-1]
            verts.append(v)
            polys.append(f + off)
            if n is None:
                from ...models.scene import compute_vertex_normals
                n = compute_vertex_normals(v, f)
            normals.append(n[f].reshape(-1, 3))
            if any_uv:
                uv = mesh.uvs if mesh.uvs is not None else np.zeros((len(v), 2))
                uvs.append((uv, f + off))
            mat = mesh.material if (keep_materials and mesh.material is not None) else None
            if mat is not None and mat not in mat_list:
                mat_list.append(mat)
            mats.append(np.full(len(f), mat_list.index(mat) if mat is not None else 0, dtype=np.int32))
            off += len(v)
        V = np.concatenate(verts)
        F = np.concatenate(polys).astype(np.int32)
        pvi = F.copy()
        pvi[:, 2] = -pvi[:, 2] - 1                       # fin de polígono: índice XOR -1
        gid = ids()
        ge = objects.add("Geometry", gid, "\x00\x01Geometry", "Mesh")
        _p70(ge)
        ge.add("GeometryVersion", I32(124))
        ge.add("Vertices", np.ascontiguousarray(V, dtype=np.float64).reshape(-1))
        ge.add("PolygonVertexIndex", np.ascontiguousarray(pvi, dtype=np.int32).reshape(-1))
        ln = ge.add("LayerElementNormal", I32(0))
        ln.add("Version", I32(101))
        ln.add("Name", "")
        ln.add("MappingInformationType", "ByPolygonVertex")
        ln.add("ReferenceInformationType", "Direct")
        ln.add("Normals", np.ascontiguousarray(np.concatenate(normals), dtype=np.float64).reshape(-1))
        if any_uv:
            UV = np.concatenate([u for u, _ in uvs])
            UVI = np.concatenate([fi for _, fi in uvs]).astype(np.int32)
            lu = ge.add("LayerElementUV", I32(0))
            lu.add("Version", I32(101))
            lu.add("Name", "UVMap")
            lu.add("MappingInformationType", "ByPolygonVertex")
            lu.add("ReferenceInformationType", "IndexToDirect")
            lu.add("UV", np.ascontiguousarray(UV, dtype=np.float64).reshape(-1))
            lu.add("UVIndex", UVI.reshape(-1))
        if mat_list:
            lm = ge.add("LayerElementMaterial", I32(0))
            lm.add("Version", I32(101))
            lm.add("Name", "")
            M = np.concatenate(mats)
            if len(mat_list) == 1:
                lm.add("MappingInformationType", "AllSame")
                lm.add("ReferenceInformationType", "IndexToDirect")
                lm.add("Materials", np.zeros(1, dtype=np.int32))
            else:
                lm.add("MappingInformationType", "ByPolygon")
                lm.add("ReferenceInformationType", "IndexToDirect")
                lm.add("Materials", M.astype(np.int32))
        layer = ge.add("Layer", I32(0))
        layer.add("Version", I32(100))
        for t in (["LayerElementNormal"] + (["LayerElementMaterial"] if mat_list else [])
                  + (["LayerElementUV"] if any_uv else [])):
            le = layer.add("LayerElement")
            le.add("Type", t)
            le.add("TypedIndex", I32(0))
        counts["Geometry"] += 1
        geom_cache[key] = (gid, mat_list)
        return gid, mat_list

    # ------------------------------------------------------------ nodos
    model_ids: dict[int, I64] = {}
    local_override: dict[int, np.ndarray] = {}
    baked_nodes = 0
    for idx, world, parent in scene.iter_nodes():
        node = scene.nodes[idx]
        local = local_override.get(idx, node.matrix)
        dec = _decompose(local)
        bake = None
        if dec is None:
            # Matriz con cizalla: se aplica a la geometría y se propaga a los hijos
            bake = local
            for c in node.children:
                local_override[c] = local @ local_override.get(c, scene.nodes[c].matrix)
            dec = (np.zeros(3), np.zeros(3), np.ones(3))
            baked_nodes += 1
        t, r, s = dec
        meshes = [mi for mi in node.meshes if len(scene.meshes[mi].faces)]
        mid = ids()
        model_ids[idx] = mid
        me = objects.add("Model", mid, f"{node.name}\x00\x01Model", "Mesh" if meshes else "Null")
        me.add("Version", I32(232))
        p70 = _p70(me)
        _p(p70, "RotationActive", "bool", "", "", I32(1))
        _p(p70, "InheritType", "enum", "", "", I32(1))
        _p(p70, "ScalingMax", "Vector3D", "Vector", "", 0.0, 0.0, 0.0)
        _p(p70, "DefaultAttributeIndex", "int", "Integer", "", I32(0))
        _p(p70, "Lcl Translation", "Lcl Translation", "", "A", float(t[0]), float(t[1]), float(t[2]))
        _p(p70, "Lcl Rotation", "Lcl Rotation", "", "A", float(r[0]), float(r[1]), float(r[2]))
        _p(p70, "Lcl Scaling", "Lcl Scaling", "", "A", float(s[0]), float(s[1]), float(s[2]))
        me.add("Shading", True)
        me.add("Culling", "CullingOff")
        conns.add("C", "OO", mid, model_ids[parent] if parent is not None else I64(0))
        counts["Model"] += 1
        if meshes:
            gid, mlist = geometry(meshes, bake)
            conns.add("C", "OO", gid, mid)
            for mat in mlist:
                if mat in mat_ids:
                    conns.add("C", "OO", mat_ids[mat], mid)
    if baked_nodes:
        report.info(f"FBX: {baked_nodes} transformación(es) con cizalla aplicadas a la geometría.")
    if counts["Geometry"] == 0:
        raise ValueError("No hay geometría para exportar a FBX.")

    # ------------------------------------------------------------ documento
    root: list[Elem] = []
    hx = Elem("FBXHeaderExtension")
    hx.add("FBXHeaderVersion", I32(1003))
    hx.add("FBXVersion", I32(_VERSION))
    hx.add("EncryptionType", I32(0))
    lt = time.localtime()
    ts = hx.add("CreationTimeStamp")
    for k, v in (("Version", 1000), ("Year", lt.tm_year), ("Month", lt.tm_mon), ("Day", lt.tm_mday),
                 ("Hour", lt.tm_hour), ("Minute", lt.tm_min), ("Second", lt.tm_sec), ("Millisecond", 0)):
        ts.add(k, I32(v))
    hx.add("Creator", f"{APP_NAME} {__version__}")
    root.append(hx)
    root.append(Elem("FileId", Raw(_FILE_ID)))
    root.append(Elem("CreationTime", _TIME_ID))
    root.append(Elem("Creator", f"{APP_NAME} {__version__}"))

    gs = Elem("GlobalSettings")
    gs.add("Version", I32(1000))
    gp = _p70(gs)
    for name, val in (("UpAxis", 1), ("UpAxisSign", 1), ("FrontAxis", 2), ("FrontAxisSign", 1),
                      ("CoordAxis", 0), ("CoordAxisSign", 1), ("OriginalUpAxis", 1), ("OriginalUpAxisSign", 1)):
        _p(gp, name, "int", "Integer", "", I32(val))
    _p(gp, "UnitScaleFactor", "double", "Number", "", 100.0)
    _p(gp, "OriginalUnitScaleFactor", "double", "Number", "", 100.0)
    _p(gp, "AmbientColor", "ColorRGB", "Color", "", 0.0, 0.0, 0.0)
    _p(gp, "DefaultCamera", "KString", "", "", "Producer Perspective")
    _p(gp, "TimeMode", "enum", "", "", I32(11))
    _p(gp, "TimeSpanStart", "KTime", "Time", "", I64(0))
    _p(gp, "TimeSpanStop", "KTime", "Time", "", I64(46186158000))
    _p(gp, "CustomFrameRate", "double", "Number", "", 24.0)
    root.append(gs)

    docs = Elem("Documents")
    docs.add("Count", I32(1))
    d = docs.add("Document", ids(), "Scene", "Scene")
    dp = _p70(d)
    _p(dp, "SourceObject", "object", "", "")
    _p(dp, "ActiveAnimStackName", "KString", "", "", "")
    d.add("RootNode", I64(0))
    root.append(docs)
    root.append(Elem("References"))

    defs = Elem("Definitions")
    defs.add("Version", I32(100))
    used = {k: v for k, v in counts.items() if v}
    defs.add("Count", I32(1 + sum(used.values())))
    ot = defs.add("ObjectType", "GlobalSettings")
    ot.add("Count", I32(1))
    for k, v in used.items():
        o = defs.add("ObjectType", k)
        o.add("Count", I32(v))
    root.append(defs)
    root.append(objects)
    root.append(conns)
    takes = Elem("Takes")
    takes.add("Current", "")
    root.append(takes)

    out = bytearray(_HEAD_MAGIC + struct.pack("<I", _VERSION))
    for e in root:
        _write_elem(out, e)
    out += _NULL_RECORD
    out += _FOOT_ID
    out += b"\x00" * 4
    pad = ((len(out) + 15) & ~15) - len(out)
    out += b"\x00" * (pad if pad else 16)
    out += struct.pack("<I", _VERSION)
    out += b"\x00" * 120
    out += _FOOT_MAGIC
    with open(path, "wb") as fh:
        fh.write(out)
    return written
