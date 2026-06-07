import functools
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event

import gdown
import requests

from src.cancellation import Cancelled

_log = logging.getLogger(__name__)

try:
    from gdown.exceptions import FileURLRetrievalError as _GdownPermissionError
except ImportError:
    _GdownPermissionError = None

THREADS = 5
_MAX_RETRIES = 4
_INITIAL_BACKOFF = 1.0  # seconds; doubles on each retry (1 → 2 → 4 → 8)

# Per-image download timeouts.  The read timeout fires only when *no data is
# received* for that many seconds — it does not limit total download time, so
# large files on a slow connection will still work.
_CONNECT_TIMEOUT = 10   # seconds to establish the TCP connection
_READ_TIMEOUT    = 30   # seconds without receiving any data


def _install_download_timeout() -> None:
    """Patch requests.Session so every request gdown makes has a timeout.
    Without this, gdown can hang indefinitely when Drive stops responding."""
    orig = requests.Session.request

    @functools.wraps(orig)
    def _with_timeout(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (_CONNECT_TIMEOUT, _READ_TIMEOUT))
        return orig(self, method, url, **kwargs)

    requests.Session.request = _with_timeout


_install_download_timeout()


class DownloadRateLimitError(Exception):
    """Raised when Google Drive rate-limits us and all retries are exhausted."""
    pass


class DownloadPermissionError(Exception):
    """Raised when gdown cannot retrieve a Drive file URL due to missing permissions."""

    def __init__(self, drive_id: str, card_name: str) -> None:
        self.drive_id = drive_id
        self.card_name = card_name
        self.xml_name: str = ""
        self.position: int = 0
        super().__init__(f"Permisos retirados para '{card_name}' (ID: {drive_id})")


class DownloadTimeoutError(Exception):
    """Raised when a Drive download stalls and exceeds the read timeout."""

    def __init__(self, drive_id: str, card_name: str) -> None:
        self.drive_id = drive_id
        self.card_name = card_name
        self.xml_name: str = ""
        self.position: int = 0
        super().__init__(f"Tiempo de espera agotado para '{card_name}' (ID: {drive_id})")


def _drive_url(drive_id: str) -> str:
    return f"https://drive.google.com/uc?id={drive_id}"


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    keywords = ("429", "too many", "quota", "rate limit", "try again later",
                 "limit exceeded", "503", "service unavailable")
    if any(kw in msg for kw in keywords):
        return True
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) in (429, 503):
        return True
    return False


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def download_image(drive_id: str, dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix or ".jpg"
    output_path = dest_dir / f"{drive_id}{suffix}"
    if output_path.exists():
        _log.debug("Download cache hit: %s", output_path.name)
        return output_path

    _log.info("Downloading: %s (%s)", filename, drive_id)
    tmp_path = dest_dir / f"{drive_id}_{os.getpid()}_{threading.current_thread().ident}{suffix}.tmp"

    delay = _INITIAL_BACKOFF
    for attempt in range(_MAX_RETRIES + 1):
        try:
            gdown.download(_drive_url(drive_id), str(tmp_path), quiet=True)
            tmp_path.replace(output_path)
            _log.debug("Downloaded: %s", output_path.name)
            return output_path
        except requests.exceptions.Timeout:
            _safe_unlink(tmp_path)
            _log.error("Timeout downloading %s (%s)", filename, drive_id)
            raise DownloadTimeoutError(drive_id, filename)
        except Exception as exc:
            _safe_unlink(tmp_path)
            is_permission = (
                (_GdownPermissionError is not None and isinstance(exc, _GdownPermissionError))
                or "FileURLRetrievalError" in type(exc).__name__
            )
            if is_permission:
                _log.error("Permission denied: %s (%s)", filename, drive_id)
                raise DownloadPermissionError(drive_id, filename) from exc
            if _is_rate_limit_error(exc):
                if attempt < _MAX_RETRIES:
                    _log.warning(
                        "Rate limited on %s, retry %d/%d in %.0fs",
                        drive_id, attempt + 1, _MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                _log.error("Rate limit exhausted for %s", drive_id)
                raise DownloadRateLimitError() from exc
            raise

    raise DownloadRateLimitError()


def download_all(
    id_name_pairs: list[tuple[str, str]],
    dest_dir: str | Path,
    progress_callback=None,
    cancel_event: Event | None = None,
    on_image_done=None,
) -> dict[str, Path]:
    """Download multiple images in parallel.

    Returns a mapping of drive_id → local Path.
    progress_callback(completed, total) is called after each download.
    on_image_done(drive_id) is called after each image finishes (cached or downloaded).
    If `cancel_event` is provided and gets set mid-run, pending downloads are
    cancelled, in-flight ones are awaited (gdown is uninterruptible), and the
    function raises `Cancelled` once the executor has joined.
    """
    dest_dir = Path(dest_dir)
    results: dict[str, Path] = {}
    total = len(id_name_pairs)
    cancelled = False

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {
            executor.submit(download_image, drive_id, dest_dir, name): drive_id
            for drive_id, name in id_name_pairs
        }
        try:
            for i, future in enumerate(as_completed(futures), start=1):
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    for f in futures:
                        f.cancel()
                    break
                drive_id = futures[future]
                results[drive_id] = future.result()
                if on_image_done:
                    on_image_done(drive_id)
                if progress_callback:
                    progress_callback(i, total)
        except Exception:
            for f in futures:
                f.cancel()
            raise

    if cancelled:
        raise Cancelled()
    return results
