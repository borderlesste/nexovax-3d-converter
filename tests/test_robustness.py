"""Robustez: archivos corruptos, rutas Unicode/largas, cancelación, no sobrescritura, aislamiento y rendimiento."""
import hashlib
import os
import shutil
import threading
import time

import numpy as np
import pytest

from tests.conftest import asset, ASSETS
from u3dc.core.converter import convert_file
from u3dc.core.jobs import run_isolated
from u3dc.core.options import ConversionOptions
from u3dc.core.report import Status

OK = (Status.SUCCESS, Status.SUCCESS_WARNINGS)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def opts(tmp_path, dst, **kw):
    return ConversionOptions(target_format=dst, output_dir=str(tmp_path), **kw)


@pytest.mark.parametrize("name,content", [
    ("truncado.glb", lambda: open(asset("escena_jerarquia.glb"), "rb").read()[:300]),
    ("roto.step", lambda: b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\n#1=BASURA(;\n"),
    ("roto.ifc", lambda: b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n#1=IFCWALL('x',$,$);\nENDSEC;\nEND-ISO-10303-21;\n"),
    ("vacio_triangulos.stl", lambda: b"\x00" * 80 + b"\x00\x00\x00\x00"),
    ("roto.fbx", lambda: b"Kaydara FBX Binary  \x00\x1a\x00" + os.urandom(500)),
    ("roto.obj", lambda: b"v 0 0 0\nv 1 0 0\nf 1 2 9\n"),
])
def test_corrupt_inputs_fail_cleanly(name, content, tmp_path):
    src = tmp_path / "in" / name
    src.parent.mkdir()
    src.write_bytes(content())
    before = sha(src)
    out = tmp_path / "out"
    rep = run_isolated(str(src), opts(out, "glb" if not name.endswith(".glb") else "stl"))
    assert rep.status == Status.FAILED
    assert rep.errors
    assert sha(src) == before                       # el original nunca se modifica
    assert not out.exists() or not [f for f in os.listdir(out) if not f.startswith(".")]   # sin archivos parciales


def test_gltf_missing_bin_reported(tmp_path):
    shutil.copyfile(asset("escena.gltf"), tmp_path / "escena.gltf")
    rep = convert_file(str(tmp_path / "escena.gltf"), opts(tmp_path / "o", "glb"))
    assert rep.status == Status.FAILED and "escena.bin" in " ".join(rep.errors)


def test_gltf_path_traversal_blocked(tmp_path):
    import json
    doc = json.load(open(asset("escena.gltf"), encoding="utf-8"))
    doc["buffers"][0]["uri"] = "../../../Windows/win.ini"
    p = tmp_path / "malicioso.gltf"
    p.write_text(json.dumps(doc), encoding="utf-8")
    rep = convert_file(str(p), opts(tmp_path / "o", "glb"))
    assert rep.status == Status.FAILED and "bloqueada" in " ".join(rep.errors)


def test_no_overwrite_creates_suffix(tmp_path):
    r1 = convert_file(asset("soporte_binario.stl"), opts(tmp_path, "obj"))
    r2 = convert_file(asset("soporte_binario.stl"), opts(tmp_path, "obj"))
    assert r1.outputs[0] != r2.outputs[0]
    assert os.path.basename(r2.outputs[0]) == "soporte_binario (1).obj"
    r3 = convert_file(asset("soporte_binario.stl"), opts(tmp_path, "obj", overwrite=True))
    assert r3.outputs[0] == r1.outputs[0]


@pytest.mark.parametrize("src,dst", [("модель_ñ.stl", "step"), ("edificio_ñ.ifc", "glb"), ("модель_ñ.stl", "fbx")])
def test_unicode_paths(src, dst, tmp_path):
    folder = os.path.join(ASSETS, "carpeta con espacios y acentos áé")
    out = tmp_path / "salida ñ 日本"
    rep = convert_file(os.path.join(folder, src), opts(out, dst))
    assert rep.status in OK, rep.errors
    assert os.path.isfile(rep.outputs[0]) and "ñ" in os.path.basename(rep.outputs[0])


def test_long_paths(tmp_path):
    from u3dc.core.safety import long_path
    deep = str(tmp_path)
    while len(deep) < 300:
        deep = os.path.join(deep, "subcarpeta_con_nombre_largo_para_superar_max_path")
    os.makedirs(long_path(deep), exist_ok=True)
    src = os.path.join(deep, "pieza.step")
    shutil.copyfile(asset("pieza_ñandú.stp"), long_path(src))
    rep = convert_file(src, opts(deep, "stl"))
    assert rep.status in OK, rep.errors
    assert len(rep.outputs[0]) > 260 and os.path.isfile(long_path(rep.outputs[0]))


def test_cancellation_kills_worker_and_leaves_nothing(tmp_path):
    big = tmp_path / "grande.stl"
    _write_sphere_stl(str(big), 400)
    ev = threading.Event()
    threading.Timer(2.0, ev.set).start()
    out = tmp_path / "out"
    t0 = time.time()
    rep = run_isolated(str(big), opts(out, "step", max_triangles_to_cad=10_000_000), cancel_event=ev)
    assert rep.status == Status.CANCELLED
    assert time.time() - t0 < 30
    assert not out.exists() or not os.listdir(out)


def test_isolated_matches_in_process(tmp_path):
    rep = run_isolated(asset("mueble.obj"), opts(tmp_path, "fbx"))
    assert rep.status in OK and rep.validation["triangles"] == 64


def test_dense_mesh_to_cad_refused_with_explanation(tmp_path):
    big = tmp_path / "denso.stl"
    _write_sphere_stl(str(big), 400)
    rep = convert_file(str(big), opts(tmp_path / "o", "step", max_triangles_to_cad=50_000))
    assert rep.status == Status.FAILED and "no es recomendable" in rep.errors[0]
    assert not (tmp_path / "o").exists() or not os.listdir(tmp_path / "o")


@pytest.mark.slow
def test_large_mesh_performance(tmp_path):
    big = tmp_path / "millon.stl"
    _write_sphere_stl(str(big), 708)        # ≈ 1 millón de triángulos (50 MB)
    t0 = time.time()
    rep = convert_file(str(big), opts(tmp_path / "o", "glb"))
    dt = time.time() - t0
    assert rep.status in OK, rep.errors
    assert rep.stats["triangulos"] > 990_000
    assert dt < 120, f"demasiado lento: {dt:.1f} s"


def _write_sphere_stl(path, n):
    """Esfera UV con 2·n·n triángulos aprox., escrita en STL binario."""
    th = np.linspace(0, np.pi, n + 1)
    ph = np.linspace(0, 2 * np.pi, n + 1)
    T, P = np.meshgrid(th, ph, indexing="ij")
    pts = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P), np.cos(T)], -1) * 50.0
    a = pts[:-1, :-1].reshape(-1, 3)
    b = pts[1:, :-1].reshape(-1, 3)
    c = pts[1:, 1:].reshape(-1, 3)
    d = pts[:-1, 1:].reshape(-1, 3)
    tris = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    dtype = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    data = np.zeros(len(tris), dtype)
    data["v"] = tris
    with open(path, "wb") as fh:
        fh.write(b"esfera".ljust(80, b" "))
        fh.write(np.uint32(len(tris)).tobytes())
        data.tofile(fh)
