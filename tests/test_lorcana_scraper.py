"""Tests for src/lorcana_scraper.py.

Unit tests (no network) cover URL routing, data model, expand_deck logic,
and helper functions. Integration tests (marked @pytest.mark.network) hit the
live websites to detect API or format changes.

Run only unit tests:
    pytest tests/test_lorcana_scraper.py -m "not network"

Run everything including live checks:
    pytest tests/test_lorcana_scraper.py
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.cancellation import Cancelled
from src.lorcana_scraper import (
    LocanaDeck,
    LorcanaCard,
    _dreamborn_get_cards_db,
    _dreamborn_parse_nuxt,
    _dreamborn_resolve_card_id,
    _find_chrome_exe,
    _parse_inkdecks_api,
    _parse_inkdecks_cards,
    _parse_inkdecks_html,
    _scrape_dreamborn,
    _scrape_inkdecks,
    _work_dir,
    download_images,
    expand_deck,
    get_lorcana_back,
    scrape_deck,
)

# ---------------------------------------------------------------------------
# Reference URLs — kept here so network-test failures pinpoint the site
# ---------------------------------------------------------------------------

URL_LORCANA_GG = "https://lorcana.gg/decks/robin-hood-copy-eissv/"
URL_INKDECKS = "https://inkdecks.com/lorcana-metagame/deck-sapphire-amethyst-515323"
URL_DREAMBORN = "http://dreamborn.ink/es/decks/GajV82jHLmlcb4Z0Uf2h"


# ---------------------------------------------------------------------------
# Unit tests — URL routing
# ---------------------------------------------------------------------------


class TestScrapedeckRouting:
    def test_unknown_domain_raises(self):
        with pytest.raises(ValueError, match="URL no reconocida"):
            scrape_deck("https://example.com/deck/123")

    def test_lorcana_gg_routes(self):
        with patch("src.lorcana_scraper._scrape_lorcana_gg") as mock:
            mock.return_value = MagicMock(spec=LocanaDeck)
            scrape_deck(URL_LORCANA_GG)
            mock.assert_called_once_with(URL_LORCANA_GG)

    def test_inkdecks_routes(self):
        with patch("src.lorcana_scraper._scrape_inkdecks") as mock:
            mock.return_value = MagicMock(spec=LocanaDeck)
            scrape_deck(URL_INKDECKS)
            mock.assert_called_once_with(URL_INKDECKS)

    def test_dreamborn_routes(self):
        with patch("src.lorcana_scraper._scrape_dreamborn") as mock:
            mock.return_value = MagicMock(spec=LocanaDeck)
            scrape_deck(URL_DREAMBORN)
            mock.assert_called_once_with(URL_DREAMBORN)

    def test_error_message_lists_supported_sites(self):
        with pytest.raises(ValueError, match="lorcana.gg"):
            scrape_deck("https://unknown-site.com/deck/abc")


# ---------------------------------------------------------------------------
# Unit tests — LocanaDeck model
# ---------------------------------------------------------------------------


class TestLocanaDeckModel:
    def _card(self, qty: int, cid: str = "001-001") -> LorcanaCard:
        return LorcanaCard(
            card_id=cid,
            name="Test Card",
            quantity=qty,
            image_url="https://example.com/img.webp",
        )

    def test_total_slots_empty(self):
        deck = LocanaDeck(deck_id="x", name="X")
        assert deck.total_slots == 0

    def test_total_slots_sums_quantities(self):
        deck = LocanaDeck(
            deck_id="x",
            name="X",
            cards=[self._card(4, "001-001"), self._card(3, "001-002"), self._card(1, "001-003")],
        )
        assert deck.total_slots == 8

    def test_source_default(self):
        deck = LocanaDeck(deck_id="x", name="X")
        assert deck.source == "lorcana_gg"

    def test_source_custom(self):
        deck = LocanaDeck(deck_id="x", name="X", source="inkdecks")
        assert deck.source == "inkdecks"


# ---------------------------------------------------------------------------
# Unit tests — expand_deck
# ---------------------------------------------------------------------------


class TestExpandDeck:
    def _card(self, qty: int, cid: str) -> LorcanaCard:
        return LorcanaCard(
            card_id=cid,
            name="Card",
            quantity=qty,
            image_url="https://example.com/img.webp",
        )

    def test_expands_quantity(self, tmp_path):
        deck = LocanaDeck(
            deck_id="x",
            name="X",
            cards=[self._card(4, "001-001")],
        )
        img = tmp_path / "001-001.webp"
        img.write_bytes(b"img")
        fronts, backs = expand_deck(deck, {"001-001": img})
        assert len(fronts) == 4
        assert all(f == img for f in fronts)

    def test_backs_are_none(self, tmp_path):
        """None means use the pipeline default back — Lorcana has a single back."""
        deck = LocanaDeck(
            deck_id="x",
            name="X",
            cards=[self._card(3, "001-001")],
        )
        img = tmp_path / "001-001.webp"
        img.write_bytes(b"img")
        _, backs = expand_deck(deck, {"001-001": img})
        assert all(b is None for b in backs)
        assert len(backs) == 3

    def test_skips_missing_image(self):
        deck = LocanaDeck(
            deck_id="x",
            name="X",
            cards=[self._card(2, "MISSING-001")],
        )
        fronts, backs = expand_deck(deck, {})
        assert fronts == []
        assert backs == []

    def test_multiple_cards_expand_in_order(self, tmp_path):
        deck = LocanaDeck(
            deck_id="x",
            name="X",
            cards=[self._card(2, "001-001"), self._card(1, "001-002")],
        )
        img1 = tmp_path / "001-001.webp"
        img1.write_bytes(b"img1")
        img2 = tmp_path / "001-002.webp"
        img2.write_bytes(b"img2")
        fronts, _ = expand_deck(deck, {"001-001": img1, "001-002": img2})
        assert fronts == [img1, img1, img2]


# ---------------------------------------------------------------------------
# Unit tests — inkdecks card list parsing
# ---------------------------------------------------------------------------


class TestParseInkdecksCards:
    def test_dict_format(self):
        raw = {"001-001": 4, "001-002": 3}
        cards = _parse_inkdecks_cards(raw)
        assert len(cards) == 2
        qtys = {c.card_id: c.quantity for c in cards}
        assert qtys["001-001"] == 4
        assert qtys["001-002"] == 3

    def test_list_format_with_card_id_and_quantity(self):
        raw = [
            {"card_id": "001-001", "quantity": 2},
            {"card_id": "001-002", "quantity": 1},
        ]
        cards = _parse_inkdecks_cards(raw)
        assert len(cards) == 2
        assert cards[0].quantity == 2

    def test_list_format_with_id_and_count(self):
        raw = [{"id": "001-005", "count": 3, "name": "Ariel"}]
        cards = _parse_inkdecks_cards(raw)
        assert cards[0].card_id == "001-005"
        assert cards[0].quantity == 3
        assert cards[0].name == "Ariel"

    def test_empty_list(self):
        assert _parse_inkdecks_cards([]) == []

    def test_empty_dict(self):
        assert _parse_inkdecks_cards({}) == []


# ---------------------------------------------------------------------------
# Unit tests — dreamborn Nuxt data parsing
# ---------------------------------------------------------------------------


class TestDreambornParseNuxt:
    def _nuxt_arr(self) -> list:
        return [
            {"GajV82jHLmlcb4Z0Uf2h": 1},
            {"name": 2, "cards": 3},
            "Mi Mazo Lorcana",
            {"010/abc123": 4, "010/def456": 5},
            4,
            2,
        ]

    def test_extracts_name_and_cards(self):
        name, cards = _dreamborn_parse_nuxt(self._nuxt_arr(), "GajV82jHLmlcb4Z0Uf2h")
        assert name == "Mi Mazo Lorcana"
        assert cards == {"010/abc123": 4, "010/def456": 2}

    def test_deck_not_found_raises(self):
        with pytest.raises(ValueError, match="NOTFOUND"):
            _dreamborn_parse_nuxt([{"other": 0}], "NOTFOUND")

    def test_empty_cards_dict(self):
        arr = [
            {"DECK1": 1},
            {"name": 2, "cards": 3},
            "Empty Deck",
            {},
        ]
        name, cards = _dreamborn_parse_nuxt(arr, "DECK1")
        assert name == "Empty Deck"
        assert cards == {}


# ---------------------------------------------------------------------------
# Unit tests — dreamborn card ID resolution
# ---------------------------------------------------------------------------


class TestDreambornResolveCardId:
    def test_dotgg_format_returned_as_is(self):
        db_conn = MagicMock()
        result = _dreamborn_resolve_card_id("010-028", db_conn)
        assert result == "010-028"
        db_conn.cursor.assert_not_called()

    def test_non_dotgg_format_resolved_via_db(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (10, 28)
        mock_db = MagicMock()
        mock_db.cursor.return_value = mock_cur
        result = _dreamborn_resolve_card_id("010/abc123sha1hash", mock_db)
        assert result == "010-028"

    def test_unknown_id_returns_empty(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_db = MagicMock()
        mock_db.cursor.return_value = mock_cur
        result = _dreamborn_resolve_card_id("unknown-id-format", mock_db)
        assert result == ""

    def test_empty_string_returns_empty(self):
        mock_db = MagicMock()
        result = _dreamborn_resolve_card_id("", mock_db)
        assert result == ""
        mock_db.cursor.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests — download_images cancellation
# ---------------------------------------------------------------------------


class TestDownloadImagesCancellation:
    def test_raises_cancelled_when_event_set(self, tmp_path):
        from src.lorcana_scraper import download_images

        card = LorcanaCard(
            card_id="001-001",
            name="Ariel",
            quantity=1,
            image_url="https://example.com/img.webp",
        )
        deck = LocanaDeck(deck_id="x", name="X", cards=[card])
        cancel = threading.Event()
        cancel.set()

        mock_resp = MagicMock()
        mock_resp.content = b"fake"
        with patch("src.lorcana_scraper.requests.get", return_value=mock_resp):
            with pytest.raises(Cancelled):
                download_images(deck, tmp_path, cancel_event=cancel)


# ---------------------------------------------------------------------------
# Unit tests — lorcana.gg dotgg scraper (mocked HTTP)
# ---------------------------------------------------------------------------


class TestScrapeLorcanaGg:
    def _mock_deck_response(self) -> dict:
        return {
            "humanname": "Robin Hood Deck",
            "slug": "robin-hood-copy-eissv",
            "deck": {
                "001-173": 4,
                "001-197": 3,
            },
        }

    def _mock_cards_response(self) -> dict:
        return {
            "names": ["id", "name", "type", "color"],
            "data": [
                ["001-173", "Robin Hood", "Character", "amber"],
                ["001-197", "Ariel", "Character", "amber"],
            ],
        }

    def test_parses_deck_name(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        deck_resp = MagicMock()
        deck_resp.text = '{"humanname":"Robin Hood Deck","slug":"test","deck":{"001-173":4}}'
        deck_resp.json.return_value = self._mock_deck_response()

        cards_resp = MagicMock()
        cards_resp.json.return_value = self._mock_cards_response()

        with patch("src.lorcana_scraper.requests.get", side_effect=[deck_resp, cards_resp]):
            with patch("src.lorcana_scraper._dotgg_cache", None):
                with patch("src.lorcana_scraper._dotgg_name_cache", None):
                    deck = _scrape_lorcana_gg("https://lorcana.gg/decks/robin-hood-copy-eissv/")

        assert deck.name == "Robin Hood Deck"

    def test_parses_card_quantities(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        deck_resp = MagicMock()
        deck_resp.text = '{"humanname":"X","slug":"x","deck":{"001-173":4,"001-197":3}}'
        deck_resp.json.return_value = self._mock_deck_response()

        cards_resp = MagicMock()
        cards_resp.json.return_value = self._mock_cards_response()

        with patch("src.lorcana_scraper.requests.get", side_effect=[deck_resp, cards_resp]):
            with patch("src.lorcana_scraper._dotgg_cache", None):
                with patch("src.lorcana_scraper._dotgg_name_cache", None):
                    deck = _scrape_lorcana_gg("https://lorcana.gg/decks/robin-hood-copy-eissv/")

        total = sum(c.quantity for c in deck.cards)
        assert total == 7

    def test_bad_url_raises(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        with pytest.raises(ValueError, match="slug"):
            _scrape_lorcana_gg("https://lorcana.gg/")

    def test_empty_response_raises(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        resp = MagicMock()
        resp.text = ""

        with patch("src.lorcana_scraper.requests.get", return_value=resp):
            with pytest.raises(ValueError, match="disponible"):
                _scrape_lorcana_gg("https://lorcana.gg/decks/nonexistent/")

    def test_image_url_format(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        deck_resp = MagicMock()
        deck_resp.text = '{"humanname":"X","slug":"x","deck":{"001-173":1}}'
        deck_resp.json.return_value = {
            "humanname": "X",
            "slug": "x",
            "deck": {"001-173": 1},
        }
        cards_resp = MagicMock()
        cards_resp.json.return_value = self._mock_cards_response()

        with patch("src.lorcana_scraper.requests.get", side_effect=[deck_resp, cards_resp]):
            with patch("src.lorcana_scraper._dotgg_cache", None):
                with patch("src.lorcana_scraper._dotgg_name_cache", None):
                    deck = _scrape_lorcana_gg("https://lorcana.gg/decks/test/")

        assert "static.dotgg.gg/lorcana/cards/001-173.webp" in deck.cards[0].image_url

    def test_source_is_lorcana_gg(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        deck_resp = MagicMock()
        deck_resp.text = '{"humanname":"X","slug":"x","deck":{"001-173":1}}'
        deck_resp.json.return_value = {
            "humanname": "X",
            "slug": "x",
            "deck": {"001-173": 1},
        }
        cards_resp = MagicMock()
        cards_resp.json.return_value = self._mock_cards_response()

        with patch("src.lorcana_scraper.requests.get", side_effect=[deck_resp, cards_resp]):
            with patch("src.lorcana_scraper._dotgg_cache", None):
                with patch("src.lorcana_scraper._dotgg_name_cache", None):
                    deck = _scrape_lorcana_gg("https://lorcana.gg/decks/test/")

        assert deck.source == "lorcana_gg"

    def test_empty_deck_raises(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        deck_resp = MagicMock()
        deck_resp.text = '{"humanname":"X","deck":{}}'
        deck_resp.json.return_value = {"humanname": "X", "deck": {}}

        with patch("src.lorcana_scraper.requests.get", return_value=deck_resp):
            with patch("src.lorcana_scraper._load_dotgg_card_db", return_value=({}, {})):
                with pytest.raises(ValueError, match="cartas"):
                    _scrape_lorcana_gg("https://lorcana.gg/decks/empty-deck/")

    def test_invalid_qty_raises(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        deck_resp = MagicMock()
        deck_resp.text = '{"humanname":"X","deck":{"001-001":"4x"}}'
        deck_resp.json.return_value = {"humanname": "X", "deck": {"001-001": "4x"}}

        with patch("src.lorcana_scraper.requests.get", return_value=deck_resp):
            with patch(
                "src.lorcana_scraper._load_dotgg_card_db",
                return_value=({"001-001": {"name": "Ariel"}}, {}),
            ):
                with pytest.raises(ValueError, match="Cantidad"):
                    _scrape_lorcana_gg("https://lorcana.gg/decks/bad-qty/")


# ---------------------------------------------------------------------------
# Unit tests — inkdecks.com scraper (mocked HTTP)
# ---------------------------------------------------------------------------


def _inkdecks_html(cards: list[tuple[int, str, str, str]], deck_name: str = "Test Deck") -> str:
    """Build a minimal inkdecks.com server-rendered HTML page.

    cards: list of (quantity, img_path, main_name, subtitle)
    """
    rows = ""
    for qty, img_path, main_name, subtitle in cards:
        slug = main_name.lower().replace(" ", "-")
        rows += (
            f'<tr class="card-list-item" data-card-type="character"'
            f' data-quantity="{qty}" data-image-src="{img_path}">'
            f'<td><a href="/cards/details-{slug}"><b>{main_name} -</b> {subtitle}</a></td></tr>'
        )
    return f"<html><h1>{deck_name}</h1><table>{rows}</table></html>"


class TestScrapeInkdecks:
    def _api_json(self) -> dict:
        return {
            "name": "Sapphire Amethyst",
            "cards": [
                {"card_id": "001-001", "quantity": 4},
                {"card_id": "001-002", "quantity": 2},
            ],
        }

    def test_parses_deck_from_api(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = self._api_json()

        with patch("src.lorcana_scraper.requests.get", return_value=resp):
            deck = _scrape_inkdecks(
                "https://inkdecks.com/lorcana-metagame/deck-sapphire-amethyst-515323"
            )

        assert deck.name == "Sapphire Amethyst"
        assert deck.total_slots == 6
        assert deck.source == "inkdecks"
        assert deck.deck_id == "515323"

    def test_falls_back_to_html_when_api_fails(self):
        api_resp = MagicMock()
        api_resp.status_code = 404

        html_resp = MagicMock()
        html_resp.status_code = 200
        html_resp.text = _inkdecks_html(
            [(1, "/img/cards/lorcana/SET/001-003_1468x2048.webp", "Ariel", "On Human Legs")],
            deck_name="HTML Deck",
        )

        with patch("src.lorcana_scraper.requests.get", side_effect=[api_resp, html_resp]):
            deck = _scrape_inkdecks(
                "https://inkdecks.com/lorcana-metagame/deck-sapphire-amethyst-515323"
            )

        assert deck.name == "HTML Deck"
        assert deck.total_slots == 1

    def test_bad_url_raises(self):
        with pytest.raises(ValueError, match="ID"):
            _scrape_inkdecks("https://inkdecks.com/lorcana-metagame/no-numbers-here")

    def test_falls_back_to_html_when_api_raises_exception(self):
        """Network exception during API call should silently fall back to HTML."""
        html_resp = MagicMock()
        html_resp.status_code = 200
        html_resp.text = _inkdecks_html(
            [
                (1, "/img/cards/lorcana/SET/001-001_1468x2048.webp", "Ariel", "Mermaid"),
                (1, "/img/cards/lorcana/SET/001-002_1468x2048.webp", "Elsa", "Queen"),
            ],
            deck_name="Exception Fallback Deck",
        )

        with patch(
            "src.lorcana_scraper.requests.get",
            side_effect=[Exception("connection refused"), html_resp],
        ):
            deck = _scrape_inkdecks("https://inkdecks.com/lorcana-metagame/deck-test-515323")

        assert deck.name == "Exception Fallback Deck"
        assert deck.total_slots == 2

    def test_html_http_error_raises_friendly_error(self):
        """When both API and HTML page fail, raise a Spanish ValueError."""
        api_resp = MagicMock()
        api_resp.status_code = 404

        mock_http_error = requests.HTTPError("503 Service Unavailable")
        mock_http_error.response = MagicMock()
        mock_http_error.response.status_code = 503
        html_resp = MagicMock()
        html_resp.raise_for_status.side_effect = mock_http_error

        with patch("src.lorcana_scraper.requests.get", side_effect=[api_resp, html_resp]):
            with pytest.raises(ValueError, match="inkdecks"):
                _scrape_inkdecks("https://inkdecks.com/lorcana-metagame/deck-test-515323")

    def test_quantity_zero_treated_as_zero(self):
        """A card with explicit quantity=0 must not be silently upgraded to 1."""
        raw = [{"card_id": "001-001", "quantity": 0}]
        cards = _parse_inkdecks_cards(raw)
        assert cards[0].quantity == 0

    def test_quantity_key_precedence(self):
        """'quantity' wins over 'count' when both are present."""
        raw = [{"card_id": "001-001", "quantity": 3, "count": 99}]
        cards = _parse_inkdecks_cards(raw)
        assert cards[0].quantity == 3

    def test_missing_quantity_defaults_to_one(self):
        raw = [{"card_id": "001-001"}]
        cards = _parse_inkdecks_cards(raw)
        assert cards[0].quantity == 1


# ---------------------------------------------------------------------------
# Unit tests — _parse_inkdecks_api
# ---------------------------------------------------------------------------


class TestParseInkdecksApi:
    def test_empty_cards_raises(self):
        with pytest.raises(ValueError, match="cartas"):
            _parse_inkdecks_api({"name": "X", "cards": []}, "42")

    def test_empty_decklist_raises(self):
        with pytest.raises(ValueError, match="cartas"):
            _parse_inkdecks_api({"name": "X", "decklist": []}, "42")

    def test_no_cards_key_raises(self):
        with pytest.raises(ValueError, match="cartas"):
            _parse_inkdecks_api({"name": "X"}, "42")


# ---------------------------------------------------------------------------
# Unit tests — dreamborn.ink scraper (mocked Chrome CDP)
# ---------------------------------------------------------------------------


class TestScrapeDreamborn:
    def _nuxt_arr(self, deck_id: str = "TESTDECK") -> list:
        return [
            {deck_id: 1},
            {"name": 2, "cards": 3},
            "Mi Mazo Lorcana",
            {"001-001": 4},
            4,
        ]

    def test_bad_url_raises(self):
        with pytest.raises(ValueError, match="ID"):
            _scrape_dreamborn("http://dreamborn.ink/")

    def test_scrapes_deck_via_cdp(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ("Ariel",)
        mock_db = MagicMock()
        mock_db.cursor.return_value = mock_cur

        with patch("src.lorcana_scraper._dreamborn_get_nuxt_data", return_value=self._nuxt_arr()):
            with patch("src.lorcana_scraper._dreamborn_get_cards_db", return_value=mock_db):
                deck = _scrape_dreamborn("http://dreamborn.ink/es/decks/TESTDECK")

        assert deck.name == "Mi Mazo Lorcana"
        assert deck.deck_id == "TESTDECK"
        assert deck.source == "dreamborn"
        assert deck.total_slots == 4
        assert deck.cards[0].name == "Ariel"

    def test_cdp_error_raises_friendly(self):
        with patch(
            "src.lorcana_scraper._dreamborn_get_nuxt_data",
            side_effect=RuntimeError("Chrome refused"),
        ):
            with pytest.raises(ValueError, match="dreamborn.ink"):
                _scrape_dreamborn("http://dreamborn.ink/es/decks/ABC123")

    def test_empty_cards_raises(self):
        arr = [{"EMPTY": 1}, {"name": 2, "cards": 3}, "Empty Deck", {}]
        with patch("src.lorcana_scraper._dreamborn_get_nuxt_data", return_value=arr):
            with pytest.raises(ValueError, match="cartas"):
                _scrape_dreamborn("http://dreamborn.ink/es/decks/EMPTY")

    def test_deck_not_found_in_nuxt_raises(self):
        arr = [{"OTHER_DECK": 1}, {"name": 2, "cards": 3}, "Other Deck", {}]
        with patch("src.lorcana_scraper._dreamborn_get_nuxt_data", return_value=arr):
            with pytest.raises(ValueError, match="MISSING"):
                _scrape_dreamborn("http://dreamborn.ink/es/decks/MISSING")


# ---------------------------------------------------------------------------
# Unit tests — get_lorcana_back fallback
# ---------------------------------------------------------------------------


class TestGetLorcanaBack:
    def test_returns_existing_file(self, tmp_path):
        back_dir = tmp_path / "backs" / "lorcana"
        back_dir.mkdir(parents=True)
        back_file = back_dir / "back.png"
        back_file.write_bytes(b"png")
        with patch("src.lorcana_scraper._resources_dir", return_value=tmp_path):
            result = get_lorcana_back()
        assert result == back_file

    def test_generates_fallback_when_missing(self, tmp_path):
        import src.lorcana_scraper as mod

        original = mod._fallback_back_path
        mod._fallback_back_path = None
        try:
            with patch("src.lorcana_scraper._resources_dir", return_value=tmp_path):
                result = get_lorcana_back()
            assert result.exists()
            assert result.suffix == ".png"
        finally:
            mod._fallback_back_path = original

    def test_fallback_returns_same_path_on_repeated_calls(self, tmp_path):
        import src.lorcana_scraper as mod

        original = mod._fallback_back_path
        mod._fallback_back_path = None
        try:
            with patch("src.lorcana_scraper._resources_dir", return_value=tmp_path):
                first = get_lorcana_back()
                second = get_lorcana_back()
            # Singleton — both calls return identical Path (no new temp dir created)
            assert first == second
        finally:
            mod._fallback_back_path = original


# ---------------------------------------------------------------------------
# Unit tests — _parse_inkdecks_html
# ---------------------------------------------------------------------------


class TestParseInkdecksHtml:
    def test_parses_name_and_cards(self):
        html = _inkdecks_html(
            [(3, "/img/cards/lorcana/SET/001-001_1468x2048.webp", "Ariel", "Mermaid")],
            deck_name="Test Deck",
        )
        deck = _parse_inkdecks_html(html, "99")
        assert deck.name == "Test Deck"
        assert deck.total_slots == 3

    def test_missing_cards_raises(self):
        with pytest.raises(ValueError, match="inkdecks"):
            _parse_inkdecks_html("<html><h1>Empty</h1></html>", "42")

    def test_empty_cards_raises(self):
        with pytest.raises(ValueError, match="inkdecks"):
            _parse_inkdecks_html("<html><h1>Empty</h1><table></table></html>", "42")

    def test_card_name_parsed_correctly(self):
        html = _inkdecks_html(
            [(2, "/img/cards/lorcana/SET/001-001_1468x2048.webp", "Fauna", "Good-Natured Fairy")],
        )
        deck = _parse_inkdecks_html(html, "1")
        assert deck.cards[0].name == "Fauna - Good-Natured Fairy"

    def test_image_url_is_absolute(self):
        html = _inkdecks_html(
            [(1, "/img/cards/lorcana/WLD/140-204-en-12_1468x2048.webp", "X", "Y")],
        )
        deck = _parse_inkdecks_html(html, "1")
        assert deck.cards[0].image_url.startswith("https://inkdecks.com")


# ---------------------------------------------------------------------------
# Unit tests — download_images success path
# ---------------------------------------------------------------------------


class TestDownloadImagesSuccess:
    def test_downloads_and_returns_map(self, tmp_path):
        card = LorcanaCard(
            card_id="001-001",
            name="Ariel",
            quantity=2,
            image_url="https://example.com/001-001.webp",
        )
        deck = LocanaDeck(deck_id="x", name="X", cards=[card])

        mock_resp = MagicMock()
        mock_resp.content = b"fake_image_bytes"

        with patch("src.lorcana_scraper.requests.get", return_value=mock_resp):
            image_map = download_images(deck, tmp_path)

        assert "001-001" in image_map
        written = image_map["001-001"]
        assert written.exists()
        assert written.read_bytes() == b"fake_image_bytes"

    def test_deduplicates_same_card_id(self, tmp_path):
        """Two cards with the same card_id (different qty) should download only once."""
        cards = [
            LorcanaCard("001-001", "Ariel", 4, "https://example.com/001-001.webp"),
            LorcanaCard("001-001", "Ariel", 2, "https://example.com/001-001.webp"),
        ]
        deck = LocanaDeck(deck_id="x", name="X", cards=cards)

        mock_resp = MagicMock()
        mock_resp.content = b"img"

        with patch("src.lorcana_scraper.requests.get", return_value=mock_resp) as mock_get:
            download_images(deck, tmp_path)

        # Only one HTTP request despite two card entries
        assert mock_get.call_count == 1

    def test_skips_cached_file(self, tmp_path):
        card = LorcanaCard("001-001", "Ariel", 1, "https://example.com/001-001.webp")
        deck = LocanaDeck(deck_id="x", name="X", cards=[card])
        cached = tmp_path / "001-001.webp"
        cached.write_bytes(b"cached")

        with patch("src.lorcana_scraper.requests.get") as mock_get:
            image_map = download_images(deck, tmp_path)

        mock_get.assert_not_called()
        assert image_map["001-001"] == cached

    def test_calls_progress_callback(self, tmp_path):
        cards = [
            LorcanaCard("001-001", "A", 1, "https://example.com/001-001.webp"),
            LorcanaCard("001-002", "B", 1, "https://example.com/001-002.webp"),
        ]
        deck = LocanaDeck(deck_id="x", name="X", cards=cards)

        mock_resp = MagicMock()
        mock_resp.content = b"img"

        progress_calls: list[tuple[int, int]] = []
        with patch("src.lorcana_scraper.requests.get", return_value=mock_resp):
            download_images(deck, tmp_path, progress_cb=lambda d, t: progress_calls.append((d, t)))

        assert len(progress_calls) == 2
        assert progress_calls[-1] == (2, 2)

    def test_http_error_propagates(self, tmp_path):
        card = LorcanaCard("001-001", "Ariel", 1, "https://example.com/001-001.webp")
        deck = LocanaDeck(deck_id="x", name="X", cards=[card])

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        with patch("src.lorcana_scraper.requests.get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                download_images(deck, tmp_path)


# ---------------------------------------------------------------------------
# Unit tests — _scrape_lorcana_gg non-JSON response
# ---------------------------------------------------------------------------


class TestScrapeLorcanaGgEdgeCases:
    def test_non_json_response_raises_friendly_error(self):
        from src.lorcana_scraper import _scrape_lorcana_gg

        resp = MagicMock()
        resp.text = "<html>error page</html>"
        resp.json.side_effect = ValueError("not JSON")

        with patch("src.lorcana_scraper.requests.get", return_value=resp):
            with pytest.raises(ValueError, match="JSON válido"):
                _scrape_lorcana_gg("https://lorcana.gg/decks/test-slug/")


# ---------------------------------------------------------------------------
# Unit tests — _load_dotgg_card_db malformed response
# ---------------------------------------------------------------------------


class TestLoadDotggCardDb:
    def _reset_cache(self):
        import src.lorcana_scraper as mod

        mod._dotgg_cache = None
        mod._dotgg_name_cache = None

    def _restore_cache(self, original, original_name):
        import src.lorcana_scraper as mod

        mod._dotgg_cache = original
        mod._dotgg_name_cache = original_name

    def test_malformed_response_missing_names_raises(self):
        import src.lorcana_scraper as mod
        from src.lorcana_scraper import _load_dotgg_card_db

        orig, orig_name = mod._dotgg_cache, mod._dotgg_name_cache
        self._reset_cache()
        try:
            resp = MagicMock()
            resp.json.return_value = {"unexpected_key": "no names or data here"}
            with patch("src.lorcana_scraper.requests.get", return_value=resp):
                with pytest.raises(ValueError, match="formato"):
                    _load_dotgg_card_db()
        finally:
            self._restore_cache(orig, orig_name)

    def test_malformed_response_non_json_raises(self):
        import src.lorcana_scraper as mod
        from src.lorcana_scraper import _load_dotgg_card_db

        orig, orig_name = mod._dotgg_cache, mod._dotgg_name_cache
        self._reset_cache()
        try:
            resp = MagicMock()
            resp.json.side_effect = ValueError("not json")
            with patch("src.lorcana_scraper.requests.get", return_value=resp):
                with pytest.raises(ValueError, match="formato"):
                    _load_dotgg_card_db()
        finally:
            self._restore_cache(orig, orig_name)

    def test_valid_response_builds_dicts(self):
        import src.lorcana_scraper as mod
        from src.lorcana_scraper import _load_dotgg_card_db

        orig, orig_name = mod._dotgg_cache, mod._dotgg_name_cache
        self._reset_cache()
        try:
            resp = MagicMock()
            resp.json.return_value = {
                "names": ["id", "name"],
                "data": [["001-001", "Ariel"], ["001-002", "Elsa"]],
            }
            with patch("src.lorcana_scraper.requests.get", return_value=resp):
                id_to_card, name_to_id = _load_dotgg_card_db()

            assert "001-001" in id_to_card
            assert name_to_id["ariel"] == "001-001"
            assert name_to_id["elsa"] == "001-002"
        finally:
            self._restore_cache(orig, orig_name)


# ---------------------------------------------------------------------------
# Unit tests — _find_chrome_exe
# ---------------------------------------------------------------------------


class TestFindChromeExe:
    def test_returns_path_when_exe_exists(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("os.path.exists", lambda p: p == "/usr/bin/google-chrome")
        result = _find_chrome_exe()
        assert result == "/usr/bin/google-chrome"

    def test_returns_none_when_no_exe_found(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("os.path.exists", lambda p: False)
        result = _find_chrome_exe()
        assert result is None

    def test_returns_none_on_unknown_platform(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "FreeBSD")
        monkeypatch.setattr("os.path.exists", lambda p: False)
        result = _find_chrome_exe()
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests — _work_dir
# ---------------------------------------------------------------------------


class TestWorkDir:
    def test_dev_mode_returns_path_with_workdir(self, monkeypatch):
        monkeypatch.delattr("sys.frozen", raising=False)
        result = _work_dir()
        assert result.name == "workdir"

    def test_frozen_mode_returns_path_next_to_exe(self, monkeypatch, tmp_path):
        fake_exe = tmp_path / "MPCFillToPDF.exe"
        fake_exe.write_bytes(b"")
        import sys as _sys

        monkeypatch.setattr(_sys, "frozen", True, raising=False)
        monkeypatch.setattr(_sys, "executable", str(fake_exe), raising=False)
        result = _work_dir()
        assert result == tmp_path / "workdir"


# ---------------------------------------------------------------------------
# Unit tests — _dreamborn_get_cards_db
# ---------------------------------------------------------------------------


class TestDreambornGetCardsDb:
    def test_downloads_db_when_not_cached(self, tmp_path):
        import sqlite3 as _sqlite3

        db_bytes = self._minimal_sqlite_bytes()
        mock_r = MagicMock()
        mock_r.content = db_bytes
        db_path = tmp_path / "cards.db"
        with patch("src.lorcana_scraper.requests.get", return_value=mock_r):
            conn = _dreamborn_get_cards_db(db_path)
        assert db_path.exists()
        assert isinstance(conn, _sqlite3.Connection)
        conn.close()

    def test_reuses_cached_db_without_downloading(self, tmp_path):
        db_bytes = self._minimal_sqlite_bytes()
        db_path = tmp_path / "cards.db"
        db_path.write_bytes(db_bytes)
        with patch("src.lorcana_scraper.requests.get") as mock_get:
            conn = _dreamborn_get_cards_db(db_path)
        mock_get.assert_not_called()
        conn.close()

    def _minimal_sqlite_bytes(self) -> bytes:
        import sqlite3 as _sqlite3
        import tempfile

        tmp = tempfile.mktemp(suffix=".db")
        conn = _sqlite3.connect(tmp)
        conn.execute("CREATE TABLE cards (id TEXT, setId INTEGER, number INTEGER)")
        conn.commit()
        conn.close()
        with open(tmp, "rb") as f:
            data = f.read()
        import os

        os.unlink(tmp)
        return data


# ---------------------------------------------------------------------------
# Integration tests — live network calls
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestLiveScrapers:
    """Smoke-tests against the real websites.

    Detect breaking changes in a site's API or URL format.
    Skipped in CI unless the 'network' marker is explicitly included.
    """

    def _assert_valid_deck(self, deck: LocanaDeck, min_cards: int = 1) -> None:
        assert isinstance(deck, LocanaDeck)
        assert deck.name, "Deck has no name"
        assert deck.total_slots >= min_cards, f"Deck has fewer than {min_cards} cards"
        assert all(c.image_url for c in deck.cards), "Some cards have no image URL"

    def test_lorcana_gg(self):
        deck = scrape_deck(URL_LORCANA_GG)
        self._assert_valid_deck(deck, min_cards=10)
        assert deck.source == "lorcana_gg"

    def test_inkdecks(self):
        deck = scrape_deck(URL_INKDECKS)
        self._assert_valid_deck(deck, min_cards=10)
        assert deck.source == "inkdecks"

    @pytest.mark.xfail(
        strict=False,
        reason="Requiere Chrome instalado y sesión de red estable para cargar dreamborn.ink",
    )
    def test_dreamborn(self):
        deck = scrape_deck(URL_DREAMBORN)
        self._assert_valid_deck(deck, min_cards=10)
        assert deck.source == "dreamborn"
