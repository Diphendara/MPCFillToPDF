"""Tests for text_importer module."""

import pytest

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
        assert deck.deck_id == "text-import"
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
            assert card.section in ["legend", "champion", "battlefield", "rune", "maindeck", "sideboard"]

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
