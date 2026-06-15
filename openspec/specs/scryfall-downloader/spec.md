# scryfall-downloader Specification

## Purpose
TBD - created by archiving change download-scryfall-images. Update Purpose after archive.
## Requirements
### Requirement: Scryfall download button state
The "Descargar imágenes de Scryfall" button SHALL be enabled only when a Moxfield deck has been successfully loaded. It SHALL be disabled when there is no loaded deck or when the URL input is cleared.

#### Scenario: Enable button on successful load
- **WHEN** a Moxfield deck is successfully imported
- **THEN** the "Descargar imágenes de Scryfall" button becomes enabled.

#### Scenario: Disable button on clear
- **WHEN** the Moxfield deck is cleared or an import error occurs
- **THEN** the "Descargar imágenes de Scryfall" button becomes disabled.

### Requirement: Scryfall downloader GUI settings
The GUI SHALL display checkboxes to configure the download behavior under the URL input:
- "Usar edición exacta del mazo"
- "Preferir versión en Español"
- "Mejor imagen disponible"
The "Usar edición exacta del mazo" and "Mejor imagen disponible" checkboxes SHALL be mutually exclusive. If one is checked, the other SHALL automatically be unchecked.
The GUI SHALL also display checkboxes for card zones with "Comandantes" and "Mazo Principal" checked by default, and "Banquillo (Sideboard)" and "Tokens / Fichas" unchecked by default.
The GUI SHALL display a checkbox (labeled "Usar algoritmo OpenCV") allowing the user to select either the OpenCV/NumPy-based quality calculation method (when checked) or the Pillow-based method (when unchecked).
The GUI SHALL display a text entry to configure the quality threshold. When the quality method checkbox state changes, the quality threshold entry SHALL automatically be updated with the method's default value:
- 100 if the Pillow method is selected (checkbox unchecked).
- 300 if the OpenCV/NumPy method is selected (checkbox checked).
The entry field SHALL validate that the input is a positive integer.

#### Scenario: Mutually exclusive checkboxes
- **WHEN** the user checks "Mejor imagen disponible"
- **THEN** the "Usar edición exacta del mazo" checkbox is unchecked.

#### Scenario: Default zone selection
- **WHEN** the Moxfield deck loading tab is displayed
- **THEN** "Comandantes" and "Mazo Principal" are checked, and "Banquillo" and "Tokens / Fichas" are unchecked.

#### Scenario: Quality method toggling updates default threshold
- **WHEN** the user checks the "Usar algoritmo OpenCV" checkbox
- **THEN** the quality threshold text entry is automatically set to "300".
- **WHEN** the user unchecks the "Usar algoritmo OpenCV" checkbox
- **THEN** the quality threshold text entry is automatically set to "100".

### Requirement: Warning popup and background download execution
Clicking the "Descargar imágenes de Scryfall" button SHALL display a warning popup reminding the user that Scryfall image quality may not be optimal. If the user accepts, the image downloading process SHALL run in the background using the configured checkboxes (language, edition, zones) and quality threshold.

#### Scenario: User clicks download and accepts warning
- **WHEN** the user clicks "Descargar imágenes de Scryfall" and accepts the warning dialog
- **THEN** the download process starts in a background thread with the selected settings, the progress bar updates, and the status label displays the progress.

#### Scenario: User clicks download and cancels warning
- **WHEN** the user clicks "Descargar imágenes de Scryfall" and cancels/closes the warning dialog
- **THEN** the download process is not started.

### Requirement: Scryfall downloader progress representation
The background download task SHALL report its progress to the GUI, updating the main progress bar from 0% to 100% and displaying the current card name and download count.

#### Scenario: Downloader progress updates
- **WHEN** the background download task downloads images
- **THEN** the progress bar updates incrementally, and the status label reflects the download progress and the name of the card currently being processed.

### Requirement: Pillow-based image quality evaluation
The downloader SHALL compute a quality score for each downloaded card image using either a Pillow-based Laplacian variance check or an OpenCV/NumPy-based Laplacian variance check, depending on the method configured in the GUI.
- **Pillow method**: The image is converted to grayscale, a 3x3 Laplacian filter kernel `[0, 1, 0, 1, -4, 1, 0, 1, 0]` is applied, and the variance of pixel intensities is calculated. Due to 8-bit unsigned integer clipping in Pillow's intermediate representation, negative values are clipped to 0.
- **OpenCV/NumPy method**: The image is loaded in grayscale, the Laplacian is computed using double-precision (`cv2.CV_64F`) without clipping, and the variance of these unclipped values is calculated.
If the computed quality score is lower than the configured user threshold, the image SHALL be considered of inadequate quality.

#### Scenario: Image quality check passes
- **WHEN** the Pillow method is configured, and the image's computed Laplacian variance is 150 (greater than the threshold of 100)
- **THEN** the quality check passes and the image is accepted.
- **WHEN** the OpenCV method is configured, and the image's computed Laplacian variance is 450 (greater than the threshold of 300)
- **THEN** the quality check passes and the image is accepted.

### Requirement: Local storage and global caching
The downloader SHALL save card images for each deck in an isolated directory at `workdir/scryfall/<deck_name>_<deck_id>/` named using the format `NombreCarta_SET_CN.png` (with special characters removed/sanitized).
The downloader SHALL maintain a shared global cache directory at `workdir/scryfall_cache/`. Before downloading a card via HTTP, the downloader SHALL check if the file already exists in the global cache and passes the quality threshold. If both conditions are met, the file SHALL be copied directly to the deck folder instead of being downloaded from the network. After downloading a card that passes the quality check, a copy SHALL be saved to the global cache folder.

#### Scenario: Cache hit on download check
- **WHEN** downloading a card and its image `Sol-Ring_CMD_10.png` exists in the cache with quality 120 (above threshold 100)
- **THEN** the image is copied from cache to the deck folder and no HTTP request is made.

### Requirement: Double-faced card handling
For double-faced cards (DFCs), the downloader SHALL download both faces as separate files named `NombreCarta_SET_CN_front.png` and `NombreCarta_SET_CN_back.png`. The quality score of the card SHALL be the minimum of the quality scores of its front and back faces. Both faces MUST meet the quality threshold to be accepted.

#### Scenario: DFC quality evaluation
- **WHEN** a DFC is downloaded, and the front face quality is 110 and the back face quality is 80 (with threshold 100)
- **THEN** the card fails the quality check.

### Requirement: Spanish priority and print fallback logic
If "Preferir versión en Español" is enabled, the downloader SHALL download the specified card edition (set and collector number) in Spanish first. If its quality is below the threshold, it SHALL iterate through all other Spanish prints of the card from Scryfall. If none meet the quality threshold, it SHALL download the specified edition in English, and if that fails quality, iterate through other English prints. The downloader SHALL stop at the first print that meets the quality threshold.

#### Scenario: Fallback to other prints when exact fails quality
- **WHEN** "Preferir versión en Español" is enabled, and the exact Spanish print fails the quality threshold, but an alternative Spanish print from another set meets it
- **THEN** the alternative print image is selected and the English prints are not downloaded.

### Requirement: Rate limiting
The downloader SHALL introduce a delay of at least 0.5 seconds between HTTP requests to the Scryfall API to prevent rate limit blocks.

#### Scenario: Delay between downloads
- **WHEN** downloading consecutive card images
- **THEN** a delay of at least 0.5 seconds is executed between each request.

### Requirement: Download completion reporting and error logging
If any card in the selected zones fails to download or meet the quality threshold, the downloader SHALL log the exact error reason, continue downloading the remaining cards, and at the end:
1. Display a message box listing the names of all failed cards.
2. Write a `missing_cards.txt` report listing the failed cards and their specific failure reason (e.g., connection issues, missing image URIs, HTTP status codes, or failure to meet the image quality threshold) inside the deck's output folder.

#### Scenario: Download complete with missing cards and failure reasons
- **WHEN** the download finishes and 2 cards failed (one due to a connection error, one because it failed the quality threshold)
- **THEN** a report `missing_cards.txt` is created containing each card name and its specific failure reason, and an error dialog is displayed showing their names.

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


