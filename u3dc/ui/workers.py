"""Hilos de trabajo de la interfaz. La conversión y la vista previa se ejecutan en procesos
aislados (core.jobs); estos hilos solo los supervisan, así la interfaz nunca se bloquea."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import uuid

from PySide6.QtCore import QThread, Signal

from ..core.jobs import run_isolated, run_preview_isolated
from ..core.options import ConversionOptions
from ..core.report import Status


class ConversionThread(QThread):
    job_started = Signal(int)
    job_progress = Signal(int, float, str)
    job_finished = Signal(int, object)          # ConversionReport
    batch_finished = Signal()

    def __init__(self, jobs: list[tuple[int, str, ConversionOptions]], parallel: int = 1, parent=None):
        super().__init__(parent)
        self.jobs = list(jobs)
        self.parallel = max(1, parallel)
        self.cancel_events = {jid: threading.Event() for jid, _, _ in jobs}
        self._stop = threading.Event()

    def cancel_all(self):
        self._stop.set()
        for e in self.cancel_events.values():
            e.set()

    def cancel_job(self, jid: int):
        if jid in self.cancel_events:
            self.cancel_events[jid].set()

    def run(self):
        pending = list(self.jobs)
        lock = threading.Lock()

        def worker():
            while True:
                with lock:
                    if not pending:
                        return
                    jid, src, opts = pending.pop(0)
                ev = self.cancel_events[jid]
                if ev.is_set() or self._stop.is_set():
                    from ..core.report import ConversionReport
                    rep = ConversionReport(source=src, target_format=opts.target_format)
                    rep.status = Status.CANCELLED
                    rep.error("Cancelado antes de comenzar.")
                    self.job_finished.emit(jid, rep)
                    continue
                self.job_started.emit(jid)
                rep = run_isolated(src, opts, lambda f, m, j=jid: self.job_progress.emit(j, f, m), ev)
                self.job_finished.emit(jid, rep)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(self.parallel)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.batch_finished.emit()


class PreviewThread(QThread):
    preview_ready = Signal(str, str, dict)     # ruta de origen, npz, info
    preview_failed = Signal(str, str)

    def __init__(self, source: str, options: ConversionOptions, parent=None):
        super().__init__(parent)
        self.source = source
        self.options = options

    def run(self):
        base = os.path.join(tempfile.gettempdir(), "u3dc")
        os.makedirs(base, exist_ok=True)
        out = os.path.join(base, f"u3dc_preview_{uuid.uuid4().hex[:10]}.npz")
        try:
            info = run_preview_isolated(self.source, self.options, out)
            self.preview_ready.emit(self.source, out, info)
        except Exception as e:
            self.preview_failed.emit(self.source, str(e))
