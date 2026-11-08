"""Visor 3D basado en VTK (BSD) integrado en Qt.

Rotar: botón izquierdo · Desplazar: botón central (o Mayús + izquierdo) · Zoom: rueda.
Modos: sombreado, alambre, sombreado con aristas. Rejilla y ejes XYZ conmutables.
Si OpenGL no está disponible, el visor se desactiva sin afectar a la conversión.
"""
from __future__ import annotations

from ..i18n import tr, tr_msg

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QGridLayout

from .style import MUTED


class Viewer3D(QWidget):
    ready_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.available = False
        self.actors = []
        self.grid_actor = None
        self.mode = "shaded"
        self.show_grid = True
        self._bounds = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        try:
            import vtkmodules.qt
            vtkmodules.qt.PyQtImpl = tr("PySide6")
            from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
            import vtkmodules.vtkRenderingOpenGL2  # noqa: F401  (registra el backend OpenGL)
            import vtkmodules.vtkInteractionStyle  # noqa: F401
            from vtkmodules.vtkRenderingCore import vtkRenderer
            from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
            from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
            from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera

            self.vtk_widget = QVTKRenderWindowInteractor(self)
            lay.addWidget(self.vtk_widget)
            self.renderer = vtkRenderer()
            self.renderer.SetBackground(0.86, 0.89, 0.93)
            self.renderer.SetBackground2(0.98, 0.99, 1.0)
            self.renderer.GradientBackgroundOn()
            rw = self.vtk_widget.GetRenderWindow()
            rw.AddRenderer(self.renderer)
            rw.SetMultiSamples(4)
            self.interactor = rw.GetInteractor()
            self.style = vtkInteractorStyleTrackballCamera()
            self.interactor.SetInteractorStyle(self.style)
            axes = vtkAxesActor()
            axes.SetShaftTypeToCylinder()
            axes.SetTotalLength(1, 1, 1)
            self.axes_widget = vtkOrientationMarkerWidget()
            self.axes_widget.SetOrientationMarker(axes)
            self.axes_widget.SetInteractor(self.interactor)
            self.axes_widget.SetViewport(0.0, 0.0, 0.18, 0.28)
            self.axes_widget.SetEnabled(1)
            self.axes_widget.InteractiveOff()
            self.vtk_widget.Initialize()
            self.available = True
        except Exception as e:  # sin OpenGL o VTK: el resto de la aplicación sigue funcionando
            msg = QLabel(tr("Vista previa no disponible en este equipo.") + f"\n({e})")
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(f"color: {MUTED};")
            lay.addWidget(msg)
            self.vtk_widget = None
            return

        # superposiciones
        self.dims = QFrame(self)
        self.dims.setObjectName("dimsOverlay")
        g = QGridLayout(self.dims)
        g.setContentsMargins(10, 8, 12, 8)
        g.setVerticalSpacing(2)
        t = QLabel(tr("Dimensiones del modelo"))
        t.setStyleSheet("font-weight:600;")
        g.addWidget(t, 0, 0, 1, 2)
        self.lbl_x, self.lbl_y, self.lbl_z, self.lbl_v = QLabel(), QLabel(), QLabel(), QLabel()
        for i, (k, w) in enumerate(((tr("X:"), self.lbl_x), (tr("Y:"), self.lbl_y), (tr("Z:"), self.lbl_z), (tr("Volumen:"), self.lbl_v))):
            g.addWidget(QLabel(k), i + 1, 0)
            g.addWidget(w, i + 1, 1)
        self.dims.hide()
        self.hint = QFrame(self)
        self.hint.setObjectName("hintBar")
        h = QHBoxLayout(self.hint)
        h.setContentsMargins(10, 4, 10, 4)
        for txt in (tr("Rotar: botón izquierdo"), tr("Zoom: rueda del ratón"), tr("Desplazar: botón central")):
            h.addWidget(QLabel(txt))
        self.status = QLabel(self)
        self.status.setStyleSheet(f"color:{MUTED}; background: transparent; font-size: 11pt;")
        self.status.setAlignment(Qt.AlignCenter)
        self.set_message(tr("Seleccione un archivo para ver la vista previa"))

    # ---------------------------------------------------------------- disposición
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self.available:
            return
        self.dims.adjustSize()
        self.dims.move(10, 10)
        self.hint.adjustSize()
        self.hint.move(max(0, (self.width() - self.hint.width()) // 2), self.height() - self.hint.height() - 8)
        self.status.setGeometry(0, 0, self.width(), self.height())

    def set_message(self, text: str):
        if not self.available:
            return
        self.status.setText(text)
        self.status.setVisible(bool(text))
        self.status.raise_()

    # ---------------------------------------------------------------- contenido
    def clear(self):
        if not self.available:
            return
        for a in self.actors:
            self.renderer.RemoveActor(a)
        self.actors = []
        if self.grid_actor is not None:
            self.renderer.RemoveActor(self.grid_actor)
            self.grid_actor = None
        self.dims.hide()
        self._bounds = None
        self.vtk_widget.GetRenderWindow().Render()

    def load_npz(self, path: str, info: dict):
        if not self.available:
            return
        from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
        from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        self.clear()
        data = np.load(path)
        n = int(data["count"])
        for i in range(n):
            v = np.ascontiguousarray(data[f"v{i}"], dtype=np.float32)
            f = np.ascontiguousarray(data[f"f{i}"], dtype=np.int64)
            c = data[f"c{i}"]
            pts = vtkPoints()
            pts.SetData(numpy_to_vtk(v, deep=True))
            cells = vtkCellArray()
            offsets = np.arange(0, 3 * len(f) + 1, 3, dtype=np.int64)
            cells.SetData(numpy_to_vtkIdTypeArray(offsets, deep=True),
                          numpy_to_vtkIdTypeArray(f.reshape(-1), deep=True))
            poly = vtkPolyData()
            poly.SetPoints(pts)
            poly.SetPolys(cells)
            normals = vtkPolyDataNormals()
            normals.SetInputData(poly)
            normals.SetFeatureAngle(35)
            normals.SplittingOn()
            normals.ConsistencyOff()
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(normals.GetOutputPort())
            actor = vtkActor()
            actor.SetMapper(mapper)
            prop = actor.GetProperty()
            prop.SetColor(float(c[0]), float(c[1]), float(c[2]))
            prop.SetOpacity(max(0.15, float(c[3])))
            prop.SetSpecular(0.2)
            prop.SetSpecularPower(20)
            prop.BackfaceCullingOff()
            self.renderer.AddActor(actor)
            self.actors.append(actor)
        b = info.get("bounds")
        if b:
            self._bounds = np.array(b)
            size = self._bounds[1] - self._bounds[0]
            fmt = lambda x: f"{x:,.3f} m".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
            self.lbl_x.setText(fmt(size[0]))
            self.lbl_y.setText(fmt(size[1]))
            self.lbl_z.setText(fmt(size[2]))
            vol = info.get("volume_m3")
            self.lbl_v.setText((f"{vol:,.4f} m³".replace(",", "X").replace(".", ",").replace("X", "."))
                               if vol is not None else tr("— (malla abierta)"))
            self.dims.show()
            self.dims.adjustSize()
            self.dims.raise_()
            self.hint.raise_()
            self._make_grid()
        self.set_mode(self.mode)
        self.set_message("")
        self.reset_view()

    def _make_grid(self):
        from vtkmodules.vtkFiltersSources import vtkPlaneSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper
        if self._bounds is None:
            return
        lo, hi = self._bounds
        size = float(max(hi[0] - lo[0], hi[1] - lo[1], 1e-6))
        step = 10 ** np.floor(np.log10(size / 2)) if size > 0 else 1
        half = np.ceil(size * 0.75 / step) * step
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        cx, cy = np.round(cx / step) * step, np.round(cy / step) * step
        n = int(min(200, max(2, 2 * half / step)))
        plane = vtkPlaneSource()
        plane.SetOrigin(cx - half, cy - half, lo[2])
        plane.SetPoint1(cx + half, cy - half, lo[2])
        plane.SetPoint2(cx - half, cy + half, lo[2])
        plane.SetResolution(n, n)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(plane.GetOutputPort())
        self.grid_actor = vtkActor()
        self.grid_actor.SetMapper(mapper)
        p = self.grid_actor.GetProperty()
        p.SetRepresentationToWireframe()
        p.SetColor(0.55, 0.6, 0.68)
        p.SetOpacity(0.35)
        p.LightingOff()
        self.grid_actor.SetPickable(False)
        self.grid_actor.SetVisibility(self.show_grid)
        self.renderer.AddActor(self.grid_actor)

    # ---------------------------------------------------------------- controles
    def set_mode(self, mode: str):
        self.mode = mode
        if not self.available:
            return
        for a in self.actors:
            p = a.GetProperty()
            if mode == "wire":
                p.SetRepresentationToWireframe()
                p.EdgeVisibilityOff()
            else:
                p.SetRepresentationToSurface()
                p.SetEdgeVisibility(mode == "edges")
                p.SetEdgeColor(0.15, 0.18, 0.22)
        self.vtk_widget.GetRenderWindow().Render()

    def set_grid(self, on: bool):
        self.show_grid = on
        if self.available and self.grid_actor is not None:
            self.grid_actor.SetVisibility(on)
            self.vtk_widget.GetRenderWindow().Render()

    def set_axes(self, on: bool):
        if self.available:
            self.axes_widget.SetEnabled(1 if on else 0)
            self.vtk_widget.GetRenderWindow().Render()

    def reset_view(self):
        if not self.available:
            return
        cam = self.renderer.GetActiveCamera()
        if self._bounds is not None:
            lo, hi = self._bounds
            c = (lo + hi) / 2
            d = float(np.linalg.norm(hi - lo)) or 1.0
            cam.SetFocalPoint(*c)
            cam.SetPosition(*(c + np.array([1.0, -1.3, 0.9]) * d))
            cam.SetViewUp(0, 0, 1)
        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

    def zoom(self, factor: float):
        if not self.available:
            return
        self.renderer.GetActiveCamera().Zoom(factor)
        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

    def closeEvent(self, e):
        if self.available:
            self.vtk_widget.Finalize()
        super().closeEvent(e)
