"""Lorcana deck scraper — supports lorcana.gg, inkdecks.com"""

from __future__ import annotations

import re
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

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
}

# ── lorcana.gg (dotgg) ───────────────────────────────────────────────────────
_DOTGG_DECK_API = "https://api.dotgg.gg/cgfw/getdeck?game=lorcana&slug={slug}"
_DOTGG_CARDS_API = "https://api.dotgg.gg/cgfw/getcards?game=lorcana&mode=indexed"
_DOTGG_IMAGE_URL = "https://static.dotgg.gg/lorcana/cards/{card_id}.webp"

# ── inkdecks.com ─────────────────────────────────────────────────────────────
_INKDECKS_API = "https://inkdecks.com/api/lorcana/decks/{deck_id}"

# dotgg card DB cache
_dotgg_lock = threading.Lock()
_dotgg_cache: dict[str, dict] | None = None
_dotgg_name_cache: dict[str, str] | None = None

# Fallback back image singleton (generated once per process if back.png is missing)
_fallback_lock = threading.Lock()
_fallback_back_path: Path | None = None


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class LorcanaCard:
    card_id: str
    name: str
    quantity: int
    image_url: str


@dataclass
class LocanaDeck:
    deck_id: str
    name: str
    cards: list[LorcanaCard] = field(default_factory=list)
    source: str = "lorcana_gg"

    @property
    def total_slots(self) -> int:
        return sum(c.quantity for c in self.cards)


# ── Resources ─────────────────────────────────────────────────────────────────


def get_lorcana_back() -> Path:
    """Return the Lorcana card back image path, generating a fallback if missing."""
    back = _resources_dir() / "backs" / "lorcana" / "back.png"
    if back.exists():
        return back
    return _generate_fallback_back()


def _generate_fallback_back() -> Path:
    global _fallback_back_path
    with _fallback_lock:
        if _fallback_back_path is not None and _fallback_back_path.exists():
            return _fallback_back_path
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        path = generate_fallback_back(tmp / "back.png", "#0a1f44", "#c8a84b")
        _fallback_back_path = path
        return path


# ── Shared card DB helpers ────────────────────────────────────────────────────


def _load_dotgg_card_db() -> tuple[dict[str, dict], dict[str, str]]:
    """Fetch the dotgg lorcana cards DB once. Returns ({id: card}, {name.lower(): id})."""
    global _dotgg_cache, _dotgg_name_cache
    with _dotgg_lock:
        if _dotgg_cache is not None:
            return _dotgg_cache, _dotgg_name_cache  # type: ignore[return-value]
        r = requests.get(_DOTGG_CARDS_API, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        try:
            raw = r.json()
            names = raw["names"]
            rows = raw["data"]
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"La base de datos de cartas de dotgg.gg devolvió un formato inesperado: {exc}\n"
                "Puede ser un problema temporal. Vuelve a intentarlo."
            ) from exc
        id_to_card: dict[str, dict] = {}
        name_to_id: dict[str, str] = {}
        for row in rows:
            card = dict(zip(names, row))
            cid = card.get("id", "")
            if cid:
                id_to_card[cid] = card
                name_to_id[card.get("name", "").lower()] = cid
        _dotgg_cache = id_to_card
        _dotgg_name_cache = name_to_id
        return id_to_card, name_to_id


def _image_url_for_id(card_id: str) -> str:
    return _DOTGG_IMAGE_URL.format(card_id=card_id)


def _image_url_for_name(name: str) -> str:
    """Look up image URL by card name. Returns empty string if not found."""
    try:
        _, name_to_id = _load_dotgg_card_db()
        cid = name_to_id.get(name.lower(), "")
        if cid:
            return _image_url_for_id(cid)
    except Exception:
        pass
    return ""


# ── URL routing ───────────────────────────────────────────────────────────────


def scrape_deck(url: str) -> LocanaDeck:
    """Detect the source site from the URL and dispatch to the right scraper."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if "lorcana.gg" in host:
        return _scrape_lorcana_gg(url)
    if "inkdecks.com" in host:
        return _scrape_inkdecks(url)
    raise ValueError(f"URL no reconocida: {url}\nWebs soportadas: lorcana.gg, inkdecks.com")


# ── lorcana.gg (dotgg) scraper ───────────────────────────────────────────────


def _scrape_lorcana_gg(url: str) -> LocanaDeck:
    m = re.search(r"/decks/([^/?#]+)", url)
    if not m:
        raise ValueError(
            f"No se pudo extraer el slug de la URL de lorcana.gg: {url}\n"
            "Formato esperado: https://lorcana.gg/decks/<slug>/"
        )
    slug = m.group(1).strip("/")

    r = requests.get(_DOTGG_DECK_API.format(slug=slug), headers=_HEADERS, timeout=20)
    r.raise_for_status()
    body = r.text.strip()
    if not body:
        raise ValueError(
            f"El mazo '{slug}' no está disponible en lorcana.gg.\n"
            "Puede ser privado, haber sido eliminado, o no existir.\n"
            "Asegúrate de que la URL sea correcta y el mazo sea público."
        )
    try:
        deck_data = r.json()
    except ValueError as exc:
        raise ValueError(
            f"La respuesta de lorcana.gg para '{slug}' no es JSON válido.\n"
            "La API puede haber cambiado temporalmente. Vuelve a intentarlo."
        ) from exc

    deck_entries = deck_data.get("deck", {})
    if not deck_entries:
        raise ValueError(
            f"El mazo '{slug}' de lorcana.gg no contiene cartas.\n"
            "Puede haber sido eliminado o estar vacío."
        )

    id_to_card, _ = _load_dotgg_card_db()

    cards: list[LorcanaCard] = []
    for card_id, qty in deck_entries.items():
        meta = id_to_card.get(card_id, {})
        try:
            qty_int = int(qty)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Cantidad de carta inválida en lorcana.gg para '{card_id}': {qty!r}"
            ) from exc
        cards.append(
            LorcanaCard(
                card_id=card_id,
                name=meta.get("name", card_id),
                quantity=qty_int,
                image_url=_image_url_for_id(card_id),
            )
        )

    return LocanaDeck(
        deck_id=slug,
        name=deck_data.get("humanname", slug),
        cards=cards,
        source="lorcana_gg",
    )


# ── inkdecks.com scraper ──────────────────────────────────────────────────────


def _scrape_inkdecks(url: str) -> LocanaDeck:
    # URL format: /lorcana-metagame/deck-ARCHETYPE-ID or /lorcana-decks/SLUG-ID
    m = re.search(r"-(\d+)(?:[/?#]|$)", url)
    if not m:
        raise ValueError(
            f"No se pudo extraer el ID del mazo de la URL de inkdecks.com: {url}\n"
            "Formato esperado: https://inkdecks.com/lorcana-metagame/deck-...-<ID>"
        )
    deck_id = m.group(1)

    # Try JSON API first
    api_url = _INKDECKS_API.format(deck_id=deck_id)
    try:
        r = requests.get(api_url, headers=_HEADERS, timeout=20)
        if r.status_code == 200:
            return _parse_inkdecks_api(r.json(), deck_id)
    except Exception:
        pass

    # Fall back to HTML page scraping (__NEXT_DATA__ JSON embedded in the page)
    html_headers = {**_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"}
    try:
        r = requests.get(url, headers=html_headers, timeout=20)
        r.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        raise ValueError(
            f"No se pudo acceder al mazo {deck_id} en inkdecks.com (HTTP {status}).\n"
            "El mazo puede no existir o el sitio estar temporalmente no disponible."
        ) from exc
    return _parse_inkdecks_html(r.text, deck_id)


def _parse_inkdecks_api(data: dict, deck_id: str) -> LocanaDeck:
    """Parse inkdecks.com JSON API response."""
    name = data.get("name") or data.get("title") or data.get("deck_name") or f"Deck {deck_id}"
    raw_cards = data.get("cards") or data.get("decklist") or []
    cards = _parse_inkdecks_cards(raw_cards)
    if not cards:
        raise ValueError(
            f"No se encontraron cartas en el mazo {deck_id} de inkdecks.com.\n"
            "La respuesta de la API puede haber cambiado."
        )
    return LocanaDeck(deck_id=deck_id, name=name, cards=cards, source="inkdecks")


def _parse_inkdecks_cards(raw_cards: list | dict) -> list[LorcanaCard]:
    """Convert inkdecks card list to LorcanaCards, resolving image URLs via dotgg."""
    cards: list[LorcanaCard] = []
    if isinstance(raw_cards, dict):
        # {card_id: quantity} map
        for cid, qty in raw_cards.items():
            image_url = _image_url_for_id(cid)
            cards.append(LorcanaCard(card_id=cid, name=cid, quantity=int(qty), image_url=image_url))
    elif isinstance(raw_cards, list):
        for item in raw_cards:
            cid = item.get("card_id") or item.get("id") or item.get("cardId") or ""
            for _key in ("quantity", "count", "qty"):
                if _key in item and item[_key] is not None:
                    qty = int(item[_key])
                    break
            else:
                qty = 1
            name = item.get("name") or item.get("card_name") or cid
            image_url = item.get("image") or item.get("image_url") or ""
            if not image_url:
                if cid:
                    image_url = _image_url_for_id(cid)
                elif name:
                    image_url = _image_url_for_name(name)
            if cid or name:
                cards.append(
                    LorcanaCard(card_id=cid or name, name=name, quantity=qty, image_url=image_url)
                )
    return cards


_INKDECKS_BASE = "https://inkdecks.com"

# Matches <tr class="card-list-item" data-card-type="..." data-quantity="N" data-image-src="/img/...">
_INKDECKS_CARD_ROW = re.compile(
    r'class="card-list-item"[^>]*'
    r'data-card-type="[^"]*"[^>]*'
    r'data-quantity="(\d+)"[^>]*'
    r'data-image-src="(/img/cards/lorcana/[^"]+)"',
)
# Card name: <b>Main Name -</b>\n subtitle inside an anchor
_INKDECKS_CARD_NAME = re.compile(
    r'href="/cards/details-[^"]+">\s*(?:<b>\s*(.*?)\s*</b>\s*)?(.*?)\s*</a>',
    re.DOTALL,
)


def _parse_inkdecks_html(html: str, deck_id: str) -> LocanaDeck:
    """Extract deck data from server-rendered inkdecks.com HTML (data-* attributes on card rows)."""
    # Deck name from first <h1> or JSON-LD Article headline
    name: str = f"Deck {deck_id}"
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if h1:
        name = re.sub(r"<[^>]+>", "", h1.group(1)).strip() or name

    card_rows = _INKDECKS_CARD_ROW.findall(html)
    if not card_rows:
        raise ValueError(
            f"No se encontró el mazo {deck_id} en la página de inkdecks.com.\n"
            "Es posible que el sitio haya cambiado su estructura o el mazo no exista."
        )

    # Pair each row with the card name anchor that follows it in the HTML
    card_name_matches = list(_INKDECKS_CARD_NAME.finditer(html))
    cards: list[LorcanaCard] = []
    for i, (qty_str, img_path) in enumerate(card_rows):
        qty = int(qty_str)
        image_url = _INKDECKS_BASE + img_path
        card_id = img_path.lstrip("/")

        card_name = card_id  # fallback
        if i < len(card_name_matches):
            main = (card_name_matches[i].group(1) or "").strip().rstrip(" -").strip()
            subtitle = re.sub(r"\s+", " ", (card_name_matches[i].group(2) or "").strip())
            card_name = (
                f"{main} - {subtitle}" if main and subtitle else (main or subtitle or card_id)
            )

        cards.append(
            LorcanaCard(card_id=card_id, name=card_name, quantity=qty, image_url=image_url)
        )

    return LocanaDeck(deck_id=deck_id, name=name, cards=cards, source="inkdecks")


# ── Image download ────────────────────────────────────────────────────────────


def download_images(
    deck: LocanaDeck,
    dest_dir: Path,
    cancel_event: threading.Event | None = None,
    progress_cb: ProgressCallback = None,
) -> dict[str, Path]:
    """Download one image per unique card_id. Returns {card_id: local_path}."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    unique: dict[str, LorcanaCard] = {c.card_id: c for c in deck.cards}
    done = 0

    def _fetch(card: LorcanaCard) -> tuple[str, Path]:
        if not card.image_url:
            raise ValueError(f"Sin URL de imagen para la carta '{card.name}'")
        ext = card.image_url.rsplit(".", 1)[-1].split("?")[0] or "webp"
        safe_name = re.sub(r"[^\w\-.]", "_", card.card_id)
        path = dest_dir / f"{safe_name}.{ext}"
        if path.exists():
            return card.card_id, path
        r = requests.get(card.image_url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        path.write_bytes(r.content)
        return card.card_id, path

    image_map: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_fetch, c): c for c in unique.values()}
        for fut in as_completed(futs):
            if cancel_event and cancel_event.is_set():
                raise Cancelled()
            card_id, path = fut.result()
            image_map[card_id] = path
            done += 1
            if progress_cb:
                progress_cb(done, len(unique))

    return image_map


# ── Deck expansion ────────────────────────────────────────────────────────────


def expand_deck(
    deck: LocanaDeck,
    image_map: dict[str, Path],
) -> tuple[list[Path], list[Path | None]]:
    """Expand each card by its quantity.

    Returns (fronts, per_slot_backs) where None means use the pipeline default back.
    All Lorcana cards share the same back, so per_slot_backs is all-None.
    """
    fronts: list[Path] = []
    backs: list[Path | None] = []
    for card in deck.cards:
        img = image_map.get(card.card_id)
        if img is None:
            continue
        for _ in range(card.quantity):
            fronts.append(img)
            backs.append(None)
    return fronts, backs
