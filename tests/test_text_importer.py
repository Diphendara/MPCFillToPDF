"""Tests for text_importer module."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.text_importer import (
    TextImportError,
    build_riftbound_deck_from_text,
    parse_riftbound_text,
)


class TestParseRiftboundText:
    """Tests for parse_riftbound_text function."""

    def test_parse_simple_line(self):
        """Parse a simple card line."""
        text = "3 Sabotage (OGN-156)"
        lines = parse_riftbound_text(text)

        assert len(lines) == 1
        assert lines[0].quantity == 3
        assert lines[0].name == "Sabotage"
        assert lines[0].set_code == "OGN"
        assert lines[0].collector_number == "156"

    def test_parse_multiple_lines(self):
        """Parse multiple card lines."""
        text = """3 Sabotage (OGN-156)
1 Seal of Discord (OGN-204)
2 Rengar - Trophy Hunter (VEN-179)"""
        lines = parse_riftbound_text(text)

        assert len(lines) == 3
        assert lines[0].quantity == 3
        assert lines[1].quantity == 1
        assert lines[2].quantity == 2

    def test_parse_alternate_art_suffix(self):
        """Parse cards with alternate art suffix (e.g., 118A)."""
        text = "1 Elder Dragon (UNL-118A)"
        lines = parse_riftbound_text(text)

        assert len(lines) == 1
        assert lines[0].collector_number == "118A"

    def test_parse_token_code(self):
        """Parse token cards (e.g., T01g)."""
        text = "1 Baron Pit // Gold (UNL-T01g)"
        lines = parse_riftbound_text(text)

        assert len(lines) == 1
        assert lines[0].name == "Baron Pit // Gold"
        assert lines[0].collector_number == "T01G"

    def test_parse_with_empty_lines(self):
        """Parse text with empty lines (should skip them)."""
        text = """3 Sabotage (OGN-156)

1 Seal of Discord (OGN-204)

"""
        lines = parse_riftbound_text(text)

        assert len(lines) == 2

    def test_parse_with_comments(self):
        """Parse text with comment lines (should skip them)."""
        text = """# This is a comment
3 Sabotage (OGN-156)
// Another comment
1 Seal of Discord (OGN-204)"""
        lines = parse_riftbound_text(text)

        assert len(lines) == 2

    def test_parse_case_insensitive(self):
        """Parse codes in different cases."""
        text = "3 Sabotage (ogn-156)"
        lines = parse_riftbound_text(text)

        assert len(lines) == 1
        assert lines[0].set_code == "OGN"
        assert lines[0].collector_number == "156"

    def test_parse_extra_whitespace(self):
        """Parse lines with extra whitespace."""
        text = "  3   Sabotage   (OGN-156)  "
        lines = parse_riftbound_text(text)

        assert len(lines) == 1
        assert lines[0].quantity == 3
        assert lines[0].name == "Sabotage"

    def test_invalid_format_raises_error(self):
        """Invalid format should raise TextImportError."""
        text = "Sabotage OGN-156"  # Missing quantity and parentheses

        with pytest.raises(TextImportError) as exc_info:
            parse_riftbound_text(text)

        assert "Formato no reconocido" in str(exc_info.value)
        assert exc_info.value.line_number == 1

    def test_invalid_quantity_raises_error(self):
        """Zero quantity should raise TextImportError."""
        text = "0 Sabotage (OGN-156)"

        with pytest.raises(TextImportError) as exc_info:
            parse_riftbound_text(text)

        assert "Cantidad inválida" in str(exc_info.value)

    def test_empty_text_raises_error(self):
        """Empty text should raise TextImportError."""
        text = ""

        with pytest.raises(TextImportError) as exc_info:
            parse_riftbound_text(text)

        assert "No se encontraron cartas" in str(exc_info.value)

    def test_only_comments_raises_error(self):
        """Text with only comments should raise TextImportError."""
        text = "# Comment 1\n// Comment 2"

        with pytest.raises(TextImportError) as exc_info:
            parse_riftbound_text(text)

        assert "No se encontraron cartas" in str(exc_info.value)

    def test_complex_card_names(self):
        """Parse cards with complex names."""
        text = """1 Baron Nashor (UNL-147)
1 Baron Nashor (UNL-147A)
1 Baron Pit // Gold (UNL-T01g)
2 Rengar - Trophy Hunter (VEN-179)"""
        lines = parse_riftbound_text(text)

        assert len(lines) == 4
        assert lines[0].name == "Baron Nashor"
        assert lines[1].name == "Baron Nashor"
        assert lines[2].name == "Baron Pit // Gold"
        assert lines[3].name == "Rengar - Trophy Hunter"


class TestBuildRiftboundDeckFromText:
    """Tests for build_riftbound_deck_from_text function."""

    def test_build_deck_basic(self):
        """Build a deck from simple text."""
        text = "3 Sabotage (OGN-156)\n1 Seal of Discord (OGN-204)"
        deck = build_riftbound_deck_from_text(text, deck_name="Test Deck")

        assert deck.name == "Test Deck"
        assert deck.deck_id.startswith("text-import-")
        assert len(deck.cards) == 2
        assert deck.cards[0].name == "Sabotage"
        assert deck.cards[0].quantity == 3
        assert deck.cards[0].card_id == "OGN-156"
        assert deck.cards[1].name == "Seal of Discord"
        assert deck.cards[1].quantity == 1

    def test_build_deck_with_sections(self):
        """Build a deck and verify cards are assigned to sections."""
        text = """1 Elder Dragon (UNL-118A)
3 Sabotage (OGN-156)"""
        deck = build_riftbound_deck_from_text(text)

        # All cards should be assigned to a section
        for card in deck.cards:
            assert card.section in [
                "legend",
                "champion",
                "battlefield",
                "rune",
                "maindeck",
                "sideboard",
            ]

    def test_build_deck_image_urls(self):
        """Verify image URLs are constructed correctly."""
        text = "3 Sabotage (OGN-156)"
        deck = build_riftbound_deck_from_text(text)

        # Image URL should be present and contain the card code
        assert deck.cards[0].image_url
        assert "OGN-156" in deck.cards[0].image_url
        # Should be from dotgg CDN
        assert "dotgg.gg" in deck.cards[0].image_url

    def test_build_deck_default_name(self):
        """Build a deck without specifying a name."""
        text = "3 Sabotage (OGN-156)"
        deck = build_riftbound_deck_from_text(text)

        assert deck.name == "Imported Deck"

    def test_build_deck_total_slots(self):
        """Verify total_slots property works correctly."""
        text = """3 Sabotage (OGN-156)
1 Seal of Discord (OGN-204)
2 Rengar - Trophy Hunter (VEN-179)"""
        deck = build_riftbound_deck_from_text(text)

        assert deck.total_slots == 6  # 3 + 1 + 2


class TestParseMtgText:
    """Tests for parse_mtg_text function."""

    def test_sideboard_cards_marked_as_side_zone(self):
        """Cards after 'Sideboard:' marker get zone='side', not dropped."""
        from src.text_importer import parse_mtg_text

        text = """4 Lightning Bolt
1 Sol Ring
Sideboard:
2 Red Elemental Blast
1 Pyroblast"""
        deck = parse_mtg_text(text)
        by_name = {c.name: c for c in deck.cards}
        assert by_name["Lightning Bolt"].zone == "main"
        assert by_name["Sol Ring"].zone == "main"
        assert by_name["Red Elemental Blast"].zone == "side"
        assert by_name["Pyroblast"].zone == "side"

    def test_sb_marker_also_marks_sideboard(self):
        """The shorter 'SB:' marker works the same as 'Sideboard:'."""
        from src.text_importer import parse_mtg_text

        text = """4 Lightning Bolt
SB:
2 Red Elemental Blast"""
        deck = parse_mtg_text(text)
        by_name = {c.name: c for c in deck.cards}
        assert by_name["Lightning Bolt"].zone == "main"
        assert by_name["Red Elemental Blast"].zone == "side"

    def test_sideboard_marker_case_insensitive(self):
        """Marker matching is case-insensitive."""
        from src.text_importer import parse_mtg_text

        text = """4 Lightning Bolt
sideboard:
2 Red Elemental Blast"""
        deck = parse_mtg_text(text)
        by_name = {c.name: c for c in deck.cards}
        assert by_name["Red Elemental Blast"].zone == "side"

    def test_no_sideboard_all_main(self):
        """Without markers every card stays in main zone."""
        from src.text_importer import parse_mtg_text

        text = """4 Lightning Bolt (2ED) 137
1 Sol Ring (CMM) 814"""
        deck = parse_mtg_text(text)
        assert all(c.zone == "main" for c in deck.cards)
        assert len(deck.cards) == 2


class TestParseYgoText:
    """Tests for parse_ygo_text function."""

    @pytest.fixture
    def mock_ygo_resolver(self, monkeypatch):
        """Avoid the YGOPRODeck network call during tests."""
        from unittest.mock import MagicMock

        fake = MagicMock(
            return_value={"blue-eyes white dragon": (89631139, "Blue-Eyes White Dragon")}
        )
        monkeypatch.setattr("src.ygo_scraper._fetch_cards_by_names", fake)
        return fake

    def test_side_and_extra_deck_zones(self, mock_ygo_resolver):
        """Cards after 'Side:'/'Extra:' markers keep their zone, not dropped."""
        from src.text_importer import parse_ygo_text

        text = """3 Blue-Eyes White Dragon
Side:
1 Blue-Eyes White Dragon
Extra:
2 Blue-Eyes White Dragon"""
        deck = parse_ygo_text(text)
        zones = [(c.zone, c.quantity) for c in deck.cards]
        assert zones == [("main", 3), ("side", 1), ("extra", 2)]

    def test_main_only_stays_main(self, mock_ygo_resolver):
        """Without markers every card stays in main zone."""
        from src.text_importer import parse_ygo_text

        deck = parse_ygo_text("3 Blue-Eyes White Dragon")
        assert [(c.zone, c.quantity) for c in deck.cards] == [("main", 3)]

    def test_unresolved_card_raises(self, mock_ygo_resolver):
        """A card not found in YGOPRODeck raises TextImportError."""
        from src.text_importer import parse_ygo_text

        with pytest.raises(TextImportError):
            parse_ygo_text("1 Dark Magician")


class TestParseLorcanaText:
    """Tests for parse_lorcana_text function."""

    def test_parse_simple_line(self):
        """Parse 'Quantity Name' format."""
        from src.text_importer import parse_lorcana_text

        deck = parse_lorcana_text("4 Elsa - Snow Queen")
        assert len(deck.cards) == 1
        assert deck.cards[0].name == "Elsa - Snow Queen"
        assert deck.cards[0].quantity == 4

    def test_parse_with_card_number(self):
        """Parse 'Quantity Name (Number)' format."""
        from src.text_importer import parse_lorcana_text

        deck = parse_lorcana_text("2 Mickey Mouse (1)")
        assert deck.cards[0].name == "Mickey Mouse"
        assert deck.cards[0].card_id == "1"

    def test_parse_multiple_lines(self):
        """Parse several lines at once."""
        from src.text_importer import parse_lorcana_text

        text = """4 Elsa - Snow Queen
2 Mickey Mouse (1)
1 Hades - King of Olympus"""
        deck = parse_lorcana_text(text)
        assert len(deck.cards) == 3
        assert [c.quantity for c in deck.cards] == [4, 2, 1]

    def test_invalid_format_raises(self):
        """A line without quantity raises with line number."""
        from src.text_importer import parse_lorcana_text

        with pytest.raises(TextImportError):
            parse_lorcana_text("4 Elsa - Snow Queen\nElsa - Snow Queen")

    def test_zero_quantity_raises(self):
        """Quantity below 1 raises."""
        from src.text_importer import parse_lorcana_text

        with pytest.raises(TextImportError, match="al menos 1"):
            parse_lorcana_text("0 Elsa - Snow Queen")

    def test_empty_text_raises(self):
        """No cards found raises."""
        from src.text_importer import parse_lorcana_text

        with pytest.raises(TextImportError):
            parse_lorcana_text("   ")

    def test_comments_and_blank_lines_skipped(self):
        """Comments and empty lines are ignored."""
        from src.text_importer import parse_lorcana_text

        text = """# my deck
4 Elsa - Snow Queen

// comment
2 Mickey Mouse (1)"""
        deck = parse_lorcana_text(text)
        assert len(deck.cards) == 2


class TestParseOpText:
    """Tests for parse_op_text function."""

    def test_parse_named_with_code(self):
        """Parse 'Quantity Name (CODE)' format."""
        from src.text_importer import parse_op_text

        deck = parse_op_text("4 Roronoa Zoro (OP01-001)")
        assert deck.cards[0].name == "Roronoa Zoro"
        assert deck.cards[0].card_id == "OP01-001"
        assert deck.cards[0].is_leader is False
        assert deck.cards[0].quantity == 4

    def test_parse_leader(self):
        """Parse '(Leader)' marker."""
        from src.text_importer import parse_op_text

        deck = parse_op_text("1 Monkey D. Luffy (Leader)")
        assert deck.cards[0].name == "Monkey D. Luffy"
        assert deck.cards[0].is_leader is True
        assert deck.cards[0].card_id == ""

    def test_parse_code_only_format(self):
        """Parse '2xOP04-016_r1' compact format."""
        from src.text_importer import parse_op_text

        deck = parse_op_text("2xOP04-016_r1")
        assert deck.cards[0].card_id == "OP04-016_R1"
        assert deck.cards[0].quantity == 2
        assert deck.cards[0].is_leader is False

    def test_invalid_format_raises(self):
        """Unrecognized line raises."""
        from src.text_importer import parse_op_text

        with pytest.raises(TextImportError):
            parse_op_text("garbage line here")

    def test_zero_quantity_raises(self):
        """Quantity below 1 raises."""
        from src.text_importer import parse_op_text

        with pytest.raises(TextImportError, match="al menos 1"):
            parse_op_text("0 Roronoa Zoro (OP01-001)")

    def test_empty_text_raises(self):
        """No cards found raises."""
        from src.text_importer import parse_op_text

        with pytest.raises(TextImportError):
            parse_op_text("")

    def test_comments_and_blank_lines_skipped(self):
        """Comments and empty lines are ignored."""
        from src.text_importer import parse_op_text

        text = """# One Piece deck
1 Monkey D. Luffy (Leader)

4 Roronoa Zoro (OP01-001)"""
        deck = parse_op_text(text)
        assert len(deck.cards) == 2


class TestParseLorcanaText:
    """Tests for parse_lorcana_text function."""

    def test_parse_simple_line(self):
        """Parse 'Quantity Name' format."""
        from src.text_importer import parse_lorcana_text

        deck = parse_lorcana_text("4 Elsa - Snow Queen")
        assert len(deck.cards) == 1
        assert deck.cards[0].name == "Elsa - Snow Queen"
        assert deck.cards[0].quantity == 4

    def test_parse_with_card_number(self):
        """Parse 'Quantity Name (Number)' format."""
        from src.text_importer import parse_lorcana_text

        deck = parse_lorcana_text("2 Mickey Mouse (1)")
        assert deck.cards[0].name == "Mickey Mouse"
        assert deck.cards[0].card_id == "1"

    def test_parse_multiple_lines(self):
        """Parse several lines at once."""
        from src.text_importer import parse_lorcana_text

        text = """4 Elsa - Snow Queen
2 Mickey Mouse (1)
1 Hades - King of Olympus"""
        deck = parse_lorcana_text(text)
        assert len(deck.cards) == 3
        assert [c.quantity for c in deck.cards] == [4, 2, 1]

    def test_invalid_format_raises(self):
        """A line without quantity raises with line number."""
        from src.text_importer import parse_lorcana_text

        with pytest.raises(TextImportError, match="Línea 2"):
            parse_lorcana_text("4 Elsa - Snow Queen\nElsa - Snow Queen")

    def test_zero_quantity_raises(self):
        """Quantity below 1 raises."""
        from src.text_importer import parse_lorcana_text

        with pytest.raises(TextImportError, match="al menos 1"):
            parse_lorcana_text("0 Elsa - Snow Queen")

    def test_empty_text_raises(self):
        """No cards found raises."""
        from src.text_importer import parse_lorcana_text

        with pytest.raises(TextImportError):
            parse_lorcana_text("   ")

    def test_comments_and_blank_lines_skipped(self):
        """Comments and empty lines are ignored."""
        from src.text_importer import parse_lorcana_text

        text = """# my deck
4 Elsa - Snow Queen

// comment
2 Mickey Mouse (1)"""
        deck = parse_lorcana_text(text)
        assert len(deck.cards) == 2


class TestParseOpText:
    """Tests for parse_op_text function."""

    def test_parse_named_with_code(self):
        """Parse 'Quantity Name (CODE)' format."""
        from src.text_importer import parse_op_text

        deck = parse_op_text("4 Roronoa Zoro (OP01-001)")
        assert deck.cards[0].name == "Roronoa Zoro"
        assert deck.cards[0].card_id == "OP01-001"
        assert deck.cards[0].is_leader is False
        assert deck.cards[0].quantity == 4

    def test_parse_leader(self):
        """Parse '(Leader)' marker."""
        from src.text_importer import parse_op_text

        deck = parse_op_text("1 Monkey D. Luffy (Leader)")
        assert deck.cards[0].name == "Monkey D. Luffy"
        assert deck.cards[0].is_leader is True
        assert deck.cards[0].card_id == ""

    def test_parse_code_only_format(self):
        """Parse '2xOP04-016_r1' compact format."""
        from src.text_importer import parse_op_text

        deck = parse_op_text("2xOP04-016_r1")
        assert deck.cards[0].card_id == "OP04-016_R1"
        assert deck.cards[0].quantity == 2
        assert deck.cards[0].is_leader is False

    def test_invalid_format_raises(self):
        """Unrecognized line raises with line number."""
        from src.text_importer import parse_op_text

        with pytest.raises(TextImportError):
            parse_op_text("garbage line here")

    def test_zero_quantity_raises(self):
        """Quantity below 1 raises."""
        from src.text_importer import parse_op_text

        with pytest.raises(TextImportError, match="al menos 1"):
            parse_op_text("0 Roronoa Zoro (OP01-001)")

    def test_empty_text_raises(self):
        """No cards found raises."""
        from src.text_importer import parse_op_text

        with pytest.raises(TextImportError):
            parse_op_text("")

    def test_comments_and_blank_lines_skipped(self):
        """Comments and empty lines are ignored."""
        from src.text_importer import parse_op_text

        text = """# One Piece deck
1 Monkey D. Luffy (Leader)

4 Roronoa Zoro (OP01-001)"""
        deck = parse_op_text(text)
        assert len(deck.cards) == 2


class TestPiltoverTextImport:
    """Tests for build_riftbound_deck_from_piltover_text."""

    @staticmethod
    def _db_response(cards):
        """Mock response for the dotgg getcards endpoint."""
        names = ["id", "name", "image", "type", "supertype"]
        data = [
            [
                c.get("id", ""),
                c.get("name", ""),
                c.get("image", ""),
                c.get("type", []),
                c.get("supertype"),
            ]
            for c in cards
        ]
        resp = MagicMock()
        resp.json.return_value = {"names": names, "data": data}
        resp.raise_for_status.return_value = None
        return resp

    def _build(self, text, cards):
        from src.text_importer import build_riftbound_deck_from_piltover_text

        with patch("src.text_importer.http_get", return_value=self._db_response(cards)):
            return build_riftbound_deck_from_piltover_text(text, "Piltover Deck")

    def test_full_sections_roundtrip(self):
        cards = [
            {"id": "UNL-001", "name": "LeBlanc, Deceiver", "type": ["Legend"]},
            {"id": "UNL-002", "name": "Cull the Weak", "type": ["Spell"]},
            {"id": "UNL-003", "name": "Rune of Vigor", "type": ["Rune"]},
        ]
        deck = self._build(
            "Legend:\n1 LeBlanc, Deceiver\n\nMainDeck:\n3 Cull the Weak\n\nRunes:\n2 Rune of Vigor",
            cards,
        )
        assert deck.name == "Piltover Deck"
        assert deck.deck_id.startswith("text-import-piltover-")
        by_section = {}
        for c in deck.cards:
            by_section.setdefault(c.section, []).append(c)
        assert by_section["legend"][0].name == "LeBlanc, Deceiver"
        assert by_section["maindeck"][0].quantity == 3
        assert by_section["rune"][0].card_id == "UNL-003"

    def test_card_not_in_db_uses_placeholder(self):
        deck = self._build("MainDeck:\n1 Ghost Card", [])
        card = deck.cards[0]
        assert card.card_id == "Ghost Card"
        assert card.image_url == ""
        assert card.card_type == ""
        assert card.card_super is None

    def test_missing_image_constructs_cdn_url(self):
        cards = [{"id": "UNL-009", "name": "No Image Card", "type": ["Spell"]}]
        deck = self._build("MainDeck:\n1 No Image Card", cards)
        assert deck.cards[0].image_url == "https://static.dotgg.gg/riftbound/cards/UNL-009.webp"

    def test_supertype_and_type_string_fallbacks(self):
        cards = [
            {"id": "UNL-010", "name": "Weird Type", "type": "Champion"},
            {"id": "UNL-011", "name": "Super Card", "type": ["Champion"], "supertype": "Legend"},
        ]
        deck = self._build("MainDeck:\n1 Weird Type\nChampion:\n1 Super Card", cards)
        by_name = {c.name: c for c in deck.cards}
        assert by_name["Weird Type"].card_type == "Champion"
        assert by_name["Super Card"].card_super == "Legend"

    def test_unknown_section_header_raises(self):
        with pytest.raises(TextImportError, match="Sección desconocida"):
            self._build("Nonsense:\n1 Card", [])

    def test_card_without_section_raises(self):
        with pytest.raises(TextImportError, match="Carta sin sección"):
            self._build("1 Loose Card", [])

    def test_unrecognized_line_raises(self):
        with pytest.raises(TextImportError, match="Formato no reconocido"):
            self._build("MainDeck:\nno-quantity-here", [])

    def test_invalid_quantity_raises(self):
        with pytest.raises(TextImportError, match="Cantidad inválida"):
            self._build("MainDeck:\n0 Card", [])

    def test_empty_text_raises(self):
        with pytest.raises(TextImportError, match="No se encontraron cartas"):
            self._build("", [])


class TestRiftboundHelpers:
    """Tests for _trpc_get, _search_card_by_code, _fetch_dotgg_cards_db, _get_base_code."""

    def test_trpc_get_builds_url_and_extracts_json(self):
        from src.text_importer import _trpc_get

        resp = MagicMock()
        resp.json.return_value = {"result": {"data": {"json": {"hello": "world"}}}}
        resp.raise_for_status.return_value = None
        with patch("src.text_importer.http_get", return_value=resp) as get:
            out = _trpc_get("cards.search", {"query": "OGN-156"})
        assert out == {"hello": "world"}
        url = get.call_args.args[0]
        assert url.startswith("https://piltoverarchive.com/api/trpc/cards.search?input=")

    def test_search_card_by_code_list_result(self):
        from src.text_importer import _search_card_by_code

        resp = MagicMock()
        resp.json.return_value = {"result": {"data": {"json": [{"id": "OGN-156"}]}}}
        resp.raise_for_status.return_value = None
        with patch("src.text_importer.http_get", return_value=resp):
            assert _search_card_by_code("OGN-156") == {"id": "OGN-156"}

    def test_search_card_by_code_dict_with_cards(self):
        from src.text_importer import _search_card_by_code

        resp = MagicMock()
        resp.json.return_value = {"result": {"data": {"json": {"cards": [{"id": "UNL-118"}]}}}}
        resp.raise_for_status.return_value = None
        with patch("src.text_importer.http_get", return_value=resp):
            assert _search_card_by_code("UNL-118") == {"id": "UNL-118"}

    def test_search_card_by_code_not_found(self):
        from src.text_importer import _search_card_by_code

        resp = MagicMock()
        resp.json.return_value = {"result": {"data": {"json": []}}}
        resp.raise_for_status.return_value = None
        with patch("src.text_importer.http_get", return_value=resp):
            assert _search_card_by_code("XXX-000") is None

    def test_search_card_by_code_network_error_returns_none(self):
        from src.text_importer import _search_card_by_code

        with patch("src.text_importer.http_get", side_effect=requests.ConnectionError("boom")):
            assert _search_card_by_code("OGN-156") is None

    def test_fetch_dotgg_cards_db_builds_lookup(self):
        from src.text_importer import _fetch_dotgg_cards_db

        resp = MagicMock()
        resp.json.return_value = {
            "names": ["id", "name"],
            "data": [["UNL-118", "Elder Dragon"], ["", "No ID Card"]],
        }
        resp.raise_for_status.return_value = None
        with patch("src.text_importer.http_get", return_value=resp):
            db = _fetch_dotgg_cards_db()
        assert db == {"UNL-118": {"id": "UNL-118", "name": "Elder Dragon"}}

    def test_fetch_dotgg_cards_db_error_returns_empty(self):
        from src.text_importer import _fetch_dotgg_cards_db

        with patch("src.text_importer.http_get", side_effect=requests.Timeout("slow")):
            assert _fetch_dotgg_cards_db() == {}

    def test_get_base_code_variants(self):
        from src.text_importer import _get_base_code

        assert _get_base_code("UNL-118A") == "UNL-118"
        assert _get_base_code("UNL-T01g") == "UNL-T01"
        assert _get_base_code("OGN-156") == "OGN-156"


class TestRiftboundSideboardHeaders:
    def test_side_board_header_marks_sideboard(self):
        text = "Side Board:\n1 Sabotage (OGN-156)"
        lines = parse_riftbound_text(text)
        assert lines[0].is_sideboard is True

    def test_side_header_marks_sideboard(self):
        text = "Side:\n1 Sabotage (OGN-156)"
        lines = parse_riftbound_text(text)
        assert lines[0].is_sideboard is True


class TestBuildRiftboundCodeVariations:
    """Cover the code-variation and sideboard logic in build_riftbound_deck_from_text."""

    def _build(self, text, db):
        with patch("src.text_importer._fetch_dotgg_cards_db", return_value=db):
            return build_riftbound_deck_from_text(text)

    def test_token_code_with_lowercase_g_found(self):
        db = {"UNL-T01g": {"id": "UNL-T01g", "name": "Gold", "type": ["Token"], "image": ""}}
        deck = self._build("1 Gold (UNL-T01g)", db)
        assert deck.cards[0].card_id == "UNL-T01g"
        # No image in DB -> CDN URL built from the DB id
        assert deck.cards[0].image_url == "https://static.dotgg.gg/riftbound/cards/UNL-T01g.webp"

    def test_base_code_fallback_for_variant(self):
        db = {
            "UNL-118": {
                "id": "UNL-118",
                "name": "Elder Dragon",
                "type": ["Unit"],
                "image": "img.webp",
            }
        }
        deck = self._build("1 Elder Dragon (UNL-118A)", db)
        assert deck.cards[0].card_id == "UNL-118"

    def test_unknown_code_falls_back_to_cdn_and_maindeck(self):
        deck = self._build("1 Ghost (XXX-999)", {})
        card = deck.cards[0]
        assert card.section == "maindeck"
        assert card.image_url == "https://static.dotgg.gg/riftbound/cards/XXX-999.webp"

    def test_sideboard_card_gets_sideboard_section_and_sb_variant(self):
        db = {
            "OGN-156": {"id": "OGN-156", "name": "Sabotage", "type": ["Spell"], "image": "img.webp"}
        }
        deck = self._build("Sideboard:\n1 Sabotage (OGN-156)", db)
        card = deck.cards[0]
        assert card.section == "sideboard"
        assert card.variant_id == "OGN-156_sb"


class TestParseMtgRemaining:
    def test_card_without_set_fetches_from_scryfall(self):
        from src.text_importer import parse_mtg_text

        with patch("src.scryfall.fetch_card_by_name", return_value=("neo", "129")) as by_name:
            deck = parse_mtg_text("2 Lightning Bolt")
        assert by_name.called
        assert deck.cards[0].set_code == "neo"
        assert deck.cards[0].collector_number == "129"

    def test_scryfall_error_continues_without_set(self):
        from src.scryfall import ScryfallError
        from src.text_importer import parse_mtg_text

        with patch("src.scryfall.fetch_card_by_name", side_effect=ScryfallError("not found")):
            deck = parse_mtg_text("2 Lightning Bolt")
        assert deck.cards[0].set_code == ""

    def test_scryfall_connection_error_continues_without_set(self):
        from src.text_importer import parse_mtg_text

        with patch("src.scryfall.fetch_card_by_name", side_effect=requests.ConnectionError("down")):
            deck = parse_mtg_text("2 Lightning Bolt")
        assert deck.cards[0].set_code == ""

    def test_hyphenated_collector_splits_set_and_number(self):
        from src.text_importer import parse_mtg_text

        deck = parse_mtg_text("1 Liesa, Shroud of Dusk (PLST) CMR-286")
        assert deck.cards[0].set_code == "cmr"
        assert deck.cards[0].collector_number == "286"

    def test_invalid_line_raises_with_line_number(self):
        from src.text_importer import parse_mtg_text

        with pytest.raises(TextImportError, match="Línea 1"):
            parse_mtg_text("?? nonsense")

    def test_zero_quantity_raises(self):
        from src.text_importer import parse_mtg_text

        with pytest.raises(TextImportError, match="Cantidad inválida"):
            parse_mtg_text("0 Lightning Bolt")

    def test_empty_text_raises(self):
        from src.text_importer import parse_mtg_text

        with pytest.raises(TextImportError, match="No se encontraron cartas"):
            parse_mtg_text("")


class TestParseYgoRemaining:
    def test_line_without_quantity_defaults_to_one(self):
        from src.text_importer import parse_ygo_text

        with patch(
            "src.ygo_scraper._fetch_cards_by_names",
            return_value={"dark magician": (1, "Dark Magician")},
        ):
            deck = parse_ygo_text("Dark Magician")
        assert deck.cards[0].quantity == 1

    def test_side_and_extra_markers(self):
        from src.text_importer import parse_ygo_text

        resolved = {"a": (1, "A"), "b": (2, "B"), "c": (3, "C")}
        with patch("src.ygo_scraper._fetch_cards_by_names", return_value=resolved):
            deck = parse_ygo_text("1 A\nside:\n1 B\nextra:\n1 C")
        zones = {c.name: c.zone for c in deck.cards}
        assert zones == {"A": "main", "B": "side", "C": "extra"}

    def test_symbol_garbage_line_raises(self):
        from src.text_importer import parse_ygo_text

        with pytest.raises(TextImportError, match="Formato no reconocido"):
            parse_ygo_text("!! garbage")

    def test_zero_quantity_raises(self):
        from src.text_importer import parse_ygo_text

        with pytest.raises(TextImportError, match="Cantidad inválida"):
            parse_ygo_text("0 Dark Magician")
