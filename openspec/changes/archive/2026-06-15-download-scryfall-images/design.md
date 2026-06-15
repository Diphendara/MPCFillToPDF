## Context

Currently, the application allows users to load Moxfield decks in the Web Load window but does not provide an automated way to download the card images. Since MPCFill downloads card images using Google Drive IDs parsed from a local XML, Moxfield decks require an alternative source—namely, the Scryfall API.

This design covers adding a "Descargar imágenes de Scryfall" button to the Web Load window, triggering an isolated background downloader thread, and updating the UI progress bar.

## Goals / Non-Goals

**Goals:**
- Add a new "Descargar imágenes de Scryfall" button directly below "Generar PDF solo frontales" in the Web Load UI.
- Show a warning popup about image quality before starting the download.
- Execute the download process asynchronously in a background thread to prevent GUI freezing.
- Report downloading progress (percentage and current card status) back to the GUI and update the progress bar.
- Isolate downloader logic completely within a new `src/scryfall.py` module to keep MPCFill functionality untouched.

**Non-Goals:**
- Actual implementation of the Scryfall API downloader—only a placeholder implementation with simulated progress is within scope for this change.
- Integration of the downloaded images into the PDF generation pipeline for Web Load.

## Decisions

### 1. UI Integration in `gui/main.py`
- We will add `self.scryfall_download_btn` in `WebLoadApp._build_ui` directly below `self.fronts_only_btn`.
- We will bind the button to a new method `_on_download_scryfall_images()`.
- The button is disabled by default, and enabled only when a Moxfield deck is successfully loaded.
- We will store the loaded `deck_data` in `WebLoadApp.deck_data` when the `moxfield_success` event is processed.

### 2. Threading and Event Queue
- The download process will run on a background thread.
- Just like the Moxfield import process, the downloader thread will post progress updates to the `self.events` queue (`queue.Queue`).
- The main thread will poll `self.events` in the existing `_drain_events` loop and handle progress updates.
- We will introduce new event kinds:
  - `scryfall_download_start`: initializes download status and sets progress bar.
  - `scryfall_download_progress`: reports progress value (percentage) and the name of the card being processed.
  - `scryfall_download_success`: resets UI state to idle and displays success message.
  - `scryfall_download_error`: resets UI state to idle and displays error dialog.

### 3. Logic Isolation in `src/scryfall.py`
- We will create `src/scryfall.py` to contain the downloader thread entry point.
- The entry point function, `download_deck_images(deck_data, event_queue, cancel_event)`, will run the download simulation and put events onto the queue.

## Risks / Trade-offs

- **Risk**: User clicks "Cargar" again or closes the window while a download is running.
- **Mitigation**: Disable UI inputs (like URL entry and load button) or cancel the running thread. The download task can check the `cancel_event` flag or we can simply disable input fields/buttons while the download is active.
