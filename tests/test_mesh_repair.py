"""Malla → B-Rep (1.0.2): análisis sobre la malla soldada, reparación de defectos no manifold,
orientación vectorizada, objetivo de simplificación respetado y simplificación por pieza que
conserva los sólidos. Casos derivados del GLB real "futuristic headset" (1 930 242 triángulos).
"""
import types

import numpy as np
import pytest

from tests import stl_cases as C
from u3dc.core.converter import convert_file
from u3dc.core.options import ConversionOptions
from u3dc.core.report import Status
from u3dc.engines.cad import mesh_to_brep as mb

OK = (Status.SUCCESS, Status.SUCCESS_WARNINGS)
QUIET = types.SimpleNamespace(info=lambda m: None, warn=lambda m: None, loss=lambda m: None)


def indexed(tris: np.ndarray):
    v = tris.reshape(-1, 3).astype(np.float64)
    f = np.arange(len(v), dtype=np.int64).reshape(-1, 3)
    return v, f


def welded(tris: np.ndarray):
    v, f = indexed(tris)
    v, f, _ = mb.weld(v, f, 1e-9)
    return v, f


def closed_pieces(v, f):
    comp = mb.face_components(f, len(v))
    info = mb._component_stats(v, f, comp)
    return len(info), sum(1 for c in info if c.closed and not c.inconsistent_edges)


def test_seam_duplicates_are_welded_before_analysis():
    """Un GLB con costuras de UV repite vértices: el diagnóstico debe describir la pieza real (cerrada)."""
    v, f = indexed(C.sphere_fast(10, 24))            # cada triángulo con sus propios vértices
    rep = types.SimpleNamespace(info=lambda m: None, warn=lambda m: None, loss=lambda m: None, technical={})
    parts, tech = mb.mesh_to_parts(v, f, "esfera", ConversionOptions(), rep, budget=10**6)
    d0 = tech["malla_original"]
    assert d0["componentes"] == 1 and d0["estado"] == "cerrada"
    assert d0["duplicate_vertices"] > 0 and tech["vertices_leidos"] == len(v)
    assert [k for _, _, k in parts] == ["sólido"]


def test_vectorized_orientation_fixes_random_flips():
    v, f = welded(C.sphere_fast(10, 80))
    rng = np.random.default_rng(1)
    bad = f.copy()
    sel = rng.random(len(f)) < 0.3
    bad[sel] = bad[sel][:, ::-1]
    assert mb._edge_stats(bad)[2] > 0
    fixed, flipped = mb._orient_consistently(bad)
    assert mb._edge_stats(fixed)[2] == 0
    assert flipped == int(sel.sum())                 # se conserva la orientación mayoritaria
    assert mb._signed_volume(v, fixed) > 0


def test_union_find_components_match_expected():
    tris = np.concatenate([C.box(0, 0, 0, 1, 1, 1), C.box(5, 0, 0, 6, 1, 1), C.sphere_fast(1, 12, (20, 0, 0))])
    v, f = welded(tris)
    comp = mb.face_components(f, len(v))
    assert len(np.unique(comp)) == 3
    assert np.bincount(comp).tolist() == [12, 12, len(f) - 24]


def test_dangling_flap_on_closed_body_is_removed():
    box = C.box(0, 0, 0, 10, 10, 10)
    a, b = box[0][0], box[0][1]                        # una arista del cubo
    flap = np.array([[a, b, (a + b) / 2 + [-5, -5, 0]]])
    v, f = welded(np.concatenate([box, flap]))
    assert mb._edge_stats(f)[1] == 1                   # arista no manifold
    v2, f2, actions = mb.repair(v, f, QUIET)
    assert len(f2) == 12 and closed_pieces(v2, f2) == (1, 1)
    assert any("sueltos apoyados" in a for a in actions)


def test_back_to_back_fin_is_removed():
    box = C.box(0, 0, 0, 10, 10, 10)
    a, b = box[0][0], box[0][1]
    p = (a + b) / 2 + [-5, -5, 0]
    v, f = welded(np.concatenate([box, [[a, b, p]], [[b, a, p]]]))
    v2, f2, actions = mb.repair(v, f, QUIET)
    assert len(f2) == 12 and closed_pieces(v2, f2) == (1, 1)
    assert any("aletas sin volumen" in a for a in actions)


def test_bodies_touching_along_an_edge_become_two_solids(tmp_path):
    tris = np.concatenate([C.box(0, 0, 0, 10, 10, 10), C.box(10, 10, 0, 20, 20, 10)])   # comparten una arista
    v, f = welded(tris)
    assert mb._edge_stats(f)[1] == 1
    v2, f2, actions = mb.repair(v, f, QUIET)
    assert closed_pieces(v2, f2) == (2, 2)
    rep = convert_file(C.write_stl(str(tmp_path / "pellizco.stl"), tris),
                       ConversionOptions(target_format="step", output_dir=str(tmp_path / "o")))
    assert rep.status in OK, rep.errors
    assert rep.technical["malla_a_brep"]["mallas"][0]["resultado"]["sólido"] == 2
    assert rep.validation["solidos"] == 2 and rep.validation["superficies"] == 0


def test_simplification_target_respected_beyond_99_percent():
    import trimesh
    ico = trimesh.creation.icosphere(subdivisions=6, radius=50)          # 81 920 triángulos
    v, f = np.asarray(ico.vertices, np.float64), np.asarray(ico.faces, np.int64)
    v2, f2, info = mb.simplify(v, f, 400, None)                          # reducción del 99,5 %
    assert len(f2) <= 400 * 1.02, len(f2)                # antes se recortaba al 99 % (≈819)
    assert info["triangulos_despues"] == len(f2)


def test_simplify_by_component_keeps_thin_parts_closed():
    big = C.sphere_fast(100, 220)                                            # 96 360 triángulos
    thin = C.sphere_fast(20, 70, (300, 0, 0)) * [1, 1, 0.04] + [0, 0, 0]     # disco muy fino, 9 660
    v, f = welded(np.concatenate([big, thin]))
    assert closed_pieces(v, f) == (2, 2)
    v2, f2, info = mb.simplify_by_component(v, f, 1500, 6000)
    assert info["piezas"] == 2 and len(f2) <= 6000
    assert closed_pieces(v2, f2) == (2, 2), info
    assert info["piezas_sin_conservar_cierre"] == 0


def test_resource_budget_uses_measured_incremental_cost():
    # 716 MB libres (caso real): antes 11 201 triángulos por contar dos veces la memoria base
    n = mb.max_affordable_triangles(716, 1800)
    assert 19_000 <= n <= 21_000
    assert mb.max_affordable_triangles(716, 1800, unify_max=0) > n          # sin unión de caras cuesta menos
    assert mb.max_affordable_triangles(10**6, 60) <= 0.6 * 60_000 / mb.MS_PER_TRI + 1


def test_validation_counts_free_surfaces(tmp_path):
    tris = C.grid(10, 10)
    rep = convert_file(C.write_stl(str(tmp_path / "placa.stl"), tris),
                       ConversionOptions(target_format="step", output_dir=str(tmp_path / "o")))
    assert rep.status in OK, rep.errors
    assert rep.validation["solidos"] == 0 and rep.validation["superficies"] >= 1
