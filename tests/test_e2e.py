"""End-to-end integration tests: XML → PDF with structural verification.

Downloads are always mocked; crop and PDF generation use real (tiny) images
so the full pipeline chain is exercised.  PDF structure is verified via raw-
byte inspection — no extra dependency needed.
"""

import re
from pathlib import Path
from unittest.mock import patch

from src.pipeline import run_locals_only, run_plan
from src.precheck import analyze
from src.precheck import plan as make_plan
from tests.conftest import make_rgb_image, make_xml

W, H = 200, 280  # large enough to survive MPC bleed crop


def _img(path: Path, color=(180, 80, 40)) -> Path:
    return make_rgb_image(path, W, H, color)


def _fake_download_all(raw_dir: Path):
    """Mock for src.pipeline.download_all that writes tiny solid-colour JPEGs."""

    def _impl(
        pairs,
        dest_dir,
        progress_callback=None,
        cancel_event=None,
        on_image_done=None,
        on_speed_update=None,
    ):
        result = {}
        for did, name in pairs:
            p = dest_dir / f"{did}.jpg"
            p.parent.mkdir(parents=True, exist_ok=True)
            _img(p)
            result[did] = p
        for i, (did, _) in enumerate(pairs, 1):
            if on_image_done:
                on_image_done(did)
            if progress_callback:
                progress_callback(i, len(pairs))
        return result

    return _impl


# ---------------------------------------------------------------------------
# PDF introspection helpers (no extra deps)
# ---------------------------------------------------------------------------


def _page_count(pdf_path: Path) -> int:
    """Return total page count from the PDF page-tree /Count entry."""
    data = pdf_path.read_bytes()
    counts = [int(m.group(1)) for m in re.finditer(rb"/Count\s+(\d+)", data)]
    return max(counts) if counts else 0


def _page_size(pdf_path: Path) -> tuple[float, float]:
    """Return (width_pt, height_pt) of the first page from its /MediaBox."""
    data = pdf_path.read_bytes()
    m = re.search(rb"/MediaBox\s*\[([^\]]+)\]", data)
    if not m:
        raise ValueError("No /MediaBox found in PDF")
    nums = [float(x) for x in m.group(1).split()]
    return nums[2] - nums[0], nums[3] - nums[1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_single_card_produces_two_pages(tmp_path):
    """1-card XML → PDF with 2 pages (front page + back page)."""
    xml = make_xml(
        tmp_path / "deck.xml",
        fronts=[{"id": "F1", "name": "Card 1", "slots": "0"}],
        cardback_id="CB",
    )
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        pdfs = run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    assert len(pdfs) == 1
    assert pdfs[0].exists() and pdfs[0].stat().st_size > 0
    assert _page_count(pdfs[0]) == 2


def test_pdf_pages_are_a4(tmp_path):
    """Generated pages must be A4 (595.28 × 841.89 pts, ±2 pt tolerance)."""
    xml = make_xml(
        tmp_path / "deck.xml",
        fronts=[{"id": "F1", "name": "Card 1", "slots": "0"}],
        cardback_id="CB",
    )
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        pdfs = run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    w, h = _page_size(pdfs[0])
    assert abs(w - 595.28) < 2, f"Page width {w:.2f} ≠ A4 (595.28 pt)"
    assert abs(h - 841.89) < 2, f"Page height {h:.2f} ≠ A4 (841.89 pt)"


def test_fronts_only_produces_one_page(tmp_path):
    """fronts_only=True → 1 page, no back page."""
    xml = make_xml(
        tmp_path / "deck.xml",
        fronts=[{"id": "F1", "name": "Card 1", "slots": "0"}],
        cardback_id="CB",
    )
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        pdfs = run_plan(p.jobs, tmp_path / "out", tmp_path / "work", fronts_only=True)

    assert _page_count(pdfs[0]) == 1


def test_nine_cards_fit_one_page_pair(tmp_path):
    """9 cards fit on one 3×3 grid → 2 pages total."""
    fronts = [{"id": f"F{i}", "name": f"Card {i}", "slots": str(i)} for i in range(9)]
    xml = make_xml(tmp_path / "deck.xml", fronts=fronts, cardback_id="CB")
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        pdfs = run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    assert len(pdfs) == 1
    assert _page_count(pdfs[0]) == 2


def test_ten_cards_need_two_page_pairs(tmp_path):
    """10 cards overflow onto a second page pair → 4 pages total."""
    fronts = [{"id": f"F{i}", "name": f"Card {i}", "slots": str(i)} for i in range(10)]
    xml = make_xml(tmp_path / "deck.xml", fronts=fronts, cardback_id="CB")
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        pdfs = run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    assert len(pdfs) == 1
    assert _page_count(pdfs[0]) == 4


def test_locals_only_produces_valid_pdf(tmp_path):
    """run_locals_only with 1 front → valid 2-page A4 PDF."""
    front = _img(tmp_path / "front.jpg")
    back = _img(tmp_path / "back.jpg", color=(40, 80, 180))

    pdfs = run_locals_only(
        extra_fronts=[front],
        local_cardback=back,
        output_dir=tmp_path / "out",
        base_name="test",
        work_dir=tmp_path / "work",
    )

    assert len(pdfs) == 1
    assert pdfs[0].exists()
    assert _page_count(pdfs[0]) == 2
    w, h = _page_size(pdfs[0])
    assert abs(w - 595.28) < 2
    assert abs(h - 841.89) < 2


def test_two_xml_jobs_produce_two_pdfs(tmp_path):
    """Two separate XML jobs each emit their own PDF file."""
    xml1 = make_xml(
        tmp_path / "a.xml",
        fronts=[{"id": f"FA{i}", "name": f"A{i}", "slots": str(i)} for i in range(9)],
        cardback_id="CBA",
    )
    xml2 = make_xml(
        tmp_path / "b.xml",
        fronts=[{"id": f"FB{i}", "name": f"B{i}", "slots": str(i)} for i in range(9)],
        cardback_id="CBB",
    )
    reports = analyze([xml1, xml2])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        pdfs = run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    assert len(pdfs) == 2
    for pdf in pdfs:
        assert _page_count(pdf) == 2


def test_crop_cache_reuse(tmp_path):
    """Re-running with existing bled/ cache skips recropping (same output)."""
    xml = make_xml(
        tmp_path / "deck.xml",
        fronts=[{"id": "F1", "name": "Card 1", "slots": "0"}],
        cardback_id="CB",
    )
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        pdfs1 = run_plan(p.jobs, tmp_path / "out1", tmp_path / "work")
        pdfs2 = run_plan(p.jobs, tmp_path / "out2", tmp_path / "work")

    # Both runs succeed without error
    assert pdfs1[0].exists()
    assert pdfs2[0].exists()
    # Same page count on second run (cache was reused correctly)
    assert _page_count(pdfs1[0]) == _page_count(pdfs2[0])
