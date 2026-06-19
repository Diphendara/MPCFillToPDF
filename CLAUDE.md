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
- Run `python -m gui.main` to launch the Tkinter window.
- The user picks XML(s) via a file dialog, optionally toggles "Conservar caché", and clicks **Generar PDF(s)**.
- The pipeline runs in a worker thread; UI updates via a `queue.Queue` drained from the Tk loop.
- When done, the output folder opens automatically (`os.startfile` on Windows).
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

---

## Development style

### Language and Python version
- Python 3.10+. Use built-in generics (`list[Path]`, `dict[str, str]`, `X | None`) — never import `List`, `Dict`, `Optional` from `typing`.
- User-facing strings (UI labels, error messages, warnings) in **Spanish**. Code identifiers, log messages, and docstrings in **English**.

### Types and data structures
- Use `@dataclass` for any structured return value with more than ~3 fields. Use a plain tuple for simpler multi-value returns; annotate the return type explicitly.
- Use `Path` everywhere internally; convert `str | Path` inputs at function entry with `Path(x)`.
- Use `frozenset` for immutable constant sets (e.g., `SUPPORTED_IMAGE_EXTS`).
- Use `class Stage(str, Enum)` for typed string constants that must compare equal to raw strings (allows dict lookups with either key type).
- Use `field(default_factory=list)` for mutable defaults in dataclasses — never bare `[]`.

### Naming conventions
- Module-level constants: `SCREAMING_SNAKE_CASE`.
- Private module helpers and private instance attributes: `_underscore_prefix`.
- Dict variables: `key_to_value` pattern (e.g., `id_to_path`, `slot_to_id`, `xml_needed_ids`).
- Parallel lists: name them consistently (`local_fronts` / `local_front_crop` — same index = same card).

### Module and function design
- One concern per function. Build-functions (`_build_*`) only compute and return; they do not download, write files, or have side effects.
- Extract any loop that appears in two places into a shared private helper immediately. Do not tolerate ~20-line duplications.
- Place shared constants in `src/constants.py`. Do not re-define a constant in a consuming module.
- Place logic that belongs to a data model inside that model (e.g., `CardOrder.back_for_slot`, `CardOrder.all_drive_ids`) rather than reimplementing it in callers.

### Concurrency and cancellation
- All worker functions that can take time accept `cancel_event: Event | None` and call `_check_cancel(cancel_event)` at safe checkpoints.
- Use `ThreadPoolExecutor` + `as_completed` for parallel I/O (download, crop). Do not use `map` when you need per-item error handling or cancellation.
- GUI ↔ worker communication goes through `queue.Queue`; the Tk loop drains it with `after()`. Never call Tk methods from the worker thread.

### Error handling
- Define a custom exception class (`DownloadPermissionError`, `Cancelled`, etc.) for each distinct failure mode that callers need to handle differently.
- For user-visible errors (missing file, bad XML, permission denied), raise `ValueError` with a clear Spanish message. Catch and translate at the CLI/GUI boundary.
- Do not catch broad `Exception` in production code except at top-level handlers (CLI `main`, GUI worker wrapper) and optional-dependency guards (e.g., `plyer`).

### Comments and docstrings
- No comments that explain *what* the code does — identifiers do that.
- Add a one-line docstring only when the return value or non-obvious contract needs stating (e.g., `"""Return (drive_id, raw_path, bled_path, crop_borders) for each image."""`).
- Add an inline comment only for *why*: a hidden constraint, a workaround, or a number that comes from an external spec (e.g., `# matches mpc-autofill behaviour`).

### Testing
- Test files live in `tests/`. Shared helpers and fixtures go in `tests/conftest.py`.
- Use real tiny Pillow images for crop and PDF tests — do not mock the image pipeline.
- Mock only at module boundaries (`patch("src.pipeline.download_all")`), never inside `src/`.
- Use `tmp_path` (pytest built-in) for all temporary files.
- Group related tests in a class named `TestFeatureName`; keep each test focused on one behaviour.
- Run `python -m pytest tests/ --ignore=tests/test_downloader.py` to run the suite without network-dependent tests. All 170 tests must pass before committing.
