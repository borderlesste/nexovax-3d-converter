"""Diálogos: matriz de compatibilidad, informe de conversión y 'Acerca de'."""
from __future__ import annotations

from ..i18n import tr, tr_msg

import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QDialogButtonBox,
                               QPlainTextEdit, QPushButton, QHBoxLayout, QFileDialog, QHeaderView, QTextBrowser)

from .. import APP_NAME, __version__
from ..core.formats import FORMATS, FORMAT_ORDER
from ..core.report import Fidelity
from ..core.router import compatibility_matrix

FIDELITY_COLORS = {
    Fidelity.DIRECT: "#d7f0dc",
    Fidelity.TESSELLATED: "#dbe9fb",
    Fidelity.APPROXIMATE: "#fdf0cf",
    Fidelity.LIMITED: "#fbe0cc",
    Fidelity.UNSUPPORTED: "#f6d3d3",
}


class MatrixDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Matriz de compatibilidad de formatos"))
        self.resize(1080, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Filas: formato de origen · Columnas: formato de destino. "
                             "Pase el ratón sobre una celda para ver la ruta de conversión y las pérdidas.")))
        cells = compatibility_matrix()
        t = QTableWidget(len(FORMAT_ORDER), len(FORMAT_ORDER))
        t.setHorizontalHeaderLabels([FORMATS[f].name for f in FORMAT_ORDER])
        t.setVerticalHeaderLabels([FORMATS[f].name for f in FORMAT_ORDER])
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for c in cells:
            i, j = FORMAT_ORDER.index(c.source), FORMAT_ORDER.index(c.target)
            it = QTableWidgetItem(c.fidelity.label + "\n" + tr("Semántica: {s}", s=tr(c.semantic)))
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(QColor(FIDELITY_COLORS[c.fidelity]))
            tip = tr("Ruta:\n  ") + "\n  ".join(tr_msg(s) for s in c.route)
            if c.losses:
                tip += tr("\n\nPérdidas posibles:\n  • ") + "\n  • ".join(tr_msg(l) for l in c.losses)
            if c.note:
                tip += tr("\n\nNota: ") + tr_msg(c.note)
            it.setToolTip(tip)
            t.setItem(i, j, it)
        lay.addWidget(t)
        legend = QLabel(tr("Directa: buena conservación · Teselación: B-Rep/IFC → triángulos con tolerancia · "
                        "Aproximada: B-Rep facetado desde malla · Limitada: pérdida de información relevante"))
        legend.setWordWrap(True)
        lay.addWidget(legend)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class ReportDialog(QDialog):
    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.report = report
        self.setWindowTitle(tr("Informe de conversión — {f}", f=os.path.basename(report.source)))
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        lines = [report.summary_text(), "", tr("Registro:")]
        import time
        for ts, level, msg in report.log:
            lines.append(f"[{time.strftime('%H:%M:%S', time.localtime(ts))}] {level.upper():8} {tr_msg(msg)}")
        if report.stats.get("traza"):
            lines += ["", tr("Detalle técnico:"), report.stats["traza"]]
        txt.setPlainText("\n".join(lines))
        lay.addWidget(txt)
        row = QHBoxLayout()
        save = QPushButton(tr("Guardar informe…"))
        save.clicked.connect(self._save)
        row.addWidget(save)
        row.addStretch(1)
        close = QPushButton(tr("Cerrar"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _save(self):
        base = os.path.splitext(os.path.basename(self.report.source))[0] + "_informe"
        path, flt = QFileDialog.getSaveFileName(self, tr("Guardar informe"), base + ".txt",
                                                "Texto (*.txt);;JSON (*.json)")
        if not path:
            return
        if path.lower().endswith(".json"):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.report.to_dict(), fh, ensure_ascii=False, indent=1, default=str)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.report.summary_text())


class TextDialog(QDialog):
    def __init__(self, title: str, html: str, parent=None, size=(760, 560)):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(*size)
        lay = QVBoxLayout(self)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(False)
        tb.setHtml(html)
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


def about_html() -> str:
    import platform
    vers = {}
    for mod, name in ((tr("OCP"), tr("Open CASCADE (OCP)")), ("ifcopenshell", tr("IfcOpenShell")), (tr("PySide6"), tr("Qt / PySide6")),
                      ("numpy", tr("NumPy")), ("trimesh", "trimesh"), ("ufbx", "ufbx"), ("vtkmodules", tr("VTK"))):
        try:
            m = __import__(mod)
            v = getattr(m, "__version__", None) or getattr(m, "version", None) or "incluido"
            vers[name] = v
        except Exception:
            vers[name] = tr("no disponible")
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in vers.items())
    return (f"<h2>{APP_NAME} {__version__}</h2>"
            "<p>Conversión profesional de formatos 3D (glTF/GLB, OBJ, FBX, STL, IFC, STEP, IGES) "
            "completamente <b>offline</b>. No envía datos a ningún servidor.</p>"
            f"<p>Python {platform.python_version()} · {platform.platform()}</p>"
            f"<table cellpadding='4'>{rows}</table>"
            "<p>Consulte <i>Ayuda → Licencias de terceros</i> para los términos de cada componente.</p>")
