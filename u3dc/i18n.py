"""Internacionalización: español (idioma de origen), francés y criollo haitiano.

* tr(texto, **valores): textos fijos de la interfaz. La clave es el propio texto en español.
* tr_msg(mensaje): mensajes dinámicos del motor (avisos, pérdidas, errores) ya formateados en
  español; se reconocen mediante plantillas con marcadores {nombre} y se traducen al mostrarlos.
  Así los informes JSON se guardan en un idioma canónico y se pueden mostrar en cualquier idioma.

Idioma activo: variable de entorno U3DC_LANG (la heredan los procesos de conversión) →
preferencia guardada → idioma de Windows → español.
Para añadir un idioma: crear u3dc/locales/<código>.py con STATIC y MESSAGES y añadirlo a LANGUAGES.
"""
from __future__ import annotations

import importlib
import os
import re
from functools import lru_cache

LANGUAGES = {"es": "Español", "fr": "Français", "ht": "Kreyòl ayisyen"}
DEFAULT = "es"
_current: str | None = None


def system_language() -> str:
    """Idioma de la interfaz de Windows (es/fr/ht) o español por defecto."""
    name = ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
            name = buf.value
    except Exception:
        import locale
        name = (locale.getlocale()[0] or "")
    name = name.lower().replace("_", "-")
    if name.startswith("ht"):          # ht-HT: criollo haitiano
        return "ht"
    if name.startswith("fr"):
        return "fr"
    return "es" if name.startswith("es") else DEFAULT


def set_language(code: str) -> None:
    global _current
    code = code if code in LANGUAGES else DEFAULT
    _current = code
    os.environ["U3DC_LANG"] = code          # los procesos hijos heredan el idioma
    _catalog.cache_clear()
    _patterns.cache_clear()


def get_language() -> str:
    global _current
    if _current is None:
        env = os.environ.get("U3DC_LANG")
        _current = env if env in LANGUAGES else system_language()
    return _current


@lru_cache(maxsize=None)
def _catalog(code: str) -> tuple[dict, list]:
    if code == DEFAULT:
        return {}, []
    mod = importlib.import_module(f"u3dc.locales.{code}")
    return mod.STATIC, mod.MESSAGES


def tr(text: str, **values) -> str:
    static, _ = _catalog(get_language())
    out = static.get(text, text)
    if values:
        try:
            out = out.format(**values)
        except (KeyError, IndexError, ValueError):
            out = text.format(**values)
    return out


_FIELD = re.compile(r"\{(\w+)(?::[^}]*)?\}")


def _compile(template: str) -> re.Pattern:
    parts, pos = [], 0
    for m in _FIELD.finditer(template):
        parts.append(re.escape(template[pos:m.start()]))
        parts.append(f"(?P<{m.group(1)}>.*?)")
        pos = m.end()
    parts.append(re.escape(template[pos:]))
    return re.compile("^" + "".join(parts) + "$", re.S)


@lru_cache(maxsize=None)
def _patterns(code: str) -> list:
    _, messages = _catalog(code)
    pats = [(_compile(es), out) for es, out in messages]
    # las plantillas con más texto fijo primero (más específicas)
    pats.sort(key=lambda p: -len(_FIELD.sub("", p[0].pattern)))
    return pats


def tr_msg(message: str, _depth: int = 0) -> str:
    """Traduce un mensaje dinámico ya formateado en español."""
    if not message or get_language() == DEFAULT:
        return message
    static, _ = _catalog(get_language())
    if message in static:
        return static[message]
    if " ⇒ " in message:                      # pasos de una ruta
        return " ⇒ ".join(tr_msg(p, _depth + 1) for p in message.split(" ⇒ "))
    for pat, out in _patterns(get_language()):
        m = pat.match(message)
        if m:
            vals = {k: (tr_msg(v, _depth + 1) if _depth < 3 else v) for k, v in m.groupdict().items()}
            try:
                return _FIELD.sub(lambda f: vals.get(f.group(1), f.group(0)), out)
            except Exception:
                return message
    return message
