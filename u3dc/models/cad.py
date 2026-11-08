"""CADModel: geometría B-Rep exacta (Open CASCADE).

Convención interna: milímetros (unidad de trabajo estándar de OCCT/XDE), Z arriba.
Cada pieza conserva su forma TopoDS (ya situada en coordenadas globales), su nombre,
la ruta de ensamblaje y el color si existe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CadPart:
    name: str
    shape: Any                         # OCP.TopoDS.TopoDS_Shape
    color: tuple | None = None         # RGB 0..1
    path: tuple = ()                   # nombres de ensamblajes padre
    faceted: bool = False              # True si procede de una malla (representación facetada)
    properties: dict = field(default_factory=dict)


@dataclass
class CADModel:
    parts: list = field(default_factory=list)
    name: str = "Modelo CAD"
    unit_mm: float = 1.0               # milímetros por unidad interna (siempre 1)
    source_unit: str = "mm"            # unidad declarada en el archivo de origen
    metadata: dict = field(default_factory=dict)
    ignored: list = field(default_factory=list)

    def bounds(self):
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        import numpy as np
        box = Bnd_Box()
        any_shape = False
        for p in self.parts:
            if p.shape is None or p.shape.IsNull():
                continue
            try:
                BRepBndLib.AddOptimal_s(p.shape, box, False, False)
            except Exception:
                BRepBndLib.Add_s(p.shape, box, True)
            any_shape = True
        if not any_shape or box.IsVoid():
            return None
        lo, hi = box.CornerMin(), box.CornerMax()
        return np.array([[lo.X(), lo.Y(), lo.Z()], [hi.X(), hi.Y(), hi.Z()]], dtype=float)
