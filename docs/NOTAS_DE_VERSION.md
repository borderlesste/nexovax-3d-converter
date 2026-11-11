## NEXOVAX 3D Converter 1.0.3

**ES** — Actualización fiable desde versiones anteriores:
- Si había una versión instalada en el otro modo («para todos los usuarios» ↔ «solo para mí»), el instalador la desinstala antes de continuar (Windows puede pedir permiso de administrador). Antes quedaban dos copias y el acceso directo seguía abriendo la versión antigua, sin las correcciones de 1.0.1 y 1.0.2.
- La versión aparece en el título de la ventana, en la cabecera y en el registro de cada lote.

**FR** — Mise à jour fiable : le programme d'installation désinstalle une version installée dans l'autre mode (« pour tous les utilisateurs » ↔ « pour moi uniquement ») ; la version s'affiche dans le titre de la fenêtre, l'en-tête et le journal de chaque lot.

**HT** — Mizajou ki serye: enstalatè a dezenstale yon vèsyon ki te enstale nan lòt mòd la («pou tout itilizatè» ↔ «pou mwen sèlman»); vèsyon an parèt nan tit fenèt la, nan antèt la ak nan jounal chak lo.

Incluye todas las mejoras de 1.0.2 · Inclut toutes les améliorations de 1.0.2 · Gen tout amelyorasyon 1.0.2 yo.

### Instalación · Installation · Enstalasyon
1. Descargue / Téléchargez / Telechaje `NEXOVAX3DConverter-Setup.exe`.
2. Ejecútelo / Lancez-le / Lanse l (actualiza la versión anterior · met à jour la version précédente · mete vèsyon anvan an ajou).
3. Compruebe la suma / Vérifiez la somme / Verifye sòm nan: `SHA256SUMS.txt`.

Si Windows SmartScreen muestra «Windows protegió su PC», pulse *Más información → Ejecutar de todas formas* (instalador aún sin firma digital).

---

## NEXOVAX 3D Converter 1.0.2

**ES** — Conversión de mallas densas (GLB, OBJ, FBX, STL) a STEP/IGES:
- Las piezas cerradas se conservan como **sólidos** tras simplificar: cada pieza se simplifica por separado, se comprueba su cierre y, si lo pierde, se reintenta con más detalle dentro de la memoria disponible (modelo real de 1,9 M triángulos: 13 sólidos y 0 superficies, antes 5 sólidos y 5 superficies).
- Se respeta el objetivo de triángulos también por encima del 99 % de reducción.
- Diagnóstico correcto en GLB con costuras de textura (antes mostraba cientos de piezas abiertas inexistentes).
- Reparación de aletas, solapas y cuerpos que se tocan en un punto o arista.
- Análisis y reparación ≈3,5 veces más rápidos en mallas de millones de triángulos; presupuesto de memoria medido y más preciso, con aviso de cuánta memoria libre había.
- La validación muestra sólidos, superficies y caras.

**FR** — Conversion des maillages denses vers STEP/IGES : les pièces fermées restent des **solides** après simplification (simplification par pièce avec contrôle de fermeture), objectif de triangles respecté au-delà de 99 % de réduction, diagnostic correct des GLB à coutures de texture, réparation des ailettes et pièces en contact, analyse ≈3,5× plus rapide, budget mémoire mesuré, validation indiquant solides, surfaces et faces.

**HT** — Konvèsyon mayaj ki dans an STEP/IGES: moso ki fèmen yo rete **solid** apre senplifikasyon (senplifikasyon pa moso ak verifikasyon fèmti), objektif triyang respekte menm pi wo pase 99 % rediksyon, dyagnostik kòrèk pou GLB ki gen kouti tekstil, reparasyon zèl ak moso ki touche, analiz ≈3,5 fwa pi rapid, bidjè memwa mezire, verifikasyon an montre solid, sifas ak fas.

### Instalación · Installation · Enstalasyon
1. Descargue / Téléchargez / Telechaje `NEXOVAX3DConverter-Setup.exe`.
2. Ejecútelo / Lancez-le / Lanse l (actualiza la versión anterior · met à jour la version précédente · mete vèsyon anvan an ajou).
3. Compruebe la suma / Vérifiez la somme / Verifye sòm nan: `SHA256SUMS.txt`.

Si Windows SmartScreen muestra «Windows protegió su PC», pulse *Más información → Ejecutar de todas formas* (instalador aún sin firma digital).

---

## NEXOVAX 3D Converter 1.0.1

**ES** — Corrección de la conversión STL → STEP/IGES y diagnóstico de errores:
- Construcción B-Rep nativa de Open CASCADE (≈50 veces más rápida): un sólido por cada cuerpo cerrado, superficies para mallas abiertas, unión de caras coplanares.
- Reparación controlada de mallas (duplicados, degenerados, orientación) y simplificación automática de mallas densas, con desviación informada.
- Cada conversión deja un registro de diagnóstico (`%LOCALAPPDATA%\NEXOVAX3DConverter\logs`) con etapa, causa, traza, memoria y código de salida.
- El lote indica «Finalizado con errores» y separa procesados, correctos, con advertencias, fallidos y cancelados.

**FR** — Correction de la conversion STL → STEP/IGES et diagnostic des erreurs : construction B-Rep native (≈50× plus rapide), un solide par corps fermé, réparation et simplification automatique des maillages denses, journal de diagnostic détaillé par conversion, lot « Terminé avec des erreurs ».

**HT** — Koreksyon konvèsyon STL → STEP/IGES ak dyagnostik erè: konstriksyon B-Rep natif (≈50 fwa pi rapid), yon solid pou chak kò fèmen, reparasyon ak senplifikasyon otomatik mayaj ki dans, jounal dyagnostik detaye pou chak konvèsyon, lo a di « Fini ak erè ».

### Instalación · Installation · Enstalasyon
1. Descargue / Téléchargez / Telechaje `NEXOVAX3DConverter-Setup.exe`.
2. Ejecútelo / Lancez-le / Lanse l (actualiza la versión anterior · met à jour la version précédente · mete vèsyon anvan an ajou).
3. Compruebe la suma / Vérifiez la somme / Verifye sòm nan: `SHA256SUMS.txt`.

Si Windows SmartScreen muestra «Windows protegió su PC», pulse *Más información → Ejecutar de todas formas* (instalador aún sin firma digital).
