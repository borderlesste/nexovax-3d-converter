# Limitaciones técnicas conocidas

Se declaran explícitamente las capacidades que **no** se implementan o que solo se cubren parcialmente,
con su causa y la alternativa propuesta.

| # | Limitación | Causa | Alternativa / mitigación |
|---|---|---|---|
| 1 | **Animaciones, esqueletos (skinning), blend shapes, cámaras y luces** de FBX/glTF no se convierten. | El modelo intermedio es de geometría estática; FBX/glTF ↔ CAD/BIM no tienen equivalente. | Se exporta la pose estática y el informe lo indica. Para animación FBX ↔ glTF se recomienda una herramienta DCC (p. ej. Blender). |
| 2 | **Malla → STEP/IGES** genera B-Rep **facetado**, no superficies paramétricas; un STEP facetado ocupa ≈2,4 KB y necesita ≈13–25 KB de memoria por triángulo. | Reconstruir superficies analíticas/NURBS desde triángulos no es fiable de forma automática; el formato STEP es costoso para mallas densas. | Construcción nativa OCCT, un sólido por componente cerrado, unión de caras coplanares, reparación controlada y simplificación automática por pieza por encima de 100 000 △ (configurable) que conserva los sólidos cuando la memoria lo permite. Las piezas que no pueden cerrarse se exportan como superficie. Ver Correccion_STL_STEP_1.0.1.md y Correccion_GLB_STEP_1.0.2.md. |
| 3 | **Malla/CAD → IFC** crea `IfcBuildingElementProxy` genéricos. | No existe información semántica en el origen; inventarla falsearía el modelo. | Se conserva nombre, jerarquía (como texto) y datos de origen en el pset `NEXOVAX_Origen`. La clasificación debe hacerse en un software BIM. |
| 4 | **IFC → STEP/IGES/mallas** pierde propiedades, relaciones, fases, sistemas y espacios. | Esos formatos no pueden representarlos. | glTF/GLB conservan nombres, jerarquía espacial y psets en `extras`. `IfcSpace` no se exporta como geometría (volúmenes virtuales). |
| 5 | **IGES** no conserva la estructura de ensamblaje. | Limitación del formato/escritor IGES de OCCT. | Las piezas mantienen nombre y color. Usar STEP si se necesita la jerarquía. |
| 6 | **Ensamblajes STEP**: colores por cara, capas, PMI/GD&T y metadatos de producto avanzados no se trasladan. | Solo se transfieren nombre, color de pieza y jerarquía. | Conversión STEP→STEP conserva la geometría exacta; para PMI usar el CAD de origen. |
| 7 | **FBX de salida**: materiales PBR → Phong (aproximación), sin propiedades de usuario. | El modelo de material estándar de FBX es Phong/Lambert. | glTF/GLB recomendados si se necesita PBR fiel. |
| 8 | **FBX de salida** probado con ufbx y Assimp, no con Autodesk FBX SDK ni con Maya/3ds Max. | Esas herramientas no están disponibles en el entorno de pruebas (propietarias). | El archivo sigue la estructura binaria 7.4 estándar (cabecera, definiciones, conexiones, pie). Se recomienda una verificación puntual en el software de destino. |
| 9 | **OBJ/STL** no declaran unidades ni ejes. | Formatos sin metadatos. | Supuestos explícitos (STL mm/Z, OBJ m/Y) configurables y registrados en cada informe. |
| 10 | **Coordenadas muy alejadas del origen** (georreferenciadas) pierden precisión en glTF/STL binario. | Estos formatos almacenan vértices en float32. | Se emite advertencia si |coord| > 100 km. STEP/IFC/OBJ conservan doble precisión. |
| 11 | **Texturas**: solo color base (difusa). Mapas normal, rugosidad, emisivo, etc. no se trasladan. | Simplificación del modelo de materiales intermedio. | Los colores y factores PBR básicos sí se conservan. |
| 12 | **Primitivas de puntos y líneas** (glTF, OBJ `l`, curvas sueltas de IGES) se ignoran. | Solo se convierte geometría de superficie/sólido. | Se registra en el informe. |
| 13 | **IFC → IFC** reescribe el archivo tal cual (sin cambio de esquema IFC2X3 ↔ IFC4). | La migración de esquema exige reglas de mapeo semántico específicas. | Opción «Esquema IFC de salida» aplicable solo cuando el origen no es IFC. |
| 14 | **Archivos IFC/STEP enormes** (>2 GB) se rechazan por defecto. | Protección de memoria. | Límite configurable (`max_file_mb`); procesar en equipos con más RAM. |
| 15 | **Vista previa** requiere OpenGL 3.2. | VTK usa OpenGL. | Sin OpenGL la vista previa se desactiva y la conversión funciona igualmente. |
| 16 | **Binding ufbx 0.0.5** inestable al liberar objetos. | Defecto del binding (no de ufbx). | Lectura en proceso hijo aislado que nunca destruye objetos (ver Arquitectura). |
| 17 | **Prueba en máquina limpia y sin red**: realizada en el equipo de desarrollo. | No se dispone de una máquina Windows limpia en el entorno de construcción. | El instalador no contiene dependencias externas; ver «Verificación pendiente» en Compilacion_y_empaquetado.md. |
