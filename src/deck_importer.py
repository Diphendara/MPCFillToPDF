"""Deck list fetcher for Moxfield, Archidekt, Deckstats, TappedOut, and Manabox."""

from __future__ import annotations

import html as _html
import json as _json
import re
from dataclasses import dataclass

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 15

_MOXFIELD_RE = re.compile(r"moxfield\.com/decks/([A-Za-z0-9_-]+)")
_ARCHIDEKT_RE = re.compile(r"archidekt\.com/decks/(\d+)")
_DECKSTATS_RE = re.compile(r"deckstats\.net/decks/(\d+)/(\d+)")
_TAPPEDOUT_RE = re.compile(r"tappedout\.net/mtg-decks/([^/?#]+)")
_MANABOX_RE = re.compile(r"manabox\.app/decks/([A-Za-z0-9_-]+)")

_MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/{deck_id}"
_ARCHIDEKT_API = "https://archidekt.com/api/decks/{deck_id}/"
_DECKSTATS_API = (
    "https://deckstats.net/api.php"
    "?action=get_deck&id_type=saved&owner_id={owner_id}&id={deck_id}&response_type=json"
)
_TAPPEDOUT_API = "https://tappedout.net/mtg-decks/{slug}/?fmt=txt"

_ARCHIDEKT_SIDE_CATEGORIES = frozenset({"Sideboard"})
_ARCHIDEKT_SKIP_CATEGORIES = frozenset({"Maybeboard"})
_MANABOX_SIDE_CATS = frozenset({1})  # boardCategory 1 = sideboard

_TAPPEDOUT_MAIN_RE = re.compile(r"^(\d+)\s+(.+)$")
_TAPPEDOUT_SIDE_RE = re.compile(r"^SB:\s*(\d+)\s+(.+)$")


class DeckImportError(Exception):
    def __init__(self, message: str, platform: str = "") -> None:
        self.platform = platform
        super().__init__(message)


@dataclass
class DeckCard:
    name: str
    set_code: str
    collector_number: str
    quantity: int
    zone: str  # "main" | "side"


@dataclass
class FetchedDeck:
    name: str
    cards: list[DeckCard]


def fetch_deck(url: str) -> FetchedDeck:
    """Return the deck name and card list for the deck at url."""
    m = _MOXFIELD_RE.search(url)
    if m:
        return _fetch_moxfield(m.group(1))
    m = _ARCHIDEKT_RE.search(url)
    if m:
        return _fetch_archidekt(m.group(1))
    m = _DECKSTATS_RE.search(url)
    if m:
        return _fetch_deckstats(m.group(1), m.group(2))
    m = _TAPPEDOUT_RE.search(url)
    if m:
        return _fetch_tappedout(m.group(1))
    m = _MANABOX_RE.search(url)
    if m:
        return _fetch_manabox(m.group(1))
    raise DeckImportError(
        "URL no reconocida. Webs soportadas: moxfield.com, archidekt.com, "
        "deckstats.net, tappedout.net, manabox.app"
    )


def _fetch_moxfield(deck_id: str) -> FetchedDeck:
    url = _MOXFIELD_API.format(deck_id=deck_id)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise DeckImportError(f"Error al acceder a Moxfield: {exc}", "moxfield") from exc

    deck_name: str = data.get("name", "")
    cards: list[DeckCard] = []
    boards = data.get("boards", {})
    for board_name, zone in (
        ("mainboard", "main"),
        ("commanders", "main"),
        ("companions", "main"),
        ("sideboard", "side"),
    ):
        board = boards.get(board_name, {})
        for entry in board.get("cards", {}).values():
            card = entry.get("card", {})
            set_code = str(card.get("set", "")).lower()
            collector_number = str(card.get("cn", ""))
            name = card.get("name", "")
            qty = int(entry.get("quantity", 1))
            if not set_code or not collector_number:
                continue
            cards.append(DeckCard(name, set_code, collector_number, qty, zone))
    return FetchedDeck(name=deck_name, cards=cards)


def _fetch_archidekt(deck_id: str) -> FetchedDeck:
    url = _ARCHIDEKT_API.format(deck_id=deck_id)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise DeckImportError(f"Error al acceder a Archidekt: {exc}", "archidekt") from exc

    deck_name: str = data.get("name", "")
    cards: list[DeckCard] = []
    for entry in data.get("cards", []):
        categories = entry.get("categories", [])
        if any(c in _ARCHIDEKT_SKIP_CATEGORIES for c in categories):
            continue
        card_data = entry.get("card", {})
        edition = card_data.get("edition", {})
        set_code = str(edition.get("editioncode", "")).lower()
        collector_number = str(card_data.get("collectorNumber", ""))
        name = card_data.get("oracleCard", {}).get("name", "")
        qty = int(entry.get("quantity", 1))
        zone = "side" if any(c in _ARCHIDEKT_SIDE_CATEGORIES for c in categories) else "main"
        if not set_code or not collector_number:
            continue
        cards.append(DeckCard(name, set_code, collector_number, qty, zone))
    return FetchedDeck(name=deck_name, cards=cards)


def _fetch_deckstats(owner_id: str, deck_id: str) -> FetchedDeck:
    url = _DECKSTATS_API.format(owner_id=owner_id, deck_id=deck_id)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise DeckImportError(f"Error al acceder a Deckstats: {exc}", "deckstats") from exc

    deck_name: str = data.get("name", "")
    cards: list[DeckCard] = []
    for section in data.get("sections", []):
        for entry in section.get("cards", []):
            name = entry.get("name", "")
            qty = int(entry.get("amount", 1))
            if not name:
                continue
            cards.append(DeckCard(name, "", "", qty, "main"))
    for entry in data.get("sideboard", []):
        name = entry.get("name", "")
        qty = int(entry.get("amount", 1))
        if not name:
            continue
        cards.append(DeckCard(name, "", "", qty, "side"))
    return FetchedDeck(name=deck_name, cards=cards)


def _fetch_tappedout(slug: str) -> FetchedDeck:
    url = _TAPPEDOUT_API.format(slug=slug)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise DeckImportError(f"Error al acceder a TappedOut: {exc}", "tappedout") from exc

    deck_name = re.sub(r"\s+", " ", slug.replace("-", " ")).strip().title()
    cards: list[DeckCard] = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        m = _TAPPEDOUT_SIDE_RE.match(line)
        if m:
            cards.append(DeckCard(m.group(2).strip(), "", "", int(m.group(1)), "side"))
            continue
        m = _TAPPEDOUT_MAIN_RE.match(line)
        if m:
            cards.append(DeckCard(m.group(2).strip(), "", "", int(m.group(1)), "main"))

    if not cards:
        raise DeckImportError("No se encontraron cartas en el mazo de TappedOut", "tappedout")
    return FetchedDeck(name=deck_name, cards=cards)


def _astro_val(wrapped: object) -> object:
    if isinstance(wrapped, list) and len(wrapped) == 2 and isinstance(wrapped[0], int):
        signal_type, content = wrapped[0], wrapped[1]
        if signal_type == 0:
            return content
        if signal_type == 1:  # Astro type 1 = array; each element is also [type, value]
            return [_astro_val(item) for item in content]
    return wrapped


def _astro_find(data: object, key: str) -> object:
    """Search recursively for key in Astro dehydrated props; returns unwrapped value or None."""
    if isinstance(data, dict):
        if key in data:
            return _astro_val(data[key])
        for v in data.values():
            result = _astro_find(_astro_val(v), key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _astro_find(item, key)
            if result is not None:
                return result
    return None


def _manabox_extract_props(raw: str) -> str:
    """Return the HTML-encoded value of the props attribute containing &quot;cards&quot;."""
    marker = "&quot;cards&quot;:"
    pos = raw.find(marker)
    if pos == -1:
        return ""
    attr_pos = raw.rfind('props="', 0, pos)
    if attr_pos == -1:
        return ""
    i = attr_pos + 7
    end = i
    while end < len(raw):
        if raw[end] == '"':
            break
        if raw[end : end + 6] == "&quot;":
            end += 6
            continue
        end += 1
    return raw[i:end]


def _fetch_manabox(deck_id: str) -> FetchedDeck:
    url = f"https://manabox.app/decks/{deck_id}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise DeckImportError(f"Error al acceder a Manabox: {exc}", "manabox") from exc

    props_encoded = _manabox_extract_props(resp.text)
    if not props_encoded:
        raise DeckImportError("No se encontraron datos del mazo en Manabox", "manabox")

    try:
        props = _json.loads(_html.unescape(props_encoded))
    except _json.JSONDecodeError as exc:
        raise DeckImportError(f"Error al parsear datos de Manabox: {exc}", "manabox") from exc

    raw_cards = _astro_find(props, "cards")
    if not isinstance(raw_cards, list):
        raise DeckImportError("Formato de mazos inesperado en Manabox", "manabox")

    deck_name = str(_astro_find(props, "name") or deck_id)
    cards: list[DeckCard] = []
    for entry in raw_cards:
        if not isinstance(entry, dict):
            continue
        name = str(_astro_val(entry.get("name", "")))
        set_code = str(_astro_val(entry.get("setId", ""))).lower()
        collector_number = str(_astro_val(entry.get("collectorNumber", "")))
        quantity = int(_astro_val(entry.get("quantity", 1)))  # type: ignore[arg-type]
        board_cat = int(_astro_val(entry.get("boardCategory", 0)))  # type: ignore[arg-type]
        zone = "side" if board_cat in _MANABOX_SIDE_CATS else "main"
        if not name:
            continue
        cards.append(DeckCard(name, set_code, collector_number, quantity, zone))

    return FetchedDeck(name=deck_name, cards=cards)
