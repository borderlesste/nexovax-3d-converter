"""Reproduce la ruta STL → STEP con casos patológicos, en proceso aislado (como la interfaz).

Uso:  python tools/repro_stl_step.py <carpeta_trabajo> [casos...]
Imprime estado, causa, código de salida, tiempo y memoria de cada caso.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from tests import stl_cases as C  # noqa: E402
from u3dc.core.jobs import run_isolated  # noqa: E402
from u3dc.core.options import ConversionOptions  # noqa: E402

CASES = {
    "cubo_cerrado": lambda: C.box(0, 0, 0, 20, 30, 40),
    "malla_abierta": lambda: C.grid(30, 30, z=lambda x, y: 5 * np.sin(x / 15) * np.cos(y / 15)),
    "multi_componente": lambda: np.concatenate([C.box(0, 0, 0, 10, 10, 10), C.box(20, 0, 0, 30, 10, 10),
                                                C.sphere_fast(5, 24, (50, 5, 5))]),
    "degenerados": lambda: np.concatenate([C.box(0, 0, 0, 10, 10, 10), C.box(0, 0, 0, 10, 10, 10)[:4, [0, 1, 1]]]),
    "no_manifold": lambda: np.concatenate([C.box(0, 0, 0, 10, 10, 10), C.box(10, 10, 0, 20, 20, 10)]),
    "orientacion_mezclada": lambda: (lambda t: np.concatenate([t[:6], t[6:, ::-1]]))(C.box(0, 0, 0, 10, 10, 10)),
    "lipo_battery": lambda: C.lipo_battery(120),
    "denso_150k": lambda: C.sphere_fast(50, 275),
    "denso_400k": lambda: C.sphere_fast(50, 448),
}


def main():
    work = sys.argv[1]
    names = sys.argv[2:] or list(CASES)
    os.makedirs(work, exist_ok=True)
    for name in names:
        tris = CASES[name]()
        src = C.write_stl(os.path.join(work, f"{name}.stl"), tris)
        t0 = time.time()
        rep = run_isolated(src, ConversionOptions(target_format="step", output_dir=os.path.join(work, "out"),
                                                  overwrite=True))
        dt = time.time() - t0
        print(f"== {name}: {len(tris):,} triángulos · {rep.status} · {dt:.1f} s")
        for e in rep.errors:
            print("   ERROR:", e[:300])
        for w in rep.warnings[:6]:
            print("   aviso:", w[:200])
        t = rep.technical.get("malla_a_brep", {})
        for m in t.get("mallas", []):
            mo = m.get("malla_original", {})
            print(f"   malla: {mo.get('triangles')} △, {mo.get('componentes')} comp., estado {mo.get('estado')}, "
                  f"abiertas {mo.get('aristas_abiertas')}, no-manifold {mo.get('aristas_no_manifold')}, "
                  f"incoherentes {mo.get('aristas_orientacion_incoherente')}, degenerados {mo.get('degenerate_triangles')}, "
                  f"duplicados {mo.get('duplicate_triangles')} → {m.get('resultado')}")
            if m.get("simplificacion"):
                print("   simplificación:", m["simplificacion"])
        print(f"   etapa={rep.stage} memoria={rep.stats.get('memoria_maxima_mb')} MB escritura={rep.technical.get('escritura_cad')}")
        for k in ("solidos", "caras", "formas_no_validas"):
            if k in rep.validation:
                print(f"   {k}={rep.validation[k]}", end="")
        print()
        diag = getattr(rep, "diagnostic_log", "") or rep.stats.get("diagnostico")
        if diag:
            print("   diagnóstico:", diag)


if __name__ == "__main__":
    main()
