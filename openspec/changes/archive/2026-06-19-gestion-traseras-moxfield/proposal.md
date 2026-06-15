## Why

Currently, when users load Moxfield decks, the application downloads card images from Scryfall but does not provide a way to generate the output PDF. Unlike MPCFill XML files, Moxfield deck files do not specify back images for single-faced cards. This change introduces default cardback management and enables PDF generation for Moxfield decks, allowing users to select a default cardback image from their computer and merge Moxfield cards with custom local cards.

## What Changes

- Enable the "Generar PDF con traseras" and "Generar PDF solo frontales" buttons in the Web Load (Moxfield) view once Scryfall images are downloaded.
- Re-purpose the "Traseras" list in the "Imágenes locales (opcional)" pane: the first image added to this list will automatically act as the default cardback for all single-faced Moxfield cards.
- Implement the Moxfield PDF generation pipeline:
  - Combine Moxfield cards with any manual local front/back cards added by the user.
  - Automatically pair single-faced Moxfield cards with the default cardback.
  - Automatically pair double-faced Moxfield cards (DFCs) with their downloaded Scryfall back images.
  - Apply the PDF generation process, utilizing standard Scryfall images without crop/bleed margins by default, while preserving individual crop settings for custom local images.
- Enforce validation:
  - If the user generates a PDF with backs, they must have at least one cardback in the "Traseras" list. If not, show an error dialog.
  - If generating a fronts-only PDF, do not require a cardback image (use a dummy placeholder internally to bypass pipeline checks).

## Capabilities

### New Capabilities
- `moxfield-pdf-generation`: Handles Moxfield cardback mapping, combining downloaded cards with optional local cards, and generating standard PDFs from Scryfall downloads and local selections.

### Modified Capabilities
- `web-load-window`: Add behavior requirements for enabling the generation buttons, validating default cardback presence, and handling the transition of the progress bar during PDF generation.

## Impact

- Modifies `gui/main.py` (`WebLoadApp` class) to implement the PDF generation controls, validation logic, and hook up the background pipeline execution.
- Integrates Moxfield downloads with the existing `src/pipeline.py` execution structure.
