## ADDED Requirements

### Requirement: Default cardback selection
The first image added to the "Traseras" list in the "Imágenes locales (opcional)" pane SHALL act as the default cardback for all single-faced cards in the loaded Moxfield deck. 
- If the "Traseras" list is empty, generating a PDF with backs SHALL be disabled and show a validation error.
- If generating a fronts-only PDF, no default cardback is required, and the process SHALL proceed using a placeholder internally.

#### Scenario: Generate PDF with backs and valid default cardback
- **WHEN** the user has loaded a Moxfield deck and downloaded its images
- **AND** the user has added at least one image in the "Traseras" list
- **AND** the user clicks "Generar PDF con traseras"
- **THEN** the system generates the PDF using the first image in the "Traseras" list as the default cardback for all single-faced cards.

#### Scenario: Generate PDF with backs but no default cardback
- **WHEN** the user has loaded a Moxfield deck and downloaded its images
- **AND** the "Traseras" list is empty
- **AND** the user clicks "Generar PDF con traseras"
- **THEN** the system stops the execution and displays a message box requiring the user to add a cardback in the "Traseras" list.

#### Scenario: Generate fronts-only PDF without default cardback
- **WHEN** the user has loaded a Moxfield deck and downloaded its images
- **AND** the "Traseras" list is empty
- **AND** the user clicks "Generar PDF solo frontales"
- **THEN** the system generates the PDF containing only the front faces, bypassing the cardback validation.

### Requirement: Card back pairing logic
For Moxfield deck PDF generation, the system SHALL pair card fronts and backs according to the following logic:
- Single-faced cards SHALL use the default cardback image.
- Double-faced cards (DFCs) SHALL use their corresponding Scryfall back face image (`_back.png`) downloaded during the deck download phase.

#### Scenario: Double-faced card back pairing
- **WHEN** the system generates a PDF with backs for a Moxfield deck
- **AND** the deck contains a double-faced card (e.g. Delver of Secrets)
- **THEN** that card's front page is paired with its downloaded back face image in the output PDF.

#### Scenario: Single-faced card back pairing
- **WHEN** the system generates a PDF with backs for a Moxfield deck
- **AND** the deck contains a single-faced card (e.g. Lightning Bolt)
- **THEN** that card's front page is paired with the default cardback in the output PDF.

### Requirement: Combining Moxfield and local images
The PDF generator SHALL allow merging the Moxfield deck with manually selected local cards. Any images added to the "Frontales" list in the "Imágenes locales (opcional)" pane SHALL be appended after the Moxfield deck cards in the output PDF, maintaining their custom back pairings.

#### Scenario: Merge Moxfield deck with custom local cards
- **WHEN** the user has loaded a Moxfield deck
- **AND** the user has added local front and back images in the optional local images pane
- **AND** the user generates the PDF
- **THEN** the output PDF includes all Moxfield deck cards first, followed by the custom local cards.

### Requirement: Scryfall image crop settings
The system SHALL not crop downloaded Scryfall images by default during PDF generation, since Scryfall images do not have bleed borders. Manual local images SHALL respect their own individual "Recortar bordes extra" checkbox settings.

#### Scenario: Image cropping defaults
- **WHEN** the system processes a Moxfield deck for PDF generation
- **THEN** it sets `crop_borders = False` for all Scryfall card images
- **AND** it uses the user-specified checkbox values for any local front/back images.
