import logging
from pathlib import Path

from PIL import Image, ImageOps

_log = logging.getLogger(__name__)

# MPC bleed fractions (removed during crop)
_BLEED_X = 0.042
_BLEED_Y = 0.031

# Card trim dimensions in mm (MPC standard)
CARD_W_MM = 63.5
CARD_H_MM = 88.9

# Mirror bleed to add around each trimmed card (mm)
BLEED_MM = 1.0

# Rounded-corner fill: fraction of the shorter side used as corner radius
_CORNER_RADIUS_FRAC = 0.04
# Minimum luminance difference to consider a corner pixel "anomalous"
_CORNER_LUMA_THRESHOLD = 60


def _luminance(r: int, g: int, b: int) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _sample_border_color(
    img: Image.Image,
    corner: str,
    radius: int,
) -> tuple[int, int, int]:
    """Sample the border color near a corner by taking the median of pixels
    along the horizontal and vertical edges just outside the rounded zone."""
    w, h = img.size
    samples: list[tuple[int, int, int]] = []
    # Sample range: from radius to 2*radius along each edge
    lo = radius
    hi = min(2 * radius, min(w, h) // 2)

    if corner == "tl":
        for i in range(lo, hi):
            if i < w:
                samples.append(img.getpixel((i, 0)))
            if i < h:
                samples.append(img.getpixel((0, i)))
    elif corner == "tr":
        for i in range(lo, hi):
            if i < w:
                samples.append(img.getpixel((w - 1 - i, 0)))
            if i < h:
                samples.append(img.getpixel((w - 1, i)))
    elif corner == "bl":
        for i in range(lo, hi):
            if i < w:
                samples.append(img.getpixel((i, h - 1)))
            if i < h:
                samples.append(img.getpixel((0, h - 1 - i)))
    elif corner == "br":
        for i in range(lo, hi):
            if i < w:
                samples.append(img.getpixel((w - 1 - i, h - 1)))
            if i < h:
                samples.append(img.getpixel((w - 1, h - 1 - i)))

    if not samples:
        return (0, 0, 0)
    samples.sort(key=lambda c: _luminance(*c))
    return samples[len(samples) // 2]


def _fill_rounded_corners(img: Image.Image) -> Image.Image:
    """Detect rounded corners and fill them with the nearby border color.

    Scryfall card images have rounded corners with dark/black pixels that
    create artefacts when mirror-bleed is applied.  This function replaces
    those corner pixels with the colour sampled from the adjacent border.
    Images without rounded corners are returned unmodified.
    """
    w, h = img.size
    radius = max(1, round(min(w, h) * _CORNER_RADIUS_FRAC))
    radius_sq = radius * radius

    # Precompute quarter-circle offsets once (integer comparison, no sqrt)
    offsets = [
        (dx, dy)
        for dy in range(radius + 1)
        for dx in range(radius + 1)
        if dx * dx + dy * dy <= radius_sq
    ]

    corner_defs = (
        ("tl", 0, 0, 1, 1),
        ("tr", w - 1, 0, -1, 1),
        ("bl", 0, h - 1, 1, -1),
        ("br", w - 1, h - 1, -1, -1),
    )

    any_filled = False
    pixels = img.load()

    for name, ox, oy, sx, sy in corner_defs:
        border_color = _sample_border_color(img, name, radius)
        border_luma = _luminance(*border_color)
        filled_this = False
        for dx, dy in offsets:
            px = ox + dx * sx
            py = oy + dy * sy
            if not (0 <= px < w and 0 <= py < h):
                continue
            r, g, b = pixels[px, py][:3]
            if abs(_luminance(r, g, b) - border_luma) > _CORNER_LUMA_THRESHOLD:
                pixels[px, py] = border_color
                filled_this = True
        if filled_this:
            any_filled = True

    if any_filled:
        _log.debug("Filled rounded corners")
    return img


def _crop_to_trim(img: Image.Image) -> Image.Image:
    w, h = img.size
    bx = round(w * _BLEED_X)
    by = round(h * _BLEED_Y)
    return img.crop((bx, by, w - bx, h - by))


def _add_mirror_bleed(img: Image.Image, bx: int, by: int) -> Image.Image:
    w, h = img.size
    nw, nh = w + 2 * bx, h + 2 * by
    out = Image.new(img.mode, (nw, nh))

    out.paste(img, (bx, by))

    out.paste(ImageOps.flip(img.crop((0, 0, w, by))), (bx, 0))  # top
    out.paste(ImageOps.flip(img.crop((0, h - by, w, h))), (bx, nh - by))  # bottom
    out.paste(ImageOps.mirror(img.crop((0, 0, bx, h))), (0, by))  # left
    out.paste(ImageOps.mirror(img.crop((w - bx, 0, w, h))), (nw - bx, by))  # right

    # corners: rotate 180° of corresponding corner
    out.paste(img.crop((0, 0, bx, by)).rotate(180), (0, 0))
    out.paste(img.crop((w - bx, 0, w, by)).rotate(180), (nw - bx, 0))
    out.paste(img.crop((0, h - by, bx, h)).rotate(180), (0, nh - by))
    out.paste(img.crop((w - bx, h - by, w, h)).rotate(180), (nw - bx, nh - by))

    return out


def process_for_pdf(
    input_path: str | Path,
    output_path: str | Path,
    crop_borders: bool = True,
) -> Path:
    """Optionally crop MPC bleed, then add mirror bleed. Result is what gets
    placed in the PDF.

    `crop_borders=False` skips the MPC-bleed crop — used for user-supplied
    local images that don't carry the MPC border.

    Skips work when `output_path` already exists and is newer than `input_path`,
    matching the downloader's cache-on-disk behavior.
    """
    output_path = Path(output_path)
    input_path = Path(input_path)
    if output_path.exists() and output_path.stat().st_mtime >= input_path.stat().st_mtime:
        _log.debug("Crop cache hit: %s", output_path.name)
        return output_path
    _log.debug("Cropping: %s (crop_borders=%s)", input_path.name, crop_borders)
    try:
        img = Image.open(input_path).convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"No se puede abrir la imagen '{input_path}': {exc}") from exc
    trimmed = _crop_to_trim(img) if crop_borders else img
    if not crop_borders:
        # Scryfall images may have rounded corners with dark pixels
        trimmed = _fill_rounded_corners(trimmed)
    cw, ch = trimmed.size
    bx = round(cw * BLEED_MM / CARD_W_MM)
    by = round(ch * BLEED_MM / CARD_H_MM)
    bled = _add_mirror_bleed(trimmed, bx, by)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bled.save(output_path)
    return output_path
