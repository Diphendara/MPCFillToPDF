## ADDED Requirements

### Requirement: Main Window Card List Text Box
The main window of the application SHALL contain a scrollable text area (caja de texto) to display the imported cards when a Moxfield URL is successfully loaded.

#### Scenario: Display imported deck cards in main window text box
- **WHEN** the user successfully imports a Moxfield deck containing cards (e.g., "1 Black Lotus", "4 Lightning Bolt")
- **THEN** the main window text area is updated to show the quantity and name of each card in the deck, with one card per line.
