"""Ejecución aislada de conversiones en procesos independientes.

Cada conversión corre en su propio proceso (multiprocessing 'spawn'): si un motor nativo
falla (violación de acceso, memoria agotada, bucle), el proceso se pierde pero la
aplicación sigue funcionando y el trabajo se marca como fallido. Cancelar = terminar
el proceso; la carpeta temporal se limpia y el archivo original nunca se modifica.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import queue
import threading
import time
from dataclasses import dataclass, field

from .options import ConversionOptions
from .report import ConversionReport, Status


def _capture_native_output(staging: str):
    """Redirige stdout/stderr del proceso (también la salida de C/C++) a un archivo y activa
    faulthandler para volcar la pila de Python si se produce un fallo nativo."""
    import faulthandler
    import sys
    try:
        out = open(os.path.join(staging, "proceso_stdout_stderr.txt"), "w", buffering=1, encoding="utf-8",
                   errors="replace")
        os.dup2(out.fileno(), 1)
        os.dup2(out.fileno(), 2)
        sys.stdout = sys.stderr = out
        fh = open(os.path.join(staging, "proceso_faulthandler.txt"), "w")
        faulthandler.enable(fh, all_threads=True)
        _capture_native_output.keep = (out, fh)
    except Exception:
        pass


def _worker(source: str, options: dict, q, staging: str):
    try:
        _capture_native_output(staging)
        from . import report as report_mod
        from .converter import convert_file
        opts = ConversionOptions.from_dict(options)
        report_mod.STAGE_HOOK = lambda s: q.put(("stage", s))
        report_mod.CHECKPOINT_PATH = os.path.join(staging, "punto_control.json")

        def prog(f, m):
            try:
                q.put(("progress", float(f), str(m)))
            except Exception:
                pass

        rep = convert_file(source, opts, progress=prog, staging=staging, write_diag=False)
        q.put(("done", rep.to_dict()))
    except BaseException as e:   # noqa: BLE001
        import traceback
        try:
            q.put(("crash", f"{type(e).__name__}: {e}", traceback.format_exc()))
        except Exception:
            pass
    finally:
        try:
            q.close()
            q.join_thread()
        except Exception:
            pass


def _preview_worker(source: str, options: dict, out_path: str, q):
    try:
        from .preview import build_preview
        info = build_preview(source, ConversionOptions.from_dict(options), out_path)
        q.put(("done", info))
    except BaseException as e:   # noqa: BLE001
        try:
            q.put(("crash", f"{type(e).__name__}: {e}"))
        except Exception:
            pass
    finally:
        try:
            q.close()
            q.join_thread()
        except Exception:
            pass


def run_isolated(source: str, options: ConversionOptions, on_progress=None, cancel_event: threading.Event | None = None,
                 timeout: float | None = None) -> ConversionReport:
    """Ejecuta convert_file en un proceso aislado y SIEMPRE devuelve un informe con la causa del fallo,
    la etapa en la que estaba, el código de salida interpretado y un registro de diagnóstico local."""
    from . import diagnostics
    from .safety import make_staging_dir, cleanup_dir
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    staging = make_staging_dir()
    t_start = time.time()
    proc = ctx.Process(target=_worker, args=(source, options.to_dict(), q, staging), daemon=False)
    proc.start()
    limit = timeout or options.timeout_s
    deadline = time.time() + limit
    result = None
    crash = None
    reason = None
    last_stage, last_msg = "inicio del proceso", ""
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                reason = "cancelado"
                proc.terminate()
                break
            if time.time() > deadline:
                reason = "tiempo"
                proc.terminate()
                break
            try:
                msg = q.get(timeout=0.2)
            except queue.Empty:
                if not proc.is_alive():
                    try:
                        msg = q.get(timeout=0.5)
                    except queue.Empty:
                        break
                else:
                    continue
            kind = msg[0]
            if kind == "progress":
                last_msg = msg[2]
                if on_progress:
                    on_progress(msg[1], msg[2])
            elif kind == "stage":
                last_stage = msg[1]
            elif kind == "done":
                result = msg[1]
                break
            elif kind == "crash":
                crash = msg
                break
    finally:
        proc.join(10)
        if proc.is_alive():
            proc.kill()
            proc.join(5)
    process = {"codigo_salida": proc.exitcode, "interpretacion": diagnostics.explain_exit_code(proc.exitcode),
               "duracion_s": round(time.time() - t_start, 2), "ultima_actividad": last_msg}
    process.update(diagnostics.read_process_capture(staging))
    try:
        if result is not None:
            rep = ConversionReport.from_dict(result)
        else:
            rep = ConversionReport(source=os.path.abspath(source), target_format=options.target_format)
            rep.started = t_start
            rep.stage = last_stage
            cp = _read_checkpoint(staging)          # etapa, análisis y registro hasta el momento del fallo
            if cp:
                rep.stage = last_stage = cp.get("stage") or last_stage
                for k in ("source_format", "route", "technical", "warnings", "losses", "stats", "stage_times"):
                    if cp.get(k):
                        setattr(rep, k, cp[k])
                rep.log = [tuple(x) for x in cp.get("log", [])]
            if not rep.source_format:
                try:
                    from .formats import detect
                    rep.source_format = detect(source)[0]
                except Exception:
                    pass
            if reason == "cancelado":
                rep.status = Status.CANCELLED
                rep.error("Conversión cancelada por el usuario.")
                process["motivo"] = "cancelación del usuario"
            elif reason == "tiempo":
                rep.error(f"Tiempo máximo excedido ({int(limit)} s) en la etapa «{last_stage}»; proceso detenido. "
                          "Aumente el tiempo máximo o reduzca/simplifique el modelo.")
                process["motivo"] = "tiempo máximo excedido"
            elif crash:
                rep.error(f"Error interno del motor en la etapa «{last_stage}»: {crash[1]}")
                rep.traceback = crash[2] if len(crash) > 2 else ""
                process["motivo"] = "excepción no controlada en el proceso de trabajo"
            else:
                rep.error(f"El motor de conversión terminó de forma anormal en la etapa «{last_stage}» "
                          f"(código {process['interpretacion']}). Consulte el registro de diagnóstico.")
                process["motivo"] = "fin anormal del proceso (fallo nativo o falta de memoria)"
            rep.finished = time.time()
        rep.technical["proceso"] = {k: v for k, v in process.items() if k not in ("stdout_stderr", "faulthandler")}
        if process.get("faulthandler"):
            rep.technical["proceso"]["faulthandler_resumen"] = process["faulthandler"][-1500:]
        diagnostics.write_log(rep, options, process)
        return rep
    finally:
        cleanup_dir(staging)


def _read_checkpoint(staging: str) -> dict:
    import json
    try:
        with open(os.path.join(staging, "punto_control.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def run_preview_isolated(source: str, options: ConversionOptions, out_path: str, timeout: float = 600) -> dict:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    proc = ctx.Process(target=_preview_worker, args=(source, options.to_dict(), out_path, q), daemon=False)
    proc.start()
    try:
        try:
            kind, payload = q.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Vista previa: tiempo excedido o proceso detenido.")
    finally:
        proc.join(10)
        if proc.is_alive():
            proc.kill()
    if kind != "done":
        raise RuntimeError(payload)
    return payload


@dataclass
class Job:
    source: str
    options: ConversionOptions
    id: int = 0
    status: str = "pendiente"          # pendiente | en_cola | en_conversion | exitoso | ... | cancelado
    progress: float = 0.0
    message: str = ""
    report: ConversionReport | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class BatchRunner:
    """Procesa una lista de trabajos (secuencial o con N procesos en paralelo)."""

    def __init__(self, jobs: list[Job], parallel: int = 1, on_update=None):
        self.jobs = jobs
        self.parallel = max(1, parallel)
        self.on_update = on_update or (lambda job: None)
        self._stop = threading.Event()

    def cancel_all(self):
        self._stop.set()
        for j in self.jobs:
            j.cancel.set()

    def run(self):
        pending = list(self.jobs)
        for j in pending:
            j.status = "en_cola"
            self.on_update(j)
        lock = threading.Lock()

        def worker():
            while not self._stop.is_set():
                with lock:
                    if not pending:
                        return
                    job = pending.pop(0)
                if job.cancel.is_set():
                    job.status = Status.CANCELLED
                    self.on_update(job)
                    continue
                job.status = "en_conversion"
                self.on_update(job)

                def prog(f, m, job=job):
                    job.progress, job.message = f, m
                    self.on_update(job)

                job.report = run_isolated(job.source, job.options, prog, job.cancel)
                job.status = job.report.status
                job.progress = 1.0
                self.on_update(job)
            with lock:
                for j in pending:
                    j.status = Status.CANCELLED
                    self.on_update(j)
                pending.clear()

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(self.parallel)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
