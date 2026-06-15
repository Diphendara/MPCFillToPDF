## ADDED Requirements

### Requirement: Carga desde web button positioning and trigger
The system SHALL present a button labeled "Carga desde web" immediately to the right of the "Seleccionar XMLs…" button. Clicking this button SHALL open the URL input dialog.

#### Scenario: Open the load from web dialog
- **WHEN** the user clicks the "Carga desde web" button
- **THEN** the URL input dialog window opens and is focused.

### Requirement: URL entry dialog interface
The URL input dialog window SHALL display:
1. A label stating compatibility information (specifically mentioning "moxfield").
2. A text box to input or paste a URL.
3. An "Aceptar" (OK) button.
4. A "Cancelar" (Cancel) button.

#### Scenario: Dialog elements presentation
- **WHEN** the URL input dialog window opens
- **THEN** it displays the compatibility text, a text input field, and the "Aceptar" and "Cancelar" buttons.

### Requirement: Dialog cancellation
The system SHALL close the URL input dialog without making any network requests or modifying the loaded files list when the user cancels.

#### Scenario: User clicks Cancelar
- **WHEN** the user clicks the "Cancelar" button or closes the dialog window
- **THEN** the dialog closes and no files are loaded.

### Requirement: Dialog acceptance
The system SHALL close the URL input dialog when the user clicks "Aceptar" (Aceptar does not trigger downloads yet at this stage).

#### Scenario: User clicks Aceptar
- **WHEN** the user clicks the "Aceptar" button
- **THEN** the dialog closes.
