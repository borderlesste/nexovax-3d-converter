"""Genera docs/Matriz_de_compatibilidad.md a partir del enrutador (fuente única de verdad)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from u3dc.core.formats import FORMATS, FORMAT_ORDER  # noqa: E402
from u3dc.core.router import compatibility_matrix, CAPS  # noqa: E402

SYM = {0: "🟢 Directa", 1: "🔵 Teselación", 2: "🟡 Facetada", 3: "🟠 Limitada", 4: "🔴 No soportada"}


def main():
    cells = compatibility_matrix()
    L = ["# Matriz de compatibilidad de formatos", "",
         "Generada automáticamente desde `u3dc/core/router.py` (la misma lógica que usa la aplicación).", "",
         "## Leyenda", "",
         "| Nivel | Significado |", "|---|---|",
         "| 🟢 Directa | La geometría se transfiere sin cambio de representación (malla→malla o B-Rep→B-Rep). |",
         "| 🔵 Teselación | Superficies exactas (B-Rep CAD o geometría IFC) convertidas a triángulos con tolerancia configurable. |",
         "| 🟡 Facetada | Malla convertida a B-Rep facetado (cada triángulo = cara plana). Geométricamente válido, **no** es un sólido paramétrico. |",
         "| 🟠 Limitada | Conversión válida con pérdida relevante de información (p. ej. malla → IFC con entidades genéricas). |",
         "| 🔴 No soportada | Sin ruta técnica válida (ninguna combinación de los 8 formatos cae en esta categoría). |",
         "", "Conservación semántica: **Completa** (todo lo que el origen puede contener cabe en el destino), "
         "**Parcial** (se pierde parte: jerarquía, metadatos, texturas…) o **Solo geometría**.", "",
         "## Resumen (geometría · semántica)", "",
         "| Origen \\ Destino | " + " | ".join(FORMATS[f].name for f in FORMAT_ORDER) + " |",
         "|---|" + "---|" * len(FORMAT_ORDER)]
    for s in FORMAT_ORDER:
        row = []
        for d in FORMAT_ORDER:
            c = next(x for x in cells if x.source == s and x.target == d)
            row.append(f"{SYM[int(c.fidelity)]}<br>{c.semantic}")
        L.append(f"| **{FORMATS[s].name}** | " + " | ".join(row) + " |")
    L += ["", "## Capacidades de cada formato", "", "| Formato | Familia | Información que puede transportar |", "|---|---|---|"]
    for f in FORMAT_ORDER:
        L.append(f"| {FORMATS[f].long_name} | {FORMATS[f].family} | {', '.join(sorted(CAPS[f])) or 'solo geometría triangular'} |")
    L += ["", "## Detalle de cada combinación", ""]
    for s in FORMAT_ORDER:
        L.append(f"### Desde {FORMATS[s].name}")
        L.append("")
        for d in FORMAT_ORDER:
            c = next(x for x in cells if x.source == s and x.target == d)
            L.append(f"- **{FORMATS[s].name} → {FORMATS[d].name}** — {SYM[int(c.fidelity)]}, semántica {c.semantic.lower()}.  ")
            L.append(f"  Ruta: {' → '.join(c.route)}.  ")
            if c.losses:
                L.append(f"  Pérdidas posibles: {'; '.join(c.losses)}.  ")
            if c.note:
                L.append(f"  Nota: {c.note}")
        L.append("")
    out = os.path.join(ROOT, "docs", "Matriz_de_compatibilidad.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("Generado", out)


if __name__ == "__main__":
    main()
