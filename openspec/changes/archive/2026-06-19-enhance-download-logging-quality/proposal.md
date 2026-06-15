## Why

When downloading images from Scryfall, users have no visibility into the exact quality scores computed for each print candidate. Logging this information to a dedicated CSV file inside the deck directory will allow users to review how the downloader evaluated quality (using their chosen method) and why certain prints were accepted or rejected.

## What Changes

- Create a separate CSV file `downloaded_images_quality.csv` in the deck output folder (`workdir/scryfall/<deck_name>_<deck_id>/`) during Scryfall downloads.
- Log every image quality evaluation run, tracking card details (name, set, collector number), file path, calculation method (Pillow/OpenCV), calculated quality score, and the outcome/status (e.g., Accepted, Rejected, Cached).
- Ensure this logging covers all evaluated print images, including DFC faces, fallback checks, and best-image mode scans.

## Capabilities

### New Capabilities

<!-- None -->

### Modified Capabilities

- `scryfall-downloader`: Requirements updated to include the creation and populating of a separate CSV file recording all image quality evaluations (accepted, rejected, cached) with their respective scores and methods.

## Impact

- `src/scryfall.py`: Implement the logic to create, write, and append records to the CSV file.
- `tests/test_scryfall_downloader.py`: Update tests to verify that quality evaluations are logged correctly in the CSV file.
