"""Lorcana deck scraper — supports lorcana.gg, inkdecks.com, dreamborn.ink"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
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

# ── dreamborn.ink (Chrome CDP + SQLite) ──────────────────────────────────────
_DREAMBORN_CDP_PORT = 9223
_DREAMBORN_CARDS_DB_URL = "https://dreamborn.ink/cache/es/cards.db"

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


def _work_dir() -> Path:
    """Return the pipeline working directory for cached files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "workdir"
    return Path(__file__).resolve().parent.parent / "workdir"


def _find_chrome_exe() -> str | None:
    """Return the path to an installed Google Chrome binary, or None."""
    import platform

    system = platform.system()
    if system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
    elif system == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
    return next((c for c in candidates if os.path.exists(c)), None)


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
    if "dreamborn.ink" in host:
        return _scrape_dreamborn(url)
    raise ValueError(
        f"URL no reconocida: {url}\nWebs soportadas: lorcana.gg, inkdecks.com, dreamborn.ink"
    )


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


# ── dreamborn.ink scraper (Chrome CDP + cards.db) ────────────────────────────


def _dreamborn_get_cards_db(db_path: Path) -> sqlite3.Connection:
    """Download dreamborn cards.db if not cached and return an open connection."""
    if not db_path.exists():
        r = requests.get(_DREAMBORN_CARDS_DB_URL, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        db_path.write_bytes(r.content)
    return sqlite3.connect(str(db_path))


def _dreamborn_resolve_card_id(dreamborn_id: str, db_conn: sqlite3.Connection) -> str:
    """Convert a dreamborn card ID to dotgg format ('010-028'). Returns '' if unknown."""
    if not dreamborn_id:
        return ""
    if re.fullmatch(r"\d{3}-\d{3}", dreamborn_id):
        return dreamborn_id
    cur = db_conn.cursor()
    cur.execute("SELECT setId, number FROM cards WHERE id = ?", (dreamborn_id,))
    row = cur.fetchone()
    if row:
        set_id, number = row
        return f"{int(set_id):03d}-{int(number):03d}"
    return ""


def _dreamborn_parse_nuxt(nuxt_arr: list, deck_id: str) -> tuple[str, dict[str, int]]:
    """Extract deck name and {dreamborn_card_id: quantity} from a Nuxt 3 __NUXT_DATA__ array."""
    deck_obj_index = None
    for v in nuxt_arr:
        if isinstance(v, dict) and deck_id in v:
            deck_obj_index = v[deck_id]
            break
    if deck_obj_index is None:
        raise ValueError(
            f"No se encontró el mazo '{deck_id}' en los datos de dreamborn.ink.\n"
            "El mazo puede ser privado o haber sido eliminado."
        )
    deck_obj = nuxt_arr[deck_obj_index]
    name = nuxt_arr[deck_obj["name"]] if isinstance(deck_obj.get("name"), int) else deck_id
    cards_dict = nuxt_arr[deck_obj["cards"]] if isinstance(deck_obj.get("cards"), int) else {}
    cards_with_qty: dict[str, int] = {}
    for card_id, qty_idx in cards_dict.items():
        if isinstance(qty_idx, int) and qty_idx < len(nuxt_arr):
            cards_with_qty[card_id] = int(nuxt_arr[qty_idx])
    return name, cards_with_qty


def _dreamborn_get_nuxt_data(deck_id: str, deck_url: str) -> list:
    """Open deck URL in real Chrome via CDP and extract __NUXT_DATA__ JSON array."""
    try:
        import websocket as _ws
    except ImportError as exc:
        raise ValueError(
            "Se necesita el paquete 'websocket-client' para usar mazos de dreamborn.ink.\n"
            "Instálalo con: pip install websocket-client"
        ) from exc

    chrome_exe = _find_chrome_exe()
    if not chrome_exe:
        raise ValueError(
            "No se encontró Google Chrome instalado.\n"
            "Instala Chrome para usar mazos de dreamborn.ink."
        )

    user_data_dir = str(_work_dir() / "dreamborn_chrome")
    proc = subprocess.Popen(
        [
            chrome_exe,
            f"--remote-debugging-port={_DREAMBORN_CDP_PORT}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={user_data_dir}",
            "--start-minimized",
            deck_url,
        ]
    )

    tabs = None
    for _ in range(20):
        time.sleep(0.5)
        try:
            r = requests.get(f"http://localhost:{_DREAMBORN_CDP_PORT}/json", timeout=1)
            tabs = r.json()
            if tabs:
                break
        except Exception:
            pass

    if not tabs:
        proc.terminate()
        raise ValueError(
            "No se pudo conectar a Chrome para acceder a dreamborn.ink.\n"
            f"Asegúrate de que el puerto {_DREAMBORN_CDP_PORT} esté libre."
        )

    dreamborn_tab = next((t for t in tabs if "dreamborn" in t.get("url", "")), tabs[0])
    ws = _ws.WebSocket()
    ws.connect(dreamborn_tab["webSocketDebuggerUrl"])
    mid = [0]

    def _cdp(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        while True:
            data = json.loads(ws.recv())
            if data.get("id") == mid[0]:
                return data

    for _ in range(40):
        time.sleep(1)
        r = _cdp("Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
        title = r.get("result", {}).get("result", {}).get("value", "")
        if title and "momento" not in title.lower() and "moment" not in title.lower():
            break

    r = _cdp(
        "Runtime.evaluate",
        {
            "expression": (
                "document.getElementById('__NUXT_DATA__') "
                "? document.getElementById('__NUXT_DATA__').textContent : null"
            ),
            "returnByValue": True,
        },
    )
    nuxt_raw = r.get("result", {}).get("result", {}).get("value")
    ws.close()
    proc.terminate()

    if not nuxt_raw:
        raise ValueError(
            f"No se encontraron datos del mazo '{deck_id}' en dreamborn.ink.\n"
            "La página puede haber cambiado su estructura."
        )
    return json.loads(nuxt_raw)


def _scrape_dreamborn(url: str) -> LocanaDeck:
    m = re.search(r"/decks/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(
            f"No se pudo extraer el ID del mazo de la URL de dreamborn.ink: {url}\n"
            "Formato esperado: https://dreamborn.ink/decks/<ID>"
        )
    deck_id = m.group(1)
    deck_url = f"https://dreamborn.ink/es/decks/{deck_id}"

    try:
        nuxt_arr = _dreamborn_get_nuxt_data(deck_id, deck_url)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"No se pudo obtener datos de dreamborn.ink: {exc}\n"
            "Asegúrate de tener Google Chrome instalado."
        ) from exc

    deck_name, cards_with_qty = _dreamborn_parse_nuxt(nuxt_arr, deck_id)

    if not cards_with_qty:
        raise ValueError(
            f"El mazo '{deck_id}' de dreamborn.ink no contiene cartas.\n"
            "Puede estar vacío o haber cambiado la estructura de la página."
        )

    _work_dir().mkdir(parents=True, exist_ok=True)
    db_path = _work_dir() / "dreamborn_cards.db"
    try:
        db_conn = _dreamborn_get_cards_db(db_path)
    except Exception as exc:
        raise ValueError(
            f"No se pudo descargar la base de datos de cartas de dreamborn.ink: {exc}"
        ) from exc

    cards: list[LorcanaCard] = []
    try:
        for dreamborn_id, qty in cards_with_qty.items():
            dotgg_id = _dreamborn_resolve_card_id(dreamborn_id, db_conn)
            image_url = _DOTGG_IMAGE_URL.format(card_id=dotgg_id) if dotgg_id else ""
            cur = db_conn.cursor()
            cur.execute("SELECT name FROM cards WHERE id = ?", (dreamborn_id,))
            row = cur.fetchone()
            card_name = row[0] if row else (dotgg_id or dreamborn_id)
            cards.append(
                LorcanaCard(
                    card_id=dotgg_id or dreamborn_id,
                    name=card_name,
                    quantity=qty,
                    image_url=image_url,
                )
            )
    finally:
        db_conn.close()

    return LocanaDeck(deck_id=deck_id, name=deck_name, cards=cards, source="dreamborn")


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
