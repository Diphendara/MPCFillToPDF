## Context

During Scryfall image downloads (initiated via "Web Load" mode in the GUI), the system evaluates the quality score of images using either a Pillow-based or OpenCV-based Laplacian variance calculation. Currently, these quality checks are only logged to standard logger output or stored as a generic error in `missing_cards.txt` if a card fails the threshold. Users have requested a dedicated CSV file containing the detailed quality scores for all evaluated images.

## Goals / Non-Goals

**Goals:**
- Automatically create a `downloaded_images_quality.csv` log file inside the active deck's output folder (`workdir/scryfall/<deck_name>_<deck_id>/`).
- Log every image quality check performed during the download run, including cache hits, downloaded candidates, Spanish fallback checks, and best-image scans.
- Capture: Card Name, Set, Collector Number, Relative File Path, Quality Method, Score, and Status (e.g. `Cached`, `Accepted`, `Rejected (Below Threshold)`).

**Non-Goals:**
- Logging quality evaluations of non-Scryfall modes (e.g., standard MPCFill Google Drive mode).
- Storing high-resolution/cached evaluations across different deck folders in a centralized log database.

## Decisions

### 1. Logging Mechanism and File Access
- **Choice**: Direct CSV writing in the Scryfall downloader functions.
- **Rationale**: Since the Scryfall downloader (`download_deck_images`) runs card-by-card in a single background thread, direct file appends are thread-safe and avoid complex logging setups.
- **Alternatives Considered**: Extending Python's `logging` module with a custom handler. This was rejected because parsing a standard text log file into structured data is brittle compared to a dedicated CSV writer.

### 2. Backward Compatibility for Functions
- **Choice**: Add default-valued parameters (`threshold` and `log_eval`) to `get_cached_card` and `download_card_from_scryfall_object`.
- **Rationale**: Prevents breaking existing unit tests and keeps function signatures clean.
- **Alternatives Considered**: Creating new separate functions or wrapping existing calls. Rejected due to unnecessary code duplication.

## Risks / Trade-offs

- **[Risk]** Writing to the CSV log could fail if the output folder is locked or permission is denied.
  - *Mitigation*: Wrap CSV append operations in a try-except block, log errors via the standard logger, and do not crash the downloader thread.
- **[Risk]** Redundant log entries if best-print evaluations copy files multiple times.
  - *Mitigation*: Introduce `log_eval=False` in the final retrieval copy of the chosen best print.
