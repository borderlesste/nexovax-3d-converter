"""Genera los archivos de ejemplo de los ocho formatos en test_assets/.

Uso:  python tests/make_assets.py [carpeta]
Los modelos se crean con los propios motores (OCCT, IfcOpenShell) o se escriben a mano
(FBX ASCII, OBJ, STL ASCII) para no depender únicamente de nuestros exportadores.
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ----------------------------------------------------------------------------- CAD

def make_cad(out: str):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeTorus
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir, gp_Trsf, gp_Vec
    from u3dc.models.cad import CADModel, CadPart
    from u3dc.core.report import ConversionReport
    from u3dc.engines.cad.occt import write_cad

    def moved(shape, x, y, z):
        t = gp_Trsf()
        t.SetTranslation(gp_Vec(x, y, z))
        return BRepBuilderAPI_Transform(shape, t, True).Shape()

    plate = BRepPrimAPI_MakeBox(120.0, 80.0, 10.0).Shape()
    fil = BRepFilletAPI_MakeFillet(plate)
    exp = TopExp_Explorer(plate, TopAbs_ShapeEnum.TopAbs_EDGE)
    while exp.More():
        fil.Add(2.0, TopoDS.Edge(exp.Current()))
        exp.Next()
    plate = fil.Shape()
    for x, y in ((20, 20), (100, 20), (20, 60), (100, 60)):
        plate = BRepAlgoAPI_Cut(plate, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, -1), gp_Dir(0, 0, 1)), 5, 12).Shape()).Shape()
    boss = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(60, 40, 10), gp_Dir(0, 0, 1)), 18, 25).Shape()
    plate = BRepAlgoAPI_Fuse(plate, boss).Shape()
    plate = BRepAlgoAPI_Cut(plate, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(60, 40, 0), gp_Dir(0, 0, 1)), 8, 40).Shape()).Shape()
    pin = moved(BRepPrimAPI_MakeCylinder(4.8, 30).Shape(), 20, 20, -10)
    ball = moved(BRepPrimAPI_MakeSphere(12).Shape(), 60, 40, 60)
    torus = moved(BRepPrimAPI_MakeTorus(30, 4).Shape(), 60, 40, 20)
    cad = CADModel(name="ensamblaje_mecanico", parts=[
        CadPart("placa_base", plate, (0.70, 0.72, 0.75), ("ensamblaje_mecanico", "subconjunto_base")),
        CadPart("pasador", pin, (0.85, 0.65, 0.20), ("ensamblaje_mecanico", "subconjunto_base")),
        CadPart("esfera", ball, (0.80, 0.10, 0.10), ("ensamblaje_mecanico",)),
        CadPart("toroide", torus, (0.10, 0.30, 0.80), ("ensamblaje_mecanico",)),
    ])
    r = ConversionReport("assets")
    write_cad(cad, os.path.join(out, "ensamblaje_mecanico.step"), "step", r)
    write_cad(cad, os.path.join(out, "ensamblaje_mecanico.igs"), "iges", r)
    one = CADModel(name="pieza_ñandú", parts=[CadPart("pieza_ñandú", plate, (0.3, 0.6, 0.3))])
    write_cad(one, os.path.join(out, "pieza_ñandú.stp"), "step", r)
    write_cad(one, os.path.join(out, "pieza_curva.iges"), "iges", r)


# ----------------------------------------------------------------------------- IFC

def make_ifc(out: str, schema: str, name: str, n_storeys: int = 2):
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
    from u3dc.engines.bim.ifc import _owner_history
    api = ifcopenshell.api

    f = api.project.create_file(version=schema)
    _owner_history(f, schema)
    project = api.root.create_entity(f, ifc_class="IfcProject", name=name)
    api.unit.assign_unit(f, length={"is_metric": True, "raw": "METERS"})
    model = api.context.add_context(f, context_type="Model")
    body = api.context.add_context(f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model)
    site = api.root.create_entity(f, ifc_class="IfcSite", name="Parcela")
    bld = api.root.create_entity(f, ifc_class="IfcBuilding", name="Edificio de oficinas")
    api.aggregate.assign_object(f, products=[site], relating_object=project)
    api.aggregate.assign_object(f, products=[bld], relating_object=site)
    for e in (site, bld):
        api.geometry.edit_object_placement(f, product=e, matrix=np.eye(4))

    from u3dc.engines.bim.ifc import add_color_style

    def style(nm, rgb, transp=0.0):
        return add_color_style(f, nm, rgb, transp)

    s_wall, s_slab, s_col = style("Hormigón", (0.75, 0.75, 0.72)), style("Forjado", (0.55, 0.55, 0.6)), style("Acero", (0.3, 0.35, 0.5))
    L, W, H = 12.0, 8.0, 3.0
    for k in range(n_storeys):
        z = k * H
        st = api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=f"Planta {k}")
        api.aggregate.assign_object(f, products=[st], relating_object=bld)
        m = np.eye(4); m[2, 3] = z
        api.geometry.edit_object_placement(f, product=st, matrix=m)
        elems = []
        walls = [((0, 0), 0, L), ((L, 0), 90, W), ((L, W), 180, L), ((0, W), 270, W)]
        for i, ((x, y), ang, length) in enumerate(walls):
            w = api.root.create_entity(f, ifc_class="IfcWall" if schema != "IFC2X3" else "IfcWallStandardCase", name=f"Muro P{k}-{i + 1}")
            rep = api.geometry.add_wall_representation(f, context=body, length=length, height=H, thickness=0.25)
            api.geometry.assign_representation(f, product=w, representation=rep)
            a = np.radians(ang)
            mm = np.eye(4)
            mm[:2, :2] = [[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]
            mm[:3, 3] = [x, y, z]
            api.geometry.edit_object_placement(f, product=w, matrix=mm)
            api.style.assign_representation_styles(f, shape_representation=rep, styles=[s_wall])
            ps = api.pset.add_pset(f, product=w, name="Pset_WallCommon")
            api.pset.edit_pset(f, pset=ps, properties={"IsExternal": True, "LoadBearing": True, "Reference": "M-25"})
            elems.append(w)
        slab = api.root.create_entity(f, ifc_class="IfcSlab", name=f"Forjado P{k}")
        rep = api.geometry.add_slab_representation(f, context=body, depth=0.3,
                                                    polyline=[(0, 0), (L, 0), (L, W), (0, W), (0, 0)])
        api.geometry.assign_representation(f, product=slab, representation=rep)
        mm = np.eye(4); mm[2, 3] = z - 0.3
        api.geometry.edit_object_placement(f, product=slab, matrix=mm)
        api.style.assign_representation_styles(f, shape_representation=rep, styles=[s_slab])
        elems.append(slab)
        for j, (cx, cy) in enumerate(((4, 4), (8, 4))):
            col = api.root.create_entity(f, ifc_class="IfcColumn", name=f"Pilar P{k}-{j + 1}")
            pos = f.create_entity("IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0)))
            prof = f.create_entity("IfcCircleProfileDef", ProfileType="AREA", ProfileName="R200", Position=pos, Radius=0.2)
            rep = api.geometry.add_profile_representation(f, context=body, profile=prof, depth=H)
            api.geometry.assign_representation(f, product=col, representation=rep)
            mm = np.eye(4); mm[:3, 3] = [cx, cy, z]
            api.geometry.edit_object_placement(f, product=col, matrix=mm)
            api.style.assign_representation_styles(f, shape_representation=rep, styles=[s_col])
            ps = api.pset.add_pset(f, product=col, name="Pset_ColumnCommon")
            api.pset.edit_pset(f, pset=ps, properties={"LoadBearing": True})
            elems.append(col)
        api.spatial.assign_container(f, products=elems, relating_structure=st)
    f.write(os.path.join(out, name + ".ifc"))


# ----------------------------------------------------------------------------- mallas

def _png(color) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), color)
    d = ImageDraw.Draw(img)
    for i in range(0, 64, 16):
        d.rectangle([i, 0, i + 7, 63], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_obj(out: str):
    """OBJ escrito a mano: varios objetos, cuadriláteros, n-gono, UV, material con textura."""
    with open(os.path.join(out, "madera.png"), "wb") as fh:
        fh.write(_png((150, 100, 50)))
    with open(os.path.join(out, "mueble.mtl"), "w", encoding="utf-8") as fh:
        fh.write("newmtl Madera\nKd 0.6 0.4 0.2\nmap_Kd madera.png\n\nnewmtl Metal\nKd 0.7 0.7 0.75\nKs 0.9 0.9 0.9\nNs 200\n")
    lines = ["# mueble de prueba", "mtllib mueble.mtl"]
    vofs = 0
    vt_ofs = 0

    def box(name, x0, y0, z0, x1, y1, z1, mat):
        nonlocal vofs, vt_ofs
        lines.append(f"o {name}")
        for x in (x0, x1):
            for y in (y0, y1):
                for z in (z0, z1):
                    lines.append(f"v {x} {y} {z}")
        for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
            lines.append(f"vt {u} {v}")
        lines.append(f"usemtl {mat}")
        quads = [(1, 3, 4, 2), (5, 6, 8, 7), (1, 2, 6, 5), (3, 7, 8, 4), (1, 5, 7, 3), (2, 4, 8, 6)]
        for q in quads:
            lines.append("f " + " ".join(f"{a + vofs}/{k + 1 + vt_ofs}" for k, a in enumerate(q)))
        vofs += 8
        vt_ofs += 4

    box("Tablero", 0, 0.7, 0, 1.2, 0.74, 0.6, "Madera")
    for i, (x, z) in enumerate(((0.05, 0.05), (1.11, 0.05), (0.05, 0.51), (1.11, 0.51))):
        box(f"Pata_{i + 1}", x, 0, z, x + 0.04, 0.7, z + 0.04, "Metal")
    # hexágono (n-gono) como adorno
    lines.append("o Adorno_hexagonal")
    for k in range(6):
        a = np.pi / 3 * k
        lines.append(f"v {0.6 + 0.1 * np.cos(a):.6f} 0.741 {0.3 + 0.1 * np.sin(a):.6f}")
    lines.append("usemtl Metal")
    lines.append("f " + " ".join(str(vofs + k + 1) for k in range(6)))
    with open(os.path.join(out, "mueble.obj"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def make_stl(out: str):
    from u3dc.models.scene import SceneModel, SceneNode, Mesh
    from u3dc.engines.mesh.stl_io import write_stl
    from u3dc.core.report import ConversionReport

    def cyl(r, h, n=48):
        a = np.linspace(0, 2 * np.pi, n, endpoint=False)
        bot = np.c_[r * np.cos(a), r * np.sin(a), np.zeros(n)]
        top = bot + [0, 0, h]
        v = np.vstack([bot, top, [[0, 0, 0], [0, 0, h]]])
        f = []
        for i in range(n):
            j = (i + 1) % n
            f += [[i, j, n + j], [i, n + j, n + i], [2 * n, j, i], [2 * n + 1, n + i, n + j]]
        return v, np.array(f)

    v, f = cyl(20.0, 40.0)
    s = SceneModel(name="soporte")
    s.add_node(SceneNode("soporte", meshes=[s.add_mesh(Mesh("soporte", v, f))]))
    write_stl(s, os.path.join(out, "soporte_binario.stl"), ConversionReport("a"))
    # STL ASCII con dos sólidos escrito a mano
    with open(os.path.join(out, "dos_solidos_ascii.stl"), "w") as fh:
        for name, off in (("tetra_A", 0.0), ("tetra_B", 30.0)):
            pts = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], float) + [off, 0, 0]
            fh.write(f"solid {name}\n")
            for a, b, c in ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)):
                n = np.cross(pts[b] - pts[a], pts[c] - pts[a])
                n /= np.linalg.norm(n)
                fh.write(f"facet normal {n[0]} {n[1]} {n[2]}\n outer loop\n")
                for p in (pts[a], pts[b], pts[c]):
                    fh.write(f"  vertex {p[0]} {p[1]} {p[2]}\n")
                fh.write(" endloop\nendfacet\n")
            fh.write(f"endsolid {name}\n")


def make_gltf(out: str):
    """glTF escrito a mano (JSON + .bin + textura) con jerarquía, instancias y extras."""
    v = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)], np.float32)
    idx = np.array([0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5, 0, 4, 5, 0, 5, 1, 2, 3, 7, 2, 7, 6, 0, 2, 6, 0, 6, 4, 1, 5, 7, 1, 7, 3], np.uint16)
    uv = np.c_[v[:, 0] + .5, v[:, 1] + .5].astype(np.float32)
    binary = v.tobytes() + uv.tobytes() + idx.tobytes()
    with open(os.path.join(out, "escena.bin"), "wb") as fh:
        fh.write(binary)
    with open(os.path.join(out, "escena_textura.png"), "wb") as fh:
        fh.write(_png((40, 120, 200)))
    doc = {
        "asset": {"version": "2.0", "generator": "make_assets"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": "Raíz", "children": [1, 2, 3], "extras": {"proyecto": "prueba"}},
            {"name": "Cubo_A", "mesh": 0, "translation": [0, 0.5, 0]},
            {"name": "Cubo_B", "mesh": 0, "translation": [2, 0.5, 0], "rotation": [0, 0.3826834, 0, 0.9238795]},
            {"name": "Grupo", "translation": [0, 0, 3], "scale": [2, 2, 2], "children": [4]},
            {"name": "Cubo_C", "mesh": 0, "translation": [0, 0.25, 0]},
        ],
        "meshes": [{"name": "cubo", "primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
        "materials": [{"name": "Azul", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "baseColorTexture": {"index": 0},
                                                                "metallicFactor": 0.1, "roughnessFactor": 0.6}}],
        "textures": [{"source": 0}], "images": [{"uri": "escena_textura.png"}],
        "buffers": [{"uri": "escena.bin", "byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": v.nbytes, "target": 34962},
                        {"buffer": 0, "byteOffset": v.nbytes, "byteLength": uv.nbytes, "target": 34962},
                        {"buffer": 0, "byteOffset": v.nbytes + uv.nbytes, "byteLength": idx.nbytes, "target": 34963}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
                       "min": [-.5, -.5, -.5], "max": [.5, .5, .5]},
                      {"bufferView": 1, "componentType": 5126, "count": 8, "type": "VEC2"},
                      {"bufferView": 2, "componentType": 5123, "count": len(idx), "type": "SCALAR"}],
    }
    with open(os.path.join(out, "escena.gltf"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    # GLB empaquetado a partir del mismo contenido (escrito a mano, sin nuestro exportador)
    tex = _png((200, 60, 40))
    pad = lambda b, c=b"\x00": b + c * ((-len(b)) % 4)  # noqa: E731
    bin2 = pad(binary) + tex
    doc2 = json.loads(json.dumps(doc))
    doc2["buffers"] = [{"byteLength": len(bin2)}]
    doc2["images"] = [{"bufferView": 3, "mimeType": "image/png"}]
    doc2["bufferViews"].append({"buffer": 0, "byteOffset": len(pad(binary)), "byteLength": len(tex)})
    js = pad(json.dumps(doc2).encode(), b" ")
    bin2 = pad(bin2)
    with open(os.path.join(out, "escena_jerarquia.glb"), "wb") as fh:
        fh.write(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(bin2)))
        fh.write(struct.pack("<I", len(js)) + b"JSON" + js)
        fh.write(struct.pack("<I", len(bin2)) + b"BIN\x00" + bin2)


FBX_ASCII = """; FBX 7.3.0 project file
FBXHeaderExtension:  {
	FBXHeaderVersion: 1003
	FBXVersion: 7300
}
GlobalSettings:  {
	Version: 1000
	Properties70:  {
		P: "UpAxis", "int", "Integer", "",1
		P: "UpAxisSign", "int", "Integer", "",1
		P: "FrontAxis", "int", "Integer", "",2
		P: "FrontAxisSign", "int", "Integer", "",1
		P: "CoordAxis", "int", "Integer", "",0
		P: "CoordAxisSign", "int", "Integer", "",1
		P: "UnitScaleFactor", "double", "Number", "",1
	}
}
Objects:  {
	Geometry: 100, "Geometry::Cubo", "Mesh" {
		Vertices: *24 {
			a: -50,-50,50,50,-50,50,-50,50,50,50,50,50,-50,50,-50,50,50,-50,-50,-50,-50,50,-50,-50
		}
		PolygonVertexIndex: *24 {
			a: 0,1,3,-3,2,3,5,-5,4,5,7,-7,6,7,1,-1,1,7,5,-4,6,0,2,-5
		}
		GeometryVersion: 124
		LayerElementMaterial: 0 {
			Version: 101
			Name: ""
			MappingInformationType: "AllSame"
			ReferenceInformationType: "IndexToDirect"
			Materials: *1 {
				a: 0
			}
		}
		Layer: 0 {
			Version: 100
			LayerElement:  {
				Type: "LayerElementMaterial"
				TypedIndex: 0
			}
		}
	}
	Model: 200, "Model::Cubo_ASCII", "Mesh" {
		Version: 232
		Properties70:  {
			P: "Lcl Translation", "Lcl Translation", "", "A",0,50,0
		}
	}
	Material: 300, "Material::Verde", "" {
		Version: 102
		ShadingModel: "phong"
		Properties70:  {
			P: "DiffuseColor", "Color", "", "A",0.1,0.7,0.2
		}
	}
}
Connections:  {
	C: "OO",200,0
	C: "OO",100,200
	C: "OO",300,200
}
"""


def make_fbx(out: str):
    with open(os.path.join(out, "cubo_ascii.fbx"), "w", encoding="ascii") as fh:
        fh.write(FBX_ASCII)
    # FBX binario con jerarquía y materiales generado desde la escena glTF de prueba
    from u3dc.core.converter import convert_file
    from u3dc.core.options import ConversionOptions
    rep = convert_file(os.path.join(out, "escena_jerarquia.glb"),
                       ConversionOptions(target_format="fbx", output_dir=out, overwrite=True))
    if rep.outputs:
        os.replace(rep.outputs[0], os.path.join(out, "robot_jerarquia.fbx"))
        for extra in rep.outputs[1:]:
            pass
    else:
        raise RuntimeError("No se pudo generar el FBX de prueba: " + "; ".join(rep.errors))


def main(out=None):
    out = out or os.path.join(ROOT, "test_assets")
    os.makedirs(out, exist_ok=True)
    make_cad(out)
    make_ifc(out, "IFC4", "edificio_ifc4")
    make_ifc(out, "IFC2X3", "almacen_ifc2x3", n_storeys=1)
    make_obj(out)
    make_stl(out)
    make_gltf(out)
    make_fbx(out)
    uni = os.path.join(out, "carpeta con espacios y acentos áé")
    os.makedirs(uni, exist_ok=True)
    import shutil
    shutil.copyfile(os.path.join(out, "soporte_binario.stl"), os.path.join(uni, "модель_ñ.stl"))
    shutil.copyfile(os.path.join(out, "edificio_ifc4.ifc"), os.path.join(uni, "edificio_ñ.ifc"))
    print("Recursos de prueba generados en", out)
    for f in sorted(os.listdir(out)):
        print("  ", f)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
