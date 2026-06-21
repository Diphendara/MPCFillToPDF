"""Riftbound deck scraper — piltoverarchive.com, riftmana.com, riftbinder.com, riftdex.com, riftbound.gg"""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import requests

from src.cancellation import Cancelled
from src.constants import ProgressCallback
from src.scraper_utils import generate_fallback_back
from src.scraper_utils import resources_dir as _resources_dir

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://piltoverarchive.com/",
}

_TRPC_BASE = "https://piltoverarchive.com/api/trpc"

# ── riftmana.com ──────────────────────────────────────────────────────────────
_RM_BASE = "https://riftmana.com"
_RM_API = "https://riftmana.com/wp-json/riftmana/v2/decks/{uuid}"

# ── riftbinder.com (Firestore) ────────────────────────────────────────────────
_RB_FS_BASE = (
    "https://firestore.googleapis.com/v1"
    "/projects/riftbinder-dc881/databases/(default)/documents/decks/{id}"
)
_RB_IMG_CDN = "https://cdn.piltoverarchive.com/cards/{code}.webp"

# ── riftbound.gg (dotgg) ─────────────────────────────────────────────────────
_RBGG_DECK_API = "https://api.dotgg.gg/cgfw/getdeck?game=riftbound&slug={slug}"
_RBGG_CARDS_API = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"
_RBGG_IMG_URL = "https://static.dotgg.gg/riftbound/cards/{code}.webp"

# ── riftdex.com (Supabase) ────────────────────────────────────────────────────
_RDX_SUPA_URL = "https://duiehcongdospcckoydy.supabase.co"
_RDX_SUPA_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR1aWVoY29uZ2Rvc3BjY2tveWR5Iiw"
    "icm9sZSI6ImFub24iLCJpYXQiOjE3NTE5NzIwNTMsImV4cCI6MjA2NzU0ODA1M30"
    ".e-XlfBWPLkUIzU6DeNpx7dNJrTM05v9IedSiV6zt7_c"
)


# ── Sections ──────────────────────────────────────────────────────────────────
# Defines which PDF back each section uses.
SECTION_ORDER = ["legend", "champion", "battlefield", "rune", "maindeck", "sideboard"]

# Sections that share the maindeck back
_MAINDECK_SECTIONS = {"champion", "maindeck", "sideboard"}


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class RBCard:
    card_id: str
    variant_id: str
    name: str
    card_type: str  # "Legend", "Unit", "Rune", "Battlefield", "Spell", …
    card_super: str | None  # "Champion", "Basic", None
    quantity: int
    image_url: str
    section: str  # "legend" | "champion" | "battlefield" | "rune" | "maindeck" | "sideboard"


@dataclass
class RBDeck:
    deck_id: str
    name: str
    cards: list[RBCard] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return sum(c.quantity for c in self.cards)

    def by_section(self) -> dict[str, list[RBCard]]:
        result: dict[str, list[RBCard]] = {s: [] for s in SECTION_ORDER}
        for c in self.cards:
            result.setdefault(c.section, []).append(c)
        return result


# ── Resources ─────────────────────────────────────────────────────────────────


def get_rb_backs() -> dict[str, Path]:
    """Return {section: back_image_path} for each Riftbound card section.

    Mapping:
      black.png → legend, battlefield
      blue.png  → champion, maindeck, sideboard  (Units, Spells, Gears)
      white.png → rune
    Falls back to generated placeholder images when files are missing.
    """
    rb_dir = _resources_dir() / "backs" / "riftbound"
    black = rb_dir / "black.png"
    blue = rb_dir / "blue.png"
    white = rb_dir / "white.png"

    def _get(path: Path, fallback_key: str) -> Path:
        return path if path.exists() else _generate_fallback_back(fallback_key)

    return {
        "legend": _get(black, "legend"),
        "battlefield": _get(black, "battlefield"),
        "rune": _get(white, "rune"),
        "maindeck": _get(blue, "maindeck"),
    }


_FALLBACK_COLORS: dict[str, tuple[str, str]] = {
    "legend": ("#111111", "#888888"),
    "battlefield": ("#111111", "#888888"),
    "rune": ("#eeeeee", "#444444"),
    "maindeck": ("#0d0d1a", "#5588cc"),
}


def _generate_fallback_back(section: str) -> Path:
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    bg, border = _FALLBACK_COLORS.get(section, ("#111111", "#888888"))
    return generate_fallback_back(tmp / f"{section}.png", bg, border)


# ── Shared helpers ────────────────────────────────────────────────────────────


def _type_to_section(card_type: str, card_super: str | None = None) -> str:
    """Map Riftbound card type + super to a deck section name."""
    t = (card_type or "").lower()
    s = (card_super or "").lower()
    if t == "legend":
        return "legend"
    if t == "battlefield":
        return "battlefield"
    if t == "rune":
        return "rune"
    if t == "champion" or s == "champion":
        return "champion"
    return "maindeck"


# ── URL routing ───────────────────────────────────────────────────────────────


def scrape_deck(url: str) -> RBDeck:
    """Detect the source site from the URL and dispatch to the right scraper."""
    import urllib.parse

    host = urllib.parse.urlparse(url).netloc.lower()
    if "piltoverarchive.com" in host:
        m = re.search(r"/decks/view/([0-9a-f-]{36})", url, re.IGNORECASE)
        if not m:
            raise ValueError(
                f"URL no reconocida: {url}\n"
                "Formato esperado: https://piltoverarchive.com/decks/view/<UUID>"
            )
        return _fetch_deck(m.group(1))
    if "riftmana.com" in host:
        return _scrape_riftmana(url)
    if "riftbinder.com" in host:
        return _scrape_riftbinder(url)
    if "riftdex.com" in host:
        return _scrape_riftdex(url)
    if "riftbound.gg" in host:
        return _scrape_riftbound_gg(url)
    raise ValueError(
        f"URL no reconocida: {url}\n"
        "Webs soportadas: piltoverarchive.com, riftmana.com, "
        "riftbinder.com, riftdex.com, riftbound.gg"
    )


# ── riftbound.gg scraper (dotgg) ─────────────────────────────────────────────


def _scrape_riftbound_gg(url: str) -> RBDeck:
    m = re.search(r"/decks/([^/?#]+)", url)
    if not m:
        raise ValueError(
            f"No se pudo extraer el slug de la URL de riftbound.gg: {url}\n"
            "Formato esperado: https://riftbound.gg/decks/<slug>/"
        )
    slug = m.group(1).strip("/")

    r = requests.get(_RBGG_DECK_API.format(slug=slug), headers=_HEADERS, timeout=20)
    r.raise_for_status()
    body = r.text.strip()
    if not body:
        raise ValueError(
            f"El mazo '{slug}' no está disponible en riftbound.gg.\n"
            "Puede ser privado, haber sido eliminado, o no existir.\n"
            "Asegúrate de que la URL sea correcta y el mazo sea público."
        )
    deck_data = r.json()

    r2 = requests.get(_RBGG_CARDS_API, headers=_HEADERS, timeout=30)
    r2.raise_for_status()
    raw = r2.json()
    names = raw["names"]
    cards_db: dict[str, dict] = {row[0]: dict(zip(names, row)) for row in raw["data"]}

    cards: list[RBCard] = []

    for code, qty_str in deck_data.get("deck", {}).items():
        meta = cards_db.get(code, {})
        section = _type_to_section(meta.get("type", ""), meta.get("supertype"))
        cards.append(
            RBCard(
                card_id=code,
                variant_id=code,
                name=meta.get("name", code),
                card_type=meta.get("type", ""),
                card_super=meta.get("supertype"),
                quantity=int(qty_str),
                image_url=_RBGG_IMG_URL.format(code=code),
                section=section,
            )
        )

    # boards[1] = sideboard (boards[0] == deck)
    boards = deck_data.get("boards", [])
    if len(boards) > 1:
        for code, qty_str in boards[1].items():
            meta = cards_db.get(code, {})
            cards.append(
                RBCard(
                    card_id=code,
                    variant_id=f"{code}_sb",
                    name=meta.get("name", code),
                    card_type=meta.get("type", ""),
                    card_super=meta.get("supertype"),
                    quantity=int(qty_str),
                    image_url=_RBGG_IMG_URL.format(code=code),
                    section="sideboard",
                )
            )

    return RBDeck(
        deck_id=slug,
        name=deck_data.get("humanname", slug),
        cards=cards,
    )


# ── riftmana.com scraper ──────────────────────────────────────────────────────


def _scrape_riftmana(url: str) -> RBDeck:
    html_headers = {**_HEADERS, "Accept": "text/html"}
    r = requests.get(url, headers=html_headers, timeout=20)
    r.raise_for_status()

    m = re.search(r'data-deck-uuid=["\']([0-9a-f-]{36})["\']', r.text)
    if not m:
        raise ValueError(f"No se encontró el UUID del mazo en la página de riftmana.com: {url}")
    uuid = m.group(1)

    api_r = requests.get(
        _RM_API.format(uuid=uuid),
        headers=_HEADERS,
        timeout=20,
    )
    api_r.raise_for_status()
    data = api_r.json()["data"]["deck"]

    cards: list[RBCard] = []
    for item in data.get("cards", []):
        section = _type_to_section(item.get("type", ""), item.get("super"))
        code = item["code"].upper()
        cards.append(
            RBCard(
                card_id=code,
                variant_id=code,
                name=item.get("name", code),
                card_type=item.get("type", ""),
                card_super=item.get("super"),
                quantity=int(item.get("quantity", 1)),
                image_url=item.get("image", ""),
                section=section,
            )
        )
    for item in data.get("sideboard", []):
        code = item["code"].upper()
        cards.append(
            RBCard(
                card_id=code,
                variant_id=f"{code}_sb",
                name=item.get("name", code),
                card_type=item.get("type", ""),
                card_super=item.get("super"),
                quantity=int(item.get("quantity", 1)),
                image_url=item.get("image", ""),
                section="sideboard",
            )
        )

    return RBDeck(deck_id=uuid, name=data.get("name", uuid), cards=cards)


# ── riftbinder.com scraper (Firestore) ────────────────────────────────────────


def _fs_str(field: dict) -> str:
    """Extract a string value from a Firestore field object."""
    return field.get("stringValue") or field.get("integerValue") or ""


def _fs_arr(field: dict) -> list[dict]:
    """Extract array values from a Firestore arrayValue field."""
    return field.get("arrayValue", {}).get("values", [])


def _scrape_riftbinder(url: str) -> RBDeck:
    m = re.search(r"/decks/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"No se pudo extraer el ID del mazo de la URL de riftbinder.com: {url}")
    doc_id = m.group(1)

    r = requests.get(
        _RB_FS_BASE.format(id=doc_id),
        headers=_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    fields = r.json().get("fields", {})

    name = _fs_str(fields.get("name", {})) or doc_id
    cards: list[RBCard] = []

    def _add(code: str, qty: int, section: str) -> None:
        code = code.upper()
        cards.append(
            RBCard(
                card_id=code,
                variant_id=f"{code}_{section}",
                name=code,
                card_type=section.capitalize(),
                card_super=None,
                quantity=qty,
                image_url=_RB_IMG_CDN.format(code=code),
                section=section,
            )
        )

    legend_id = _fs_str(fields.get("legendId", {}))
    if legend_id:
        _add(legend_id, 1, "legend")

    for v in _fs_arr(fields.get("battlefields", {})):
        code = v.get("stringValue", "")
        if code:
            _add(code, 1, "battlefield")

    for v in _fs_arr(fields.get("runes", {})):
        f = v.get("mapValue", {}).get("fields", {})
        code = _fs_str(f.get("runeId", {}))
        if code:
            _add(code, 1, "rune")

    for section_key, section_name in [("mainDeck", "maindeck"), ("sideboard", "sideboard")]:
        for v in _fs_arr(fields.get(section_key, {})):
            f = v.get("mapValue", {}).get("fields", {})
            code = _fs_str(f.get("cardId", {}))
            qty = int(_fs_str(f.get("quantity", {})) or 1)
            if code:
                _add(code, qty, section_name)

    return RBDeck(deck_id=doc_id, name=name, cards=cards)


# ── riftdex.com scraper (Supabase) ────────────────────────────────────────────

_RDX_HEADERS = {
    **_HEADERS,
    "apikey": _RDX_SUPA_KEY,
    "Authorization": f"Bearer {_RDX_SUPA_KEY}",
}


def _scrape_riftdex(url: str) -> RBDeck:
    m = re.search(r"/deck/([0-9a-f-]{36})", url, re.IGNORECASE)
    if not m:
        raise ValueError(
            f"No se pudo extraer el UUID del mazo de la URL de riftdex.com: {url}\n"
            "Formato esperado: https://riftdex.com/deck/<UUID>"
        )
    deck_id = m.group(1)

    r = requests.get(
        f"{_RDX_SUPA_URL}/rest/v1/decklists?id=eq.{deck_id}&select=*",
        headers=_RDX_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise ValueError(f"No se encontró el mazo con ID {deck_id} en riftdex.com")
    deck_data = rows[0]

    # deck_data["cards"] = [{"count": N, "cardId": "<uuid>"}]
    slot_list: list[dict] = deck_data.get("cards", [])
    if not slot_list:
        raise ValueError(f"El mazo {deck_id} de riftdex.com no tiene cartas")

    # Batch-resolve all card UUIDs in one Supabase query
    card_uuids = list({s["cardId"] for s in slot_list})
    chunk_size = 200
    card_db: dict[str, dict] = {}
    for i in range(0, len(card_uuids), chunk_size):
        chunk = card_uuids[i : i + chunk_size]
        ids_param = "(" + ",".join(chunk) + ")"
        rc = requests.get(
            f"{_RDX_SUPA_URL}/rest/v1/cards"
            f"?id=in.{ids_param}"
            f"&select=id,card_name,card_number,type,image_url,super",
            headers=_RDX_HEADERS,
            timeout=20,
        )
        rc.raise_for_status()
        for row in rc.json():
            card_db[row["id"]] = row

    cards: list[RBCard] = []
    for slot in slot_list:
        cid = slot["cardId"]
        qty = int(slot.get("count", 1))
        meta = card_db.get(cid, {})
        card_number = meta.get("card_number", cid)
        section = _type_to_section(meta.get("type", ""), meta.get("super"))
        cards.append(
            RBCard(
                card_id=card_number,
                variant_id=cid,
                name=meta.get("card_name", card_number),
                card_type=meta.get("type", ""),
                card_super=meta.get("super"),
                quantity=qty,
                image_url=meta.get("image_url", ""),
                section=section,
            )
        )

    return RBDeck(deck_id=deck_id, name=deck_data.get("name", deck_id), cards=cards)


# ── API fetch ─────────────────────────────────────────────────────────────────


def _trpc_get(proc: str, payload: dict) -> dict:
    inp = quote(json.dumps({"json": payload}))
    url = f"{_TRPC_BASE}/{proc}?input={inp}"
    r = requests.get(url, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["result"]["data"]["json"]


def _resolve_image(item: dict) -> str:
    """Find the imageUrl for the selected variantId in the card's variants list."""
    variant_id = item.get("variantId")
    variants = item.get("card", {}).get("cardVariants", [])
    for v in variants:
        if v["id"] == variant_id:
            return v["imageUrl"]
    # Fallback: use first variant if the selected one is not found
    if variants:
        return variants[0]["imageUrl"]
    return ""


def _fetch_deck(deck_id: str) -> RBDeck:
    raw = _trpc_get("decks.getById", {"id": deck_id})
    if raw is None:
        raise ValueError(
            f"No se encontró el mazo con ID {deck_id} en piltoverarchive.com.\n"
            "Puede ser privado, haber sido eliminado, o el ID no ser válido."
        )

    cards: list[RBCard] = []

    # ── Legend (always 1 copy, imageUrl directly on the object) ──────────────
    leg = raw.get("legend")
    if leg:
        cards.append(
            RBCard(
                card_id=leg["cardId"],
                variant_id=leg["id"],
                name=leg["card"]["name"],
                card_type="Legend",
                card_super=None,
                quantity=1,
                image_url=leg["imageUrl"],
                section="legend",
            )
        )

    # ── Champions ─────────────────────────────────────────────────────────────
    for item in raw.get("champions", []):
        cards.append(
            RBCard(
                card_id=item["cardId"],
                variant_id=item["variantId"],
                name=item["card"]["name"],
                card_type=item["card"]["type"],
                card_super=item["card"].get("super"),
                quantity=item["quantity"],
                image_url=_resolve_image(item),
                section="champion",
            )
        )

    # ── Battlefields ──────────────────────────────────────────────────────────
    for item in raw.get("battlefields", []):
        cards.append(
            RBCard(
                card_id=item["cardId"],
                variant_id=item["variantId"],
                name=item["card"]["name"],
                card_type=item["card"]["type"],
                card_super=item["card"].get("super"),
                quantity=item["quantity"],
                image_url=_resolve_image(item),
                section="battlefield",
            )
        )

    # ── Runes ─────────────────────────────────────────────────────────────────
    for item in raw.get("runes", []):
        cards.append(
            RBCard(
                card_id=item["cardId"],
                variant_id=item["variantId"],
                name=item["card"]["name"],
                card_type=item["card"]["type"],
                card_super=item["card"].get("super"),
                quantity=item["quantity"],
                image_url=_resolve_image(item),
                section="rune",
            )
        )

    # ── Maindeck ──────────────────────────────────────────────────────────────
    for item in raw.get("maindeck", []):
        cards.append(
            RBCard(
                card_id=item["cardId"],
                variant_id=item["variantId"],
                name=item["card"]["name"],
                card_type=item["card"]["type"],
                card_super=item["card"].get("super"),
                quantity=item["quantity"],
                image_url=_resolve_image(item),
                section="maindeck",
            )
        )

    # ── Sideboard ─────────────────────────────────────────────────────────────
    for item in raw.get("sideboard", []):
        cards.append(
            RBCard(
                card_id=item["cardId"],
                variant_id=item["variantId"],
                name=item["card"]["name"],
                card_type=item["card"]["type"],
                card_super=item["card"].get("super"),
                quantity=item["quantity"],
                image_url=_resolve_image(item),
                section="sideboard",
            )
        )

    return RBDeck(deck_id=deck_id, name=raw.get("name", deck_id), cards=cards)


# ── Image download ────────────────────────────────────────────────────────────


def download_images(
    deck: RBDeck,
    dest_dir: Path,
    cancel_event: threading.Event | None = None,
    progress_cb: ProgressCallback = None,
) -> dict[str, Path]:
    """Download one image per unique (card_id, variant_id) pair.
    Returns {variant_id: local_path}.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[str, Path] = {}
    done = 0
    unique = {c.variant_id: c for c in deck.cards}

    def _fetch(card: RBCard) -> tuple[str, Path]:
        ext = card.image_url.rsplit(".", 1)[-1].split("?")[0] or "webp"
        safe_name = re.sub(r"[^\w\-.]", "_", card.variant_id)
        path = dest_dir / f"{safe_name}.{ext}"
        if path.exists():
            return card.variant_id, path
        r = requests.get(card.image_url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        path.write_bytes(r.content)
        return card.variant_id, path

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_fetch, c): c for c in unique.values()}
        for fut in as_completed(futs):
            if cancel_event and cancel_event.is_set():
                raise Cancelled()
            vid, path = fut.result()
            seen[vid] = path
            done += 1
            if progress_cb:
                progress_cb(done, len(unique))

    return seen


# ── Deck expansion ────────────────────────────────────────────────────────────


def expand_deck(
    deck: RBDeck,
    image_map: dict[str, Path],
    backs: dict[str, Path],
    include_runes: bool = True,
) -> tuple[list[Path], list[Path | None]]:
    """Expand cards by quantity in section order.

    Returns (fronts, per_slot_backs).
    Sections: legend → legend back, battlefield → battlefield back,
              rune → rune back, champion/maindeck/sideboard → maindeck back.
    None back means use the PDF default cardback.
    """
    fronts: list[Path] = []
    per_backs: list[Path | None] = []

    def _back_for(section: str) -> Path | None:
        if section == "legend":
            return backs.get("legend")
        if section == "battlefield":
            return backs.get("battlefield")
        if section == "rune":
            return backs.get("rune")
        # champion, maindeck, sideboard
        return backs.get("maindeck")

    for section in SECTION_ORDER:
        if section == "rune" and not include_runes:
            continue
        for card in deck.by_section()[section]:
            img = image_map.get(card.variant_id)
            if img is None:
                continue
            back = _back_for(section)
            for _ in range(card.quantity):
                fronts.append(img)
                per_backs.append(back)

    return fronts, per_backs
