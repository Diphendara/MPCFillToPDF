## Context

The Scryfall downloader runs asynchronously to fetch images based on Moxfield deck listings. When card downloads fail, they are reported as failed, but the reasons (e.g. connection timeout, quality threshold mismatch, or missing image metadata on Scryfall) are lost. This design updates the return signatures of internal download helpers to bubble up specific failure reasons, writes them to `missing_cards.txt`, and adds intensive integration tests leveraging the Moxfield deck in `env.py`.

## Goals / Non-Goals

**Goals:**
- Bubbling up specific failure reasons (e.g. connection issues, HTTP status errors, missing API data, or image quality below the threshold) from HTTP requests and quality checks.
- Logging these detailed reasons at warning/error levels.
- Listing these detailed reasons in the generated `missing_cards.txt`.
- Implementing intensive testing for Scryfall functionality, including mock-based unit tests and a live/mocked integration test suite that utilizes the deck URL specified in `env.py`.

**Non-Goals:**
- Changing the layout of the GUI downloader (only the output text files and logs are updated).
- Modifying non-Scryfall downloading features (e.g. Google Drive downloader is unaffected).

## Decisions

### 1. Refactor Helper Return Signatures

To bubble up failure reasons, we will change key function signatures:
- `download_image_file`: Keep returning `bool` but log specific connection/HTTP exceptions.
- `download_card_from_scryfall_object`: Change return signature from `tuple[bool, float, bool]` to `tuple[bool, float, bool, str]`, where the fourth element is `reason`.
- `process_exact_edition` and `process_best_image`: Ensure they collect and return specific failure reasons (e.g., if multiple prints were tried, combine their reasons, or return the primary reason).

### 2. Live and Mocked Intensive Integration Tests

We will create a new test file `tests/test_scryfall_integration.py`. This test suite will:
- Read `env.py` to get `TESTDECK`.
- Support mock-based execution (default) and live network-based execution (when run with a specific environment variable or flag).
- Test all Scryfall download features: exact edition, best image, Spanish priority, double-faced cards, caching, and rate limiting.

## Risks / Trade-offs

- [Risk] Live integration tests might hit rate limits or require network connectivity.
- [Mitigation] Make the live network tests optional (only execute live calls if an environment variable `LIVE_INTEGRATION_TESTS` is set to `1` or if the test is run directly, otherwise use high-fidelity mocks).
