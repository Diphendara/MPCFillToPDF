"""Image cropping and mirror-bleed generation for print-ready cards."""

import logging
from pathlib import Path

import numpy as np
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
    """Sample the border color near a corner by taking the median of pixels.

    Samples along the horizontal and vertical edges just outside the rounded zone.
    Vectorized with numpy for performance.
    """
    w, h = img.size
    arr = np.asarray(img)
    # Sample range: from radius to 2*radius along each edge
    lo = radius
    hi = min(2 * radius, min(w, h) // 2)
    if lo >= hi:
        return (0, 0, 0)

    idx = np.arange(lo, hi)
    if corner == "tl":
        h_samples = arr[0, idx[idx < w]]
        v_samples = arr[idx[idx < h], 0]
    elif corner == "tr":
        h_samples = arr[0, w - 1 - idx[idx < w]]
        v_samples = arr[idx[idx < h], w - 1]
    elif corner == "bl":
        h_samples = arr[h - 1, idx[idx < w]]
        v_samples = arr[h - 1 - idx[idx < h], 0]
    else:  # "br"
        h_samples = arr[h - 1, w - 1 - idx[idx < w]]
        v_samples = arr[h - 1 - idx[idx < h], w - 1]

    samples = np.concatenate([h_samples, v_samples])
    if samples.size == 0:
        return (0, 0, 0)
    # Median by luminance (same ordering as before, but vectorized)
    luma = 0.299 * samples[:, 0] + 0.587 * samples[:, 1] + 0.114 * samples[:, 2]
    median_idx = np.argsort(luma, kind="stable")[len(luma) // 2]
    r, g, b = samples[median_idx][:3]
    return (int(r), int(g), int(b))


def _fill_rounded_corners(img: Image.Image) -> Image.Image:
    """Detect rounded corners and fill them with the nearby border color.

    Scryfall card images have rounded corners with dark/black pixels that
    create artefacts when mirror-bleed is applied.  This function replaces
    those corner pixels with the colour sampled from the adjacent border.
    Images without rounded corners are returned unmodified.

    Vectorized with numpy: builds a quarter-circle mask per corner and
    replaces anomalous pixels in one shot instead of per-pixel Python loops.
    """
    w, h = img.size
    radius = max(1, round(min(w, h) * _CORNER_RADIUS_FRAC))

    arr = np.asarray(img).copy()
    # Precompute quarter-circle boolean mask once (radius+1 × radius+1)
    dy, dx = np.mgrid[0 : radius + 1, 0 : radius + 1]
    quarter_mask = (dx * dx + dy * dy) <= radius * radius

    corner_defs = (
        ("tl", 0, 0),
        ("tr", w - 1, 0),
        ("bl", 0, h - 1),
        ("br", w - 1, h - 1),
    )

    any_filled = False
    for name, ox, oy in corner_defs:
        border_color = _sample_border_color(img, name, radius)
        border_luma = _luminance(*border_color)

        # Slice the corner region from the array (top-left origin of the region)
        if name == "tl":
            y0, x0 = 0, 0
            region = arr[y0 : y0 + radius + 1, x0 : x0 + radius + 1]
            mask = quarter_mask
        elif name == "tr":
            y0, x0 = 0, w - 1 - radius
            region = arr[y0 : y0 + radius + 1, x0 : x0 + radius + 1]
            mask = quarter_mask[:, ::-1]  # flip horizontally
        elif name == "bl":
            y0, x0 = h - 1 - radius, 0
            region = arr[y0 : y0 + radius + 1, x0 : x0 + radius + 1]
            mask = quarter_mask[::-1, :]  # flip vertically
        else:  # "br"
            y0, x0 = h - 1 - radius, w - 1 - radius
            region = arr[y0 : y0 + radius + 1, x0 : x0 + radius + 1]
            mask = quarter_mask[::-1, ::-1]  # flip both

        if region.shape[0] == 0 or region.shape[1] == 0:
            continue
        # Clamp mask to actual region size (edges of very small images)
        mh, mw = region.shape[:2]
        mask = mask[:mh, :mw]

        # Luminance of every pixel in the region, vectorized
        region_luma = 0.299 * region[:, :, 0] + 0.587 * region[:, :, 1] + 0.114 * region[:, :, 2]
        anomalous = mask & (np.abs(region_luma - border_luma) > _CORNER_LUMA_THRESHOLD)
        if anomalous.any():
            region[anomalous] = border_color
            any_filled = True

    if any_filled:
        _log.debug("Filled rounded corners")
        return Image.fromarray(arr)
    return img


def _crop_to_trim(img: Image.Image) -> Image.Image:
    w, h = img.size
    bx = round(w * _BLEED_X)
    by = round(h * _BLEED_Y)
    return img.crop((bx, by, w - bx, h - by))


def _fit_to_card_aspect(img: Image.Image, card_w_mm: float, card_h_mm: float) -> Image.Image:
    """Center-crop a non-standard card image to its physical trim proportion."""
    w, h = img.size
    target_ratio = card_w_mm / card_h_mm
    image_ratio = w / h
    if abs(image_ratio - target_ratio) < 0.001:
        return img
    if image_ratio > target_ratio:
        target_width = round(h * target_ratio)
        left = (w - target_width) // 2
        return img.crop((left, 0, left + target_width, h))
    target_height = round(w / target_ratio)
    top = (h - target_height) // 2
    return img.crop((0, top, w, top + target_height))


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
    card_w_mm: float = CARD_W_MM,
    card_h_mm: float = CARD_H_MM,
) -> Path:
    """Optionally crop MPC bleed, then add mirror bleed.

    The result is what gets placed in the PDF.

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
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        # OSError covers FileNotFoundError and PIL.UnidentifiedImageError.
        raise RuntimeError(f"No se puede abrir la imagen '{input_path}': {exc}") from exc
    trimmed = _crop_to_trim(img) if crop_borders else img
    if not crop_borders:
        # Scryfall images may have rounded corners with dark pixels
        trimmed = _fill_rounded_corners(trimmed)
    if (card_w_mm, card_h_mm) != (CARD_W_MM, CARD_H_MM):
        trimmed = _fit_to_card_aspect(trimmed, card_w_mm, card_h_mm)
    cw, ch = trimmed.size
    bx = round(cw * BLEED_MM / card_w_mm)
    by = round(ch * BLEED_MM / card_h_mm)
    bled = _add_mirror_bleed(trimmed, bx, by)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        bled.save(output_path, quality=95, optimize=True)
    elif suffix == ".png":
        bled.save(output_path, optimize=True)
    else:
        bled.save(output_path)
    return output_path
