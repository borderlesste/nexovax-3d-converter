"""Motor BIM basado en IfcOpenShell (LGPL-3.0).

* Lectura IFC2X3 / IFC4 / IFC4X3 (validación de esquema y contenido).
* IFC → SceneModel: teselación por elemento, instancias de geometría compartida,
  jerarquía espacial (Proyecto/Sitio/Edificio/Planta), estilos y propiedades (psets).
* IFC → CADModel: geometría B-Rep exacta generada por IfcOpenShell/OCCT.
* SceneModel → IFC: entidades genéricas IfcBuildingElementProxy con representación de malla.
"""
from __future__ import annotations

import multiprocessing
import os
import tempfile
import time

import numpy as np

from ... import APP_NAME, __version__
from ...models.bim import BIMModel
from ...models.cad import CADModel, CadPart
from ...models.scene import SceneModel, SceneNode, Mesh, Material

EXCLUDED_CLASSES = ("IfcOpeningElement", "IfcSpace", "IfcVirtualElement", "IfcAnnotation", "IfcGrid")


# ============================================================================ lectura

def read_ifc(path: str, report) -> BIMModel:
    import ifcopenshell
    try:
        f = ifcopenshell.open(path)
    except Exception as e:
        raise ValueError(f"IfcOpenShell no pudo abrir el IFC: {e}")
    schema = f.schema
    if schema not in ("IFC2X3", "IFC4", "IFC4X3", "IFC4X3_ADD2", "IFC4X1", "IFC4X2"):
        report.warn(f"Esquema IFC poco habitual ({schema}); se intenta procesar igualmente.")
    bim = BIMModel(ifc=f, path=path, schema=schema, name=os.path.splitext(os.path.basename(path))[0])
    projects = f.by_type("IfcProject")
    if projects and projects[0].Name:
        bim.name = projects[0].Name
    n = len(bim.products_with_geometry())
    report.info(f"IFC {schema}: {len(f.by_type('IfcProduct'))} productos, {n} con representación geométrica.")
    if n == 0:
        raise ValueError("El IFC no contiene productos con geometría.")
    return bim


def _settings(options, brep: bool = False):
    import ifcopenshell.geom as geom
    s = geom.settings()
    s.set("use-world-coords", False)
    s.set("apply-default-materials", True)
    s.set("weld-vertices", True)
    if brep:
        s.set("iterator-output", s.SERIALIZED)
    else:
        from ...core.options import QUALITY_PRESETS
        rel, ang = QUALITY_PRESETS.get(options.quality, QUALITY_PRESETS["alta"])
        lin_m = (options.linear_tolerance_mm / 1000.0) if options.linear_tolerance_mm else None
        if lin_m:
            s.set("mesher-linear-deflection", float(lin_m))
        else:
            # deflexión absoluta razonable para arquitectura según la calidad
            s.set("mesher-linear-deflection", {"baja": 0.02, "media": 0.005, "alta": 0.001,
                                                "muy_alta": 0.0002}.get(options.quality, 0.001))
        s.set("mesher-angular-deflection", float(options.angular_tolerance_rad or ang))
    return s


def _iterate(bim: BIMModel, settings, report, progress=None):
    import ifcopenshell.geom as geom
    threads = max(1, min(8, (multiprocessing.cpu_count() or 2) - 1))
    it = geom.iterator(settings, bim.ifc, threads, exclude=list(EXCLUDED_CLASSES))
    if not it.initialize():
        raise ValueError("IfcOpenShell no pudo generar geometría para ningún elemento.")
    count = 0
    while True:
        shape = it.get()
        count += 1
        if progress and count % 25 == 0:
            progress(min(0.99, it.progress() / 100.0), f"Procesando geometría IFC ({count} elementos)")
        yield shape
        if not it.next():
            break


def _spatial_path(element) -> list:
    """Cadena de contenedores/agregados desde el proyecto hasta el elemento (excluido)."""
    import ifcopenshell.util.element as ue
    chain = []
    cur = element
    seen = set()
    while cur is not None and cur.id() not in seen:
        seen.add(cur.id())
        parent = ue.get_aggregate(cur) or ue.get_container(cur) or getattr(ue, "get_nest", lambda e: None)(cur)
        if parent is None:
            break
        chain.insert(0, parent)
        cur = parent
    return chain


def _label(e) -> str:
    name = getattr(e, "Name", None)
    return str(name) if name else e.is_a()


def _props(element, include: bool) -> dict:
    props = {"GlobalId": getattr(element, "GlobalId", ""), "IfcClass": element.is_a()}
    for attr in ("Name", "Description", "ObjectType", "Tag", "PredefinedType"):
        v = getattr(element, attr, None) if hasattr(element, attr) else None
        if v not in (None, ""):
            props[attr] = str(v)
    if include:
        try:
            import ifcopenshell.util.element as ue
            psets = ue.get_psets(element)
            for pname, pvals in psets.items():
                props[pname] = {k: v for k, v in pvals.items() if k != "id"}
        except Exception:
            pass
    return props


# ============================================================================ IFC → malla

def bim_to_scene(bim: BIMModel, options, report, progress=None) -> SceneModel:
    import ifcopenshell.util.shape as ushape

    scene = SceneModel(name=bim.name)
    scene.metadata.update({"unit_m": 1.0, "up": "Z"})
    mat_cache: dict[tuple, int] = {}
    geom_cache: dict[str, list[int]] = {}
    group_nodes: dict[int, int] = {}
    failed = 0
    processed = 0

    def group(entity) -> int | None:
        if entity.id() in group_nodes:
            return group_nodes[entity.id()]
        chain = _spatial_path(entity)
        parent = group(chain[-1]) if chain else None
        node = SceneNode(name=_label(entity), kind=entity.is_a(),
                         properties=_props(entity, False) if options.include_properties else {})
        group_nodes[entity.id()] = scene.add_node(node, parent)
        return group_nodes[entity.id()]

    def material(m) -> int | None:
        if not options.keep_materials or m is None:
            return None
        try:
            rgb = tuple(float(c) for c in m.diffuse.components)
        except Exception:
            rgb = (0.8, 0.8, 0.8)
        alpha = 1.0
        try:
            if m.has_transparency:
                alpha = 1.0 - float(m.transparency)
        except Exception:
            pass
        key = (m.name, rgb, round(alpha, 3))
        if key not in mat_cache:
            mat_cache[key] = scene.add_material(Material(name=m.name or "material", base_color=(*rgb, alpha),
                                                         roughness=0.7, double_sided=alpha < 1))
        return mat_cache[key]

    for shape in _iterate(bim, _settings(options), report, progress):
        try:
            element = bim.ifc.by_id(shape.id)
            g = shape.geometry
            gid = str(g.id)
            if gid not in geom_cache:
                verts = np.asarray(g.verts, dtype=float).reshape(-1, 3)
                faces = np.asarray(g.faces, dtype=np.int64).reshape(-1, 3)
                mats = list(g.materials)
                mids = np.asarray(g.material_ids, dtype=np.int64)
                meshes = []
                if len(faces):
                    if len(mids) != len(faces):
                        mids = np.zeros(len(faces), np.int64)
                    for mi in np.unique(mids):
                        sel = faces[mids == mi]
                        used, inv = np.unique(sel, return_inverse=True)
                        mat = material(mats[mi]) if 0 <= mi < len(mats) else None
                        name = _label(element) if len(np.unique(mids)) == 1 else f"{_label(element)}_{mats[mi].name if 0 <= mi < len(mats) else mi}"
                        normals = None
                        try:
                            nr = np.asarray(g.normals, dtype=float).reshape(-1, 3)
                            if len(nr) == len(verts):
                                normals = nr[used]
                        except Exception:
                            pass
                        meshes.append(scene.add_mesh(Mesh(name=name, vertices=verts[used], faces=inv.reshape(-1, 3),
                                                          normals=normals, material=mat)))
                geom_cache[gid] = meshes
            if not geom_cache[gid]:
                continue
            matrix = np.asarray(ushape.get_shape_matrix(shape), dtype=float)
            chain = _spatial_path(element) if options.keep_structure else []
            parent = group(chain[-1]) if chain else None
            scene.add_node(SceneNode(name=_label(element), matrix=matrix, meshes=list(geom_cache[gid]),
                                     kind=element.is_a(),
                                     properties=_props(element, options.include_properties)), parent)
            processed += 1
        except Exception as e:  # un elemento defectuoso no detiene la conversión
            failed += 1
            if failed <= 5:
                report.warn(f"Elemento IFC #{getattr(shape, 'id', '?')} omitido: {e}")
    expected = len([p for p in bim.products_with_geometry() if not p.is_a() in EXCLUDED_CLASSES
                    and not any(p.is_a(c) for c in EXCLUDED_CLASSES)])
    if processed < expected:
        report.warn(f"Se procesaron {processed} de {expected} elementos con representación "
                    "(algunos no tienen geometría de cuerpo 3D válida).")
    if failed > 5:
        report.warn(f"... y {failed - 5} elementos más omitidos.")
    if bim.ifc.by_type("IfcSpace"):
        report.loss(f"{len(bim.ifc.by_type('IfcSpace'))} espacio(s) IfcSpace no se exportan como geometría.")
    if not scene.meshes:
        raise ValueError("IfcOpenShell no produjo geometría triangulada.")
    if not options.include_properties:
        report.loss("Propiedades IFC (psets) no incluidas por configuración.")
    return scene


# ============================================================================ IFC → B-Rep

def bim_to_cad(bim: BIMModel, options, report, progress=None) -> CADModel:
    import ifcopenshell.util.shape as ushape
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    from OCP.gp import gp_Trsf, gp_GTrsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

    cad = CADModel(name=bim.name)
    tmpdir = tempfile.mkdtemp(prefix="u3dc_brep_")
    failed = 0
    try:
        for shape in _iterate(bim, _settings(options, brep=True), report, progress):
            try:
                element = bim.ifc.by_id(shape.id)
                data = shape.geometry.brep_data
                if not data:
                    continue
                fn = os.path.join(tmpdir, f"{shape.id}.brep")
                with open(fn, "w", encoding="ascii", errors="ignore") as fh:
                    fh.write(data)
                occ = TopoDS_Shape()
                if not BRepTools.Read_s(occ, fn, BRep_Builder()) or occ.IsNull():
                    raise ValueError("BRep vacío")
                os.remove(fn)
                m = np.asarray(ushape.get_shape_matrix(shape), dtype=float)
                # Colocación (m) y escala a mm
                t = gp_Trsf()
                r = m[:3, :3]
                t.SetValues(float(r[0, 0]), float(r[0, 1]), float(r[0, 2]), float(m[0, 3] * 1000.0),
                            float(r[1, 0]), float(r[1, 1]), float(r[1, 2]), float(m[1, 3] * 1000.0),
                            float(r[2, 0]), float(r[2, 1]), float(r[2, 2]), float(m[2, 3] * 1000.0))
                s = gp_Trsf()
                s.SetScaleFactor(1000.0)
                occ = BRepBuilderAPI_Transform(occ, s, True).Shape()
                occ = BRepBuilderAPI_Transform(occ, t, False).Shape()
                color = None
                try:
                    styles = list(shape.geometry.surface_styles)
                    if styles:
                        color = tuple(float(c) for c in styles[0].diffuse.components)
                except Exception:
                    pass
                path = tuple(_label(e) for e in _spatial_path(element)) if options.keep_structure else ()
                cad.parts.append(CadPart(name=_label(element), shape=occ, color=color, path=path,
                                         properties={"GlobalId": element.GlobalId, "IfcClass": element.is_a()}))
            except Exception as e:
                failed += 1
                if failed <= 5:
                    report.warn(f"Elemento IFC #{getattr(shape, 'id', '?')} sin B-Rep exportable: {e}")
    finally:
        try:
            for fn in os.listdir(tmpdir):
                os.remove(os.path.join(tmpdir, fn))
            os.rmdir(tmpdir)
        except OSError:
            pass
    if failed > 5:
        report.warn(f"... y {failed - 5} elementos más sin B-Rep.")
    if not cad.parts:
        raise ValueError("No se pudo obtener geometría B-Rep de ningún elemento IFC.")
    report.info(f"{len(cad.parts)} elemento(s) IFC convertidos a B-Rep exacto.")
    return cad


# ============================================================================ malla → IFC

def scene_to_bim(scene: SceneModel, options, report, source_name: str = "", source_format: str = "",
                 progress=None) -> BIMModel:
    import ifcopenshell
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.project
    import ifcopenshell.api.pset
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.style
    import ifcopenshell.api.unit
    import ifcopenshell.api.owner
    api = ifcopenshell.api

    schema = options.ifc_schema if options.ifc_schema in ("IFC4", "IFC2X3") else "IFC4"
    f = api.project.create_file(version=schema)
    _owner_history(f, schema)
    project = api.root.create_entity(f, ifc_class="IfcProject", name=scene.name or "Proyecto")
    api.unit.assign_unit(f, length={"is_metric": True, "raw": "METERS"})
    model = api.context.add_context(f, context_type="Model")
    body = api.context.add_context(f, context_type="Model", context_identifier="Body",
                                   target_view="MODEL_VIEW", parent=model)
    site = api.root.create_entity(f, ifc_class="IfcSite", name="Sitio")
    building = api.root.create_entity(f, ifc_class="IfcBuilding", name="Edificio")
    storey = api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="Planta")
    api.aggregate.assign_object(f, products=[site], relating_object=project)
    api.aggregate.assign_object(f, products=[building], relating_object=site)
    api.aggregate.assign_object(f, products=[storey], relating_object=building)
    for e in (site, building, storey):
        api.geometry.edit_object_placement(f, product=e, matrix=np.eye(4))

    styles: dict[int, object] = {}

    def style_for(mi):
        if mi is None or not options.keep_materials or mi >= len(scene.materials):
            return None
        if mi not in styles:
            m = scene.materials[mi]
            styles[mi] = add_color_style(f, m.name, m.base_color[:3], 1.0 - m.base_color[3])
        return styles[mi]

    parents = {idx: parent for idx, _, parent in scene.iter_nodes()}
    products = []
    count = 0
    total = max(1, scene.triangle_count())
    done = 0
    for idx, world, parent in scene.iter_nodes():
        node = scene.nodes[idx]
        for mi in node.meshes:
            mesh = scene.meshes[mi]
            if len(mesh.faces) == 0:
                continue
            count += 1
            if progress:
                progress(done / total, f"Creando entidad IFC {count}")
            done += len(mesh.faces)
            name = node.name if len(node.meshes) == 1 else f"{node.name}_{mesh.name}"
            elem = api.root.create_entity(f, ifc_class="IfcBuildingElementProxy", name=name)
            a = world[:3, :3]
            rigid = np.allclose(a.T @ a, np.eye(3), atol=1e-6) and np.linalg.det(a) > 0
            if rigid:
                verts, place = mesh.vertices, world
            else:   # escala/cizalla/espejo: se aplica a los vértices (IFC no admite escala en la colocación)
                verts = mesh.vertices @ a.T + world[:3, 3]
                place = np.eye(4)
            faces = mesh.faces if np.linalg.det(a) >= 0 else mesh.faces[:, ::-1]
            rep = api.geometry.add_mesh_representation(
                f, context=body, vertices=[np.asarray(verts, dtype=float).tolist()],
                faces=[np.asarray(faces, dtype=int).tolist()], force_faceted_brep=(schema == "IFC2X3"))
            api.geometry.assign_representation(f, product=elem, representation=rep)
            api.geometry.edit_object_placement(f, product=elem, matrix=np.asarray(place, dtype=float), is_si=True)
            st = style_for(mesh.material)
            if st is not None:
                api.style.assign_representation_styles(f, shape_representation=rep, styles=[st])
            path = []
            p = parent
            while p is not None:
                path.insert(0, scene.nodes[p].name)
                p = parents.get(p)
            if options.include_properties:
                props = {"ArchivoOrigen": source_name, "FormatoOrigen": source_format, "NombreOrigen": node.name}
                if path:
                    props["RutaJerarquia"] = "/".join(path)
                for k, v in node.properties.items():
                    if isinstance(v, (str, int, float, bool)) and len(props) < 60:
                        props[f"Origen_{k}"[:255]] = v if not isinstance(v, str) else v[:255]
                pset = api.pset.add_pset(f, product=elem, name="NEXOVAX_Origen")
                api.pset.edit_pset(f, pset=pset, properties=props)
            products.append(elem)
    if not products:
        raise ValueError("No hay geometría para crear entidades IFC.")
    api.spatial.assign_container(f, products=products, relating_structure=storey)
    report.info(f"IFC {schema}: {len(products)} IfcBuildingElementProxy creados con representación de malla.")
    return BIMModel(ifc=f, schema=schema, name=scene.name)


def add_color_style(f, name: str, rgb, transparency: float = 0.0):
    """Estilo de superficie con color (IFC4: Shading; IFC2X3: Rendering, que admite transparencia)."""
    import ifcopenshell.api.style
    api = ifcopenshell.api
    st = api.style.add_style(f, name=name)
    colour = {"Name": None, "Red": float(rgb[0]), "Green": float(rgb[1]), "Blue": float(rgb[2])}
    if f.schema == "IFC2X3":
        api.style.add_surface_style(f, style=st, ifc_class="IfcSurfaceStyleRendering", attributes={
            "SurfaceColour": colour, "Transparency": float(transparency), "ReflectanceMethod": "NOTDEFINED"})
    else:
        api.style.add_surface_style(f, style=st, ifc_class="IfcSurfaceStyleShading", attributes={
            "SurfaceColour": colour, "Transparency": float(transparency)})
    return st


def _owner_history(f, schema):
    """IFC2X3 exige OwnerHistory; se crea uno mínimo identificando la aplicación."""
    if schema != "IFC2X3":
        return
    import ifcopenshell.api.owner
    import ifcopenshell.api.owner.settings as osettings
    person = f.createIfcPerson(None, None, "Usuario", None, None, None, None, None)
    org = f.createIfcOrganization(None, APP_NAME, None, None, None)
    user = f.createIfcPersonAndOrganization(person, org, None)
    app = f.createIfcApplication(org, __version__, APP_NAME, "NEXOVAX")
    osettings.get_user = lambda ifc: user
    osettings.get_application = lambda ifc: app


def write_ifc(bim: BIMModel, path: str, report) -> list[str]:
    bim.ifc.write(path)
    return [path]
