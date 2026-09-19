# Contexto del proyecto

## Propósito

MPCFillToPDF es una aplicación Python 3.10+ que convierte XML de MPCFill, imágenes locales y mazos de varios TCG en PDFs A4 listos para imprimir. Tiene una GUI Tkinter (`python -m gui.main`), una CLI para XML/imágenes (`python -m cli.main`) y builds PyInstaller multiplataforma.

## Mapa de arquitectura

```text
GUI / CLI
   ├─ entradas: XML, imágenes locales o URLs de mazos
   ├─ precheck.py: validación, conteo, acceso a Drive y Plan/PdfJob
   └─ pipeline.py: descarga → crop/bleed → pdf_generator.py
                         ├─ downloader.py / gdown / Drive API
                         ├─ scrapers y scryfall.py
                         └─ cropper.py
```

- `src/parser.py`: XML → `CardOrder`/`CardImage`, incluyendo reversos por slot.
- `src/validator.py`: warnings de estructura, slots, frontales y reversos.
- `src/precheck.py`: análisis, planificación y manifiesto de fusiones.
- `src/pipeline.py`: orquestación; entradas principales `run`, `run_merged`, `run_plan`, `run_locals_only`, `run_deck_url`.
- `src/print_batch.py`, `src/print_run.py`, `src/execution_plan.py`: lote imprimible normalizado,
  política de PDF separado y combinación de entradas sin Tkinter.
- `src/worker_events.py`: eventos tipados del worker; la GUI los recibe por `queue.Queue`.
- `src/downloader.py`: caché, Drive API/gdown, reintentos y errores tipados.
- `src/cropper.py`: recorte MPC opcional, relleno de esquinas y sangrado espejo.
- `src/pdf_generator.py`: cuadrícula A4 3×3, traseras espejadas por columnas, marcas y división por tamaño.
- `src/deck_importer.py`, `src/scryfall.py`, `src/*_scraper.py`: importación de Magic, One Piece, Riftbound, Lorcana y Yu-Gi-Oh!.
- `gui/main.py`: estado de la aplicación y trabajador en segundo plano; las pestañas son mixins en `gui/*_tab.py`.
- `build_exe.py`: generación de ejecutables y recursos temporales de PyInstaller.

## Contratos que no se deben romper

1. Una carta ocupa un slot; el valor `<quantity>` es metadato y no sustituye el conteo de `<fronts>`.
2. El orden se conserva mediante listas paralelas: frontal, reverso y `crop` comparten índice.
3. Dentro de cada XML las cartas se ordenan por nombre sin distinguir mayúsculas; los empates usan el slot original.
4. El reverso de impresión se obtiene invirtiendo las columnas de cada fila, sin reflejar la imagen.
5. Los frontales locales se añaden al último trabajo; en GUI el orden de entradas adicionales es locales, One Piece, Riftbound, Lorcana y Magic por URL.
6. La cancelación atraviesa las operaciones largas mediante `threading.Event` y `Cancelled`.
7. La GUI solo se toca desde el hilo Tkinter; el worker publica eventos en una cola y el loop los drena con `after()`.
8. Los nombres y rutas de salida se crean por ejecución (`DD_MM_YYYY_HH-MM-SS`); la caché puede conservarse explícitamente.
9. Yu-Gi-Oh! usa una rejilla A4 de 3×3 con corte 59 × 86 mm y se genera siempre separado de XML y del resto de TCG.
10. Nunca se generan, solicitan ni incorporan imágenes creadas por IA; solo se procesan imágenes
    locales, recursos incluidos o imágenes descargadas de fuentes externas compatibles.
11. Los lotes imprimibles declaran si se combinan o generan un PDF independiente y qué rejilla usan;
    la GUI no debe codificar reglas específicas de un TCG.

## Entradas y salidas

Yu-Gi-Oh! se importa desde YDKE o YGOPRODeck y se genera siempre en PDF separado; no se mezcla con XML ni con los otros TCG.

La GUI usa rutas relativas a la carpeta base de la aplicación: `procesamiento/` para caché/logs, `archivos generados/` para PDFs y `settings.json` para preferencias. La CLI recibe `--xml-dir`, `--out-dir` y `--workdir`, y crea `run.log` en la carpeta de ejecución.

Los recursos estáticos están en `resources/backs`, `icons` y `src/assets`. `config.json` y `DRIVE_API_KEY` son opcionales y no deben versionarse.

Al seleccionar XML en la GUI, el resumen se construye desde los `CardOrder` ya analizados y muestra el plan efectivo: PDFs independientes, XML fusionados, cartas adicionales que se adjuntan al último trabajo y huecos por PDF. Al iniciar la ejecución, el mismo conteo de entradas adicionales se pasa a `plan()` para que la confirmación de huecos coincida con `run_plan`.

`pdf_generator.generate()` estima primero los grupos por tamaño de imagen y después mide PDFs temporales ya renderizados. Divide de nuevo los grupos que exceden el límite real, siempre entre parejas de páginas para preservar el orden de impresión a doble cara; una pareja individual nunca se parte.

## Pruebas y calidad

La suite cubre parser, validator, precheck, pipeline, cropper, PDF, downloader, scrapers, configuración, CLI y GUI. Las pruebas de red están marcadas `network`; CI omite `tests/test_downloader.py` completo y ejecuta el resto con `-m "not network"`. Para cambios en downloader hay que ejecutar además sus tests no-red.

La CI prueba Python 3.10–3.13 en Ubuntu y ejecuta Tkinter mediante Xvfb. El workflow de build genera artefactos para Windows, macOS y Linux con Python 3.11.

## Estado observado al documentar

- El árbol de trabajo no mostraba cambios versionados pendientes.
- La ejecución de pruebas no pudo iniciarse en este entorno porque el comando `python` no está disponible en PATH; antes de concluir que hay fallos, activar `.venv` o localizar el intérprete instalado.
- La documentación existente (`README.md` y `CLAUDE.md`) es la referencia funcional detallada; este documento resume contratos para sesiones rápidas y no debe duplicar instrucciones de usuario.

## Riesgos y puntos de atención

- Los scrapers dependen de HTML/APIs externas y pueden romperse aunque las pruebas locales pasen.
- El acceso a imágenes de Google Drive depende de permisos públicos, caché y, opcionalmente, una clave API.
- El tamaño de división de PDF es una estimación basada en imágenes únicas, no un límite duro.
- Cambios en `CardOrder`, en el mapeo de slots o en `pdf_generator.py` pueden afectar simultáneamente a GUI, CLI, fusiones y doble cara.
- No borrar cachés de trabajo ni artefactos del usuario sin confirmar el objetivo exacto.

## Checklist para una sesión futura

1. Leer este archivo y `CLAUDE.md`.
2. Revisar `git status --short` y no sobrescribir cambios existentes.
3. Identificar si el cambio afecta entrada, planificación, transformación de imágenes, PDF o adaptadores.
4. Añadir/ajustar tests en `tests/` siguiendo los límites de mocking descritos en `CLAUDE.md`.
5. Ejecutar la selección de tests correspondiente y Ruff.
6. Si cambia el comportamiento visible, actualizar `README.md` y este contexto.
