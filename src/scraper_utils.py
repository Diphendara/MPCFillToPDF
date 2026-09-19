"""Shared utilities for deck scrapers."""

from __future__ import annotations

import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event

from src.cancellation import Cancelled
from src.constants import ProgressCallback
from src.http_client import get as http_get


def resources_dir() -> Path:
    """Return the project resources directory, handling frozen (.exe) and dev environments."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources"
    return Path(__file__).resolve().parent.parent / "resources"


def bundled_back(game: str, stem: str = "back") -> Path | None:
    """Find a bundled card back without coupling a scraper to one image format."""
    back_dir = resources_dir() / "backs" / game
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        if (path := back_dir / f"{stem}{suffix}").exists():
            return path
    return None


def generate_fallback_back(
    path: Path,
    bg: str,
    border: str,
    size: tuple[int, int] = (480, 670),
) -> Path:
    """Draw a plain colored card-back rectangle and save it to path. Returns path."""
    from PIL import Image, ImageDraw

    W, H = size
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    bw = max(6, W // 25)
    draw.rectangle([0, 0, W - 1, H - 1], outline=border, width=bw)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return path


def download_url_images(
    urls: dict[str, str],
    dest_dir: Path,
    path_for_key: Callable[[str, str], Path],
    headers: dict[str, str],
    cancel_event: Event | None = None,
    progress_cb: ProgressCallback = None,
) -> dict[str, Path]:
    """Cache and download keyed image URLs with consistent cancellation/progress."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    def _fetch(key: str, url: str) -> tuple[str, Path]:
        path = path_for_key(key, url)
        if not path.exists():
            response = http_get(url, headers=headers)
            path.write_bytes(response.content)
        return key, path

    result: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch, key, url): key for key, url in urls.items()}
        for done, future in enumerate(as_completed(futures), start=1):
            if cancel_event and cancel_event.is_set():
                for pending in futures:
                    pending.cancel()
                raise Cancelled()
            key, path = future.result()
            result[key] = path
            if progress_cb:
                progress_cb(done, len(urls))
    return result
