## 1. Setup and Preparation

- [x] 1.1 Create the CSV logging helper function `log_quality_evaluation` in `src/scryfall.py`.

## 2. Core Downloader Implementation

- [x] 2.1 Update `download_deck_images` in `src/scryfall.py` to initialize the `downloaded_images_quality.csv` file with the correct headers at the start of the download process.
- [x] 2.2 Refactor `get_cached_card` to accept the optional parameters `log_eval` and log quality checks using `log_quality_evaluation` when `log_eval=True`.
- [x] 2.3 Refactor `download_card_from_scryfall_object` to accept `threshold` and `log_eval`, and log quality check evaluations using `log_quality_evaluation` when `log_eval=True`.
- [x] 2.4 Update all calls to `get_cached_card` and `download_card_from_scryfall_object` in `process_exact_edition` and `process_best_image` to pass the correct arguments, setting `log_eval=False` only when copying the final accepted print in best image mode.

## 3. Testing and Verification

- [x] 3.1 Write unit tests in `tests/test_scryfall_downloader.py` to verify that quality evaluations are logged correctly in the CSV file with the expected status (Accepted, Rejected, Cached).
- [x] 3.2 Run the Scryfall downloader test suite to verify no regressions and that the new logging feature is working correctly.

## 4. Documentation and Cleanup

- [x] 4.1 Update `CLAUDE.md` to document the new `downloaded_images_quality.csv` file, its format, and behavior.
- [x] 4.2 Commit all changes and proposal artifacts to the Git repository.
