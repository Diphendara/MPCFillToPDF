# MPCFillToPDF

Automated pipeline that converts an MPCFill XML project file into a print-ready PDF for a local print shop.

## What it does

1. Parses an MPCFill XML file to extract card front/back assignments and Google Drive image IDs
2. Downloads images from Google Drive
3. Crops images (removes MPC bleed border: 4.2% width + 3.1% height per side)
4. Generates a duplex-ready PDF with fronts on page 1 and mirrored backs on page 2

## XML structure (MPCFill format)

- `<fronts>` and `<backs>` contain `<card>` entries with `<id>` (Google Drive file ID), `<slots>`, `<name>`, `<query>`
- Slot numbers pair fronts with backs (same slot number = same physical card)
- `<cardback>` is the default back for all slots not listed in `<backs>`
- Cards without a specific entry in `<backs>` use the default cardback

## PDF layout

- Paper: A4 portrait
- Grid: 3 columns × 3 rows = 9 cards per page
- Cards are evenly spaced; crop marks appear in the page margins (not between cards)
- Page 1: front faces in slot order (slots 0–8, left to right, top to bottom)
- Page 2: backs horizontally mirrored so duplex printing aligns correctly
  - Mirroring means slot positions: [2,1,0 / 5,4,3 / 8,7,6] on back page
  - Each slot uses its specific back if defined in `<backs>`, otherwise uses `<cardback>`

## Tech stack

- **Language**: Python 3.10+
- **XML parsing**: `xml.etree.ElementTree` (stdlib)
- **Image download**: `requests` (with Google Drive large-file redirect handling)
- **Image processing**: `Pillow`
- **PDF generation**: `reportlab`

## Interfaces

The project targets three delivery modes, built in this order:

1. **CLI** — accepts XML path, outputs PDF path; basis for the other interfaces ✅ v1
2. **Desktop GUI** — file picker + progress display; for end users on Windows/Mac/Linux ✅ v2 (Tkinter, packaged with PyInstaller)

## Project structure

```
MPCFillToPDF/
├── src/
│   ├── parser.py          # XML parsing → structured card data
│   ├── downloader.py      # Google Drive image download
│   ├── cropper.py         # Bleed removal (Pillow)
│   ├── pdf_generator.py   # PDF layout + chunking (reportlab)
│   ├── moxfield.py        # Moxfield deck downloader & parser
│   ├── scryfall.py        # Scryfall deck image downloader placeholder
│   └── pipeline.py        # Orchestrates the full flow
├── cli/
│   └── main.py            # CLI: batch-processes xml/*.xml into out/
├── gui/
│   ├── main.py            # Tkinter GUI entry point
│   └── paths.py           # Resolves out/ and workdir/ next to the .exe when frozen
├── build_exe.py           # PyInstaller build script (produces dist/MPCFillToPDF.exe)
├── xml/                   # Drop .xml inputs here (CLI mode)
├── out/                   # Generated PDFs (gitignored)
├── workdir/               # Cached downloads + intermediate images (gitignored)
├── examples/
│   ├── example.xml        # Reference MPCFill project file
│   ├── example.pdf        # Target PDF output (reference)
│   └── imgsPdf/           # Screenshots of the reference PDF layout
└── tests/
```

### CLI usage
- Run `python -m cli.main` to process every `xml/*.xml` and write its PDF(s) to `out/`.
- Output names: `out/<xml_stem>.pdf`, or `out/<xml_stem>_1.pdf`, `out/<xml_stem>_2.pdf`, … when split.

### GUI usage
- Run `python -m gui.main` to launch the Tkinter Launcher.
- The launcher lets the user choose between **MPCFill** and **Web Load** modes.
- In **MPCFill** mode: Load local XMLs, manage local images, and generate PDFs.
- In **Web Load** mode: Enter a Moxfield URL directly, download/import the deck, list it in the text pane, and manage local images.
- `gui/paths.py` resolves `out/` and `workdir/` next to `sys.executable` when frozen by PyInstaller, otherwise next to the project root.

### Packaging (V2 → .exe)
- `python build_exe.py` runs PyInstaller with `--onefile --windowed`, bundling `src/assets/` as data.
- Output: `dist/MPCFillToPDF.exe`. The .exe is portable — drop it anywhere and it creates `out/` and `workdir/` next to itself on first run.

### Size-based splitting
- Cap: each output PDF stays under 500 MB on disk (decimal MB). `MAX_PDF_BYTES` in `pdf_generator.py` is set to 480 MB so the projected estimate has a safety margin.
- The cut is taken after the next even page (back), so each chunk remains independently duplex-ready.
- Per-pair size is projected from the cropped image file sizes with per-extension multipliers: JPEG ×1.30 (kept as `/DCTDecode` with ~25% ASCII85 overhead), PNG ×2.00 (reportlab decodes PNGs and re-encodes with Flate+ASCII85, roughly doubling photographic card art). When a pair's projected new bytes would push the chunk past the cap, a new chunk starts — even if that leaves the next chunk with a single page-pair (2 pages).

## Key implementation notes

### Image download
- **Primary (API key configured):** `GET https://www.googleapis.com/drive/v3/files/{id}?alt=media&key={KEY}` via `requests`. Works for public Drive files; avoids anonymous rate limiting (HTTP 429). The key is read from `config.json` in dev and from the XOR-obfuscated `src/_bundled_key.py` module in the .exe.
- **Fallback (no API key):** `gdown.download(f"https://drive.google.com/uc?id={drive_id}", ...)` — the original behaviour; may hit rate limits on large batches.
- `src/config.py` → `get_drive_api_key()` handles resolution order (bundled → config.json → None).
- `src/_bundled_key.py` is generated by `build_exe.py` at build time and deleted afterwards; it is gitignored and never committed.
- `config.json` (gitignored) is the dev-time key store; `config.example.json` is the committed template.
- Download with 5 parallel threads (matches mpc-autofill behaviour)

### Image cropping
- Crop formula: `border_x = round(width * 0.042)`, `border_y = round(height * 0.031)`
- Crop box: `(border_x, border_y, width - border_x, height - border_y)`

### PDF layout (matches examples/example.pdf exactly)
- Paper: A4 portrait (210mm × 297mm)
- Grid: 3 columns × 3 rows = 9 cards per page
- Card trim size: 63.5mm × 88.9mm (MPC standard)
- Bleed: 1mm kept around each trim (image size is 65.5 × 90.9mm)
- Margin page-edge → trim: 5.75mm horizontal, 11.15mm vertical
- Gap between trims: 4mm horizontal and vertical (= 2mm visible white between images)
- Cut lines: thin black lines (0.5pt) extending from the page edges to the card corners and across the gaps, forming a continuous trim grid
- Page 1 fronts slot order: left→right, top→bottom (slots 0–8)
- Page 2 backs are horizontally mirrored: `col_back = 2 - col_front`, same row
  - Each slot uses its specific back if in `<backs>`, otherwise uses `<cardback>`

### Cards per page
- Always 9 (3×3); when total cards > 9 generate multiple front/back page pairs
- Last page pair may have fewer than 9 cards; empty slots left blank

### Scryfall Downloader (Web Load mode)
- Initiated from `WebLoadApp` via the "Descargar imágenes de Scryfall" button.
- Runs in a background thread to prevent UI locking.
- Reports progress events (`scryfall_download_start`, `scryfall_download_progress`, `scryfall_download_success`, `scryfall_download_error`) to update the progress bar and status labels.
- The downloader implementation resides in `src/scryfall.py` with real HTTP calls to the Scryfall API.
- **Features**:
  - **Rate Limiting**: Thread-safe lock enforcing at least 0.5s delay between HTTP requests.
  - **Quality Check**: Dual-algorithm Laplacian variance check (implemented in `src/quality.py`).
    - *Pillow method*: 8-bit unsigned integer calculations with clipping. Default threshold is 100.
    - *OpenCV method*: Float64 unclipped calculations using `opencv-python` and `numpy`. Default threshold is 300.
    - Configured via a checkbox in the GUI which dynamically updates the default threshold entry value.
  - **Caching**: Global cache in `workdir/scryfall_cache/`. Checks cache first and copies on hit; writes to cache on success.
  - **Fallback Logic**: Resolves print fallbacks when "Preferir versión en Español" is selected (exact Spanish -> alternative Spanish -> exact English -> alternative English).
  - **Best Image Mode**: Downloads and evaluates all prints for a card in the selected language, selecting the highest-scoring image that meets the threshold.
  - **Double-faced Cards (DFCs)**: Downloads both faces separately, calculates the minimum quality score of the two faces, and requires both to meet the threshold.
  - **Error Reporting**: Writes `missing_cards.txt` in the isolated deck folder (`workdir/scryfall/<deck_name>_<deck_id>/`) and displays a summary warning listing failed cards. Failure entries in the report include the specific failure reason (e.g. connection timeout, connection error, HTTP error status, or quality score below threshold) in parentheses.
  - **Quality Logging**: Writes a separate CSV file `downloaded_images_quality.csv` inside the deck folder (`workdir/scryfall/<deck_name>_<deck_id>/`) recording the detailed quality evaluation for every print image checked during execution. Columns: Card Name, Set, Collector Number, File Path (relative to the workspace root), Method (pillow/opencv), Quality Score, Status (Accepted, Rejected (Below Threshold), Cached).
  - **Cache Clearing**: Manual cache clearance using the "Limpiar Caché" button in `WebLoadApp`. Launches a modal `CleanCacheDialog` allowing the user to selectively delete the Moxfield/Scryfall deck downloads (`workdir/scryfall`), global Scryfall image cache (`workdir/scryfall_cache`), and/or MPCFill raw/cropped images (`workdir/raw` and `workdir/bled`) after showing a confirmation prompt.
  - **PDF Generation**: Triggered via "Generar PDF con traseras" or "Generar PDF solo frontales" in `WebLoadApp`.
    - **Worker Thread**: Spawns a background thread running `WebLoadApp._work` which maps deck card structures to paths and calls `pipeline.run_locals_only`.
    - **Cardback Mapping**: Maps single-faced cards to the default cardback (first image in the "Traseras" list) and DFCs automatically to their downloaded `_back.png` file.
    - **Bypass for Fronts-Only**: Bypasses cardback checks when generating fronts-only PDFs by supplying a placeholder cardback path internally.
    - **Merged Prints**: Combines Moxfield deck cards with any manual local front/back cards added by the user in the optional images pane.
    - **Selective Cropping**: Sets `crop_borders = False` for Scryfall-downloaded card images, while respecting checkbox values for manual local images in `local_crop_map`.
    - **Progress & Event Handling**: Forwards standard pipeline events (cropping, PDF generation status, and final done dialogs) from the events queue using `App._handle(ev)` inside `WebLoadApp._drain_events`.


## Testing

- Run unit and mock integration tests:
  ```bash
  .venv/bin/pytest
  ```
- Run live network integration tests using the deck from `env.py`:
  ```bash
  LIVE_INTEGRATION_TESTS=1 .venv/bin/pytest tests/test_scryfall_integration.py
  ```


