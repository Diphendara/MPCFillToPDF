# Guía rápida de cambios

Usar este documento después de leer `AGENTS.md`, `README.md`, `CLAUDE.md` y
`docs/PROJECT_CONTEXT.md`. No sustituye sus contratos: reduce el tiempo de
localización antes de editar.

## Elegir el punto de entrada

| Si el cambio trata sobre... | Empezar por | Comprobar también | Pruebas principales |
| --- | --- | --- | --- |
| XML, slots, orden o reversos | `src/parser.py`, `src/validator.py` | `src/precheck.py`, `_build_slot_maps` en `src/pipeline.py` | `test_parser.py`, `test_validator.py`, `test_precheck.py`, `test_pipeline.py` |
| Planes, fusiones, huecos o manifiesto | `src/precheck.py` | `cli/main.py`, `gui/main.py`, `src/pipeline.py` | `test_precheck.py`, `test_pipeline.py`, `test_cli.py` |
| Descarga de Drive, caché o reintentos | `src/downloader.py` | `src/config.py`, `src/pipeline.py` | `test_downloader.py`, `test_config.py`, `test_pipeline.py` |
| Recorte, esquinas o sangrado | `src/cropper.py` | `src/pipeline.py`, dimensiones de `src/pdf_generator.py` | `test_cropper.py`, `test_e2e.py`, `test_pipeline.py` |
| Rejilla, doble cara, marcas o tamaño de PDF | `src/pdf_generator.py` | `src/constants.py`, `src/cropper.py`, `src/pipeline.py` | `test_pdf_generator.py`, `test_e2e.py`, `test_pipeline.py` |
| Importación de Magic | `src/deck_importer.py`, `src/scryfall.py` | `gui/xml_tab.py`, `gui/main.py`, `src/pipeline.py` | `test_deck_importer.py`, `test_scryfall.py`, `test_gui.py` |
| One Piece, Riftbound o Lorcana | El `src/*_scraper.py` correspondiente | Su pestaña `gui/*_tab.py`, `gui/main.py` | El `test_*_scraper.py` correspondiente, `test_gui.py` |
| Entradas, diálogos o progreso de la GUI | La pestaña `gui/*_tab.py` correspondiente | `gui/main.py`, `gui/widgets.py`, `src/app_settings.py` | `test_gui.py`, `test_app_settings.py` |
| Argumentos, mensajes o limpieza de CLI | `cli/main.py` | `src/precheck.py`, `src/pipeline.py` | `test_cli.py` |
| Preferencias o rutas de ejecución | `src/app_settings.py`, `gui/paths.py` | `gui/settings_tab.py`, `gui/main.py` | `test_app_settings.py`, `test_config.py`, `test_gui.py` |
| Ejecutable o recursos empaquetados | `build_exe.py`, `MPCFillToPDF.spec` | `.github/workflows/build.yml`, `.gitignore` | Build local cuando proceda; revisar el workflow |

## Flujo y fronteras

```text
GUI (Tk, hilo principal) ─┐
                         ├─ precheck: parse/validate/analyze/plan
CLI ─────────────────────┘                 │
                                           ▼
                       pipeline: download → crop/bleed → PDF
                          │            │              │
                       Drive/Scryfall  Pillow       ReportLab
```

- La GUI prepara el plan y ejecuta trabajo lento en un hilo. Ese hilo solo
  publica eventos en `App.events`; `_drain_events` es quien actualiza Tk.
- La CLI es un adaptador: valida argumentos, confirma avisos, configura log y
  delega. No mover lógica de dominio a ella.
- Los importadores web descargan y expanden sus mazos a listas paralelas antes
  de llamar a `run_plan` o `run_locals_only`.
- `run_plan` procesa todos los trabajos por fases globales: parseo, descarga,
  recorte y generación. No cambiar ese orden sin revisar progreso, caché y
  cancelación.

## Invariantes que requieren pruebas cruzadas

| Cambio en... | Riesgo que hay que comprobar |
| --- | --- |
| `CardOrder`, `_build_slot_maps` o listas locales | Cada frontal conserva su reverso y flag de crop por índice; el orden XML es `(nombre.casefold(), slot original)`. |
| `plan` o `PdfJob` | XML completos siguen independientes; varios incompletos se fusionan ordenados por número de cartas; extras solo se añaden al último trabajo. |
| `cropper.py` o constantes de tamaño | Tamaño de imagen con sangrado y posición de corte del PDF siguen representando la misma carta física. |
| `pdf_generator.py` | Las traseras invierten columnas, no el arte; una pareja frontal/trasera no se divide entre archivos. |
| Callbacks o ejecutores | `cancel_event` se propaga y no se llama a Tk desde el worker. |
| Scrapers | La expansión mantiene cantidad, nombre, frontal, reverso y crop sincronizados; las pruebas de red siguen siendo opt-in. |

## Comandos de verificación

Primero localizar el intérprete. En Windows se prefiere el entorno del proyecto:

```powershell
$py = if (Test-Path .venv\Scripts\python.exe) { '.venv\Scripts\python.exe' } else { 'python' }
& $py -m pytest tests/ --ignore=tests/test_downloader.py -m "not network" -q
& $py -m pytest tests/test_downloader.py -m "not network" -q
& $py -m ruff check .
& $py -m ruff format --check .
```

Para un cambio acotado, ejecutar primero los ficheros indicados en la tabla y
después la verificación completa antes de entregar. Los tests GUI pueden
omitirse si el entorno no tiene pantalla; documentar ese hecho, no ocultarlo.

## Estado de referencia (12-09-2026)

- Python 3.13 está instalado en el perfil de usuario en
  `C:\Users\Cristian\AppData\Local\Programs\Python\Python313\python.exe`.
  En el entorno aislado de los agentes el comando `python` puede no resolver
  aunque esas rutas aparezcan en `PATH`; comprobar el intérprete real antes de
  concluir que no está instalado.
- Tras instalar `requirements.txt`, `pytest` y `ruff` en ese intérprete, la
  verificación mínima pasó: 463 tests en la selección principal, 20 en
  `test_downloader.py`, y Ruff sin incidencias. Repetirla tras cambios de
  código; este resultado no sustituye una ejecución futura.
- `AGENTS.md` y `docs/PROJECT_CONTEXT.md` están preparados como documentación
  local pendiente de versionar. No mezclar con cachés de `workdir/`, PDFs de
  `out/` ni configuración privada.
- La documentación se debe actualizar cuando un cambio visible altere rutas,
  importadores soportados, contratos de orden/slots o el flujo de generación.
