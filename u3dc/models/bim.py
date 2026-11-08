"""BIMModel: modelo IFC (IfcOpenShell) con entidades, propiedades y relaciones."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BIMModel:
    ifc: Any                           # ifcopenshell.file
    path: str | None = None
    schema: str = "IFC4"
    name: str = "Modelo IFC"
    metadata: dict = field(default_factory=dict)
    ignored: list = field(default_factory=list)

    def products_with_geometry(self):
        return [p for p in self.ifc.by_type("IfcProduct")
                if getattr(p, "Representation", None) is not None]
