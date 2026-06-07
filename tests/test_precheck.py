"""Tests for src/precheck.py — card analysis, planning, and manifest writing."""
from pathlib import Path

import pytest

from unittest.mock import patch, MagicMock

from src.precheck import (
    CARDS_PER_PAGE,
    XmlReport,
    PdfJob,
    Plan,
    analyze,
    check_drive_access,
    collect_drive_ids,
    format_merge_info,
    format_warning,
    plan,
    write_manifest,
)
from tests.conftest import make_xml


# ─── helpers ────────────────────────────────────────────────────────────────

def _xml(tmp_path: Path, n_cards: int, name: str = "deck") -> Path:
    fronts = [{"id": f"ID{i:04d}", "name": f"Card{i}", "slots": str(i)}
              for i in range(n_cards)]
    return make_xml(tmp_path / f"{name}.xml", fronts)


# ─── analyze ────────────────────────────────────────────────────────────────

def test_analyze_exact_multiple_of_9(tmp_path):
    p = _xml(tmp_path, 9)
    (r,) = analyze([p])
    assert r.cards == 9
    assert r.blanks == 0
    assert not r.has_blanks


def test_analyze_with_leftover_cards(tmp_path):
    p = _xml(tmp_path, 7)
    (r,) = analyze([p])
    assert r.cards == 7
    assert r.blanks == 2
    assert r.has_blanks


def test_analyze_single_card(tmp_path):
    p = _xml(tmp_path, 1)
    (r,) = analyze([p])
    assert r.cards == 1
    assert r.blanks == 8


def test_analyze_multiple_xmls(tmp_path):
    p1 = _xml(tmp_path, 9, "a")
    p2 = _xml(tmp_path, 5, "b")
    reports = analyze([p1, p2])
    assert len(reports) == 2
    assert reports[0].cards == 9
    assert reports[1].cards == 5


def test_analyze_path_stored(tmp_path):
    p = _xml(tmp_path, 3)
    (r,) = analyze([p])
    assert r.path == p


# ─── PdfJob properties ───────────────────────────────────────────────────────

def test_pdfjob_is_merged_single(tmp_path):
    j = PdfJob([tmp_path / "a.xml"], "a", 9)
    assert not j.is_merged


def test_pdfjob_is_merged_multiple(tmp_path):
    j = PdfJob([tmp_path / "a.xml", tmp_path / "b.xml"], "a_b_union", 14)
    assert j.is_merged


def test_pdfjob_total_cards(tmp_path):
    j = PdfJob([tmp_path / "a.xml"], "a", 9, extra_locals=3)
    assert j.total_cards == 12


def test_pdfjob_blanks_zero(tmp_path):
    j = PdfJob([tmp_path / "a.xml"], "a", 9)
    assert j.blanks == 0


def test_pdfjob_blanks_nonzero(tmp_path):
    j = PdfJob([tmp_path / "a.xml"], "a", 7)
    assert j.blanks == 2


def test_pdfjob_display_name_solo(tmp_path):
    j = PdfJob([tmp_path / "a.xml"], "a", 9)
    assert j.display_name == "a.xml"


def test_pdfjob_display_name_merged(tmp_path):
    j = PdfJob([tmp_path / "a.xml", tmp_path / "b.xml"], "merged", 14)
    assert j.display_name == "merged"


# ─── plan ───────────────────────────────────────────────────────────────────

def test_plan_single_aligned_no_merge(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r])
    assert len(p.jobs) == 1
    assert not p.jobs[0].is_merged
    assert not p.has_merge
    assert not p.has_blanks


def test_plan_single_unaligned_solo_job(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 7, 2)
    p = plan([r])
    assert len(p.jobs) == 1
    assert not p.jobs[0].is_merged
    assert p.has_blanks


def test_plan_two_aligned_two_solo_jobs(tmp_path):
    r1 = XmlReport(tmp_path / "a.xml", 9, 0)
    r2 = XmlReport(tmp_path / "b.xml", 18, 0)
    p = plan([r1, r2])
    assert len(p.jobs) == 2
    assert not p.has_merge
    assert not p.has_blanks


def test_plan_two_unaligned_merged_into_one(tmp_path):
    r1 = XmlReport(tmp_path / "a.xml", 7, 2)
    r2 = XmlReport(tmp_path / "b.xml", 5, 4)
    p = plan([r1, r2])
    assert len(p.jobs) == 1
    assert p.jobs[0].is_merged
    assert p.jobs[0].cards == 12
    assert p.has_merge


def test_plan_merged_job_name_contains_union(tmp_path):
    r1 = XmlReport(tmp_path / "alpha.xml", 7, 2)
    r2 = XmlReport(tmp_path / "beta.xml", 5, 4)
    p = plan([r1, r2])
    assert "union" in p.jobs[0].base_name


def test_plan_mixed_aligned_and_unaligned(tmp_path):
    r_aligned = XmlReport(tmp_path / "a.xml", 9, 0)
    r1 = XmlReport(tmp_path / "b.xml", 7, 2)
    r2 = XmlReport(tmp_path / "c.xml", 5, 4)
    p = plan([r_aligned, r1, r2])
    assert len(p.jobs) == 2
    solo_jobs = [j for j in p.jobs if not j.is_merged]
    merge_jobs = [j for j in p.jobs if j.is_merged]
    assert len(solo_jobs) == 1
    assert len(merge_jobs) == 1
    assert solo_jobs[0].cards == 9
    assert merge_jobs[0].cards == 12


def test_plan_locals_added_to_last_job(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r], local_count=3)
    assert p.jobs[-1].extra_locals == 3
    assert p.jobs[-1].total_cards == 12


def test_plan_locals_affect_blanks_calculation(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r], local_count=1)
    # 9 + 1 = 10 cards → 10 % 9 = 1 → blanks = 8
    assert p.jobs[-1].total_cards == 10
    assert p.jobs[-1].blanks == 8


def test_plan_empty_reports(tmp_path):
    p = plan([])
    assert p.jobs == []
    assert not p.has_merge


# ─── format helpers ──────────────────────────────────────────────────────────

def test_format_merge_info_none_when_no_merge(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r])
    assert format_merge_info(p) is None


def test_format_merge_info_contains_xml_names(tmp_path):
    r1 = XmlReport(tmp_path / "alpha.xml", 7, 2)
    r2 = XmlReport(tmp_path / "beta.xml", 5, 4)
    p = plan([r1, r2])
    info = format_merge_info(p)
    assert info is not None
    assert "alpha.xml" in info
    assert "beta.xml" in info


def test_format_warning_none_when_no_blanks(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r])
    assert format_warning(p) is None


def test_format_warning_present_when_blanks_exist(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 7, 2)
    p = plan([r])
    w = format_warning(p)
    assert w is not None
    assert "2" in w  # mentions the blank count


def test_format_warning_mentions_local_count(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r], local_count=1)
    w = format_warning(p)
    assert w is not None
    assert "local" in w


# ─── write_manifest ──────────────────────────────────────────────────────────

def test_write_manifest_returns_none_when_no_merge(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r])
    out = tmp_path / "out"
    out.mkdir()
    assert write_manifest(p, [r], out) is None


def test_write_manifest_no_file_when_no_merge(tmp_path):
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r])
    out = tmp_path / "out"
    out.mkdir()
    write_manifest(p, [r], out)
    assert not (out / "resumen.txt").exists()


def test_write_manifest_creates_file_when_merged(tmp_path):
    r1 = XmlReport(tmp_path / "a.xml", 7, 2)
    r2 = XmlReport(tmp_path / "b.xml", 5, 4)
    p = plan([r1, r2])
    out = tmp_path / "out"
    out.mkdir()
    result = write_manifest(p, [r1, r2], out)
    assert result is not None
    assert result.exists()


def test_write_manifest_content_has_xml_names(tmp_path):
    r1 = XmlReport(tmp_path / "alpha.xml", 7, 2)
    r2 = XmlReport(tmp_path / "beta.xml", 5, 4)
    p = plan([r1, r2])
    out = tmp_path / "out"
    out.mkdir()
    result = write_manifest(p, [r1, r2], out)
    content = result.read_text(encoding="utf-8")
    assert "alpha.xml" in content
    assert "beta.xml" in content


# ─── collect_drive_ids ───────────────────────────────────────────────────────

def test_collect_drive_ids_returns_fronts_backs_cardback(tmp_path):
    p = make_xml(
        tmp_path / "a.xml",
        fronts=[{"id": "F01", "name": "Front", "slots": "0"}],
        backs=[{"id": "B01", "name": "Back", "slots": "0"}],
        cardback_id="CB01",
    )
    pairs = collect_drive_ids([p])
    ids = {did for did, _ in pairs}
    assert ids == {"F01", "B01", "CB01"}


def test_collect_drive_ids_deduplicates(tmp_path):
    p = make_xml(
        tmp_path / "a.xml",
        fronts=[{"id": "SAME", "name": "X", "slots": "0"},
                {"id": "SAME", "name": "X", "slots": "1"}],
        cardback_id="CB01",
    )
    pairs = collect_drive_ids([p])
    ids = [did for did, _ in pairs]
    assert ids.count("SAME") == 1


def test_collect_drive_ids_multiple_xmls(tmp_path):
    p1 = make_xml(tmp_path / "a.xml",
                  fronts=[{"id": "F01", "name": "A", "slots": "0"}],
                  cardback_id="CB01")
    p2 = make_xml(tmp_path / "b.xml",
                  fronts=[{"id": "F02", "name": "B", "slots": "0"}],
                  cardback_id="CB02")
    pairs = collect_drive_ids([p1, p2])
    ids = {did for did, _ in pairs}
    assert {"F01", "F02", "CB01", "CB02"} <= ids


def test_collect_drive_ids_skips_unparseable(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("not xml", encoding="utf-8")
    good = make_xml(tmp_path / "good.xml",
                    fronts=[{"id": "F01", "name": "A", "slots": "0"}],
                    cardback_id="CB01")
    pairs = collect_drive_ids([bad, good])
    ids = {did for did, _ in pairs}
    assert "F01" in ids  # good XML processed; bad XML silently skipped


def test_collect_drive_ids_empty_list():
    assert collect_drive_ids([]) == []


# ─── check_drive_access ──────────────────────────────────────────────────────

def _mock_response(status_code: int):
    r = MagicMock()
    r.status_code = status_code
    r.close = MagicMock()
    return r


def test_check_drive_access_all_ok():
    pairs = [("ID1", "a.jpg"), ("ID2", "b.jpg")]
    with patch("src.precheck.requests.get", return_value=_mock_response(200)):
        result = check_drive_access(pairs)
    assert result == []


def test_check_drive_access_detects_403():
    pairs = [("ID1", "a.jpg"), ("ID2", "b.jpg")]

    def _side_effect(url, **kw):
        return _mock_response(403 if "ID1" in url else 200)

    with patch("src.precheck.requests.get", side_effect=_side_effect):
        result = check_drive_access(pairs)

    assert len(result) == 1
    assert result[0][0] == "ID1"


def test_check_drive_access_detects_404():
    pairs = [("ID1", "a.jpg")]
    with patch("src.precheck.requests.get", return_value=_mock_response(404)):
        result = check_drive_access(pairs)
    assert len(result) == 1


def test_check_drive_access_network_error_not_flagged():
    pairs = [("ID1", "a.jpg")]
    with patch("src.precheck.requests.get", side_effect=Exception("network error")):
        result = check_drive_access(pairs)
    assert result == []  # network errors are not treated as permission failures


def test_check_drive_access_progress_callback(tmp_path):
    calls = []
    pairs = [("ID1", "a.jpg"), ("ID2", "b.jpg"), ("ID3", "c.jpg")]
    with patch("src.precheck.requests.get", return_value=_mock_response(200)):
        check_drive_access(pairs, progress_callback=lambda d, t: calls.append((d, t)))
    assert len(calls) == 3
    assert all(t == 3 for _, t in calls)


def test_check_drive_access_empty_list():
    assert check_drive_access([]) == []


# ─── write_manifest (existing test, kept here) ───────────────────────────────

def test_write_manifest_removes_stale_file(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "resumen.txt"
    stale.write_text("old data", encoding="utf-8")
    r = XmlReport(tmp_path / "a.xml", 9, 0)
    p = plan([r])
    write_manifest(p, [r], out)
    assert not stale.exists()
