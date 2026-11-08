# Matriz de compatibilidad de formatos

Generada automáticamente desde `u3dc/core/router.py` (la misma lógica que usa la aplicación).

## Leyenda

| Nivel | Significado |
|---|---|
| 🟢 Directa | La geometría se transfiere sin cambio de representación (malla→malla o B-Rep→B-Rep). |
| 🔵 Teselación | Superficies exactas (B-Rep CAD o geometría IFC) convertidas a triángulos con tolerancia configurable. |
| 🟡 Facetada | Malla convertida a B-Rep facetado (cada triángulo = cara plana). Geométricamente válido, **no** es un sólido paramétrico. |
| 🟠 Limitada | Conversión válida con pérdida relevante de información (p. ej. malla → IFC con entidades genéricas). |
| 🔴 No soportada | Sin ruta técnica válida (ninguna combinación de los 8 formatos cae en esta categoría). |

Conservación semántica: **Completa** (todo lo que el origen puede contener cabe en el destino), **Parcial** (se pierde parte: jerarquía, metadatos, texturas…) o **Solo geometría**.

## Resumen (geometría · semántica)

| Origen \ Destino | glTF | GLB | OBJ | FBX | STL | IFC | STEP | IGES |
|---|---|---|---|---|---|---|---|---|
| **glTF** | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Parcial | 🟢 Directa<br>Parcial | 🟢 Directa<br>Solo geometría | 🟠 Limitada<br>Parcial | 🟡 Facetada<br>Parcial | 🟡 Facetada<br>Parcial |
| **GLB** | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Parcial | 🟢 Directa<br>Parcial | 🟢 Directa<br>Solo geometría | 🟠 Limitada<br>Parcial | 🟡 Facetada<br>Parcial | 🟡 Facetada<br>Parcial |
| **OBJ** | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Solo geometría | 🟠 Limitada<br>Parcial | 🟡 Facetada<br>Parcial | 🟡 Facetada<br>Parcial |
| **FBX** | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Parcial | 🟢 Directa<br>Completa | 🟢 Directa<br>Solo geometría | 🟠 Limitada<br>Parcial | 🟡 Facetada<br>Parcial | 🟡 Facetada<br>Parcial |
| **STL** | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa | 🟠 Limitada<br>Completa | 🟡 Facetada<br>Completa | 🟡 Facetada<br>Completa |
| **IFC** | 🔵 Teselación<br>Parcial | 🔵 Teselación<br>Parcial | 🔵 Teselación<br>Parcial | 🔵 Teselación<br>Parcial | 🔵 Teselación<br>Solo geometría | 🟢 Directa<br>Completa | 🟢 Directa<br>Parcial | 🟢 Directa<br>Parcial |
| **STEP** | 🔵 Teselación<br>Completa | 🔵 Teselación<br>Completa | 🔵 Teselación<br>Parcial | 🔵 Teselación<br>Completa | 🔵 Teselación<br>Solo geometría | 🟠 Limitada<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Parcial |
| **IGES** | 🔵 Teselación<br>Completa | 🔵 Teselación<br>Completa | 🔵 Teselación<br>Parcial | 🔵 Teselación<br>Completa | 🔵 Teselación<br>Solo geometría | 🟠 Limitada<br>Completa | 🟢 Directa<br>Completa | 🟢 Directa<br>Completa |

## Capacidades de cada formato

| Formato | Familia | Información que puede transportar |
|---|---|---|
| glTF 2.0 (JSON + recursos) | mesh | Instancias, Jerarquía, Materiales, Metadatos, Nombres, Texturas, UV, Unidades |
| GLB (glTF binario) | mesh | Instancias, Jerarquía, Materiales, Metadatos, Nombres, Texturas, UV, Unidades |
| Wavefront OBJ | mesh | Materiales, Nombres, Texturas, UV |
| Autodesk FBX (binario 7.4) | mesh | Instancias, Jerarquía, Materiales, Nombres, Texturas, UV, Unidades |
| STL (estereolitografía) | mesh | solo geometría triangular |
| IFC (Industry Foundation Classes) | bim | B-Rep exacto, Jerarquía, Materiales, Metadatos, Nombres, Semántica BIM, Unidades |
| STEP AP203/AP214/AP242 | cad | B-Rep exacto, Colores, Jerarquía, Nombres, Unidades |
| IGES 5.3 | cad | B-Rep exacto, Colores, Nombres, Unidades |

## Detalle de cada combinación

### Desde glTF

- **glTF → glTF** — 🟢 Directa, semántica completa.  
  Ruta: Importar glTF → Exportar glTF.  
- **glTF → GLB** — 🟢 Directa, semántica completa.  
  Ruta: Importar glTF → Exportar GLB.  
- **glTF → OBJ** — 🟢 Directa, semántica parcial.  
  Ruta: Importar glTF → Exportar OBJ + MTL.  
  Pérdidas posibles: Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas; Instancias de glTF: no representable en OBJ; Jerarquía de glTF: no representable en OBJ; Metadatos de glTF: no representable en OBJ; Unidades de glTF: no representable en OBJ.  
- **glTF → FBX** — 🟢 Directa, semántica parcial.  
  Ruta: Importar glTF → Exportar FBX binario 7.4.  
  Pérdidas posibles: Materiales PBR convertidos a modelo Phong de FBX (aproximación visual); Metadatos de glTF: no representable en FBX.  
- **glTF → STL** — 🟢 Directa, semántica solo geometría.  
  Ruta: Importar glTF → Exportar STL.  
  Pérdidas posibles: STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía; Instancias de glTF: no representable en STL; Jerarquía de glTF: no representable en STL; Materiales de glTF: no representable en STL; Metadatos de glTF: no representable en STL; Nombres de glTF: no representable en STL; Texturas de glTF: no representable en STL; UV de glTF: no representable en STL; Unidades de glTF: no representable en STL.  
- **glTF → IFC** — 🟠 Limitada, semántica parcial.  
  Ruta: Importar glTF → Malla → IFC genérico (IfcBuildingElementProxy) → Exportar IFC.  
  Pérdidas posibles: No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta); Instancias de glTF: no representable en IFC; Texturas de glTF: no representable en IFC; UV de glTF: no representable en IFC.  
- **glTF → STEP** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar glTF → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar STEP (B-Rep).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; Instancias de glTF: no representable en STEP; Metadatos de glTF: no representable en STEP; Texturas de glTF: no representable en STEP; UV de glTF: no representable en STEP.  
  Nota: Válida como B-Rep facetado.
- **glTF → IGES** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar glTF → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes; Instancias de glTF: no representable en IGES; Jerarquía de glTF: no representable en IGES; Metadatos de glTF: no representable en IGES; Texturas de glTF: no representable en IGES; UV de glTF: no representable en IGES.  

### Desde GLB

- **GLB → glTF** — 🟢 Directa, semántica completa.  
  Ruta: Importar GLB → Exportar glTF.  
- **GLB → GLB** — 🟢 Directa, semántica completa.  
  Ruta: Importar GLB → Exportar GLB.  
- **GLB → OBJ** — 🟢 Directa, semántica parcial.  
  Ruta: Importar GLB → Exportar OBJ + MTL.  
  Pérdidas posibles: Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas; Instancias de GLB: no representable en OBJ; Jerarquía de GLB: no representable en OBJ; Metadatos de GLB: no representable en OBJ; Unidades de GLB: no representable en OBJ.  
- **GLB → FBX** — 🟢 Directa, semántica parcial.  
  Ruta: Importar GLB → Exportar FBX binario 7.4.  
  Pérdidas posibles: Materiales PBR convertidos a modelo Phong de FBX (aproximación visual); Metadatos de GLB: no representable en FBX.  
- **GLB → STL** — 🟢 Directa, semántica solo geometría.  
  Ruta: Importar GLB → Exportar STL.  
  Pérdidas posibles: STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía; Instancias de GLB: no representable en STL; Jerarquía de GLB: no representable en STL; Materiales de GLB: no representable en STL; Metadatos de GLB: no representable en STL; Nombres de GLB: no representable en STL; Texturas de GLB: no representable en STL; UV de GLB: no representable en STL; Unidades de GLB: no representable en STL.  
- **GLB → IFC** — 🟠 Limitada, semántica parcial.  
  Ruta: Importar GLB → Malla → IFC genérico (IfcBuildingElementProxy) → Exportar IFC.  
  Pérdidas posibles: No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta); Instancias de GLB: no representable en IFC; Texturas de GLB: no representable en IFC; UV de GLB: no representable en IFC.  
- **GLB → STEP** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar GLB → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar STEP (B-Rep).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; Instancias de GLB: no representable en STEP; Metadatos de GLB: no representable en STEP; Texturas de GLB: no representable en STEP; UV de GLB: no representable en STEP.  
  Nota: Válida como B-Rep facetado.
- **GLB → IGES** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar GLB → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes; Instancias de GLB: no representable en IGES; Jerarquía de GLB: no representable en IGES; Metadatos de GLB: no representable en IGES; Texturas de GLB: no representable en IGES; UV de GLB: no representable en IGES.  

### Desde OBJ

- **OBJ → glTF** — 🟢 Directa, semántica completa.  
  Ruta: Importar OBJ → Exportar glTF.  
- **OBJ → GLB** — 🟢 Directa, semántica completa.  
  Ruta: Importar OBJ → Exportar GLB.  
- **OBJ → OBJ** — 🟢 Directa, semántica completa.  
  Ruta: Importar OBJ → Exportar OBJ + MTL.  
  Pérdidas posibles: Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas.  
- **OBJ → FBX** — 🟢 Directa, semántica completa.  
  Ruta: Importar OBJ → Exportar FBX binario 7.4.  
  Pérdidas posibles: Materiales PBR convertidos a modelo Phong de FBX (aproximación visual).  
- **OBJ → STL** — 🟢 Directa, semántica solo geometría.  
  Ruta: Importar OBJ → Exportar STL.  
  Pérdidas posibles: STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía; Materiales de OBJ: no representable en STL; Nombres de OBJ: no representable en STL; Texturas de OBJ: no representable en STL; UV de OBJ: no representable en STL.  
- **OBJ → IFC** — 🟠 Limitada, semántica parcial.  
  Ruta: Importar OBJ → Malla → IFC genérico (IfcBuildingElementProxy) → Exportar IFC.  
  Pérdidas posibles: No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta); Texturas de OBJ: no representable en IFC; UV de OBJ: no representable en IFC.  
- **OBJ → STEP** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar OBJ → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar STEP (B-Rep).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; Texturas de OBJ: no representable en STEP; UV de OBJ: no representable en STEP.  
  Nota: Válida como B-Rep facetado; se pierden texturas y UV.
- **OBJ → IGES** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar OBJ → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes; Texturas de OBJ: no representable en IGES; UV de OBJ: no representable en IGES.  
  Nota: Válida como superficies facetadas; se pierden texturas y UV.

### Desde FBX

- **FBX → glTF** — 🟢 Directa, semántica completa.  
  Ruta: Importar FBX → Exportar glTF.  
- **FBX → GLB** — 🟢 Directa, semántica completa.  
  Ruta: Importar FBX → Exportar GLB.  
- **FBX → OBJ** — 🟢 Directa, semántica parcial.  
  Ruta: Importar FBX → Exportar OBJ + MTL.  
  Pérdidas posibles: Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas; Instancias de FBX: no representable en OBJ; Jerarquía de FBX: no representable en OBJ; Unidades de FBX: no representable en OBJ.  
- **FBX → FBX** — 🟢 Directa, semántica completa.  
  Ruta: Importar FBX → Exportar FBX binario 7.4.  
  Pérdidas posibles: Materiales PBR convertidos a modelo Phong de FBX (aproximación visual).  
- **FBX → STL** — 🟢 Directa, semántica solo geometría.  
  Ruta: Importar FBX → Exportar STL.  
  Pérdidas posibles: STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía; Instancias de FBX: no representable en STL; Jerarquía de FBX: no representable en STL; Materiales de FBX: no representable en STL; Nombres de FBX: no representable en STL; Texturas de FBX: no representable en STL; UV de FBX: no representable en STL; Unidades de FBX: no representable en STL.  
- **FBX → IFC** — 🟠 Limitada, semántica parcial.  
  Ruta: Importar FBX → Malla → IFC genérico (IfcBuildingElementProxy) → Exportar IFC.  
  Pérdidas posibles: No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta); Instancias de FBX: no representable en IFC; Texturas de FBX: no representable en IFC; UV de FBX: no representable en IFC.  
- **FBX → STEP** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar FBX → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar STEP (B-Rep).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; Instancias de FBX: no representable en STEP; Texturas de FBX: no representable en STEP; UV de FBX: no representable en STEP.  
  Nota: Solo geometría estática; animaciones, huesos y deformaciones se ignoran.
- **FBX → IGES** — 🟡 Facetada, semántica parcial.  
  Ruta: Importar FBX → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes; Instancias de FBX: no representable en IGES; Jerarquía de FBX: no representable en IGES; Texturas de FBX: no representable en IGES; UV de FBX: no representable en IGES.  

### Desde STL

- **STL → glTF** — 🟢 Directa, semántica completa.  
  Ruta: Importar STL → Exportar glTF.  
- **STL → GLB** — 🟢 Directa, semántica completa.  
  Ruta: Importar STL → Exportar GLB.  
- **STL → OBJ** — 🟢 Directa, semántica completa.  
  Ruta: Importar STL → Exportar OBJ + MTL.  
  Pérdidas posibles: Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas.  
- **STL → FBX** — 🟢 Directa, semántica completa.  
  Ruta: Importar STL → Exportar FBX binario 7.4.  
  Pérdidas posibles: Materiales PBR convertidos a modelo Phong de FBX (aproximación visual).  
- **STL → STL** — 🟢 Directa, semántica completa.  
  Ruta: Importar STL → Exportar STL.  
  Pérdidas posibles: STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía.  
- **STL → IFC** — 🟠 Limitada, semántica completa.  
  Ruta: Importar STL → Malla → IFC genérico (IfcBuildingElementProxy) → Exportar IFC.  
  Pérdidas posibles: No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta).  
- **STL → STEP** — 🟡 Facetada, semántica completa.  
  Ruta: Importar STL → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar STEP (B-Rep).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico.  
  Nota: Válida como B-Rep facetado. No recomendable para mallas de más de ~200.000 triángulos (límite configurable).
- **STL → IGES** — 🟡 Facetada, semántica completa.  
  Ruta: Importar STL → Malla → B-Rep facetado (OCCT, cosido de caras) → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: Representación facetada: cada triángulo es una cara plana; no se recupera un sólido CAD paramétrico; IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes.  
  Nota: Válida como superficies facetadas. No recomendable para mallas muy densas.

### Desde IFC

- **IFC → glTF** — 🔵 Teselación, semántica parcial.  
  Ruta: Importar IFC → Teselación IFC → triángulos (IfcOpenShell) → Exportar glTF.  
  Pérdidas posibles: Geometría IFC aproximada por triángulos; Relaciones IFC (conexiones, sistemas, fases, aberturas como entidades) no representables en mallas; Semántica BIM de IFC: no representable en glTF.  
- **IFC → GLB** — 🔵 Teselación, semántica parcial.  
  Ruta: Importar IFC → Teselación IFC → triángulos (IfcOpenShell) → Exportar GLB.  
  Pérdidas posibles: Geometría IFC aproximada por triángulos; Relaciones IFC (conexiones, sistemas, fases, aberturas como entidades) no representables en mallas; Semántica BIM de IFC: no representable en GLB.  
- **IFC → OBJ** — 🔵 Teselación, semántica parcial.  
  Ruta: Importar IFC → Teselación IFC → triángulos (IfcOpenShell) → Exportar OBJ + MTL.  
  Pérdidas posibles: Geometría IFC aproximada por triángulos; Relaciones IFC (conexiones, sistemas, fases, aberturas como entidades) no representables en mallas; Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas; Jerarquía de IFC: no representable en OBJ; Metadatos de IFC: no representable en OBJ; Semántica BIM de IFC: no representable en OBJ; Unidades de IFC: no representable en OBJ.  
- **IFC → FBX** — 🔵 Teselación, semántica parcial.  
  Ruta: Importar IFC → Teselación IFC → triángulos (IfcOpenShell) → Exportar FBX binario 7.4.  
  Pérdidas posibles: Geometría IFC aproximada por triángulos; Relaciones IFC (conexiones, sistemas, fases, aberturas como entidades) no representables en mallas; Materiales PBR convertidos a modelo Phong de FBX (aproximación visual); Metadatos de IFC: no representable en FBX; Semántica BIM de IFC: no representable en FBX.  
- **IFC → STL** — 🔵 Teselación, semántica solo geometría.  
  Ruta: Importar IFC → Teselación IFC → triángulos (IfcOpenShell) → Exportar STL.  
  Pérdidas posibles: Geometría IFC aproximada por triángulos; Relaciones IFC (conexiones, sistemas, fases, aberturas como entidades) no representables en mallas; STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía; Jerarquía de IFC: no representable en STL; Materiales de IFC: no representable en STL; Metadatos de IFC: no representable en STL; Nombres de IFC: no representable en STL; Semántica BIM de IFC: no representable en STL; Unidades de IFC: no representable en STL.  
- **IFC → IFC** — 🟢 Directa, semántica completa.  
  Ruta: Importar IFC → Exportar IFC.  
- **IFC → STEP** — 🟢 Directa, semántica parcial.  
  Ruta: Importar IFC → Geometría IFC → B-Rep exacto (IfcOpenShell + OCCT) → Exportar STEP (B-Rep).  
  Pérdidas posibles: Datos BIM (propiedades, clasificación, relaciones, estructura espacial) no representables en CAD; Metadatos de IFC: no representable en STEP; Semántica BIM de IFC: no representable en STEP.  
  Nota: Geometría B-Rep exacta cuando la define IFC (extrusiones, B-Rep); la información BIM se pierde.
- **IFC → IGES** — 🟢 Directa, semántica parcial.  
  Ruta: Importar IFC → Geometría IFC → B-Rep exacto (IfcOpenShell + OCCT) → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: Datos BIM (propiedades, clasificación, relaciones, estructura espacial) no representables en CAD; IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes; Jerarquía de IFC: no representable en IGES; Metadatos de IFC: no representable en IGES; Semántica BIM de IFC: no representable en IGES.  
  Nota: Geometría B-Rep exacta; la información BIM se pierde.

### Desde STEP

- **STEP → glTF** — 🔵 Teselación, semántica completa.  
  Ruta: Importar STEP → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar glTF.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada.  
- **STEP → GLB** — 🔵 Teselación, semántica completa.  
  Ruta: Importar STEP → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar GLB.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada.  
- **STEP → OBJ** — 🔵 Teselación, semántica parcial.  
  Ruta: Importar STEP → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar OBJ + MTL.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas; Jerarquía de STEP: no representable en OBJ; Unidades de STEP: no representable en OBJ.  
- **STEP → FBX** — 🔵 Teselación, semántica completa.  
  Ruta: Importar STEP → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar FBX binario 7.4.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; Materiales PBR convertidos a modelo Phong de FBX (aproximación visual).  
- **STEP → STL** — 🔵 Teselación, semántica solo geometría.  
  Ruta: Importar STEP → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar STL.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía; Colores de STEP: no representable en STL; Jerarquía de STEP: no representable en STL; Nombres de STEP: no representable en STL; Unidades de STEP: no representable en STL.  
- **STEP → IFC** — 🟠 Limitada, semántica completa.  
  Ruta: Importar STEP → Teselación B-Rep → triángulos (OCCT BRepMesh) → Malla → IFC genérico (IfcBuildingElementProxy) → Exportar IFC.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta).  
  Nota: La geometría se tesela y se crean entidades genéricas IfcBuildingElementProxy.
- **STEP → STEP** — 🟢 Directa, semántica completa.  
  Ruta: Importar STEP → Exportar STEP (B-Rep).  
- **STEP → IGES** — 🟢 Directa, semántica parcial.  
  Ruta: Importar STEP → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes; Jerarquía de STEP: no representable en IGES.  
  Nota: Conversión B-Rep directa.

### Desde IGES

- **IGES → glTF** — 🔵 Teselación, semántica completa.  
  Ruta: Importar IGES → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar glTF.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada.  
- **IGES → GLB** — 🔵 Teselación, semántica completa.  
  Ruta: Importar IGES → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar GLB.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada.  
- **IGES → OBJ** — 🔵 Teselación, semántica parcial.  
  Ruta: Importar IGES → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar OBJ + MTL.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; Jerarquía aplanada: cada objeto se escribe como grupo con transformaciones aplicadas; Unidades de IGES: no representable en OBJ.  
- **IGES → FBX** — 🔵 Teselación, semántica completa.  
  Ruta: Importar IGES → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar FBX binario 7.4.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; Materiales PBR convertidos a modelo Phong de FBX (aproximación visual).  
- **IGES → STL** — 🔵 Teselación, semántica solo geometría.  
  Ruta: Importar IGES → Teselación B-Rep → triángulos (OCCT BRepMesh) → Exportar STL.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; STL no admite materiales, texturas, UV, nombres de objetos ni jerarquía; Colores de IGES: no representable en STL; Nombres de IGES: no representable en STL; Unidades de IGES: no representable en STL.  
- **IGES → IFC** — 🟠 Limitada, semántica completa.  
  Ruta: Importar IGES → Teselación B-Rep → triángulos (OCCT BRepMesh) → Malla → IFC genérico (IfcBuildingElementProxy) → Exportar IFC.  
  Pérdidas posibles: Superficies exactas B-Rep aproximadas por triángulos según la tolerancia configurada; No existe información BIM en el origen: se crean entidades genéricas IfcBuildingElementProxy dentro de una estructura espacial mínima (Proyecto/Sitio/Edificio/Planta).  
  Nota: La geometría se tesela y se crean entidades genéricas IfcBuildingElementProxy.
- **IGES → STEP** — 🟢 Directa, semántica completa.  
  Ruta: Importar IGES → Exportar STEP (B-Rep).  
  Nota: Conversión B-Rep directa; superficies sueltas se exportan como tales.
- **IGES → IGES** — 🟢 Directa, semántica completa.  
  Ruta: Importar IGES → Exportar IGES (B-Rep, entidades 186/514).  
  Pérdidas posibles: IGES no conserva la estructura de ensamblaje; las piezas se exportan como entidades independientes.  

