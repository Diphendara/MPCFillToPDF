"""Yu-Gi-Oh! deck import from YDKE strings and YGOPRODeck pages."""

from __future__ import annotations

import base64
import html
import json
import re
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests  # noqa: F401 - retained as the scraper's test transport seam

from src.constants import ProgressCallback
from src.http_client import get as http_get
from src.scraper_utils import bundled_back, download_url_images, generate_fallback_back

_HEADERS = {"User-Agent": "Mozilla/5.0 (MPCFillToPDF Yu-Gi-Oh! importer)"}
_CARD_INFO_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
_IMAGE_URL = "https://images.ygoprodeck.com/images/cards/{card_id}.jpg"


@dataclass(frozen=True)
class YGOCard:
    card_id: int
    name: str
    quantity: int
    zone: str


@dataclass
class YGODeck:
    name: str
    deck_id: str
    cards: list[YGOCard]

    def total_slots(self, include_side: bool = False) -> int:
        return sum(c.quantity for c in self.cards if c.zone != "side" or include_side)

    @property
    def side_slots(self) -> int:
        """Return the number of optional Side Deck cards."""
        return sum(c.quantity for c in self.cards if c.zone == "side")


@dataclass(frozen=True)
class YGOUrlAdapter:
    """One external deck source behind the common ``YGODeck`` interface."""

    domains: tuple[str, ...]
    parse_page: Callable[[str, str], YGODeck]


def get_ygo_back() -> Path:
    """Return the bundled Yu-Gi-Oh! back or create a neutral proxy back."""
    if back := bundled_back("yugioh"):
        return back
    import tempfile

    return generate_fallback_back(
        Path(tempfile.mkdtemp()) / "yugioh_proxy_back.png",
        "#5A321A",
        "#D7A15B",
        size=(590, 860),
    )


def _decode_ydke_part(value: str) -> list[int]:
    if not value:
        return []
    try:
        raw = base64.b64decode(value)
    except Exception as exc:
        raise ValueError("La cadena YDKE contiene datos inválidos.") from exc
    if len(raw) % 4:
        raise ValueError("La cadena YDKE contiene IDs de carta incompletos.")
    return list(struct.unpack(f"<{len(raw) // 4}I", raw))


def _card_rows(parts: list[tuple[str, list[int]]], names: dict[int, str]) -> list[YGOCard]:
    cards: list[YGOCard] = []
    for zone, ids in parts:
        quantities: dict[int, int] = {}
        for card_id in ids:
            quantities[card_id] = quantities.get(card_id, 0) + 1
        cards.extend(
            YGOCard(card_id, names.get(card_id, str(card_id)), quantity, zone)
            for card_id, quantity in quantities.items()
        )
    return cards


def _fetch_names(card_ids: list[int]) -> dict[int, str]:
    if not card_ids:
        return {}
    names: dict[int, str] = {}
    for start in range(0, len(card_ids), 40):
        response = http_get(
            _CARD_INFO_URL,
            params={"id": ",".join(map(str, card_ids[start : start + 40]))},
            headers=_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        for row in response.json().get("data", []):
            names[int(row["id"])] = row["name"]
    return names


def _fetch_cards_by_names(card_names: list[str]) -> dict[str, tuple[int, str]]:
    """Resolve exact card names through the YGOPRODeck card API."""
    resolved: dict[str, tuple[int, str]] = {}
    for start in range(0, len(card_names), 20):
        response = http_get(
            _CARD_INFO_URL,
            params={"name": "|".join(card_names[start : start + 20])},
            headers=_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        for row in response.json().get("data", []):
            resolved[row["name"].casefold()] = (int(row["id"]), row["name"])
    return resolved


def _parse_ygoprodeck_page(page_html: str, url: str) -> YGODeck:
    parts: list[tuple[str, list[int]]] = []
    for zone, variable in (
        ("main", "maindeckjs"),
        ("extra", "extradeckjs"),
        ("side", "sidedeckjs"),
    ):
        match = re.search(rf"var {variable}\s*=\s*'([^']*)';", page_html)
        if not match:
            continue
        try:
            card_ids = [int(card_id) for card_id in json.loads(match.group(1))]
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("La lista de cartas de YGOPRODeck no es valida.") from exc
        parts.append((zone, card_ids))
    if not parts or not any(card_ids for _, card_ids in parts):
        raise ValueError("No se encontraron cartas en esta URL de YGOPRODeck.")
    title_match = re.search(r'var deckname\s*=\s*("(?:[^"\\]|\\.)*")\s*;', page_html)
    name = json.loads(title_match.group(1)) if title_match else "Mazo Yu-Gi-Oh!"
    id_match = re.search(r"var deckid\s*=\s*'([^']+)'", page_html)
    deck_id = id_match.group(1) if id_match else url
    ids = list(dict.fromkeys(card_id for _, card_ids in parts for card_id in card_ids))
    return YGODeck(name=name, deck_id=deck_id, cards=_card_rows(parts, _fetch_names(ids)))


def _parse_meta_page(page_html: str, url: str) -> YGODeck:
    names = [
        html.unescape(unquote(match)) for match in re.findall(r'href="/cards/([^"?#]+)', page_html)
    ]
    if not names:
        raise ValueError("No se encontraron cartas en esta URL de Yu-Gi-Oh! Meta.")
    card_by_name = _fetch_cards_by_names(list(dict.fromkeys(names)))
    missing = sorted({name for name in names if name.casefold() not in card_by_name})
    if missing:
        raise ValueError(f"No se pudieron resolver estas cartas: {', '.join(missing[:3])}.")
    quantities: dict[str, int] = {}
    for name in names:
        key = name.casefold()
        quantities[key] = quantities.get(key, 0) + 1
    cards = [
        YGOCard(card_by_name[key][0], card_by_name[key][1], quantity, "main")
        for key, quantity in quantities.items()
    ]
    title_match = re.search(
        r"<title[^>]*>\s*(.*?)\s*</title>", page_html, re.DOTALL | re.IGNORECASE
    )
    name = (
        html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip())
        if title_match
        else "Mazo Yu-Gi-Oh!"
    )
    return YGODeck(name=name, deck_id=url, cards=cards)


def _parse_shared_deck_page(page_html: str, url: str) -> YGODeck:
    """Use an exported YDKE when a source exposes it, else parse its card links."""
    match = re.search(r"ydke://[^\"'\s<]+", unquote(page_html))
    if match:
        slug = urlparse(url).path.rstrip("/").split("/")[-1] or "Mazo Yu-Gi-Oh!"
        return parse_ydke(match.group(0), name=slug)
    return _parse_meta_page(page_html, url)


_URL_ADAPTERS = (
    YGOUrlAdapter(("ygoprodeck.com",), _parse_ygoprodeck_page),
    YGOUrlAdapter(("masterduelmeta.com", "yugiohmeta.com"), _parse_shared_deck_page),
)


def _adapter_for_host(host: str) -> YGOUrlAdapter | None:
    return next(
        (
            adapter
            for adapter in _URL_ADAPTERS
            if any(host == domain or host.endswith(f".{domain}") for domain in adapter.domains)
        ),
        None,
    )


def parse_ydke(value: str, name: str = "Mazo Yu-Gi-Oh!") -> YGODeck:
    """Parse a portable `ydke://` deck string into main, extra and side cards."""
    decoded = unquote(value.strip())
    if not decoded.startswith("ydke://"):
        raise ValueError("Se esperaba una cadena YDKE que empiece por ydke://")
    parts = decoded[7:].split("!")
    if len(parts) < 3:
        raise ValueError("La cadena YDKE debe incluir Main, Extra y Side Deck.")
    zones = [
        ("main", _decode_ydke_part(parts[0])),
        ("extra", _decode_ydke_part(parts[1])),
        ("side", _decode_ydke_part(parts[2])),
    ]
    ids = list(dict.fromkeys(card_id for _, ids in zones for card_id in ids))
    cards = _card_rows(zones, _fetch_names(ids))
    if not cards:
        raise ValueError("El mazo Yu-Gi-Oh! no contiene cartas.")
    return YGODeck(name=name, deck_id=decoded, cards=cards)


def parse_ydk(content: str, name: str, deck_id: str) -> YGODeck:
    """Parse a YDK file into main, extra and side cards."""
    section_to_zone = {"#main": "main", "#extra": "extra", "!side": "side"}
    zone_to_ids = {"main": [], "extra": [], "side": []}
    zone: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line in section_to_zone:
            zone = section_to_zone[line]
        elif zone is not None and line.isdecimal():
            zone_to_ids[zone].append(int(line))
    parts = [(zone_name, zone_to_ids[zone_name]) for zone_name in ("main", "extra", "side")]
    ids = list(dict.fromkeys(card_id for _, card_ids in parts for card_id in card_ids))
    cards = _card_rows(parts, _fetch_names(ids))
    if not cards:
        raise ValueError("El archivo YDK no contiene cartas.")
    return YGODeck(name=name, deck_id=deck_id, cards=cards)


def _scrape_edison_deck(value: str) -> YGODeck:
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    event = query.get("event", [""])[0]
    deck_name = query.get("deck", [""])[0]
    if not event or not deck_name:
        raise ValueError("La URL de Edison Format debe incluir event y deck.")
    base = f"{parsed.scheme}://{parsed.netloc}"
    ydk_url = f"{base}/data/ydk/{quote(event, safe='')}/{quote(deck_name, safe='')}.ydk"
    response = http_get(ydk_url, headers=_HEADERS, timeout=20)
    return parse_ydk(response.text, deck_name, value)


def _scrape_legacy_deck(value: str) -> YGODeck:
    """Import YDKE directly or extract a shared YDKE code from YGOPRODeck."""
    value = value.strip()
    if value.startswith("ydke://"):
        return parse_ydke(value)
    host = urlparse(value).netloc.lower()
    if "ygoprodeck.com" not in host:
        raise ValueError("Formato no reconocido. Pega una cadena YDKE o una URL de YGOPRODeck.")
    response = http_get(value, headers=_HEADERS, timeout=20)
    match = re.search(r"ydke://[^\"'\s<]+", unquote(response.text))
    if not match:
        raise ValueError(
            "No se pudo leer este mazo de YGOPRODeck. Usa «Export Deck» y pega la cadena YDKE."
        )
    slug = urlparse(value).path.rstrip("/").split("/")[-1] or "Mazo Yu-Gi-Oh!"
    return parse_ydke(match.group(0), name=slug)


def _scrape_supported_deck(value: str) -> YGODeck:
    """Import a YDKE string or a public deck URL from supported builders."""
    value = value.strip()
    if value.startswith("ydke://"):
        return parse_ydke(value)
    host = urlparse(value).netloc.lower()
    adapter = _adapter_for_host(host)
    if adapter is None:
        raise ValueError(
            "Formato no reconocido. Usa YDKE, YGOPRODeck, Master Duel Meta o Yu-Gi-Oh! Meta."
        )
    response = http_get(value, headers=_HEADERS, timeout=20)
    return adapter.parse_page(response.text, value)


def scrape_deck(value: str) -> YGODeck:
    """Import a YDKE string or a public deck URL from a supported builder."""
    value = value.strip()
    if value.startswith("ydke://"):
        return parse_ydke(value)
    host = urlparse(value).netloc.lower()
    if host == "edisonformat.net" or host.endswith(".edisonformat.net"):
        return _scrape_edison_deck(value)
    return _scrape_supported_deck(value)


def download_images(
    deck: YGODeck,
    dest_dir: Path,
    cancel_event: threading.Event | None = None,
    progress_cb: ProgressCallback = None,
) -> dict[int, Path]:
    """Download each unique Yu-Gi-Oh! card image once."""
    card_ids = list(dict.fromkeys(card.card_id for card in deck.cards))
    downloaded = download_url_images(
        {str(card_id): _IMAGE_URL.format(card_id=card_id) for card_id in card_ids},
        dest_dir,
        lambda key, _url: dest_dir / f"{key}.jpg",
        _HEADERS,
        cancel_event,
        progress_cb,
    )
    return {int(card_id): path for card_id, path in downloaded.items()}


def expand_deck(
    deck: YGODeck, image_map: dict[int, Path], include_side: bool = False
) -> list[Path]:
    """Expand a deck in stable alphabetical order, retaining Main/Extra before Side."""
    zones = ("main", "extra", "side") if include_side else ("main", "extra")
    fronts: list[Path] = []
    for zone in zones:
        cards_in_zone = sorted(
            (c for c in deck.cards if c.zone == zone), key=lambda c: c.name.casefold()
        )
        for card in cards_in_zone:
            if path := image_map.get(card.card_id):
                fronts.extend([path] * card.quantity)
    return fronts
