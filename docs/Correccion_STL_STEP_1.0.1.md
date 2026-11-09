# Corrección STL → STEP y diagnóstico de errores (versión 1.0.1)

## 1. Problema notificado
Convertir `lipo battery 3d model (1)_converted.stl` a STEP terminaba con «conversión fallida» y el lote mostraba
«0 correctas, 0 con advertencias, 1 fallidas/canceladas», sin una causa técnica identificable.

El archivo original no estaba disponible en el equipo de desarrollo. Se reprodujeron los fallos con modelos
equivalentes generados de forma determinista (`tests/stl_cases.py`): esferas densas cerradas, mallas abiertas,
varios cuerpos en un solo STL, triángulos degenerados y duplicados, orientación mezclada, aristas no manifold y un
modelo tipo «batería LiPo» con todos esos defectos (`tools/repro_stl_step.py`).

## 2. Causa raíz (con evidencia)
| # | Causa | Evidencia (versión 1.0.0) | Función |
|---|---|---|---|
| 1 | **Construcción B-Rep triángulo a triángulo en Python** (`MakePolygon/MakeWire/MakeFace` por triángulo, `BRepCheck` y cosido de respaldo) | 150 000 △ → **359 s**; 2,4 ms por triángulo | `occt.mesh_to_shape` |
| 2 | **Límite fijo de 200 000 triángulos sin alternativa** | 400 000 △ → fallo inmediato: «La malla tiene 399 616 triángulos; el límite…» | `occt.scene_to_cad` |
| 3 | **Coste de memoria y tamaño no estimados**. Un STEP facetado es intrínsecamente costoso | Medido con OCCT: 150 000 △ → 2,15 GB de memoria y STEP de 375 MB; 400 000 △ → **4,05 GB y 1,02 GB**, unos 9 min. En un equipo de 8 GB el proceso se queda sin memoria o supera el tiempo máximo y termina de forma anormal | toda la ruta |
| 4 | **Todos los componentes como una sola pieza** | 3 cuerpos cerrados en un STL → 0 sólidos (todo como superficie) | `occt.mesh_to_shape` |
| 5 | **Sin reparación**: duplicados, degenerados y orientación incoherente impedían crear sólidos | LiPo sintética: 0 sólidos, 34 s | `occt.mesh_to_shape` |
| 6 | **Diagnóstico insuficiente**: si el proceso moría, solo se informaba «terminó inesperadamente (código N)», sin etapa ni pila | revisión de `jobs.run_isolated` | `jobs.run_isolated` |
| 7 | Carpetas temporales `%TEMP%\u3dc\u3dc_*` huérfanas tras trabajos cancelados o caídos | 4 carpetas encontradas en el equipo | `converter` / `jobs` |
| 8 | Fin de lote ambiguo: «Lote finalizado: 0 correctas…» sin «con errores»; progreso al 100 % mezclado con resultados | captura del usuario | `main_window._batch_finished` |

Causa más probable del caso notificado: un STL descargado y convertido en línea suele tener entre cientos de miles y
millones de triángulos, además de duplicados, componentes separados y caras no manifold. Con 1.0.0 eso producía las
causas 2 o 3: un rechazo por límite, o la muerte del proceso por memoria o tiempo, con un mensaje poco explicativo
(causa 6). No se puede confirmar sin el archivo; el registro de diagnóstico de 1.0.1 lo identificará exactamente si se
repite.

## 3. Corrección
### Nuevo motor `u3dc/engines/cad/mesh_to_brep.py`
1. **Análisis**: vértices, triángulos, vértices duplicados, triángulos degenerados y duplicados, componentes
   conectados, aristas abiertas y no manifold, aristas con orientación incoherente, volumen con signo por componente,
   y estado global (cerrada, abierta o no manifold).
2. **Reparación controlada** (opción, activada por defecto). Suelda vértices casi coincidentes, elimina degenerados y
   duplicados, orienta las normales de forma coherente (recorrido en anchura) y hacia fuera en componentes cerrados.
   No rellena agujeros ni inventa geometría. Cada acción queda registrada.
3. **Estimación de recursos**. Calcula memoria, tiempo y tamaño del STEP con el coste medido, frente a la memoria
   libre y al tiempo máximo por archivo.
4. **Simplificación** (opción «automática», con objetivo configurable; 100 000 △ por defecto). Usa decimación
   cuadrática con `fast-simplification` (MIT), con una alternativa de agrupación de vértices. Informa la desviación
   de la caja envolvente y el cambio de volumen, y el aviso indica si el objetivo lo fijó el usuario, el límite de
   triángulos o la memoria libre. Política de memoria:
   * **Simplificación automática:** el límite usa el 70 % de la memoria libre.
   * **Simplificación desactivada:** se admite hasta el 100 % de la memoria libre, con aviso de uso elevado; por
     encima, la conversión falla con una explicación cuantificada (memoria, tiempo y tamaño del STEP estimados).

   Esta política se ajustó porque una prueba falló cuando solo había 879 MB libres, mientras PyInstaller compilaba
   en paralelo. El propio registro de diagnóstico identificó la causa.
5. **Construcción nativa** con `BRepBuilderAPI_MakeShapeOnMesh` (C++), unas 50 veces más rápida. Genera un sólido
   por cada componente cerrado, manifold y coherente, validado con `BRepCheck`; las superficies abiertas o no manifold
   se exportan como *shell*. Se comprueban los resultados de las funciones de OCCT.
6. **Unión de caras coplanares** con `ShapeUpgrade_UnifySameDomain` (por ejemplo, un cubo pasa de 12 a 6 caras),
   validada; si la unión no es válida, se conserva el B-Rep facetado.
7. **Escritura STEP**: se registran los resultados reales de `Transfer()` y `Write()`, y el tamaño del archivo. El
   archivo se reabre y se valida antes de publicarlo; la comprobación `BRepCheck` completa se limita por tamaño y,
   cuando se omite, se indica.

### Diagnóstico (`u3dc/core/diagnostics.py`, `jobs.py`, `converter.py`, `report.py`)
* Cada conversión deja `%LOCALAPPDATA%\NEXOVAX3DConverter\logs\AAAAMMDD-HHMMSS_<archivo>.log` con:
  * rutas, formato y tamaño, opciones y etapas con su duración;
  * análisis de la malla antes y después de la reparación o simplificación;
  * memoria máxima, resultado de transferencia y escritura, y validación;
  * excepción con **traza completa** y, si el proceso murió, código de salida interpretado (NTSTATUS),
    **stdout/stderr** del proceso (incluida la salida de C++) y **pila de faulthandler**.
* Hay un **punto de control síncrono** en disco en cada cambio de etapa: aunque el proceso muera por un fallo nativo,
  se sabe en qué etapa estaba y se conserva el análisis hecho hasta entonces.
* El proceso padre crea y elimina la carpeta temporal: no quedan restos aunque el proceso de trabajo muera.

### Interfaz (`u3dc/ui/main_window.py`, `dialogs.py`)
* En caso de fallo el registro muestra la causa, la etapa, el código de salida y la ruta del registro de
  diagnóstico. Para abrirlo hay botón en el informe y entrada en el menú contextual.
* Contadores separados del progreso: «Procesados x/y · Correctos · Con advertencias · Fallidos · Cancelados».
* El fin de lote con fallos muestra en rojo **«Finalizado con errores»** y selecciona el archivo fallido. Así la vista
  previa y las causas corresponden al trabajo que falló; al hacer clic en la cola también se selecciona su archivo.
* Nuevas opciones de malla → CAD: reparar, unir caras coplanares, simplificar automáticamente, objetivo de
  triángulos y límite absoluto.
* Las opciones de cada trabajo se fijan al iniciar el lote; la vista previa no altera los trabajos en cola.
* Los STL binarios se nombran por su archivo, no por la cabecera binaria, que suele ser texto basura.

## 4. Resultados de las pruebas
| Caso | 1.0.0 | 1.0.1 |
|---|---|---|
| Cubo STL cerrado → STEP | sólido con 12 caras | **sólido válido con 6 caras**; dimensiones exactas al reabrir |
| Malla abierta → STEP | superficie | superficie (*shell*) válida, avisada |
| Varios componentes | 0 sólidos | **un sólido por componente (3)** |
| Degenerados, duplicados y orientación | parcial | reparados y registrados → **sólido válido** |
| LiPo sintética (141 aristas no manifold, 1 241 incoherentes) | 0 sólidos, 34 s | **5 sólidos, 17 s** |
| 150 000 △ | 359 s | **92 s** (simplificada; volumen −0,009 %) |
| 400 000 △ | **fallido** | **correcto en 123 s**, 1,96 GB (simplificada; volumen −0,009 %) |
| Denso sin simplificar por encima de los recursos | — | fallo **explicado**: memoria, tiempo y tamaño estimados, y etapa |
| Fallo nativo real (violación de acceso simulada) | «terminó inesperadamente» | etapa exacta, código de salida, pila faulthandler, análisis conservado |
| STL → OBJ / GLB (comparación) | — | mismas dimensiones que STL → STEP |
| STEP generado → reapertura | — | sólidos, validez `BRepCheck` y caja envolvente verificados |

Batería completa: ver `docs/resultados_pruebas.txt` (incluye `tests/test_stl_to_step.py`).

## 5. Limitaciones que permanecen
* **No se reconstruye CAD paramétrico.** El STEP es un B-Rep facetado; las caras coplanares se unen, pero las
  superficies curvas siguen formadas por triángulos.
* **Coste intrínseco del STEP facetado**: unos 2,5 KB de archivo y 13 KB de memoria por triángulo. Por eso, por
  defecto, se simplifica por encima de 100 000 triángulos y el límite automático depende de la memoria libre.
* **Las mallas no manifold** (por ejemplo, dos cuerpos que se tocan en una arista) se exportan como superficie, no
  como sólido. Separarlas automáticamente requeriría reconstrucción topológica no fiable.
* **No se rellenan agujeros**: una malla abierta sigue siendo una superficie abierta.
* **No se probó el archivo real del usuario**, porque no estaba disponible. Si vuelve a fallar, el registro de
  diagnóstico indicará la etapa y la causa exactas.
