"""Text-based deck importer for various TCGs.

Parses deck lists from plain text in various formats and converts them
to the same data structures used by URL-based importers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.rb_scraper import RBCard, RBDeck, _type_to_section


class TextImportError(Exception):
    """Raised when text cannot be parsed as a valid deck list."""

    def __init__(self, message: str, line_number: int | None = None) -> None:
        self.line_number = line_number
        if line_number is not None:
            message = f"Línea {line_number}: {message}"
        super().__init__(message)


@dataclass
class ParsedCardLine:
    """A single parsed line from a text deck list."""

    quantity: int
    name: str
    set_code: str
    collector_number: str
    raw_line: str
    line_number: int


# Regex for Riftbound format: "3 Sabotage (OGN-156)" or "1 Elder Dragon (UNL-118A)"
# Captures: quantity, name, set_code, collector_number
_RIFTBOUND_LINE_RE = re.compile(
    r"^(\d+)\s+(.+?)\s*\((([A-Z]+)-([0-9A-Z]+))\)\s*$",
    re.IGNORECASE
)


def parse_riftbound_text(text: str) -> list[ParsedCardLine]:
    """Parse Riftbound deck list from text.

    Expected format per line:
        3 Sabotage (OGN-156)
        1 Elder Dragon (UNL-118A)
        1 Baron Pit // Gold (UNL-T01g)

    Returns a list of ParsedCardLine objects.
    Raises TextImportError if any line is invalid.
    """
    lines: list[ParsedCardLine] = []

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        match = _RIFTBOUND_LINE_RE.match(line)
        if not match:
            raise TextImportError(
                f"Formato no reconocido: '{line}'. "
                "Formato esperado: 'Cantidad Nombre (SET-NUMERO)'",
                line_number=line_num
            )

        quantity = int(match.group(1))
        name = match.group(2).strip()
        full_code = match.group(3).upper()  # e.g., "OGN-156"
        set_code = match.group(4).upper()   # e.g., "OGN"
        collector_number = match.group(5).upper()  # e.g., "156" or "118A" or "T01g"

        if quantity < 1:
            raise TextImportError(
                f"Cantidad inválida: {quantity}. Debe ser al menos 1.",
                line_number=line_num
            )

        lines.append(
            ParsedCardLine(
                quantity=quantity,
                name=name,
                set_code=set_code,
                collector_number=collector_number,
                raw_line=raw_line,
                line_number=line_num,
            )
        )

    if not lines:
        raise TextImportError("No se encontraron cartas en el texto proporcionado.")

    return lines


def build_riftbound_deck_from_text(
    text: str,
    deck_name: str = "Imported Deck"
) -> RBDeck:
    """Build an RBDeck from pasted text.

    Parses the text and enriches each card with data from Piltover Archive API.
    Returns an RBDeck ready to be used in the GUI and PDF generation pipeline.
    """
    from src.http_client import get as http_get

    parsed_lines = parse_riftbound_text(text)

    # Build card codes for batch lookup
    card_codes = [f"{line.set_code}-{line.collector_number}" for line in parsed_lines]

    # Fetch card metadata from Piltover Archive
    # The API endpoint for card lookup by code
    cards_data = _fetch_cards_metadata(card_codes)

    # Build RBCard objects
    cards: list[RBCard] = []
    for line in parsed_lines:
        code = f"{line.set_code}-{line.collector_number}"
        metadata = cards_data.get(code, {})

        card_type = metadata.get("type", "")
        card_super = metadata.get("super")
        section = _type_to_section(card_type, card_super)

        # Use the image URL from metadata, or construct from CDN pattern
        image_url = metadata.get("imageUrl", "")
        if not image_url:
            image_url = f"https://cdn.piltoverarchive.com/cards/{code}.webp"

        cards.append(
            RBCard(
                card_id=code,
                variant_id=code,
                name=line.name,  # Use the name from the text (user-friendly)
                card_type=card_type,
                card_super=card_super,
                quantity=line.quantity,
                image_url=image_url,
                section=section,
            )
        )

    return RBDeck(
        deck_id="text-import",
        name=deck_name,
        cards=cards,
    )


def _fetch_cards_metadata(card_codes: list[str]) -> dict[str, dict]:
    """Fetch metadata for multiple cards from Piltover Archive API.

    Returns a dict mapping card code (e.g., "OGN-156") to card metadata.
    Uses the cards.search tRPC endpoint to look up cards by their codes.
    """
    from src.http_client import get as http_get
    import json
    from urllib.parse import quote

    if not card_codes:
        return {}

    _TRPC_BASE = "https://piltoverarchive.com/api/trpc"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://piltoverarchive.com/",
    }

    metadata_map: dict[str, dict] = {}

    # Try to fetch each card individually using the search endpoint
    # This is a fallback approach - ideally we'd use a batch endpoint
    for code in card_codes:
        try:
            # Search for the card by code
            # The API might have an endpoint like cards.getByCode or cards.search
            # For now, we'll use a simple approach and construct image URLs from CDN
            # TODO: Implement actual API lookup when the correct endpoint is identified

            # For now, return minimal metadata
            # The image URL will be constructed from the CDN pattern
            metadata_map[code] = {
                "type": "",  # Will be determined from card type patterns
                "super": None,
                "imageUrl": f"https://cdn.piltoverarchive.com/cards/{code}.webp",
            }
        except Exception:
            # If lookup fails, continue with minimal data
            metadata_map[code] = {
                "type": "",
                "super": None,
                "imageUrl": f"https://cdn.piltoverarchive.com/cards/{code}.webp",
            }

    return metadata_map
