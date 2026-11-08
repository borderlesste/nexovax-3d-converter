"""Hoja de estilo (tema claro profesional)."""

PRIMARY = "#1f6fd6"
PRIMARY_DARK = "#1856a8"
TEXT = "#1d2733"
MUTED = "#5b6b7c"
BORDER = "#d9e0ea"
BG = "#eef2f7"
PANEL = "#ffffff"
OK = "#1e8e3e"
WARN = "#b26a00"
ERR = "#c62828"

QSS = f"""
* {{ font-family: "Segoe UI", "Segoe UI Variable", Arial; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QWidget#central {{ background: {BG}; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel#panelTitle {{ font-size: 12pt; font-weight: 600; }}
QLabel#appTitle {{ font-size: 16pt; font-weight: 700; }}
QLabel#appSubtitle {{ color: {MUTED}; font-size: 10.5pt; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#sectionTitle {{ font-weight: 600; }}
QFrame#header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QPushButton {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ background: #f4f7fb; border-color: #b9c6d6; }}
QPushButton:pressed {{ background: #e8eef6; }}
QPushButton:disabled {{ color: #9aa8b6; background: #f6f8fb; }}
QPushButton#primary {{ background: {PRIMARY}; color: white; border: 1px solid {PRIMARY_DARK}; font-weight: 600; }}
QPushButton#primary:hover {{ background: #2a7ce6; }}
QPushButton#primary:disabled {{ background: #9dbbe6; border-color: #9dbbe6; }}
QPushButton#bigPrimary {{ background: {PRIMARY}; color: white; border: 1px solid {PRIMARY_DARK}; font-weight: 700;
    font-size: 11.5pt; padding: 10px 26px; border-radius: 6px; }}
QPushButton#bigPrimary:hover {{ background: #2a7ce6; }}
QPushButton#bigPrimary:disabled {{ background: #9dbbe6; border-color: #9dbbe6; }}
QPushButton#danger {{ color: {ERR}; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: #eef3fa; border-color: {BORDER}; }}
QToolButton:checked {{ background: #dce9fb; border-color: #a9c6ef; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: white; border: 1px solid {BORDER}; border-radius: 5px;
    padding: 4px 6px; min-height: 20px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {PRIMARY}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ background: #f3f5f8; color: #9aa8b6; }}
QLineEdit[readOnly="true"] {{ background: #f3f5f8; }}
QCheckBox:disabled {{ color: #9aa8b6; }}
QTableWidget, QTreeWidget, QListWidget {{ background: white; border: none; gridline-color: #edf1f6;
    selection-background-color: #e3eefc; selection-color: {TEXT}; alternate-background-color: #fafbfd; }}
QHeaderView::section {{ background: white; border: none; border-bottom: 1px solid {BORDER}; padding: 6px;
    font-weight: 600; }}
QProgressBar {{ border: none; background: #e3e9f1; border-radius: 4px; height: 10px; text-align: center; }}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 4px; }}
QSlider::groove:horizontal {{ height: 4px; background: #d6deea; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {PRIMARY}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {PRIMARY}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::handle:horizontal:disabled, QSlider::sub-page:horizontal:disabled {{ background: #b8c4d3; }}
QFrame#warnBox {{ background: #fff8e6; border: 1px solid #f2d48a; border-radius: 8px; }}
QFrame#routeBox {{ background: #f4f8fe; border: 1px solid #cfe0f7; border-radius: 6px; }}
QFrame#dimsOverlay {{ background: rgba(30, 40, 52, 205); border-radius: 6px; }}
QFrame#dimsOverlay QLabel {{ color: white; }}
QFrame#hintBar {{ background: rgba(30, 40, 52, 170); border-radius: 6px; }}
QFrame#hintBar QLabel {{ color: #e8eef6; font-size: 9pt; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 6px; margin-top: 14px; padding: 8px 6px 6px 6px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
QSplitter::handle {{ background: {BG}; }}
QToolTip {{ background: #1d2733; color: white; border: none; padding: 6px; }}
QMenu {{ background: white; border: 1px solid {BORDER}; }}
QMenu::item {{ padding: 6px 22px; }}
QMenu::item:selected {{ background: #e3eefc; }}
"""
