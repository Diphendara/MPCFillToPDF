from pathlib import Path

from src.parser import parse, CardOrder
from src.downloader import download_all
from src.cropper import process_for_pdf
from src.pdf_generator import generate


def run(
    xml_path: str | Path,
    output_pdf: str | Path,
    work_dir: str | Path = "workdir",
    progress_callback=None,
) -> None:
    """Full pipeline: XML → PDF.

    progress_callback(stage: str, done: int, total: int)
    """
    xml_path = Path(xml_path)
    output_pdf = Path(output_pdf)
    work_dir = Path(work_dir)

    raw_dir  = work_dir / "raw"
    bled_dir = work_dir / "bled"

    def _cb(stage):
        def _inner(done, total):
            if progress_callback:
                progress_callback(stage, done, total)
        return _inner

    # 1. Parse
    order: CardOrder = parse(xml_path)

    # 2. Collect unique images
    id_name_map: dict[str, str] = {}
    for card in order.fronts + order.backs:
        id_name_map[card.drive_id] = card.name
    id_name_map[order.cardback_id] = "cardback.jpg"

    # 3. Download
    id_to_raw = download_all(list(id_name_map.items()), raw_dir, _cb("download"))

    # 4. Crop + mirror bleed
    total = len(id_to_raw)
    id_to_bled: dict[str, Path] = {}
    for i, (drive_id, raw_path) in enumerate(id_to_raw.items(), start=1):
        id_to_bled[drive_id] = process_for_pdf(raw_path, bled_dir / raw_path.name)
        if progress_callback:
            progress_callback("crop", i, total)

    # 5. Build slot → id maps
    front_slot_to_id: dict[int, str] = {}
    for card in order.fronts:
        for slot in card.slots:
            front_slot_to_id[slot] = card.drive_id

    back_slot_to_id: dict[int, str] = {}
    for card in order.backs:
        for slot in card.slots:
            back_slot_to_id[slot] = card.drive_id
    for slot in front_slot_to_id:
        if slot not in back_slot_to_id:
            back_slot_to_id[slot] = order.cardback_id

    ordered_slots = sorted(front_slot_to_id.keys())

    # 6. Generate PDF
    generate(output_pdf, ordered_slots, front_slot_to_id, back_slot_to_id, id_to_bled)
