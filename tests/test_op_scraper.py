"""Tests for src/op_scraper.py.

Unit tests (no network) cover URL routing, URL parsing and image-URL generation.
Integration tests (marked @pytest.mark.network) hit the live websites to detect
API or format changes that would break the scrapers.

Run only unit tests:
    pytest tests/test_op_scraper.py -m "not network"

Run everything including live checks:
    pytest tests/test_op_scraper.py
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.op_scraper import (
    OPCard,
    OPDeck,
    _kaizoku_img,
    _scrape_kaizoku,
    scrape_deck,
)

# ---------------------------------------------------------------------------
# Reference deck URLs provided by the user — kept here so failures in network
# tests pinpoint exactly which site broke.
# ---------------------------------------------------------------------------

URL_ONEPIECE_GG  = "https://onepiece.gg/decks/god-ussop/"
URL_EGMANEVENTS  = (
    "https://deckbuilder.egmanevents.com/?deck="
    "EB01-001:1,EB01-002:1,EB01-003:2,EB01-004:2,EB01-005:1,EB01-007:1,EB01-008:1"
)
URL_CARDKAIZOKU  = (
    "https://deckbuilder.cardkaizoku.com/?deck="
    "2xEB01-004%7C1xEB01-008%7C2xEB01-003%7C1xEB01-002%7C1xEB01-007%7C1xEB01-005%7C1xEB01-001"
)


# ---------------------------------------------------------------------------
# Unit tests — URL routing
# ---------------------------------------------------------------------------

class TestScrapedeckRouting:
    def test_unknown_domain_raises(self):
        with pytest.raises(ValueError, match="URL no reconocida"):
            scrape_deck("https://example.com/deck/123")

    def test_onepiece_gg_routes_to_dotgg(self):
        with patch("src.op_scraper._scrape_dotgg") as mock:
            mock.return_value = MagicMock(spec=OPDeck)
            scrape_deck(URL_ONEPIECE_GG)
            mock.assert_called_once_with(URL_ONEPIECE_GG)

    def test_egmanevents_routes_to_egman(self):
        with patch("src.op_scraper._scrape_egman") as mock:
            mock.return_value = MagicMock(spec=OPDeck)
            scrape_deck(URL_EGMANEVENTS)
            mock.assert_called_once_with(URL_EGMANEVENTS)

    def test_cardkaizoku_routes_to_kaizoku(self):
        with patch("src.op_scraper._scrape_kaizoku") as mock:
            mock.return_value = MagicMock(spec=OPDeck)
            scrape_deck(URL_CARDKAIZOKU)
            mock.assert_called_once_with(URL_CARDKAIZOKU)


# ---------------------------------------------------------------------------
# Unit tests — kaizoku URL parsing
# ---------------------------------------------------------------------------

class TestScrapeKaizoku:
    def _mock_cards_db(self):
        return {
            "EB01-001": {"name": "Kouzuki Oden", "category": "Leader", "color": ["Red", "Green"]},
            "EB01-002": {"name": "Izo",           "category": "Character", "color": ["Red"]},
            "EB01-004": {"name": "Koza",           "category": "Character", "color": ["Red"]},
        }

    def test_parses_pipe_separated_format(self):
        with patch("src.op_scraper._egman_cards_db", return_value=self._mock_cards_db()):
            deck = _scrape_kaizoku(
                "https://deckbuilder.cardkaizoku.com/?deck=1xEB01-001|2xEB01-002|3xEB01-004"
            )
        assert deck.source == "kaizoku"
        quantities = {c.card_id: c.quantity for c in deck.cards}
        assert quantities["EB01-001"] == 1
        assert quantities["EB01-002"] == 2
        assert quantities["EB01-004"] == 3

    def test_parses_url_encoded_pipes(self):
        with patch("src.op_scraper._egman_cards_db", return_value=self._mock_cards_db()):
            deck = _scrape_kaizoku(
                "https://deckbuilder.cardkaizoku.com/?deck=1xEB01-001%7C2xEB01-002"
            )
        assert len(deck.cards) == 2

    def test_detects_leader(self):
        with patch("src.op_scraper._egman_cards_db", return_value=self._mock_cards_db()):
            deck = _scrape_kaizoku(
                "https://deckbuilder.cardkaizoku.com/?deck=1xEB01-001|2xEB01-002"
            )
        assert deck.leader is not None
        assert deck.leader.card_id == "EB01-001"

    def test_deck_name_uses_leader(self):
        with patch("src.op_scraper._egman_cards_db", return_value=self._mock_cards_db()):
            deck = _scrape_kaizoku(
                "https://deckbuilder.cardkaizoku.com/?deck=1xEB01-001|2xEB01-002"
            )
        assert "Kouzuki Oden" in deck.name

    def test_missing_deck_param_raises(self):
        with pytest.raises(ValueError, match="deck="):
            _scrape_kaizoku("https://deckbuilder.cardkaizoku.com/")

    def test_empty_deck_raises(self):
        with pytest.raises(ValueError):
            _scrape_kaizoku("https://deckbuilder.cardkaizoku.com/?deck=")


# ---------------------------------------------------------------------------
# Unit tests — image URL generation
# ---------------------------------------------------------------------------

class TestImageUrls:
    def test_kaizoku_image_url_uses_prefix(self):
        assert _kaizoku_img("EB01-004") == "https://cdn.cardkaizoku.com/cards_en/EB01/EB01-004.png"

    def test_kaizoku_image_url_op_prefix(self):
        assert _kaizoku_img("OP03-114") == "https://cdn.cardkaizoku.com/cards_en/OP03/OP03-114.png"

    def test_kaizoku_image_url_st_prefix(self):
        assert _kaizoku_img("ST01-001") == "https://cdn.cardkaizoku.com/cards_en/ST01/ST01-001.png"


# ---------------------------------------------------------------------------
# Unit tests — OPDeck / OPCard model
# ---------------------------------------------------------------------------

class TestOPDeckModel:
    def _make_deck(self, cards):
        return OPDeck(name="Test", slug="test", cards=cards, source="dotgg")

    def test_leader_returns_none_when_no_leader(self):
        deck = self._make_deck([
            OPCard("OP01-002", "A", 4, False, ["Red"]),
        ])
        assert deck.leader is None

    def test_leader_returns_leader_card(self):
        leader = OPCard("OP01-001", "Leader", 1, True, ["Red"])
        deck = self._make_deck([leader, OPCard("OP01-002", "A", 4, False, ["Red"])])
        assert deck.leader is leader

    def test_total_slots_sums_quantities(self):
        deck = self._make_deck([
            OPCard("A", "A", 4, False, []),
            OPCard("B", "B", 3, False, []),
            OPCard("C", "C", 1, True,  []),
        ])
        assert deck.total_slots == 8


# ---------------------------------------------------------------------------
# Integration tests — live network calls
# ---------------------------------------------------------------------------

@pytest.mark.network
class TestLiveScrapers:
    """Smoke-tests against the real websites.

    These tests detect breaking changes in a site's API or URL format.
    They are skipped in CI unless the 'network' marker is explicitly included.
    Each test asserts the minimum contract: a valid deck with a leader and cards.
    """

    def _assert_valid_deck(self, deck: OPDeck, expected_source: str) -> None:
        assert isinstance(deck, OPDeck)
        assert deck.source == expected_source
        assert deck.total_slots > 0, "Deck has no cards"
        assert deck.leader is not None, "No leader card found"
        assert len(deck.leader.colors) > 0, "Leader has no colors"

    def test_onepiece_gg_god_ussop(self):
        deck = scrape_deck(URL_ONEPIECE_GG)
        self._assert_valid_deck(deck, "dotgg")

    def test_egmanevents_eb01_deck(self):
        deck = scrape_deck(URL_EGMANEVENTS)
        self._assert_valid_deck(deck, "egman")
        leader = deck.leader
        assert leader.card_id == "EB01-001"
        assert leader.name == "Kouzuki Oden"

    def test_cardkaizoku_eb01_deck(self):
        deck = scrape_deck(URL_CARDKAIZOKU)
        self._assert_valid_deck(deck, "kaizoku")
        leader = deck.leader
        assert leader.card_id == "EB01-001"
        assert leader.name == "Kouzuki Oden"
        assert deck.total_slots == 9
