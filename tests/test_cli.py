"""Interfaz de línea de comandos."""
import json

from tests.conftest import asset
from u3dc.cli import main


def test_cli_matrix(capsys):
    assert main(["matrix"]) == 0
    out = capsys.readouterr().out
    assert "STEP" in out and "Facetada" in out


def test_cli_convert_batch_with_report(tmp_path):
    rep = tmp_path / "informe.json"
    code = main(["convert", asset("mueble.obj"), asset("soporte_binario.stl"), "-t", "fbx", "-o", str(tmp_path),
                 "--report", str(rep)])
    assert code == 0
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert len(data) == 2 and all(d["status"].startswith("exitoso") for d in data)


def test_cli_info(capsys):
    assert main(["info", asset("edificio_ifc4.ifc")]) == 0
    assert "IFC" in capsys.readouterr().out
