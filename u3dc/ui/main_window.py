"""Ventana principal de NEXOVAX 3D Converter."""
from __future__ import annotations

from ..i18n import tr, tr_msg

import json
import os
import time

from PySide6.QtCore import Qt, QSettings, QTimer, QSize, QUrl
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QToolButton, QLineEdit,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox, QDoubleSpinBox,
    QSpinBox, QCheckBox, QSlider, QFormLayout, QScrollArea, QProgressBar, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QMenu, QGridLayout, QSizePolicy, QInputDialog)

from .. import APP_NAME, APP_ID, __version__
from ..core.formats import FORMATS, FORMAT_ORDER, ALL_EXTENSIONS, detect, DetectionError
from ..core.options import ConversionOptions, UNIT_LABELS
from ..core.report import Fidelity, Status
from ..core.router import find_route, runtime_losses, semantic_level, NOTES
from .dialogs import MatrixDialog, ReportDialog, TextDialog, about_html, FIDELITY_COLORS
from .icons import icon, FORMAT_ICON, app_icon
from .style import PRIMARY, OK, WARN, ERR, MUTED
from .viewer import Viewer3D
from .workers import ConversionThread, PreviewThread

QUALITIES = [("baja", tr("Baja")), ("media", tr("Media")), ("alta", tr("Alta")), ("muy_alta", tr("Muy alta"))]
STATUS_VIEW = {
    "pendiente": (tr("Pendiente"), "clock", MUTED),
    "en_cola": (tr("En cola"), "hourglass", MUTED),
    "en_conversion": (tr("En conversión"), "sync", PRIMARY),
    Status.SUCCESS: (tr("Convertido"), "check", OK),
    Status.SUCCESS_WARNINGS: (tr("Con advertencias"), "warning", WARN),
    Status.FAILED: (tr("Fallido"), "error", ERR),
    Status.CANCELLED: (tr("Cancelado"), "cancel", MUTED),
    "no_valido": (tr("No reconocido"), "error", ERR),
}


def human_size(n: int) -> str:
    for unit in (tr("B"), tr("KB"), tr("MB"), tr("GB")):
        if n < 1024 or unit == tr("GB"):
            s = f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
            return s.replace(".", ",")
        n /= 1024
    return str(n)


def panel(title: str, icon_name: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    fr = QFrame()
    fr.setObjectName("panel")
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(8)
    head = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(icon(icon_name, PRIMARY, 22).pixmap(22, 22))
    head.addWidget(ic)
    t = QLabel(title)
    t.setObjectName("panelTitle")
    head.addWidget(t)
    head.addStretch(1)
    lay.addLayout(head)
    return fr, lay, head


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else None
        if avail is not None:
            self.resize(min(1600, int(avail.width() * 0.95)), min(960, int(avail.height() * 0.92)))
        else:
            self.resize(1400, 860)
        self.setAcceptDrops(True)
        self.settings = QSettings(APP_ID, APP_ID)
        self.files: dict[int, dict] = {}
        self._next_id = 1
        self.conv_thread: ConversionThread | None = None
        self.preview_thread: PreviewThread | None = None
        self.preview_pending: str | None = None
        self.preview_cache: dict[str, tuple[str, dict]] = {}
        self.current_preview_path: str | None = None
        self.batch_started = 0.0
        self.batch_total = 0
        self.batch_done = 0
        self.job_progress: dict[int, float] = {}
        self.current_job: int | None = None
        self.last_output_dir: str | None = None
        self._build()
        self._load_settings()
        self._update_applicability()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)
        from ..core.safety import cleanup_stale_temp
        cleanup_stale_temp()

    # ===================================================================== construcción
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(10, 10, 10, 10)
        vsplit = QSplitter(Qt.Vertical)
        hsplit = QSplitter(Qt.Horizontal)
        hsplit.addWidget(self._build_files_panel())
        hsplit.addWidget(self._build_preview_panel())
        hsplit.addWidget(self._build_config_panel())
        hsplit.setSizes([470, 640, 450])
        hsplit.setStretchFactor(0, 4)
        hsplit.setStretchFactor(1, 5)
        hsplit.setStretchFactor(2, 3)
        hsplit.setChildrenCollapsible(False)
        vsplit.addWidget(hsplit)
        vsplit.addWidget(self._build_processing_panel())
        vsplit.setSizes([640, 290])
        vsplit.setStretchFactor(0, 2)
        vsplit.setStretchFactor(1, 1)
        vsplit.setChildrenCollapsible(False)
        self.hsplit, self.vsplit = hsplit, vsplit
        bl.addWidget(vsplit)
        root.addWidget(body, 1)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search.setFocus())
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.add_files)
        QShortcut(QKeySequence("Delete"), self.table, activated=self.remove_selected)
        QShortcut(QKeySequence("F5"), self, activated=self.start_conversion)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_preview_fullscreen)

    def _build_header(self) -> QWidget:
        hdr = QFrame()
        hdr.setObjectName("header")
        lay = QVBoxLayout(hdr)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)
        row1 = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(36, 36))
        row1.addWidget(logo)
        t = QLabel(APP_NAME)
        t.setObjectName("appTitle")
        row1.addWidget(t)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#d9e0ea;")
        row1.addSpacing(8)
        row1.addWidget(sep)
        row1.addSpacing(8)
        sub = QLabel(tr("Conversión profesional de formatos 3D · Offline · Windows"))
        sub.setObjectName("appSubtitle")
        row1.addWidget(sub)
        row1.addStretch(1)
        lay.addLayout(row1)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        b_add = QPushButton(icon("add_file", PRIMARY), tr("  Añadir archivos"))
        b_add.clicked.connect(self.add_files)
        b_dir = QPushButton(icon("add_folder", PRIMARY), tr("  Añadir carpeta"))
        b_dir.clicked.connect(self.add_folder)
        b_del = QPushButton(icon("trash", "#3d4b5c"), tr("  Eliminar"))
        b_del.clicked.connect(self.remove_selected)
        for b in (b_add, b_dir, b_del):
            b.setIconSize(QSize(18, 18))
            row2.addWidget(b)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#d9e0ea;")
        row2.addWidget(sep2)
        self.btn_convert_top = QPushButton(icon("play", "white"), tr("  Convertir"))
        self.btn_convert_top.setObjectName("primary")
        self.btn_convert_top.setIconSize(QSize(16, 16))
        self.btn_convert_top.clicked.connect(self.start_conversion)
        row2.addWidget(self.btn_convert_top)
        row2.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Filtrar archivos…  (Ctrl + F)"))
        self.search.addAction(icon("search", MUTED), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(300)
        self.search.textChanged.connect(self._apply_filter)
        row2.addWidget(self.search)
        from ..i18n import LANGUAGES, get_language
        self.cmb_lang = QComboBox()
        self.cmb_lang.setToolTip("Idioma · Langue · Lang")
        for code, name in LANGUAGES.items():
            self.cmb_lang.addItem(icon("globe", PRIMARY), name, code)
        self.cmb_lang.setCurrentIndex(self.cmb_lang.findData(get_language()))
        self.cmb_lang.currentIndexChanged.connect(self._change_language)
        row2.addWidget(self.cmb_lang)
        help_btn = QPushButton(icon("help", "#3d4b5c"), tr("  Ayuda"))
        menu = QMenu(help_btn)
        menu.addAction(icon("report"), tr("Manual de usuario"), self.open_manual)
        menu.addAction(icon("matrix"), tr("Matriz de compatibilidad"), lambda: MatrixDialog(self).exec())
        menu.addAction(icon("log"), tr("Licencias de terceros"), self.open_licenses)
        menu.addSeparator()
        menu.addAction(icon("info"), tr("Acerca de {app}", app=APP_NAME),
                       lambda: TextDialog(tr("Acerca de {app}", app=APP_NAME), about_html(), self, (620, 480)).exec())
        help_btn.setMenu(menu)
        row2.addWidget(help_btn)
        lay.addLayout(row2)
        return hdr

    # ------------------------------------------------------------------ archivos
    def _build_files_panel(self) -> QWidget:
        fr, lay, head = panel(tr("Archivos"), "folder")
        self.lbl_count = QLabel(tr("0 archivos"))
        self.lbl_count.setObjectName("muted")
        head.addWidget(self.lbl_count)
        # Columnas: Nombre (con casilla e icono) · Extensión · Tamaño · Estado
        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(["Nombre", tr("Ext."), tr("Tamaño"), tr("Estado")])
        t.verticalHeader().hide()
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setShowGrid(False)
        t.setAlternatingRowColors(False)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        t.setColumnWidth(3, 132)
        hh.setMinimumSectionSize(30)
        t.setTextElideMode(Qt.ElideRight)
        t.verticalHeader().setDefaultSectionSize(36)
        t.setIconSize(QSize(20, 20))
        t.itemSelectionChanged.connect(self._on_file_selected)
        t.itemChanged.connect(lambda *_: self._update_applicability())
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(self._files_menu)
        t.cellDoubleClicked.connect(self._file_double_clicked)
        self.table = t
        lay.addWidget(t)
        self.drop_hint = QLabel(tr("Arrastre aquí archivos o carpetas\n(.gltf .glb .obj .fbx .stl .ifc .step .stp .igs .iges)"))
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setObjectName("muted")
        lay.addWidget(self.drop_hint)
        return fr

    # ------------------------------------------------------------------ vista previa
    def _build_preview_panel(self) -> QWidget:
        fr, lay, head = panel(tr("Vista previa 3D"), "cube")
        self.lbl_preview_name = QLabel("")
        self.lbl_preview_name.setObjectName("muted")
        head.addWidget(self.lbl_preview_name)
        tb = QHBoxLayout()
        tb.setSpacing(4)

        def tbtn(name, tip, slot, checkable=False, checked=False):
            b = QToolButton()
            b.setIcon(icon(name, "#2b3a4a", 20))
            b.setIconSize(QSize(20, 20))
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setChecked(checked)
            if checkable:
                b.toggled.connect(slot)
            else:
                b.clicked.connect(slot)
            tb.addWidget(b)
            return b

        tbtn("rotate", tr("Restablecer vista isométrica"), lambda: self.viewer.reset_view())
        tbtn("fit", tr("Centrar el modelo"), lambda: self.viewer.reset_view())
        tbtn("zoom_in", tr("Acercar"), lambda: self.viewer.zoom(1.25))
        tbtn("zoom_out", tr("Alejar"), lambda: self.viewer.zoom(0.8))
        tb.addSpacing(8)
        self.cmb_view = QComboBox()
        self.cmb_view.addItem(icon("cube"), tr("Sombreado"), "shaded")
        self.cmb_view.addItem(icon("wire"), tr("Alambre"), "wire")
        self.cmb_view.addItem(icon("layers"), tr("Sombreado + aristas"), "edges")
        self.cmb_view.currentIndexChanged.connect(lambda: self.viewer.set_mode(self.cmb_view.currentData()))
        tb.addWidget(self.cmb_view)
        tb.addSpacing(8)
        tbtn("grid", tr("Mostrar rejilla"), lambda on: self.viewer.set_grid(on), True, True)
        tbtn("axes", tr("Mostrar ejes XYZ"), lambda on: self.viewer.set_axes(on), True, True)
        tb.addStretch(1)
        tbtn("fullscreen", tr("Vista previa a pantalla completa (F11)"), self.toggle_preview_fullscreen)
        lay.addLayout(tb)
        self.viewer = Viewer3D()
        self.viewer.setMinimumHeight(260)
        lay.addWidget(self.viewer, 1)
        self.lbl_preview_info = QLabel("")
        self.lbl_preview_info.setObjectName("muted")
        lay.addWidget(self.lbl_preview_info)
        return fr

    # ------------------------------------------------------------------ configuración
    def _build_config_panel(self) -> QWidget:
        fr, lay, head = panel(tr("Configuración"), "settings")
        prof = QPushButton(icon("layers"), tr(" Perfiles"))
        self.profile_menu = QMenu(prof)
        self.profile_menu.aboutToShow.connect(self._fill_profiles_menu)
        prof.setMenu(self.profile_menu)
        head.addWidget(prof)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setContentsMargins(2, 2, 6, 2)
        form.setVerticalSpacing(8)

        self.txt_source = QLineEdit()
        self.txt_source.setReadOnly(True)
        self.txt_source.setPlaceholderText("—")
        form.addRow(tr("Formato de origen detectado:"), self.txt_source)
        self.cmb_target = QComboBox()
        for f in FORMAT_ORDER:
            self.cmb_target.addItem(icon(FORMAT_ICON[f]), tr(FORMATS[f].long_name), f)
        self.cmb_target.setCurrentIndex(FORMAT_ORDER.index("glb"))
        self.cmb_target.currentIndexChanged.connect(self._update_applicability)
        form.addRow(tr("Formato de destino:"), self.cmb_target)
        out_row = QHBoxLayout()
        self.txt_out = QLineEdit()
        self.txt_out.setPlaceholderText(tr("Misma carpeta que cada archivo de origen"))
        b_out = QToolButton()
        b_out.setIcon(icon("folder"))
        b_out.setToolTip(tr("Elegir carpeta de salida"))
        b_out.clicked.connect(self._choose_output)
        out_row.addWidget(self.txt_out)
        out_row.addWidget(b_out)
        form.addRow(tr("Carpeta de salida:"), out_row)

        self.route_box = QFrame()
        self.route_box.setObjectName("routeBox")
        rb = QVBoxLayout(self.route_box)
        rb.setContentsMargins(10, 8, 10, 8)
        self.lbl_route_fid = QLabel("")
        self.lbl_route_fid.setStyleSheet("font-weight:600;")
        self.lbl_route = QLabel("")
        self.lbl_route.setWordWrap(True)
        self.lbl_route.setObjectName("muted")
        rb.addWidget(self.lbl_route_fid)
        rb.addWidget(self.lbl_route)
        form.addRow(self.route_box)

        qrow = QHBoxLayout()
        self.sld_quality = QSlider(Qt.Horizontal)
        self.sld_quality.setRange(0, 3)
        self.sld_quality.setValue(2)
        self.sld_quality.setPageStep(1)
        self.cmb_quality = QComboBox()
        for k, v in QUALITIES:
            self.cmb_quality.addItem(v, k)
        self.cmb_quality.setCurrentIndex(2)
        self.sld_quality.valueChanged.connect(self.cmb_quality.setCurrentIndex)
        self.cmb_quality.currentIndexChanged.connect(self.sld_quality.setValue)
        qrow.addWidget(self.sld_quality, 1)
        qrow.addWidget(self.cmb_quality)
        self.lbl_quality = QLabel(tr("Calidad de malla:"))
        form.addRow(self.lbl_quality, qrow)
        self.spn_tol = QDoubleSpinBox()
        self.spn_tol.setRange(0.0, 1000.0)
        self.spn_tol.setDecimals(3)
        self.spn_tol.setSingleStep(0.05)
        self.spn_tol.setSuffix(tr(" mm"))
        self.spn_tol.setSpecialValueText(tr("Automática (según calidad)"))
        self.spn_tol.setToolTip(tr("Desviación máxima entre la superficie exacta y los triángulos (cordal).\n"
                                "0 = automática en función de la calidad y del tamaño del modelo."))
        self.lbl_tol = QLabel(tr("Tolerancia de teselación:"))
        form.addRow(self.lbl_tol, self.spn_tol)
        self.spn_scale = QDoubleSpinBox()
        self.spn_scale.setRange(1e-6, 1e6)
        self.spn_scale.setDecimals(6)
        self.spn_scale.setValue(1.0)
        self.spn_scale.setToolTip(tr("Factor de escala adicional aplicado a la geometría (1 = sin cambios)."))
        form.addRow(tr("Escala:"), self.spn_scale)

        def units_combo():
            c = QComboBox()
            c.addItem(tr("Automáticas (convención del formato)"), "auto")
            for k, v in UNIT_LABELS.items():
                c.addItem(tr(v), k)
            return c

        self.cmb_in_units = units_combo()
        self.cmb_in_units.setToolTip(tr("OBJ y STL no declaran unidades. Automático: STL en mm, OBJ en m."))
        self.lbl_in_units = QLabel(tr("Unidades de origen (OBJ/STL):"))
        form.addRow(self.lbl_in_units, self.cmb_in_units)
        self.cmb_out_units = units_combo()
        self.cmb_out_units.setToolTip(tr("Unidad numérica para OBJ/STL de salida. Automático: la del archivo de origen."))
        self.lbl_out_units = QLabel(tr("Unidades de salida (OBJ/STL):"))
        form.addRow(self.lbl_out_units, self.cmb_out_units)

        def axis_combo(auto_txt):
            c = QComboBox()
            c.addItem(auto_txt, "auto")
            c.addItem(tr("Z arriba (X derecha, Y adelante)"), tr("Z"))
            c.addItem(tr("Y arriba (X derecha, Z hacia el observador)"), tr("Y"))
            return c

        self.cmb_in_axis = axis_combo(tr("Automática (OBJ: Y arriba · STL: Z arriba)"))
        self.lbl_in_axis = QLabel(tr("Orientación de ejes de origen:"))
        form.addRow(self.lbl_in_axis, self.cmb_in_axis)
        self.cmb_out_axis = axis_combo(tr("Automática (OBJ: Y arriba · STL: Z arriba)"))
        self.lbl_out_axis = QLabel(tr("Orientación de ejes de salida:"))
        form.addRow(self.lbl_out_axis, self.cmb_out_axis)
        self.chk_materials = QCheckBox(tr("Conservar materiales (colores, texturas)"))
        self.chk_materials.setChecked(True)
        form.addRow(self.chk_materials)
        self.chk_structure = QCheckBox(tr("Conservar estructura (jerarquía de objetos/capas)"))
        self.chk_structure.setChecked(True)
        form.addRow(self.chk_structure)

        spec = QLabel(tr("Opciones específicas"))
        spec.setObjectName("sectionTitle")
        form.addRow(spec)
        self.chk_props = QCheckBox(tr("Incluir propiedades / metadatos (psets IFC, extras glTF)"))
        self.chk_props.setChecked(True)
        form.addRow(self.chk_props)
        self.chk_merge = QCheckBox(tr("Fusionar geometría por material"))
        form.addRow(self.chk_merge)
        self.chk_stl_ascii = QCheckBox(tr("STL en formato ASCII (por defecto binario)"))
        form.addRow(self.chk_stl_ascii)
        self.chk_embed = QCheckBox(tr("glTF con recursos embebidos (un solo archivo .gltf)"))
        form.addRow(self.chk_embed)
        self.cmb_ifc = QComboBox()
        self.cmb_ifc.addItem(tr("IFC4"), tr("IFC4"))
        self.cmb_ifc.addItem(tr("IFC2X3"), tr("IFC2X3"))
        self.lbl_ifc = QLabel(tr("Esquema IFC de salida:"))
        form.addRow(self.lbl_ifc, self.cmb_ifc)
        self.cmb_step = QComboBox()
        for k, v in ((tr("AP214"), tr("AP214 (automoción, colores)")), (tr("AP242"), tr("AP242 (moderno)")), (tr("AP203"), tr("AP203 (básico)"))):
            self.cmb_step.addItem(v, k)
        self.lbl_step = QLabel(tr("Esquema STEP:"))
        form.addRow(self.lbl_step, self.cmb_step)
        self.chk_solid = QCheckBox(tr("Malla → CAD: crear sólidos cerrados cuando sea posible"))
        self.chk_solid.setChecked(True)
        form.addRow(self.chk_solid)
        self.chk_repair = QCheckBox(tr("Malla → CAD: reparar malla (soldar, degenerados, duplicados, normales)"))
        self.chk_repair.setChecked(True)
        form.addRow(self.chk_repair)
        self.chk_unify = QCheckBox(tr("Malla → CAD: unir triángulos coplanares en caras"))
        self.chk_unify.setChecked(True)
        form.addRow(self.chk_unify)
        self.chk_simplify = QCheckBox(tr("Malla → CAD: simplificar mallas densas automáticamente"))
        self.chk_simplify.setChecked(True)
        self.chk_simplify.setToolTip(tr("Un STEP facetado ocupa ≈2,5 KB y ≈13 KB de memoria por triángulo. Por encima del "
                                        "objetivo, la malla se reduce conservando la forma; la desviación se informa."))
        form.addRow(self.chk_simplify)
        self.spn_target = QSpinBox()
        self.spn_target.setRange(1000, 2_000_000)
        self.spn_target.setSingleStep(10_000)
        self.spn_target.setValue(100_000)
        self.spn_target.setGroupSeparatorShown(True)
        self.lbl_target = QLabel(tr("Objetivo de simplificación (triángulos):"))
        form.addRow(self.lbl_target, self.spn_target)
        self.spn_maxtri = QSpinBox()
        self.spn_maxtri.setRange(1000, 5_000_000)
        self.spn_maxtri.setSingleStep(50_000)
        self.spn_maxtri.setValue(1_000_000)
        self.spn_maxtri.setGroupSeparatorShown(True)
        self.spn_maxtri.setToolTip(tr("Límite absoluto. Además se aplica un límite automático según la memoria libre "
                                      "y el tiempo máximo por archivo."))
        self.lbl_maxtri = QLabel(tr("Límite de triángulos → CAD:"))
        form.addRow(self.lbl_maxtri, self.spn_maxtri)
        self.chk_validate = QCheckBox(tr("Validar el resultado (relectura y comparación)"))
        self.chk_validate.setChecked(True)
        form.addRow(self.chk_validate)
        self.chk_overwrite = QCheckBox(tr("Sobrescribir archivos existentes"))
        self.chk_overwrite.setToolTip(tr("Desactivado: se añade un sufijo (1), (2)… para no sobrescribir."))
        form.addRow(self.chk_overwrite)
        self.spn_parallel = QSpinBox()
        self.spn_parallel.setRange(1, 4)
        self.spn_parallel.setValue(1)
        self.spn_parallel.setToolTip(tr("Número de conversiones simultáneas (cada una en un proceso aislado)."))
        form.addRow(tr("Conversiones simultáneas:"), self.spn_parallel)
        self.spn_timeout = QSpinBox()
        self.spn_timeout.setRange(30, 86400)
        self.spn_timeout.setValue(1800)
        self.spn_timeout.setSuffix(tr(" s"))
        form.addRow(tr("Tiempo máximo por archivo:"), self.spn_timeout)
        for w in (self.cmb_in_units, self.cmb_in_axis):
            w.currentIndexChanged.connect(self._invalidate_previews)
        for c in inner.findChildren(QComboBox):   # que los textos largos no ensanchen el panel
            c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(8)
        scroll.setWidget(inner)
        lay.addWidget(scroll)
        fr.setMinimumWidth(330)
        return fr

    # ------------------------------------------------------------------ procesamiento
    def _build_processing_panel(self) -> QWidget:
        fr, lay, head = panel(tr("Procesamiento"), "layers")
        top = QHBoxLayout()
        self.btn_convert = QPushButton(icon("play", "white", 18), tr("  CONVERTIR"))
        self.btn_convert.setObjectName("bigPrimary")
        self.btn_convert.setIconSize(QSize(18, 18))
        self.btn_convert.clicked.connect(self.start_conversion)
        top.addWidget(self.btn_convert)
        self.btn_cancel = QPushButton(icon("stop", ERR, 16), tr("  Cancelar"))
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_conversion)
        top.addWidget(self.btn_cancel)
        top.addSpacing(14)
        mid = QVBoxLayout()
        self.lbl_current = QLabel(tr("Listo."))
        mid.addWidget(self.lbl_current)
        prow = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        prow.addWidget(self.progress, 1)
        self.lbl_pct = QLabel("0 %")
        self.lbl_pct.setStyleSheet("font-weight:700;")
        self.lbl_pct.setMinimumWidth(48)
        prow.addWidget(self.lbl_pct)
        mid.addLayout(prow)
        self.lbl_counts = QLabel("")
        self.lbl_counts.setObjectName("muted")
        mid.addWidget(self.lbl_counts)
        top.addLayout(mid, 1)
        times = QVBoxLayout()
        self.lbl_elapsed = QLabel(tr("Tiempo transcurrido: 00:00:00"))
        self.lbl_eta = QLabel(tr("Tiempo restante estimado: —"))
        for w in (self.lbl_elapsed, self.lbl_eta):
            w.setObjectName("muted")
            times.addWidget(w)
        top.addLayout(times)
        self.btn_open_out = QPushButton(icon("folder", PRIMARY), tr("  Abrir carpeta de destino"))
        self.btn_open_out.clicked.connect(self.open_output_folder)
        top.addWidget(self.btn_open_out)
        lay.addLayout(top)

        bottom = QHBoxLayout()
        # cola
        qf = QVBoxLayout()
        qh = QHBoxLayout()
        qi = QLabel()
        qi.setPixmap(icon("list", PRIMARY, 18).pixmap(18, 18))
        qh.addWidget(qi)
        self.lbl_queue = QLabel(tr("Cola de conversión (0)"))
        self.lbl_queue.setObjectName("sectionTitle")
        qh.addWidget(self.lbl_queue)
        qh.addStretch(1)
        qf.addLayout(qh)
        self.queue = QTableWidget(0, 4)
        self.queue.setHorizontalHeaderLabels(["#", tr("Archivo"), tr("Conversión"), tr("Estado")])
        self.queue.verticalHeader().hide()
        self.queue.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue.setShowGrid(False)
        qhh = self.queue.horizontalHeader()
        qhh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        qhh.setSectionResizeMode(1, QHeaderView.Stretch)
        qhh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        qhh.setSectionResizeMode(3, QHeaderView.Interactive)
        self.queue.setColumnWidth(3, 170)
        self.queue.verticalHeader().setDefaultSectionSize(28)
        self.queue.cellDoubleClicked.connect(self._queue_double_clicked)
        self.queue.itemSelectionChanged.connect(self._queue_selected)
        self.queue.setToolTip(tr("Doble clic: ver el informe completo de la conversión"))
        qf.addWidget(self.queue)
        bottom.addLayout(qf, 5)
        # registro
        lf = QVBoxLayout()
        lh = QHBoxLayout()
        li = QLabel()
        li.setPixmap(icon("log", PRIMARY, 18).pixmap(18, 18))
        lh.addWidget(li)
        t = QLabel(tr("Registro (log)"))
        t.setObjectName("sectionTitle")
        lh.addWidget(t)
        lh.addStretch(1)
        b_save_log = QToolButton()
        b_save_log.setIcon(icon("save"))
        b_save_log.setToolTip(tr("Guardar registro"))
        b_save_log.clicked.connect(self.save_log)
        lh.addWidget(b_save_log)
        lf.addLayout(lh)
        self.log = QListWidget()
        self.log.setWordWrap(True)
        lf.addWidget(self.log)
        bottom.addLayout(lf, 6)
        # advertencias
        self.warn_box = QFrame()
        self.warn_box.setObjectName("warnBox")
        wl = QVBoxLayout(self.warn_box)
        wl.setContentsMargins(12, 10, 12, 10)
        wh = QHBoxLayout()
        wi = QLabel()
        wi.setPixmap(icon("warning", WARN, 20).pixmap(20, 20))
        wh.addWidget(wi)
        self.lbl_warn_title = QLabel(tr("Posible pérdida de información"))
        self.lbl_warn_title.setStyleSheet(f"font-weight:700; color:{WARN};")
        wh.addWidget(self.lbl_warn_title)
        wh.addStretch(1)
        wl.addLayout(wh)
        self.lbl_warn = QLabel(tr("Seleccione archivos y un formato de destino para ver las posibles pérdidas."))
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_warn.setTextFormat(Qt.RichText)
        ws = QScrollArea()
        ws.setWidgetResizable(True)
        ws.setWidget(self.lbl_warn)
        wl.addWidget(ws, 1)
        self.warn_box.setMinimumWidth(360)
        bottom.addWidget(self.warn_box, 4)
        lay.addLayout(bottom, 1)
        return fr

    # ===================================================================== archivos
    def add_files(self):
        start = self.settings.value("last_input_dir", os.path.expanduser("~"))
        flt = tr("Modelos 3D (") + " ".join("*" + e for e in ALL_EXTENSIONS) + ");;Todos los archivos (*.*)"
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Añadir archivos"), start, flt)
        if paths:
            self.settings.setValue("last_input_dir", os.path.dirname(paths[0]))
            self.add_paths(paths)

    def add_folder(self):
        start = self.settings.value("last_input_dir", os.path.expanduser("~"))
        d = QFileDialog.getExistingDirectory(self, tr("Añadir carpeta"), start)
        if not d:
            return
        self.settings.setValue("last_input_dir", d)
        rec = QMessageBox.question(self, tr("Añadir carpeta"), tr("¿Incluir también las subcarpetas?"),
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes
        self.add_paths([d], recursive=rec)

    def add_paths(self, paths: list[str], recursive: bool = True):
        found = []
        for p in paths:
            if os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    for f in sorted(files):
                        if os.path.splitext(f)[1].lower() in ALL_EXTENSIONS:
                            found.append(os.path.join(root, f))
                    if not recursive:
                        break
            elif os.path.isfile(p):
                found.append(p)
        known = {os.path.normcase(os.path.abspath(v["path"])) for v in self.files.values()}
        added = 0
        self.table.blockSignals(True)
        for p in found:
            ap = os.path.abspath(p)
            if os.path.normcase(ap) in known:
                continue
            known.add(os.path.normcase(ap))
            fid = self._next_id
            self._next_id += 1
            try:
                fmt, warns = detect(ap)
                status = "pendiente"
            except (DetectionError, OSError) as e:
                fmt, warns, status = None, [str(e)], "no_valido"
            self.files[fid] = {"path": ap, "fmt": fmt, "size": os.path.getsize(ap) if os.path.exists(ap) else 0,
                               "status": status, "report": None, "detect_warnings": warns}
            self._insert_row(fid)
            added += 1
            for w in warns:
                self._log("warning", f"{os.path.basename(ap)}: {tr_msg(w)}")
        self.table.blockSignals(False)
        self._refresh_count()
        if added:
            self._log("info", tr("{n} archivo(s) añadido(s).", n=added))
            if self.table.currentRow() < 0:
                self.table.selectRow(0)
        self._update_applicability()

    def _insert_row(self, fid: int):
        f = self.files[fid]
        r = self.table.rowCount()
        self.table.insertRow(r)
        name = QTableWidgetItem(icon(FORMAT_ICON.get(f["fmt"] or "", "cube"), PRIMARY), os.path.basename(f["path"]))
        name.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        name.setCheckState(Qt.Checked if f["fmt"] else Qt.Unchecked)
        name.setData(Qt.UserRole, fid)
        name.setToolTip(f["path"])
        self.table.setItem(r, 0, name)
        self.table.setItem(r, 1, QTableWidgetItem(os.path.splitext(f["path"])[1].lower()))
        sz = QTableWidgetItem(human_size(f["size"]))
        sz.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(r, 2, sz)
        self.table.setItem(r, 3, QTableWidgetItem())
        self._set_status(fid, f["status"])

    def _row_of(self, fid: int) -> int:
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.data(Qt.UserRole) == fid:
                return r
        return -1

    def _set_status(self, fid: int, status: str):
        self.files[fid]["status"] = status
        r = self._row_of(fid)
        if r < 0:
            return
        label, ic, color = STATUS_VIEW.get(status, (status, "info", MUTED))
        it = self.table.item(r, 3)
        it.setText(label)
        it.setToolTip(label)
        it.setIcon(icon(ic, color))
        it.setForeground(QColor(color))

    def remove_selected(self):
        if self.conv_thread is not None and self.conv_thread.isRunning():
            QMessageBox.information(self, APP_NAME, tr("No se pueden eliminar archivos mientras hay una conversión en curso."))
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            fid = self.table.item(r, 0).data(Qt.UserRole)
            self.files.pop(fid, None)
            self.table.removeRow(r)
        self._refresh_count()
        self._update_applicability()
        if self.table.rowCount() == 0:
            self.viewer.clear()
            self.viewer.set_message(tr("Seleccione un archivo para ver la vista previa"))

    def _refresh_count(self):
        n = len(self.files)
        self.lbl_count.setText(tr("{n} archivos", n=n) if n != 1 else tr("1 archivo"))
        self.drop_hint.setVisible(n == 0)

    def _apply_filter(self, text: str):
        text = text.lower().strip()
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text().lower()
            self.table.setRowHidden(r, bool(text) and text not in name)

    def _checked_ids(self) -> list[int]:
        out = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it.checkState() == Qt.Checked:
                fid = it.data(Qt.UserRole)
                if self.files.get(fid, {}).get("fmt"):
                    out.append(fid)
        return out

    def _current_id(self) -> int | None:
        r = self.table.currentRow()
        if r < 0 or self.table.item(r, 0) is None:
            return None
        return self.table.item(r, 0).data(Qt.UserRole)

    def _files_menu(self, pos):
        fid = self._current_id()
        m = QMenu(self)
        m.addAction(icon("check"), tr("Marcar todos"), lambda: self._check_all(True))
        m.addAction(icon("cancel"), tr("Desmarcar todos"), lambda: self._check_all(False))
        m.addSeparator()
        if fid is not None:
            p = self.files[fid]["path"]
            m.addAction(icon("folder"), tr("Abrir carpeta del archivo"), lambda: os.startfile(os.path.dirname(p)))
            if self.files[fid].get("report") is not None:
                m.addAction(icon("report"), tr("Ver informe de conversión"),
                            lambda: ReportDialog(self.files[fid]["report"], self).exec())
                diag = getattr(self.files[fid]["report"], "diagnostic_log", "")
                if diag and os.path.isfile(diag):
                    m.addAction(icon("log"), tr("Abrir registro de diagnóstico"), lambda d=diag: os.startfile(d))
        m.addAction(icon("trash"), tr("Eliminar de la lista"), self.remove_selected)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _check_all(self, on: bool):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            fid = self.table.item(r, 0).data(Qt.UserRole)
            if self.files[fid]["fmt"]:
                self.table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_applicability()

    def _file_double_clicked(self, row, col):
        fid = self.table.item(row, 0).data(Qt.UserRole)
        if self.files[fid].get("report") is not None:
            ReportDialog(self.files[fid]["report"], self).exec()

    # ===================================================================== drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)

    # ===================================================================== selección y vista previa
    def _on_file_selected(self):
        fid = self._current_id()
        if fid is None or fid not in self.files:
            return
        f = self.files[fid]
        self.txt_source.setText(tr(FORMATS[f["fmt"]].long_name) if f["fmt"] else tr("No reconocido"))
        self.txt_source.setCursorPosition(0)
        self.lbl_preview_name.setText(os.path.basename(f["path"]))
        self._update_route_info()
        if f["fmt"]:
            self.request_preview(f["path"])
        if f.get("report") is not None:
            self._show_losses(f["report"].losses, f["report"].warnings, done=True)

    def _invalidate_previews(self):
        self.preview_cache.clear()
        fid = self._current_id()
        if fid is not None and self.files[fid]["fmt"]:
            self.request_preview(self.files[fid]["path"])

    def request_preview(self, path: str):
        if path in self.preview_cache:
            npz, info = self.preview_cache[path]
            self._show_preview(path, npz, info)
            return
        self.current_preview_path = path
        if self.preview_thread is not None and self.preview_thread.isRunning():
            self.preview_pending = path
            return
        self.viewer.clear()
        self.viewer.set_message(tr("Generando vista previa…"))
        self.lbl_preview_info.setText("")
        self.preview_thread = PreviewThread(path, self._options())
        self.preview_thread.preview_ready.connect(self._preview_ready)
        self.preview_thread.preview_failed.connect(self._preview_failed)
        self.preview_thread.finished.connect(self._preview_thread_done)
        self.preview_thread.start()

    def _preview_thread_done(self):
        if self.preview_pending:
            p, self.preview_pending = self.preview_pending, None
            self.request_preview(p)

    def _preview_ready(self, path, npz, info):
        self.preview_cache[path] = (npz, info)
        if path == self.current_preview_path and not self.preview_pending:
            self._show_preview(path, npz, info)

    def _show_preview(self, path, npz, info):
        self.current_preview_path = path
        try:
            self.viewer.load_npz(npz, info)
        except Exception as e:
            self.viewer.set_message(tr("No se pudo mostrar la vista previa: {e}", e=e))
            return
        txt = tr("{o} objeto(s) · {t} triángulos · {m} material(es)", o=info['objects'], t=f"{info['triangles']:,}".replace(",", "."), m=info['materials'])
        if info.get("textures"):
            txt += " · " + tr("{n} textura(s)", n=info['textures'])
        self.lbl_preview_info.setText(txt)

    def _preview_failed(self, path, msg):
        if path == self.current_preview_path:
            self.viewer.clear()
            self.viewer.set_message(tr("No se pudo generar la vista previa:\n") + msg[:300])
            self._log("error", tr("Vista previa de {f}: {msg}", f=os.path.basename(path), msg=tr_msg(msg)))

    def toggle_preview_fullscreen(self):
        full = self.hsplit.widget(0).isVisible()
        for w in (self.hsplit.widget(0), self.hsplit.widget(2), self.vsplit.widget(1)):
            w.setVisible(not full)

    # ===================================================================== opciones
    def _target(self) -> str:
        return self.cmb_target.currentData()

    def _options(self) -> ConversionOptions:
        return ConversionOptions(
            target_format=self._target(), output_dir=self.txt_out.text().strip(),
            quality=self.cmb_quality.currentData(),
            linear_tolerance_mm=self.spn_tol.value() or None,
            scale=self.spn_scale.value(), input_units=self.cmb_in_units.currentData(),
            output_units=self.cmb_out_units.currentData(), input_up_axis=self.cmb_in_axis.currentData(),
            output_up_axis=self.cmb_out_axis.currentData(), keep_materials=self.chk_materials.isChecked(),
            keep_structure=self.chk_structure.isChecked(), include_properties=self.chk_props.isChecked(),
            merge_by_material=self.chk_merge.isChecked(), stl_ascii=self.chk_stl_ascii.isChecked(),
            gltf_embed=self.chk_embed.isChecked(), ifc_schema=self.cmb_ifc.currentData(),
            step_schema=self.cmb_step.currentData(), sew_mesh_to_solid=self.chk_solid.isChecked(),
            mesh_repair=self.chk_repair.isChecked(), unify_coplanar=self.chk_unify.isChecked(),
            mesh_simplify="auto" if self.chk_simplify.isChecked() else "off",
            mesh_target_triangles=self.spn_target.value(),
            max_triangles_to_cad=self.spn_maxtri.value(), timeout_s=self.spn_timeout.value(),
            overwrite=self.chk_overwrite.isChecked(), validate=self.chk_validate.isChecked())

    def _apply_options(self, o: ConversionOptions):
        def set_combo(c, val):
            i = c.findData(val)
            if i >= 0:
                c.setCurrentIndex(i)
        set_combo(self.cmb_target, o.target_format)
        self.txt_out.setText(o.output_dir)
        set_combo(self.cmb_quality, o.quality)
        self.spn_tol.setValue(o.linear_tolerance_mm or 0.0)
        self.spn_scale.setValue(o.scale)
        set_combo(self.cmb_in_units, o.input_units)
        set_combo(self.cmb_out_units, o.output_units)
        set_combo(self.cmb_in_axis, o.input_up_axis)
        set_combo(self.cmb_out_axis, o.output_up_axis)
        self.chk_materials.setChecked(o.keep_materials)
        self.chk_structure.setChecked(o.keep_structure)
        self.chk_props.setChecked(o.include_properties)
        self.chk_merge.setChecked(o.merge_by_material)
        self.chk_stl_ascii.setChecked(o.stl_ascii)
        self.chk_embed.setChecked(o.gltf_embed)
        set_combo(self.cmb_ifc, o.ifc_schema)
        set_combo(self.cmb_step, o.step_schema)
        self.chk_solid.setChecked(o.sew_mesh_to_solid)
        self.chk_repair.setChecked(o.mesh_repair)
        self.chk_unify.setChecked(o.unify_coplanar)
        self.chk_simplify.setChecked(o.mesh_simplify != "off")
        self.spn_target.setValue(o.mesh_target_triangles)
        self.spn_maxtri.setValue(o.max_triangles_to_cad)
        self.spn_timeout.setValue(o.timeout_s)
        self.chk_overwrite.setChecked(o.overwrite)
        self.chk_validate.setChecked(o.validate)

    def _choose_output(self):
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta de salida"), self.txt_out.text() or os.path.expanduser("~"))
        if d:
            self.txt_out.setText(d)

    def _update_applicability(self):
        """Habilita solo los parámetros que afectan a las conversiones seleccionadas."""
        dst = self._target()
        ids = self._checked_ids() or ([self._current_id()] if self._current_id() else [])
        srcs = {self.files[i]["fmt"] for i in ids if i in self.files and self.files[i]["fmt"]}
        fam = {FORMATS[s].family for s in srcs}
        tess = any(r is not None and any(e.dst == "scene" and e.src in ("cad", "bim") for e in r.edges)
                   for r in (find_route(s, dst) for s in srcs))
        to_cad = dst in ("step", "iges") and bool(fam & {"mesh"})
        unitless_in = bool(srcs & {"obj", "stl"})
        unitless_out = dst in ("obj", "stl")
        mesh_out = FORMATS[dst].family == "mesh"
        rules = [
            ((self.lbl_quality, self.sld_quality, self.cmb_quality, self.lbl_tol, self.spn_tol), tess or not srcs),
            ((self.lbl_in_units, self.cmb_in_units, self.lbl_in_axis, self.cmb_in_axis), unitless_in or not srcs),
            ((self.lbl_out_units, self.cmb_out_units, self.lbl_out_axis, self.cmb_out_axis), unitless_out),
            ((self.chk_materials,), dst != "stl"),
            ((self.chk_structure,), dst not in ("stl", "obj", "iges")),
            ((self.chk_props,), dst in ("gltf", "glb", "ifc")),
            ((self.chk_merge,), dst in ("gltf", "glb", "fbx", "obj")),
            ((self.chk_stl_ascii,), dst == "stl"),
            ((self.chk_embed,), dst == "gltf"),
            ((self.lbl_ifc, self.cmb_ifc), dst == "ifc" and (srcs != {"ifc"})),
            ((self.lbl_step, self.cmb_step), dst == "step"),
            ((self.chk_solid, self.chk_repair, self.chk_unify, self.chk_simplify, self.lbl_target, self.spn_target,
              self.lbl_maxtri, self.spn_maxtri), to_cad or (dst in ("step", "iges") and not srcs)),
        ]
        for widgets, enabled in rules:
            for w in widgets:
                w.setEnabled(bool(enabled))
        self._update_route_info()

    def _update_route_info(self):
        dst = self._target()
        fid = self._current_id()
        src = self.files[fid]["fmt"] if fid in self.files else None
        if not src:
            ids = self._checked_ids()
            src = self.files[ids[0]]["fmt"] if ids else None
        if not src:
            self.lbl_route_fid.setText(tr("Ruta de conversión"))
            self.lbl_route.setText(tr("Añada archivos para ver la ruta de conversión."))
            return
        r = find_route(src, dst)
        if r is None:
            self.lbl_route_fid.setText(tr("No soportada"))
            self.lbl_route.setText(tr("No existe una ruta técnica válida."))
            return
        fid_label = r.fidelity.label
        self.lbl_route_fid.setText(tr("{a} → {b}: {fid} · semántica {sem}", a=FORMATS[src].name, b=FORMATS[dst].name,
                                      fid=fid_label, sem=tr(semantic_level(src, dst)).lower()))
        self.route_box.setStyleSheet(f"QFrame#routeBox {{ background: {FIDELITY_COLORS[r.fidelity]}; "
                                     "border: 1px solid #cfd8e3; border-radius: 6px; }")
        txt = " → ".join(tr_msg(s) for s in r.steps)
        note = NOTES.get((src, dst))
        if note:
            txt += "\n" + tr_msg(note)
        self.lbl_route.setText(txt)
        self._show_losses(runtime_losses(r), [], done=False)

    def _show_losses(self, losses, warnings, done: bool):
        if not losses and not warnings:
            self.lbl_warn_title.setText(tr("Sin pérdidas de información previstas") if not done else tr("Sin incidencias"))
            self.lbl_warn.setText(tr("La conversión conserva la información representable en ambos formatos."))
            return
        self.lbl_warn_title.setText(tr("Pérdidas e incidencias de la conversión") if done else tr("Posible pérdida de información"))
        items = "".join(f"<li>{tr_msg(l)}</li>" for l in losses)
        items += "".join(f"<li style='color:#7a5200'>{tr_msg(w)}</li>" for w in warnings[:12])
        self.lbl_warn.setText(f"<ul style='margin-left:-20px'>{items}</ul>")

    # ===================================================================== perfiles
    def _profiles_path(self) -> str:
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_ID)
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "perfiles.json")

    def _read_profiles(self) -> dict:
        try:
            with open(self._profiles_path(), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _fill_profiles_menu(self):
        m = self.profile_menu
        m.clear()
        m.addAction(icon("save"), tr("Guardar configuración actual como perfil…"), self._save_profile)
        profiles = self._read_profiles()
        if profiles:
            m.addSeparator()
            for name in sorted(profiles):
                m.addAction(icon("layers"), name, lambda n=name: self._load_profile(n))
            m.addSeparator()
            dm = m.addMenu(icon("trash"), tr("Eliminar perfil"))
            for name in sorted(profiles):
                dm.addAction(name, lambda n=name: self._delete_profile(n))
        m.addSeparator()
        m.addAction(icon("rotate"), tr("Restablecer valores predeterminados"), lambda: self._apply_options(ConversionOptions()))

    def _save_profile(self):
        name, ok = QInputDialog.getText(self, tr("Guardar perfil"), tr("Nombre del perfil:"))
        if ok and name.strip():
            p = self._read_profiles()
            p[name.strip()] = self._options().to_dict()
            with open(self._profiles_path(), "w", encoding="utf-8") as fh:
                json.dump(p, fh, ensure_ascii=False, indent=1)
            self._log("info", tr("Perfil '{p}' guardado.", p=name.strip()))

    def _load_profile(self, name):
        p = self._read_profiles().get(name)
        if p:
            self._apply_options(ConversionOptions.from_dict(p))
            self._log("info", tr("Perfil '{p}' cargado.", p=name))

    def _delete_profile(self, name):
        p = self._read_profiles()
        p.pop(name, None)
        with open(self._profiles_path(), "w", encoding="utf-8") as fh:
            json.dump(p, fh, ensure_ascii=False, indent=1)

    # ===================================================================== conversión
    def start_conversion(self):
        if self.conv_thread is not None and self.conv_thread.isRunning():
            return
        ids = self._checked_ids()
        if not ids:
            QMessageBox.information(self, APP_NAME, tr("Marque al menos un archivo válido para convertir."))
            return
        opts = self._options()
        if opts.output_dir and not os.path.isdir(opts.output_dir):
            try:
                os.makedirs(opts.output_dir, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, APP_NAME, tr("No se puede crear la carpeta de salida:\n{e}", e=e))
                return
        unsupported = [i for i in ids if find_route(self.files[i]["fmt"], opts.target_format) is None]
        if unsupported:
            QMessageBox.warning(self, APP_NAME, tr("Algunas conversiones no tienen ruta válida y se omitirán."))
            ids = [i for i in ids if i not in unsupported]
        self.queue.setRowCount(0)
        jobs = []
        for k, fid in enumerate(ids, 1):
            f = self.files[fid]
            r = self.queue.rowCount()
            self.queue.insertRow(r)
            it = QTableWidgetItem(str(k))
            it.setData(Qt.UserRole, fid)
            self.queue.setItem(r, 0, it)
            self.queue.setItem(r, 1, QTableWidgetItem(os.path.basename(f["path"])))
            self.queue.setItem(r, 2, QTableWidgetItem(f"{FORMATS[f['fmt']].name} → {FORMATS[opts.target_format].name}"))
            self.queue.setItem(r, 3, QTableWidgetItem())
            self._set_status(fid, "en_cola")
            self._set_queue_status(fid, "en_cola")
            f["report"] = None
            jobs.append((fid, f["path"], opts))
        self.lbl_queue.setText(tr("Cola de conversión ({n})", n=len(jobs)))
        self.batch_total = len(jobs)
        self.batch_done = 0
        self.job_progress = {fid: 0.0 for fid, _, _ in jobs}
        self.batch_started = time.time()
        self.batch_stats = {"ok": 0, "warn": 0, "fail": 0, "cancel": 0}
        self.batch_first_failed = None
        self.lbl_counts.setText("")
        self.lbl_current.setStyleSheet("")
        self.conv_thread = ConversionThread(jobs, parallel=self.spn_parallel.value())
        self.conv_thread.job_started.connect(self._job_started)
        self.conv_thread.job_progress.connect(self._job_progress)
        self.conv_thread.job_finished.connect(self._job_finished)
        self.conv_thread.batch_finished.connect(self._batch_finished)
        self.btn_convert.setEnabled(False)
        self.btn_convert_top.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._log("info", tr("Iniciando lote: {n} archivo(s) → {fmt}.", n=len(jobs), fmt=FORMATS[opts.target_format].name))
        self.settings.setValue("options", json.dumps(opts.to_dict()))
        self.conv_thread.start()

    def cancel_conversion(self):
        if self.conv_thread is not None and self.conv_thread.isRunning():
            self.conv_thread.cancel_all()
            self._log("warning", tr("Cancelación solicitada: se detienen los trabajos en curso y pendientes."))
            self.btn_cancel.setEnabled(False)

    def _set_queue_status(self, fid, status):
        for r in range(self.queue.rowCount()):
            if self.queue.item(r, 0).data(Qt.UserRole) == fid:
                label, ic, color = STATUS_VIEW.get(status, (status, "info", MUTED))
                it = self.queue.item(r, 3)
                it.setText(label)
                it.setIcon(icon(ic, color))
                it.setForeground(QColor(color))
                return

    def _job_started(self, fid):
        self.current_job = fid
        f = self.files[fid]
        self._set_status(fid, "en_conversion")
        self._set_queue_status(fid, "en_conversion")
        ext = FORMATS[self._job_target()].extensions[0] if self._job_target() else ""
        self.lbl_current.setText(tr("Convirtiendo: {a} → {b}", a=os.path.basename(f['path']),
                                    b=os.path.splitext(os.path.basename(f['path']))[0] + ext))
        self._log("info", tr("Iniciando conversión de \"{f}\"…", f=os.path.basename(f['path'])))

    def _job_target(self):
        if self.conv_thread and self.conv_thread.jobs:
            return self.conv_thread.jobs[0][2].target_format
        return None

    def _job_progress(self, fid, frac, msg):
        self.job_progress[fid] = frac
        if fid == self.current_job:
            self.lbl_current.setToolTip(msg)
        self._update_overall()

    def _job_finished(self, fid, rep):
        self.files[fid]["report"] = rep
        self.job_progress[fid] = 1.0
        self.batch_done += 1
        self._set_status(fid, rep.status)
        self._set_queue_status(fid, rep.status)
        name = os.path.basename(self.files[fid]["path"])
        for ts, level, msg in rep.log:
            if level in ("warning", "loss", "error"):
                self._log(level, f"{name}: {tr_msg(msg)}", ts)
        if rep.status in (Status.SUCCESS, Status.SUCCESS_WARNINGS):
            self.batch_stats["ok" if rep.status == Status.SUCCESS else "warn"] += 1
            for o in rep.outputs[:1]:
                self._log("ok", tr("{f}: escrito {o}", f=name, o=o))
                self.last_output_dir = os.path.dirname(o)
            v = rep.validation
            if v:
                parts = []
                if "desviacion_dimensiones_m" in v:
                    parts.append(tr("Δ dimensiones {d} mm", d=f"{v['desviacion_dimensiones_m'] * 1000:.4g}"))
                for k in ("triangles", "solidos", "productos", "assimp_triangles"):
                    if k in v:
                        parts.append(f"{k}={v[k]}")
                self._log("ok", tr("{f}: validación correcta ({d})", f=name, d=', '.join(parts)))
        else:
            self.batch_stats["cancel" if rep.status == Status.CANCELLED else "fail"] += 1
            if rep.status == Status.FAILED:
                self._log("error", tr("{f}: conversión fallida. El archivo original no se ha modificado.", f=name))
                if rep.stage:
                    self._log("error", tr("{f}: etapa del fallo: {s}", f=name, s=tr_msg(rep.stage)))
                proc = rep.technical.get("proceso", {}) if isinstance(rep.technical, dict) else {}
                if proc.get("codigo_salida") not in (None, 0):
                    self._log("error", tr("{f}: código de salida del proceso: {c}", f=name, c=proc.get("interpretacion")))
                if self.batch_first_failed is None:
                    self.batch_first_failed = fid
        diag = getattr(rep, "diagnostic_log", "")
        if diag:
            self._log("error" if rep.status == Status.FAILED else "info",
                      tr("{f}: registro de diagnóstico: {p}", f=name, p=diag))
        if fid == self._current_id():
            self._show_losses(rep.losses, rep.warnings + rep.errors, done=True)
        self._update_overall()

    def _batch_finished(self):
        s = self.batch_stats
        good = s['ok'] + s['warn']
        bad = s['fail'] + s['cancel']
        if bad == 0:
            self._log("ok", tr("Lote finalizado: {ok} correctas, {warn} con advertencias, {fail} fallidas/canceladas.",
                               ok=s['ok'], warn=s['warn'], fail=0))
            self.lbl_current.setText(tr("Finalizado: {n} de {t} archivo(s) convertidos.", n=good, t=self.batch_total))
            self.lbl_current.setStyleSheet(f"color:{OK}; font-weight:600;")
        else:
            self._log("error", tr("Lote finalizado con errores: {ok} correctas, {warn} con advertencias, {fail} fallidas, "
                                  "{cancel} canceladas.", ok=s['ok'], warn=s['warn'], fail=s['fail'], cancel=s['cancel']))
            self.lbl_current.setText(tr("Finalizado con errores: {n} de {t} archivo(s) convertidos.", n=good,
                                        t=self.batch_total))
            self.lbl_current.setStyleSheet(f"color:{ERR}; font-weight:600;")
            if self.batch_first_failed is not None:      # mostrar el archivo fallido (vista previa y causas)
                r = self._row_of(self.batch_first_failed)
                if r >= 0:
                    self.table.selectRow(r)
                rep = self.files[self.batch_first_failed].get("report")
                if rep is not None:
                    self._show_losses(rep.losses, rep.errors + rep.warnings, done=True)
        self.btn_convert.setEnabled(True)
        self.btn_convert_top.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(1000)
        self.lbl_pct.setText("100 %")
        self.lbl_eta.setText(tr("Tiempo restante estimado: 00:00:00"))
        self.current_job = None
        QApplicationBeep()

    def _update_overall(self):
        if not self.batch_total:
            return
        frac = sum(self.job_progress.values()) / self.batch_total
        self.progress.setValue(int(frac * 1000))
        self.lbl_pct.setText(f"{int(frac * 100)} %")
        self._overall_frac = frac
        s = self.batch_stats
        self.lbl_counts.setText(tr("Procesados: {d}/{t} · Correctos: {ok} · Con advertencias: {w} · Fallidos: {f} · "
                                   "Cancelados: {c}", d=self.batch_done, t=self.batch_total, ok=s['ok'], w=s['warn'],
                                   f=s['fail'], c=s['cancel']))

    def _tick(self):
        if self.conv_thread is not None and self.conv_thread.isRunning():
            el = time.time() - self.batch_started
            self.lbl_elapsed.setText(tr("Tiempo transcurrido: ") + time.strftime("%H:%M:%S", time.gmtime(el)))
            frac = getattr(self, "_overall_frac", 0.0)
            if frac > 0.03:
                rem = el / frac * (1 - frac)
                self.lbl_eta.setText(tr("Tiempo restante estimado: ") + time.strftime("%H:%M:%S", time.gmtime(rem)))

    def _queue_double_clicked(self, row, col):
        fid = self.queue.item(row, 0).data(Qt.UserRole)
        rep = self.files.get(fid, {}).get("report")
        if rep is not None:
            ReportDialog(rep, self).exec()

    def _queue_selected(self):
        r = self.queue.currentRow()
        if r < 0:
            return
        fid = self.queue.item(r, 0).data(Qt.UserRole)
        row = self._row_of(fid)
        if row >= 0 and self.table.currentRow() != row:
            self.table.selectRow(row)             # la vista previa y el formato de origen pasan a ese archivo
        rep = self.files.get(fid, {}).get("report")
        if rep is not None:
            self._show_losses(rep.losses, rep.warnings + rep.errors, done=True)

    def open_output_folder(self):
        d = self.last_output_dir or self.txt_out.text().strip()
        if not d:
            fid = self._current_id()
            d = os.path.dirname(self.files[fid]["path"]) if fid else ""
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            QMessageBox.information(self, APP_NAME, tr("Todavía no hay una carpeta de destino."))

    # ===================================================================== registro
    def _log(self, level: str, msg: str, ts: float | None = None):
        t = time.strftime("%H:%M:%S", time.localtime(ts or time.time()))
        ic, color = {"info": ("info", PRIMARY), "warning": ("warning", WARN), "loss": ("warning", WARN),
                     "error": ("error", ERR), "ok": ("check", OK)}.get(level, ("info", PRIMARY))
        it = QListWidgetItem(icon(ic, color, 16), f"[{t}]  {msg}")
        if level in ("warning", "loss"):
            it.setForeground(QColor(WARN))
        elif level == "error":
            it.setForeground(QColor(ERR))
        self.log.addItem(it)
        if self.log.count() > 5000:
            self.log.takeItem(0)
        self.log.scrollToBottom()

    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar registro"), "registro_conversion.txt", tr("Texto (*.txt)"))
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(self.log.count()):
                    fh.write(self.log.item(i).text() + "\n")

    # ===================================================================== ayuda
    def _doc_path(self, name: str) -> str | None:
        from .app import resource_dir
        for base in (os.path.join(resource_dir(), "docs"), os.path.join(resource_dir(), "..", "docs")):
            p = os.path.abspath(os.path.join(base, name))
            if os.path.isfile(p):
                return p
        return None

    def open_manual(self):
        p = self._doc_path(tr("Manual_de_usuario.html"))
        if p:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        else:
            QMessageBox.information(self, APP_NAME, tr("No se encontró el manual en la instalación."))

    def open_licenses(self):
        p = self._doc_path(tr("LICENCIAS_TERCEROS.html"))
        if p:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        else:
            QMessageBox.information(self, APP_NAME, tr("No se encontró el archivo de licencias."))

    def _change_language(self):
        from ..i18n import set_language
        code = self.cmb_lang.currentData()
        self.settings.setValue("language", code)
        self.settings.sync()
        set_language(code)
        if self.conv_thread is not None and self.conv_thread.isRunning():
            QMessageBox.information(self, APP_NAME, tr("El idioma se aplicará al reiniciar la aplicación."))
            return
        if QMessageBox.question(self, APP_NAME, tr("Es necesario reiniciar la aplicación para cambiar el idioma. "
                                                   "¿Reiniciar ahora?")) == QMessageBox.Yes:
            import subprocess
            import sys
            args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "u3dc"]
            files = [v["path"] for v in self.files.values()]
            self.close()
            subprocess.Popen(args + files, close_fds=True)

    # ===================================================================== ajustes
    def _load_settings(self):
        g = self.settings.value("geometry")
        if g is not None:
            self.restoreGeometry(g)
        raw = self.settings.value("options")
        if raw:
            try:
                self._apply_options(ConversionOptions.from_dict(json.loads(raw)))
            except Exception:
                pass

    def closeEvent(self, e):
        if self.conv_thread is not None and self.conv_thread.isRunning():
            if QMessageBox.question(self, APP_NAME, tr("Hay conversiones en curso. ¿Cancelarlas y salir?")) != QMessageBox.Yes:
                e.ignore()
                return
            self.conv_thread.cancel_all()
            self.conv_thread.wait(15000)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("options", json.dumps(self._options().to_dict()))
        for npz, _ in self.preview_cache.values():
            try:
                os.remove(npz)
            except OSError:
                pass
        self.viewer.close()
        super().closeEvent(e)


def QApplicationBeep():
    from PySide6.QtWidgets import QApplication
    QApplication.beep()
