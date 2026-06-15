## Context

The application currently supports loading MPCFill XML projects. In a previous change, a placeholder dialog for "Carga desde web" was introduced but without any backend loading logic. This design specifies how we will process Moxfield URLs, download deck information via Moxfield's unofficial API, and display the imported card list in a new scrollable text area on the main window.

## Goals / Non-Goals

**Goals:**
- Identify Moxfield URLs entered in the web import dialog.
- Download the deck JSON using requests.
- Parse the deck's mainboard, commanders, sideboard, and tokens.
- Add a scrollable text area (`tk.Text` with scrollbar) to the main window to display the card list.
- Keep the import functionality modular and isolated in new files/libraries.

**Non-Goals:**
- Downloading card images from Scryfall or generating PDFs from the Moxfield deck list in this iteration (this is a display/import phase).

## Decisions

### 1. New Module for Moxfield API (`src/moxfield.py`)
- **Rationale**: To maintain modularity and keep the core GUI clean, all URL parsing, regex deck ID extraction, and API calls to `api.moxfield.com` will reside in a new module: `src/moxfield.py`.
- **Alternatives considered**: Putting the logic directly inside `gui/main.py` (rejected as it violates separation of concerns).

### 2. Main Window UI Layout modification
- **Decision**: Divide the left column of the main window into two rows:
  - Row 0: Existing "Archivos XML" list pane.
  - Row 1: New "Cartas Importadas" pane containing a read-only `tk.Text` widget and scrollbar.
- **Rationale**: This preserves the clean two-column layout without cluttering other sections.

## Risks / Trade-offs

- **[Risk] Unofficial API break** → Moxfield's internal API `https://api.moxfield.com/v2/decks/all/{deck_id}` is undocumented and subject to change.
  - *Mitigation*: Gracefully handle HTTP errors and JSON decoding exceptions, and alert the user with a descriptive error dialog if the fetch fails.
