"""Lista los textos traducibles: literales tr("…") del código + textos canónicos del motor.

Uso:  python tools/i18n_keys.py [--missing fr|ht]
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def tr_literals() -> list[str]:
    keys = []
    for r, _, fs in os.walk(os.path.join(ROOT, "u3dc")):
        if "locales" in r:
            continue
        for f in fs:
            if f.endswith(".py"):
                t = ast.parse(open(os.path.join(r, f), encoding="utf-8").read())
                for n in ast.walk(t):
                    if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args \
                            and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                        keys.append(n.args[0].value)
    return keys


def canonical() -> list[str]:
    from u3dc.core import router
    from u3dc.core.formats import FORMATS
    from u3dc.core.options import UNIT_LABELS
    from u3dc.core.report import FIDELITY_LABELS, Status
    out = [e.description for e in router.EDGES] + [l for e in router.EDGES for l in e.losses]
    out += list(router.NOTES.values()) + sorted({c for caps in router.CAPS.values() for c in caps})
    out += ["Completa", "Parcial", "Solo geometría"]
    out += list(FIDELITY_LABELS.values()) + list(Status.LABELS.values())
    out += [f.long_name for f in FORMATS.values()] + list(UNIT_LABELS.values())
    return out


IDENTITY = {"Open CASCADE (OCP)", "IfcOpenShell", "PySide6", "Qt / PySide6", "NumPy", "LICENCIAS_TERCEROS.html"}


def needs_translation(k: str) -> bool:
    s = k.strip()
    if s in IDENTITY or s in ("", "m", "mm", "cm", "in", "ft", "s"):
        return False
    return any(c.islower() for c in s) or (s.replace("Á", "A").replace("É", "E").replace("Í", "I").isalpha() and len(s) >= 6)


def all_keys() -> list[str]:
    seen, out = set(), []
    for k in tr_literals() + canonical():
        if k not in seen and needs_translation(k):
            seen.add(k)
            out.append(k)
    return out


if __name__ == "__main__":
    keys = all_keys()
    if len(sys.argv) > 2 and sys.argv[1] == "--missing":
        import importlib
        mod = importlib.import_module(f"u3dc.locales.{sys.argv[2]}")
        keys = [k for k in keys if k not in mod.STATIC]
    for k in keys:
        print(repr(k))
    print(len(keys), "claves", file=sys.stderr)
