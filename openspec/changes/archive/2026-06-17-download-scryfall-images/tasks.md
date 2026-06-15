## 1. GUI Expansion

- [x] 1.1 Add checkboxes for download modes ("Usar edición exacta del mazo", "Mejor imagen disponible", "Preferir versión en Español") under the Moxfield URL entry in `gui/main.py` and manage their mutual exclusion.
- [x] 1.2 Add text entry field for quality threshold in the GUI next to the checkboxes with default value of `100` and configure validation.
- [x] 1.3 Add checkboxes for card zone selection ("Comandantes", "Mazo Principal", "Banquillo (Sideboard)", "Tokens / Fichas") in the GUI, setting Comandantes and Mainboard checked by default.
- [x] 1.4 Link the background downloader thread triggers in `gui/main.py` to pass all selected GUI configurations (modes, zones, and threshold) to `download_deck_images`.

## 2. Image Quality Assessment and Storage

- [x] 2.1 Implement the Pillow-based image quality evaluation function `evaluate_image_quality` in `src/downloader.py` using Laplacian variance filtering.
- [x] 2.2 Configure isolated output folders (`workdir/scryfall/<deck_name>_<deck_id>/`) and the central cache folder (`workdir/scryfall_cache/`).
- [x] 2.3 Implement the caching and image copy logic: check cache first, verify quality threshold, copy on hit, and update cache after successful HTTP downloads.

## 3. Real Downloader Core Logic

- [x] 3.1 Implement the HTTP Scryfall API download loop in `src/scryfall.py` requesting PNG format and respecting a 0.5s rate-limiting delay between requests.
- [x] 3.2 Implement double-faced card (DFC) handling: download both faces as `_front.png` and `_back.png`, calculate minimum quality score, and ensure both faces meet the threshold.
- [x] 3.3 Implement the Spanish-to-English fallback print resolution logic based on the "Preferir versión en Español" setting.
- [x] 3.4 Implement the "Mejor imagen disponible" print resolution logic: download and evaluate quality of all prints, keeping the highest-scoring image.
- [x] 3.5 Implement cancellation checks in the download loop using `cancel_event`.

## 4. Reporting and Documentation

- [x] 4.1 Implement post-download error aggregation, summary dialog display, and outputting `missing_cards.txt` inside the deck's output folder.
- [x] 4.2 Update `README.md` with descriptions of the new Scryfall downloading GUI options and configurations.
- [x] 4.3 Update `CLAUDE.md` with detailed explanations of the changes and configuration options.

## 5. Verification and Testing

- [x] 5.1 Write unit tests in `tests/test_scryfall_downloader.py` to verify the Pillow-based quality calculation, mutual exclusion behavior, caching, fallback logic, and DFC quality checks.
- [ ] 5.2 Perform manual end-to-end download verification using a sample Moxfield deck and verify the GUI behavior, cache hits, and generation of `missing_cards.txt`.
- [ ] 5.3 Commit the implemented changes to the local Git repository.
