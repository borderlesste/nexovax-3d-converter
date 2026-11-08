# Arquitectura y análisis de viabilidad

## 1. Naturaleza de los formatos

| Familia | Formatos | Representación | Unidades / ejes |
|---|---|---|---|
| Mallas | glTF, GLB, OBJ, FBX, STL | Triángulos/polígonos, materiales, jerarquía (según formato) | glTF: m, Y arriba (norma). FBX: declara unidad y ejes. OBJ/STL: **no declaran nada** |
| CAD | STEP (AP203/214/242), IGES | B-Rep exacto: sólidos, caras sobre superficies analíticas/NURBS, tolerancias | Declaran unidad; Z arriba |
| BIM | IFC2X3, IFC4, IFC4X3 | Entidades semánticas + geometría (extrusiones, B-Rep, mallas), propiedades, relaciones | Unidades del proyecto; Z arriba |

Consecuencias que guían el diseño:

* **Malla → CAD** no puede recuperar un sólido paramétrico; lo honesto es un **B-Rep facetado** (cada triángulo una cara plana),
  válido para OCCT y para cualquier sistema CAD, y declararlo como *aproximado*.
* **CAD/BIM → malla** exige **teselación** con tolerancia controlable.
* **CAD ↔ CAD** e **IFC → CAD** pueden conservar la geometría exacta (B-Rep) sin pasar por triángulos.
* **Cualquier formato → IFC** sin información BIM de origen solo puede producir **entidades genéricas**
  (`IfcBuildingElementProxy`) en una estructura espacial mínima. No se inventan muros, forjados ni materiales constructivos.
* OBJ/STL obligan a **suponer unidades y ejes**; la suposición se hace explícita en opciones e informe.

## 2. Matriz de viabilidad

Las 64 combinaciones tienen una ruta técnica válida; ninguna es «no soportada». El detalle (ruta, pérdidas, notas)
se genera automáticamente desde el enrutador en [Matriz_de_compatibilidad.md](Matriz_de_compatibilidad.md), y los
resultados medidos sobre archivos reales en [resultados_matriz.md](resultados_matriz.md).

| Origen \ Destino | glTF/GLB/OBJ/FBX/STL | IFC | STEP / IGES |
|---|---|---|---|
| **glTF/GLB/OBJ/FBX/STL** | Directa | Limitada (proxy genérico) | Aproximada (B-Rep facetado) |
| **IFC** | Teselación | Directa | **Directa (B-Rep exacto)**, pérdida semántica |
| **STEP / IGES** | Teselación | Limitada (teselación + proxy) | Directa |

«No recomendable» (pero soportado con límite configurable): mallas muy densas → STEP/IGES (por defecto se rechazan
por encima de 200 000 triángulos, con explicación).

## 3. Selección de motores

| Necesidad | Motor elegido | Licencia | Motivo |
|---|---|---|---|
| STEP/IGES, B-Rep, teselación, validación de formas | **Open CASCADE** vía **OCP** (cadquery-ocp) | LGPL-2.1+exc. / Apache-2.0 | Referencia libre para B-Rep; XDE conserva nombres, colores y ensamblajes |
| IFC (lectura, geometría, escritura) | **IfcOpenShell 0.9** | LGPL-3.0 | Soporta IFC2X3/IFC4/IFC4X3; genera B-Rep OCCT serializado (ruta IFC→STEP exacta) |
| glTF/GLB lectura | **trimesh** | MIT | Lector maduro, texturas y jerarquía |
| FBX y OBJ lectura | **ufbx** | MIT | Lector FBX robusto (binario/ASCII, todas las versiones), normaliza unidades y ejes |
| Escritura glTF/GLB, OBJ, STL, **FBX** | **Implementación propia** | — | Control de instancias, extras, unidades. FBX binario 7.4 escrito sin FBX SDK |
| Validación independiente de mallas | **Assimp** (assimp-py) | BSD-3 / MIT | Segundo lector, distinto del usado para escribir/leer |
| Visor 3D | **VTK 9** | BSD-3 | Ya requerido por OCP; visor robusto con OpenGL |
| Interfaz | **PySide6 (Qt 6)** | LGPL-3.0 | Interfaz nativa, hilos, arrastrar y soltar |

**Blender** se evaluó (modo background) y se descartó: ≈1 GB adicional, licencia GPL y su única aportación diferencial
(FBX) queda cubierta por ufbx + escritor propio, validado con ufbx **y** Assimp. **Assimp** no se usa como exportador
FBX porque el binding disponible es solo de importación. Ningún motor se usa para lo que no soporta bien: por ejemplo,
el FBX de salida se verifica con dos lectores independientes.

### Incidencia documentada del binding ufbx
El binding Python `ufbx 0.0.5` libera memoria interna de la escena al destruir algunos objetos envoltorio (violación de
acceso comprobada). Solución: la lectura nativa se ejecuta **siempre** en un proceso hijo desechable que conserva vivos
todos los envoltorios, copia los datos a numpy y termina con `os._exit` (`u3dc/engines/mesh/ufbx_reader.py`).

## 4. Arquitectura

```
Archivo → Detección (contenido real) → Importador → Representación → Transformación → Exportador → Validación → Publicación atómica
```

```
u3dc/
├── __main__.py           GUI sin argumentos; CLI con "convert|matrix|info"
├── cli.py                línea de comandos
├── core/
│   ├── formats.py        registro de formatos + detección por contenido
│   ├── router.py         grafo de rutas (Dijkstra por fidelidad), capacidades, matriz
│   ├── adapters.py       importadores / transformaciones / exportadores; unidades y ejes
│   ├── converter.py      orquestador de una conversión (informe, validación, escritura atómica)
│   ├── validator.py      relectura, dimensiones, lector independiente, esquema IFC
│   ├── jobs.py           procesos aislados, cancelación, tiempo máximo, lotes
│   ├── preview.py        datos de vista previa (proceso aislado)
│   ├── safety.py         rutas largas/Unicode, nombres, temporales, escritura atómica
│   ├── options.py        opciones serializables
│   └── report.py         informe: estado, fidelidad, pérdidas, registro
├── models/               SceneModel · CADModel · BIMModel (representaciones intermedias)
├── engines/
│   ├── mesh/             gltf_io, gltf_writer, obj_writer, stl_io, fbx_writer, ufbx_reader, polygons
│   ├── cad/occt.py       STEP/IGES XDE, teselación, malla→B-Rep, cosido IGES
│   └── bim/ifc.py        IFC → malla, IFC → B-Rep, malla → IFC
└── ui/                   ventana principal, visor VTK, hilos, diálogos, iconos, estilo
```

### Representaciones intermedias
* **SceneModel** (metros, Z arriba): nodos con matriz local, mallas compartidas (instancias), materiales PBR, texturas,
  propiedades por nodo.
* **CADModel** (milímetros): piezas `TopoDS_Shape` con nombre, color, ruta de ensamblaje y marca de «facetada».
* **BIMModel**: archivo IfcOpenShell (entidades, psets, relaciones) + metadatos.

No se reduce todo a mallas: el enrutador minimiza primero la pérdida geométrica y después el número de pasos, por lo que
IFC→STEP usa `bim → cad` (B-Rep exacto) y STEP↔IGES nunca tesela.

### Unidades y ejes (nunca silenciosos)
Cada importador normaliza a la convención interna mediante una transformación de raíz (sin hornear vértices cuando no es
necesario). Cada exportador aplica la convención del destino. Los supuestos para OBJ/STL y la unidad numérica escrita en
OBJ/STL aparecen como advertencias en el informe.

### Aislamiento, seguridad y escritura atómica
* Cada conversión y cada vista previa se ejecuta en un **proceso independiente** (`multiprocessing` spawn); un fallo
  nativo solo marca ese trabajo como fallido. Cancelar termina el proceso.
* Se trabaja en `%TEMP%\u3dc\u3dc_xxxx`; los motores C++ reciben copias con ruta corta ASCII si la original es larga o
  Unicode. Tras validar, los archivos se copian al destino como `.partial` y se renombran (`os.replace`).
* Sin sobrescritura accidental (sufijo «(1)»), límite de tamaño, tiempo máximo, límite de triángulos para CAD.
* Recursos externos (buffers/texturas) restringidos a la carpeta del modelo; URL y rutas `..` bloqueadas; no se ejecuta
  ningún contenido de los modelos.

### Validación automática (tras cada conversión)
Existencia y tamaño → relectura con el adaptador → presencia de geometría → comparación de caja envolvente (tolerancia
0,2 % de la diagonal + 4× la tolerancia de teselación; >5 % = fallo) y nº de objetos → lector independiente
(Assimp / BRepCheck de OCCT / validación de esquema IfcOpenShell). Resultado: exitoso, exitoso con advertencias o fallido.
