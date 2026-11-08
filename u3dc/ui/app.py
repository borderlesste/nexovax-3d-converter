"""Arranque de la aplicación gráfica."""
from __future__ import annotations

import os
import sys


def resource_dir() -> str:
    """Carpeta base de recursos (instalación congelada o árbol de fuentes)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(argv: list[str] | None = None) -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from .. import APP_NAME, APP_ID
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setStyle("Fusion")
    from .style import QSS
    app.setStyleSheet(QSS)
    # idioma: preferencia guardada > variable U3DC_LANG > idioma de Windows (antes de crear la ventana)
    from PySide6.QtCore import QSettings, QTranslator, QLibraryInfo
    from ..i18n import set_language, get_language
    saved = QSettings(APP_ID, APP_ID).value("language")
    set_language(saved or get_language())
    qt_tr = QTranslator(app)                 # diálogos estándar de Qt (Sí/No, Abrir…) en el idioma activo
    qt_lang = {"es": "es", "fr": "fr", "ht": "fr"}[get_language()]   # Qt no tiene criollo: francés
    if qt_tr.load(f"qtbase_{qt_lang}",
                                                    QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(qt_tr)
    try:   # identificador propio en la barra de tareas de Windows
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    from .main_window import MainWindow
    from .icons import app_icon
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.show()
    files = [a for a in (argv or []) if os.path.exists(a)]
    if files:
        w.add_paths(files)
    shot_dir = os.environ.get("U3DC_SELFTEST")
    if shot_dir:
        _selftest(app, w, shot_dir)
    return app.exec()


def _selftest(app, w, out_dir: str):
    """Autoprueba de la interfaz: vista previa, conversión por lotes y capturas de pantalla reales."""
    from PySide6.QtCore import QTimer
    os.makedirs(out_dir, exist_ok=True)
    w.showMaximized()
    w.raise_()
    w.activateWindow()
    state = {"t": 0, "phase": "preview"}
    log = open(os.path.join(out_dir, "selftest.log"), "w", encoding="utf-8")

    def shot(name):
        from PIL import ImageGrab
        app.processEvents()
        g = w.frameGeometry()
        ratio = w.devicePixelRatioF()
        bbox = (int(g.x() * ratio), int(g.y() * ratio), int((g.x() + g.width()) * ratio), int((g.y() + g.height()) * ratio))
        ImageGrab.grab(bbox=bbox, all_screens=True).save(os.path.join(out_dir, name))
        log.write(f"captura {name}\n")
        log.flush()

    def step():
        state["t"] += 1
        if state["phase"] == "preview":
            if state["t"] == 1:
                for r in range(w.table.rowCount()):
                    if w.table.item(r, 0).text().endswith(".ifc"):
                        w.table.selectRow(r)
                        break
            if w.preview_cache or state["t"] > 120:
                state["phase"] = "convert"
                QTimer.singleShot(1500, lambda: (shot("gui_vista_previa.png"), w.start_conversion(),
                                                 QTimer.singleShot(1000, step)))
                return
        elif state["phase"] == "convert":
            if w.conv_thread is not None and not w.conv_thread.isRunning() and w.batch_done == w.batch_total:
                state["phase"] = "done"
                for r in range(w.queue.rowCount()):
                    log.write(" | ".join(w.queue.item(r, c).text() for c in range(4)) + "\n")
                for i in range(w.log.count()):
                    log.write(w.log.item(i).text() + "\n")
                log.flush()
                QTimer.singleShot(1000, lambda: (shot("gui_conversion.png"), log.close(), app.quit()))
                return
            if state["t"] > 1200:
                log.write("tiempo agotado\n")
                log.close()
                app.quit()
                return
        QTimer.singleShot(500, step)

    QTimer.singleShot(2500, step)
