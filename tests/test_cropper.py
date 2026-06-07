"""Tests for src/cropper.py — bleed crop and mirror-bleed generation."""
import time
from pathlib import Path

import pytest
from PIL import Image

from src.cropper import (
    BLEED_MM,
    CARD_H_MM,
    CARD_W_MM,
    _BLEED_X,
    _BLEED_Y,
    crop_image,
    process_for_pdf,
)


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


# ─── crop_image ─────────────────────────────────────────────────────────────

def test_crop_image_output_dimensions(tmp_path):
    w, h = 200, 280
    inp = _img(tmp_path / "card.jpg", w, h)
    out = tmp_path / "cropped.jpg"
    crop_image(inp, out)
    bx = round(w * _BLEED_X)
    by = round(h * _BLEED_Y)
    assert Image.open(out).size == (w - 2 * bx, h - 2 * by)


def test_crop_image_smaller_than_input(tmp_path):
    w, h = 300, 420
    inp = _img(tmp_path / "card.jpg", w, h)
    out = tmp_path / "cropped.jpg"
    crop_image(inp, out)
    cw, ch = Image.open(out).size
    assert cw < w and ch < h


def test_crop_image_creates_parent_dirs(tmp_path):
    inp = _img(tmp_path / "card.jpg")
    out = tmp_path / "nested" / "dir" / "cropped.jpg"
    crop_image(inp, out)
    assert out.exists()


def test_crop_image_invalid_raises(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"garbage")
    out = tmp_path / "out.jpg"
    with pytest.raises(RuntimeError, match="abrir"):
        crop_image(bad, out)
