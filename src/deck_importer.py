"""Deck list fetcher for Moxfield and Archidekt."""

from __future__ import annotations

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

_MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/{deck_id}"
_ARCHIDEKT_API = "https://archidekt.com/api/decks/{deck_id}/"

_ARCHIDEKT_SIDE_CATEGORIES = frozenset({"Sideboard"})
_ARCHIDEKT_SKIP_CATEGORIES = frozenset({"Maybeboard"})


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
    raise DeckImportError("URL no reconocida. Webs soportadas: moxfield.com, archidekt.com")


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
