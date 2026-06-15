## ADDED Requirements

### Requirement: Image quality evaluation logging

The downloader SHALL create a CSV log file at `workdir/scryfall/<deck_name>_<deck_id>/downloaded_images_quality.csv` during Scryfall downloads.
For every image quality evaluation performed during the execution (including Spanish fallbacks, DFC faces, best-image scans, and cache lookups), the downloader SHALL append a row to the CSV file.
The CSV file SHALL include the following columns in order:
- `Card Name`: The sanitized name of the card.
- `Set`: The set code of the print being evaluated.
- `Collector Number`: The collector number of the print being evaluated.
- `File Path`: The path to the image file (relative to the workspace root).
- `Method`: The quality evaluation method used (`pillow` or `opencv`).
- `Quality Score`: The computed quality score as a floating-point number.
- `Status`: The outcome of the evaluation (`Accepted`, `Rejected (Below Threshold)`, or `Cached`).

#### Scenario: Log file creation and entry writing
- **WHEN** the downloader runs and evaluates card quality
- **THEN** the CSV file is created at the correct path, includes the header row, and has one row for each evaluated image with the correct fields and status.
