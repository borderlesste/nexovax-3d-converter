"""Informe de conversión: estado, nivel de fidelidad, pérdidas y validación."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict
from enum import IntEnum

from ..i18n import tr, tr_msg


# Gancho opcional: el proceso de trabajo lo usa para comunicar la etapa al proceso padre, de modo que
# si el proceso muere por un fallo nativo se sepa en qué etapa estaba.
STAGE_HOOK = None
# Ruta de un punto de control en disco (lo fija el proceso de trabajo): se reescribe de forma
# síncrona en cada cambio de etapa para que el proceso padre conozca la etapa, el análisis técnico y
# el registro aunque el proceso muera sin poder enviar nada.
CHECKPOINT_PATH = None


class Fidelity(IntEnum):
    DIRECT = 0          # conversión directa, buena conservación
    TESSELLATED = 1     # triangulación/teselación con tolerancia
    APPROXIMATE = 2     # representación geométrica aproximada (p. ej. B-Rep facetado)
    LIMITED = 3         # conversión limitada con pérdida de información relevante
    UNSUPPORTED = 4

    @property
    def label(self) -> str:
        return tr(FIDELITY_LABELS[self])


FIDELITY_LABELS = {
    Fidelity.DIRECT: "Directa",
    Fidelity.TESSELLATED: "Teselación",
    Fidelity.APPROXIMATE: "Aproximada (facetada)",
    Fidelity.LIMITED: "Limitada (con pérdidas)",
    Fidelity.UNSUPPORTED: "No soportada",
}


class Status:
    SUCCESS = "exitoso"
    SUCCESS_WARNINGS = "exitoso_con_advertencias"
    FAILED = "fallido"
    CANCELLED = "cancelado"

    LABELS = {
        "exitoso": "Exitoso",
        "exitoso_con_advertencias": "Exitoso con advertencias",
        "fallido": "Fallido",
        "cancelado": "Cancelado",
    }


@dataclass
class ConversionReport:
    source: str
    source_format: str = ""
    target_format: str = ""
    outputs: list = field(default_factory=list)
    status: str = Status.FAILED
    fidelity: int = int(Fidelity.DIRECT)
    semantic: str = ""
    route: list = field(default_factory=list)
    log: list = field(default_factory=list)          # (timestamp, nivel, mensaje)
    warnings: list = field(default_factory=list)
    losses: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    stage: str = ""                                   # etapa actual / etapa del fallo
    stage_times: dict = field(default_factory=dict)   # duración de cada etapa (s)
    technical: dict = field(default_factory=dict)     # detalle técnico (malla, escritura, proceso…)
    traceback: str = ""                               # traza completa de la excepción
    diagnostic_log: str = ""                          # ruta del archivo de diagnóstico
    started: float = field(default_factory=time.time)
    finished: float = 0.0

    def set_stage(self, stage: str):
        now = time.time()
        if self.stage:
            self.stage_times[self.stage] = round(self.stage_times.get(self.stage, 0.0) + now - getattr(self, "_t", now), 2)
        self.stage = stage
        self._t = now
        if STAGE_HOOK is not None:
            try:
                STAGE_HOOK(stage)
            except Exception:
                pass
        if CHECKPOINT_PATH:
            self.checkpoint()
        # Solo para pruebas automáticas: simula un fallo nativo real (violación de acceso) en una etapa
        if os.environ.get("U3DC_TEST_CRASH_STAGE") == stage and os.environ.get("U3DC_TEST_CRASH_OK") == "1":
            import faulthandler
            faulthandler._sigsegv()          # escritura en dirección nula desde C: fallo nativo real

    def checkpoint(self):
        try:
            import json
            data = {"stage": self.stage, "source_format": self.source_format, "route": self.route,
                    "technical": self.technical, "log": self.log, "warnings": self.warnings, "losses": self.losses,
                    "stats": self.stats, "stage_times": self.stage_times}
            tmp = CHECKPOINT_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, default=str)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, CHECKPOINT_PATH)
        except Exception:
            pass

    def info(self, msg: str):
        self.log.append((time.time(), "info", msg))

    def warn(self, msg: str):
        if msg not in self.warnings:
            self.warnings.append(msg)
            self.log.append((time.time(), "warning", msg))

    def loss(self, msg: str):
        if msg not in self.losses:
            self.losses.append(msg)
            self.log.append((time.time(), "loss", msg))

    def error(self, msg: str):
        self.errors.append(msg)
        self.log.append((time.time(), "error", msg))

    def degrade(self, f: Fidelity):
        self.fidelity = max(int(self.fidelity), int(f))

    @property
    def fidelity_label(self) -> str:
        return Fidelity(self.fidelity).label

    @property
    def status_label(self) -> str:
        return tr(Status.LABELS.get(self.status, self.status))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ConversionReport":
        r = cls(source=d.get("source", ""))
        for k, v in d.items():
            if hasattr(r, k):
                setattr(r, k, v)
        return r

    def summary_text(self) -> str:
        """Resumen legible en el idioma activo (los datos se guardan en el idioma canónico)."""
        lines = [tr("Origen: {s}", s=self.source),
                 tr("Formato: {a} → {b}", a=self.source_format, b=self.target_format),
                 tr("Estado: {s}", s=self.status_label),
                 tr("Fidelidad geométrica: {f}", f=self.fidelity_label)]
        if self.semantic:
            lines.append(tr("Conservación semántica: {s}", s=tr(self.semantic)))
        if self.route:
            lines.append(tr("Ruta: {r}", r=" → ".join(tr_msg(s) for s in self.route)))
        for o in self.outputs:
            lines.append(tr("Salida: {o}", o=o))
        if self.stats:
            lines.append(tr("Estadísticas: {s}", s=", ".join(f"{k}={v}" for k, v in self.stats.items() if k != "traza")))
        if self.validation:
            lines.append(tr("Validación: {s}", s=", ".join(f"{k}={v}" for k, v in self.validation.items())))
        for w in self.warnings:
            lines.append(tr("ADVERTENCIA") + ": " + tr_msg(w))
        for l in self.losses:
            lines.append(tr("PÉRDIDA") + ": " + tr_msg(l))
        for e in self.errors:
            lines.append("ERROR: " + tr_msg(e))
        if self.errors and self.stage:
            lines.append(tr("Etapa del fallo: {s}", s=tr_msg(self.stage)))
        if self.diagnostic_log:
            lines.append(tr("Registro de diagnóstico: {p}", p=self.diagnostic_log))
        return "\n".join(lines)