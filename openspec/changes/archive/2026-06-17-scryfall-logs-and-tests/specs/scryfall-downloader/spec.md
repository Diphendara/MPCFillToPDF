## MODIFIED Requirements

### Requirement: Download completion reporting and error logging
If any card in the selected zones fails to download or meet the quality threshold, the downloader SHALL log the exact error reason, continue downloading the remaining cards, and at the end:
1. Display a message box listing the names of all failed cards.
2. Write a `missing_cards.txt` report listing the failed cards and their specific failure reason (e.g., connection issues, missing image URIs, HTTP status codes, or failure to meet the image quality threshold) inside the deck's output folder.

#### Scenario: Download complete with missing cards and failure reasons
- **WHEN** the download finishes and 2 cards failed (one due to a connection error, one because it failed the quality threshold)
- **THEN** a report `missing_cards.txt` is created containing each card name and its specific failure reason, and an error dialog is displayed showing their names.
