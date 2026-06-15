## ADDED Requirements

### Requirement: Scryfall download button state
The "Descargar imágenes de Scryfall" button SHALL be enabled only when a Moxfield deck has been successfully loaded. It SHALL be disabled when there is no loaded deck or when the URL input is cleared.

#### Scenario: Enable button on successful load
- **WHEN** a Moxfield deck is successfully imported
- **THEN** the "Descargar imágenes de Scryfall" button becomes enabled.

#### Scenario: Disable button on clear
- **WHEN** the Moxfield deck is cleared or an import error occurs
- **THEN** the "Descargar imágenes de Scryfall" button becomes disabled.

### Requirement: Warning popup and background download execution
Clicking the "Descargar imágenes de Scryfall" button SHALL display a warning popup reminding the user that Scryfall image quality may not be optimal. If the user accepts, the image downloading process SHALL run in the background.

#### Scenario: User clicks download and accepts warning
- **WHEN** the user clicks "Descargar imágenes de Scryfall" and accepts the warning dialog
- **THEN** the download process starts in a background thread, the progress bar updates, and the status label displays the progress.

#### Scenario: User clicks download and cancels warning
- **WHEN** the user clicks "Descargar imágenes de Scryfall" and cancels/closes the warning dialog
- **THEN** the download process is not started.

### Requirement: Scryfall downloader progress representation
The background download task SHALL report its progress to the GUI, updating the main progress bar from 0% to 100% and displaying download status messages.

#### Scenario: Downloader progress updates
- **WHEN** the background download task downloads images
- **THEN** the progress bar updates incrementally and the status label reflects the download progress.
