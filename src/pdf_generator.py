from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# Card trim size
CARD_W = 63.5 * mm
CARD_H = 88.9 * mm

# Mirror bleed added around each card (must match cropper.BLEED_MM)
BLEED = 1.0 * mm

# Full image size (trim + bleed on all 4 sides)
IMAGE_W = CARD_W + 2 * BLEED
IMAGE_H = CARD_H + 2 * BLEED

# Grid
COLS = 3
ROWS = 3
CARDS_PER_PAGE = COLS * ROWS

# Distance from page edge to the card trim line.
# Values taken directly from examples/example.pdf vector coordinates
# (visible white = MARGIN - BLEED = 4.75 mm horizontal, 10.15 mm vertical).
MARGIN_X = 5.75 * mm
MARGIN_Y = 11.15 * mm

# Crop mark style
MARK_W = 0.5

PAGE_W, PAGE_H = A4

# Gap between adjacent card trims — derived so the target margins are exact.
# Horizontal and vertical gaps can differ slightly to satisfy both margins.
GAP_X = (PAGE_W - 2 * MARGIN_X - COLS * CARD_W) / (COLS - 1)
GAP_Y = (PAGE_H - 2 * MARGIN_Y - ROWS * CARD_H) / (ROWS - 1)


def _trim_origin(col: int, row: int) -> tuple[float, float]:
    """Bottom-left of a card's trim area (ReportLab: y=0 at bottom)."""
    x = MARGIN_X + col * (CARD_W + GAP_X)
    y = PAGE_H - MARGIN_Y - (row + 1) * CARD_H - row * GAP_Y
    return x, y


def _white_bands(trim_edges: list[float], page_extent: float) -> list[tuple[float, float]]:
    """Given sorted trim edges along one axis, return the white-space intervals
    where a perpendicular cut line should be visible (page margins + gaps)."""
    edges = sorted(trim_edges)
    bands = [(0.0, edges[0])]
    for i in range(1, len(edges) - 1, 2):
        bands.append((edges[i], edges[i + 1]))
    bands.append((edges[-1], page_extent))
    return bands


def _draw_crop_marks(c: canvas.Canvas) -> None:
    """Cut lines that span the white margins and the gaps between cards,
    forming a continuous trim grid (matches examples/example_2.pdf style)."""
    xs = [MARGIN_X + col * (CARD_W + GAP_X) + dx
          for col in range(COLS) for dx in (0.0, CARD_W)]
    ys = [PAGE_H - MARGIN_Y - (row + 1) * CARD_H - row * GAP_Y + dy
          for row in range(ROWS) for dy in (0.0, CARD_H)]

    y_bands = _white_bands(ys, PAGE_H)
    x_bands = _white_bands(xs, PAGE_W)

    c.saveState()
    c.setLineWidth(MARK_W)
    c.setStrokeColorRGB(0, 0, 0)
    for x in xs:
        for y1, y2 in y_bands:
            c.line(x, y1, x, y2)
    for y in ys:
        for x1, x2 in x_bands:
            c.line(x1, y, x2, y)
    c.restoreState()


def _draw_page(
    c: canvas.Canvas,
    slots: list[int | None],
    id_to_path: dict[str, Path],
    slot_to_id: dict[int, str],
) -> None:
    _draw_crop_marks(c)

    for idx, slot in enumerate(slots):
        col, row = idx % COLS, idx // COLS
        x, y = _trim_origin(col, row)
        if slot is not None and slot in slot_to_id:
            img_path = id_to_path.get(slot_to_id[slot])
            if img_path and img_path.exists():
                c.drawImage(str(img_path),
                            x - BLEED, y - BLEED,
                            width=IMAGE_W, height=IMAGE_H)


# Maximum PDF size before splitting into multiple chunks (bytes).
MAX_PDF_BYTES = 500 * 1024 * 1024


def _pair_drive_ids(
    page_slots: list[int],
    front_slot_to_id: dict[int, str],
    back_slot_to_id: dict[int, str],
) -> set[str]:
    ids: set[str] = set()
    for slot in page_slots:
        for slot_map in (front_slot_to_id, back_slot_to_id):
            drive_id = slot_map.get(slot)
            if drive_id:
                ids.add(drive_id)
    return ids


def generate(
    output_dir: str | Path,
    base_name: str,
    ordered_slots: list[int],
    front_slot_to_id: dict[int, str],
    back_slot_to_id: dict[int, str],
    id_to_path: dict[str, Path],
    max_bytes: int = MAX_PDF_BYTES,
    progress_callback=None,
) -> list[Path]:
    """Generate one or more PDFs in `output_dir`. A new chunk starts after
    every front/back pair whose addition would push the cumulative image
    bytes past `max_bytes` — i.e. we always cut on an even page so each
    chunk is independently duplex-ready.

    Output: `<base_name>.pdf` if a single chunk fits, otherwise
    `<base_name>_1.pdf`, `<base_name>_2.pdf`, …
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = [ordered_slots[i:i + CARDS_PER_PAGE]
             for i in range(0, len(ordered_slots), CARDS_PER_PAGE)]

    def id_bytes(drive_id: str) -> int:
        p = id_to_path.get(drive_id)
        return p.stat().st_size if p and p.exists() else 0

    chunks: list[list[list[int]]] = []
    current: list[list[int]] = []
    seen: set[str] = set()
    current_bytes = 0
    for page_slots in pages:
        pair_ids = _pair_drive_ids(page_slots, front_slot_to_id, back_slot_to_id)
        added = sum(id_bytes(i) for i in pair_ids - seen)
        # Only split when this pair brings new bytes that push us past the
        # cap. A pair that reuses images already in the chunk (added == 0)
        # is free to attach even if the chunk is already at/over the cap.
        if current and added > 0 and current_bytes + added > max_bytes:
            chunks.append(current)
            current = []
            seen = set()
            current_bytes = 0
            added = sum(id_bytes(i) for i in pair_ids)
        current.append(page_slots)
        seen |= pair_ids
        current_bytes += added
    if current:
        chunks.append(current)

    multiple = len(chunks) > 1
    outputs: list[Path] = []
    total_pairs = sum(len(c) for c in chunks)
    done_pairs = 0
    for idx, chunk in enumerate(chunks, start=1):
        suffix = f"_{idx}" if multiple else ""
        path = output_dir / f"{base_name}{suffix}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        for page_slots in chunk:
            padded = page_slots + [None] * (CARDS_PER_PAGE - len(page_slots))

            _draw_page(c, padded, id_to_path, front_slot_to_id)
            c.showPage()

            mirrored = []
            for row in range(ROWS):
                mirrored.extend(reversed(padded[row * COLS:(row + 1) * COLS]))

            _draw_page(c, mirrored, id_to_path, back_slot_to_id)
            c.showPage()

            done_pairs += 1
            if progress_callback:
                progress_callback(done_pairs, total_pairs)
        c.save()
        outputs.append(path)

    return outputs
