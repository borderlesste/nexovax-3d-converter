"""Genera packaging/app.ico (multi-resolución) a partir del icono vectorial de la aplicación."""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PIL import Image  # noqa: E402


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    from u3dc.ui.icons import app_icon
    ic = app_icon()
    pm = ic.pixmap(256, 256)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    img = Image.open(io.BytesIO(bytes(buf.data())))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
    img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(os.path.join(os.path.dirname(out), "app.png"))
    print("Icono generado:", out)


if __name__ == "__main__":
    main()
