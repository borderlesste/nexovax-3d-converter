"""Interfaz de línea de comandos.

Ejemplos:
  NEXOVAX3DConverter.exe convert pieza.step -t stl -o C:\\salida
  NEXOVAX3DConverter.exe convert *.ifc -t glb --quality media
  NEXOVAX3DConverter.exe matrix
  NEXOVAX3DConverter.exe info modelo.fbx
"""
from __future__ import annotations

from .i18n import tr, tr_msg

import argparse
import glob
import json
import os
import sys

from . import APP_NAME, __version__
from .core.formats import FORMATS, FORMAT_ORDER, ALL_EXTENSIONS, detect
from .core.options import ConversionOptions, UNITS_TO_METERS, QUALITY_PRESETS
from .core.report import Status


def _expand(inputs: list[str], recursive: bool) -> list[str]:
    out = []
    for item in inputs:
        if os.path.isdir(item):
            pattern = "**/*" if recursive else "*"
            for p in glob.glob(os.path.join(item, pattern), recursive=recursive):
                if os.path.splitext(p)[1].lower() in ALL_EXTENSIONS and os.path.isfile(p):
                    out.append(p)
        elif any(c in item for c in "*?["):
            out.extend(p for p in glob.glob(item) if os.path.isfile(p))
        else:
            out.append(item)
    return out


def cmd_convert(args) -> int:
    files = _expand(args.inputs, args.recursive)
    if not files:
        print(tr("No se encontraron archivos de entrada."), file=sys.stderr)
        return 2
    opts = ConversionOptions(
        target_format=args.to, output_dir=args.output or "", quality=args.quality,
        linear_tolerance_mm=args.tolerance, scale=args.scale, input_units=args.input_units,
        output_units=args.output_units, input_up_axis=args.input_up, output_up_axis=args.output_up,
        keep_materials=not args.no_materials, keep_structure=not args.no_structure,
        include_properties=not args.no_properties, stl_ascii=args.stl_ascii, gltf_embed=args.gltf_embed,
        ifc_schema=args.ifc_schema, step_schema=args.step_schema, overwrite=args.overwrite,
        validate=not args.no_validate, max_triangles_to_cad=args.max_cad_triangles, timeout_s=args.timeout,
        mesh_simplify="off" if args.no_simplify else "auto", mesh_target_triangles=args.target_triangles,
        mesh_repair=not args.no_repair, unify_coplanar=not args.no_unify)
    from .core.jobs import run_isolated
    from .core.converter import convert_file
    results = []
    failed = 0
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f} → {FORMATS[args.to].name}", flush=True)

        def prog(frac, msg):
            if args.verbose:
                print(f"   {frac * 100:5.1f}%  {tr_msg(msg)}", flush=True)

        rep = convert_file(f, opts, prog) if args.no_isolation else run_isolated(f, opts, prog)
        results.append(rep)
        print(f"   → {rep.status_label} · {rep.fidelity_label}" + (f" · {', '.join(rep.outputs)}" if rep.outputs else ""))
        for w in rep.warnings:
            print("   " + tr("ADVERTENCIA") + ": " + tr_msg(w))
        for l in rep.losses:
            print("   " + tr("PÉRDIDA") + ": " + tr_msg(l))
        for e in rep.errors:
            print("   ERROR: " + tr_msg(e))
        if rep.errors and rep.stage:
            print("   " + tr("Etapa del fallo: {s}", s=tr_msg(rep.stage)))
        if rep.diagnostic_log:
            print("   " + tr("Registro de diagnóstico: {p}", p=rep.diagnostic_log))
        if rep.status in (Status.FAILED, Status.CANCELLED):
            failed += 1
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump([r.to_dict() for r in results], fh, ensure_ascii=False, indent=1, default=str)
    print("\n" + tr("Resumen: {ok} correctas, {fail} fallidas.", ok=len(results) - failed, fail=failed))
    return 1 if failed else 0


def cmd_matrix(args) -> int:
    from .core.router import compatibility_matrix
    cells = compatibility_matrix()
    if args.json:
        print(json.dumps([{"origen": c.source, "destino": c.target, "fidelidad": c.fidelity.label,
                           "semantica": c.semantic, "ruta": c.route, "perdidas": c.losses, "nota": c.note}
                          for c in cells], ensure_ascii=False, indent=1))
        return 0
    head = "origen\\destino".ljust(15) + "".join(FORMATS[f].name.ljust(13) for f in FORMAT_ORDER)
    print(head)
    abbrev = {0: tr("Directa"), 1: tr("Teselación"), 2: tr("Facetada"), 3: tr("Limitada"), 4: "—"}
    for s in FORMAT_ORDER:
        row = FORMATS[s].name.ljust(15)
        for d in FORMAT_ORDER:
            c = next(x for x in cells if x.source == s and x.target == d)
            row += abbrev[int(c.fidelity)].ljust(13)
        print(row)
    return 0


def cmd_info(args) -> int:
    for f in args.inputs:
        fmt, warns = detect(f)
        print(f"{f}: {tr(FORMATS[fmt].long_name)} ({os.path.getsize(f):,} bytes)")
        for w in warns:
            print(f"   {tr_msg(w)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nexovax3d-cli", description=f"{APP_NAME} {__version__} — " + tr("modo consola"))
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("convert", help=tr("convertir archivos"))
    c.add_argument("inputs", nargs="+")
    c.add_argument("-t", "--to", required=True, choices=FORMAT_ORDER)
    c.add_argument("-o", "--output", help=tr("carpeta de salida (por defecto, la del archivo de origen)"))
    c.add_argument("-r", "--recursive", action="store_true")
    c.add_argument("--quality", default="alta", choices=list(QUALITY_PRESETS))
    c.add_argument("--tolerance", type=float, default=None, help=tr("tolerancia lineal de teselación en mm"))
    c.add_argument("--scale", type=float, default=1.0)
    c.add_argument("--input-units", default="auto", choices=["auto", *UNITS_TO_METERS])
    c.add_argument("--output-units", default="auto", choices=["auto", *UNITS_TO_METERS])
    c.add_argument("--input-up", default="auto", choices=["auto", "Y", "Z"])
    c.add_argument("--output-up", default="auto", choices=["auto", "Y", "Z"])
    c.add_argument("--no-materials", action="store_true")
    c.add_argument("--no-structure", action="store_true")
    c.add_argument("--no-properties", action="store_true")
    c.add_argument("--stl-ascii", action="store_true")
    c.add_argument("--gltf-embed", action="store_true")
    c.add_argument("--ifc-schema", default="IFC4", choices=["IFC4", "IFC2X3"])
    c.add_argument("--step-schema", default="AP214", choices=["AP203", "AP214", "AP242"])
    c.add_argument("--max-cad-triangles", type=int, default=1_000_000)
    c.add_argument("--no-simplify", action="store_true", help=tr("malla → CAD: no simplificar mallas densas"))
    c.add_argument("--target-triangles", type=int, default=100_000, help=tr("malla → CAD: objetivo de simplificación"))
    c.add_argument("--no-repair", action="store_true", help=tr("malla → CAD: no reparar la malla"))
    c.add_argument("--no-unify", action="store_true", help=tr("malla → CAD: no unir triángulos coplanares"))
    c.add_argument("--timeout", type=int, default=1800)
    c.add_argument("--overwrite", action="store_true")
    c.add_argument("--no-validate", action="store_true")
    c.add_argument("--no-isolation", action="store_true", help=tr("no usar proceso aislado (depuración)"))
    c.add_argument("--report", help=tr("guardar informe JSON"))
    c.add_argument("-v", "--verbose", action="store_true")
    c.set_defaults(func=cmd_convert)
    m = sub.add_parser("matrix", help=tr("mostrar la matriz de compatibilidad"))
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_matrix)
    i = sub.add_parser("info", help=tr("detectar el formato real de archivos"))
    i.add_argument("inputs", nargs="+")
    i.set_defaults(func=cmd_info)
    return p


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    from .i18n import set_language, get_language, LANGUAGES
    if "--lang" in argv:                      # --lang es|fr|ht (también variable U3DC_LANG)
        i = argv.index("--lang")
        code = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
        set_language(code if code in LANGUAGES else get_language())
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)
