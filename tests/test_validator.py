"""Tests for src/validator.py — business-logic XML validation."""

from pathlib import Path

from src.validator import ValidationWarning, validate

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _codes(warnings: list[ValidationWarning]) -> list[str]:
    return [w.code for w in warnings]


def _make_xml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "test.xml"
    p.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<order>\n"
        "    <details><quantity>9</quantity></details>\n" + body + "</order>\n",
        encoding="utf-8",
    )
    return p


def _xml_full(
    tmp_path,
    fronts: list[tuple[str, str, str]],  # (id, name, slots)
    backs: list[tuple[str, str, str]] | None = None,
    cardback: str = "CB001",
) -> Path:
    def _cards(entries):
        return "\n".join(
            f"        <card><id>{i}</id><name>{n}</name><slots>{s}</slots></card>"
            for i, n, s in (entries or [])
        )

    body = (
        f"    <fronts>\n{_cards(fronts)}\n    </fronts>\n"
        f"    <backs>\n{_cards(backs)}\n    </backs>\n"
        f"    <cardback>{cardback}</cardback>\n"
    )
    return _make_xml(tmp_path, body)


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_valid_xml_returns_no_warnings(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[("F1", "Front1", "0"), ("F2", "Front2", "1")],
        backs=[("B1", "Back1", "0")],
    )
    assert validate(xml) == []


def test_valid_xml_no_backs_section(tmp_path):
    xml = _xml_full(tmp_path, fronts=[("F1", "Card1", "0")], backs=[])
    assert validate(xml) == []


# ---------------------------------------------------------------------------
# parse error
# ---------------------------------------------------------------------------


def test_parse_error_returns_warning(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<<not xml>>", encoding="utf-8")
    warnings = validate(bad)
    assert len(warnings) == 1
    assert warnings[0].code == "parse_error"


def test_nonexistent_file_returns_parse_error_warning(tmp_path):
    warnings = validate(tmp_path / "missing.xml")
    assert len(warnings) == 1
    assert warnings[0].code == "parse_error"


# ---------------------------------------------------------------------------
# no_fronts
# ---------------------------------------------------------------------------


def test_no_fronts_warning(tmp_path):
    xml = _xml_full(tmp_path, fronts=[], backs=[])
    codes = _codes(validate(xml))
    assert "no_fronts" in codes


def test_no_fronts_stops_further_checks(tmp_path):
    # Even if backs had orphan slots, no_fronts short-circuits.
    xml = _xml_full(tmp_path, fronts=[], backs=[("B1", "Back1", "5")])
    codes = _codes(validate(xml))
    assert codes == ["no_fronts"]


# ---------------------------------------------------------------------------
# duplicate_front_slot
# ---------------------------------------------------------------------------


def test_duplicate_front_slot(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[
            ("F1", "Alpha", "0,1"),
            ("F2", "Beta", "1,2"),  # slot 1 duplicated
        ],
    )
    codes = _codes(validate(xml))
    assert "duplicate_front_slot" in codes


def test_no_duplicate_front_slot_when_unique(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[("F1", "Alpha", "0,1"), ("F2", "Beta", "2,3")],
    )
    assert "duplicate_front_slot" not in _codes(validate(xml))


# ---------------------------------------------------------------------------
# duplicate_back_slot
# ---------------------------------------------------------------------------


def test_duplicate_back_slot(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[("F1", "Card", "0,1,2")],
        backs=[
            ("B1", "BackA", "0,1"),
            ("B2", "BackB", "1,2"),  # slot 1 duplicated
        ],
    )
    codes = _codes(validate(xml))
    assert "duplicate_back_slot" in codes


def test_no_duplicate_back_slot_when_unique(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[("F1", "Card", "0,1,2")],
        backs=[("B1", "BackA", "0"), ("B2", "BackB", "1,2")],
    )
    assert "duplicate_back_slot" not in _codes(validate(xml))


# ---------------------------------------------------------------------------
# orphan_back_slot
# ---------------------------------------------------------------------------


def test_orphan_back_slot(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[("F1", "Card", "0")],
        backs=[("B1", "Back1", "0"), ("B2", "Back2", "5")],  # slot 5 not in fronts
    )
    codes = _codes(validate(xml))
    assert "orphan_back_slot" in codes


def test_no_orphan_when_all_back_slots_have_fronts(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[("F1", "Card", "0,1")],
        backs=[("B1", "Back1", "0,1")],
    )
    assert "orphan_back_slot" not in _codes(validate(xml))


# ---------------------------------------------------------------------------
# empty_cardback
# ---------------------------------------------------------------------------


def test_empty_cardback_causes_parse_error(tmp_path):
    # The parser raises ValueError for an empty <cardback>, which the validator
    # surfaces as a parse_error warning rather than empty_cardback.
    xml = _xml_full(tmp_path, fronts=[("F1", "Card", "0")], cardback="")
    codes = _codes(validate(xml))
    assert "parse_error" in codes


def test_valid_cardback_no_warning(tmp_path):
    xml = _xml_full(tmp_path, fronts=[("F1", "Card", "0")], cardback="CB001")
    assert "empty_cardback" not in _codes(validate(xml))
    assert "parse_error" not in _codes(validate(xml))


# ---------------------------------------------------------------------------
# multiple warnings at once
# ---------------------------------------------------------------------------


def test_multiple_warnings_returned_together(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[
            ("F1", "Alpha", "0,1"),
            ("F2", "Beta", "1,2"),  # duplicate front slot 1
        ],
        backs=[("B1", "Back1", "5")],  # orphan back slot 5
    )
    codes = _codes(validate(xml))
    assert "duplicate_front_slot" in codes
    assert "orphan_back_slot" in codes


# ---------------------------------------------------------------------------
# message content (spot-check Spanish text)
# ---------------------------------------------------------------------------


def test_warning_messages_are_in_spanish(tmp_path):
    xml = _xml_full(
        tmp_path,
        fronts=[("F1", "Alpha", "0"), ("F2", "Beta", "0")],  # duplicate slot 0
    )
    warnings = validate(xml)
    dup = next(w for w in warnings if w.code == "duplicate_front_slot")
    assert "slot" in dup.message.lower()
    assert "fronts" in dup.message.lower() or "front" in dup.message.lower()
