"""Detección de formatos y selección de rutas."""
import os
import shutil

import pytest

from tests.conftest import asset
from u3dc.core.formats import detect, DetectionError, FORMAT_ORDER
from u3dc.core.report import Fidelity
from u3dc.core.router import find_route, compatibility_matrix

EXPECTED = {
    "escena.gltf": "gltf", "escena_jerarquia.glb": "glb", "mueble.obj": "obj", "robot_jerarquia.fbx": "fbx",
    "cubo_ascii.fbx": "fbx", "soporte_binario.stl": "stl", "dos_solidos_ascii.stl": "stl",
    "edificio_ifc4.ifc": "ifc", "almacen_ifc2x3.ifc": "ifc", "ensamblaje_mecanico.step": "step",
    "pieza_ñandú.stp": "step", "ensamblaje_mecanico.igs": "iges", "pieza_curva.iges": "iges",
}


@pytest.mark.parametrize("name,fmt", EXPECTED.items())
def test_detect_by_content(name, fmt):
    got, _ = detect(asset(name))
    assert got == fmt


def test_extension_mismatch_uses_content(tmp_path):
    fake = tmp_path / "en_realidad_step.stl"
    shutil.copyfile(asset("ensamblaje_mecanico.step"), fake)
    fmt, warns = detect(str(fake))
    assert fmt == "step" and warns


def test_empty_and_garbage_rejected(tmp_path):
    e = tmp_path / "vacio.glb"
    e.write_bytes(b"")
    with pytest.raises(DetectionError):
        detect(str(e))
    g = tmp_path / "basura.xyz"
    g.write_bytes(os.urandom(4096))
    with pytest.raises(DetectionError):
        detect(str(g))


def test_all_64_pairs_have_a_route():
    cells = compatibility_matrix()
    assert len(cells) == 64
    assert all(c.fidelity != Fidelity.UNSUPPORTED for c in cells)


@pytest.mark.parametrize("src,dst,fid", [
    ("step", "stl", Fidelity.TESSELLATED), ("step", "glb", Fidelity.TESSELLATED), ("step", "iges", Fidelity.DIRECT),
    ("iges", "step", Fidelity.DIRECT), ("ifc", "obj", Fidelity.TESSELLATED), ("ifc", "glb", Fidelity.TESSELLATED),
    ("ifc", "step", Fidelity.DIRECT), ("obj", "glb", Fidelity.DIRECT), ("obj", "stl", Fidelity.DIRECT),
    ("glb", "fbx", Fidelity.DIRECT), ("fbx", "glb", Fidelity.DIRECT), ("stl", "obj", Fidelity.DIRECT),
    ("stl", "step", Fidelity.APPROXIMATE), ("stl", "ifc", Fidelity.LIMITED),
])
def test_mandatory_routes(src, dst, fid):
    r = find_route(src, dst)
    assert r is not None and r.fidelity == fid


def test_ifc_to_step_keeps_brep_not_mesh():
    r = find_route("ifc", "step")
    assert r.representations == ["bim", "cad"], "IFC→STEP no debe pasar por malla"


def test_cad_to_cad_never_meshes():
    for s in ("step", "iges"):
        for d in ("step", "iges"):
            assert "scene" not in find_route(s, d).representations
