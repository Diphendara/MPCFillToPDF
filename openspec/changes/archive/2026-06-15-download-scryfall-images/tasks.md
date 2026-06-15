## 1. Implement Scryfall Downloader Module

- [x] 1.1 Create `src/scryfall.py` with placeholder download_deck_images function
- [x] 1.2 Write unit tests for `src/scryfall.py` in `tests/test_scryfall.py`

## 2. Implement GUI Changes

- [x] 2.1 Add "Descargar imágenes de Scryfall" button to WebLoadApp in `gui/main.py`
- [x] 2.2 Store `deck_data` in WebLoadApp upon successful Moxfield deck load
- [x] 2.3 Implement the `_on_download_scryfall_images` method to show the warning and spawn the downloader thread
- [x] 2.4 Update the event loop `_drain_events` in WebLoadApp to process Scryfall downloader progress and update UI
- [x] 2.6 Manually verify GUI download flow and progress representation
- [x] 2.7 Commit changes to the local Git repository
