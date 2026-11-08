"""Opciones de conversión (serializables para pasarlas a procesos aislados)."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

UNITS_TO_METERS = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}
UNIT_LABELS = {"mm": "Milímetros (mm)", "cm": "Centímetros (cm)", "m": "Metros (m)",
               "in": "Pulgadas (in)", "ft": "Pies (ft)"}

# Calidad de malla → (tolerancia lineal relativa a la diagonal, deflexión angular en radianes)
QUALITY_PRESETS = {
    "baja": (2e-3, 0.8),
    "media": (5e-4, 0.5),
    "alta": (1e-4, 0.3),
    "muy_alta": (2e-5, 0.15),
}


@dataclass
class ConversionOptions:
    target_format: str = "glb"
    output_dir: str = ""
    # Teselación (CAD/BIM → malla)
    quality: str = "alta"
    linear_tolerance_mm: float | None = None   # None = automática según calidad y tamaño
    angular_tolerance_rad: float | None = None
    # Escala y unidades
    scale: float = 1.0
    input_units: str = "auto"       # para formatos sin unidades (OBJ/STL). auto: STL=mm, OBJ=m
    output_units: str = "auto"      # para formatos sin unidades. auto: conservar unidad de origen
    input_up_axis: str = "auto"     # para OBJ/STL. auto: OBJ=Y, STL=Z
    output_up_axis: str = "auto"    # para OBJ/STL. auto: OBJ=Y, STL=Z
    # Conservación
    keep_materials: bool = True
    keep_structure: bool = True
    include_properties: bool = True
    fix_normals: bool = True
    merge_by_material: bool = False   # salida de malla: un objeto por material (reduce nº de objetos)
    # Opciones específicas
    stl_ascii: bool = False
    gltf_embed: bool = False        # .gltf con buffers embebidos (data URI)
    ifc_schema: str = "IFC4"        # IFC4 | IFC2X3
    step_schema: str = "AP214"      # AP203 | AP214 | AP242
    sew_mesh_to_solid: bool = True  # malla → STEP/IGES: intentar sólido cerrado
    # Límites y seguridad
    max_file_mb: int = 2048
    max_triangles_to_cad: int = 200_000
    timeout_s: int = 1800
    overwrite: bool = False
    validate: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ConversionOptions":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
