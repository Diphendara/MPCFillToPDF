"""PDF generation: page layout, printer marks and chunked output.

Uses PyMuPDF (fitz) instead of ReportLab for significantly faster rendering.
PyMuPDF inserts JPEG images directly as DCTDecode streams without re-encoding,
and reuses image XObjects when the same image appears multiple times.
"""

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import pymupdf

from src.app_settings import (
    DEFAULT_CUT_LINE_COLOR,
    DEFAULT_CUT_LINE_OVER_BACKS,
    DEFAULT_CUT_LINE_OVER_CARDS,
    DEFAULT_CUT_LINE_OVER_FRONTS,
    DEFAULT_CUT_LINE_STYLE,
    DEFAULT_CUT_LINE_WIDTH,
)
from src.cancellation import Cancelled
from src.constants import CARDS_PER_PAGE, COLS, ROWS, ProgressCallback

# A4 dimensions in points (same as reportlab.lib.pagesizes.A4)
A4_W = 595.2755905511812
A4_H = 841.8897637795277


@dataclass(frozen=True)
class CardLayout:
    """Physical trim grid used for a PDF page."""

    card_w: float
    card_h: float
    margin_x: float
    margin_y: float
    gap_x: float
    gap_y: float

    @property
    def trim_size_mm(self) -> tuple[float, float]:
        """Trim dimensions shared with image processing, in millimetres."""
        mm = 72 / 25.4  # 1 mm in points
        return round(self.card_w / mm, 6), round(self.card_h / mm, 6)


# 1 mm in points
mm = 72 / 25.4

# Standard MPC / Magic-compatible grid.
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

PAGE_W, PAGE_H = A4_W, A4_H

# Gap between adjacent card trims — derived so the target margins are exact.
# Horizontal and vertical gaps can differ slightly to satisfy both margins.
GAP_X = (PAGE_W - 2 * MARGIN_X - COLS * CARD_W) / (COLS - 1)
GAP_Y = (PAGE_H - 2 * MARGIN_Y - ROWS * CARD_H) / (ROWS - 1)

STANDARD_LAYOUT = CardLayout(CARD_W, CARD_H, MARGIN_X, MARGIN_Y, GAP_X, GAP_Y)

# Yu-Gi-Oh! cards are 59 x 86 mm. This remains a 3 x 3 grid, but with
# dedicated gaps and margins so its cuts do not share the MPC-sized grid.
YUGIOH_LAYOUT = CardLayout(59 * mm, 86 * mm, 10.5 * mm, 12.5 * mm, 6 * mm, 7 * mm)


def _trim_origin(col: int, row: int, layout: CardLayout = STANDARD_LAYOUT) -> tuple[float, float]:
    """Bottom-left of a card's trim area (ReportLab convention: y=0 at bottom).

    Kept for backward compatibility with tests. Internally converted to
    PyMuPDF top-left coordinates when rendering.
    """
    x = layout.margin_x + col * (layout.card_w + layout.gap_x)
    y = PAGE_H - layout.margin_y - (row + 1) * layout.card_h - row * layout.gap_y
    return x, y


def _trim_origin_top(
    col: int, row: int, layout: CardLayout = STANDARD_LAYOUT
) -> tuple[float, float]:
    """Top-left of a card's trim area (PyMuPDF convention: y=0 at top)."""
    x = layout.margin_x + col * (layout.card_w + layout.gap_x)
    y = layout.margin_y + row * (layout.card_h + layout.gap_y)
    return x, y


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert '#rrggbb' to (r, g, b) floats in [0, 1]."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255.0, g / 255.0, b / 255.0


def _insert_image(
    page: pymupdf.Page,
    image_xrefs: dict[str, int],
    img_path: Path,
    rect: pymupdf.Rect,
) -> None:
    """Place an image, embedding its bytes only the first time per document.

    Subsequent placements reuse the same XObject (xref), so repeated cards
    and front/back pairs add no extra image data to the PDF. The original
    JPEG/PNG stream is embedded as-is (no recompression).
    """
    key = str(img_path)
    xref = image_xrefs.get(key, 0)
    if xref == 0:
        # First placement embeds the source stream and returns its xref.
        # keep_proportion=False matches ReportLab's drawImage: the image
        # fills the rect exactly (card images are pre-sized by the cropper).
        xref = page.insert_image(rect, filename=key, keep_proportion=False)
        image_xrefs[key] = xref
    else:
        page.insert_image(rect, xref=xref, keep_proportion=False)


def _draw_crop_marks(
    page: pymupdf.Page,
    layout: CardLayout = STANDARD_LAYOUT,
    color_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0),
    style: str = DEFAULT_CUT_LINE_STYLE,
    line_width: float = DEFAULT_CUT_LINE_WIDTH,
) -> None:
    """Draw trim guides.

    style='ticks': short ticks in page margins only (for print shops).
    style='full': continuous lines spanning the full page (for self-cutting).
    """
    xs = [
        layout.margin_x + col * (layout.card_w + layout.gap_x) + dx
        for col in range(COLS)
        for dx in (0.0, layout.card_w)
    ]
    ys = [
        layout.margin_y + row * (layout.card_h + layout.gap_y) + dy
        for row in range(ROWS)
        for dy in (0.0, layout.card_h)
    ]

    if style == "full":
        for x in xs:
            page.draw_line(
                pymupdf.Point(x, 0), pymupdf.Point(x, PAGE_H), color=color_rgb, width=line_width
            )
        for y in ys:
            page.draw_line(
                pymupdf.Point(0, y), pymupdf.Point(PAGE_W, y), color=color_rgb, width=line_width
            )
    else:
        top_y_end = layout.margin_y - MARK_GAP
        bot_y_end = PAGE_H - layout.margin_y + MARK_GAP
        for x in xs:
            page.draw_line(
                pymupdf.Point(x, 0), pymupdf.Point(x, top_y_end), color=color_rgb, width=line_width
            )
            page.draw_line(
                pymupdf.Point(x, bot_y_end),
                pymupdf.Point(x, PAGE_H),
                color=color_rgb,
                width=line_width,
            )
        left_x_end = layout.margin_x - MARK_GAP
        right_x_end = PAGE_W - layout.margin_x + MARK_GAP
        for y in ys:
            page.draw_line(
                pymupdf.Point(0, y), pymupdf.Point(left_x_end, y), color=color_rgb, width=line_width
            )
            page.draw_line(
                pymupdf.Point(right_x_end, y),
                pymupdf.Point(PAGE_W, y),
                color=color_rgb,
                width=line_width,
            )


def _draw_printer_marks(
    page: pymupdf.Page,
    image_xrefs: dict[str, int],
    page_label: str | None = None,
) -> None:
    """Draw page-corner registration crosshairs plus the CMYK calibration bar.

    Also draws the optional page-pair label (e.g. "1", "1B").
    """
    if CORNER_MARK_PATH.exists():
        s = CORNER_MARK_PT
        for x, y in [(0, 0), (PAGE_W - s, 0), (0, PAGE_H - s), (PAGE_W - s, PAGE_H - s)]:
            rect = pymupdf.Rect(x, y, x + s, y + s)
            _insert_image(page, image_xrefs, CORNER_MARK_PATH, rect)
    if COLOR_BAR_PATH.exists():
        # ReportLab draws the bar at y=PAGE_H-COLOR_BAR_H in bottom-origin
        # coordinates, i.e. flush against the TOP edge -> [0, COLOR_BAR_H] here.
        rect = pymupdf.Rect(COLOR_BAR_X, 0, COLOR_BAR_X + COLOR_BAR_W, COLOR_BAR_H)
        _insert_image(page, image_xrefs, COLOR_BAR_PATH, rect)
    if page_label:
        # ReportLab: drawString(295.4, 15.3, ...) → y=15.3 from bottom
        # PyMuPDF: y from top → PAGE_H - 15.3
        page.insert_text(
            pymupdf.Point(295.4, PAGE_H - 15.3),
            page_label,
            fontsize=8,
            fontname="helv",
            color=(0, 0, 0),
        )


def _draw_page(
    page: pymupdf.Page,
    image_xrefs: dict[str, int],
    slots: list[int | None],
    id_to_path: dict[str, Path],
    slot_to_id: dict[int, str],
    layout: CardLayout = STANDARD_LAYOUT,
    page_label: str | None = None,
    cut_line_color: str = DEFAULT_CUT_LINE_COLOR,
    cut_line_style: str = DEFAULT_CUT_LINE_STYLE,
    cut_line_width: float = DEFAULT_CUT_LINE_WIDTH,
    cut_line_over_cards: bool = DEFAULT_CUT_LINE_OVER_CARDS,
    _valid_paths: set[str] | None = None,
) -> None:
    color_rgb = _hex_to_rgb(cut_line_color)

    if not cut_line_over_cards:
        _draw_crop_marks(page, layout, color_rgb, cut_line_style, cut_line_width)
    _draw_printer_marks(page, image_xrefs, page_label)

    for idx, slot in enumerate(slots):
        col, row = idx % COLS, idx // COLS
        x, y = _trim_origin_top(col, row, layout)
        if slot is not None and slot in slot_to_id:
            img_path = id_to_path.get(slot_to_id[slot])
            if img_path is None:
                continue
            # Use the pre-validated set when available (avoids repeated
            # exists() syscalls); fall back to a direct check otherwise.
            if _valid_paths is not None:
                if str(img_path) not in _valid_paths:
                    continue
            elif not img_path.exists():
                continue
            rect = pymupdf.Rect(
                x - BLEED,
                y - BLEED,
                x - BLEED + layout.card_w + 2 * BLEED,
                y - BLEED + layout.card_h + 2 * BLEED,
            )
            _insert_image(page, image_xrefs, img_path, rect)

    if cut_line_over_cards:
        _draw_crop_marks(page, layout, color_rgb, cut_line_style, cut_line_width)


# Cap each generated PDF at 500 MB on disk (decimal MB, as reported by file
# managers). We aim for 480 MB so the final file stays comfortably under
# 500 MB even when the per-image projection is a few percent off.
MAX_PDF_BYTES = 480 * 1000 * 1000

# Projection factors from on-disk image size to its contribution to the
# final PDF. PyMuPDF embeds JPEG sources as /DCTDecode and PNG sources as
# /FlateDecode without re-encoding (≈1× plus a small object overhead). The
# factors stay deliberately conservative (same values the ReportLab engine
# used) so the chunking phase keeps its historical behaviour; the
# post-render safety net in _fit_chunk guarantees no oversized file is ever
# produced.
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


def _render_chunk(
    path: Path,
    chunk: list[list[int]],
    first_pair_no: int,
    id_to_path: dict[str, Path],
    front_slot_to_id: dict[int, str],
    back_slot_to_id: dict[int, str],
    fronts_only: bool,
    cut_line_color: str,
    cut_line_style: str,
    cut_line_width: float,
    cut_line_over_cards: bool,
    cut_line_over_fronts: bool,
    cut_line_over_backs: bool,
    cancel_event: Event | None,
    layout: CardLayout = STANDARD_LAYOUT,
) -> None:
    """Write a duplex-safe chunk, preserving its original global page labels."""
    # Pre-validate image paths once per chunk to avoid per-slot exists() syscalls.
    _valid: set[str] = {str(p) for p in id_to_path.values() if p.exists()}
    image_xrefs: dict[str, int] = {}

    doc = pymupdf.open()
    try:
        for page_index, page_slots in enumerate(chunk):
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled()
            pair_no = first_pair_no + page_index
            padded = page_slots + [None] * (CARDS_PER_PAGE - len(page_slots))

            front_over = cut_line_over_cards and cut_line_over_fronts
            front_style = (
                cut_line_style if (not cut_line_over_cards or cut_line_over_fronts) else "ticks"
            )
            page = doc.new_page(width=PAGE_W, height=PAGE_H)
            _draw_page(
                page,
                image_xrefs,
                padded,
                id_to_path,
                front_slot_to_id,
                layout,
                page_label=str(pair_no),
                cut_line_color=cut_line_color,
                cut_line_style=front_style,
                cut_line_width=cut_line_width,
                cut_line_over_cards=front_over,
                _valid_paths=_valid,
            )

            if not fronts_only:
                mirrored = []
                for row in range(ROWS):
                    mirrored.extend(reversed(padded[row * COLS : (row + 1) * COLS]))

                back_over = cut_line_over_cards and cut_line_over_backs
                back_style = (
                    cut_line_style if (not cut_line_over_cards or cut_line_over_backs) else "ticks"
                )
                page = doc.new_page(width=PAGE_W, height=PAGE_H)
                _draw_page(
                    page,
                    image_xrefs,
                    mirrored,
                    id_to_path,
                    back_slot_to_id,
                    layout,
                    page_label=f"{pair_no}B",
                    cut_line_color=cut_line_color,
                    cut_line_style=back_style,
                    cut_line_width=cut_line_width,
                    cut_line_over_cards=back_over,
                    _valid_paths=_valid,
                )
        doc.save(str(path), deflate=True, garbage=3)
    finally:
        doc.close()


def generate(
    output_dir: str | Path,
    base_name: str,
    ordered_slots: list[int],
    front_slot_to_id: dict[int, str],
    back_slot_to_id: dict[int, str],
    id_to_path: dict[str, Path],
    max_bytes: int = MAX_PDF_BYTES,
    progress_callback: ProgressCallback = None,
    cancel_event: Event | None = None,
    fronts_only: bool = False,
    cut_line_color: str = DEFAULT_CUT_LINE_COLOR,
    cut_line_style: str = DEFAULT_CUT_LINE_STYLE,
    cut_line_width: float = DEFAULT_CUT_LINE_WIDTH,
    cut_line_over_cards: bool = DEFAULT_CUT_LINE_OVER_CARDS,
    cut_line_over_fronts: bool = DEFAULT_CUT_LINE_OVER_FRONTS,
    cut_line_over_backs: bool = DEFAULT_CUT_LINE_OVER_BACKS,
    layout: CardLayout = STANDARD_LAYOUT,
    fallback_base_name: str | None = None,
) -> list[Path]:
    """Generate one or more PDFs in `output_dir`.

    A new chunk starts after every front/back pair whose addition would push
    the cumulative image bytes past `max_bytes` — i.e. we always cut on an
    even page so each chunk is independently duplex-ready.

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

    def _estimate_chunk_bytes(chunk: list[list[int]]) -> int:
        """Estimate the on-disk PDF size of a chunk without rendering it.

        Uses the same _projected_pdf_bytes projection as the chunking phase,
        summing only unique image IDs across the whole chunk.
        """
        seen_ids: set[str] = set()
        total = 0
        for page_slots in chunk:
            for drive_id in _pair_drive_ids(page_slots, front_slot_to_id, back_slot_to_id):
                if drive_id not in seen_ids:
                    seen_ids.add(drive_id)
                    total += id_bytes(drive_id)
        return total

    def _fit_chunk(
        chunk: list[list[int]], temp_dir: Path, probe_number: list[int]
    ) -> list[tuple[list[list[int]], Path]]:
        """Render a chunk once and return (chunk, rendered_path) pairs.

        Fast path: if the byte projection says this chunk fits, render it
        exactly once to a temp file and trust the projection (the chunking
        phase already split on projected bytes). If the projection says it
        won't fit, split without rendering.

        Safety net: after rendering, the actual on-disk size is checked. If
        the projection underestimated and the file exceeds max_bytes, the
        chunk is split and each half re-rendered — so a bad projection can
        never produce an oversized PDF.
        """
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()
        if len(chunk) > 1 and _estimate_chunk_bytes(chunk) > max_bytes:
            # Projection says it won't fit — split without rendering.
            midpoint = len(chunk) // 2
            return _fit_chunk(chunk[:midpoint], temp_dir, probe_number) + _fit_chunk(
                chunk[midpoint:], temp_dir, probe_number
            )
        rendered = temp_dir / f"chunk_{probe_number[0]}.pdf"
        probe_number[0] += 1
        _render_chunk(
            rendered,
            chunk,
            1,
            id_to_path,
            front_slot_to_id,
            back_slot_to_id,
            fronts_only,
            cut_line_color,
            cut_line_style,
            cut_line_width,
            cut_line_over_cards,
            cut_line_over_fronts,
            cut_line_over_backs,
            cancel_event,
            layout,
        )
        if rendered.stat().st_size <= max_bytes or len(chunk) == 1:
            return [(chunk, rendered)]
        # Projection underestimated: split and re-render each half.
        rendered.unlink()
        midpoint = len(chunk) // 2
        return _fit_chunk(chunk[:midpoint], temp_dir, probe_number) + _fit_chunk(
            chunk[midpoint:], temp_dir, probe_number
        )

    with TemporaryDirectory(prefix=".mpcfill_pdf_", dir=output_dir) as temp:
        probe_number = [0]
        fitted = [pair for chunk in chunks for pair in _fit_chunk(chunk, Path(temp), probe_number)]

        fitted_chunks = [chunk for chunk, _ in fitted]
        multiple = len(fitted_chunks) > 1
        suffixes = [f"_{idx}" if multiple else "" for idx in range(1, len(fitted_chunks) + 1)]
        use_fallback = fallback_base_name is not None and any(
            _is_windows_invalid_output_path(output_dir / f"{base_name}{suffix}.pdf")
            for suffix in suffixes
        )
        effective_base_name = fallback_base_name if use_fallback else base_name
        outputs: list[Path] = []
        total_pairs = sum(len(chunk) for chunk in fitted_chunks)
        done_pairs = 0
        for idx, (chunk, rendered) in enumerate(fitted, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled()
            suffix = f"_{idx}" if multiple or use_fallback else ""
            path = output_dir / f"{effective_base_name}{suffix}.pdf"
            # The chunk was already rendered exactly once in _fit_chunk;
            # just move the finished file to its final name.
            rendered.replace(path)
            for _ in chunk:
                done_pairs += 1
                if progress_callback:
                    progress_callback(done_pairs, total_pairs)
            outputs.append(path)

    return outputs


def _is_windows_invalid_output_path(path: Path) -> bool:
    return len(path.name) > 255 or len(str(path)) >= 260
