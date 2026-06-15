## Why

This change allows users in the Web Load (Moxfield) view to download card images directly from Scryfall. Since Moxfield decks do not contain Google Drive image IDs like MPCFill XML files, downloading images from Scryfall is required to generate card previews and prepare files for PDF generation.

## What Changes

- Add a new button "Descargar imágenes de Scryfall" directly below the "Generar PDF solo frontales" button in the Web Load UI.
- When clicked, display a warning popup reminding the user that Scryfall image quality might not be optimal for printing.
- Start a background download task for the Moxfield deck's card images using a progress bar to show download progress.
- Implement the downloader logic as an isolated module to keep MPCFill functionality completely unaffected.
- The downloader is initially a placeholder displaying simulated progress in the progress bar.

## Capabilities

### New Capabilities
- `scryfall-downloader`: Capability to download MTG card images from Scryfall for a loaded Moxfield deck, showing download progress.

### Modified Capabilities
- `web-load-window`: Adding the download button and linking it to the downloader progress bar.

## Impact

- `gui/main.py`: Updated to add the button, warning dialog, progress tracking, and event binding in the Web Load UI.
- `src/scryfall.py` (New): Isolated module containing downloader placeholder logic.
- `CLAUDE.md`: Updated to document the new Scryfall downloading capability.
