"""Tests for src/parser.py — XML parsing into CardOrder."""
import textwrap
from pathlib import Path

import pytest

from src.parser import parse, CardOrder, CardImage


# ─── helpers ────────────────────────────────────────────────────────────────

def _write(tmp_path: Path, content: str, name: str = "test.xml") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


MINIMAL = """\
    <?xml version="1.0" encoding="utf-8"?>
    <order>
        <details><quantity>9</quantity></details>
        <fronts>
            <card><id>F01</id><name>Card A</name><slots>0, 1, 2</slots></card>
        </fronts>
        <backs/>
        <cardback>CB01</cardback>
    </order>
"""


# ─── basic parsing ───────────────────────────────────────────────────────────

def test_parse_returns_card_order(tmp_path):
    order = parse(_write(tmp_path, MINIMAL))
    assert isinstance(order, CardOrder)


def test_parse_quantity(tmp_path):
    order = parse(_write(tmp_path, MINIMAL))
    assert order.quantity == 9


def test_parse_fronts(tmp_path):
    order = parse(_write(tmp_path, MINIMAL))
    assert len(order.fronts) == 1
    card = order.fronts[0]
    assert isinstance(card, CardImage)
    assert card.drive_id == "F01"
    assert card.name == "Card A"
    assert card.slots == [0, 1, 2]


def test_parse_no_backs_defaults_to_empty(tmp_path):
    order = parse(_write(tmp_path, MINIMAL))
    assert order.backs == []


def test_parse_cardback_id(tmp_path):
    order = parse(_write(tmp_path, MINIMAL))
    assert order.cardback_id == "CB01"


def test_parse_multiple_fronts(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
                <card><id>F02</id><name>B</name><slots>1, 2</slots></card>
            </fronts>
            <backs/>
            <cardback>CB01</cardback>
        </order>
    """
    order = parse(_write(tmp_path, xml))
    assert len(order.fronts) == 2
    assert order.fronts[1].drive_id == "F02"
    assert order.fronts[1].slots == [1, 2]


def test_parse_explicit_backs(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
                <card><id>F02</id><name>B</name><slots>1</slots></card>
            </fronts>
            <backs>
                <card><id>B01</id><name>Back</name><slots>0</slots></card>
            </backs>
            <cardback>CB01</cardback>
        </order>
    """
    order = parse(_write(tmp_path, xml))
    assert len(order.backs) == 1
    assert order.backs[0].drive_id == "B01"
    assert order.backs[0].slots == [0]


# ─── error cases ─────────────────────────────────────────────────────────────

def test_parse_missing_cardback_element(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
            </fronts>
            <backs/>
        </order>
    """
    with pytest.raises(ValueError, match="cardback"):
        parse(_write(tmp_path, xml))


def test_parse_empty_cardback(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
            </fronts>
            <backs/>
            <cardback>   </cardback>
        </order>
    """
    with pytest.raises(ValueError, match="cardback"):
        parse(_write(tmp_path, xml))


def test_parse_missing_drive_id_in_fronts(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id></id><name>A</name><slots>0</slots></card>
            </fronts>
            <backs/>
            <cardback>CB01</cardback>
        </order>
    """
    with pytest.raises(ValueError, match="sin ID"):
        parse(_write(tmp_path, xml))


def test_parse_missing_drive_id_in_backs(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
            </fronts>
            <backs>
                <card><id></id><name>B</name><slots>0</slots></card>
            </backs>
            <cardback>CB01</cardback>
        </order>
    """
    with pytest.raises(ValueError, match="sin ID"):
        parse(_write(tmp_path, xml))


def test_parse_invalid_xml_raises_value_error(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<<< not valid xml >>>", encoding="utf-8")
    with pytest.raises(ValueError, match="inválido"):
        parse(p)


# ─── CardOrder methods ───────────────────────────────────────────────────────

def test_back_for_slot_returns_specific_back(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
                <card><id>F02</id><name>B</name><slots>1</slots></card>
            </fronts>
            <backs>
                <card><id>B01</id><name>Back</name><slots>0</slots></card>
            </backs>
            <cardback>CB01</cardback>
        </order>
    """
    order = parse(_write(tmp_path, xml))
    assert order.back_for_slot(0) == "B01"


def test_back_for_slot_falls_back_to_cardback(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
                <card><id>F02</id><name>B</name><slots>1</slots></card>
            </fronts>
            <backs>
                <card><id>B01</id><name>Back</name><slots>0</slots></card>
            </backs>
            <cardback>CB01</cardback>
        </order>
    """
    order = parse(_write(tmp_path, xml))
    assert order.back_for_slot(1) == "CB01"


def test_all_drive_ids_includes_all_unique_ids(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>F01</id><name>A</name><slots>0</slots></card>
            </fronts>
            <backs>
                <card><id>B01</id><name>Back</name><slots>0</slots></card>
            </backs>
            <cardback>CB01</cardback>
        </order>
    """
    order = parse(_write(tmp_path, xml))
    assert order.all_drive_ids() == {"F01", "B01", "CB01"}


def test_all_drive_ids_no_explicit_backs(tmp_path):
    order = parse(_write(tmp_path, MINIMAL))
    assert order.all_drive_ids() == {"F01", "CB01"}


def test_all_drive_ids_front_used_as_back_not_duplicated(tmp_path):
    xml = """\
        <?xml version="1.0" encoding="utf-8"?>
        <order>
            <details><quantity>9</quantity></details>
            <fronts>
                <card><id>SAME</id><name>A</name><slots>0</slots></card>
            </fronts>
            <backs>
                <card><id>SAME</id><name>A</name><slots>0</slots></card>
            </backs>
            <cardback>CB01</cardback>
        </order>
    """
    order = parse(_write(tmp_path, xml))
    assert order.all_drive_ids() == {"SAME", "CB01"}
