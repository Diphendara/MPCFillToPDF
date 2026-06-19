"""One Piece Card Game deck scraper — supports onepiece.gg, deckbuilder.egmanevents.com, deckbuilder.cardkaizoku.com."""

from __future__ import annotations

import re
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from src.cancellation import Cancelled

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── dotgg (onepiece.gg) ────────────────────────────────────────────────────
_DOTGG_DECK_API = "https://api.dotgg.gg/cgfw/getdeck?game=onepiece&slug={slug}"
_DOTGG_CARDS_API = "https://api.dotgg.gg/cgfw/getcards?game=onepiece&mode=indexed"
_DOTGG_IMAGE_URL = "https://static.dotgg.gg/onepiece/card/{card_id}.webp"

# ── egmanevents ────────────────────────────────────────────────────────────
_EGMAN_CARDS_API = "https://deckbuilder.egmanevents.com/api/cards/optcg"
_EGMAN_IMAGE_URL = "https://deckbuilder.egmanevents.com/api/images/optcg/{card_id}.png"
_EGMAN_SUPABASE = "https://resgvirjzcpamfumrygh.supabase.co"
_EGMAN_SUPA_KEY = "sb_publishable_bdDgor6ifmOvryEuZKWniw_RBzb3vuh"

# ── cardkaizoku ────────────────────────────────────────────────────────────
_KAIZOKU_CDN = "https://cdn.cardkaizoku.com"
_KAIZOKU_REFERER = "https://deckbuilder.cardkaizoku.com/"


# ── Image URL callables keyed by source ───────────────────────────────────
def _kaizoku_img(card_id: str) -> str:
    prefix = card_id.split("-")[0]
    return f"{_KAIZOKU_CDN}/cards_en/{prefix}/{card_id}.png"


_IMAGE_URL_FUNC_BY_SOURCE = {
    "dotgg": lambda cid: _DOTGG_IMAGE_URL.format(card_id=cid),
    "egman": lambda cid: _EGMAN_IMAGE_URL.format(card_id=cid),
    "kaizoku": _kaizoku_img,
}
_IMAGE_EXT_BY_SOURCE: dict[str, str] = {
    "dotgg": "webp",
    "egman": "png",
    "kaizoku": "png",
}
_IMAGE_EXTRA_HEADERS_BY_SOURCE: dict[str, dict] = {
    "kaizoku": {"Referer": _KAIZOKU_REFERER},
}

# ── Resources ─────────────────────────────────────────────────────────────
_STANDARD_BACK_BG = "#0A1628"
_STANDARD_BACK_BORDER = "#B0B8C8"


def _resources_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources"
    return Path(__file__).resolve().parent.parent / "resources"


def get_op_backs() -> tuple[Path, Path]:
    """Return (default_back, leader_back) from resources/backs/op/.
    Falls back to generating simple colored images if the files are missing.
    """
    op_dir = _resources_dir() / "backs" / "op"
    default = op_dir / "default.png"
    leader = op_dir / "lider.png"
    if default.exists() and leader.exists():
        return default, leader
    return _generate_fallback_backs()


def _generate_fallback_backs() -> tuple[Path, Path]:
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    W, H = 480, 670

    def _make(path: Path, bg: str, border: str) -> Path:
        img = Image.new("RGB", (W, H), bg)
        draw = ImageDraw.Draw(img)
        bw = max(6, W // 25)
        draw.rectangle([0, 0, W - 1, H - 1], outline=border, width=bw)
        img.save(path, "PNG")
        return path

    return (
        _make(tmp / "default.png", _STANDARD_BACK_BG, _STANDARD_BACK_BORDER),
        _make(tmp / "lider.png", "#8B0000", "#CCCCCC"),
    )


# ── Data model ────────────────────────────────────────────────────────────


@dataclass
class OPCard:
    card_id: str
    name: str
    quantity: int
    is_leader: bool
    colors: list[str]


@dataclass
class OPDeck:
    name: str
    slug: str
    cards: list[OPCard]
    source: str = "dotgg"  # "dotgg" | "egman" | "kaizoku"

    @property
    def leader(self) -> OPCard | None:
        return next((c for c in self.cards if c.is_leader), None)

    @property
    def total_slots(self) -> int:
        return sum(c.quantity for c in self.cards)


# ── URL routing ───────────────────────────────────────────────────────────


def scrape_deck(url: str) -> OPDeck:
    """Detect the source site from the URL and dispatch to the right scraper."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if "onepiece.gg" in host:
        return _scrape_dotgg(url)
    if "egmanevents.com" in host:
        return _scrape_egman(url)
    if "cardkaizoku.com" in host:
        return _scrape_kaizoku(url)
    raise ValueError(
        f"URL no reconocida: {url}\n"
        "Webs soportadas: onepiece.gg, deckbuilder.egmanevents.com, deckbuilder.cardkaizoku.com"
    )


# ── dotgg / onepiece.gg ──────────────────────────────────────────────────


def _scrape_dotgg(url: str) -> OPDeck:
    m = re.search(r"/decks/([^/?#]+)", url)
    if not m:
        raise ValueError(f"No se pudo extraer el slug de la URL: {url}")
    slug = m.group(1).strip("/")

    r = requests.get(_DOTGG_DECK_API.format(slug=slug), headers=_HEADERS, timeout=15)
    r.raise_for_status()
    deck_data = r.json()

    r2 = requests.get(_DOTGG_CARDS_API, headers=_HEADERS, timeout=30)
    r2.raise_for_status()
    raw = r2.json()
    names = raw["names"]
    cards_db: dict[str, dict] = {row[0]: dict(zip(names, row)) for row in raw["data"]}

    cards: list[OPCard] = []
    for card_id, qty_str in deck_data["deck"].items():
        meta = cards_db.get(card_id, {})
        is_leader = meta.get("cardType", "").upper() == "LEADER"
        color_str = meta.get("Color", "")
        colors = [c.strip() for c in color_str.split("/") if c.strip()]
        cards.append(
            OPCard(
                card_id=card_id,
                name=meta.get("name", card_id),
                quantity=int(qty_str),
                is_leader=is_leader,
                colors=colors,
            )
        )

    return OPDeck(
        name=deck_data.get("humanname", slug),
        slug=slug,
        cards=cards,
        source="dotgg",
    )


# ── egmanevents ──────────────────────────────────────────────────────────


def _egman_cards_db() -> dict[str, dict]:
    r = requests.get(_EGMAN_CARDS_API, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    return {c["card_code"]: c for c in r.json()}


def _egman_build_deck(
    deck_map: dict[str, int],
    cards_db: dict[str, dict],
    slug: str,
    source: str = "egman",
) -> OPDeck:
    cards: list[OPCard] = []
    for card_id, qty in deck_map.items():
        meta = cards_db.get(card_id, {})
        is_leader = meta.get("category", "").lower() == "leader"
        raw_colors = meta.get("color", [])
        colors = (
            raw_colors if isinstance(raw_colors, list) else ([raw_colors] if raw_colors else [])
        )
        cards.append(
            OPCard(
                card_id=card_id,
                name=meta.get("name", card_id),
                quantity=qty,
                is_leader=is_leader,
                colors=colors,
            )
        )

    leader = next((c for c in cards if c.is_leader), None)
    name = f"{leader.name} Deck" if leader else slug
    return OPDeck(name=name, slug=f"{source}_{slug}", cards=cards, source=source)


def _scrape_egman(url: str) -> OPDeck:
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)

    if "deck" in qs:
        # Direct format: ?deck=CARD:COUNT,CARD:COUNT,...
        deck_str = qs["deck"][0]
        deck_map: dict[str, int] = {}
        for part in deck_str.split(","):
            part = part.strip()
            if ":" in part:
                card_id, count = part.rsplit(":", 1)
                try:
                    deck_map[card_id.strip()] = int(count)
                except ValueError:
                    pass
        if not deck_map:
            raise ValueError("No se encontraron cartas en el parámetro ?deck= de la URL.")
        slug = "direct"

    elif parsed.path.startswith("/d/"):
        # Short URL: /d/CODE → Supabase RPC
        short_code = parsed.path[3:].strip("/")
        if not short_code:
            raise ValueError("Código de mazo vacío en la URL /d/...")
        deck_map, slug = _egman_load_short_code(short_code)

    else:
        raise ValueError(
            "URL de egmanevents no reconocida.\n"
            "Formatos válidos:\n"
            "  • https://deckbuilder.egmanevents.com/?deck=CARTA:X,...\n"
            "  • https://deckbuilder.egmanevents.com/d/CODIGO"
        )

    cards_db = _egman_cards_db()
    return _egman_build_deck(deck_map, cards_db, slug)


def _egman_load_short_code(code: str) -> tuple[dict[str, int], str]:
    """Resolve /d/CODE via Supabase RPC. Returns (deck_map, slug)."""
    rpc_url = f"{_EGMAN_SUPABASE}/rest/v1/rpc/get_deck_by_short_code"
    headers = {
        **_HEADERS,
        "apikey": _EGMAN_SUPA_KEY,
        "Authorization": f"Bearer {_EGMAN_SUPA_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.post(rpc_url, json={"p_code": code}, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    if not data:
        raise ValueError(f"No se encontró ningún mazo con el código: {code}")

    row = data[0] if isinstance(data, list) else data
    deck_data = row.get("deck_data") or row.get("deckData") or {}

    # deck_data puede ser dict {card_id: count} o lista [{card_code, count}, ...]
    deck_map: dict[str, int] = {}
    if isinstance(deck_data, dict):
        deck_map = {k: int(v) for k, v in deck_data.items()}
    elif isinstance(deck_data, list):
        for entry in deck_data:
            cid = entry.get("card_code") or entry.get("cardCode") or entry.get("id", "")
            cnt = int(entry.get("count", entry.get("quantity", 1)))
            if cid:
                deck_map[cid] = cnt

    if not deck_map:
        raise ValueError(f"El mazo con código {code} está vacío o tiene un formato desconocido.")

    slug = row.get("short_code", code)
    return deck_map, slug


# ── cardkaizoku ──────────────────────────────────────────────────────────


def _scrape_kaizoku(url: str) -> OPDeck:
    """Parse ?deck={N}x{CARD_ID}|{N}x{CARD_ID}|... from cardkaizoku.com."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    deck_str = qs.get("deck", [""])[0]
    if not deck_str:
        raise ValueError(
            "No se encontró el parámetro ?deck= en la URL de cardkaizoku.\n"
            "Formato esperado: https://deckbuilder.cardkaizoku.com/?deck=2xOP01-001|3xOP01-002|..."
        )

    deck_map: dict[str, int] = {}
    for part in deck_str.split("|"):
        part = part.strip()
        m = re.match(r"(\d+)x(.+)", part)
        if m:
            count = int(m.group(1))
            card_id = m.group(2).strip().upper()
            deck_map[card_id] = deck_map.get(card_id, 0) + count

    if not deck_map:
        raise ValueError(
            "No se encontraron cartas en el parámetro ?deck= de la URL de cardkaizoku."
        )

    cards_db = _egman_cards_db()
    return _egman_build_deck(deck_map, cards_db, "direct", source="kaizoku")


# ── Image download ─────────────────────────────────────────────────────────


def download_images(
    deck: OPDeck,
    dest_dir: Path,
    cancel_event: threading.Event | None = None,
    progress_cb=None,
) -> dict[str, Path]:
    """Download one image per unique card. Returns {card_id: local_path}."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    url_func = _IMAGE_URL_FUNC_BY_SOURCE.get(
        deck.source,
        lambda cid: _DOTGG_IMAGE_URL.format(card_id=cid),
    )
    ext = _IMAGE_EXT_BY_SOURCE.get(deck.source, "webp")
    extra_headers = _IMAGE_EXTRA_HEADERS_BY_SOURCE.get(deck.source, {})
    req_headers = {**_HEADERS, **extra_headers}
    done = 0

    def _fetch(card: OPCard) -> tuple[str, Path]:
        path = dest_dir / f"{card.card_id}.{ext}"
        if path.exists():
            return card.card_id, path
        url = url_func(card.card_id)
        try:
            r = requests.get(url, headers=req_headers, timeout=20)
            r.raise_for_status()
            path.write_bytes(r.content)
            return card.card_id, path
        except requests.exceptions.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
        # Primary source returned 404 — fall back to kaizoku CDN (covers all sets)
        fb_path = dest_dir / f"{card.card_id}.png"
        if fb_path.exists():
            return card.card_id, fb_path
        fb_r = requests.get(
            _kaizoku_img(card.card_id),
            headers={**_HEADERS, "Referer": _KAIZOKU_REFERER},
            timeout=20,
        )
        fb_r.raise_for_status()
        fb_path.write_bytes(fb_r.content)
        return card.card_id, fb_path

    image_map: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_fetch, c): c for c in deck.cards}
        for fut in as_completed(futs):
            if cancel_event and cancel_event.is_set():
                raise Cancelled()
            card_id, path = fut.result()
            image_map[card_id] = path
            done += 1
            if progress_cb:
                progress_cb(done, len(deck.cards))

    return image_map


# ── Deck expansion ────────────────────────────────────────────────────────


def expand_deck(
    deck: OPDeck,
    image_map: dict[str, Path],
    leader_back: Path | None,
    standard_back: Path,
) -> tuple[list[Path], list[Path | None]]:
    """Expand each card by its quantity.
    Returns (fronts, per_slot_backs) where None means use the standard back.
    """
    fronts: list[Path] = []
    backs: list[Path | None] = []
    for card in deck.cards:
        img_path = image_map.get(card.card_id)
        if img_path is None:
            continue
        slot_back: Path | None = leader_back if (card.is_leader and leader_back) else None
        for _ in range(card.quantity):
            fronts.append(img_path)
            backs.append(slot_back)
    return fronts, backs
