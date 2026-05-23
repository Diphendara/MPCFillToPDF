from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event

import gdown

from src.cancellation import Cancelled


THREADS = 5


def _drive_url(drive_id: str) -> str:
    return f"https://drive.google.com/uc?id={drive_id}"


def download_image(drive_id: str, dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Use the drive_id as the stem to avoid filesystem issues with card names
    suffix = Path(filename).suffix or ".jpg"
    output_path = dest_dir / f"{drive_id}{suffix}"
    if output_path.exists():
        return output_path
    gdown.download(_drive_url(drive_id), str(output_path), quiet=True)
    return output_path


def download_all(
    id_name_pairs: list[tuple[str, str]],
    dest_dir: str | Path,
    progress_callback=None,
    cancel_event: Event | None = None,
) -> dict[str, Path]:
    """Download multiple images in parallel.

    Returns a mapping of drive_id → local Path.
    progress_callback(completed, total) is called after each download.
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
        for i, future in enumerate(as_completed(futures), start=1):
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                for f in futures:
                    f.cancel()
                break
            drive_id = futures[future]
            results[drive_id] = future.result()
            if progress_callback:
                progress_callback(i, total)

    if cancelled:
        raise Cancelled()
    return results
