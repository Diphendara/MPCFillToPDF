## Why

Currently, users must manually download XML project files to local disk and select them to load decks into the application. Integrating the ability to load decks directly via a Moxfield URL will streamline the user workflow and provide a more integrated deck-building and previewing experience.

## What Changes

- **URL Detection**: The system will parse the URL entered in the "Carga desde web" dialog to identify it as a Moxfield URL (by checking for "moxfield" in the string).
- **Moxfield Deck Downloading & Parsing**: The system will query Moxfield's API to download the deck composition (mainboard, commanders, sideboard, tokens), parsing the JSON response into a list of cards.
- **Main Window Card Listing**: The parsed card list will be displayed in the main window. A text box (or a scrollable list view) will be introduced in the main window to show the cards.

## Capabilities

### New Capabilities
- `moxfield-deck-import`: Download and parse deck lists from Moxfield URLs.
- `main-window-card-display`: Display the list of cards in a text box on the main window.

### Modified Capabilities
<!-- None -->

## Impact

- **GUI Layout (`gui/main.py`)**: Modified to handle acceptance of Moxfield URLs, trigger background downloads, and display the resulting card list in a text component on the main window.
- **Project Structure**: Introduce new modules for Moxfield API communication and deck parsing to keep code organized and maintainable.
- **CLAUDE.md**: Updated to document the new project layout.
