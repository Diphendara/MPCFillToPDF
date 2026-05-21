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


def generate(
    output_path: str | Path,
    ordered_slots: list[int],
    front_slot_to_id: dict[int, str],
    back_slot_to_id: dict[int, str],
    id_to_path: dict[str, Path],
) -> None:
    c = canvas.Canvas(str(output_path), pagesize=A4)

    pages = [ordered_slots[i:i + CARDS_PER_PAGE]
             for i in range(0, len(ordered_slots), CARDS_PER_PAGE)]

    for page_slots in pages:
        padded = page_slots + [None] * (CARDS_PER_PAGE - len(page_slots))

        _draw_page(c, padded, id_to_path, front_slot_to_id)
        c.showPage()

        mirrored = []
        for row in range(ROWS):
            mirrored.extend(reversed(padded[row * COLS:(row + 1) * COLS]))

        _draw_page(c, mirrored, id_to_path, back_slot_to_id)
        c.showPage()

    c.save()
