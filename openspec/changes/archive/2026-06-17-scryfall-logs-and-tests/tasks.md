## 1. Core Downloader Refactoring

- [x] 1.1 Refactor return values in `download_card_from_scryfall_object` to return a 4-tuple: `(success, quality, is_dfc, reason_or_error)`.
- [x] 1.2 Update `process_exact_edition` and `process_best_image` to collect specific reasons for failures and bubble them up.
- [x] 1.3 Update the main downloader loop `download_deck_images` to format and write the specific reasons of failure into `missing_cards.txt` alongside card names.
- [x] 1.4 Enhance logs in `src/scryfall.py` to print exact reason details when requests or quality checks fail.

## 2. Test Suite Expansion

- [x] 2.1 Update `tests/test_scryfall_downloader.py` to assert correct bubble up of detailed error reasons (connection/HTTP errors, quality below threshold, etc.).
- [x] 2.2 Create `tests/test_scryfall_integration.py` to run intensive tests against mocked and live endpoints (using the deck URL from `env.py`).
- [x] 2.3 Verify all tests pass by running the test runner command `.venv/bin/pytest`.

## 3. Documentation Updates

- [x] 3.1 Update `CLAUDE.md` to reflect the new test structure and error reporting features.
- [x] 3.2 Request user to commit the changes.
