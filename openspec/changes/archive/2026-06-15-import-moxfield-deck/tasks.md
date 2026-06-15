## 1. Moxfield Download & Parse Logic

- [x] 1.1 Create new module `src/moxfield.py` containing regex URL identification, deck ID extraction, and JSON downloader using requests.
- [x] 1.2 Implement parsing of mainboard, sideboard, commanders, and tokens from Moxfield JSON.
- [x] 1.3 Add comprehensive unit tests in `tests/test_moxfield.py` to cover URL detection, ID extraction, and parser logic.

## 2. GUI Integration

- [x] 2.1 Modify `gui/main.py` to divide the left column into two rows, adding a new LabelFrame "Cartas Importadas" with a scrollable read-only `tk.Text` widget.
- [x] 2.2 Update `_load_from_web_dialog` acceptance callback in `gui/main.py` to detect Moxfield URLs and trigger background importing.
- [x] 2.3 Implement background download worker in GUI to fetch the deck, populate the "Cartas Importadas" text box, and display status messages.
- [x] 2.4 Add manual integration tests to verify the UI updates correctly on successful import and displays errors on invalid/failed imports.

## 3. Documentation & Commit

- [x] 3.1 Update `README.md` to describe the Moxfield import functionality.
- [x] 3.2 Update `CLAUDE.md` to document the new file structure (`src/moxfield.py` and `tests/test_moxfield.py`).
- [x] 3.3 Commit the changes to the local Git repository.
