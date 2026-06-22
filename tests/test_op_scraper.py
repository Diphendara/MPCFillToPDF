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
    _egman_load_short_code,
    _kaizoku_img,
    _scrape_dotgg,
    _scrape_egman,
    _scrape_kaizoku,
    download_images,
    expand_deck,
    get_op_backs,
    scrape_deck,
)

# ---------------------------------------------------------------------------
# Reference deck URLs provided by the user — kept here so failures in network
# tests pinpoint exactly which site broke.
# ---------------------------------------------------------------------------

URL_ONEPIECE_GG = "https://onepiece.gg/decks/god-ussop/"
URL_EGMANEVENTS = (
    "https://deckbuilder.egmanevents.com/?deck="
    "EB01-001:1,EB01-002:1,EB01-003:2,EB01-004:2,EB01-005:1,EB01-007:1,EB01-008:1"
)
URL_CARDKAIZOKU = (
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
            "EB01-002": {"name": "Izo", "category": "Character", "color": ["Red"]},
            "EB01-004": {"name": "Koza", "category": "Character", "color": ["Red"]},
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
        deck = self._make_deck(
            [
                OPCard("OP01-002", "A", 4, False, ["Red"]),
            ]
        )
        assert deck.leader is None

    def test_leader_returns_leader_card(self):
        leader = OPCard("OP01-001", "Leader", 1, True, ["Red"])
        deck = self._make_deck([leader, OPCard("OP01-002", "A", 4, False, ["Red"])])
        assert deck.leader is leader

    def test_total_slots_sums_quantities(self):
        deck = self._make_deck(
            [
                OPCard("A", "A", 4, False, []),
                OPCard("B", "B", 3, False, []),
                OPCard("C", "C", 1, True, []),
            ]
        )
        assert deck.total_slots == 8


# ---------------------------------------------------------------------------
# Unit tests — _scrape_dotgg parsing
# ---------------------------------------------------------------------------


class TestScrapeDotgg:
    def _deck_resp(self):
        return {"humanname": "Test Deck", "deck": {"OP01-001": "1", "OP01-002": "4"}}

    def _cards_resp(self):
        return {
            "names": ["id", "name", "cardType", "Color"],
            "data": [
                ["OP01-001", "Leader Card", "LEADER", "Red"],
                ["OP01-002", "Normal Card", "Character", "Red"],
            ],
        }

    def _two_mocks(self):
        r1 = MagicMock()
        r1.json.return_value = self._deck_resp()
        r1.text = "nonempty"
        r2 = MagicMock()
        r2.json.return_value = self._cards_resp()
        return r1, r2

    def test_parses_deck_name_and_quantities(self):
        r1, r2 = self._two_mocks()
        with patch("src.op_scraper.requests.get", side_effect=[r1, r2]):
            deck = _scrape_dotgg("https://onepiece.gg/decks/test-deck/")
        assert deck.name == "Test Deck"
        assert deck.slug == "test-deck"
        assert deck.source == "dotgg"
        qtys = {c.card_id: c.quantity for c in deck.cards}
        assert qtys["OP01-001"] == 1
        assert qtys["OP01-002"] == 4

    def test_detects_leader(self):
        r1, r2 = self._two_mocks()
        with patch("src.op_scraper.requests.get", side_effect=[r1, r2]):
            deck = _scrape_dotgg("https://onepiece.gg/decks/test-deck/")
        assert deck.leader is not None
        assert deck.leader.card_id == "OP01-001"
        assert deck.leader.is_leader is True

    def test_parses_colors(self):
        r1, r2 = self._two_mocks()
        with patch("src.op_scraper.requests.get", side_effect=[r1, r2]):
            deck = _scrape_dotgg("https://onepiece.gg/decks/test-deck/")
        leader = deck.leader
        assert "Red" in leader.colors

    def test_bad_url_raises(self):
        with pytest.raises(ValueError, match="slug"):
            _scrape_dotgg("https://onepiece.gg/")


# ---------------------------------------------------------------------------
# Unit tests — _scrape_egman parsing
# ---------------------------------------------------------------------------


class TestScrapeEgman:
    def _cards_db(self):
        return {
            "EB01-001": {"name": "Kouzuki Oden", "category": "Leader", "color": ["Red", "Green"]},
            "EB01-002": {"name": "Izo", "category": "Character", "color": ["Red"]},
        }

    def test_parses_query_string_format(self):
        with patch("src.op_scraper._egman_cards_db", return_value=self._cards_db()):
            deck = _scrape_egman("https://deckbuilder.egmanevents.com/?deck=EB01-001:1,EB01-002:4")
        qtys = {c.card_id: c.quantity for c in deck.cards}
        assert qtys["EB01-001"] == 1
        assert qtys["EB01-002"] == 4

    def test_query_string_detects_leader(self):
        with patch("src.op_scraper._egman_cards_db", return_value=self._cards_db()):
            deck = _scrape_egman("https://deckbuilder.egmanevents.com/?deck=EB01-001:1,EB01-002:4")
        assert deck.leader is not None
        assert deck.leader.card_id == "EB01-001"

    def test_empty_deck_param_raises(self):
        with pytest.raises(ValueError, match="deck"):
            _scrape_egman("https://deckbuilder.egmanevents.com/?deck=")

    def test_short_code_format_calls_load_short_code(self):
        with patch("src.op_scraper._egman_load_short_code") as mock_load:
            mock_load.return_value = ({"EB01-001": 1}, "test-code")
            with patch("src.op_scraper._egman_cards_db", return_value=self._cards_db()):
                _scrape_egman("https://deckbuilder.egmanevents.com/d/TEST123")
            mock_load.assert_called_once_with("TEST123")

    def test_unrecognized_url_raises(self):
        with pytest.raises(ValueError, match="no reconocida"):
            _scrape_egman("https://deckbuilder.egmanevents.com/other/path")

    def test_load_short_code_posts_to_supabase(self):
        mock_r = MagicMock()
        mock_r.json.return_value = [{"deck_data": {"EB01-001": 2}, "short_code": "abc"}]
        with patch("src.op_scraper.requests.post", return_value=mock_r) as mock_post:
            deck_map, slug = _egman_load_short_code("abc")
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "get_deck_by_short_code" in call_url
        assert mock_post.call_args[1]["json"] == {"p_code": "abc"}
        assert deck_map == {"EB01-001": 2}
        assert slug == "abc"

    def test_load_short_code_not_found_raises(self):
        mock_r = MagicMock()
        mock_r.json.return_value = []
        with patch("src.op_scraper.requests.post", return_value=mock_r):
            with pytest.raises(ValueError, match="código"):
                _egman_load_short_code("missing")

    def test_load_short_code_list_format(self):
        mock_r = MagicMock()
        mock_r.json.return_value = [
            {
                "deck_data": [
                    {"card_code": "EB01-001", "count": 3},
                    {"card_code": "EB01-002", "count": 1},
                ],
                "short_code": "xyz",
            }
        ]
        with patch("src.op_scraper.requests.post", return_value=mock_r):
            deck_map, slug = _egman_load_short_code("xyz")
        assert deck_map == {"EB01-001": 3, "EB01-002": 1}
        assert slug == "xyz"


# ---------------------------------------------------------------------------
# Unit tests — download_images 404 fallback
# ---------------------------------------------------------------------------


class TestDownloadImagesFallback:
    def _single_card_deck(self, source="dotgg"):
        return OPDeck(
            name="Test",
            slug="test",
            cards=[OPCard("OP01-001", "Card", 1, False, [])],
            source=source,
        )

    def test_uses_primary_url_on_success(self, tmp_path):
        deck = self._single_card_deck()
        mock_r = MagicMock()
        mock_r.content = b"img_data"
        with patch("src.op_scraper.requests.get", return_value=mock_r):
            result = download_images(deck, tmp_path)
        assert "OP01-001" in result
        assert result["OP01-001"].read_bytes() == b"img_data"

    def test_falls_back_to_kaizoku_on_404(self, tmp_path):
        from requests.exceptions import HTTPError

        deck = self._single_card_deck(source="dotgg")

        err_resp = MagicMock()
        err_resp.status_code = 404
        primary_err = HTTPError(response=err_resp)

        primary_mock = MagicMock()
        primary_mock.raise_for_status.side_effect = primary_err

        fallback_mock = MagicMock()
        fallback_mock.content = b"fallback_bytes"

        with patch("src.op_scraper.requests.get", side_effect=[primary_mock, fallback_mock]):
            result = download_images(deck, tmp_path)

        assert "OP01-001" in result
        assert result["OP01-001"].read_bytes() == b"fallback_bytes"
        assert result["OP01-001"].suffix == ".png"

    def test_non_404_error_propagates(self, tmp_path):
        from requests.exceptions import HTTPError

        deck = self._single_card_deck()

        err_resp = MagicMock()
        err_resp.status_code = 500
        primary_err = HTTPError(response=err_resp)

        primary_mock = MagicMock()
        primary_mock.raise_for_status.side_effect = primary_err

        with patch("src.op_scraper.requests.get", return_value=primary_mock):
            with pytest.raises(HTTPError):
                download_images(deck, tmp_path)


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


# ---------------------------------------------------------------------------
# Unit tests — expand_deck
# ---------------------------------------------------------------------------


class TestExpandDeck:
    def _make_deck(self, cards: list[OPCard]) -> OPDeck:
        return OPDeck(name="Test", slug="test", cards=cards, source="dotgg")

    def test_expands_by_quantity(self, tmp_path):
        img = tmp_path / "card.jpg"
        img.touch()
        standard = tmp_path / "std.jpg"
        standard.touch()
        deck = self._make_deck([OPCard("OP01-001", "Card", 3, False, [])])
        fronts, backs = expand_deck(deck, {"OP01-001": img}, None, standard)
        assert len(fronts) == 3
        assert len(backs) == 3

    def test_leader_gets_leader_back(self, tmp_path):
        front = tmp_path / "front.jpg"
        front.touch()
        leader_back = tmp_path / "leader.jpg"
        leader_back.touch()
        standard = tmp_path / "std.jpg"
        standard.touch()
        deck = self._make_deck([OPCard("OP01-001", "Leader", 1, True, [])])
        _, backs = expand_deck(deck, {"OP01-001": front}, leader_back, standard)
        assert backs[0] == leader_back

    def test_non_leader_gets_none_back(self, tmp_path):
        front = tmp_path / "front.jpg"
        front.touch()
        leader_back = tmp_path / "leader.jpg"
        leader_back.touch()
        standard = tmp_path / "std.jpg"
        standard.touch()
        deck = self._make_deck([OPCard("OP01-002", "Normal", 2, False, [])])
        _, backs = expand_deck(deck, {"OP01-002": front}, leader_back, standard)
        assert all(b is None for b in backs)

    def test_leader_back_none_returns_none_for_leader(self, tmp_path):
        front = tmp_path / "front.jpg"
        front.touch()
        standard = tmp_path / "std.jpg"
        standard.touch()
        deck = self._make_deck([OPCard("OP01-001", "Leader", 1, True, [])])
        _, backs = expand_deck(deck, {"OP01-001": front}, None, standard)
        assert backs[0] is None

    def test_card_missing_from_image_map_skipped(self, tmp_path):
        standard = tmp_path / "std.jpg"
        standard.touch()
        deck = self._make_deck([OPCard("OP01-999", "Missing", 3, False, [])])
        fronts, backs = expand_deck(deck, {}, None, standard)
        assert fronts == []
        assert backs == []

    def test_mixed_leader_and_non_leader(self, tmp_path):
        f1 = tmp_path / "f1.jpg"
        f1.touch()
        f2 = tmp_path / "f2.jpg"
        f2.touch()
        leader_back = tmp_path / "leader.jpg"
        leader_back.touch()
        standard = tmp_path / "std.jpg"
        standard.touch()
        cards = [
            OPCard("OP01-001", "Leader", 1, True, []),
            OPCard("OP01-002", "Normal", 2, False, []),
        ]
        deck = self._make_deck(cards)
        image_map = {"OP01-001": f1, "OP01-002": f2}
        fronts, backs = expand_deck(deck, image_map, leader_back, standard)
        assert len(fronts) == 3
        assert backs[0] == leader_back
        assert backs[1] is None
        assert backs[2] is None


# ---------------------------------------------------------------------------
# Unit tests — get_op_backs
# ---------------------------------------------------------------------------


class TestGetOpBacks:
    def test_returns_real_files_when_both_present(self, tmp_path):
        op_dir = tmp_path / "backs" / "op"
        op_dir.mkdir(parents=True)
        default = op_dir / "default.png"
        leader = op_dir / "lider.png"
        default.write_bytes(b"fake")
        leader.write_bytes(b"fake")
        with patch("src.op_scraper._resources_dir", return_value=tmp_path):
            d, lider = get_op_backs()
        assert d == default
        assert lider == leader

    def test_falls_back_to_generated_when_missing(self, tmp_path):
        with patch("src.op_scraper._resources_dir", return_value=tmp_path):
            d, lider = get_op_backs()
        assert d.exists()
        assert lider.exists()
        assert d.suffix == ".png"
        assert lider.suffix == ".png"

    def test_falls_back_when_only_default_missing(self, tmp_path):
        op_dir = tmp_path / "backs" / "op"
        op_dir.mkdir(parents=True)
        (op_dir / "lider.png").write_bytes(b"fake")
        with patch("src.op_scraper._resources_dir", return_value=tmp_path):
            d, lider = get_op_backs()
        assert d.exists()
        assert lider.exists()
