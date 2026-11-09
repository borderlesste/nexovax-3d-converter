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
