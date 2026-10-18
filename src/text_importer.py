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
    is_sideboard: bool = False


# Regex for Riftbound format: "3 Sabotage (OGN-156)" or "1 Elder Dragon (UNL-118A)"
# Captures: quantity, name, set_code, collector_number
_RIFTBOUND_LINE_RE = re.compile(r"^(\d+)\s+(.+?)\s*\((([A-Z]+)-([0-9A-Z]+))\)\s*$", re.IGNORECASE)

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

    Supports optional "Side Board:" or "Sideboard:" section header.
    Cards after that header are marked as sideboard.

    Returns a list of ParsedCardLine objects.
    Raises TextImportError if any line is invalid.
    """
    lines: list[ParsedCardLine] = []
    in_sideboard = False

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        # Detect sideboard section header
        if line.lower() in ("side board:", "sideboard:", "side:"):
            in_sideboard = True
            continue

        match = _RIFTBOUND_LINE_RE.match(line)
        if not match:
            raise TextImportError(
                f"Formato no reconocido: '{line}'. "
                "Formato esperado: 'Cantidad Nombre (SET-NUMERO)'",
                line_number=line_num,
            )

        quantity = int(match.group(1))
        name = match.group(2).strip()
        set_code = match.group(4).upper()  # e.g., "OGN"
        collector_number = match.group(5).upper()  # e.g., "156" or "118A" or "T01g"

        if quantity < 1:
            raise TextImportError(
                f"Cantidad inválida: {quantity}. Debe ser al menos 1.", line_number=line_num
            )

        lines.append(
            ParsedCardLine(
                quantity=quantity,
                name=name,
                set_code=set_code,
                collector_number=collector_number,
                raw_line=raw_line,
                line_number=line_num,
                is_sideboard=in_sideboard,
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


def _fetch_dotgg_cards_db() -> dict[str, dict]:
    """Fetch all Riftbound cards from dotgg API and build a lookup dict by card code.

    Returns a dict mapping card code (e.g., "UNL-118") to card metadata.
    """
    _RBGG_CARDS_API = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    try:
        r = http_get(_RBGG_CARDS_API, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        raw = r.json()
        names = raw["names"]

        cards_db: dict[str, dict] = {}
        for row in raw["data"]:
            card_dict = dict(zip(names, row))
            card_id = card_dict.get("id", "")
            if card_id:
                cards_db[card_id] = card_dict

        return cards_db
    except Exception:
        return {}


def _get_base_code(code: str) -> str:
    """Get the base card code without variant suffix.

    Examples:
        UNL-118A -> UNL-118
        UNL-147A -> UNL-147
        UNL-T01g -> UNL-T01
        OGN-156 -> OGN-156
    """
    # Remove trailing letters that are variant indicators
    # But keep the 'T' in tokens like T01g
    import re

    # For tokens like UNL-T01g, keep the T but remove the variant letter
    if "-T" in code:
        # UNL-T01g -> UNL-T01
        return re.sub(r"([A-Z]+-T\d+)[a-z]$", r"\1", code, flags=re.IGNORECASE)

    # For regular variants like UNL-118A -> UNL-118
    return re.sub(r"([A-Z]+-\d+)[A-Z]$", r"\1", code)


def build_riftbound_deck_from_text(text: str, deck_name: str = "Imported Deck") -> RBDeck:
    """Build an RBDeck from pasted text.

    Parses the text and enriches each card with data from dotgg API.
    Returns an RBDeck ready to be used in the GUI and PDF generation pipeline.
    """
    parsed_lines = parse_riftbound_text(text)

    # Fetch all cards from dotgg API
    cards_db = _fetch_dotgg_cards_db()

    # Build RBCard objects
    cards: list[RBCard] = []
    for line in parsed_lines:
        code = f"{line.set_code}-{line.collector_number}"

        # Try to find the card in the database
        # Try multiple case variations (dotgg uses lowercase for some variants)
        card_data = None
        code_variations = [
            code,  # Original: OGN-039A
            code.lower(),  # Lowercase: ogn-039a
            code.upper(),  # Uppercase: OGN-039A
            # Mixed: OGN-039a (uppercase set, lowercase variant)
            f"{line.set_code.upper()}-{line.collector_number.lower()}",
        ]

        # For tokens, also try with lowercase 'g' suffix (e.g., UNL-T01g)
        if "-T" in code:
            # UNL-T01G -> UNL-T01g
            code_variations.append(
                f"{line.set_code.upper()}-{line.collector_number[:-1]}{line.collector_number[-1].lower()}"
            )

        for code_var in code_variations:
            card_data = cards_db.get(code_var)
            if card_data:
                break

        # If still not found, try base code (without variant suffix)
        if not card_data:
            base_code = _get_base_code(code)
            card_data = cards_db.get(base_code)

        if card_data:
            # Use real data from API
            card_type_list = card_data.get("type", [])
            card_type = (
                card_type_list[0]
                if isinstance(card_type_list, list) and card_type_list
                else str(card_type_list)
            )
            card_super = card_data.get("supertype") or None
            section = _type_to_section(card_type, card_super)

            # Get image URL from dotgg (use the ID from the database, which has correct case)
            card_id = card_data.get("id", code)
            image_url = card_data.get("image", "")

            # If no image URL, construct it with the card_id from DB
            if not image_url:
                image_url = f"https://static.dotgg.gg/riftbound/cards/{card_id}.webp"

            variant_id = code  # Keep the original code as variant_id for tracking
        else:
            # Fallback: use minimal data and construct CDN URL
            card_type = ""
            card_super = None
            section = "maindeck"  # Default section
            # Use the full code for image (variants work on dotgg CDN)
            image_url = f"https://static.dotgg.gg/riftbound/cards/{code}.webp"
            card_id = code
            variant_id = code

        # Override section if card is in sideboard
        if line.is_sideboard:
            section = "sideboard"
            variant_id = f"{variant_id}_sb"

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


def build_riftbound_deck_from_piltover_text(text: str, deck_name: str = "Imported Deck") -> RBDeck:
    """Build an RBDeck from Piltover Archive text export format.

    Expected format:
        Legend:
        1 LeBlanc, Deceiver

        Champion:
        1 LeBlanc, Fragmented

        MainDeck:
        3 Cull the Weak
        ...

    This format includes section headers and card names without set codes.
    Cards are looked up in the dotgg database by name.
    """
    # Section mapping from Piltover format to internal sections
    section_map = {
        "legend": "legend",
        "champion": "champion",
        "maindeck": "maindeck",
        "battlefields": "battlefield",
        "runes": "rune",
        "sideboard": "sideboard",
    }

    # Parse the text
    current_section = None
    parsed_cards: list[tuple[str, str, int]] = []  # (section, name, quantity)

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # Skip empty lines
        if not line:
            continue

        # Check if it's a section header
        if line.endswith(":"):
            section_name = line[:-1].strip().lower()
            if section_name in section_map:
                current_section = section_map[section_name]
            else:
                raise TextImportError(
                    f"Sección desconocida: '{line}'. "
                    f"Secciones válidas: {', '.join(section_map.keys())}",
                    line_number=line_num,
                )
            continue

        # Parse card line: "3 Card Name"
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if not match:
            raise TextImportError(
                f"Formato no reconocido: '{line}'. "
                "Formato esperado: 'Cantidad Nombre' o encabezado de sección 'Sección:'",
                line_number=line_num,
            )

        if current_section is None:
            raise TextImportError(
                f"Carta sin sección: '{line}'. "
                "Las cartas deben estar bajo una sección (Legend:, Champion:, MainDeck:, etc.)",
                line_number=line_num,
            )

        quantity = int(match.group(1))
        name = match.group(2).strip()

        if quantity < 1:
            raise TextImportError(
                f"Cantidad inválida: {quantity}. Debe ser al menos 1.",
                line_number=line_num,
            )

        parsed_cards.append((current_section, name, quantity))

    if not parsed_cards:
        raise TextImportError("No se encontraron cartas en el texto proporcionado.")

    # Fetch all cards from dotgg API to look up by name
    cards_db = _fetch_dotgg_cards_db()

    # Build a name lookup (case-insensitive)
    name_lookup: dict[str, dict] = {}
    for card_id, card_data in cards_db.items():
        card_name = card_data.get("name", "")
        if card_name:
            name_lookup[card_name.lower()] = card_data

    # Build RBCard objects
    cards: list[RBCard] = []
    for section, name, quantity in parsed_cards:
        # Look up card by name
        card_data = name_lookup.get(name.lower())

        if card_data:
            # Found in database
            card_id = card_data.get("id", "")
            image_url = card_data.get("image", "")
            if not image_url and card_id:
                image_url = f"https://static.dotgg.gg/riftbound/cards/{card_id}.webp"

            card_type_list = card_data.get("type", [])
            card_type = (
                card_type_list[0]
                if isinstance(card_type_list, list) and card_type_list
                else str(card_type_list)
            )
            card_super = card_data.get("supertype") or None
            variant_id = card_id
        else:
            # Not found - use placeholder data
            card_id = name  # Use name as ID
            image_url = ""  # No image available
            card_type = ""
            card_super = None
            variant_id = name

        cards.append(
            RBCard(
                card_id=card_id,
                variant_id=variant_id,
                name=name,
                card_type=card_type,
                card_super=card_super,
                quantity=quantity,
                image_url=image_url,
                section=section,
            )
        )

    return RBDeck(
        deck_id="text-import-piltover",
        name=deck_name,
        cards=cards,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MTG (Magic: The Gathering) Text Parser
# ═══════════════════════════════════════════════════════════════════════════════

# Regex for MTG format: "4 Lightning Bolt" or "1 Black Lotus (LEA)" or "1 Dark Leo & Shredder (TMT) 142" or "1 Mana Confluence (CMR) 721 *F*" or "1 Liesa, Shroud of Dusk (PLST) CMR-286"
_MTG_LINE_RE = re.compile(
    r"^(\d+)\s+(.+?)(?:\s+\(([A-Z0-9]+)\)(?:\s+([A-Z0-9-]+))?)?(?:\s+\*[A-Z]+\*)?\s*$",
    re.IGNORECASE,
)


def parse_mtg_text(text: str) -> list[tuple[int, str, str]]:
    """Parse MTG deck list from text.

    Expected formats:
        4 Lightning Bolt
        1 Black Lotus (LEA)
        2 Counterspell (MH2)  # with optional set code

    Returns list of (quantity, name, set_code) tuples.
    """
    from src.deck_importer import DeckCard, FetchedDeck

    cards: list[DeckCard] = []

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        # Check for sideboard marker
        zone = "main"
        if line.lower().startswith("sideboard:") or line.lower().startswith("sb:"):
            continue  # TODO: Handle sideboard cards

        match = _MTG_LINE_RE.match(line)
        if not match:
            raise TextImportError(
                f"Formato no reconocido: '{line}'. "
                "Formato esperado: 'Cantidad Nombre' o 'Cantidad Nombre (SET)'",
                line_number=line_num,
            )

        quantity = int(match.group(1))
        name = match.group(2).strip()
        set_code = match.group(3).upper() if match.group(3) else ""
        collector_number = match.group(4) if match.group(4) else ""

        # Handle special collector formats like "CMR-286" (The List cards)
        # If collector contains a hyphen, it might be "ORIGINAL_SET-NUMBER"
        if collector_number and "-" in collector_number:
            # Extract the actual set and number from "CMR-286"
            parts = collector_number.split("-", 1)
            if len(parts) == 2:
                # Use the embedded set code instead of the display set
                set_code = parts[0].upper()
                collector_number = parts[1]

        if quantity < 1:
            raise TextImportError(
                f"Cantidad inválida: {quantity}. Debe ser al menos 1.", line_number=line_num
            )

        # If no set code provided, fetch from Scryfall
        if not set_code:
            try:
                from src.scryfall import fetch_card_by_name

                fetched_set, fetched_collector = fetch_card_by_name(name)
                set_code = fetched_set.upper()
                collector_number = fetched_collector
            except Exception:
                # If fetch fails, continue without set/collector
                # The download pipeline will try to fetch by name later
                pass

        cards.append(
            DeckCard(
                name=name,
                set_code=set_code.lower() if set_code else "",
                collector_number=collector_number,
                quantity=quantity,
                zone=zone,
            )
        )

    if not cards:
        raise TextImportError("No se encontraron cartas en el texto proporcionado.")

    return FetchedDeck(name="Imported from text", cards=cards)


# ═══════════════════════════════════════════════════════════════════════════════
# Lorcana Text Parser
# ═══════════════════════════════════════════════════════════════════════════════

# Regex for Lorcana format: "4 Elsa - Snow Queen" or "2 Mickey Mouse (1)"
_LORCANA_LINE_RE = re.compile(r"^(\d+)\s+(.+?)(?:\s+\((\d+)\))?\s*$", re.IGNORECASE)


def parse_lorcana_text(text: str) -> list[tuple[int, str, str]]:
    """Parse Lorcana deck list from text.

    Expected formats:
        4 Elsa - Snow Queen
        2 Mickey Mouse (1)

    Returns list of (quantity, name, card_number) tuples.
    """
    from src.lorcana_scraper import LocanaDeck, LorcanaCard

    cards: list[LorcanaCard] = []

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#") or line.startswith("//"):
            continue

        match = _LORCANA_LINE_RE.match(line)
        if not match:
            raise TextImportError(
                f"Formato no reconocido: '{line}'. "
                "Formato esperado: 'Cantidad Nombre' o 'Cantidad Nombre (Numero)'",
                line_number=line_num,
            )

        quantity = int(match.group(1))
        name = match.group(2).strip()
        card_number = match.group(3) if match.group(3) else ""

        if quantity < 1:
            raise TextImportError(
                f"Cantidad inválida: {quantity}. Debe ser al menos 1.", line_number=line_num
            )

        # For Lorcana, we'll use the card number as card_id if available
        card_id = card_number if card_number else name

        cards.append(
            LorcanaCard(
                card_id=card_id,
                name=name,
                quantity=quantity,
                image_url="",  # Will need to be resolved from Lorcana API
            )
        )

    if not cards:
        raise TextImportError("No se encontraron cartas en el texto proporcionado.")

    return LocanaDeck(
        deck_id="text-import",
        name="Imported from text",
        cards=cards,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# One Piece Text Parser
# ═══════════════════════════════════════════════════════════════════════════════

# Regex for One Piece formats:
#   "4 Luffy (OP01-001)" or "1 Zoro (Leader)"
#   "2xOP04-016_r1" or "1xOP13-004"
_OP_LINE_RE = re.compile(
    r"^(?:(\d+)\s+(.+?)\s+\(([A-Z0-9-_]+|Leader)\)|(\d+)x([A-Z0-9-]+(?:_[a-z0-9]+)?))\s*$",
    re.IGNORECASE,
)


def parse_op_text(text: str) -> list[tuple[int, str, str, bool]]:
    """Parse One Piece deck list from text.

    Expected formats:
        1 Monkey D. Luffy (Leader)
        4 Roronoa Zoro (OP01-001)
        2xOP04-016_r1
        1xOP13-004

    Returns OPDeck object.
    """
    from src.op_scraper import OPCard, OPDeck

    cards: list[OPCard] = []

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#") or line.startswith("//"):
            continue

        match = _OP_LINE_RE.match(line)
        if not match:
            raise TextImportError(
                f"Formato no reconocido: '{line}'. "
                "Formatos esperados: 'Cantidad Nombre (CODIGO)', 'Cantidad Nombre (Leader)', o 'CantidadxCODIGO'",
                line_number=line_num,
            )

        # Check which format matched
        if match.group(1):  # Format: "4 Luffy (OP01-001)"
            quantity = int(match.group(1))
            name = match.group(2).strip()
            code_or_leader = match.group(3).upper()
            is_leader = code_or_leader == "LEADER"
            card_id = "" if is_leader else code_or_leader
        else:  # Format: "2xOP04-016_r1"
            quantity = int(match.group(4))
            card_id = match.group(5).upper()
            name = card_id  # Use card_id as name for now
            is_leader = False

        if quantity < 1:
            raise TextImportError(
                f"Cantidad inválida: {quantity}. Debe ser al menos 1.", line_number=line_num
            )

        cards.append(
            OPCard(
                card_id=card_id,
                name=name,
                quantity=quantity,
                is_leader=is_leader,
                colors=[],  # Will need to be resolved from OP API
            )
        )

    if not cards:
        raise TextImportError("No se encontraron cartas en el texto proporcionado.")

    return OPDeck(
        name="Imported from text",
        slug="text-import",
        cards=cards,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Yu-Gi-Oh Text Parser
# ═══════════════════════════════════════════════════════════════════════════════

# Regex for Yu-Gi-Oh format: "3 Blue-Eyes White Dragon" or "1 Dark Magician (LOB)"
_YGO_LINE_RE = re.compile(r"^(\d+)\s+(.+?)(?:\s+\(([A-Z0-9]+)\))?\s*$", re.IGNORECASE)


def parse_ygo_text(text: str) -> list[tuple[int, str, str]]:
    """Parse Yu-Gi-Oh deck list from text.

    Expected formats:
        3 Blue-Eyes White Dragon
        1 Dark Magician (LOB)

    Returns YGODeck object.
    """
    from src.ygo_scraper import YGOCard, YGODeck

    cards: list[YGOCard] = []

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#") or line.startswith("//"):
            continue

        # Check for side/extra deck markers
        zone = "main"
        if line.lower().startswith("side:") or line.lower().startswith("extra:"):
            zone = "side" if line.lower().startswith("side:") else "extra"
            continue  # TODO: Handle section headers

        match = _YGO_LINE_RE.match(line)
        if not match:
            raise TextImportError(
                f"Formato no reconocido: '{line}'. "
                "Formato esperado: 'Cantidad Nombre' o 'Cantidad Nombre (SET)'",
                line_number=line_num,
            )

        quantity = int(match.group(1))
        name = match.group(2).strip()

        if quantity < 1:
            raise TextImportError(
                f"Cantidad inválida: {quantity}. Debe ser al menos 1.", line_number=line_num
            )

        # For YGO, we need to resolve the card ID from the name
        # This will require an API call to YGOPRODeck or similar
        cards.append(
            YGOCard(
                card_id=0,  # Will need to be resolved
                name=name,
                quantity=quantity,
                zone=zone,
            )
        )

    if not cards:
        raise TextImportError("No se encontraron cartas en el texto proporcionado.")

    return YGODeck(
        name="Imported from text",
        deck_id="text-import",
        cards=cards,
    )
