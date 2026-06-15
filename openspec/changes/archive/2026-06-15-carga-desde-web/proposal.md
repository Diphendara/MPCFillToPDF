## Why

Users currently need to manually download XML files to their local disk and then select them using "Seleccionar XMLs". This change introduces the ability to load files directly from a web URL, saving manual download steps and improving user workflow.

## What Changes

- Add a new button "Carga desde web" on the XML file pane layout, placed immediately after the "Seleccionar XMLs..." button.
- Clicking the "Carga desde web" button opens a new modal/dialog window.
- The modal displays compatibility information at the top (currently stating that "moxfield" is supported).
- The modal provides a text input field to paste the URL.
- The modal contains "Aceptar" (OK) and "Cancelar" (Cancel) buttons.
- Submitting the URL closes the dialog. (The actual logic to process, download, and load the URL will be integrated at a later stage).

## Capabilities

### New Capabilities
- `carga-desde-web`: Add the button and URL paste dialog to the UI layout.

### Modified Capabilities
<!-- None -->

## Impact

- **UI Layout (`gui/main.py`)**: Modified to place the new button and implement the URL entry dialog.
