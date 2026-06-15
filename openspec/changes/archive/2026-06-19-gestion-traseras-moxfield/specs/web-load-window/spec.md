## ADDED Requirements

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
