"""Scryfall image downloader — fetches card images by set code and collector number."""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Event

import requests

from src.cancellation import Cancelled
from src.constants import ProgressCallback
from src.deck_importer import DeckCard

_log = logging.getLogger(__name__)

_SCRYFALL_API = "https://api.scryfall.com/cards/{set_code}/{number}"
_HEADERS = {
    "User-Agent": "MPCFillToPDF/2.0",
    "Accept": "application/json",
}
_TIMEOUT = 15
_RATE_DELAY = 0.1  # Scryfall policy: max 10 req/s

SCRYFALL_THREADS = 5

_rate_lock = threading.Lock()
_last_request_time: float = 0.0

_cache: dict[tuple[str, str], ScryfallCard] = {}
_cache_lock = threading.Lock()


class ScryfallError(Exception):
    pass


@dataclass
class ScryfallCard:
    front_url: str
    back_url: str | None


def _throttled_get(url: str) -> requests.Response:
    global _last_request_time
    with _rate_lock:
        now = time.monotonic()
        wait = _RATE_DELAY - (now - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()
    return requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)


def fetch_card(set_code: str, collector_number: str) -> ScryfallCard:
    """Return front/back image URLs for the given printing from Scryfall."""
    key = (set_code.lower(), collector_number)
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    url = _SCRYFALL_API.format(set_code=set_code.lower(), number=collector_number)
    try:
        resp = _throttled_get(url)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        raise ScryfallError(
            f"Carta no encontrada en Scryfall: {set_code}/{collector_number} ({exc})"
        ) from exc
    except requests.RequestException as exc:
        raise ScryfallError(
            f"Error de conexión con Scryfall ({set_code}/{collector_number}): {exc}"
        ) from exc

    if "image_uris" in data:
        result = ScryfallCard(data["image_uris"]["large"], None)
    elif "card_faces" in data:
        faces = data["card_faces"]
        front = faces[0].get("image_uris", {}).get("large", "")
        back = faces[1].get("image_uris", {}).get("large") if len(faces) > 1 else None
        if not front:
            raise ScryfallError(
                f"No se encontró imagen de frente para {set_code}/{collector_number}"
            )
        result = ScryfallCard(front, back)
    else:
        raise ScryfallError(
            f"Formato de respuesta inesperado de Scryfall para {set_code}/{collector_number}"
        )

    with _cache_lock:
        _cache[key] = result
    return result


def _ext_from_url(url: str) -> str:
    m = re.search(r"\.(jpg|jpeg|png|webp)", url, re.IGNORECASE)
    return f".{m.group(1).lower()}" if m else ".jpg"


def download_card_images(card: DeckCard, dest_dir: Path) -> tuple[Path, Path | None]:
    """Download front and (for MDFCs) back images. Returns (front_path, back_path|None)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    scryfall = fetch_card(card.set_code, card.collector_number)
    slug = f"{card.set_code.lower()}_{card.collector_number}"

    front_ext = _ext_from_url(scryfall.front_url)
    front_path = dest_dir / f"{slug}{front_ext}"
    if not front_path.exists():
        _log.info("Descargando imagen: %s", slug)
        resp = _throttled_get(scryfall.front_url)
        resp.raise_for_status()
        front_path.write_bytes(resp.content)

    back_path: Path | None = None
    if scryfall.back_url:
        back_ext = _ext_from_url(scryfall.back_url)
        back_path = dest_dir / f"{slug}_back{back_ext}"
        if not back_path.exists():
            _log.info("Descargando reverso MDFC: %s", slug)
            resp = _throttled_get(scryfall.back_url)
            resp.raise_for_status()
            back_path.write_bytes(resp.content)

    return front_path, back_path


def download_deck_images(
    cards: list[DeckCard],
    dest_dir: Path,
    progress_cb: ProgressCallback = None,
    cancel_event: Event | None = None,
) -> list[tuple[DeckCard, Path, Path | None]]:
    """Download images for all unique cards in parallel.

    Returns an ordered list of (card, front_path, back_path|None) matching the input order.
    """
    total = len(cards)
    done = 0
    id_to_result: dict[int, tuple[DeckCard, Path, Path | None]] = {}

    with ThreadPoolExecutor(max_workers=SCRYFALL_THREADS) as executor:
        futures = {
            executor.submit(download_card_images, c, dest_dir): (i, c) for i, c in enumerate(cards)
        }
        try:
            for future in as_completed(futures):
                if cancel_event is not None and cancel_event.is_set():
                    for f in futures:
                        f.cancel()
                    raise Cancelled()
                idx, card = futures[future]
                front_path, back_path = future.result()
                id_to_result[idx] = (card, front_path, back_path)
                done += 1
                if progress_cb:
                    progress_cb(done, total)
        except Exception:
            for f in futures:
                f.cancel()
            raise

    return [id_to_result[i] for i in range(len(cards))]
