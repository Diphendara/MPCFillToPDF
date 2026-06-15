## Why

When downloading images from Scryfall, failure messages do not specify the root cause of the failure. This makes it difficult for users to diagnose if a card download failed due to network connectivity issues or because the available images did not meet the configured Laplacian variance quality threshold. Enhancing logging and adding comprehensive automated tests will make the download pipeline more transparent and reliable.

## What Changes

- Enhance the background Scryfall download process to log specific reasons for each card download failure (e.g., connection errors, missing image URLs, HTTP status errors, or failure to meet the image quality threshold).
- Update the final download report (`missing_cards.txt`) to include these specific failure reasons alongside each card name.
- Integrate the test deck specified in `env.py` into a new suite of intensive automated integration tests for the Scryfall downloader.
- Implement comprehensive unit and integration tests covering rate-limiting, double-faced cards, caching, language fallbacks, and quality checking.

## Capabilities

### Modified Capabilities

- `scryfall-downloader`: Requirements are updated to specify that detailed failure reasons must be captured, logged, and written to the `missing_cards.txt` report.

## Impact

- `src/scryfall.py`: Downloader thread and helper functions updated to return and log detailed failure reasons.
- `tests/test_scryfall_downloader.py`: Enhanced with more intensive test cases.
- New test suite `/tests/test_scryfall_integration.py` created to test the downloader against real deck endpoints (including the one from `env.py`).
