import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event

import requests

from src.cancellation import Cancelled
from src.constants import ImageDoneCallback, ProgressCallback, SpeedCallback

_log = logging.getLogger(__name__)

THREADS = 5
_MAX_RETRIES = 4
_INITIAL_BACKOFF = 1.0  # seconds; doubles on each retry (1 → 2 → 4 → 8)
_TIMEOUT_RETRY_DELAY = 5.0  # seconds to wait before retrying timed-out images

# Per-image download timeouts.  The read timeout fires only when *no data is
# received* for that many seconds — it does not limit total download time, so
# large files on a slow connection will still work.
_CONNECT_TIMEOUT = 10  # seconds to establish the TCP connection
_READ_TIMEOUT = 30  # seconds without receiving any data


class DownloadRateLimitError(Exception):
    """Raised when Google Drive rate-limits us and all retries are exhausted."""

    pass


class DownloadPartialError(Exception):
    """Raised by download_all when individual images fail but the batch continues.

    Collects *all* per-image failures so the caller can report them together
    instead of stopping at the first error.

    Attributes:
        permission_errors: list of (drive_id, card_name) with revoked Drive access.
        timeout_errors:    list of (drive_id, card_name) that still timed out
                           after a retry.
        xml_context:       drive_id → (xml_filename, 1-based position);
                           populated by the pipeline after enrichment.
    """

    def __init__(
        self,
        permission_errors: list[tuple[str, str]],
        timeout_errors: list[tuple[str, str]],
    ) -> None:
        self.permission_errors = permission_errors
        self.timeout_errors = timeout_errors
        self.xml_context: dict[str, tuple[str, int]] = {}
        n = len(permission_errors) + len(timeout_errors)
        super().__init__(f"{n} imagen(es) no se pudieron descargar")


class DownloadPermissionError(Exception):
    """Raised when a Drive file cannot be downloaded due to missing permissions."""

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


def _lh4_url(drive_id: str) -> str:
    return f"https://lh4.googleusercontent.com/d/{drive_id}=d"


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    keywords = (
        "429",
        "too many",
        "quota",
        "rate limit",
        "try again later",
        "limit exceeded",
        "503",
        "service unavailable",
    )
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
            resp = requests.get(
                _lh4_url(drive_id),
                stream=True,
                timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
            )
            resp.raise_for_status()
            with tmp_path.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    fh.write(chunk)
            tmp_path.replace(output_path)
            _log.debug("Downloaded: %s", output_path.name)
            return output_path
        except requests.exceptions.Timeout:
            _safe_unlink(tmp_path)
            _log.error("Timeout downloading %s (%s)", filename, drive_id)
            raise DownloadTimeoutError(drive_id, filename)
        except requests.HTTPError as exc:
            _safe_unlink(tmp_path)
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (403, 404):
                _log.error("Permission denied: %s (%s)", filename, drive_id)
                raise DownloadPermissionError(drive_id, filename) from exc
            if _is_rate_limit_error(exc):
                if attempt < _MAX_RETRIES:
                    _log.warning(
                        "Rate limited on %s, retry %d/%d in %.0fs",
                        drive_id,
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                _log.error("Rate limit exhausted for %s", drive_id)
                raise DownloadRateLimitError() from exc
            raise
        except Exception as exc:
            _safe_unlink(tmp_path)
            if _is_rate_limit_error(exc):
                if attempt < _MAX_RETRIES:
                    _log.warning(
                        "Rate limited on %s, retry %d/%d in %.0fs",
                        drive_id,
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
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
    progress_callback: ProgressCallback = None,
    cancel_event: Event | None = None,
    on_image_done: ImageDoneCallback = None,
    on_speed_update: SpeedCallback = None,
) -> dict[str, Path]:
    """Download multiple images in parallel.

    Returns a mapping of drive_id → local Path.
    progress_callback(completed, total) is called after each download.
    on_image_done(drive_id) is called after each image finishes (cached or downloaded).
    on_speed_update(speed_mbps, eta_sec) is called after each download with running
    speed and estimated remaining time (both floats); only called after ≥0.1 s elapsed.
    If `cancel_event` is provided and gets set mid-run, pending downloads are
    cancelled, in-flight ones are awaited before the executor shuts down, and the
    function raises `Cancelled` once the executor has joined.
    """
    dest_dir = Path(dest_dir)
    results: dict[str, Path] = {}
    total = len(id_name_pairs)
    cancelled = False

    _dl_start = time.time()
    _bytes_done = 0
    _count_done = 0

    # Per-image failures collected across the whole batch.
    _perm_errors: list[tuple[str, str]] = []
    _timeout_errors: list[tuple[str, str]] = []

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
                try:
                    results[drive_id] = future.result()
                except DownloadPermissionError as exc:
                    # Permanent failure — record and continue the rest.
                    _perm_errors.append((exc.drive_id, exc.card_name))
                    _log.warning("Permission denied (skipping): %s", exc.card_name)
                except DownloadTimeoutError as exc:
                    # Transient failure — record for a retry after the batch.
                    _timeout_errors.append((exc.drive_id, exc.card_name))
                    _log.warning("Timeout (will retry): %s", exc.card_name)
                else:
                    _count_done += 1
                    try:
                        _bytes_done += results[drive_id].stat().st_size
                    except OSError:
                        pass
                    elapsed = time.time() - _dl_start
                    if elapsed > 0.1 and on_speed_update and _bytes_done > 0:
                        speed_bps = _bytes_done / elapsed
                        remaining = total - _count_done
                        avg_bytes = _bytes_done / _count_done
                        eta_sec = avg_bytes * remaining / speed_bps if speed_bps > 0 else 0.0
                        on_speed_update(speed_bps / (1024 * 1024), eta_sec)
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

    # Retry timed-out images once, sequentially, after a brief pause.
    if _timeout_errors:
        _log.info(
            "Retrying %d timed-out image(s) after %.0fs…",
            len(_timeout_errors),
            _TIMEOUT_RETRY_DELAY,
        )
        time.sleep(_TIMEOUT_RETRY_DELAY)
        still_failed: list[tuple[str, str]] = []
        for drive_id, card_name in _timeout_errors:
            if cancel_event is not None and cancel_event.is_set():
                break
            try:
                results[drive_id] = download_image(drive_id, dest_dir, card_name)
                _log.info("Retry succeeded: %s", card_name)
            except Exception as exc:
                still_failed.append((drive_id, card_name))
                _log.error("Retry failed for %s: %s", card_name, exc)
        _timeout_errors = still_failed

    if _perm_errors or _timeout_errors:
        raise DownloadPartialError(_perm_errors, _timeout_errors)

    return results
