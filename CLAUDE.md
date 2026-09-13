# MPCFillToPDF

Python 3.10+ application that converts MPCFill XML, local images and imported TCG decks into print-ready A4 PDFs. It provides a Tkinter GUI and an XML/local-image CLI, with PyInstaller builds for Windows, macOS and Linux. See [README.md](README.md) for user instructions and supported URL formats.

## Architecture and entry points

| Module | Responsibility |
| --- | --- |
| `src/parser.py` | Parse XML into `CardImage` and `CardOrder`; resolve per-slot backs. |
| `src/validator.py` | Return `ValidationWarning` objects for parsing errors, absent fronts, duplicate slots and orphan backs. |
| `src/precheck.py` | Collect/check Drive IDs, count cards, create `XmlReport`, `PdfJob` and `Plan`, write `resumen.txt`. |
| `src/pipeline.py` | Coordinate slot mapping, download, crop and PDF generation. |
| `src/downloader.py` | Drive API/gdown downloads, disk cache, retries, progress and typed errors. |
| `src/deck_importer.py` | Import Magic lists into `FetchedDeck` / `DeckCard`. |
| `src/scryfall.py` | Resolve Magic images by printing or name, including double-faced cards. |
| `src/op_scraper.py`, `src/rb_scraper.py`, `src/lorcana_scraper.py` | Scrape decks, download images and expand quantities into parallel front/back lists. |
| `src/cropper.py` | Optional MPC border crop, rounded-corner fill and mirror bleed. |
| `src/pdf_generator.py` | A4 layout, printer marks, configurable cut lines and size-based splitting. |
| `src/app_settings.py` | Persist GUI export path and cut-line preferences. |
| `src/config.py` | Resolve the runtime Drive key. |
| `src/constants.py`, `src/cancellation.py`, `src/scraper_utils.py` | Shared grid/callback types, `Cancelled`, resource paths and fallback backs. |
| `gui/main.py` | `AppState`, `MtgUrlDeck`, `App`, combined-input workflow and worker events. |
| `gui/*_tab.py`, `gui/widgets.py`, `gui/paths.py` | Tab mixins, reusable UI/preview widgets and runtime paths. |
| `cli/main.py` | Batch XML/local-image interface; no deck URL command-line option. |
| `build_exe.py` | Platform-specific PyInstaller build. |

Pipeline entry points:

- `run`: one XML, with optional local fronts/backs.
- `run_merged`: concatenate multiple XMLs under a supplied base name.
- `run_plan`: build all jobs, deduplicate/download all Drive images, crop all images, then generate PDFs per job. Extra local images attach only to the last job. Supports per-XML download/crop progress and download speed callbacks.
- `run_locals_only`: generate from image paths with a required default local back; accepts cut-line settings.
- `run_deck_url`: import a Magic URL, download Scryfall images and delegate to `run_locals_only`; sideboard excluded by default.

The GUI downloads/expands web decks before calling `run_plan` or `run_locals_only`. Its extra-image order is local fronts, One Piece, Riftbound, Lorcana, then Magic URL decks. The Tk loop drains a `queue.Queue` every 80 ms; cancellation uses a `threading.Event` and `Cancelled`.

## XML, ordering and planning contracts

- `<details><quantity>` is parsed as metadata. Precheck counts actual entries in the fronts' slot lists.
- `<fronts>` and `<backs>` contain `<card>` entries with `<id>`, `<name>` and comma-separated `<slots>`. `<query>` may be present but is not consumed.
- Original slot numbers pair fronts and backs. `CardOrder.back_for_slot` uses an explicit back when present, otherwise `<cardback>`. A nonempty `<cardback>` and card IDs are required by the parser.
- `_build_slot_maps` sorts each XML's front entries by `(name.casefold(), original_slot)` and assigns new sequential slots while preserving each original back. Do not assume output follows the original XML slot order.
- `plan` keeps XMLs with counts divisible by 9 as separate jobs. Multiple incomplete XMLs are always merged, even when their sum is not divisible by 9, ordered by descending card count. A single incomplete XML stays separate. `local_count` contributes to the last job's blank count.
- The GUI sorts imported cards by name within each deck. Local fronts retain the user's order. Riftbound's expansion also sorts by name despite its section-order docstring; back selection still depends on section.
- `write_manifest` writes `resumen.txt` only for merges and removes a stale manifest otherwise. It reports XML counts and base names, currently omitting the actual PDF's `out_` prefix, split indices and extra inputs.

## Importers and backs

- Magic: Moxfield, Archidekt, Deckstats, TappedOut and ManaBox. Scryfall resolves set/collector number or exact name; normal cards use `resources/backs/mtg/back.jpg`, double-faced cards use their own second image. The GUI allows a local back for normal cards and optional sideboard inclusion.
- One Piece: onepiece.gg, deckbuilder.egmanevents.com (query/short links), deckbuilder.cardkaizoku.com. Leader and standard backs are separate.
- Riftbound: riftbound.gg, piltoverarchive.com, riftmana.com, riftbinder.com and riftdex.com. Backs depend on section; the GUI can omit runes.
- Lorcana: lorcana.gg and inkdecks.com. Shared back; no Dreamborn importer. The current deck dataclass is spelled `LocanaDeck`.
- These are implemented integrations, not a guarantee that external endpoints are currently available. Network tests are opt-in.

## Downloads, cache and cancellation

- Drive uses 5 workers. With a key it tries API v3 first; recognised permission failures fall back to gdown. Without a key it uses gdown directly.
- Runtime key order: `src._bundled_key` → project-root `config.json` → no key. The downloader loads it once at import. `DRIVE_API_KEY` is a build-time fallback, not a runtime environment lookup.
- Drive images are cached as `<drive_id><extension>`. Downloads use a temporary file and rename on completion. Existing final files are reused.
- Connect/read timeouts are 10/30 seconds; the read timeout is inactivity, not total duration. Rate-limit retries use delays of 1, 2, 4 and 8 seconds. Batch timeouts get one sequential retry after a 5-second pause; remaining permission/timeout failures become `DownloadPartialError`.
- Importing `src.downloader` patches `requests.Session.request` to supply default timeouts for gdown requests.
- Scryfall uses 5 image workers, a shared 0.1-second API request interval, in-memory metadata/name caches and disk image cache.
- Local paths use stable synthetic IDs derived from their resolved path. Crop cache reuse compares output/input modification times; `_nocrop` distinguishes local images processed without MPC cropping.
- Cancellation is cooperative. In-flight network calls, sleeps and crop work may need to finish before the executor joins; do not promise immediate cancellation.

## Image processing and PDF contract

- MPC crop per side: `round(width * 0.042)` horizontally and `round(height * 0.031)` vertically.
- Local images default to no crop; web deck images also skip MPC cropping. With cropping disabled, rounded-corner fill runs before mirror bleed.
- Trim: 63.5 × 88.9 mm. Mirror bleed: 1 mm per side; placed image: 65.5 × 90.9 mm. Keep `cropper.py` and `pdf_generator.py` dimensions consistent.
- A4 portrait, 3 columns × 3 rows. Page-edge-to-trim margins: 5.75 mm horizontal and 11.15 mm vertical. Gaps are derived from these values (4 mm per axis).
- Fronts occupy rows left to right, top to bottom. Backs reverse column positions within each row: `[2,1,0 / 5,4,3 / 8,7,6]`. The artwork itself is not mirrored. Last-page empty slots remain blank.
- Default cut lines: black `#000000`, 1 pt, `ticks` in margins. `full` spans the page. Color, width, layering and front/back application are parameters; GUI settings persist them. When overlay is enabled but disabled for a face type, that face falls back to margin ticks.
- `src/assets/` contains corner registration marks and the top calibration bar. Page labels are `1`, `1B`, `2`, `2B`, etc., placed near the bottom center and continuing across chunks.
- `fronts_only=True` omits back pages, but does not remove input back requirements or all back processing; the size estimate still includes back IDs.
- Actual names: `out_<base_name>.pdf`, or `out_<base_name>_1.pdf`, etc. for multiple chunks.
- Splitting uses projected unique-image bytes per chunk: JPEG ×1.30, PNG/other formats ×2.00. `MAX_PDF_BYTES` is 480,000,000, aiming below 500 MB; it is not a checked final-file cap. A single oversized pair is kept intact. Duplex pairs never span separate output files.

## Running and runtime paths

- GUI: `python -m gui.main`.
- CLI: `python -m cli.main --help`; defaults are `--xml-dir xml --out-dir out --workdir workdir`. The input directory is user-created, not a bundled fixture.
- CLI runs create `out/DD_MM_YYYY_HH-MM-SS/` with PDFs, `run.log` and optional `resumen.txt`. `--test` preserves raw/bled cache; `--yes` bypasses blank/access prompts; `--fronts-only` omits back pages. See README for local-image options.
- Current CLI limitation: `--local-cardback` is used for locals-only generation, but is not forwarded through the XML `run_plan` branch. Use explicit `--local-backs` there.
- GUI base directory is the repository root in source mode and the directory containing `sys.executable` when frozen. Outputs default to `<base>/MPCFillToPDF/archivos generados/DD_MM_YYYY_HH-MM-SS/`.
- GUI cache/logs live in `<base>/MPCFillToPDF/procesamiento/`; subdirectories are `raw`, `bled`, `op_raw`, `rb_raw`, `lorcana_raw` and `scryfall`. A successful run removes image caches unless the user enables “Guardar en el PC las imágenes entre ejecuciones”.
- GUI settings live in `<base>/MPCFillToPDF/settings.json`. A custom export path changes only the PDF destination. The CLI does not load GUI settings.
- `gui.log` is enabled in source mode; frozen builds require `--debug-logging`. The GUI opens the execution output directory on success.
- Without XML, the GUI requires at least one local back when local fronts are present, including fronts-only mode.

## Packaging and development tooling

- Runtime dependencies: Pillow, ReportLab, gdown, requests, windnd (Windows drag/drop) and plyer (optional notifications). Install `requirements.txt` on Windows; README has the non-Windows installation matching dependency ranges without windnd. Tkinter must be available for GUI use.
- `python build_exe.py` invokes PyInstaller with `--onefile --windowed --noupx`, bundling `src/assets/`, `icons/` and `resources/`. It builds for the current platform: `dist/MPCFillToPDF.exe` on Windows; `dist/MPCFillToPDF` on macOS/Linux.
- Build key lookup: `config.json` first, then `DRIVE_API_KEY`. It generates XOR-obfuscated `src/_bundled_key.py` and `gui/_build_flags.py`; both are gitignored and removed in the `finally` around the PyInstaller invocation. Do not commit keys or generated modules.
- `.github/workflows/build.yml` runs on pushes to `main`, builds on Windows/macOS/Ubuntu with Python 3.11, and uploads artifacts. Windows builds compile the PyInstaller bootloader from source.
- `.github/workflows/tests.yml` runs on pushes/PRs with Python 3.10–3.13 on Ubuntu. It excludes `test_downloader.py` and tests marked `network`; GUI tests skip if no display is available.
- `pytest.ini` defaults to `-m "not network"`. End-to-end tests mock downloads but use real tiny Pillow images and ReportLab PDFs, inspecting PDF bytes without another PDF dependency.
- Install development tools with `python -m pip install pytest ruff`. Read-only lint checks: `python -m ruff check .` and `python -m ruff format --check .`.
- Ruff targets Python 3.10, line length 100, rules E/F/I/UP, with E501 ignored. `.pre-commit-config.yaml` and `.githooks/pre-commit` run `ruff_hook.py` and pytest. The Ruff hook fixes/formats the whole project and runs `git add -u`, so it mutates and stages tracked changes.
- `examples/` is ignored private/local reference material and may be absent. Tests create their own fixtures. `out/`, `workdir/`, build outputs and GUI runtime data are generated, not source inputs to edit.

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
- Run `python -m pytest tests/ --ignore=tests/test_downloader.py -m "not network" -q` for the CI/hook selection. This excludes the entire downloader test module, including mocked tests; run those separately with `python -m pytest tests/test_downloader.py -m "not network"`. Require the applicable tests to pass before committing; do not assume a fixed test count.
