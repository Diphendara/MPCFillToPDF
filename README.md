# MPCFillToPDF

Convierte XML de MPCFill, imágenes locales y mazos importados desde webs en PDFs para imprimir: A4, 3×3 cartas por página y traseras colocadas para impresión a doble cara. También permite generar solo los frontales.

[Tutorial en la wiki](https://github.com/Diphendara/MPCFillToPDF/wiki/1-%E2%80%90-Tutorial). Para sugerencias o errores, abre una issue en el repositorio o contacta con **@diphendara** en Twitter/Bluesky.

## Instalación desde el código

Necesitas **Python 3.10 o superior** con Tkinter. Ejecuta los comandos desde la raíz del proyecto:

```sh
git clone https://github.com/Diphendara/MPCFillToPDF.git
cd MPCFillToPDF
python -m venv .venv
```

Activa el entorno en PowerShell (Windows):

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS/Linux:

```sh
source .venv/bin/activate
python -m pip install 'Pillow>=10.0,<12' 'reportlab>=4.0,<5' 'gdown>=5.0,<6' 'requests>=2.28,<3' 'plyer>=2.0,<3'
```

`requirements.txt` incluye `windnd`, usado para arrastrar archivos en Windows. En macOS/Linux se omite, como hace el workflow de empaquetado. Si tu instalación de Python no incluye Tkinter, instálalo antes de abrir la GUI. `plyer` proporciona notificaciones de escritorio cuando están disponibles.

## Interfaz gráfica

```sh
python -m gui.main
```

Puedes combinar las siguientes entradas en una ejecución:

- **Magic:** selecciona uno o varios XML de MPCFill o pulsa **Añadir desde URL** para importar un mazo. Los XML tienen vista previa y avisos de validación. Los mazos por URL permiten incluir el sideboard y elegir un reverso local; las cartas de doble cara conservan su propia trasera.
- **One Piece**, **Riftbound** y **Lorcana:** pega la URL y pulsa **Añadir**. En Riftbound puedes elegir si imprimir las runas.
- **Imágenes locales:** añade frontales y reversos, incluso varias veces la misma imagen, asigna un reverso a cada frontal y activa el recorte del borde MPC por imagen. El modo **Multiselección** permite arrastrar sobre varios frontales y aplicarles a la vez una trasera o el recorte. Se aceptan `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif` y `.tiff`.
- **Configuración:** elige la carpeta de exportación y el color, grosor (0,1–10 pt) y estilo de las líneas de corte. Las líneas completas permiten elegir si se dibujan sobre frontales, traseras o ambos. Los cambios se guardan automáticamente.

Si añades frontales locales sin ningún XML, debes añadir al menos un reverso local, incluso para generar solo frontales. El primero sirve de reverso predeterminado.

Usa **Generar PDF con traseras (Para copisteria, con espejo horizontal)** o **Generar PDF solo frontales**. El resumen muestra las cartas y los huecos previstos; pueden aparecer confirmaciones sobre líneas de corte, advertencias de XML y acceso a Drive. **Detener** solicita la cancelación; las descargas en curso pueden tardar en terminar.

**Guardar en el PC las imágenes entre ejecuciones** conserva la caché y está desactivado por defecto. Tras una ejecución correcta, si está desmarcado se eliminan las carpetas de imágenes temporales. Al finalizar se abre la carpeta de la ejecución.

### Carpetas y configuración

En la GUI, la carpeta base es la raíz del proyecto al ejecutar desde el código, o la carpeta del ejecutable al usar la versión empaquetada:

```text
<carpeta base>/MPCFillToPDF/
├── archivos generados/
│   └── DD_MM_YYYY_HH-MM-SS/  # PDFs y resumen.txt si hay fusiones
├── procesamiento/
│   ├── raw/                 # imágenes de Drive
│   ├── bled/                # imágenes procesadas para el PDF
│   ├── op_raw/
│   ├── rb_raw/
│   ├── lorcana_raw/
│   ├── scryfall/
│   └── gui.log              # al ejecutar desde código o compilar con logging
└── settings.json            # preferencias de la GUI
```

Las carpetas se crean según se necesitan. Una carpeta de exportación personalizada sustituye a `archivos generados/`; la caché y `settings.json` mantienen su ubicación. La CLI usa sus propias rutas y no lee estas preferencias.

## Webs soportadas para diferentes TCG

Estos son los importadores implementados en el código. Los mazos deben ser accesibles públicamente; cambios en las webs o sus APIs pueden afectar a la importación.

### Magic: The Gathering

| Web | Formato de URL |
| --- | --- |
| Moxfield | `https://moxfield.com/decks/ID` |
| Archidekt | `https://archidekt.com/decks/ID` |
| Deckstats | `https://deckstats.net/decks/USUARIO/MAZO` |
| TappedOut | `https://tappedout.net/mtg-decks/nombre-del-mazo/` |
| ManaBox | `https://manabox.app/decks/ID` |

Las listas se importan desde esas webs y las imágenes se obtienen de **Scryfall**, por edición y número de colección o por nombre cuando faltan esos datos. El sideboard está desactivado por defecto. Las imágenes de Scryfall se procesan sin recortar el borde MPC y pueden tener distinta calidad que las de un XML de MPCFill.

### One Piece Card Game

| Web | Formato de URL |
| --- | --- |
| onepiece.gg | `https://onepiece.gg/decks/nombre-del-mazo` |
| deckbuilder.egmanevents.com | `https://deckbuilder.egmanevents.com/?deck=CARTA:X,...` o `https://deckbuilder.egmanevents.com/d/CODIGO` |
| deckbuilder.cardkaizoku.com | `https://deckbuilder.cardkaizoku.com/?deck=2xOP01-001\|3xOP01-002\|...` |

Los líderes usan un reverso específico; el resto usa el reverso estándar de One Piece.

### Riftbound TCG

| Web | Formato de URL |
| --- | --- |
| riftbound.gg | `https://riftbound.gg/decks/nombre-del-mazo/` |
| piltoverarchive.com | `https://piltoverarchive.com/decks/view/UUID` |
| riftmana.com | `https://riftmana.com/decks/nombre-del-mazo` |
| riftbinder.com | `https://riftbinder.com/decks/ID` |
| riftdex.com | `https://riftdex.com/deck/UUID` |

Los reversos se asignan según la sección de la carta (leyenda, campo de batalla, runa o mazo).

### Lorcana

| Web | Formato de URL |
| --- | --- |
| lorcana.gg | `https://lorcana.gg/decks/nombre-del-mazo/` |
| inkdecks.com | `https://inkdecks.com/lorcana-metagame/deck-nombre-ID` |

Todas las cartas usan el reverso de Lorcana. El importador actual no admite Dreamborn.

## Google Drive: clave de API opcional

Los XML de MPCFill contienen identificadores de imágenes alojadas en Google Drive. Sin clave, el programa descarga mediante `gdown`. Para usar la API de Drive al ejecutar desde el código, copia `config.example.json` a `config.json` en la raíz y sustituye el valor de ejemplo:

```json
{
  "google_drive_api_key": "TU_CLAVE_DE_API"
}
```

Usa una clave de un proyecto con la API de Google Drive habilitada. `config.json` está excluido de Git. Reinicia la aplicación después de cambiarlo: la clave se carga al importar el módulo de descargas.

Con clave se intenta primero la API v3; ante errores reconocidos como de permisos se prueba también `gdown`. Hay reintentos ante límites de descarga y tiempos de espera, pero una clave no garantiza que todas las imágenes estén disponibles. La aplicación verifica el acceso a las imágenes de Drive que no están en caché y muestra las incidencias.

## Línea de comandos

La CLI procesa XML e imágenes locales. La importación de mazos por URL está disponible en la GUI, no como opción de la CLI.

```sh
python -m cli.main --help
python -m cli.main --xml-dir xml --out-dir out --workdir workdir
```

Crea `xml/` y coloca allí los XML, o indica otra carpeta. Cada ejecución crea `out/DD_MM_YYYY_HH-MM-SS/` con los PDFs, `run.log` y, si hay fusiones, `resumen.txt`.

Ejemplo solo con imágenes locales:

```sh
python -m cli.main --local-fronts carta1.jpg carta2.png --local-cardback reverso.jpg --locals-base-name mi_mazo --yes
```

| Opción | Comportamiento |
| --- | --- |
| `--xml-dir`, `--out-dir`, `--workdir` | Carpetas de entrada, salida y trabajo; por defecto `xml`, `out` y `workdir`. |
| `--local-fronts IMG ...` | Añade frontales al último trabajo del plan, o genera solo con imágenes si no hay XML. |
| `--local-backs IMG ...` | Reversos emparejados por orden con los frontales locales. Los que falten usan el reverso predeterminado. |
| `--local-cardback IMG` | Reverso predeterminado obligatorio cuando no hay XML. Actualmente no se aplica en la ruta con XML; usa `--local-backs` para asignar esos reversos explícitamente. |
| `--locals-base-name NAME` | Nombre base para generación sin XML; por defecto `locales`. |
| `--local-needs-crop` | Recorta el borde MPC de las imágenes locales; por defecto no se recorta. |
| `--fronts-only` | Genera solo frontales. Sigue requiriendo los datos de reversos de la entrada. |
| `--test` | Conserva `workdir/raw` y `workdir/bled` al terminar; no ejecuta pruebas. |
| `--yes`, `-y` | Continúa sin pedir confirmación por huecos o avisos de acceso a Drive. |
| `--verbose`, `-v` | Muestra logs de depuración en stderr además de escribir `run.log`. |

## Fusiones y orden de las cartas

El plan cuenta las cartas a partir de los slots de `<fronts>`, no del valor declarado en `<quantity>`:

1. Cada XML con un número de cartas múltiplo de 9 genera un trabajo separado.
2. Si hay varios XML incompletos, **siempre se fusionan**, aunque la suma siga dejando huecos. Se ordenan de mayor a menor número de cartas para la unión.
3. Si solo hay un XML incompleto, conserva su trabajo individual.
4. Los frontales adicionales se añaden al último trabajo. En la GUI se añaden en este orden: locales, One Piece, Riftbound, Lorcana y Magic por URL. Sin XML, estas entradas se combinan en un único trabajo.

Dentro de cada XML, las cartas se ordenan alfabéticamente por nombre, sin distinguir mayúsculas, y por slot original en caso de empate. Cada carta conserva el reverso asociado a su slot original. Los mazos importados en la GUI también ordenan sus cartas por nombre dentro de cada mazo; los frontales locales mantienen el orden elegido.

Los archivos se llaman `out_<nombre>.pdf`, o `out_<nombre>_1.pdf`, `out_<nombre>_2.pdf`, etc. si se dividen por tamaño. Una unión usa un nombre como `out_mazo_a_mazo_b_union.pdf`.

Cuando hay fusiones se escribe `resumen.txt` con el desglose de cartas por XML. Actualmente el manifiesto muestra el nombre base con `.pdf`, sin el prefijo `out_` ni los índices de división; tampoco desglosa las entradas adicionales.

## Formato del PDF generado

- A4 vertical: 210 × 297 mm, 3 columnas × 3 filas.
- Carta recortada: 63,5 × 88,9 mm. Sangrado en espejo de 1 mm: imagen final de 65,5 × 90,9 mm.
- El borde MPC se recorta un 4,2 % del ancho y un 3,1 % del alto por cada lado. Las imágenes locales no se recortan por defecto; las importadas desde webs tampoco. En imágenes sin recorte se aplica un relleno de esquinas para reducir artefactos antes de añadir el sangrado.
- Margen desde el borde de la página hasta el corte: 5,75 mm horizontal y 11,15 mm vertical. Separación entre cortes: 4 mm en ambos ejes.
- Frontales de izquierda a derecha y de arriba abajo. En las traseras se invierten las posiciones de las columnas de cada fila; la imagen de la carta no se refleja.
- Marcas de corte negras de 1 pt en los márgenes por defecto. En la GUI se pueden configurar líneas completas, color, grosor y aplicación sobre frontales/traseras.
- Marcas de registro en las cuatro esquinas, barra de calibración CMYK en la parte superior y numeración inferior `1`, `1B`, `2`, `2B`, etc.
- Los slots vacíos de la última página se dejan en blanco. En modo solo frontales se omiten las páginas de traseras.

En la pestaña **Configuración** puedes introducir el **tamaño máximo de PDF** en MB, hasta 2,5 GB (200 MB por defecto). El cambio se guarda al salir de la pestaña. La división usa ese umbral estimado, calculado a partir de las imágenes únicas de cada bloque: JPEG ×1,30; PNG y otros formatos ×2. No es un límite garantizado del tamaño final. Las parejas frontal/trasera no se separan, por lo que cada archivo sigue siendo apto para doble cara; una pareja individual puede superar el umbral.

## Empaquetado

Con las dependencias de la aplicación instaladas:

```sh
python -m pip install pyinstaller
python build_exe.py
```

El script empaqueta para el sistema en el que se ejecuta: `dist/MPCFillToPDF.exe` en Windows y `dist/MPCFillToPDF` en macOS/Linux. Incluye los recursos, iconos y marcas de impresión. La GUI guarda sus datos junto al ejecutable, en las rutas descritas arriba.

```sh
python build_exe.py --debug-logging
```

Esta opción habilita `procesamiento/gui.log` en la versión empaquetada; por defecto está deshabilitado. Al ejecutar desde el código, el log está habilitado.

Durante el build se busca la clave de Drive en `config.json` y, si falta, en la variable `DRIVE_API_KEY`. Se incorpora ofuscada mediante XOR. `src/_bundled_key.py` y `gui/_build_flags.py` son temporales generados por el script, excluidos de Git y eliminados al finalizar la invocación de PyInstaller.

El workflow de build se ejecuta al hacer push a `main`, construye para Windows, macOS y Linux con Python 3.11 y sube los artefactos. En Windows también compila el bootloader de PyInstaller.

## Desarrollo y pruebas

```sh
python -m pip install pytest ruff
python -m pytest tests/ --ignore=tests/test_downloader.py -m "not network" -q
python -m ruff check .
python -m ruff format --check .
```

El comando de pytest coincide con la selección usada por CI y los hooks. `pytest.ini` excluye por defecto las pruebas marcadas `network`; para incluirlas hay que indicar `-m network` o cambiar la selección. El comando anterior también excluye todo `test_downloader.py`, incluidas sus pruebas con mocks. Puedes ejecutarlas por separado con `python -m pytest tests/test_downloader.py -m "not network"`.

Los tests de integración usan imágenes pequeñas reales para recorte y generación de PDF, con las descargas simuladas. Los tests de GUI se omiten si Tkinter no puede abrir una pantalla. CI prueba Python 3.10, 3.11, 3.12 y 3.13 en Ubuntu.

Las convenciones de contribución están en [CLAUDE.md](CLAUDE.md). Ruff usa Python 3.10 como objetivo y longitud de línea 100. Hay hooks en `.pre-commit-config.yaml` y `.githooks/pre-commit`: ejecutan Ruff y pytest. `ruff_hook.py` aplica correcciones y formato a todo el proyecto y vuelve a añadir a staging los cambios de archivos ya seguidos mediante `git add -u`.

## Estructura del proyecto

```text
cli/main.py              # CLI para XML e imágenes locales
gui/main.py              # Tkinter, estado, planificación y eventos del trabajador
gui/*_tab.py             # Magic/XML, One Piece, Riftbound, Lorcana, locales y ajustes
gui/widgets.py           # Previsualizaciones, tooltips, progreso y notificaciones
gui/paths.py             # Directorios de datos de la GUI
src/parser.py            # XML → CardOrder / CardImage
src/validator.py         # Avisos sobre slots y estructura de las cartas
src/precheck.py          # Acceso a Drive, conteo, plan y manifiesto
src/pipeline.py          # run, run_merged, run_plan, run_locals_only, run_deck_url
src/downloader.py        # Drive, caché, reintentos y errores de descarga
src/deck_importer.py     # Listas de mazos de Magic
src/scryfall.py          # Imágenes de Magic y cartas de doble cara
src/*_scraper.py         # Importación, descarga y expansión de los otros TCG
src/cropper.py           # Recorte, relleno de esquinas y sangrado en espejo
src/pdf_generator.py     # Maquetación, marcas y división de PDFs
src/app_settings.py      # Persistencia de preferencias de la GUI
src/config.py            # Resolución de la clave de Drive en tiempo de ejecución
src/constants.py         # Cuadrícula, extensiones y tipos de callbacks
src/cancellation.py      # Excepción de cancelación
src/scraper_utils.py     # Recursos y generación de reversos de reserva
src/assets/              # Marcas de registro y barra de calibración
resources/backs/         # Reversos de Magic, One Piece, Riftbound y Lorcana
icons/                   # Iconos de las pestañas
tests/                   # Pruebas unitarias, de integración y de GUI
build_exe.py             # Empaquetado con PyInstaller
.github/workflows/       # Pruebas y builds multiplataforma
```
