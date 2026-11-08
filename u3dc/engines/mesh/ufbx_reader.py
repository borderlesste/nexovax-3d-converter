"""Lectura de FBX (binario y ASCII, todas las versiones) y OBJ mediante ufbx (MIT).

ufbx normaliza directamente a la convención canónica (metros, Z arriba, diestro).

Aislamiento: el binding Python de ufbx 0.0.x libera memoria interna de la escena cuando se
destruyen algunos de sus objetos envoltorio (comprobado: provoca violaciones de acceso).
Por eso la lectura nativa se ejecuta SIEMPRE en un proceso hijo desechable que:
  * conserva vivos todos los envoltorios que crea (lista `keep`),
  * copia la escena a estructuras Python/numpy puras,
  * las envía al proceso padre y termina con os._exit() sin destruir nada.
El proceso padre nunca toca objetos de ufbx.
"""
from __future__ import annotations

import io
import multiprocessing as mp
import os

import numpy as np

from ...models.scene import SceneModel, SceneNode, Mesh, Material, Texture
from .polygons import triangulate, compact_corners


# ============================================================================ proceso hijo

class _Keep:
    """Mantiene vivos todos los envoltorios de ufbx creados durante la extracción."""

    def __init__(self):
        self.items = []

    def __call__(self, obj):
        self.items.append(obj)
        return obj

    def attr(self, obj, *names):
        for n in names:
            obj = self(getattr(obj, n))
        return obj


def _vals(K, lst, width) -> np.ndarray:
    n = len(lst)
    if n == 0:
        return np.zeros((0, width))
    return np.array([tuple(K(lst[i])) for i in range(n)], dtype=np.float64).reshape(n, width)


def _ints(lst) -> np.ndarray:
    n = len(lst)
    return np.fromiter((lst[i] for i in range(n)), dtype=np.int64, count=n)


def _mat4(K, m) -> np.ndarray:
    out = np.eye(4)
    for c, name in enumerate(("c0", "c1", "c2", "c3")):
        out[:3, c] = tuple(K(getattr(m, name)))
    return out


def _load_texture_file(names: list[str], model_dir: str) -> bytes:
    """Busca la textura solo dentro de la carpeta del modelo (o subcarpetas)."""
    for fn in names:
        if not fn:
            continue
        fn = fn.replace("\\", "/")
        cands = [fn if os.path.isabs(fn) else os.path.join(model_dir, fn),
                 os.path.join(model_dir, os.path.basename(fn))]
        for c in cands:
            c = os.path.abspath(c)
            try:
                inside = os.path.commonpath([model_dir, c]) == model_dir
            except ValueError:
                inside = False
            if inside and os.path.isfile(c):
                with open(c, "rb") as fh:
                    return fh.read()
    return b""


def _extract(path: str, is_obj: bool, obj_unit_m: float, obj_up: str) -> dict:
    import ufbx

    K = _Keep()
    msgs: list[tuple[str, str]] = []
    opts = dict(
        target_axes=ufbx.axes_right_handed_z_up,
        target_unit_meters=1.0,
        space_conversion=ufbx.SpaceConversion.MODIFY_GEOMETRY,
        geometry_transform_handling=ufbx.GeometryTransformHandling.MODIFY_GEOMETRY,
        load_external_files=False,
        ignore_missing_external_files=True,
        generate_missing_normals=False,
        # índices fuera de rango = archivo corrupto: abortar en lugar de recortar en silencio
        index_error_handling=ufbx.IndexErrorHandling.ABORT_LOADING,
    )
    if is_obj:
        opts["obj_axes"] = ufbx.axes_right_handed_y_up if obj_up == "Y" else ufbx.axes_right_handed_z_up
        opts["obj_unit_meters"] = float(obj_unit_m)
        mtl = os.path.splitext(path)[0] + ".mtl"
        if os.path.isfile(mtl):
            opts["obj_mtl_path"] = mtl
    fs = K(ufbx.load_file(path, **opts))
    model_dir = os.path.dirname(os.path.abspath(path))
    out: dict = {"meta": {}, "materials": {}, "textures": {}, "meshes": {}, "nodes": [], "msgs": msgs}

    meta = K.attr(fs, "metadata")
    out["meta"]["creator"] = str(meta.creator)
    out["meta"]["ascii"] = bool(meta.ascii)
    st = K.attr(fs, "settings")
    try:
        out["meta"]["original_unit_m"] = float(st.original_unit_meters)
    except Exception:
        out["meta"]["original_unit_m"] = 0.01
    wl = K.attr(meta, "warnings")
    for i in range(len(wl)):
        msgs.append(("warn", f"Lector FBX/OBJ: {K(wl[i]).description}"))

    if not is_obj:
        stacks = K.attr(fs, "anim_stacks")
        n_anim = sum(1 for i in range(len(stacks)) if len(K.attr(K(stacks[i]), "layers")))
        if len(K.attr(fs, "anim_curves")) and n_anim:
            msgs.append(("loss", f"{n_anim} pila(s) de animación FBX no se convierten: se exporta la pose estática."))
        if len(K.attr(fs, "skin_deformers")):
            msgs.append(("loss", "Deformaciones de esqueleto (skinning) ignoradas: se usa la geometría en pose de enlace."))
        if len(K.attr(fs, "blend_deformers")):
            msgs.append(("loss", "Formas de mezcla (blend shapes) ignoradas."))
        nc, nl = len(K.attr(fs, "cameras")), len(K.attr(fs, "lights"))
        if nc or nl:
            msgs.append(("loss", f"{nc} cámara(s) y {nl} luz(ces) no se convierten."))
        if len(K.attr(fs, "nurbs_surfaces")) or len(K.attr(fs, "nurbs_curves")):
            msgs.append(("loss", "Superficies/curvas NURBS de FBX no soportadas: se ignoran."))

    # ---- texturas
    textures = K.attr(fs, "textures")
    for i in range(len(textures)):
        t = K(textures[i])
        name = t.name or t.relative_filename or f"tex{i}"
        try:
            content = bytes(t.content)
        except Exception:
            content = b""
        if not content:
            content = _load_texture_file([t.relative_filename, t.filename, t.absolute_filename], model_dir)
        if not content:
            msgs.append(("warn", f"Textura no encontrada o fuera de la carpeta del modelo: {name}"))
            out["textures"][t.element_id] = None
        else:
            out["textures"][t.element_id] = (str(name), content)

    # ---- materiales
    prio = ("DiffuseColor", "Diffuse", "Kd", "map_Kd", "BaseColor", "base_color", "baseColor",
            "Maya|baseColor", "3dsMax|Parameters|base_color_map")
    materials = K.attr(fs, "materials")
    for i in range(len(materials)):
        m = K(materials[i])
        pbr = K.attr(m, "pbr")

        def mapv(name, default):
            mp_ = K.attr(pbr, name)
            return float(K(mp_.value_vec4)[0]) if mp_.has_value else default

        bc = K.attr(pbr, "base_color")
        col = tuple(K(bc.value_vec4)) if bc.has_value else tuple(K(K.attr(m, "fbx", "diffuse_color").value_vec4))
        factor = mapv("base_factor", 1.0)
        cands = []
        mtl = K.attr(m, "textures")
        for k in range(len(mtl)):
            mtx = K(mtl[k])
            cands.append((str(mtx.material_prop), K.attr(mtx, "texture").element_id))
        tex_id = None
        for p in prio:
            hit = [t for n, t in cands if n == p]
            if hit:
                tex_id = hit[0]
                break
        if tex_id is None:
            hit = [t for n, t in cands if "diffuse" in n.lower() or "color" in n.lower()]
            tex_id = hit[0] if hit else None
        out["materials"][m.element_id] = dict(
            name=str(m.name) or f"material_{i}",
            rgba=(col[0] * factor, col[1] * factor, col[2] * factor, mapv("opacity", 1.0)),
            rough=mapv("roughness", 0.8), metal=mapv("metalness", 0.0), tex=tex_id)

    # ---- mallas
    meshes = K.attr(fs, "meshes")
    for i in range(len(meshes)):
        mesh = K(meshes[i])
        faces = K.attr(mesh, "faces")
        nf = len(faces)
        starts = np.empty(nf, np.int64)
        counts = np.empty(nf, np.int64)
        for k in range(nf):
            f = faces[k]                     # Face es una tupla Python pura
            starts[k] = f.index_begin
            counts[k] = f.num_indices
        rec = {"name": str(mesh.name), "starts": starts, "counts": counts,
               "reversed": bool(mesh.reversed_winding)}
        vp = K.attr(mesh, "vertex_position")
        rec["pos"] = _vals(K, K.attr(vp, "values"), 3)
        rec["pos_idx"] = _ints(K.attr(vp, "indices"))
        vn = K.attr(mesh, "vertex_normal")
        if vn.exists:
            rec["nrm"] = _vals(K, K.attr(vn, "values"), 3)
            rec["nrm_idx"] = _ints(K.attr(vn, "indices"))
        vu = K.attr(mesh, "vertex_uv")
        if vu.exists:
            rec["uv"] = _vals(K, K.attr(vu, "values"), 2)
            rec["uv_idx"] = _ints(K.attr(vu, "indices"))
        fm = K.attr(mesh, "face_material")
        rec["face_mat"] = _ints(fm) if len(fm) else np.zeros(nf, np.int64)
        ml = K.attr(mesh, "materials")
        rec["mats"] = [K(ml[k]).element_id for k in range(len(ml))]
        out["meshes"][mesh.element_id] = rec

    # ---- nodos (ufbx los ordena por profundidad)
    nodes = K.attr(fs, "nodes")
    for i in range(len(nodes)):
        n = K(nodes[i])
        if n.is_root:
            out["root_id"] = n.element_id
            continue
        par = K(n.parent)
        mesh_ref = K(n.mesh)
        nm = K.attr(n, "materials")
        out["nodes"].append(dict(
            id=n.element_id, parent=par.element_id if par is not None else None,
            name=str(n.name) or f"nodo_{i}", matrix=_mat4(K, K.attr(n, "node_to_parent")),
            mesh=mesh_ref.element_id if mesh_ref is not None else None,
            mats=[K(nm[k]).element_id for k in range(len(nm))]))
    _extract.keep = K           # nunca destruir: el proceso termina con os._exit()
    return out


def _child_entry(conn, path, is_obj, obj_unit_m, obj_up):
    try:
        data = _extract(path, is_obj, obj_unit_m, obj_up)
        conn.send(("ok", data))
    except BaseException as e:   # noqa: BLE001 — se informa al padre
        try:
            conn.send(("error", f"{type(e).__name__}: {e}"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        finally:
            os._exit(0)


def _extract_isolated(path: str, is_obj: bool, obj_unit_m: float, obj_up: str, timeout: float = 900.0) -> dict:
    ctx = mp.get_context("spawn")
    recv, send = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child_entry, args=(send, path, is_obj, obj_unit_m, obj_up), daemon=False)
    proc.start()
    send.close()
    try:
        if not recv.poll(timeout):
            raise TimeoutError("Tiempo de lectura FBX/OBJ excedido.")
        try:
            status, payload = recv.recv()
        except EOFError:
            raise RuntimeError("El lector FBX/OBJ terminó inesperadamente (archivo posiblemente corrupto).")
    finally:
        proc.join(5)
        if proc.is_alive():
            proc.kill()
        recv.close()
    if status != "ok":
        raise ValueError(f"No se pudo leer el archivo: {payload}")
    return payload


# ============================================================================ proceso padre

def _image_bytes(data: bytes, name: str, report) -> tuple[bytes, str] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return data, "image/jpeg"
    try:  # TGA, BMP, DDS… → PNG
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        report.warn(f"Textura '{name}' convertida a PNG.")
        return buf.getvalue(), "image/png"
    except Exception:
        report.warn(f"Formato de textura no soportado: {name}")
        return None


def read_with_ufbx(path: str, report, is_obj: bool = False, obj_unit_m: float = 1.0, obj_up: str = "Y") -> SceneModel:
    data = _extract_isolated(path, is_obj, obj_unit_m, obj_up)
    for level, msg in data.get("msgs", []):
        (report.loss if level == "loss" else report.warn)(msg)
    if data["meta"].get("ascii") and not is_obj:
        report.info("FBX ASCII detectado.")
    return _build_scene(data, path, report)


def _build_scene(data: dict, path: str, report) -> SceneModel:
    scene = SceneModel(name=os.path.splitext(os.path.basename(path))[0])
    scene.metadata.update({"unit_m": 1.0, "up": "Z", "creator": data["meta"].get("creator", ""),
                           "original_unit_m": data["meta"].get("original_unit_m", 0.01)})
    tex_index: dict[int, int | None] = {}
    mat_index: dict[int, int] = {}

    def texture(tid):
        if tid is None or data["textures"].get(tid) is None:
            return None
        if tid not in tex_index:
            name, content = data["textures"][tid]
            got = _image_bytes(content, name, report)
            if got is None:
                tex_index[tid] = None
            else:
                scene.textures.append(Texture(name=os.path.splitext(os.path.basename(name))[0] or "tex",
                                              data=got[0], mime=got[1]))
                tex_index[tid] = len(scene.textures) - 1
        return tex_index[tid]

    def material(mid):
        if mid is None or mid not in data["materials"]:
            return None
        if mid not in mat_index:
            m = data["materials"][mid]
            mat_index[mid] = scene.add_material(Material(
                name=m["name"], base_color=tuple(float(np.clip(c, 0, 1)) for c in m["rgba"]),
                metallic=float(np.clip(m["metal"], 0, 1)), roughness=float(np.clip(m["rough"], 0, 1)),
                base_color_texture=texture(m["tex"])))
        return mat_index[mid]

    mesh_cache: dict[tuple, list[int]] = {}

    def convert(mesh_id, node_mats, node_name) -> list[int]:
        rec = data["meshes"].get(mesh_id)
        if rec is None:
            return []
        mats = node_mats or rec["mats"]
        key = (mesh_id, tuple(mats))
        if key in mesh_cache:
            return mesh_cache[key]
        starts, counts = rec["starts"], rec["counts"]
        corner_pos = rec["pos"][rec["pos_idx"]]
        valid = counts >= 3
        if not valid.all():
            report.loss(f"Malla '{rec['name'] or node_name}': {int((~valid).sum())} caras de puntos/líneas ignoradas.")
        tris, tri_face = triangulate(starts[valid], counts[valid], corner_pos)
        tri_face = np.nonzero(valid)[0][tri_face]
        keys = [rec["pos_idx"]]
        if "nrm" in rec:
            keys.append(rec["nrm_idx"])
        if "uv" in rec:
            keys.append(rec["uv_idx"])
        keys = np.stack(keys, axis=1)
        tri_mat = rec["face_mat"][tri_face] if len(tri_face) else np.zeros(0, np.int64)
        result = []
        uniq = np.unique(tri_mat) if len(tri_mat) else []
        for mid in uniq:
            sel = tris[tri_mat == mid]
            rep, f = compact_corners(keys, sel)
            v = rec["pos"][rec["pos_idx"][rep]]
            nrm = rec["nrm"][rec["nrm_idx"][rep]] if "nrm" in rec else None
            uv = rec["uv"][rec["uv_idx"][rep]] if "uv" in rec else None
            mat_id = mats[mid] if 0 <= mid < len(mats) else None
            name = rec["name"] or node_name or "malla"
            if len(uniq) > 1:
                mname = data["materials"].get(mat_id, {}).get("name", str(mid))
                name = f"{name}_{mname}"
            if rec["reversed"]:
                f = f[:, ::-1]
            result.append(scene.add_mesh(Mesh(name=name, vertices=v, faces=f, normals=nrm, uvs=uv,
                                              material=material(mat_id))))
        mesh_cache[key] = result
        return result

    id_to_idx: dict[int, int] = {}
    root_id = data.get("root_id")
    pending = list(data["nodes"])
    for _ in range(256):
        if not pending:
            break
        rest = []
        for n in pending:
            par = n["parent"]
            if par is not None and par != root_id and par not in id_to_idx:
                rest.append(n)
                continue
            node = SceneNode(name=n["name"], matrix=n["matrix"])
            if n["mesh"] is not None:
                node.meshes = convert(n["mesh"], n["mats"], n["name"])
            parent_idx = id_to_idx.get(par) if par not in (None, root_id) else None
            id_to_idx[n["id"]] = scene.add_node(node, parent_idx)
        if len(rest) == len(pending):
            report.warn(f"{len(rest)} nodo(s) con jerarquía inválida ignorados.")
            break
        pending = rest
    if not scene.meshes:
        raise ValueError("El archivo no contiene mallas con caras.")
    return scene
