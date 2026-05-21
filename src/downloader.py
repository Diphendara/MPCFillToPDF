from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import gdown


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
) -> dict[str, Path]:
    """Download multiple images in parallel.

    Returns a mapping of drive_id → local Path.
    progress_callback(completed, total) is called after each download.
    """
    dest_dir = Path(dest_dir)
    results: dict[str, Path] = {}
    total = len(id_name_pairs)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {
            executor.submit(download_image, drive_id, dest_dir, name): drive_id
            for drive_id, name in id_name_pairs
        }
        for i, future in enumerate(as_completed(futures), start=1):
            drive_id = futures[future]
            results[drive_id] = future.result()
            if progress_callback:
                progress_callback(i, total)

    return results
