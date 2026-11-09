"""Registro de diagnóstico local de cada conversión.

Cada conversión (correcta o no) deja un archivo de texto en
    %LOCALAPPDATA%\\NEXOVAX3DConverter\\logs\\AAAAMMDD-HHMMSS_<archivo>.log
con: rutas de entrada/salida, formato y tamaño, opciones, análisis de la malla, etapas y tiempos,
memoria máxima, resultado de transferencia/escritura, validación, excepción con traza completa y,
si el proceso de conversión terminó de forma anormal, su código de salida interpretado, su salida
estándar/errores y el volcado de faulthandler (pila de Python en el momento de un fallo nativo).
Todo es local: nada se envía fuera del equipo.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import time

from .. import APP_ID, APP_NAME, __version__

MAX_LOGS = 300

# Códigos NTSTATUS habituales cuando un proceso nativo termina de forma anormal en Windows
EXIT_CODES = {
    0xC0000005: "violación de acceso (fallo nativo en una biblioteca C/C++)",
    0xC00000FD: "desbordamiento de pila",
    0xC0000409: "terminación forzada por la biblioteca (fail-fast / abort)",
    0xC0000017: "memoria insuficiente (sin memoria virtual)",
    0xC000012D: "límite de memoria comprometida alcanzado",
    0xC0000374: "corrupción del montón (heap)",
    0xC000001D: "instrucción no válida",
    0xC0000094: "división entera por cero",
    0xC0000420: "aserción interna fallida",
    0x00000001: "error no controlado del intérprete",
    0x00000003: "terminación abrupta (abort / señal fatal, p. ej. fallo de segmentación)",
}


def log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_ID, "logs")
    os.makedirs(d, exist_ok=True)
    return d


def explain_exit_code(code) -> str:
    if code is None:
        return "sin código (proceso aún activo o desconocido)"
    u = code & 0xFFFFFFFF
    desc = EXIT_CODES.get(u)
    hexa = f"0x{u:08X}"
    if code == 0:
        return "0 (normal)"
    if desc:
        return f"{code} ({hexa}): {desc}"
    if code < 0:
        return f"{code}: terminado por señal/forzado"
    return f"{code} ({hexa})"


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def peak_memory_mb() -> float | None:
    """Memoria máxima (working set) del proceso actual, en MB."""
    try:
        c = _PMC()
        c.cb = ctypes.sizeof(_PMC)
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_ulong]
        if k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return round(c.PeakWorkingSetSize / 2 ** 20, 1)
    except Exception:
        pass
    return None


def _tail(path: str, max_chars: int = 20000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read()
        return data[-max_chars:]
    except OSError:
        return ""


def read_process_capture(staging: str | None) -> dict:
    """Lee la salida estándar/errores y el volcado de faulthandler capturados en el proceso de trabajo."""
    if not staging:
        return {}
    out = {}
    so = _tail(os.path.join(staging, "proceso_stdout_stderr.txt"))
    fh = _tail(os.path.join(staging, "proceso_faulthandler.txt"))
    if so.strip():
        # OCCT imprime estadísticas muy verbosas: se conserva lo relevante al final
        out["stdout_stderr"] = so
    if fh.strip():
        out["faulthandler"] = fh
    return out


def write_log(report, options=None, process: dict | None = None) -> str:
    """Escribe el archivo de diagnóstico y devuelve su ruta (también se guarda en report.diagnostic_log)."""
    try:
        d = log_dir()
        stem = os.path.splitext(os.path.basename(report.source or "conversion"))[0][:60]
        safe = "".join(ch if ch.isalnum() or ch in "-_ ()." else "_" for ch in stem) or "conversion"
        path = os.path.join(d, f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(report.started))}_{safe}.log")
        L = []
        w = L.append
        w(f"{APP_NAME} {__version__} — registro de diagnóstico")
        w(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report.started))} · "
          f"{platform.platform()} · Python {platform.python_version()}")
        w("")
        w("== Resultado")
        w(f"Estado: {report.status}")
        w(f"Etapa{' del fallo' if report.errors else ' final'}: {report.stage or '—'}")
        for e in report.errors:
            w(f"Error: {e}")
        w(f"Fidelidad: {report.fidelity_label} · Semántica: {report.semantic or '—'}")
        dur = (report.finished or time.time()) - report.started
        w(f"Duración total: {dur:.2f} s")
        w("")
        w("== Archivos")
        w(f"Entrada: {report.source}")
        try:
            w(f"Tamaño de entrada: {os.path.getsize(report.source):,} bytes")
        except OSError:
            w("Tamaño de entrada: (no accesible)")
        w(f"Formato: {report.source_format or '¿?'} → {report.target_format}")
        for o in report.outputs:
            try:
                w(f"Salida: {o} ({os.path.getsize(o):,} bytes)")
            except OSError:
                w(f"Salida: {o}")
        if options is not None:
            w(f"Carpeta de salida configurada: {getattr(options, 'output_dir', '') or '(la del archivo de origen)'}")
        w("")
        w("== Ruta de conversión")
        for s in report.route:
            w(f"  - {s}")
        w("")
        w("== Etapas y tiempos (s)")
        for k, v in report.stage_times.items():
            w(f"  {k}: {v}")
        for k in ("importacion_s", "exportacion_s", "validacion_s", "memoria_maxima_mb"):
            if k in report.stats:
                w(f"  {k}: {report.stats[k]}")
        w("")
        w("== Estadísticas")
        w(json.dumps({k: v for k, v in report.stats.items() if k != "traza"}, ensure_ascii=False, indent=1, default=str))
        if report.technical:
            w("")
            w("== Detalle técnico (malla, B-Rep, escritura)")
            w(json.dumps(report.technical, ensure_ascii=False, indent=1, default=str))
        if report.validation:
            w("")
            w("== Validación")
            w(json.dumps(report.validation, ensure_ascii=False, indent=1, default=str))
        if process:
            w("")
            w("== Proceso de conversión")
            for k in ("codigo_salida", "interpretacion", "duracion_s", "motivo"):
                if k in process:
                    w(f"{k}: {process[k]}")
            if process.get("faulthandler"):
                w("-- faulthandler (pila en el momento del fallo nativo):")
                w(process["faulthandler"])
            if process.get("stdout_stderr"):
                w("-- salida estándar / errores del proceso (final):")
                w(process["stdout_stderr"])
        if options is not None:
            w("")
            w("== Opciones")
            w(json.dumps(options.to_dict(), ensure_ascii=False, indent=1, default=str))
        if report.traceback:
            w("")
            w("== Traza completa de la excepción")
            w(report.traceback)
        w("")
        w("== Registro")
        for ts, level, msg in report.log:
            w(f"[{time.strftime('%H:%M:%S', time.localtime(ts))}] {level.upper():8} {msg}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
        report.diagnostic_log = path
        _rotate(d)
        return path
    except Exception:
        return ""


def _rotate(d: str) -> None:
    try:
        logs = sorted((os.path.join(d, n) for n in os.listdir(d) if n.endswith(".log")), key=os.path.getmtime)
        for p in logs[:-MAX_LOGS]:
            os.remove(p)
    except OSError:
        pass
