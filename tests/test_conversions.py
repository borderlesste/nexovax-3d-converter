"""Conversiones obligatorias (sección 12) con comprobaciones geométricas y semánticas."""
import json
import os
import struct

import numpy as np
import pytest

from tests.conftest import asset
from u3dc.core.converter import convert_file
from u3dc.core.options import ConversionOptions
from u3dc.core.report import Status, ConversionReport
from u3dc.core import adapters

OK = (Status.SUCCESS, Status.SUCCESS_WARNINGS)

MANDATORY = [
    ("ensamblaje_mecanico.step", "stl"), ("ensamblaje_mecanico.step", "glb"), ("ensamblaje_mecanico.step", "iges"),
    ("ensamblaje_mecanico.igs", "step"), ("edificio_ifc4.ifc", "obj"), ("edificio_ifc4.ifc", "glb"),
    ("edificio_ifc4.ifc", "step"), ("mueble.obj", "glb"), ("mueble.obj", "stl"), ("escena_jerarquia.glb", "fbx"),
    ("robot_jerarquia.fbx", "glb"), ("soporte_binario.stl", "obj"), ("soporte_binario.stl", "step"),
    ("soporte_binario.stl", "ifc"),
]


def conv(src, dst, tmp_path, **kw) -> ConversionReport:
    opts = ConversionOptions(target_format=dst, output_dir=str(tmp_path), **kw)
    return convert_file(asset(src) if not os.path.isabs(src) else src, opts)


def reread(path, fmt, **kw):
    opts = ConversionOptions(**kw)
    return adapters.read(fmt, path, opts, ConversionReport(path))


@pytest.mark.parametrize("src,dst", MANDATORY)
def test_mandatory_conversion(src, dst, tmp_path):
    rep = conv(src, dst, tmp_path)
    assert rep.status in OK, rep.errors
    assert rep.outputs and all(os.path.getsize(o) > 0 for o in rep.outputs)
    v = rep.validation
    if "desviacion_dimensiones_m" in v:
        diag = float(np.linalg.norm(rep.stats["dimensiones_m"]))
        assert v["desviacion_dimensiones_m"] <= diag * 1e-3


def test_step_to_stl_tolerance_controls_density(tmp_path):
    coarse = conv("ensamblaje_mecanico.step", "stl", tmp_path / "a", quality="baja")
    fine = conv("ensamblaje_mecanico.step", "stl", tmp_path / "b", quality="muy_alta")
    assert fine.stats["triangulos"] > coarse.stats["triangulos"] * 2


def test_step_roundtrip_preserves_names_colors_solids(tmp_path):
    rep = conv("ensamblaje_mecanico.step", "step", tmp_path)
    _, cad = reread(rep.outputs[0], "step")
    names = sorted(p.name for p in cad.parts)
    assert names == ["esfera", "pasador", "placa_base", "toroide"]
    colors = {p.name: p.color for p in cad.parts}
    assert np.allclose(colors["esfera"], (0.8, 0.1, 0.1), atol=0.02)
    from u3dc.engines.cad.occt import shape_stats
    assert all(shape_stats(p.shape)["solidos"] == 1 for p in cad.parts)


def test_iges_to_step_keeps_solids(tmp_path):
    rep = conv("ensamblaje_mecanico.igs", "step", tmp_path)
    assert rep.validation["solidos"] == 4


def test_ifc_to_glb_keeps_names_hierarchy_and_properties(tmp_path):
    rep = conv("edificio_ifc4.ifc", "glb", tmp_path)
    from u3dc.engines.mesh.gltf_io import read_gltf_json
    doc = read_gltf_json(rep.outputs[0])
    names = [n.get("name") for n in doc["nodes"]]
    assert "Planta 0" in names and "Edificio de oficinas" in names
    wall = next(n for n in doc["nodes"] if n.get("name") == "Muro P0-1")
    assert wall["extras"]["IfcClass"] in ("IfcWall", "IfcWallStandardCase")
    assert wall["extras"]["Pset_WallCommon"]["IsExternal"] is True
    assert len(wall["extras"]["GlobalId"]) == 22


def test_ifc_to_step_one_solid_per_element(tmp_path):
    rep = conv("edificio_ifc4.ifc", "step", tmp_path)
    assert rep.validation["solidos"] == 14
    assert any("BIM" in l for l in rep.losses)


def test_glb_fbx_glb_roundtrip_hierarchy_materials(tmp_path):
    r1 = conv("escena_jerarquia.glb", "fbx", tmp_path / "a")
    r2 = conv(r1.outputs[0], "glb", tmp_path / "b")
    assert r2.status in OK
    _, sc = reread(r2.outputs[0], "glb")
    names = {n.name for n in sc.nodes}
    assert {"Raíz", "Cubo_A", "Cubo_B", "Grupo", "Cubo_C"} <= names
    assert len(sc.materials) >= 1 and len(sc.textures) == 1
    _, orig = reread(asset("escena_jerarquia.glb"), "glb")
    assert np.allclose(sc.bounds(), orig.bounds(), atol=1e-5)


def test_obj_to_stl_reports_material_loss(tmp_path):
    rep = conv("mueble.obj", "stl", tmp_path)
    assert any("materiales" in l.lower() for l in rep.losses)
    data = open(rep.outputs[0], "rb").read()
    assert struct.unpack("<I", data[80:84])[0] == rep.stats["triangulos"]


def test_stl_to_step_is_faceted_solid_not_parametric(tmp_path):
    rep = conv("soporte_binario.stl", "step", tmp_path)
    assert rep.fidelity_label.startswith("Aproximada")
    assert rep.validation["solidos"] == 1
    assert any("no se recupera un sólido CAD paramétrico" in l for l in rep.losses)


def test_stl_to_ifc_generic_proxy_without_invented_bim(tmp_path):
    rep = conv("soporte_binario.stl", "ifc", tmp_path)
    import ifcopenshell
    f = ifcopenshell.open(rep.outputs[0])
    proxies = f.by_type("IfcBuildingElementProxy")
    assert len(proxies) == 1
    assert not f.by_type("IfcWall") and not f.by_type("IfcSlab")
    assert rep.validation["errores_esquema"] == 0


def test_units_stl_mm_to_glb_meters(tmp_path):
    rep = conv("soporte_binario.stl", "glb", tmp_path)
    assert np.allclose(rep.stats["dimensiones_m"], [0.04, 0.04, 0.04], atol=1e-6)


def test_units_ifc_m_to_stl_m_and_mm(tmp_path):
    rep = conv("edificio_ifc4.ifc", "stl", tmp_path / "a")
    _, sc = reread(rep.outputs[0], "stl", input_units="m")
    assert np.allclose(np.ptp(sc.bounds(), axis=0), [12, 8, 6.3], atol=1e-4)
    rep = conv("edificio_ifc4.ifc", "stl", tmp_path / "b", output_units="mm")
    _, sc = reread(rep.outputs[0], "stl", input_units="m")   # leído como m: valores numéricos en mm
    assert np.allclose(np.ptp(sc.bounds(), axis=0), [12000, 8000, 6300], atol=0.1)


def test_fbx_ascii_units_and_axes(tmp_path):
    """cubo_ascii.fbx: 100 cm, Y arriba, desplazado 50 cm en Y → 1 m, Z ∈ [0, 1]."""
    rep = conv("cubo_ascii.fbx", "glb", tmp_path)
    _, sc = reread(rep.outputs[0], "glb")
    b = sc.bounds()
    assert np.allclose(b, [[-0.5, -0.5, 0.0], [0.5, 0.5, 1.0]], atol=1e-6)


def test_scale_option(tmp_path):
    rep = conv("soporte_binario.stl", "glb", tmp_path, scale=2.0)
    assert np.allclose(rep.stats["dimensiones_m"], [0.08, 0.08, 0.08], atol=1e-6)
    assert any("Escala" in w for w in rep.warnings)


def test_merge_by_material(tmp_path):
    rep = conv("mueble.obj", "glb", tmp_path, merge_by_material=True)
    assert rep.validation["objetos"] == 2


def test_gltf_external_resources_written_and_referenced(tmp_path):
    rep = conv("escena.gltf", "gltf", tmp_path)
    doc = json.load(open(rep.outputs[0], encoding="utf-8"))
    for b in doc["buffers"]:
        assert os.path.isfile(os.path.join(tmp_path, b["uri"]))
    for im in doc.get("images", []):
        assert os.path.isfile(os.path.join(tmp_path, im["uri"]))


def test_ifc2x3_output_schema(tmp_path):
    rep = conv("mueble.obj", "ifc", tmp_path, ifc_schema="IFC2X3")
    import ifcopenshell
    f = ifcopenshell.open(rep.outputs[0])
    assert f.schema == "IFC2X3" and len(f.by_type("IfcBuildingElementProxy")) == 6


ALL_FORMATS = ["gltf", "glb", "obj", "fbx", "stl", "ifc", "step", "iges"]
SOURCES = {"gltf": "escena.gltf", "glb": "escena_jerarquia.glb", "obj": "mueble.obj", "fbx": "robot_jerarquia.fbx",
           "stl": "dos_solidos_ascii.stl", "ifc": "almacen_ifc2x3.ifc", "step": "ensamblaje_mecanico.step",
           "iges": "pieza_curva.iges"}


@pytest.mark.parametrize("src", ALL_FORMATS)
@pytest.mark.parametrize("dst", ALL_FORMATS)
def test_full_matrix(src, dst, tmp_path):
    rep = conv(SOURCES[src], dst, tmp_path)
    assert rep.status in OK, rep.errors
    assert rep.validation
