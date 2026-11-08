"""Representaciones intermedias: SceneModel (mallas), CADModel (B-Rep) y BIMModel (IFC)."""
from .scene import SceneModel, SceneNode, Mesh, Material, Texture
from .cad import CADModel, CadPart
from .bim import BIMModel

__all__ = ["SceneModel", "SceneNode", "Mesh", "Material", "Texture", "CADModel", "CadPart", "BIMModel"]
