from pathlib import Path
from threading import Event

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from src.app_settings import (
    DEFAULT_CUT_LINE_COLOR,
    DEFAULT_CUT_LINE_OVER_BACKS,
    DEFAULT_CUT_LINE_OVER_CARDS,
    DEFAULT_CUT_LINE_OVER_FRONTS,
    DEFAULT_CUT_LINE_STYLE,
    DEFAULT_CUT_LINE_WIDTH,
)
from src.cancellation import Cancelled
from src.constants import CARDS_PER_PAGE, COLS, ROWS

# Card trim size
CARD_W = 63.5 * mm
CARD_H = 88.9 * mm

# Mirror bleed added around each card (must match cropper.BLEED_MM)
BLEED = 1.0 * mm

# Full image size (trim + bleed on all 4 sides)
IMAGE_W = CARD_W + 2 * BLEED
IMAGE_H = CARD_H + 2 * BLEED

# Distance from page edge to the card trim line.
# Values taken directly from examples/example.pdf vector coordinates
# (visible white = MARGIN - BLEED = 4.75 mm horizontal, 10.15 mm vertical).
MARGIN_X = 5.75 * mm
MARGIN_Y = 11.15 * mm

# Crop mark style — ticks in the page margins
MARK_W = 1.0
MARK_GAP = 3.0  # pt between trim line and tick endpoint

# Printer-mark assets
ASSETS_DIR = Path(__file__).parent / "assets"
CORNER_MARK_PATH = ASSETS_DIR / "corner_mark.png"
CORNER_MARK_PT = 10.0  # 10×10pt registration crosshair at each page corner
COLOR_BAR_PATH = ASSETS_DIR / "color_bar.png"
COLOR_BAR_W, COLOR_BAR_H = 200.0, 15.0  # top-center CMYK calibration bar
COLOR_BAR_X = 197.64

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


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert '#rrggbb' to (r, g, b) floats in [0, 1]."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255.0, g / 255.0, b / 255.0


def _draw_crop_marks(
    c: canvas.Canvas,
    color_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0),
    style: str = DEFAULT_CUT_LINE_STYLE,
    line_width: float = DEFAULT_CUT_LINE_WIDTH,
) -> None:
    """Draw trim guides.

    style='ticks': short ticks in page margins only (for print shops).
    style='full': continuous lines spanning the full page (for self-cutting).
    """
    xs = [MARGIN_X + col * (CARD_W + GAP_X) + dx for col in range(COLS) for dx in (0.0, CARD_W)]
    ys = [
        PAGE_H - MARGIN_Y - (row + 1) * CARD_H - row * GAP_Y + dy
        for row in range(ROWS)
        for dy in (0.0, CARD_H)
    ]

    c.saveState()
    c.setLineWidth(line_width)
    c.setStrokeColorRGB(*color_rgb)

    if style == "full":
        for x in xs:
            c.line(x, 0, x, PAGE_H)
        for y in ys:
            c.line(0, y, PAGE_W, y)
    else:
        top_y_end = PAGE_H - MARGIN_Y + MARK_GAP
        bot_y_end = MARGIN_Y - MARK_GAP
        for x in xs:
            c.line(x, 0, x, bot_y_end)
            c.line(x, top_y_end, x, PAGE_H)
        left_x_end = MARGIN_X - MARK_GAP
        right_x_end = PAGE_W - MARGIN_X + MARK_GAP
        for y in ys:
            c.line(0, y, left_x_end, y)
            c.line(right_x_end, y, PAGE_W, y)

    c.restoreState()


def _draw_printer_marks(c: canvas.Canvas, page_label: str | None = None) -> None:
    """Page-corner registration crosshairs plus the CMYK calibration bar
    and (optional) page-pair label (e.g. "1", "1B")."""
    if CORNER_MARK_PATH.exists():
        s = CORNER_MARK_PT
        for x, y in [(0, 0), (PAGE_W - s, 0), (0, PAGE_H - s), (PAGE_W - s, PAGE_H - s)]:
            c.drawImage(str(CORNER_MARK_PATH), x, y, width=s, height=s, mask="auto")
    if COLOR_BAR_PATH.exists():
        c.drawImage(
            str(COLOR_BAR_PATH),
            COLOR_BAR_X,
            PAGE_H - COLOR_BAR_H,
            width=COLOR_BAR_W,
            height=COLOR_BAR_H,
            mask="auto",
        )
    if page_label:
        c.saveState()
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(295.4, 15.3, page_label)
        c.restoreState()


def _draw_page(
    c: canvas.Canvas,
    slots: list[int | None],
    id_to_path: dict[str, Path],
    slot_to_id: dict[int, str],
    page_label: str | None = None,
    cut_line_color: str = DEFAULT_CUT_LINE_COLOR,
    cut_line_style: str = DEFAULT_CUT_LINE_STYLE,
    cut_line_width: float = DEFAULT_CUT_LINE_WIDTH,
    cut_line_over_cards: bool = DEFAULT_CUT_LINE_OVER_CARDS,
) -> None:
    color_rgb = _hex_to_rgb(cut_line_color)

    if not cut_line_over_cards:
        _draw_crop_marks(c, color_rgb, cut_line_style, cut_line_width)
    _draw_printer_marks(c, page_label)

    for idx, slot in enumerate(slots):
        col, row = idx % COLS, idx // COLS
        x, y = _trim_origin(col, row)
        if slot is not None and slot in slot_to_id:
            img_path = id_to_path.get(slot_to_id[slot])
            if img_path and img_path.exists():
                c.drawImage(str(img_path), x - BLEED, y - BLEED, width=IMAGE_W, height=IMAGE_H)

    if cut_line_over_cards:
        _draw_crop_marks(c, color_rgb, cut_line_style, cut_line_width)


# Cap each generated PDF at 500 MB on disk (decimal MB, as reported by file
# managers). We aim for 480 MB so the final file stays comfortably under
# 500 MB even when the per-image projection is a few percent off.
MAX_PDF_BYTES = 480 * 1000 * 1000

# Projection factors from on-disk image size to its contribution to the
# final PDF. reportlab keeps JPEG sources as /DCTDecode (≈1× plus a 25%
# ASCII85 overhead), but decodes PNG sources and re-encodes them with
# Flate+ASCII85 — for photographic card art the resulting stream is
# roughly 2× the original PNG.
_PDF_GROWTH = {".jpg": 1.30, ".jpeg": 1.30, ".png": 2.00}
_PDF_GROWTH_DEFAULT = 2.00


def _projected_pdf_bytes(path: Path | None) -> int:
    if not path or not path.exists():
        return 0
    factor = _PDF_GROWTH.get(path.suffix.lower(), _PDF_GROWTH_DEFAULT)
    return int(path.stat().st_size * factor)


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
    cancel_event: Event | None = None,
    fronts_only: bool = False,
    cut_line_color: str = DEFAULT_CUT_LINE_COLOR,
    cut_line_style: str = DEFAULT_CUT_LINE_STYLE,
    cut_line_width: float = DEFAULT_CUT_LINE_WIDTH,
    cut_line_over_cards: bool = DEFAULT_CUT_LINE_OVER_CARDS,
    cut_line_over_fronts: bool = DEFAULT_CUT_LINE_OVER_FRONTS,
    cut_line_over_backs: bool = DEFAULT_CUT_LINE_OVER_BACKS,
) -> list[Path]:
    """Generate one or more PDFs in `output_dir`. A new chunk starts after
    every front/back pair whose addition would push the cumulative image
    bytes past `max_bytes` — i.e. we always cut on an even page so each
    chunk is independently duplex-ready.

    When `fronts_only=True`, only front pages are emitted (no back pages).

    Output: `<base_name>.pdf` if a single chunk fits, otherwise
    `<base_name>_1.pdf`, `<base_name>_2.pdf`, …
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = [
        ordered_slots[i : i + CARDS_PER_PAGE] for i in range(0, len(ordered_slots), CARDS_PER_PAGE)
    ]

    def id_bytes(drive_id: str) -> int:
        return _projected_pdf_bytes(id_to_path.get(drive_id))

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
    pair_no = 0
    for idx, chunk in enumerate(chunks, start=1):
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()
        suffix = f"_{idx}" if multiple else ""
        path = output_dir / f"{base_name}{suffix}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        for page_slots in chunk:
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled()
            pair_no += 1
            padded = page_slots + [None] * (CARDS_PER_PAGE - len(page_slots))

            # When over_cards is active but unchecked for this page type,
            # fall back to ticks-only (margin lines, drawn before images).
            front_over = cut_line_over_cards and cut_line_over_fronts
            front_style = (
                cut_line_style if (not cut_line_over_cards or cut_line_over_fronts) else "ticks"
            )

            _draw_page(
                c,
                padded,
                id_to_path,
                front_slot_to_id,
                page_label=str(pair_no),
                cut_line_color=cut_line_color,
                cut_line_style=front_style,
                cut_line_width=cut_line_width,
                cut_line_over_cards=front_over,
            )
            c.showPage()

            if not fronts_only:
                mirrored = []
                for row in range(ROWS):
                    mirrored.extend(reversed(padded[row * COLS : (row + 1) * COLS]))

                back_over = cut_line_over_cards and cut_line_over_backs
                back_style = (
                    cut_line_style if (not cut_line_over_cards or cut_line_over_backs) else "ticks"
                )

                _draw_page(
                    c,
                    mirrored,
                    id_to_path,
                    back_slot_to_id,
                    page_label=f"{pair_no}B",
                    cut_line_color=cut_line_color,
                    cut_line_style=back_style,
                    cut_line_width=cut_line_width,
                    cut_line_over_cards=back_over,
                )
                c.showPage()

            done_pairs += 1
            if progress_callback:
                progress_callback(done_pairs, total_pairs)
        c.save()
        outputs.append(path)

    return outputs
