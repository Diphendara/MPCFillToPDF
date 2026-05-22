from pathlib import Path

from src.parser import parse, CardOrder
from src.downloader import download_all
from src.cropper import process_for_pdf
from src.pdf_generator import generate


def run(
    xml_path: str | Path,
    output_dir: str | Path,
    work_dir: str | Path = "workdir",
    progress_callback=None,
) -> list[Path]:
    """Single-XML pipeline: XML → one or more PDFs named after the XML stem."""
    xml_path = Path(xml_path)
    return _run_xmls([xml_path], xml_path.stem, output_dir, work_dir, progress_callback)


def run_merged(
    xml_paths: list[str | Path],
    output_dir: str | Path,
    base_name: str,
    work_dir: str | Path = "workdir",
    progress_callback=None,
) -> list[Path]:
    """Multi-XML pipeline: concatenate the XMLs' fronts in order and emit one
    or more PDFs named `<base_name>.pdf` (or `<base_name>_1.pdf`, … when split).
    Each card keeps its own back (from its own XML)."""
    paths = [Path(p) for p in xml_paths]
    return _run_xmls(paths, base_name, output_dir, work_dir, progress_callback)


def _run_xmls(
    xml_paths: list[Path],
    base_name: str,
    output_dir: str | Path,
    work_dir: str | Path,
    progress_callback=None,
) -> list[Path]:
    output_dir = Path(output_dir)
    work_dir = Path(work_dir)
    raw_dir = work_dir / "raw"
    bled_dir = work_dir / "bled"

    def _cb(stage):
        def _inner(done, total):
            if progress_callback:
                progress_callback(stage, done, total)
        return _inner

    # 1. Parse all XMLs and concatenate slots into one global numbering.
    orders: list[CardOrder] = [parse(p) for p in xml_paths]

    front_slot_to_id: dict[int, str] = {}
    back_slot_to_id: dict[int, str] = {}
    id_name_map: dict[str, str] = {}
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

    # 2. Download
    id_to_raw = download_all(list(id_name_map.items()), raw_dir, _cb("download"))

    # 3. Crop + mirror bleed
    total = len(id_to_raw)
    id_to_bled: dict[str, Path] = {}
    for i, (drive_id, raw_path) in enumerate(id_to_raw.items(), start=1):
        id_to_bled[drive_id] = process_for_pdf(raw_path, bled_dir / raw_path.name)
        if progress_callback:
            progress_callback("crop", i, total)

    # 4. Generate PDF(s)
    ordered_slots = sorted(front_slot_to_id.keys())
    return generate(
        output_dir, base_name, ordered_slots,
        front_slot_to_id, back_slot_to_id, id_to_bled,
        progress_callback=_cb("pdf"),
    )
