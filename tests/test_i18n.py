"""Traducciones: completitud de catálogos, coherencia de marcadores y cobertura de mensajes reales."""
import importlib
import re

import pytest

from tests.conftest import asset
from u3dc import i18n
from u3dc.core.converter import convert_file
from u3dc.core.options import ConversionOptions
from tools.i18n_keys import all_keys

LANGS = ["fr", "ht"]
FIELD = re.compile(r"\{(\w+)")


@pytest.fixture(autouse=True)
def restore_language():
    yield
    i18n.set_language("es")


@pytest.mark.parametrize("lang", LANGS)
def test_every_ui_and_engine_text_is_translated(lang):
    cat = importlib.import_module(f"u3dc.locales.{lang}")
    missing = [k for k in all_keys() if k not in cat.STATIC]
    assert not missing, f"Faltan {len(missing)} traducciones ({lang}): {missing[:10]}"


@pytest.mark.parametrize("lang", LANGS)
def test_placeholders_match(lang):
    cat = importlib.import_module(f"u3dc.locales.{lang}")
    for es, out in list(cat.STATIC.items()) + list(cat.MESSAGES):
        assert set(FIELD.findall(es)) == set(FIELD.findall(out)), (lang, es, out)


CASES = [("soporte_binario.stl", "step"), ("dos_solidos_ascii.stl", "iges"), ("edificio_ifc4.ifc", "glb"), ("mueble.obj", "fbx"),
         ("robot_jerarquia.fbx", "stl"), ("ensamblaje_mecanico.step", "ifc"), ("escena.gltf", "obj"),
         ("almacen_ifc2x3.ifc", "iges")]


@pytest.mark.parametrize("lang", LANGS)
def test_real_engine_messages_are_translated(lang, tmp_path):
    """Convierte archivos reales y comprueba que cada aviso/pérdida/error emitido se traduce."""
    i18n.set_language("es")
    msgs = set()
    for src, dst in CASES:
        rep = convert_file(asset(src), ConversionOptions(target_format=dst, output_dir=str(tmp_path / dst)))
        msgs |= {m for _, _, m in rep.log} | set(rep.route)
    bad = tmp_path / "roto.step"
    bad.write_bytes(b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\n#1=X(;\n")
    msgs |= set(convert_file(str(bad), ConversionOptions(target_format="stl", output_dir=str(tmp_path))).errors)
    from tests import stl_cases as SC
    dense = SC.write_stl(str(tmp_path / "denso.stl"), SC.sphere_fast(20, 120))
    for kw in ({"mesh_target_triangles": 5000}, {"mesh_simplify": "off", "max_triangles_to_cad": 5000}):
        r = convert_file(dense, ConversionOptions(target_format="step", output_dir=str(tmp_path / "d"), **kw))
        msgs |= {m for _, _, m in r.log} | {r.stage}
    defects = SC.write_stl(str(tmp_path / "defectos.stl"), SC.lipo_battery(48))
    r = convert_file(defects, ConversionOptions(target_format="step", output_dir=str(tmp_path / "e")))
    msgs |= {m for _, _, m in r.log}
    i18n.set_language(lang)
    untranslated = [m for m in msgs if i18n.tr_msg(m) == m]
    assert not untranslated, f"Mensajes sin traducir ({lang}): {untranslated}"


def test_language_switch_and_fallback():
    i18n.set_language("fr")
    assert i18n.tr("Archivos") == "Fichiers"
    assert i18n.tr("{n} archivos", n=3) == "3 fichiers"
    assert i18n.tr_msg("Escala adicional aplicada: ×2.") == "Échelle supplémentaire appliquée : ×2."
    i18n.set_language("ht")
    assert i18n.tr("Archivos") == "Fichye"
    assert i18n.tr_msg("Texto que no existe") == "Texto que no existe"
    i18n.set_language("xx")
    assert i18n.get_language() == "es"
