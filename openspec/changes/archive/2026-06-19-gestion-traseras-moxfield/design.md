## Context

In the current codebase, the `WebLoadApp` class in `gui/main.py` provides loading and downloading of Moxfield decks, but the PDF generation methods (`_start`) are stubbed out. Because Moxfield decks do not contain cardback identifiers for single-faced cards, we need to map them to a default cardback image selected by the user while preserving automatic backs for double-faced cards (DFCs).

## Goals / Non-Goals

**Goals:**
- Implement PDF generation (both duplex with cardbacks and fronts-only) for Moxfield decks in `WebLoadApp`.
- Reuse the existing "Imágenes locales (opcional) > Traseras" list to define the default cardback.
- Support combining Moxfield decks with manually added optional front/back cards.
- Prevent cropping of Scryfall-sourced images while honoring individual crop options for manually added local images.
- Validate file existence on disk before beginning the PDF pipeline.

**Non-Goals:**
- Modifying the core rendering loop in `src/pdf_generator.py` or the execution flow in `src/pipeline.py`.
- Creating a separate UI dialog or settings pane to map custom backs to specific Moxfield cards.

## Decisions

### 1. Treating Moxfield Cards as Local Inputs in `run_locals_only`
- **Choice:** Re-use `src.pipeline.run_locals_only` instead of writing a new entry point.
- **Rationale:** Since Scryfall downloads card images to `workdir/scryfall/<deck_name>_<deck_id>/`, these files are already local on disk. We can assemble lists of paths (`extra_fronts` and `extra_backs`) for the Moxfield cards, append manual local cards if any, and invoke the existing `run_locals_only` pipeline. This avoids code duplication.

### 2. Cardback Assignment & DFC Detection
- **Choice:** Automatically map card backs using file naming conventions.
- **Rationale:** We use `src.scryfall.sanitize_filename` to reconstruct paths for each card in the deck:
  - If a card has both `_front.png` and `_back.png` in the download folder, it is identified as a DFC and paired with its own back.
  - If only `<prefix>.png` exists, it is single-faced and paired with `None` (which the pipeline resolves to the default `local_cardback`).

### 3. Validation and Fallback for Empty Cardback List
- **Choice:** Block duplex generation if no cardbacks are selected; bypass for fronts-only.
- **Rationale:** For double-sided prints, at least one cardback is required. If `self.local_backs` is empty, we show a popup and stop. For fronts-only prints, backs are never rendered, so we bypass the check by supplying the first card's front path as the default cardback to satisfy the pipeline's validator.

### 4. Selective Cropping via `local_crop_map`
- **Choice:** Build `local_crop_map` explicitly passing `False` for Scryfall paths and reading the checkbox states for manual local paths.
- **Rationale:** Scryfall images do not have bleed borders, so applying MPC bleed crops would cut off card text.

### 5. Event Forwarding in `WebLoadApp._drain_events`
- **Choice:** Add a fallback call to `self._handle(ev)` inside `WebLoadApp._drain_events` for unhandled event types.
- **Rationale:** The pipeline emits standard progress/completion events. Forwarding unhandled events to `App._handle` ensures that `WebLoadApp` correctly handles progress bar updates and showing the final dialog.

## Risks / Trade-offs

- **[Risk] Missing Files on Disk** → If the user loaded a deck, partially downloaded images, or manually modified the folder, some files might be missing.
  - *Mitigation:* Before spawning the worker thread, `WebLoadApp._start` will verify that every card in the selected zones has its required front (and back for DFCs) file on disk. If any are missing, it stops and prompts the user to run the download again.
- **[Risk] Filename Sanitization Discrepancies** → Mismatches in special characters between downloading and PDF generation mapping could lead to missing files.
  - *Mitigation:* Import and use `sanitize_filename` directly from `src/scryfall.py` to ensure identical path construction.
