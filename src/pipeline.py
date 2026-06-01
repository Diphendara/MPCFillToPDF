import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from src.cancellation import Cancelled
from src.parser import parse, CardOrder
from src.downloader import download_all, DownloadPermissionError, DownloadTimeoutError
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
    # drive_id → (xml_filename, 1-based slot position) for friendly error messages
    drive_id_context: dict[str, tuple[str, int]] = {}
    next_slot = 0
    for path, order in zip(xml_paths, orders):
        xml_name = path.name
        front_by_slot = {s: c.drive_id for c in order.fronts for s in c.slots}
        back_by_slot  = {s: c.drive_id for c in order.backs  for s in c.slots}
        for orig_slot in sorted(front_by_slot):
            new_slot = next_slot
            next_slot += 1
            fid = front_by_slot[orig_slot]
            front_slot_to_id[new_slot] = fid
            back_slot_to_id[new_slot]  = back_by_slot.get(orig_slot, order.cardback_id)
            if fid not in drive_id_context:
                drive_id_context[fid] = (xml_name, new_slot + 1)
            bid = back_slot_to_id[new_slot]
            if bid not in drive_id_context:
                drive_id_context[bid] = (xml_name, new_slot + 1)
        for card in order.fronts + order.backs:
            id_name_map[card.drive_id] = card.name
        id_name_map[order.cardback_id] = "cardback.jpg"
        if order.cardback_id not in drive_id_context:
            drive_id_context[order.cardback_id] = (xml_name, 0)

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
    try:
        id_to_raw = download_all(
            download_pairs, raw_dir, _cb("download"), cancel_event=cancel_event,
        )
    except (DownloadPermissionError, DownloadTimeoutError) as e:
        ctx = drive_id_context.get(e.drive_id)
        if ctx:
            e.xml_name, e.position = ctx
        raise
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


# ---------------------------------------------------------------------------
# run_plan — download-first multi-job orchestration
# ---------------------------------------------------------------------------

@dataclass
class _JobData:
    base_name: str
    ordered_slots: list[int]
    front_slot_to_id: dict[int, str]
    back_slot_to_id: dict[int, str]
    local_id_to_path: dict[str, Path]
    id_name_map: dict[str, str]
    drive_id_context: dict[str, tuple[str, int]]
    xml_needed_ids: dict[str, set[str]]


def _build_job_data(
    xml_paths: list[Path],
    base_name: str,
    next_slot: int,
    extra_fronts: list[Path],
    extra_backs: list[Path | None],
    fallback_cardback_id: str,
) -> tuple[_JobData, int]:
    """Parse XMLs and build all slot maps for one job.
    Returns (job_data, updated next_slot). Does not download or crop anything."""
    orders = [parse(p) for p in xml_paths]

    front_slot_to_id: dict[int, str] = {}
    back_slot_to_id: dict[int, str] = {}
    id_name_map: dict[str, str] = {}
    local_id_to_path: dict[str, Path] = {}
    drive_id_context: dict[str, tuple[str, int]] = {}
    xml_needed_ids: dict[str, set[str]] = {}

    for path, order in zip(xml_paths, orders):
        xml_name = path.name
        front_by_slot = {s: c.drive_id for c in order.fronts for s in c.slots}
        back_by_slot  = {s: c.drive_id for c in order.backs  for s in c.slots}
        needed: set[str] = set()
        for orig_slot in sorted(front_by_slot):
            ns = next_slot
            next_slot += 1
            fid = front_by_slot[orig_slot]
            front_slot_to_id[ns] = fid
            back_slot_to_id[ns]  = back_by_slot.get(orig_slot, order.cardback_id)
            needed.add(fid)
            needed.add(back_slot_to_id[ns])
            if fid not in drive_id_context:
                drive_id_context[fid] = (xml_name, ns + 1)
            bid = back_slot_to_id[ns]
            if bid not in drive_id_context:
                drive_id_context[bid] = (xml_name, ns + 1)
        needed.add(order.cardback_id)
        xml_needed_ids[xml_name] = needed
        for card in order.fronts + order.backs:
            id_name_map[card.drive_id] = card.name
        id_name_map[order.cardback_id] = "cardback.jpg"
        if order.cardback_id not in drive_id_context:
            drive_id_context[order.cardback_id] = (xml_name, 0)

    for i, fp in enumerate(extra_fronts):
        sid = _local_synthetic_id(fp)
        local_id_to_path[sid] = fp
        ns = next_slot
        next_slot += 1
        front_slot_to_id[ns] = sid
        bp = extra_backs[i] if i < len(extra_backs) else None
        if bp is not None:
            bsid = _local_synthetic_id(bp)
            local_id_to_path[bsid] = bp
            back_slot_to_id[ns] = bsid
        else:
            back_slot_to_id[ns] = fallback_cardback_id

    return _JobData(
        base_name=base_name,
        ordered_slots=sorted(front_slot_to_id.keys()),
        front_slot_to_id=front_slot_to_id,
        back_slot_to_id=back_slot_to_id,
        local_id_to_path=local_id_to_path,
        id_name_map=id_name_map,
        drive_id_context=drive_id_context,
        xml_needed_ids=xml_needed_ids,
    ), next_slot


def run_plan(
    jobs: list,
    output_dir: str | Path,
    work_dir: str | Path = "workdir",
    progress_callback=None,
    cancel_event: Event | None = None,
    extra_fronts: list[str | Path] | None = None,
    extra_backs: list[str | Path | None] | None = None,
    local_crop_map: dict[Path, bool] | None = None,
    on_job_pdf_start=None,
    on_xml_download_progress=None,
    on_xml_crop_progress=None,
) -> list[Path]:
    """Download ALL images first, then crop all, then generate each job's PDFs.

    on_job_pdf_start(job_idx, total_jobs, job_name) is called just before
    starting PDF generation for each job so callers can update their UI label.
    on_xml_download_progress(xml_name, done, total) is called after each image
    download completes, with the per-XML running totals.
    on_xml_crop_progress(xml_name, done, total) is called after each image
    crop completes, with the per-XML running totals.
    """
    output_dir = Path(output_dir)
    work_dir   = Path(work_dir)
    raw_dir    = work_dir / "raw"
    bled_dir   = work_dir / "bled"

    extra_fronts_p = [Path(p) for p in (extra_fronts or [])]
    extra_backs_p  = [Path(p) if p is not None else None for p in (extra_backs or [])]
    crop_map: dict[Path, bool] = {Path(k): bool(v) for k, v in (local_crop_map or {}).items()}

    def _check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()

    def _cb(stage):
        def _inner(done, total):
            if progress_callback:
                progress_callback(stage, done, total)
        return _inner

    # --- Phase 1: parse all jobs ------------------------------------------------
    job_data_list: list[_JobData] = []
    combined_id_name:  dict[str, str]            = {}
    combined_locals:   dict[str, Path]           = {}
    combined_context:  dict[str, tuple[str, int]] = {}
    combined_xml_ids:  dict[str, set[str]]        = {}
    next_slot = 0
    last_idx  = len(jobs) - 1

    for i, job in enumerate(jobs):
        is_last   = (i == last_idx)
        ef        = extra_fronts_p if is_last else []
        eb        = extra_backs_p  if is_last else []
        fallback  = parse(Path(job.xml_paths[0])).cardback_id if job.xml_paths else ""

        jd, next_slot = _build_job_data(
            xml_paths=[Path(p) for p in job.xml_paths],
            base_name=job.base_name,
            next_slot=next_slot,
            extra_fronts=ef,
            extra_backs=eb,
            fallback_cardback_id=fallback,
        )
        job_data_list.append(jd)
        combined_id_name.update(jd.id_name_map)
        combined_locals.update(jd.local_id_to_path)
        combined_context.update(jd.drive_id_context)
        for xml_name, ids in jd.xml_needed_ids.items():
            combined_xml_ids.setdefault(xml_name, set()).update(ids)

    _check_cancel()

    # --- Phase 2: download all images -------------------------------------------
    download_pairs = [
        (did, name) for did, name in combined_id_name.items()
        if did not in combined_locals
    ]

    # Per-XML download progress tracking
    _dl_ids_set = {did for did, _ in download_pairs}
    _xml_totals = {
        name: len(ids & _dl_ids_set)
        for name, ids in combined_xml_ids.items()
        if ids & _dl_ids_set
    }
    _xml_done: dict[str, int] = {name: 0 for name in _xml_totals}

    def _on_image_done(drive_id: str) -> None:
        if not on_xml_download_progress:
            return
        for xml_name, ids in combined_xml_ids.items():
            if xml_name in _xml_totals and drive_id in ids:
                _xml_done[xml_name] += 1
                on_xml_download_progress(xml_name, _xml_done[xml_name], _xml_totals[xml_name])

    try:
        id_to_raw = download_all(
            download_pairs, raw_dir, _cb("download"), cancel_event=cancel_event,
            on_image_done=_on_image_done,
        )
    except (DownloadPermissionError, DownloadTimeoutError) as e:
        ctx = combined_context.get(e.drive_id)
        if ctx:
            e.xml_name, e.position = ctx
        raise
    id_to_raw.update(combined_locals)

    _check_cancel()

    # --- Phase 3: crop all images -----------------------------------------------
    total_imgs = len(id_to_raw)
    id_to_bled: dict[str, Path] = {}

    # Per-XML crop progress tracking
    _raw_ids_set = set(id_to_raw.keys())
    _xml_crop_totals = {
        name: len(ids & _raw_ids_set)
        for name, ids in combined_xml_ids.items()
        if ids & _raw_ids_set
    }
    _xml_crop_done: dict[str, int] = {name: 0 for name in _xml_crop_totals}

    for idx, (drive_id, raw_path) in enumerate(id_to_raw.items(), start=1):
        _check_cancel()
        is_local = drive_id in combined_locals
        if is_local:
            local_path   = combined_locals[drive_id]
            crop_borders = crop_map.get(local_path, False)
            suffix       = raw_path.suffix.lower() or ".jpg"
            tag          = "" if crop_borders else "_nocrop"
            bled_name    = f"{drive_id}{tag}{suffix}"
        else:
            crop_borders = True
            bled_name    = raw_path.name
        id_to_bled[drive_id] = process_for_pdf(
            raw_path, bled_dir / bled_name, crop_borders=crop_borders,
        )
        if progress_callback:
            progress_callback("crop", idx, total_imgs)
        if on_xml_crop_progress:
            for xml_name, ids in combined_xml_ids.items():
                if xml_name in _xml_crop_totals and drive_id in ids:
                    _xml_crop_done[xml_name] += 1
                    on_xml_crop_progress(xml_name, _xml_crop_done[xml_name], _xml_crop_totals[xml_name])

    _check_cancel()

    # --- Phase 4: generate PDFs for each job ------------------------------------
    all_outputs: list[Path] = []
    total_jobs = len(job_data_list)
    for job_idx, jd in enumerate(job_data_list, start=1):
        _check_cancel()
        if on_job_pdf_start:
            on_job_pdf_start(job_idx, total_jobs, jd.base_name)
        outputs = generate(
            output_dir, jd.base_name, jd.ordered_slots,
            jd.front_slot_to_id, jd.back_slot_to_id, id_to_bled,
            progress_callback=_cb("pdf"),
            cancel_event=cancel_event,
        )
        all_outputs.extend(outputs)

    return all_outputs
