"""Orquestador de conversión: detección → importación → transformaciones → exportación →
validación → publicación atómica de resultados."""
from __future__ import annotations

import os
import time
import traceback

from . import adapters
from .formats import FORMATS, detect, DetectionError
from .options import ConversionOptions
from .report import ConversionReport, Fidelity, Status
from .router import find_route, semantic_level, runtime_losses, NOTES
from .safety import (make_staging_dir, cleanup_dir, unique_output_names, atomic_move, safe_filename,
                     needs_short_copy, copy_for_engine, long_path)
from .validator import validate_output


class Cancelled(Exception):
    pass


AUX_SUFFIXES = {"gltf": [".bin"], "obj": [".mtl"]}


def plan(source_fmt: str, target_fmt: str) -> dict:
    """Resumen de la ruta prevista (para la interfaz)."""
    r = find_route(source_fmt, target_fmt)
    if r is None:
        return {"supported": False, "fidelity": Fidelity.UNSUPPORTED, "steps": [], "losses": []}
    return {"supported": True, "fidelity": r.fidelity, "steps": r.steps, "losses": r.losses(),
            "semantic": semantic_level(source_fmt, target_fmt), "note": NOTES.get((source_fmt, target_fmt), "")}


def convert_file(source: str, options: ConversionOptions, progress=None, cancelled=None,
                 staging: str | None = None, write_diag: bool = True) -> ConversionReport:
    """Convierte un archivo. Nunca modifica el original. Devuelve siempre un informe.

    staging: carpeta temporal creada por el proceso padre (que la limpia aunque este proceso muera).
    write_diag: escribir el registro de diagnóstico (en modo aislado lo escribe el proceso padre,
    que además conoce el código de salida y la salida estándar/errores del proceso).
    """
    report = ConversionReport(source=os.path.abspath(source), target_format=options.target_format)
    own_staging = staging is None

    def step(frac: float, msg: str):
        if cancelled is not None and cancelled():
            raise Cancelled()
        if progress:
            progress(frac, msg)

    try:
        report.set_stage("detección de formato")
        step(0.0, "Detectando formato")
        if not os.path.isfile(long_path(source)):
            raise DetectionError(f"El archivo no existe: {source}")
        size_mb = os.path.getsize(long_path(source)) / 1e6
        if size_mb > options.max_file_mb:
            raise ValueError(f"El archivo ({size_mb:.0f} MB) supera el límite configurado de {options.max_file_mb} MB.")
        src_fmt, det_warn = detect(long_path(source))
        for w in det_warn:
            report.warn(w)
        report.source_format = src_fmt
        dst_fmt = options.target_format
        if dst_fmt not in FORMATS:
            raise ValueError(f"Formato de destino desconocido: {dst_fmt}")
        route = find_route(src_fmt, dst_fmt)
        if route is None:
            raise ValueError(f"No existe una ruta técnica válida de {FORMATS[src_fmt].name} a {FORMATS[dst_fmt].name}.")
        report.route = route.steps
        report.fidelity = int(route.fidelity)
        report.semantic = semantic_level(src_fmt, dst_fmt)
        report.info(f"Ruta: {' ⇒ '.join(route.steps)}")
        for l in runtime_losses(route):
            report.loss(l)

        # --------------------------------------------------------- preparación
        if own_staging:
            staging = make_staging_dir()
        work_input = source
        if FORMATS[src_fmt].family in ("cad", "bim") and needs_short_copy(source):
            work_input = copy_for_engine(source, staging, src_fmt)
            report.info("Ruta larga o con caracteres no ASCII: se usa una copia temporal para el motor CAD/BIM.")
        elif len(os.path.abspath(source)) >= 240:
            work_input = long_path(source)

        # --------------------------------------------------------- importación
        report.set_stage("lectura del archivo")
        step(0.05, f"Importando {FORMATS[src_fmt].name}")
        t0 = time.time()
        rep, model = adapters.read(src_fmt, work_input, options, report,
                                   progress=lambda f, m: step(0.05 + 0.25 * f, m))
        report.stats["importacion_s"] = round(time.time() - t0, 2)
        _record_ignored(model, report)

        # --------------------------------------------------------- transformaciones
        # La escala del usuario se aplica en la primera representación geométrica (malla o CAD).
        scaled = False
        if rep in ("scene", "cad"):
            model = adapters.apply_user_scale(rep, model, options.scale, report)
            scaled = True
        last_bounds = adapters.canonical_bounds(rep, model)
        reps = route.representations
        for i, nxt in enumerate(reps[1:], start=1):
            report.set_stage(f"transformación {rep} → {nxt}")
            step(0.3 + 0.1 * i, f"Transformando {rep} → {nxt}")
            t0 = time.time()
            base = 0.3 + 0.1 * i
            model = adapters.transform(rep, nxt, model, options, report,
                                       progress=lambda f, m, b=base: step(b + 0.25 * f, m))
            report.stats[f"{rep}_a_{nxt}_s"] = round(time.time() - t0, 2)
            rep = nxt
            if not scaled and rep in ("scene", "cad"):
                model = adapters.apply_user_scale(rep, model, options.scale, report)
                scaled = True
            b = adapters.canonical_bounds(rep, model)
            if b is not None:
                last_bounds = b
        if not scaled:
            adapters.apply_user_scale(rep, model, options.scale, report)   # IFC → IFC: solo advierte

        expected = {"bounds": adapters.canonical_bounds(rep, model) if rep != "bim" else last_bounds,
                    "instances": adapters.instance_count(rep, model),
                    "tolerance_m": float(getattr(model, "metadata", {}).get("tolerance_mm", 0.0)) / 1000.0}
        if rep == "scene" and options.merge_by_material and dst_fmt in ("gltf", "glb", "fbx", "obj"):
            from ..models.scene import merge_by_material
            model = merge_by_material(model)
            report.loss("Geometría fusionada por material: se pierden la jerarquía y los nombres individuales.")
            expected["instances"] = adapters.instance_count(rep, model)
        if rep == "scene":
            report.stats["triangulos"] = model.triangle_count()
            report.stats["objetos"] = expected["instances"]
            _mesh_checks(model, report, options)
        elif rep == "cad":
            report.stats["piezas"] = len(model.parts)
        elif rep == "bim":
            report.stats["productos_ifc"] = expected["instances"]
        if expected["bounds"] is not None:
            size = expected["bounds"][1] - expected["bounds"][0]
            report.stats["dimensiones_m"] = [round(float(x), 6) for x in size]

        # --------------------------------------------------------- exportación
        report.set_stage(f"exportación {FORMATS[dst_fmt].name}")
        step(0.75, f"Exportando {FORMATS[dst_fmt].name}")
        out_dir = options.output_dir or os.path.dirname(os.path.abspath(source))
        os.makedirs(long_path(out_dir), exist_ok=True)
        ext = FORMATS[dst_fmt].extensions[0]
        stem = safe_filename(os.path.splitext(os.path.basename(source))[0])
        stem = unique_output_names(out_dir, stem, ext, AUX_SUFFIXES.get(dst_fmt, []) + ["_tex0.png", "_tex0.jpg"],
                                   options.overwrite)
        # Escritores Python: nombre definitivo (las referencias internas quedan correctas).
        # Escritores C++ (OCCT/IfcOpenShell): nombre ASCII corto y renombrado posterior.
        stage_stem = stem if rep == "scene" else "model"
        stage_main = os.path.join(staging, "out", stage_stem + ext)
        os.makedirs(os.path.dirname(stage_main), exist_ok=True)
        t0 = time.time()
        if rep == "scene":
            frame = adapters.output_frame(dst_fmt, model, options)
        else:
            frame = (1.0, "Z")
        files = adapters.write(dst_fmt, rep, model, stage_main, options, report)
        report.stats["exportacion_s"] = round(time.time() - t0, 2)
        if stage_stem != stem:
            files = _rename_staged(files, stage_main, stem, dst_fmt)
        expected["frame"] = frame
        expected["check_instances"] = not (src_fmt in ("gltf", "glb", "obj") or dst_fmt in ("obj", "stl"))

        # --------------------------------------------------------- validación
        if options.validate:
            report.set_stage("validación del resultado")
            step(0.88, "Validando el resultado")
            t0 = time.time()
            report.validation = validate_output(files, dst_fmt, options, expected, report)
            report.stats["validacion_s"] = round(time.time() - t0, 2)
        else:
            report.warn("Validación posterior desactivada por configuración.")

        # --------------------------------------------------------- publicación atómica
        report.set_stage("publicación de archivos")
        step(0.97, "Guardando archivos")
        outputs = []
        for f in files:
            name = os.path.basename(f)
            final = os.path.join(out_dir, name)
            atomic_move(f, final, options.overwrite)
            outputs.append(final)
        report.outputs = outputs
        report.status = Status.SUCCESS_WARNINGS if (report.warnings or report.losses
                                                    or not report.validation.get("ok", True)) else Status.SUCCESS
        report.info("Conversión finalizada.")
        step(1.0, "Completado")
        report.set_stage("completada")
    except Cancelled:
        report.status = Status.CANCELLED
        report.error("Conversión cancelada por el usuario.")
    except MemoryError:
        report.status = Status.FAILED
        report.error(f"Memoria insuficiente para procesar el modelo (etapa: {report.stage}).")
        report.traceback = traceback.format_exc()
        report.technical["excepcion"] = {"tipo": "MemoryError", "etapa": report.stage}
    except Exception as e:  # cualquier fallo se informa; el original nunca se toca
        report.status = Status.FAILED
        report.error(_friendly(e))
        report.traceback = traceback.format_exc()
        report.technical["excepcion"] = {"tipo": f"{type(e).__module__}.{type(e).__name__}",
                                         "mensaje": str(e), "etapa": report.stage}
    finally:
        report.stage_times[report.stage] = round(report.stage_times.get(report.stage, 0.0)
                                                 + time.time() - getattr(report, "_t", time.time()), 2)
        if own_staging:
            cleanup_dir(staging)
        report.finished = time.time()
        from .diagnostics import peak_memory_mb, write_log
        report.stats["memoria_maxima_mb"] = peak_memory_mb()
        report.stats["duracion_total_s"] = round(report.finished - report.started, 2)
        if write_diag:
            write_log(report, options)
    return report


def _rename_staged(files: list[str], stage_main: str, stem: str, fmt: str) -> list[str]:
    """Renombra 'model.*' → '<stem>.*' y actualiza las referencias en glTF/OBJ."""
    import json
    out = []
    d = os.path.dirname(stage_main)
    mapping = {}
    for f in files:
        base = os.path.basename(f)
        new = stem + base[len("model"):] if base.startswith("model") else base
        mapping[base] = new
    for f in files:
        base = os.path.basename(f)
        dst = os.path.join(d, mapping[base])
        if f != dst:
            os.replace(f, dst)
        out.append(dst)
    main = out[0]
    if fmt == "gltf":
        with open(main, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        for kind in ("buffers", "images"):
            for item in doc.get(kind, []):
                if "uri" in item and item["uri"] in mapping:
                    item["uri"] = mapping[item["uri"]]
        with open(main, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
    elif fmt == "obj":
        _rewrite_refs(main, mapping, ("mtllib ",))
        mtl = [p for p in out if p.endswith(".mtl")]
        if mtl:
            _rewrite_refs(mtl[0], mapping, ("map_Kd ",))
    elif fmt == "fbx":
        pass   # las texturas FBX van embebidas; el nombre externo es solo informativo
    return out


def _rewrite_refs(path: str, mapping: dict, prefixes: tuple):
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    for i, line in enumerate(lines):
        for p in prefixes:
            if line.startswith(p):
                ref = line[len(p):].strip()
                if ref in mapping:
                    lines[i] = f"{p}{mapping[ref]}\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(lines)


def _record_ignored(model, report):
    for item in getattr(model, "ignored", []) or []:
        report.loss(item)


def _mesh_checks(scene, report, options):
    from ..models.scene import mesh_quality, compute_vertex_normals
    degenerate = open_meshes = 0
    for m in scene.meshes:
        if len(m.faces) == 0:
            continue
        q = mesh_quality(m.vertices, m.faces)
        degenerate += q["degenerate"]
        open_meshes += 0 if q["closed"] else 1
        if options.fix_normals and m.normals is None:
            m.normals = compute_vertex_normals(m.vertices, m.faces)
        elif options.fix_normals and m.normals is not None:
            bad = ~np.isfinite(m.normals).all(axis=1) | (np.linalg.norm(m.normals, axis=1) < 1e-6)
            if bad.any():
                m.normals = compute_vertex_normals(m.vertices, m.faces)
                report.info(f"Normales no válidas recalculadas en '{m.name}'.")
    report.stats["triangulos_degenerados"] = degenerate
    report.stats["mallas_abiertas"] = open_meshes
    if degenerate:
        report.warn(f"{degenerate} triángulo(s) degenerado(s) (área nula) detectados.")


import numpy as np  # noqa: E402  (usado en _mesh_checks)


def _friendly(e: Exception) -> str:
    msg = str(e) or type(e).__name__
    if isinstance(e, FileNotFoundError):
        return f"Archivo no encontrado: {msg}"
    if isinstance(e, PermissionError):
        return f"Permiso denegado: {msg}"
    if isinstance(e, (DetectionError, ValueError, TimeoutError, FileExistsError)):
        return msg
    # excepción de una biblioteca (OCCT, IfcOpenShell…): se conserva su tipo para poder identificarla
    return f"{type(e).__name__}: {msg}"
