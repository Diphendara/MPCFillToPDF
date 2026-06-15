## ADDED Requirements

### Requirement: Web Load window layout
The Web Load workspace window SHALL have a layout similar to MPCFill, containing:
1. Left pane: A frame for Moxfield URL input field and a "Cargar" button at the top, and a scrollable text area to display the imported cards at the bottom.
2. Right pane: A frame for selecting optional local images (fronts and backs), matching the original MPCFill layout.
3. Bottom pane: A status label, a progress bar, a cache checkbox, and placeholder generation buttons.

#### Scenario: Web Load window presentation
- **WHEN** the Web Load window opens
- **THEN** it displays the URL input section, the imported cards pane, the local images section, the status bar, and progress bar.

### Requirement: Moxfield URL input and loading
The user SHALL be able to type or paste a Moxfield deck URL into the input field and click "Cargar" to download the deck.

#### Scenario: Enter and load valid Moxfield URL
- **WHEN** the user inputs a valid Moxfield URL in the input field and clicks "Cargar"
- **THEN** the system downloads the deck, parses it, and displays the card list in the imported cards text pane.

#### Scenario: Enter invalid URL
- **WHEN** the user inputs an invalid URL or unsupported domain in the input field and clicks "Cargar"
- **THEN** the system displays an error message stating that only Moxfield is supported.
