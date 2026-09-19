"""Tests for src/cropper.py — bleed crop and mirror-bleed generation."""

import time
from pathlib import Path

import pytest
from PIL import Image, ImageOps

from src.cropper import (
    _BLEED_X,
    _BLEED_Y,
    BLEED_MM,
    CARD_H_MM,
    CARD_W_MM,
    _add_mirror_bleed,
    _fill_rounded_corners,
    process_for_pdf,
)
from src.pdf_generator import YUGIOH_LAYOUT

# ─── helpers ────────────────────────────────────────────────────────────────


def _img(path: Path, w: int = 200, h: int = 280, color=(180, 80, 40)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color).save(str(path), format="JPEG")
    return path


def _expected_bled_size(w: int, h: int, crop: bool) -> tuple[int, int]:
    if crop:
        bx = round(w * _BLEED_X)
        by = round(h * _BLEED_Y)
        tw, th = w - 2 * bx, h - 2 * by
    else:
        tw, th = w, h
    mx = round(tw * BLEED_MM / CARD_W_MM)
    my = round(th * BLEED_MM / CARD_H_MM)
    return tw + 2 * mx, th + 2 * my


# ─── process_for_pdf ────────────────────────────────────────────────────────


def test_process_for_pdf_creates_output_file(tmp_path):
    inp = _img(tmp_path / "raw" / "card.jpg")
    out = tmp_path / "bled" / "card.jpg"
    result = process_for_pdf(inp, out, crop_borders=True)
    assert result == out
    assert out.exists()


def test_process_for_pdf_output_dimensions_with_crop(tmp_path):
    w, h = 200, 280
    inp = _img(tmp_path / "card.jpg", w, h)
    out = tmp_path / "bled.jpg"
    process_for_pdf(inp, out, crop_borders=True)
    assert Image.open(out).size == _expected_bled_size(w, h, crop=True)


def test_process_for_pdf_output_dimensions_without_crop(tmp_path):
    w, h = 200, 280
    inp = _img(tmp_path / "card.jpg", w, h)
    out = tmp_path / "bled_nocrop.jpg"
    process_for_pdf(inp, out, crop_borders=False)
    assert Image.open(out).size == _expected_bled_size(w, h, crop=False)


def test_process_for_pdf_uses_yugioh_trim_dimensions_for_mirror_bleed(tmp_path):
    inp = _img(tmp_path / "ygo.jpg", 590, 860)
    out = tmp_path / "ygo_bled.jpg"

    process_for_pdf(inp, out, crop_borders=False, card_w_mm=59, card_h_mm=86)

    assert Image.open(out).size == (610, 880)
    assert YUGIOH_LAYOUT.trim_size_mm == (59, 86)


def test_process_for_pdf_center_crops_wide_yugioh_back_to_card_aspect(tmp_path):
    inp = _img(tmp_path / "ygo_back.jpg", 3012, 4210)
    out = tmp_path / "ygo_back_bled.jpg"

    process_for_pdf(inp, out, crop_borders=False, card_w_mm=59, card_h_mm=86)

    trimmed_width = round(4210 * 59 / 86)
    bleed_x = round(trimmed_width / 59)
    bleed_y = round(4210 / 86)
    assert Image.open(out).size == (trimmed_width + 2 * bleed_x, 4210 + 2 * bleed_y)


def test_process_for_pdf_without_crop_is_larger(tmp_path):
    """Skipping the MPC-bleed crop should yield a larger result image."""
    w, h = 200, 280
    inp = _img(tmp_path / "card.jpg", w, h)

    out_crop = tmp_path / "with_crop.jpg"
    out_nocrop = tmp_path / "no_crop.jpg"
    process_for_pdf(inp, out_crop, crop_borders=True)
    process_for_pdf(inp, out_nocrop, crop_borders=False)

    wc, hc = Image.open(out_crop).size
    wn, hn = Image.open(out_nocrop).size
    assert wn > wc and hn > hc


def test_process_for_pdf_cache_hit_skips_work(tmp_path):
    """Output newer than input → file not re-written (mtime unchanged)."""
    inp = _img(tmp_path / "card.jpg")
    out = tmp_path / "bled.jpg"
    process_for_pdf(inp, out, crop_borders=True)
    mtime_first = out.stat().st_mtime
    time.sleep(0.05)
    process_for_pdf(inp, out, crop_borders=True)
    assert out.stat().st_mtime == mtime_first


def test_process_for_pdf_invalid_image_raises(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image at all")
    out = tmp_path / "out.jpg"
    with pytest.raises(RuntimeError, match="abrir"):
        process_for_pdf(bad, out)


def test_process_for_pdf_creates_parent_dirs(tmp_path):
    inp = _img(tmp_path / "card.jpg")
    out = tmp_path / "a" / "b" / "c" / "bled.jpg"
    process_for_pdf(inp, out, crop_borders=True)
    assert out.exists()


# ─── _add_mirror_bleed ──────────────────────────────────────────────────────


def _gradient_image(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    for y in range(h):
        for x in range(w):
            img.putpixel((x, y), (x * 13 % 251 + 1, y * 17 % 251 + 1, (x + y) * 7 % 251 + 1))
    return img


class TestAddMirrorBleed:
    def test_output_size(self):
        img = _gradient_image(10, 12)
        out = _add_mirror_bleed(img, bx=2, by=3)
        assert out.size == (14, 18)

    def test_center_matches_original(self):
        img = _gradient_image(10, 12)
        bx, by = 2, 3
        out = _add_mirror_bleed(img, bx=bx, by=by)
        center = out.crop((bx, by, bx + 10, by + 12))
        assert list(center.getdata()) == list(img.getdata())

    def test_left_bleed_is_mirror_of_left_strip(self):
        img = _gradient_image(10, 12)
        bx, by = 2, 3
        out = _add_mirror_bleed(img, bx=bx, by=by)
        expected = ImageOps.mirror(img.crop((0, 0, bx, 12)))
        actual = out.crop((0, by, bx, by + 12))
        assert list(actual.getdata()) == list(expected.getdata())

    def test_right_bleed_is_mirror_of_right_strip(self):
        img = _gradient_image(10, 12)
        bx, by = 2, 3
        w, h = 10, 12
        nw = w + 2 * bx
        out = _add_mirror_bleed(img, bx=bx, by=by)
        expected = ImageOps.mirror(img.crop((w - bx, 0, w, h)))
        actual = out.crop((nw - bx, by, nw, by + h))
        assert list(actual.getdata()) == list(expected.getdata())

    def test_top_bleed_is_flip_of_top_strip(self):
        img = _gradient_image(10, 12)
        bx, by = 2, 3
        out = _add_mirror_bleed(img, bx=bx, by=by)
        expected = ImageOps.flip(img.crop((0, 0, 10, by)))
        actual = out.crop((bx, 0, bx + 10, by))
        assert list(actual.getdata()) == list(expected.getdata())

    def test_bottom_bleed_is_flip_of_bottom_strip(self):
        img = _gradient_image(10, 12)
        bx, by = 2, 3
        w, h = 10, 12
        nh = h + 2 * by
        out = _add_mirror_bleed(img, bx=bx, by=by)
        expected = ImageOps.flip(img.crop((0, h - by, w, h)))
        actual = out.crop((bx, nh - by, bx + w, nh))
        assert list(actual.getdata()) == list(expected.getdata())


# ─── _fill_rounded_corners ──────────────────────────────────────────────────


def _img_with_rounded_corners(w: int, h: int, border_color, corner_color) -> Image.Image:
    """Create an image with a solid border_color and dark corner_color in the
    corner zones to simulate Scryfall rounded corners."""
    import math

    img = Image.new("RGB", (w, h), border_color)
    radius = max(1, round(min(w, h) * 0.04))
    pixels = img.load()
    # Paint dark arcs in each corner
    corners = [(0, 0, 1, 1), (w - 1, 0, -1, 1), (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)]
    for ox, oy, sx, sy in corners:
        for dy in range(radius):
            for dx in range(radius):
                dist = math.sqrt(dx * dx + dy * dy)
                # Only fill inside the radius (the "rounded" zone)
                if dist <= radius * 0.9:
                    px = ox + dx * sx
                    py = oy + dy * sy
                    if 0 <= px < w and 0 <= py < h:
                        pixels[px, py] = corner_color
    return img


class TestFillRoundedCorners:
    def test_fills_dark_corners(self):
        """Dark corner pixels should be replaced by the border colour."""
        border = (180, 120, 80)
        dark = (5, 5, 5)
        img = _img_with_rounded_corners(200, 280, border, dark)
        result = _fill_rounded_corners(img)
        # Check top-left pixel was filled
        assert result.getpixel((0, 0)) == border

    def test_no_change_on_uniform_image(self):
        """A uniform image without rounded corners should not be modified."""
        color = (150, 100, 60)
        img = Image.new("RGB", (200, 280), color)
        original_data = list(img.getdata())
        result = _fill_rounded_corners(img)
        assert list(result.getdata()) == original_data

    def test_only_corner_zone_is_affected(self):
        """Pixels outside the corner zone should remain untouched."""

        border = (180, 120, 80)
        dark = (5, 5, 5)
        w, h = 200, 280
        img = _img_with_rounded_corners(w, h, border, dark)
        # Sample a pixel safely inside the image but outside any corner zone
        center_x, center_y = w // 2, h // 2
        original = img.getpixel((center_x, center_y))
        _fill_rounded_corners(img)
        assert img.getpixel((center_x, center_y)) == original

    def test_all_four_corners_are_filled(self):
        """All four corners should get their dark pixels replaced."""
        border = (200, 160, 100)
        dark = (0, 0, 0)
        w, h = 200, 280
        img = _img_with_rounded_corners(w, h, border, dark)
        result = _fill_rounded_corners(img)
        # Check one pixel in each corner
        assert result.getpixel((0, 0)) == border
        assert result.getpixel((w - 1, 0)) == border
        assert result.getpixel((0, h - 1)) == border
        assert result.getpixel((w - 1, h - 1)) == border

    def test_process_for_pdf_applies_fill_when_no_crop(self, tmp_path):
        """process_for_pdf with crop_borders=False should fill rounded corners."""
        border = (180, 120, 80)
        dark = (5, 5, 5)
        img = _img_with_rounded_corners(200, 280, border, dark)
        inp = tmp_path / "scryfall.png"
        img.save(str(inp))
        out = tmp_path / "bled.png"
        process_for_pdf(inp, out, crop_borders=False)
        result = Image.open(out)
        # The bled image is larger; the original image starts at (bx, by)
        cw, ch = 200, 280
        bx = round(cw * BLEED_MM / CARD_W_MM)
        by = round(ch * BLEED_MM / CARD_H_MM)
        # The pixel at the original top-left should now be the border color
        assert result.getpixel((bx, by)) == border
