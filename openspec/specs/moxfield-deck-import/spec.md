# moxfield-deck-import Specification

## Purpose
Specifies the capability to identify Moxfield URLs, fetch deck compositions from Moxfield's API, and parse them.

## Requirements

### Requirement: Moxfield URL Detection
The system SHALL identify whether a given URL belongs to Moxfield by checking if the string "moxfield" (case-insensitive) is present in the URL.

#### Scenario: Identify Moxfield URL
- **WHEN** the user submits a URL containing "moxfield.com/decks/..."
- **THEN** the system identifies the URL as a Moxfield URL.

### Requirement: Moxfield Deck Extraction and Download
The system SHALL extract the unique deck ID from the Moxfield URL using a regular expression and download the deck details in JSON format from the unofficial Moxfield API: `https://api.moxfield.com/v2/decks/all/{deck_id}`.

#### Scenario: Download Moxfield Deck
- **WHEN** the system processes a Moxfield URL with deck ID `abc-123`
- **THEN** it performs an HTTP GET request to `https://api.moxfield.com/v2/decks/all/abc-123` with a custom User-Agent.

### Requirement: Moxfield Deck Parsing
The system SHALL parse the downloaded Moxfield JSON to extract the deck's card names, quantities, and sets for the mainboard, commanders, sideboard, and tokens.

#### Scenario: Parse downloaded JSON
- **WHEN** the system receives the JSON response for a deck
- **THEN** it compiles a list of cards containing the card name, quantity, set code, and collector number.
