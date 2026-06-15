# web-load-window Specification

## Purpose
Defines the layout and behavior of the Web Load workspace window.
## Requirements
### Requirement: Web Load window layout
The Web Load workspace window SHALL have a layout similar to MPCFill, containing:
1. Left pane: A frame for Moxfield URL input field and a "Cargar" button at the top, and a scrollable text area to display the imported cards at the bottom.
2. Right pane: A frame for selecting optional local images (fronts and backs), matching the original MPCFill layout.
3. Bottom pane: A status label, a progress bar, a cache checkbox, a "Limpiar Caché" button, and placeholder generation buttons.

#### Scenario: Web Load window presentation
- **WHEN** the Web Load window opens
- **THEN** it displays the URL input section, the imported cards pane, the local images section, the status bar, the progress bar, and the "Limpiar Caché" button.

### Requirement: Moxfield URL input and loading
The user SHALL be able to type or paste a Moxfield deck URL into the input field and click "Cargar" to download the deck.

#### Scenario: Enter and load valid Moxfield URL
- **WHEN** the user inputs a valid Moxfield URL in the input field and clicks "Cargar"
- **THEN** the system downloads the deck, parses it, and displays the card list in the imported cards text pane.

#### Scenario: Enter invalid URL
- **WHEN** the user inputs an invalid URL or unsupported domain in the input field and clicks "Cargar"
- **THEN** the system displays an error message stating that only Moxfield is supported.

### Requirement: Scryfall image download option
The Web Load window bottom pane SHALL contain a button named "Descargar imágenes de Scryfall" located directly below the "Generar PDF solo frontales" button.

#### Scenario: Display Scryfall download button
- **WHEN** the Web Load window layout is displayed
- **THEN** the "Descargar imágenes de Scryfall" button is visible and initially disabled.

### Requirement: Cache cleanup option
The Web Load window SHALL provide a "Limpiar Caché" button. Clicking this button SHALL display a selection dialog showing checkboxes for three cache components:
1. Moxfield/Scryfall deck downloads (`workdir/scryfall`) - Checked by default.
2. Global Scryfall image cache (`workdir/scryfall_cache`) - Checked by default.
3. MPCFill raw downloads and cropped images (`workdir/raw` and `workdir/bled`) - Unchecked by default.
Clicking "Aceptar" in this dialog SHALL show a confirmation prompt. If confirmed, the system SHALL delete the selected folders and display a success message box.

#### Scenario: Display cache cleanup selection dialog
- **WHEN** the user clicks the "Limpiar Caché" button
- **THEN** the selection dialog is displayed with the three checkboxes and their default states, alongside "Aceptar" and "Cancelar" buttons.

#### Scenario: Cancel cache cleanup selection
- **WHEN** the user clicks "Cancelar" on the cache selection dialog
- **THEN** the dialog is closed and no folders are deleted.

#### Scenario: Cancel deletion confirmation
- **WHEN** the user clicks "Aceptar" on the selection dialog but selects "No" on the confirmation prompt
- **THEN** the prompt and dialog close, and no folders are deleted.

#### Scenario: Confirm cache cleanup deletion
- **WHEN** the user selects one or more checkboxes, clicks "Aceptar", and selects "Sí" on the confirmation prompt
- **THEN** the selected folders are deleted from disk, a success message box is displayed, and the dialog is closed.

### Requirement: PDF generation buttons state
The PDF generation buttons ("Generar PDF con traseras" and "Generar PDF solo frontales") in the Web Load window SHALL be enabled only when a Moxfield deck has been loaded and its card images have been successfully downloaded from Scryfall. They SHALL remain disabled in all other states (e.g., when no deck is loaded, during downloading, or if the deck is cleared).

#### Scenario: Buttons disabled initially
- **WHEN** the Web Load window opens
- **THEN** the "Generar PDF con traseras" and "Generar PDF solo frontales" buttons are disabled.

#### Scenario: Buttons enabled after download success
- **WHEN** the user successfully downloads a Moxfield deck's card images from Scryfall
- **THEN** the "Generar PDF con traseras" and "Generar PDF solo frontales" buttons become enabled.

#### Scenario: Buttons disabled on clear
- **WHEN** the user clicks "Vaciar" to clear the loaded Moxfield deck
- **THEN** the PDF generation buttons are disabled.

### Requirement: PDF generation execution and progress
Clicking an enabled PDF generation button SHALL trigger a background generation thread. The UI progress bar and status label SHALL update to show the current phase (cropping images and writing the PDF file). Once complete, the status label SHALL indicate success and the system SHALL open the output directory.

#### Scenario: PDF generation execution progress
- **WHEN** the user clicks "Generar PDF con traseras" or "Generar PDF solo frontales"
- **THEN** the system launches a background worker thread
- **AND** updates the status label to show the cropping and generation progress
- **AND** updates the progress bar based on completed cards.

#### Scenario: PDF generation completion
- **WHEN** the PDF generation pipeline finishes successfully
- **THEN** the progress bar reaches 100%
- **AND** the status label displays the final success message and output folder name
- **AND** the system opens the output folder in the OS file explorer.


