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

    out.paste(ImageOps.flip(img.crop((0, 0, w, by))),          (bx, 0))           # top
    out.paste(ImageOps.flip(img.crop((0, h - by, w, h))),      (bx, nh - by))     # bottom
    out.paste(ImageOps.mirror(img.crop((0, 0, bx, h))),        (0, by))           # left
    out.paste(ImageOps.mirror(img.crop((w - bx, 0, w, h))),    (nw - bx, by))     # right

    # corners: rotate 180° of corresponding corner
    out.paste(img.crop((0,      0,      bx, by)).rotate(180), (0,       0))
    out.paste(img.crop((w - bx, 0,      w,  by)).rotate(180), (nw - bx, 0))
    out.paste(img.crop((0,      h - by, bx, h )).rotate(180), (0,       nh - by))
    out.paste(img.crop((w - bx, h - by, w,  h )).rotate(180), (nw - bx, nh - by))

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
    cw, ch = trimmed.size
    bx = round(cw * BLEED_MM / CARD_W_MM)
    by = round(ch * BLEED_MM / CARD_H_MM)
    bled = _add_mirror_bleed(trimmed, bx, by)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bled.save(output_path)
    return output_path


def crop_image(input_path: str | Path, output_path: str | Path) -> None:
    """Standalone crop to trim size (without bleed)."""
    try:
        img = Image.open(input_path)
    except Exception as exc:
        raise RuntimeError(f"No se puede abrir la imagen '{input_path}': {exc}") from exc
    trimmed = _crop_to_trim(img)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trimmed.save(output_path)
