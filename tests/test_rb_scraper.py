"""Tests for src/rb_scraper.py.

Unit tests (no network) cover URL routing, section mapping, expand_deck logic,
and helper functions. Integration tests (marked @pytest.mark.network) hit the
live websites to detect API or format changes.

Run only unit tests:
    pytest tests/test_rb_scraper.py -m "not network"

Run everything including live checks:
    pytest tests/test_rb_scraper.py
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cancellation import Cancelled
from src.rb_scraper import (
    SECTION_ORDER,
    RBCard,
    RBDeck,
    _fs_arr,
    _fs_str,
    _scrape_riftbinder,
    _type_to_section,
    expand_deck,
    scrape_deck,
)

# ---------------------------------------------------------------------------
# Reference deck URLs — kept here so network-test failures pinpoint the site
# ---------------------------------------------------------------------------

URL_PILTOVER = "https://piltoverarchive.com/decks/view/00000000-0000-0000-0000-000000000001"
URL_RIFTMANA = "https://riftmana.com/deck/some-deck"
URL_RIFTBINDER = "https://riftbinder.com/decks/abc123"
URL_RIFTDEX = "https://riftdex.com/deck/00000000-0000-0000-0000-000000000001"
URL_RIFTBOUNDGG = "https://riftbound.gg/decks/some-slug/"


# ---------------------------------------------------------------------------
# Unit tests — URL routing
# ---------------------------------------------------------------------------


class TestScrapedeckRouting:
    def test_unknown_domain_raises(self):
        with pytest.raises(ValueError, match="URL no reconocida"):
            scrape_deck("https://example.com/deck/123")

    def test_piltoverarchive_routes_to_fetch_deck(self):
        with patch("src.rb_scraper._fetch_deck") as mock:
            mock.return_value = MagicMock(spec=RBDeck)
            scrape_deck(
                "https://piltoverarchive.com/decks/view/00000000-0000-0000-0000-000000000001"
            )
            mock.assert_called_once_with("00000000-0000-0000-0000-000000000001")

    def test_piltoverarchive_bad_url_raises(self):
        with pytest.raises(ValueError, match="UUID"):
            scrape_deck("https://piltoverarchive.com/decks/")

    def test_riftmana_routes(self):
        with patch("src.rb_scraper._scrape_riftmana") as mock:
            mock.return_value = MagicMock(spec=RBDeck)
            scrape_deck(URL_RIFTMANA)
            mock.assert_called_once_with(URL_RIFTMANA)

    def test_riftbinder_routes(self):
        with patch("src.rb_scraper._scrape_riftbinder") as mock:
            mock.return_value = MagicMock(spec=RBDeck)
            scrape_deck(URL_RIFTBINDER)
            mock.assert_called_once_with(URL_RIFTBINDER)

    def test_riftdex_routes(self):
        with patch("src.rb_scraper._scrape_riftdex") as mock:
            mock.return_value = MagicMock(spec=RBDeck)
            scrape_deck(URL_RIFTDEX)
            mock.assert_called_once_with(URL_RIFTDEX)

    def test_riftbound_gg_routes(self):
        with patch("src.rb_scraper._scrape_riftbound_gg") as mock:
            mock.return_value = MagicMock(spec=RBDeck)
            scrape_deck(URL_RIFTBOUNDGG)
            mock.assert_called_once_with(URL_RIFTBOUNDGG)


# ---------------------------------------------------------------------------
# Unit tests — _type_to_section
# ---------------------------------------------------------------------------


class TestTypeToSection:
    def test_legend(self):
        assert _type_to_section("Legend") == "legend"

    def test_battlefield(self):
        assert _type_to_section("Battlefield") == "battlefield"

    def test_rune(self):
        assert _type_to_section("Rune") == "rune"

    def test_champion_by_type(self):
        assert _type_to_section("Champion") == "champion"

    def test_champion_by_super(self):
        assert _type_to_section("Unit", "Champion") == "champion"

    def test_unit_is_maindeck(self):
        assert _type_to_section("Unit") == "maindeck"

    def test_spell_is_maindeck(self):
        assert _type_to_section("Spell") == "maindeck"

    def test_empty_is_maindeck(self):
        assert _type_to_section("") == "maindeck"

    def test_case_insensitive(self):
        assert _type_to_section("LEGEND") == "legend"
        assert _type_to_section("battlefield") == "battlefield"


# ---------------------------------------------------------------------------
# Unit tests — Firestore helpers (_fs_str, _fs_arr)
# ---------------------------------------------------------------------------


class TestFirestoreHelpers:
    def test_fs_str_string_value(self):
        assert _fs_str({"stringValue": "hello"}) == "hello"

    def test_fs_str_integer_value(self):
        assert _fs_str({"integerValue": "42"}) == "42"

    def test_fs_str_empty_dict(self):
        assert _fs_str({}) == ""

    def test_fs_arr_returns_values(self):
        field = {"arrayValue": {"values": [{"stringValue": "a"}, {"stringValue": "b"}]}}
        assert _fs_arr(field) == [{"stringValue": "a"}, {"stringValue": "b"}]

    def test_fs_arr_missing_returns_empty(self):
        assert _fs_arr({}) == []

    def test_fs_arr_empty_array(self):
        assert _fs_arr({"arrayValue": {}}) == []


# ---------------------------------------------------------------------------
# Unit tests — _scrape_riftbinder (Firestore mock)
# ---------------------------------------------------------------------------


class TestScrapeRiftbinder:
    def _firestore_response(self) -> dict:
        return {
            "fields": {
                "name": {"stringValue": "Test Deck"},
                "legendId": {"stringValue": "RB-LEGEND-001"},
                "battlefields": {"arrayValue": {"values": [{"stringValue": "RB-BF-001"}]}},
                "runes": {
                    "arrayValue": {
                        "values": [
                            {"mapValue": {"fields": {"runeId": {"stringValue": "RB-RUNE-001"}}}}
                        ]
                    }
                },
                "mainDeck": {
                    "arrayValue": {
                        "values": [
                            {
                                "mapValue": {
                                    "fields": {
                                        "cardId": {"stringValue": "RB-UNIT-001"},
                                        "quantity": {"integerValue": "3"},
                                    }
                                }
                            }
                        ]
                    }
                },
                "sideboard": {
                    "arrayValue": {
                        "values": [
                            {
                                "mapValue": {
                                    "fields": {
                                        "cardId": {"stringValue": "RB-UNIT-002"},
                                        "quantity": {"integerValue": "1"},
                                    }
                                }
                            }
                        ]
                    }
                },
            }
        }

    def test_parses_name(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._firestore_response()
        with patch("src.rb_scraper.requests.get", return_value=mock_resp):
            deck = _scrape_riftbinder("https://riftbinder.com/decks/abc123")
        assert deck.name == "Test Deck"

    def test_parses_legend(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._firestore_response()
        with patch("src.rb_scraper.requests.get", return_value=mock_resp):
            deck = _scrape_riftbinder("https://riftbinder.com/decks/abc123")
        legend_cards = [c for c in deck.cards if c.section == "legend"]
        assert len(legend_cards) == 1
        assert legend_cards[0].card_id == "RB-LEGEND-001"

    def test_parses_battlefield(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._firestore_response()
        with patch("src.rb_scraper.requests.get", return_value=mock_resp):
            deck = _scrape_riftbinder("https://riftbinder.com/decks/abc123")
        bf = [c for c in deck.cards if c.section == "battlefield"]
        assert len(bf) == 1
        assert bf[0].card_id == "RB-BF-001"

    def test_parses_maindeck_quantity(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._firestore_response()
        with patch("src.rb_scraper.requests.get", return_value=mock_resp):
            deck = _scrape_riftbinder("https://riftbinder.com/decks/abc123")
        main = [c for c in deck.cards if c.section == "maindeck"]
        assert len(main) == 1
        assert main[0].quantity == 3

    def test_parses_sideboard(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._firestore_response()
        with patch("src.rb_scraper.requests.get", return_value=mock_resp):
            deck = _scrape_riftbinder("https://riftbinder.com/decks/abc123")
        sb = [c for c in deck.cards if c.section == "sideboard"]
        assert len(sb) == 1

    def test_bad_url_raises(self):
        with pytest.raises(ValueError, match="ID"):
            _scrape_riftbinder("https://riftbinder.com/decks/")


# ---------------------------------------------------------------------------
# Unit tests — RBDeck model
# ---------------------------------------------------------------------------


class TestRBDeckModel:
    def _make_deck(self, cards: list[RBCard]) -> RBDeck:
        return RBDeck(deck_id="test-id", name="Test", cards=cards)

    def _card(self, section: str, qty: int = 1, variant_id: str | None = None) -> RBCard:
        cid = f"RB-{section.upper()}-001"
        return RBCard(
            card_id=cid,
            variant_id=variant_id or cid,
            name="Card",
            card_type=section.capitalize(),
            card_super=None,
            quantity=qty,
            image_url="https://example.com/img.webp",
            section=section,
        )

    def test_total_slots_sums_quantities(self):
        deck = self._make_deck(
            [
                self._card("legend", 1),
                self._card("maindeck", 4),
                self._card("rune", 2),
            ]
        )
        assert deck.total_slots == 7

    def test_by_section_groups_correctly(self):
        legend = self._card("legend")
        main = self._card("maindeck", 3)
        deck = self._make_deck([legend, main])
        grouped = deck.by_section()
        assert grouped["legend"] == [legend]
        assert grouped["maindeck"] == [main]
        assert grouped["battlefield"] == []

    def test_by_section_contains_all_section_keys(self):
        deck = self._make_deck([])
        grouped = deck.by_section()
        assert set(grouped.keys()) == set(SECTION_ORDER)


# ---------------------------------------------------------------------------
# Unit tests — expand_deck
# ---------------------------------------------------------------------------


class TestExpandDeck:
    def _back_map(self, tmp_path: Path) -> dict[str, Path]:
        backs = {}
        for section in ("legend", "battlefield", "rune", "maindeck"):
            p = tmp_path / f"{section}.png"
            p.write_bytes(b"fake")
            backs[section] = p
        return backs

    def _card(self, section: str, qty: int, variant_id: str) -> RBCard:
        return RBCard(
            card_id=variant_id,
            variant_id=variant_id,
            name="Card",
            card_type=section.capitalize(),
            card_super=None,
            quantity=qty,
            image_url="https://example.com/img.webp",
            section=section,
        )

    def test_expands_quantity(self, tmp_path):
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("maindeck", 3, "UNIT-001"),
            ],
        )
        img = tmp_path / "UNIT-001.webp"
        img.write_bytes(b"img")
        backs = self._back_map(tmp_path)
        fronts, per_backs = expand_deck(deck, {"UNIT-001": img}, backs)
        assert len(fronts) == 3
        assert all(f == img for f in fronts)

    def test_legend_uses_legend_back(self, tmp_path):
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("legend", 1, "LEG-001"),
            ],
        )
        img = tmp_path / "LEG-001.webp"
        img.write_bytes(b"img")
        backs = self._back_map(tmp_path)
        _, per_backs = expand_deck(deck, {"LEG-001": img}, backs)
        assert per_backs[0] == backs["legend"]

    def test_rune_uses_rune_back(self, tmp_path):
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("rune", 1, "RUNE-001"),
            ],
        )
        img = tmp_path / "RUNE-001.webp"
        img.write_bytes(b"img")
        backs = self._back_map(tmp_path)
        _, per_backs = expand_deck(deck, {"RUNE-001": img}, backs)
        assert per_backs[0] == backs["rune"]

    def test_champion_uses_maindeck_back(self, tmp_path):
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("champion", 1, "CHAMP-001"),
            ],
        )
        img = tmp_path / "CHAMP-001.webp"
        img.write_bytes(b"img")
        backs = self._back_map(tmp_path)
        _, per_backs = expand_deck(deck, {"CHAMP-001": img}, backs)
        assert per_backs[0] == backs["maindeck"]

    def test_sideboard_uses_maindeck_back(self, tmp_path):
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("sideboard", 2, "SB-001"),
            ],
        )
        img = tmp_path / "SB-001.webp"
        img.write_bytes(b"img")
        backs = self._back_map(tmp_path)
        _, per_backs = expand_deck(deck, {"SB-001": img}, backs)
        assert all(b == backs["maindeck"] for b in per_backs)

    def test_skips_missing_image(self, tmp_path):
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("maindeck", 2, "MISSING-001"),
            ],
        )
        backs = self._back_map(tmp_path)
        fronts, per_backs = expand_deck(deck, {}, backs)
        assert fronts == []
        assert per_backs == []

    def test_include_runes_false_skips_rune_section(self, tmp_path):
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("rune", 1, "RUNE-001"),
                self._card("maindeck", 1, "UNIT-001"),
            ],
        )
        rune_img = tmp_path / "RUNE-001.webp"
        rune_img.write_bytes(b"img")
        unit_img = tmp_path / "UNIT-001.webp"
        unit_img.write_bytes(b"img")
        backs = self._back_map(tmp_path)
        image_map = {"RUNE-001": rune_img, "UNIT-001": unit_img}
        fronts, _ = expand_deck(deck, image_map, backs, include_runes=False)
        assert len(fronts) == 1
        assert fronts[0] == unit_img

    def test_section_order_is_preserved(self, tmp_path):
        """Cards appear in SECTION_ORDER regardless of insertion order."""
        deck = RBDeck(
            deck_id="x",
            name="X",
            cards=[
                self._card("maindeck", 1, "UNIT-001"),
                self._card("legend", 1, "LEG-001"),
            ],
        )
        unit_img = tmp_path / "UNIT-001.webp"
        unit_img.write_bytes(b"img")
        leg_img = tmp_path / "LEG-001.webp"
        leg_img.write_bytes(b"img")
        backs = self._back_map(tmp_path)
        fronts, _ = expand_deck(deck, {"UNIT-001": unit_img, "LEG-001": leg_img}, backs)
        # Legend should appear first (legend precedes maindeck in SECTION_ORDER)
        assert fronts[0] == leg_img
        assert fronts[1] == unit_img


# ---------------------------------------------------------------------------
# Unit tests — download_images cancellation
# ---------------------------------------------------------------------------


class TestDownloadImagesCancellation:
    def test_raises_cancelled_when_event_set(self, tmp_path):
        from src.rb_scraper import download_images

        card = RBCard(
            card_id="RB-001",
            variant_id="RB-001",
            name="Card",
            card_type="Unit",
            card_super=None,
            quantity=1,
            image_url="https://example.com/img.webp",
            section="maindeck",
        )
        deck = RBDeck(deck_id="x", name="X", cards=[card])
        cancel = threading.Event()
        cancel.set()

        mock_resp = MagicMock()
        mock_resp.content = b"fake"
        with patch("src.rb_scraper.requests.get", return_value=mock_resp):
            with pytest.raises(Cancelled):
                download_images(deck, tmp_path, cancel_event=cancel)


# ---------------------------------------------------------------------------
# Integration tests — live network calls
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestLiveScrapers:
    """Smoke-tests against the real websites.

    Detect breaking changes in a site's API or URL format.
    Skipped in CI unless the 'network' marker is explicitly included.
    """

    URL_PILTOVER = "https://piltoverarchive.com/decks/view/6e82e7e5-3de3-41d2-8aee-c30fc0bbe4d6"
    URL_RIFTBOUND_GG = "https://riftbound.gg/decks/test-deck/"

    def _assert_valid_deck(self, deck: RBDeck) -> None:
        assert isinstance(deck, RBDeck)
        assert deck.total_slots > 0, "Deck has no cards"
        legend = [c for c in deck.cards if c.section == "legend"]
        assert len(legend) == 1, "Deck has no legend"

    def test_piltoverarchive(self):
        deck = scrape_deck(self.URL_PILTOVER)
        self._assert_valid_deck(deck)

    def test_riftbound_gg(self):
        deck = scrape_deck(self.URL_RIFTBOUND_GG)
        self._assert_valid_deck(deck)
