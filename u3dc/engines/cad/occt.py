"""Motor CAD basado en Open CASCADE Technology (OCP / cadquery-ocp).

* Lectura/escritura STEP e IGES con XDE (nombres, colores y ensamblajes).
* Teselación B-Rep → malla con tolerancias lineal/angular (BRepMesh).
* Malla → B-Rep facetado con topología compartida (caras planas cosidas → sólido si es cerrada).
* Validación de formas (BRepCheck_Analyzer).
Unidad interna: milímetros.
"""
from __future__ import annotations

import os
import time

import numpy as np

from ...models.cad import CADModel, CadPart
from ...models.scene import SceneModel, SceneNode, Mesh, Material, compute_vertex_normals


# ============================================================================ utilidades XDE

def _new_doc():
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.InitDocument(doc)
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 0.001)    # unidad interna del documento: mm
    return doc


def _label_name(label) -> str:
    from OCP.TDataStd import TDataStd_Name
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return ""


def _label_color(color_tool, label, shape=None):
    from OCP.Quantity import Quantity_Color
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_ColorTool
    c = Quantity_Color()
    for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
        if XCAFDoc_ColorTool.GetColor_s(label, kind, c):
            return (c.Red(), c.Green(), c.Blue())
        if shape is not None and color_tool.GetColor(shape, kind, c):
            return (c.Red(), c.Green(), c.Blue())
    return None


def _face_color(color_tool, shape):
    """Color del primer subelemento coloreado (IGES suele asignar colores a sólidos/caras)."""
    from OCP.Quantity import Quantity_Color
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_ColorType
    c = Quantity_Color()
    for kind_shape in (TopAbs_ShapeEnum.TopAbs_SOLID, TopAbs_ShapeEnum.TopAbs_SHELL, TopAbs_ShapeEnum.TopAbs_FACE):
        exp = TopExp_Explorer(shape, kind_shape)
        n = 0
        while exp.More() and n < 50:
            for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
                if color_tool.GetColor(exp.Current(), kind, c):
                    return (c.Red(), c.Green(), c.Blue())
            exp.Next()
            n += 1
    return None


def _static(name: str, value):
    from OCP.Interface import Interface_Static
    if isinstance(value, str):
        Interface_Static.SetCVal_s(name, value)
    else:
        Interface_Static.SetIVal_s(name, int(value))


# ============================================================================ lectura

def read_cad(path: str, fmt: str, report) -> CADModel:
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.TDF import TDF_Label
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    from OCP.STEPControl import STEPControl_Controller
    from OCP.IGESControl import IGESControl_Controller
    STEPControl_Controller.Init_s()
    IGESControl_Controller.Init_s()
    _static("xstep.cascade.unit", "MM")
    _static("read.precision.mode", 0)
    doc = _new_doc()
    if fmt == "step":
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        reader = STEPCAFControl_Reader()
    else:
        from OCP.IGESCAFControl import IGESCAFControl_Reader
        reader = IGESCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    reader.SetLayerMode(True)
    status = reader.ReadFile(path)
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ValueError(f"OCCT no pudo leer el archivo {fmt.upper()} (estado: {status.name}). "
                         "Archivo corrupto o no conforme a la norma.")
    if not reader.Transfer(doc):
        raise ValueError(f"OCCT no pudo transferir la geometría {fmt.upper()}.")
    try:
        units = _file_units(reader, fmt)
    except Exception:
        units = ""
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    cad = CADModel(name=os.path.splitext(os.path.basename(path))[0], source_unit=units or "mm")
    if units and units.lower() not in ("mm", "millimetre", "millimeter"):
        report.info(f"Unidades del archivo: {units}; convertidas a mm por OCCT.")

    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)
    counter = [0]

    def walk(label, loc, path_names, inherited_color, inst_name=""):
        name = inst_name or _label_name(label) or f"pieza_{counter[0] + 1}"
        if XCAFDoc_ShapeTool.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            XCAFDoc_ShapeTool.GetComponents_s(label, comps, False)
            col = _label_color(color_tool, label) or inherited_color
            for i in range(1, comps.Length() + 1):
                comp = comps.Value(i)
                ref = TDF_Label()
                XCAFDoc_ShapeTool.GetReferredShape_s(comp, ref)
                cloc = XCAFDoc_ShapeTool.GetLocation_s(comp)
                ccol = _label_color(color_tool, comp) or col
                walk(ref, loc.Multiplied(cloc), path_names + (name,), ccol, _label_name(comp))
            return
        shape = XCAFDoc_ShapeTool.GetShape_s(label)
        if shape.IsNull():
            return
        shape = shape.Moved(loc)
        color = _label_color(color_tool, label, shape) or inherited_color or _face_color(color_tool, shape)
        counter[0] += 1
        cad.parts.append(CadPart(name=name, shape=shape, color=color, path=path_names))

    for i in range(1, free.Length() + 1):
        walk(free.Value(i), TopLoc_Location(), (), None)
    if not cad.parts:
        raise ValueError(f"El archivo {fmt.upper()} no contiene formas transferibles.")
    sewn = 0
    for p in cad.parts:
        new = _sew_loose_faces(p.shape)
        if new is not None:
            p.shape = new
            sewn += 1
    if sewn:
        report.info(f"{sewn} pieza(s) con caras sueltas cosidas (tolerancia OCCT) para recuperar la topología.")
    _check_shapes(cad, report)
    return cad


def _sew_loose_faces(shape):
    """Si la forma tiene caras que no pertenecen a ningún sólido/shell (típico de IGES), las cose
    y, si el resultado es cerrado, crea un sólido. Devuelve None si no hace falta."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    def count(s, kind, avoid=None):
        exp = TopExp_Explorer(s, kind, avoid) if avoid is not None else TopExp_Explorer(s, kind)
        n = 0
        while exp.More():
            n += 1
            exp.Next()
        return n

    free_faces = count(shape, TopAbs_ShapeEnum.TopAbs_FACE, TopAbs_ShapeEnum.TopAbs_SHELL)
    if free_faces < 2:
        return None
    sew = BRepBuilderAPI_Sewing(1e-3)
    sew.Add(shape)
    sew.Perform()
    res = sew.SewedShape()
    if res.IsNull():
        return None
    exp = TopExp_Explorer(res, TopAbs_ShapeEnum.TopAbs_SHELL)
    shells = []
    while exp.More():
        shells.append(TopoDS.Shell(exp.Current()))
        exp.Next()
    if len(shells) == 1 and count(res, TopAbs_ShapeEnum.TopAbs_FACE, TopAbs_ShapeEnum.TopAbs_SHELL) == 0:
        try:
            ms = BRepBuilderAPI_MakeSolid(shells[0])
            if ms.IsDone():
                fx = ShapeFix_Solid(ms.Solid())
                fx.Perform()
                solid = fx.Solid()
                from OCP.BRep import BRep_Tool
                if BRep_Tool.IsClosed_s(shells[0]) and BRepCheck_Analyzer(solid).IsValid():
                    return solid
        except Exception:
            pass
    return res


def _file_units(reader, fmt: str) -> str:
    if fmt != "step":
        return ""
    from OCP.collections import Sequence_TCollection_AsciiString as TColStd_SequenceOfAsciiString
    lu, au, su = TColStd_SequenceOfAsciiString(), TColStd_SequenceOfAsciiString(), TColStd_SequenceOfAsciiString()
    reader.ChangeReader().FileUnits(lu, au, su)
    return lu.Value(1).ToCString() if lu.Length() else ""


def _check_shapes(cad: CADModel, report) -> None:
    from OCP.BRepCheck import BRepCheck_Analyzer
    invalid = 0
    for p in cad.parts:
        try:
            if not BRepCheck_Analyzer(p.shape).IsValid():
                invalid += 1
        except Exception:
            invalid += 1
    if invalid:
        report.warn(f"{invalid} forma(s) B-Rep no superan la comprobación de validez de OCCT "
                    "(se procesan igualmente; revise el resultado).")


def shape_stats(shape) -> dict:
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    out = {}
    for key, kind in (("solidos", TopAbs_ShapeEnum.TopAbs_SOLID), ("caras", TopAbs_ShapeEnum.TopAbs_FACE)):
        exp = TopExp_Explorer(shape, kind)
        n = 0
        while exp.More():
            n += 1
            exp.Next()
        out[key] = n
    return out


# ============================================================================ escritura

def _record_write(report, key: str, value, seconds: float, path: str | None = None) -> None:
    tech = getattr(report, "technical", None)
    if tech is None:
        return
    w = tech.setdefault("escritura_cad", {})
    w[key] = value
    w[key + "_s"] = round(seconds, 2)
    if path and os.path.isfile(path):
        w["bytes"] = os.path.getsize(path)


def write_cad(cad: CADModel, path: str, fmt: str, report, step_schema: str = "AP214",
              keep_structure: bool = True) -> list[str]:
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType

    parts = [p for p in cad.parts if p.shape is not None and not p.shape.IsNull()]
    if not parts:
        raise ValueError("No hay formas B-Rep para exportar.")
    doc = _new_doc()
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    def set_name(label, name):
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(str(name), True))

    use_asm = keep_structure and fmt == "step" and (len(parts) > 1 or any(p.path for p in parts))
    asm_labels: dict[tuple, object] = {}

    def assembly(path_names: tuple):
        if path_names in asm_labels:
            return asm_labels[path_names]
        lab = shape_tool.NewShape()
        set_name(lab, path_names[-1] if path_names else cad.name)
        if path_names:
            parent = assembly(path_names[:-1])
            comp = shape_tool.AddComponent(parent, lab, TopLoc_Location())
            set_name(comp, path_names[-1])
        asm_labels[path_names] = lab
        return lab

    def rel_path(path_names: tuple) -> tuple:
        # el ensamblaje raíz ya lleva el nombre del modelo: no duplicarlo
        return tuple(path_names[1:]) if path_names and path_names[0] == cad.name else tuple(path_names)

    for p in parts:
        # En ensamblajes la ubicación va en el componente (así los estilos/colores se conservan)
        base = p.shape.Located(TopLoc_Location()) if use_asm else p.shape
        lab = shape_tool.AddShape(base, False)
        set_name(lab, p.name)
        if p.color is not None:
            color_tool.SetColor(lab, Quantity_Color(float(p.color[0]), float(p.color[1]), float(p.color[2]),
                                                    Quantity_TypeOfColor.Quantity_TOC_RGB),
                                XCAFDoc_ColorType.XCAFDoc_ColorSurf)
        if use_asm:
            parent = assembly(rel_path(tuple(p.path)))
            comp = shape_tool.AddComponent(parent, lab, p.shape.Location())
            set_name(comp, p.name)
    if use_asm:
        shape_tool.UpdateAssemblies()

    if fmt == "step":
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.STEPControl import STEPControl_Controller
        STEPControl_Controller.Init_s()            # registra los parámetros estáticos antes de fijarlos
        schema = {"AP203": "AP203", "AP214": "AP214IS", "AP242": "AP242DIS"}.get(step_schema, "AP214IS")
        _static("write.step.schema", schema)
        _static("write.step.unit", "MM")
        _static("write.step.product.name", cad.name)
        writer = STEPCAFControl_Writer()
        writer.SetNameMode(True)
        writer.SetColorMode(True)
        set_stage = getattr(report, "set_stage", lambda s: None)
        set_stage("transferencia STEP")
        t0 = time.time()
        transferred = bool(writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs))
        _record_write(report, "transferencia", transferred, time.time() - t0)
        if not transferred:
            raise ValueError("OCCT no pudo transferir la geometría a STEP.")
        set_stage("escritura STEP")
        t0 = time.time()
        status = writer.Write(path)
        _record_write(report, "escritura", getattr(status, "name", str(status)), time.time() - t0, path)
    else:
        from OCP.IGESCAFControl import IGESCAFControl_Writer
        from OCP.IGESControl import IGESControl_Controller
        IGESControl_Controller.Init_s()            # registra los parámetros estáticos antes de fijarlos
        _static("write.iges.unit", "MM")
        _static("write.iges.brep.mode", 1)            # sólidos B-Rep (entidades 186/514)
        writer = IGESCAFControl_Writer()
        writer.SetNameMode(True)
        writer.SetColorMode(True)
        set_stage = getattr(report, "set_stage", lambda s: None)
        set_stage("transferencia IGES")
        t0 = time.time()
        transferred = bool(writer.Transfer(doc))
        _record_write(report, "transferencia", transferred, time.time() - t0)
        if not transferred:
            raise ValueError("OCCT no pudo transferir la geometría a IGES.")
        set_stage("escritura IGES")
        t0 = time.time()
        status = writer.Write(path)
        _record_write(report, "escritura", status if isinstance(status, bool) else getattr(status, "name", str(status)),
                      time.time() - t0, path)
        if keep_structure and any(p.path for p in parts):
            report.loss("IGES: la jerarquía de ensamblaje se aplana (piezas independientes con nombre).")
    ok = status if isinstance(status, bool) else status == IFSelect_ReturnStatus.IFSelect_RetDone
    if not ok or not os.path.isfile(path):
        raise ValueError(f"OCCT no pudo escribir el archivo {fmt.upper()}.")
    return [path]


# ============================================================================ CAD → malla

def tessellation_params(cad: CADModel, options) -> tuple[float, float, float]:
    from ...core.options import QUALITY_PRESETS
    bb = cad.bounds()
    diag = float(np.linalg.norm(bb[1] - bb[0])) if bb is not None else 1000.0
    rel, ang = QUALITY_PRESETS.get(options.quality, QUALITY_PRESETS["alta"])
    lin = options.linear_tolerance_mm if options.linear_tolerance_mm else diag * rel
    if options.angular_tolerance_rad:
        ang = options.angular_tolerance_rad
    lin = max(lin, diag * 1e-7, 1e-6)
    return lin, ang, diag


def tessellate(cad: CADModel, options, report, progress=None) -> SceneModel:
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_Orientation
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    lin, ang, diag = tessellation_params(cad, options)
    report.info(f"Teselación: tolerancia lineal {lin:.4g} mm, angular {np.degrees(ang):.1f}°")
    scene = SceneModel(name=cad.name)
    scene.metadata.update({"unit_m": 1.0, "up": "Z", "tolerance_mm": lin})   # salida en metros
    mat_cache: dict[tuple, int] = {}
    group_nodes: dict[tuple, int] = {}

    def group(path_names: tuple):
        if not path_names:
            return None
        if path_names in group_nodes:
            return group_nodes[path_names]
        parent = group(path_names[:-1])
        group_nodes[path_names] = scene.add_node(SceneNode(name=path_names[-1]), parent)
        return group_nodes[path_names]

    empty = 0
    for pi, part in enumerate(cad.parts):
        if progress:
            progress(pi / max(1, len(cad.parts)), f"Teselando {part.name}")
        BRepMesh_IncrementalMesh(part.shape, lin, False, ang, True)
        verts, tris, norms = [], [], []
        off = 0
        exp = TopExp_Explorer(part.shape, TopAbs_ShapeEnum.TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face(exp.Current())
            exp.Next()
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is None:
                continue
            trsf = loc.Transformation()
            nn = tri.NbNodes()
            pts = np.empty((nn, 3))
            for i in range(1, nn + 1):
                p = tri.Node(i).Transformed(trsf)
                pts[i - 1] = (p.X(), p.Y(), p.Z())
            nt = tri.NbTriangles()
            t = np.empty((nt, 3), dtype=np.int64)
            for i in range(1, nt + 1):
                t[i - 1] = tri.Triangle(i).Get()
            t -= 1
            if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
                t = t[:, ::-1]
            norms.append(compute_vertex_normals(pts, t))
            verts.append(pts)
            tris.append(t + off)
            off += nn
        if not tris:
            empty += 1
            continue
        V = np.concatenate(verts) * 0.001          # mm → m
        F = np.concatenate(tris)
        N = np.concatenate(norms)
        # triángulos de área nula (polos de esferas, bordes de empalmes): se eliminan
        tv = V[F]
        area2 = np.linalg.norm(np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0]), axis=1)
        keep = area2 > (max(diag, 1e-9) * 1e-3 * 1e-9) ** 2
        if not keep.all():
            F = F[keep]
        mat = None
        if options.keep_materials and part.color is not None:
            key = tuple(round(c, 4) for c in part.color)
            if key not in mat_cache:
                mat_cache[key] = scene.add_material(Material(name=f"color_{len(mat_cache) + 1}",
                                                             base_color=(*part.color, 1.0), roughness=0.5))
            mat = mat_cache[key]
        mi = scene.add_mesh(Mesh(name=part.name, vertices=V, faces=F, normals=N, material=mat))
        parent = group(tuple(part.path)) if options.keep_structure else None
        scene.add_node(SceneNode(name=part.name, meshes=[mi], properties=dict(part.properties)), parent)
    if empty:
        report.warn(f"{empty} pieza(s) sin caras teselables (curvas, puntos o formas vacías) se omiten.")
    if not scene.meshes:
        raise ValueError("La teselación no produjo triángulos (el modelo no contiene superficies).")
    return scene


# ============================================================================ malla → B-Rep facetado

def scene_to_cad(scene: SceneModel, options, report, progress=None) -> CADModel:
    """Malla (m) → CAD (mm) facetado. Cada componente conectado de cada malla es una pieza.

    Delegado en mesh_to_brep: análisis, reparación, estimación de recursos, simplificación opcional y
    construcción nativa (BRepBuilderAPI_MakeShapeOnMesh). Registra todo en report.technical.
    """
    import copy
    from . import mesh_to_brep as mb

    set_stage = getattr(report, "set_stage", lambda s: None)
    set_stage("estimación de recursos")
    total = scene.triangle_count()
    avail = mb.available_memory_mb()
    affordable = mb.max_affordable_triangles(avail, options.timeout_s)
    budget = min(int(options.max_triangles_to_cad), affordable)
    limit_reason = ("limitado por la memoria libre y el tiempo máximo" if affordable < int(options.max_triangles_to_cad)
                    else "limitado por el límite de triángulos → CAD")
    tech = {"triangulos_totales": int(total), "memoria_disponible_mb": round(avail), "limite_triangulos": budget,
            "estimacion_sin_simplificar": mb.estimate(total), "mallas": []}
    if hasattr(report, "technical"):
        report.technical["malla_a_brep"] = tech
    report.info(f"Recursos: {round(avail):,} MB de memoria libre; límite de B-Rep facetado: {budget:,} triángulos.")
    target_total = min(int(getattr(options, "mesh_target_triangles", 100_000)), budget)
    cad = CADModel(name=scene.name)
    parents = {idx: parent for idx, _, parent in scene.iter_nodes()}
    built = {"sólido": 0, "superficie": 0, "superficie no manifold": 0}
    done = 0
    for idx, world, parent in list(scene.iter_nodes()):
        node = scene.nodes[idx]
        path = []
        p = parent
        while p is not None:
            path.insert(0, scene.nodes[p].name)
            p = parents[p]
        for mi in node.meshes:
            mesh = scene.meshes[mi]
            if len(mesh.faces) == 0:
                continue
            v = mesh.vertices @ world[:3, :3].T + world[:3, 3]
            f = mesh.faces[:, ::-1] if np.linalg.det(world[:3, :3]) < 0 else mesh.faces
            name = node.name if len(node.meshes) == 1 else f"{node.name}_{mesh.name}"
            share = len(f) / max(total, 1)
            mopts = copy.copy(options)
            mopts.mesh_target_triangles = max(1000, int(target_total * share)) if total > target_total else target_total
            mopts.resource_limited_target = target_total < int(getattr(options, "mesh_target_triangles", 100_000))
            mopts.resource_limit_reason = limit_reason
            mopts.hard_triangle_budget = max(1000, int(min(int(options.max_triangles_to_cad),
                                                           mb.max_affordable_triangles(avail, options.timeout_s, 1.0)) * share))
            mbudget = max(1000, int(budget * share))

            def prog(fr, msg, d=done, n=len(f)):
                if progress:
                    progress((d + fr * n) / max(total, 1), msg)

            mtech: dict = {}
            tech["mallas"].append(mtech)
            parts, _ = mb.mesh_to_parts(np.asarray(v, np.float64) * 1000.0, np.asarray(f, np.int64), name,
                                        mopts, report, mbudget, prog, tech=mtech)
            done += len(f)
            color = None
            if mesh.material is not None and mesh.material < len(scene.materials):
                color = tuple(scene.materials[mesh.material].base_color[:3])
            for pname, shape, kind in parts:
                built[kind] += 1
                cad.parts.append(CadPart(name=pname, shape=shape, color=color,
                                         path=tuple(path) if options.keep_structure else (), faceted=True,
                                         properties={"tipo": kind}))
    if not cad.parts:
        raise ValueError("No hay geometría para convertir a B-Rep.")
    tech["resultado"] = built
    return cad
