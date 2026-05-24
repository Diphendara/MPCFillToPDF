import hashlib
from pathlib import Path
from threading import Event

from src.cancellation import Cancelled
from src.parser import parse, CardOrder
from src.downloader import download_all
from src.cropper import process_for_pdf
from src.pdf_generator import generate


def run(
    xml_path: str | Path,
    output_dir: str | Path,
    work_dir: str | Path = "workdir",
    progress_callback=None,
    cancel_event: Event | None = None,
    extra_fronts: list[str | Path] | None = None,
    extra_backs: list[str | Path | None] | None = None,
    local_crop_map: dict[Path, bool] | None = None,
) -> list[Path]:
    """Single-XML pipeline: XML → one or more PDFs named after the XML stem.

    `extra_fronts` and `extra_backs` are optional local image paths. The fronts
    are appended after the XML cards; each pairs with the back at the same
    index, or falls back to the XML's default cardback when no paired back is
    supplied.

    `local_crop_map` lets each local image choose whether to apply the MPC
    bleed crop. Missing entries default to `False` (no crop).
    """
    xml_path = Path(xml_path)
    return _run_xmls(
        [xml_path], xml_path.stem, output_dir, work_dir, progress_callback, cancel_event,
        extra_fronts=extra_fronts, extra_backs=extra_backs,
        local_crop_map=local_crop_map,
    )


def run_merged(
    xml_paths: list[str | Path],
    output_dir: str | Path,
    base_name: str,
    work_dir: str | Path = "workdir",
    progress_callback=None,
    cancel_event: Event | None = None,
    extra_fronts: list[str | Path] | None = None,
    extra_backs: list[str | Path | None] | None = None,
    local_crop_map: dict[Path, bool] | None = None,
) -> list[Path]:
    """Multi-XML pipeline: concatenate the XMLs' fronts in order and emit one
    or more PDFs named `<base_name>.pdf` (or `<base_name>_1.pdf`, … when split).
    Each card keeps its own back (from its own XML).

    `extra_fronts` / `extra_backs` behave as in `run`; the first XML's
    cardback is the fallback when no paired back is supplied.
    """
    paths = [Path(p) for p in xml_paths]
    return _run_xmls(
        paths, base_name, output_dir, work_dir, progress_callback, cancel_event,
        extra_fronts=extra_fronts, extra_backs=extra_backs,
        local_crop_map=local_crop_map,
    )


def run_locals_only(
    extra_fronts: list[str | Path],
    local_cardback: str | Path,
    output_dir: str | Path,
    base_name: str,
    work_dir: str | Path = "workdir",
    progress_callback=None,
    cancel_event: Event | None = None,
    extra_backs: list[str | Path | None] | None = None,
    local_crop_map: dict[Path, bool] | None = None,
) -> list[Path]:
    """Generate PDF(s) only from local images (no XML).

    A `local_cardback` image is required — it's used for every front that
    doesn't have a paired back in `extra_backs`.
    """
    if not extra_fronts:
        raise ValueError("run_locals_only requires at least one front image.")
    return _run_xmls(
        [], base_name, output_dir, work_dir, progress_callback, cancel_event,
        extra_fronts=extra_fronts, extra_backs=extra_backs,
        local_cardback=local_cardback, local_crop_map=local_crop_map,
    )


def _local_synthetic_id(path: Path) -> str:
    """Stable synthetic 'drive ID' for a local file, derived from its absolute
    path. The hash keeps it short, filesystem-safe, and cache-friendly across
    re-runs of the same file."""
    h = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"local_{h}"


def _run_xmls(
    xml_paths: list[Path],
    base_name: str,
    output_dir: str | Path,
    work_dir: str | Path,
    progress_callback=None,
    cancel_event: Event | None = None,
    extra_fronts: list[str | Path] | None = None,
    extra_backs: list[str | Path | None] | None = None,
    local_cardback: str | Path | None = None,
    local_crop_map: dict[Path, bool] | None = None,
) -> list[Path]:
    extra_fronts = [Path(p) for p in (extra_fronts or [])]
    # extra_backs is parallel to extra_fronts; entries may be None to mean
    # "use the fallback cardback" (so GUI/CLI callers can mix explicit per-front
    # backs with implicit defaults).
    extra_backs_raw = list(extra_backs or [])
    extra_backs = [Path(p) if p is not None else None for p in extra_backs_raw]
    local_cardback_path = Path(local_cardback) if local_cardback else None
    crop_map: dict[Path, bool] = {
        Path(k): bool(v) for k, v in (local_crop_map or {}).items()
    }

    output_dir = Path(output_dir)
    work_dir = Path(work_dir)
    raw_dir = work_dir / "raw"
    bled_dir = work_dir / "bled"

    def _check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()

    def _cb(stage):
        def _inner(done, total):
            if progress_callback:
                progress_callback(stage, done, total)
        return _inner

    # 1. Parse all XMLs and concatenate slots into one global numbering.
    orders: list[CardOrder] = [parse(p) for p in xml_paths]

    if not orders and not extra_fronts:
        raise ValueError("Se requiere al menos un XML o imágenes locales.")
    if not orders and local_cardback_path is None:
        raise ValueError("Sin XML se requiere un cardback local (--local-cardback).")

    front_slot_to_id: dict[int, str] = {}
    back_slot_to_id: dict[int, str] = {}
    id_name_map: dict[str, str] = {}
    local_id_to_path: dict[str, Path] = {}
    next_slot = 0
    for order in orders:
        front_by_slot = {s: c.drive_id for c in order.fronts for s in c.slots}
        back_by_slot  = {s: c.drive_id for c in order.backs  for s in c.slots}
        for orig_slot in sorted(front_by_slot):
            new_slot = next_slot
            next_slot += 1
            front_slot_to_id[new_slot] = front_by_slot[orig_slot]
            back_slot_to_id[new_slot]  = back_by_slot.get(orig_slot, order.cardback_id)
        for card in order.fronts + order.backs:
            id_name_map[card.drive_id] = card.name
        id_name_map[order.cardback_id] = "cardback.jpg"

    # Cardback fallback used for local fronts without a paired back.
    if local_cardback_path is not None:
        fallback_cardback_id = _local_synthetic_id(local_cardback_path)
        local_id_to_path[fallback_cardback_id] = local_cardback_path
    else:
        fallback_cardback_id = orders[0].cardback_id

    for i, fp in enumerate(extra_fronts):
        sid = _local_synthetic_id(fp)
        local_id_to_path[sid] = fp
        new_slot = next_slot
        next_slot += 1
        front_slot_to_id[new_slot] = sid
        bp = extra_backs[i] if i < len(extra_backs) else None
        if bp is not None:
            bsid = _local_synthetic_id(bp)
            local_id_to_path[bsid] = bp
            back_slot_to_id[new_slot] = bsid
        else:
            back_slot_to_id[new_slot] = fallback_cardback_id

    _check_cancel()

    # 2. Download (skip local IDs — they're already on disk).
    download_pairs = [
        (did, name) for did, name in id_name_map.items()
        if did not in local_id_to_path
    ]
    id_to_raw = download_all(
        download_pairs, raw_dir, _cb("download"), cancel_event=cancel_event,
    )
    id_to_raw.update(local_id_to_path)

    # 3. Crop + mirror bleed
    total = len(id_to_raw)
    id_to_bled: dict[str, Path] = {}
    for i, (drive_id, raw_path) in enumerate(id_to_raw.items(), start=1):
        _check_cancel()
        is_local = drive_id in local_id_to_path
        if is_local:
            local_path = local_id_to_path[drive_id]
            crop_borders = crop_map.get(local_path, False)
            # Two local files may share a basename — key the bled output
            # by the synthetic id so they don't overwrite each other. The
            # `_nocrop` suffix keeps cached output for both crop modes.
            suffix = raw_path.suffix.lower() or ".jpg"
            tag = "" if crop_borders else "_nocrop"
            bled_name = f"{drive_id}{tag}{suffix}"
        else:
            crop_borders = True
            bled_name = raw_path.name
        id_to_bled[drive_id] = process_for_pdf(
            raw_path, bled_dir / bled_name, crop_borders=crop_borders,
        )
        if progress_callback:
            progress_callback("crop", i, total)

    _check_cancel()

    # 4. Generate PDF(s)
    ordered_slots = sorted(front_slot_to_id.keys())
    return generate(
        output_dir, base_name, ordered_slots,
        front_slot_to_id, back_slot_to_id, id_to_bled,
        progress_callback=_cb("pdf"),
        cancel_event=cancel_event,
    )
