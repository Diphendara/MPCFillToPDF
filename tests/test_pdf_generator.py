"""Tests for src/pdf_generator.py — PDF layout and chunk splitting."""

import threading
from pathlib import Path

import pytest
from PIL import Image

from src.cancellation import Cancelled
from src.pdf_generator import (
    CARDS_PER_PAGE,
    _pair_drive_ids,
    _projected_pdf_bytes,
    generate,
)

# ─── helpers ────────────────────────────────────────────────────────────────


def _img(path: Path, w: int = 100, h: int = 140, color=(180, 80, 40)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color).save(str(path), format="JPEG")
    return path


def _slot_maps(n: int, front_prefix="F", back_prefix="B"):
    """Return (ordered_slots, front_slot_to_id, back_slot_to_id) for n cards."""
    slots = list(range(n))
    front = {s: f"{front_prefix}{s}" for s in slots}
    back = {s: f"{back_prefix}{s}" for s in slots}
    return slots, front, back


def _id_to_path(front: dict, back: dict, path: Path) -> dict[str, Path]:
    """Map every drive ID in front+back to the same tiny image."""
    result = {}
    for did in {*front.values(), *back.values()}:
        result[did] = path
    return result


# ─── _projected_pdf_bytes ────────────────────────────────────────────────────


def test_projected_pdf_bytes_missing_path():
    assert _projected_pdf_bytes(None) == 0


def test_projected_pdf_bytes_nonexistent_file(tmp_path):
    assert _projected_pdf_bytes(tmp_path / "ghost.jpg") == 0


def test_projected_pdf_bytes_jpeg(tmp_path):
    p = _img(tmp_path / "card.jpg")
    size = p.stat().st_size
    projected = _projected_pdf_bytes(p)
    assert projected == int(size * 1.30)


def test_projected_pdf_bytes_png(tmp_path):
    p = tmp_path / "card.png"
    Image.new("RGB", (50, 70), (100, 150, 200)).save(str(p), format="PNG")
    size = p.stat().st_size
    assert _projected_pdf_bytes(p) == int(size * 2.00)


# ─── _pair_drive_ids ─────────────────────────────────────────────────────────


def test_pair_drive_ids_collects_front_and_back():
    slots, front, back = _slot_maps(3)
    ids = _pair_drive_ids(slots, front, back)
    assert ids == {*front.values(), *back.values()}


def test_pair_drive_ids_empty_slots():
    assert _pair_drive_ids([], {}, {}) == set()


# ─── generate — basic output ─────────────────────────────────────────────────


def test_generate_creates_pdf_file(tmp_path):
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(1)
    id_to_path = _id_to_path(front, back, img)

    results = generate(tmp_path / "out", "deck", slots, front, back, id_to_path)
    assert len(results) == 1
    assert results[0].exists()
    assert results[0].stat().st_size > 0


def test_generate_pdf_named_correctly(tmp_path):
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(1)
    results = generate(
        tmp_path / "out", "mydeck", slots, front, back, _id_to_path(front, back, img)
    )
    assert results[0].name == "out_mydeck.pdf"


def test_generate_creates_output_dir(tmp_path):
    img = _img(tmp_path / "card.jpg")
    out_dir = tmp_path / "nested" / "output"
    slots, front, back = _slot_maps(1)
    generate(out_dir, "deck", slots, front, back, _id_to_path(front, back, img))
    assert out_dir.exists()


def test_generate_no_slots_returns_empty(tmp_path):
    results = generate(tmp_path / "out", "empty", [], {}, {}, {})
    assert results == []


# ─── generate — page counts ──────────────────────────────────────────────────


def test_generate_without_fronts_only_has_two_pages_per_batch(tmp_path):
    """With 1 page-batch: PDF should have 2 pages (front + back)."""
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(CARDS_PER_PAGE)
    results = generate(tmp_path / "out", "deck", slots, front, back, _id_to_path(front, back, img))
    # Use raw PDF bytes to count showPage markers (/Page entries)
    content = results[0].read_bytes()
    # Each page is recorded as a /Page dictionary in the PDF cross-reference.
    # Counting b'/Page' occurrences is a reliable proxy for page count.
    page_count = content.count(b"/Page\n") + content.count(b"/Page\r")
    assert page_count == 2


def test_generate_fronts_only_produces_smaller_file(tmp_path):
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(CARDS_PER_PAGE)
    id_map = _id_to_path(front, back, img)

    r_both = generate(tmp_path / "out_both", "deck", slots, front, back, id_map, fronts_only=False)
    r_fronts = generate(
        tmp_path / "out_fronts", "deck", slots, front, back, id_map, fronts_only=True
    )

    assert r_fronts[0].stat().st_size < r_both[0].stat().st_size


# ─── generate — progress callback ────────────────────────────────────────────


def test_generate_progress_callback_fires_for_each_pair(tmp_path):
    img = _img(tmp_path / "card.jpg")
    # Two full page batches = 2 pairs
    slots, front, back = _slot_maps(CARDS_PER_PAGE * 2)
    id_map = _id_to_path(front, back, img)

    calls = []
    generate(
        tmp_path / "out",
        "deck",
        slots,
        front,
        back,
        id_map,
        progress_callback=lambda d, t: calls.append((d, t)),
    )

    assert len(calls) == 2
    assert calls[-1] == (2, 2)


def test_generate_progress_total_matches_page_count(tmp_path):
    img = _img(tmp_path / "card.jpg")
    n_pages = 3
    slots, front, back = _slot_maps(CARDS_PER_PAGE * n_pages)
    id_map = _id_to_path(front, back, img)

    totals = set()
    generate(
        tmp_path / "out",
        "deck",
        slots,
        front,
        back,
        id_map,
        progress_callback=lambda d, t: totals.add(t),
    )

    assert totals == {n_pages}


# ─── generate — cancellation ─────────────────────────────────────────────────


def test_generate_raises_cancelled_when_event_set(tmp_path):
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(CARDS_PER_PAGE)
    event = threading.Event()
    event.set()

    with pytest.raises(Cancelled):
        generate(
            tmp_path / "out",
            "deck",
            slots,
            front,
            back,
            _id_to_path(front, back, img),
            cancel_event=event,
        )


# ─── generate — chunk splitting ──────────────────────────────────────────────


def test_generate_splits_into_multiple_chunks(tmp_path):
    """Setting max_bytes=1 forces every page pair into its own chunk."""
    img = _img(tmp_path / "card.jpg")
    # Two page batches worth of cards
    slots, front, back = _slot_maps(CARDS_PER_PAGE * 2)
    id_map = _id_to_path(front, back, img)

    results = generate(tmp_path / "out", "deck", slots, front, back, id_map, max_bytes=1)

    assert len(results) == 2


def test_generate_split_files_named_with_index(tmp_path):
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(CARDS_PER_PAGE * 2)
    id_map = _id_to_path(front, back, img)

    results = generate(tmp_path / "out", "deck", slots, front, back, id_map, max_bytes=1)

    names = {r.name for r in results}
    assert "out_deck_1.pdf" in names
    assert "out_deck_2.pdf" in names


def test_generate_no_split_when_under_cap(tmp_path):
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(CARDS_PER_PAGE * 2)
    id_map = _id_to_path(front, back, img)

    results = generate(
        tmp_path / "out", "deck", slots, front, back, id_map, max_bytes=10 * 1000 * 1000 * 1000
    )  # 10 GB cap

    assert len(results) == 1


def test_generate_split_all_files_exist(tmp_path):
    img = _img(tmp_path / "card.jpg")
    slots, front, back = _slot_maps(CARDS_PER_PAGE * 3)
    id_map = _id_to_path(front, back, img)

    results = generate(tmp_path / "out", "deck", slots, front, back, id_map, max_bytes=1)

    for r in results:
        assert r.exists()
        assert r.stat().st_size > 0
