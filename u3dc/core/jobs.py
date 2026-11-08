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


def _worker(source: str, options: dict, q):
    try:
        from .converter import convert_file
        opts = ConversionOptions.from_dict(options)

        def prog(f, m):
            try:
                q.put(("progress", float(f), str(m)))
            except Exception:
                pass

        rep = convert_file(source, opts, progress=prog)
        q.put(("done", rep.to_dict()))
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
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(source, options.to_dict(), q), daemon=False)
    proc.start()
    deadline = time.time() + (timeout or options.timeout_s)
    result = None
    crash = None
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                proc.join(5)
                rep = ConversionReport(source=os.path.abspath(source), target_format=options.target_format)
                rep.status = Status.CANCELLED
                rep.error("Conversión cancelada por el usuario.")
                return rep
            if time.time() > deadline:
                proc.terminate()
                proc.join(5)
                rep = ConversionReport(source=os.path.abspath(source), target_format=options.target_format)
                rep.error(f"Tiempo máximo excedido ({int(timeout or options.timeout_s)} s); proceso detenido.")
                return rep
            try:
                msg = q.get(timeout=0.2)
            except queue.Empty:
                if not proc.is_alive():
                    # vaciar mensajes pendientes
                    try:
                        msg = q.get(timeout=0.5)
                    except queue.Empty:
                        break
                else:
                    continue
            kind = msg[0]
            if kind == "progress" and on_progress:
                on_progress(msg[1], msg[2])
            elif kind == "done":
                result = msg[1]
                break
            elif kind == "crash":
                crash = msg[1]
                break
    finally:
        proc.join(10)
        if proc.is_alive():
            proc.kill()
    if result is not None:
        return ConversionReport.from_dict(result)
    rep = ConversionReport(source=os.path.abspath(source), target_format=options.target_format)
    if crash:
        rep.error(f"Error interno del motor: {crash}")
    else:
        rep.error(f"El motor de conversión terminó inesperadamente (código {proc.exitcode}). "
                  "El archivo puede estar dañado o requerir más memoria.")
    return rep


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
