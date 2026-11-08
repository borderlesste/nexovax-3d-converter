"""Ejecuta la matriz completa de conversiones sobre test_assets/ y documenta los resultados.

Uso:  python tests/run_matrix.py [--parallel N] [--out carpeta]
Genera docs/resultados_matriz.md y docs/resultados_matriz.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from u3dc.core.formats import FORMATS, FORMAT_ORDER  # noqa: E402
from u3dc.core.jobs import Job, BatchRunner  # noqa: E402
from u3dc.core.options import ConversionOptions  # noqa: E402
from u3dc.core.report import Fidelity  # noqa: E402

SOURCES = [
    "escena.gltf", "escena_jerarquia.glb", "mueble.obj", "robot_jerarquia.fbx", "cubo_ascii.fbx",
    "soporte_binario.stl", "dos_solidos_ascii.stl", "edificio_ifc4.ifc", "almacen_ifc2x3.ifc",
    "ensamblaje_mecanico.step", "ensamblaje_mecanico.igs",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    assets = os.path.join(ROOT, "test_assets")
    out_root = args.out or os.path.join(ROOT, "build", "matrix_out")
    jobs = []
    for src in SOURCES:
        for dst in FORMAT_ORDER:
            od = os.path.join(out_root, f"{os.path.splitext(src)[0]}_{os.path.splitext(src)[1][1:]}", dst)
            os.makedirs(od, exist_ok=True)
            jobs.append(Job(os.path.join(assets, src), ConversionOptions(target_format=dst, output_dir=od, overwrite=True)))
    t0 = time.time()
    done = [0]

    def upd(job):
        if job.report is not None and job.progress >= 1.0 and not getattr(job, "_printed", False):
            job._printed = True
            done[0] += 1
            r = job.report
            print(f"[{done[0]:3}/{len(jobs)}] {os.path.basename(job.source):28} → {job.options.target_format:5} "
                  f"{r.status_label:26} {r.fidelity_label}", flush=True)

    BatchRunner(jobs, parallel=args.parallel, on_update=upd).run()
    rows = []
    for j in jobs:
        r = j.report
        rows.append({"origen": os.path.basename(j.source), "formato_origen": r.source_format,
                     "destino": j.options.target_format, "estado": r.status, "fidelidad": Fidelity(r.fidelity).label,
                     "semantica": r.semantic, "validacion": r.validation, "estadisticas": {k: v for k, v in r.stats.items() if k != "traza"},
                     "advertencias": r.warnings, "perdidas": r.losses, "errores": r.errors,
                     "salidas": [os.path.relpath(o, out_root) for o in r.outputs]})
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "resultados_matriz.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)
    ok = sum(1 for r in rows if r["estado"].startswith("exitoso"))
    lines = ["# Resultados de la matriz de conversiones", "",
             f"Ejecutado: {time.strftime('%Y-%m-%d %H:%M')} · {len(rows)} conversiones · {ok} correctas · "
             f"{len(rows) - ok} fallidas · {time.time() - t0:.0f} s", "",
             "Estado: ✅ exitoso · ⚠️ exitoso con advertencias (pérdidas documentadas) · ❌ fallido", "",
             "| Origen | " + " | ".join(FORMATS[f].name for f in FORMAT_ORDER) + " |",
             "|---|" + "---|" * len(FORMAT_ORDER)]
    sym = {"exitoso": "✅", "exitoso_con_advertencias": "⚠️", "fallido": "❌", "cancelado": "⏹"}
    for src in SOURCES:
        cells = []
        for dst in FORMAT_ORDER:
            r = next(x for x in rows if x["origen"] == src and x["destino"] == dst)
            v = r["validacion"]
            dev = v.get("desviacion_dimensiones_m")
            cell = sym.get(r["estado"], "?") + " " + r["fidelidad"].split(" ")[0]
            if dev is not None:
                cell += f" (Δ{dev * 1000:.3g} mm)"
            cells.append(cell)
        lines.append(f"| {src} | " + " | ".join(cells) + " |")
    lines += ["", "Δ = máxima desviación de la caja envolvente entre el modelo intermedio y el archivo generado "
              "releído (validación automática).", "", "## Errores", ""]
    errs = [r for r in rows if r["errores"]]
    lines += [f"- {r['origen']} → {r['destino']}: {'; '.join(r['errores'])}" for r in errs] or ["Ninguno."]
    with open(os.path.join(ROOT, "docs", "resultados_matriz.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n{ok}/{len(rows)} conversiones correctas en {time.time() - t0:.0f} s")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
