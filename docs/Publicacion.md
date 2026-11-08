# Cómo publicar NEXOVAX 3D Converter para que cualquiera lo descargue

## Recomendación: GitHub (gratuito) + página de descarga

| Canal | Coste | Para qué sirve | Notas |
|---|---|---|---|
| **GitHub Releases** | Gratis (repositorio público) | Alojar `NEXOVAX3DConverter-Setup.exe` con enlace de descarga permanente | Admite archivos de hasta 2 GB (el instalador ocupa ≈140 MB). Historial de versiones y notas. |
| **GitHub Pages** | Gratis | Página web de presentación trilingüe con botón de descarga | Publicada desde `docs/index.html`: https://borderlesste.github.io/nexovax-3d-converter/ |
| **winget** (Windows Package Manager) | Gratis | Instalación con `winget install NEXOVAX.3DConverter` | Se envía un *manifest* (pull request) al repositorio `microsoft/winget-pkgs` apuntando a la URL de GitHub Releases y a su SHA-256. Hacerlo después de la primera versión estable. |
| **SourceForge** | Gratis | Réplica de descargas y estadísticas | Opcional, útil como segundo origen de descarga. |
| **Microsoft Store** | Requiere cuenta de desarrollador (consultar condiciones vigentes) | Máxima confianza para usuarios no técnicos | Acepta aplicaciones Win32 empaquetadas como EXE/MSI; exige firma digital y revisión. Paso posterior. |

### Pasos con GitHub (sin necesidad de saber Git)
1. Crear una cuenta en github.com y un repositorio **público**, por ejemplo `nexovax-3d-converter`.
2. Subir el código: botón **Add file → Upload files** y arrastrar el contenido de la carpeta del proyecto
   **excepto** `.venv/` y `build/` (ya listados en `.gitignore`). Alternativa más cómoda: *GitHub Desktop*.
3. Crear la versión: **Releases → Draft a new release**, etiqueta `v1.0.0`, pegar el texto de `docs/NOTAS_DE_VERSION.md`
   y adjuntar `build/installer/NEXOVAX3DConverter-Setup.exe` (y un `SHA256SUMS.txt`).
4. Enlace de descarga permanente para compartir:
   `https://github.com/<usuario>/nexovax-3d-converter/releases/latest/download/NEXOVAX3DConverter-Setup.exe`
5. Página web: **Settings → Pages → Deploy from a branch**, carpeta `/docs` (ya configurado).

### Automatización (escalabilidad)
El archivo `.github/workflows/release.yml` compila en los servidores de GitHub (Windows) y publica el instalador
automáticamente cuando se lanza manualmente desde la pestaña Actions indicando una etiqueta (p. ej. `v1.1.0`): ejecuta las 153 pruebas, PyInstaller, Inno Setup, calcula el
SHA-256 y adjunta todo a la versión. Así cada nueva versión se publica igual, sin depender de este equipo.
*Este flujo no se ha ejecutado todavía (requiere el repositorio en GitHub); revisar el primer resultado en la pestaña Actions.*

## Antes de publicar (pendiente del titular)
1. **Licencia del código propio: MIT** (elegida). Compatible con las bibliotecas incluidas, que se enlazan dinámicamente (LGPL),
   y válida para la firma gratuita de proyectos de código abierto (punto 3).
2. **Licencia de ufbx.** El paquete `ufbx 0.0.5` de PyPI no declara licencia en sus metadatos (la biblioteca original es
   MIT/dominio público). Confirmarlo con el autor del binding antes de una distribución comercial.
3. **Firma digital del instalador.** Sin firma, Windows SmartScreen mostrará «Windows protegió su PC» hasta que el archivo
   gane reputación, y algunos antivirus marcan por error ejecutables de PyInstaller. Opciones:
   * **SignPath Foundation** – firma gratuita para proyectos de código abierto que compilan en CI público.
   * **Certum Open Source Code Signing** – certificado de bajo coste para desarrolladores de software libre.
   * **Azure Trusted Signing** – servicio de pago mensual de Microsoft; requiere verificación de identidad y su
     disponibilidad depende del país.
   * Certificado OV/EV de una autoridad comercial.
   La firma se añade en `build.ps1` con `signtool sign` sobre los `.exe` y sobre el instalador (Inno Setup admite `SignTool=`).
4. **Marca y dominio.** Comprobar que «NEXOVAX» no está registrado por terceros en su sector y registrar el dominio si se
   desea una web propia.
5. **Revisión de idiomas.** El criollo haitiano (interfaz, manual e instalador) debe revisarlo un hablante nativo.
6. **Logotipo.** El PNG recibido mide 192×192 px; el icono de 256 px se obtiene ampliándolo. Para máxima nitidez,
   aportar el logotipo en SVG o en PNG ≥ 512 px y regenerar con `packaging\make_icon.py`.
7. **Prueba en un Windows limpio y sin red** (ver Compilacion_y_empaquetado.md).

## Añadir más idiomas (escalabilidad)
1. Copiar `u3dc/locales/fr.py` como `u3dc/locales/<código>.py` y traducir `STATIC` y `MESSAGES`.
2. Añadir el código a `LANGUAGES` en `u3dc/i18n.py`.
3. `python tools/i18n_keys.py --missing <código>` lista lo que falta; `pytest tests/test_i18n.py` verifica que todo
   mensaje real del motor quede traducido.
4. Añadir el idioma al instalador (`[Languages]` y `[CustomMessages]` en `packaging/installer.iss`) y traducir el manual.
