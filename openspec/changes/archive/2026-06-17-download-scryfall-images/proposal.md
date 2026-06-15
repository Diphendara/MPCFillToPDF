## Why

El modo "Web Load" de la interfaz gráfica actualmente simula la descarga de imágenes de Scryfall. Para que el programa sea plenamente funcional, necesitamos sustituir esta simulación por un descargador real y robusto que obtenga las imágenes de las cartas de un mazo de Moxfield, evalúe su calidad y permita al usuario configurar filtros de idioma, edición exacta y calidad mínima.

## What Changes

- **Integración real con Scryfall:** Sustitución del mock simulado por llamadas reales a la API de Scryfall para descargar imágenes en formato PNG.
- **Controles adicionales en la GUI:**
  - Checkbox "Usar edición exacta del mazo" (activo por defecto).
  - Checkbox "Mejor imagen disponible" (mutuamente excluyente con el anterior).
  - Checkbox "Preferir versión en Español" (activo por defecto).
  - Caja de entrada de texto para configurar el umbral de calidad (valor inicial: 100).
  - Checkboxes para seleccionar las zonas a descargar ("Comandantes" y "Mazo Principal" activos por defecto; "Banquillo" y "Tokens/Fichas" inactivos por defecto).
- **Control de calidad automatizado (Blur check):** Evaluación del desenfoque mediante la varianza del operador Laplaciano implementado de forma eficiente con Pillow para evitar añadir OpenCV y NumPy.
- **Sistema de Caché local:** Almacenamiento y reutilización de descargas válidas en `workdir/scryfall_cache/` para optimizar ancho de banda y velocidad.
- **Reporte de descargas incompletas:** Generación de un reporte de texto (`missing_cards.txt`) y un cuadro de diálogo al finalizar la descarga detallando cualquier carta que haya fallado o no haya cumplido con el umbral de calidad mínimo.

## Capabilities

### New Capabilities
*Ninguna.*

### Modified Capabilities
- `scryfall-downloader`: La especificación actual cubre únicamente comportamientos simulados. Se modifica para definir los requisitos del descargador real, los controles excluyentes en la GUI, las estrategias de caché, el soporte para cartas de doble cara (DFCs) y el reporte final de calidad.

## Impact

- **`src/scryfall.py`**: Se implementará el bucle real de descargas con gestión de rate limit (delays), soporte a reintentos, validación de calidad y lógica de fallback (edición exacta en español -> alternativas español -> exacta inglés -> alternativas inglés).
- **`gui/main.py`**: Se expandirá la sección de controles del modo "Web Load" para añadir los nuevos checkboxes y la entrada de umbral. Se vinculará la ejecución del hilo de descarga con estos parámetros.
- **`src/pipeline.py` / `src/downloader.py`**: Se agregará la función óptima de calidad basada en Pillow y se asegurará que el sistema de almacenamiento en caché sea accesible.
- **Dependencias**: No se introducen nuevas dependencias en `requirements.txt` o `pyproject.toml`, manteniendo ligero el empaquetado final con PyInstaller.
