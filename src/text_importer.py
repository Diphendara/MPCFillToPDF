"""Text-based deck importer for various TCGs.

Parses deck lists from plain text in various formats and converts them
to the same data structures used by URL-based importers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import quote

from src.http_client import get as http_get
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

_TRPC_BASE = "https://piltoverarchive.com/api/trpc"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://piltoverarchive.com/",
}


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


def _trpc_get(proc: str, payload: dict) -> dict:
    """Make a tRPC GET request to Piltover Archive API."""
    inp = quote(json.dumps({"json": payload}))
    url = f"{_TRPC_BASE}/{proc}?input={inp}"
    r = http_get(url, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["result"]["data"]["json"]


def _search_card_by_code(code: str) -> dict | None:
    """Search for a card by its code (e.g., 'OGN-156') using Piltover Archive API.

    Returns card metadata dict or None if not found.
    """
    try:
        # Try the cards.search endpoint
        result = _trpc_get("cards.search", {"query": code})

        # The result might be a list of cards or a dict with cards
        if isinstance(result, list) and result:
            return result[0]
        elif isinstance(result, dict) and "cards" in result:
            cards = result["cards"]
            if cards:
                return cards[0]

        return None
    except Exception:
        # If search fails, return None
        return None


def build_riftbound_deck_from_text(
    text: str,
    deck_name: str = "Imported Deck"
) -> RBDeck:
    """Build an RBDeck from pasted text.

    Parses the text and enriches each card with data from Piltover Archive API.
    Returns an RBDeck ready to be used in the GUI and PDF generation pipeline.
    """
    parsed_lines = parse_riftbound_text(text)

    # Build RBCard objects
    cards: list[RBCard] = []
    for line in parsed_lines:
        code = f"{line.set_code}-{line.collector_number}"

        # Try to fetch card metadata from API
        metadata = _search_card_by_code(code)

        if metadata:
            # Use real data from API
            card_type = metadata.get("type", "")
            card_super = metadata.get("super")
            section = _type_to_section(card_type, card_super)

            # Get image URL from variants
            image_url = ""
            variants = metadata.get("cardVariants", [])
            if variants:
                # Use first variant's image
                image_url = variants[0].get("imageUrl", "")

            # Fallback to CDN if no image URL
            if not image_url:
                image_url = f"https://cdn.piltoverarchive.com/cards/{code}.webp"

            # Use real card ID and variant ID from API
            card_id = metadata.get("id", code)
            variant_id = variants[0].get("id", code) if variants else code
        else:
            # Fallback: use minimal data
            card_type = ""
            card_super = None
            section = "maindeck"  # Default section
            image_url = f"https://cdn.piltoverarchive.com/cards/{code}.webp"
            card_id = code
            variant_id = code

        cards.append(
            RBCard(
                card_id=card_id,
                variant_id=variant_id,
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
