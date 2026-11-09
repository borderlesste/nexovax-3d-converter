# Corrección GLB → STEP (malla densa) — NEXOVAX 3D Converter 1.0.2

Caso real analizado: `futuristic headset 3d model.glb` (65 MB, 1 malla de 1 930 242 triángulos con
texturas) → STEP, en un equipo con 8 GB de RAM y **716 MB libres** en el momento de convertir.

## Resultado de la versión 1.0.1 (registro de diagnóstico del usuario)

| Dato | 1.0.1 |
|---|---|
| Diagnóstico inicial | 695 componentes, «abierta», 85 830 aristas abiertas |
| Objetivo de simplificación | 11 201 triángulos (por memoria libre) |
| Triángulos obtenidos | 19 302 (no se respetó el objetivo) |
| Malla final | 10 piezas: 5 cerradas, 5 no manifold (314 aristas no manifold, 536 con orientación incoherente) |
| STEP | 5 sólidos + 5 superficies, 44 MB |
| Tiempo | 143 s (análisis 21 s, reparación 68 s, validación 35 s) |

## Causas raíz (con evidencia)

1. **Diagnóstico inicial engañoso.** El análisis se hacía sobre los vértices tal como vienen en el GLB.
   Las costuras de UV/normales duplican vértices en la misma posición (44 121 en este modelo), así que
   cada isla de textura parecía una pieza abierta: 695 «componentes» y 85 830 aristas abiertas. Soldando
   esos vértices, la malla real tiene **9 piezas** con solo 4 aristas abiertas y 3 no manifold.
2. **Objetivo de simplificación ignorado.** `simplify()` calculaba una fracción de reducción recortada al
   99 % (`np.clip(..., 0.99)`): 1 930 242 × 1 % = 19 302 triángulos, aunque el objetivo fuera 11 201.
3. **La simplificación global destruía los sólidos.** La decimación cuadrática de toda la malla al ~1 %
   aplastaba las piezas finas (cables, placas) en láminas dobles: aristas no manifold y «aletas» sin
   volumen. Por eso 5 de 10 piezas salían como superficies.
4. **Presupuesto de memoria mal calibrado.** La memoria libre se mide dentro del proceso de trabajo
   (que ya ocupa su memoria base), pero la fórmula volvía a restar 350 MB de base, y el coste por
   triángulo no distinguía la unión de caras coplanares. Medición real: +522 MB para 20 000 triángulos
   y +1 163 MB para 50 000 (≈0,025 MB/triángulo con unión de caras; ≈0,0135 MB sin ella).
5. **Lentitud.** Componentes conectados y orientación se calculaban por propagación de etiquetas
   (cientos de iteraciones) o con un recorrido en Python triángulo a triángulo, más un bucle por
   componente que recorría toda la malla cada vez.
6. **Mensaje de validación ambiguo.** «sólidos=5» no mencionaba las 5 superficies exportadas.

## Correcciones (`u3dc/engines/cad/mesh_to_brep.py`, `occt.py`, `validator.py`, `ui/main_window.py`)

- Soldadura de vértices coincidentes **antes** del análisis; el registro muestra los vértices leídos y
  los repetidos unidos.
- Reparación sin inventar geometría: elimina triángulos repetidos, **aletas** (pares espalda con
  espalda) y **solapas** colgantes de aristas no manifold; **separa vértices/aristas no manifold**
  (cuerpos que se tocan en un punto o arista pasan a ser sólidos independientes).
- Union-find vectorizado (con paridad para la orientación): componentes 29 s → 0,9 s, orientación
  163 s → 2,6 s en 1,9 M triángulos.
- `simplify()` usa `target_count`: el objetivo se respeta también por encima del 99 %.
- **Simplificación por pieza** (`simplify_by_component`): reparto con peso n^0,75, comprobación de
  cada pieza (sin aristas no manifold, cerrada si lo era, como mucho 4 cuerpos cerrados que se tocan
  en un vértice) y reintentos con otra agresividad del decimador o con más triángulos, sin superar un
  límite duro de recursos (memoria libre completa y como mucho 1,5 × el objetivo). Si aun así no es
  posible, se informa cuántas piezas salen como superficies y qué hacer.
- Presupuesto con el coste medido y sin doble cuenta de la memoria base; el motivo del límite indica
  los MB libres («cierre otras aplicaciones para conservar más detalle»).
- Validación: cuenta sólidos, **superficies** y caras; la interfaz lo muestra traducido.

## Pruebas

`tests/test_mesh_repair.py` (10 pruebas): costuras soldadas antes del análisis, orientación con 30 %
de triángulos invertidos, componentes por union-find, solapa colgante, aleta, dos cuerpos que se tocan
en una arista → 2 sólidos, objetivo respetado con reducción del 99,5 %, pieza fina que sigue cerrada
tras simplificar, presupuesto de memoria medido, recuento de superficies en la validación.

## Verificación con el archivo real (proceso aislado, igual que la interfaz)

El resultado depende de la memoria libre en el momento de convertir (el objetivo se adapta a ella).

| Memoria libre | Objetivo | Triángulos | Resultado | Tiempo |
|---|---|---|---|---|
| 716 MB (caso 1.0.1) | 11 201 → ahora 20 048 | 24 722 | 11 sólidos + 3 superficies (antes 5 + 5) | — |
| 1 004 MB | 28 118 | 39 570 | 12 sólidos, 0 superficies | — |
| 1 335 MB (CLI, `nexovax3d-cli`) | 37 376 | 52 648 | **13 sólidos, 0 superficies**, 52 648 caras, validación correcta, STEP 125 MB | 156 s, pico 1 224 MB |

Las dos primeras filas son la tubería malla → B-Rep ejecutada con el presupuesto de cada caso; la
última es la conversión completa con relectura del STEP. En 1.0.1 el análisis + reparación tardaban
89 s; ahora ≈26 s. La validación (relectura completa del STEP) es la etapa más lenta (≈60 s).

Batería completa: 175/175 pruebas correctas (2026-11-09, 272 s).
