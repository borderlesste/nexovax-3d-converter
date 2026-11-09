"""STL → STEP: casos obligatorios, reapertura del STEP generado y diagnóstico de fallos."""
import os

import numpy as np
import pytest

from tests import stl_cases as C
from u3dc.core import adapters
from u3dc.core.converter import convert_file
from u3dc.core.jobs import run_isolated
from u3dc.core.options import ConversionOptions
from u3dc.core.report import ConversionReport, Status

OK = (Status.SUCCESS, Status.SUCCESS_WARNINGS)


def stl(tmp_path, name, tris):
    return C.write_stl(str(tmp_path / f"{name}.stl"), tris)


def to_step(src, tmp_path, **kw):
    return convert_file(src, ConversionOptions(target_format="step", output_dir=str(tmp_path / "out"), **kw))


def reopen_step(path):
    """Reapertura independiente del STEP generado: formas, validez OCCT y caja envolvente (mm)."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    from u3dc.engines.cad.occt import read_cad, shape_stats
    cad = read_cad(path, "step", ConversionReport(path))
    solids = sum(shape_stats(p.shape)["solidos"] for p in cad.parts)
    faces = sum(shape_stats(p.shape)["caras"] for p in cad.parts)
    valid = all(BRepCheck_Analyzer(p.shape).IsValid() for p in cad.parts)
    return cad, solids, faces, valid, cad.bounds()


def mesh_tech(rep):
    return rep.technical["malla_a_brep"]["mallas"][0]


def test_closed_cube_becomes_valid_solid(tmp_path):
    rep = to_step(stl(tmp_path, "cubo", C.box(0, 0, 0, 20, 30, 40)), tmp_path)
    assert rep.status in OK, rep.errors
    _, solids, faces, valid, bb = reopen_step(rep.outputs[0])
    assert solids == 1 and valid
    assert faces == 6                           # triángulos coplanares unidos en caras rectangulares
    assert np.allclose(bb, [[0, 0, 0], [20, 30, 40]], atol=1e-6)
    assert rep.technical["escritura_cad"]["transferencia"] is True
    assert rep.technical["escritura_cad"]["escritura"] == "IFSelect_RetDone"
    assert os.path.isfile(rep.diagnostic_log)


def test_open_mesh_exported_as_surface(tmp_path):
    tris = C.grid(20, 20, z=lambda x, y: 4 * np.sin(x / 12) * np.cos(y / 12))
    rep = to_step(stl(tmp_path, "abierta", tris), tmp_path)
    assert rep.status in OK, rep.errors
    assert mesh_tech(rep)["malla_original"]["estado"] == "abierta"
    _, solids, faces, valid, _ = reopen_step(rep.outputs[0])
    assert solids == 0 and faces > 0 and valid
    assert any("superficies (shell)" in w for w in rep.warnings)


def test_multiple_components_each_a_solid(tmp_path):
    tris = np.concatenate([C.box(0, 0, 0, 10, 10, 10), C.box(20, 0, 0, 30, 10, 10), C.sphere_fast(5, 24, (50, 5, 5))])
    rep = to_step(stl(tmp_path, "multi", tris), tmp_path)
    assert rep.status in OK, rep.errors
    assert mesh_tech(rep)["malla_original"]["componentes"] == 3
    _, solids, _, valid, bb = reopen_step(rep.outputs[0])
    assert solids == 3 and valid
    assert np.allclose(bb[1], [55, 10, 10], atol=1e-6)


def test_degenerate_duplicates_and_orientation_repaired(tmp_path):
    cube = C.box(0, 0, 0, 10, 10, 10)
    tris = np.concatenate([cube[:6], cube[6:, ::-1], cube[:3], cube[:4, [0, 1, 1]]])   # invertidos, duplicados, degenerados
    rep = to_step(stl(tmp_path, "defectos", tris), tmp_path)
    assert rep.status in OK, rep.errors
    m = mesh_tech(rep)
    assert m["malla_original"]["degenerate_triangles"] == 4
    assert m["malla_original"]["duplicate_triangles"] == 3
    assert m["malla_original"]["aristas_orientacion_incoherente"] > 0
    assert any("degenerado" in a for a in m["reparaciones"]) and any("reorientados" in a for a in m["reparaciones"])
    _, solids, _, valid, _ = reopen_step(rep.outputs[0])
    assert solids == 1 and valid


def test_lipo_like_model(tmp_path):
    rep = to_step(stl(tmp_path, "lipo battery 3d model (1)_converted", C.lipo_battery(96)), tmp_path)
    assert rep.status in OK, rep.errors
    _, solids, _, valid, _ = reopen_step(rep.outputs[0])
    assert solids == 5 and valid


def test_dense_mesh_simplified(tmp_path):
    tris = C.sphere_fast(50, 300)                                # ≈179 000 triángulos
    rep = to_step(stl(tmp_path, "denso", tris), tmp_path, mesh_target_triangles=20_000)
    assert rep.status in OK, rep.errors
    s = mesh_tech(rep)["simplificacion"]
    assert s["triangulos_antes"] > 170_000 and s["triangulos_despues"] <= 21_000
    assert abs(s["cambio_volumen_pct"]) < 1.0
    assert any("simplificada" in w for w in rep.warnings)
    _, solids, _, valid, bb = reopen_step(rep.outputs[0])
    assert solids == 1 and valid
    assert np.allclose(bb, [[-50, -50, -50], [50, 50, 50]], atol=0.5)


def test_dense_mesh_without_simplification_fails_with_explanation(tmp_path):
    tris = C.sphere_fast(50, 300)
    rep = to_step(stl(tmp_path, "denso_sin", tris), tmp_path, mesh_simplify="off", max_triangles_to_cad=50_000)
    assert rep.status == Status.FAILED
    assert "Active la simplificación" in rep.errors[0] and "MB" in rep.errors[0]
    assert rep.stage == "estimación de recursos"
    log = open(rep.diagnostic_log, encoding="utf-8").read()
    for needle in ("Entrada:", "Etapa del fallo: estimación de recursos", "triangles", "componentes",
                   "Traza completa de la excepción", "ValueError"):
        assert needle in log, needle
    assert not (tmp_path / "out").exists() or not os.listdir(tmp_path / "out")


def test_dense_mesh_full_resolution_when_simplification_off(tmp_path):
    tris = C.sphere_fast(50, 60)                                 # ≈7 000 triángulos, sin simplificar
    rep = to_step(stl(tmp_path, "sin_simpl", tris), tmp_path, mesh_simplify="off")
    assert rep.status in OK, rep.errors
    assert "simplificacion" not in mesh_tech(rep)
    assert mesh_tech(rep)["malla_final"]["triangles"] == len(tris)          # resolución completa
    assert 0 < rep.validation["caras"] <= len(tris)                         # caras coplanares unidas


@pytest.mark.parametrize("dst", ["obj", "glb"])
def test_comparison_stl_to_mesh_formats(tmp_path, dst):
    src = stl(tmp_path, "lipo", C.lipo_battery(96))
    a = convert_file(src, ConversionOptions(target_format=dst, output_dir=str(tmp_path / dst)))
    b = to_step(src, tmp_path)
    assert a.status in OK and b.status in OK
    assert np.allclose(a.stats["dimensiones_m"], b.stats["dimensiones_m"], atol=1e-6)


def test_native_crash_is_diagnosed(tmp_path, monkeypatch):
    """Un fallo nativo real (violación de acceso) en la construcción B-Rep queda identificado."""
    monkeypatch.setenv("U3DC_TEST_CRASH_STAGE", "construcción B-Rep")
    monkeypatch.setenv("U3DC_TEST_CRASH_OK", "1")
    src = stl(tmp_path, "crash", C.box(0, 0, 0, 1, 1, 1))
    rep = run_isolated(src, ConversionOptions(target_format="step", output_dir=str(tmp_path / "out")))
    assert rep.status == Status.FAILED
    assert "construcción B-Rep" in rep.errors[0] and rep.stage == "construcción B-Rep"
    assert rep.technical["proceso"]["codigo_salida"] not in (0, None)
    assert rep.source_format == "stl"
    assert rep.technical["malla_a_brep"]["mallas"][0]["malla_original"]["triangles"] == 12   # análisis previo conservado
    log = open(rep.diagnostic_log, encoding="utf-8").read()
    assert "Segmentation fault" in log and "mesh_to_parts" in log    # pila de Python en el momento del fallo
    assert not (tmp_path / "out").exists() or not os.listdir(tmp_path / "out")


def test_isolated_run_leaves_no_temp_dirs(tmp_path):
    import tempfile
    base = os.path.join(tempfile.gettempdir(), "u3dc")
    before = set(os.listdir(base)) if os.path.isdir(base) else set()
    src = stl(tmp_path, "cubo", C.box(0, 0, 0, 1, 1, 1))
    rep = run_isolated(src, ConversionOptions(target_format="step", output_dir=str(tmp_path / "out")))
    assert rep.status in OK
    after = set(os.listdir(base))
    assert not {d for d in after - before if d.startswith("u3dc_")}
