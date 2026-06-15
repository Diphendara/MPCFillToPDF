## MODIFIED Requirements

### Requirement: Web Load window layout
The Web Load workspace window SHALL have a layout similar to MPCFill, containing:
1. Left pane: A frame for Moxfield URL input field and a "Cargar" button at the top, and a scrollable text area to display the imported cards at the bottom.
2. Right pane: A frame for selecting optional local images (fronts and backs), matching the original MPCFill layout.
3. Bottom pane: A status label, a progress bar, a cache checkbox, a "Limpiar Caché" button, and placeholder generation buttons.

#### Scenario: Web Load window presentation
- **WHEN** the Web Load window opens
- **THEN** it displays the URL input section, the imported cards pane, the local images section, the status bar, the progress bar, and the "Limpiar Caché" button.

## ADDED Requirements

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
