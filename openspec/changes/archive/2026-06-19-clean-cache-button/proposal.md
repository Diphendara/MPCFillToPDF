## Why

The application generates significant cache and temporary files over time, including downloaded raw images, cropped/processed cards, and Scryfall API caches, which can consume substantial disk space. Currently, there is no manual way to clean up these cache folders from the user interface without manually navigating to the `workdir` directory on disk.

## What Changes

- Add a "Limpiar Caché" (Clean Cache) button to the Web Load window to allow users to manually clear cache and download files.
- Introduce a selection dialog when clicking the button, letting the user choose which parts of the cache to delete via checkboxes (Moxfield/Scryfall deck downloads, global Scryfall image cache, or MPCFill raw/cropped images).
- Display a confirmation prompt before performing the deletion, and a success message box upon completion.

## Capabilities

### New Capabilities
<!-- Capabilities being introduced. Replace <name> with kebab-case identifier (e.g., user-auth, data-export, api-rate-limiting). Each creates specs/<name>/spec.md -->

### Modified Capabilities
<!-- Existing capabilities whose REQUIREMENTS are changing (not just implementation).
     Only list here if spec-level behavior changes. Each needs a delta spec file.
     Use existing spec names from openspec/specs/. Leave empty if no requirement changes. -->
- `web-load-window`: Add a "Limpiar Caché" button in the bottom pane, which displays a dialog allowing users to selectively clean up specific cache folders with confirmation.

## Impact

- `gui/main.py`: Modify `WebLoadApp` layout and add a new modal dialog helper.
- `gui/paths.py`: Ensure safe resolution of work directories during clean-up.
