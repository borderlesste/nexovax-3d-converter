"""Iconos vectoriales propios (SVG en línea, sin dependencias ni recursos externos)."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

_S = 'fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'

PATHS = {
    "add_file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 11v6M9 14h6"/>',
    "add_folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    "play": '<path d="M7 4l13 8-13 8z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6"/><path d="M12 17.5v.01"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "cube": '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
    "log": '<path d="M7 3h8l4 4v14H7z"/><path d="M15 3v4h4M10 12h6M10 16h6"/>',
    "warning": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "sync": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 3v5h5"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 21v-5h-5"/>',
    "hourglass": '<path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "error": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "cancel": '<circle cx="12" cy="12" r="9"/><path d="M6 18L18 6"/>',
    "cursor": '<path d="M5 3l14 7-6 2-2 6z"/>',
    "move": '<path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>',
    "rotate": '<path d="M20 12a8 8 0 1 1-3-6.2"/><path d="M20 4v5h-5"/>',
    "fit": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
    "zoom_in": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6M11 8v6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6"/>',
    "fullscreen": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "grid": '<path d="M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18"/>',
    "axes": '<path d="M5 19V5M5 19h14M5 19l9-9"/><path d="M5 5l-2 3M5 5l2 3M19 19l-3-2M19 19l-3 2"/>',
    "building": '<path d="M4 21V5l8-3v19M12 8l8 3v10M4 21h16M7 8h2M7 12h2M7 16h2M15 13h2M15 17h2"/>',
    "part": '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    "triangle": '<path d="M12 3l9 17H3z"/><path d="M12 3v17M3 20l9-7 9 7"/>',
    "stack": '<path d="M3 7l9-4 9 4-9 4z"/><path d="M3 12l9 4 9-4M3 17l9 4 9-4"/>',
    "box": '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M12 11v10M3 7l9 4 9-4"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h7V3M8 21v-7h8v7"/>',
    "report": '<path d="M7 3h10v18H7z"/><path d="M10 8h4M10 12h4M10 16h2"/>',
    "matrix": '<path d="M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18"/>',
    "wire": '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M3 7l18 10M21 7L3 17M12 2v20"/>',
}

FORMAT_ICON = {"ifc": "building", "step": "part", "iges": "box", "glb": "globe", "gltf": "globe",
               "obj": "triangle", "stl": "stack", "fbx": "cube"}


def svg(name: str, color: str = "#2b3a4a", size: int = 24) -> bytes:
    body = PATHS.get(name, PATHS["cube"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'{_S.format(c=color)}>{body}</svg>').encode()


@lru_cache(maxsize=512)
def icon(name: str, color: str = "#2b3a4a", size: int = 20) -> QIcon:
    renderer = QSvgRenderer(QByteArray(svg(name, color, 24)))
    ic = QIcon()
    for s in (size, size * 2):
        pm = QPixmap(QSize(s, s))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        ic.addPixmap(pm)
    return ic


LOGO_PATH = __import__("os").path.join(__import__("os").path.dirname(__file__), "resources", "logo.png")


def app_icon() -> QIcon:
    """Logotipo NEXOVAX (resources/logo.png) escalado a los tamaños habituales de Windows."""
    src = QPixmap(LOGO_PATH)
    ic = QIcon()
    if src.isNull():
        return icon("cube", "#1f6fd6", 32)
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(src.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return ic
