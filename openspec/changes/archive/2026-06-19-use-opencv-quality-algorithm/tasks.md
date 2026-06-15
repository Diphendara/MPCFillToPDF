## 1. Setup and Dependencies

- [x] 1.1 Add `opencv-python` and `numpy` to `requirements.txt` and `pyproject.toml` and sync the project dependencies.

## 2. Core Quality Module

- [x] 2.1 Create `src/quality.py` containing Pillow and OpenCV/NumPy quality evaluation algorithms.
- [x] 2.2 Refactor `evaluate_image_quality` in `src/downloader.py` to delegate to `src/quality.py`.

## 3. Downloader Integration

- [x] 3.1 Update function signatures and calls in `src/scryfall.py` (`get_cached_card`, `download_card_from_scryfall_object`, `process_exact_edition`, `process_best_image`, and `download_deck_images`) to propagate the `quality_method` parameter.

## 4. GUI Integration

- [x] 4.1 Add the "Usar algoritmo OpenCV" checkbox to the quality options frame in `gui/main.py`.
- [x] 4.2 Bind a callback to the OpenCV checkbox to dynamically update the quality threshold entry field (100 for Pillow, 300 for OpenCV).
- [x] 4.3 Update `_on_download_scryfall_images` in `gui/main.py` to pass the selected quality method to the downloader thread.

## 5. Verification, Documentation, and Git Commit

- [x] 5.1 Implement unit and integration tests in `tests/test_scryfall_downloader.py` and `tests/test_scryfall_integration.py` covering the new quality calculation methods and GUI defaults.
- [x] 5.2 Update `README.md` and `CLAUDE.md` to document the new quality method choices and dependencies.
- [x] 5.3 Commit all change implementation work to the local Git repository.
