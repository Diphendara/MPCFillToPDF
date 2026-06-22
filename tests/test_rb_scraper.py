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
    _fetch_deck,
    _fs_arr,
    _fs_str,
    _resolve_image,
    _scrape_riftbinder,
    _scrape_riftbound_gg,
    _scrape_riftdex,
    _scrape_riftmana,
    _trpc_get,
    _type_to_section,
    download_images,
    expand_deck,
    get_rb_backs,
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
# Unit tests — _trpc_get
# ---------------------------------------------------------------------------


class TestTrpcGet:
    def test_builds_url_and_parses_result(self):
        mock_r = MagicMock()
        mock_r.json.return_value = {"result": {"data": {"json": {"key": "value"}}}}
        with patch("src.rb_scraper.requests.get", return_value=mock_r) as mock_get:
            result = _trpc_get("decks.getById", {"id": "abc"})
        assert result == {"key": "value"}
        call_url = mock_get.call_args[0][0]
        assert "decks.getById" in call_url
        assert "piltoverarchive.com" in call_url

    def test_passes_encoded_payload(self):
        mock_r = MagicMock()
        mock_r.json.return_value = {"result": {"data": {"json": {}}}}
        with patch("src.rb_scraper.requests.get", return_value=mock_r) as mock_get:
            _trpc_get("proc", {"id": "xyz"})
        call_url = mock_get.call_args[0][0]
        assert "input=" in call_url
        assert "xyz" in call_url


# ---------------------------------------------------------------------------
# Unit tests — _resolve_image
# ---------------------------------------------------------------------------


class TestResolveImage:
    def test_returns_matching_variant_url(self):
        item = {
            "variantId": "v002",
            "card": {
                "cardVariants": [
                    {"id": "v001", "imageUrl": "url1"},
                    {"id": "v002", "imageUrl": "url2"},
                ]
            },
        }
        assert _resolve_image(item) == "url2"

    def test_falls_back_to_first_variant_when_preferred_missing(self):
        item = {
            "variantId": "v999",
            "card": {"cardVariants": [{"id": "v001", "imageUrl": "url1"}]},
        }
        assert _resolve_image(item) == "url1"

    def test_returns_empty_when_no_variants(self):
        item = {"variantId": "v001", "card": {"cardVariants": []}}
        assert _resolve_image(item) == ""


# ---------------------------------------------------------------------------
# Unit tests — _fetch_deck (piltoverarchive)
# ---------------------------------------------------------------------------


class TestFetchDeck:
    def _raw(self):
        return {
            "name": "PA Deck",
            "legend": {
                "cardId": "L001",
                "id": "v-leg",
                "imageUrl": "https://example.com/L001.webp",
                "card": {"name": "The Legend", "type": "Legend"},
            },
            "champions": [],
            "battlefields": [],
            "runes": [],
            "maindeck": [
                {
                    "cardId": "C001",
                    "variantId": "v001",
                    "quantity": 4,
                    "card": {
                        "name": "A Unit",
                        "type": "Unit",
                        "super": None,
                        "cardVariants": [
                            {"id": "v001", "imageUrl": "https://example.com/C001.webp"}
                        ],
                    },
                }
            ],
            "sideboard": [],
        }

    def test_parses_legend_and_maindeck(self):
        with patch("src.rb_scraper._trpc_get", return_value=self._raw()):
            deck = _fetch_deck("test-id")
        assert deck.name == "PA Deck"
        sections = {c.section for c in deck.cards}
        assert "legend" in sections
        assert "maindeck" in sections
        qtys = {c.card_id: c.quantity for c in deck.cards}
        assert qtys["C001"] == 4

    def test_legend_gets_image_url_directly(self):
        with patch("src.rb_scraper._trpc_get", return_value=self._raw()):
            deck = _fetch_deck("test-id")
        legend = next(c for c in deck.cards if c.section == "legend")
        assert legend.image_url == "https://example.com/L001.webp"

    def test_not_found_raises(self):
        with patch("src.rb_scraper._trpc_get", return_value=None):
            with pytest.raises(ValueError, match="No se encontró"):
                _fetch_deck("missing-id")


# ---------------------------------------------------------------------------
# Unit tests — _scrape_riftbound_gg
# ---------------------------------------------------------------------------


class TestScrapeRiftboundGg:
    def _deck_json(self):
        return {
            "humanname": "RBgg Deck",
            "deck": {"CARD-001": "4", "CARD-002": "1"},
            "boards": [],
        }

    def _cards_json(self):
        return {
            "names": ["id", "name", "type", "supertype"],
            "data": [
                ["CARD-001", "Unit Card", "Unit", None],
                ["CARD-002", "Legend Card", "Legend", None],
            ],
        }

    def test_parses_deck_and_cards(self):
        r1 = MagicMock()
        r1.text = "nonempty"
        r1.json.return_value = self._deck_json()
        r2 = MagicMock()
        r2.json.return_value = self._cards_json()
        with patch("src.rb_scraper.requests.get", side_effect=[r1, r2]):
            deck = _scrape_riftbound_gg("https://riftbound.gg/decks/my-deck/")
        assert deck.name == "RBgg Deck"
        qtys = {c.card_id: c.quantity for c in deck.cards}
        assert qtys["CARD-001"] == 4
        assert qtys["CARD-002"] == 1

    def test_assigns_section_from_type(self):
        r1 = MagicMock()
        r1.text = "nonempty"
        r1.json.return_value = self._deck_json()
        r2 = MagicMock()
        r2.json.return_value = self._cards_json()
        with patch("src.rb_scraper.requests.get", side_effect=[r1, r2]):
            deck = _scrape_riftbound_gg("https://riftbound.gg/decks/my-deck/")
        sections = {c.card_id: c.section for c in deck.cards}
        assert sections["CARD-002"] == "legend"
        assert sections["CARD-001"] == "maindeck"

    def test_empty_body_raises(self):
        r1 = MagicMock()
        r1.text = "  "
        with patch("src.rb_scraper.requests.get", return_value=r1):
            with pytest.raises(ValueError, match="privado"):
                _scrape_riftbound_gg("https://riftbound.gg/decks/my-deck/")

    def test_bad_url_raises(self):
        with pytest.raises(ValueError, match="slug"):
            _scrape_riftbound_gg("https://riftbound.gg/")


# ---------------------------------------------------------------------------
# Unit tests — _scrape_riftmana
# ---------------------------------------------------------------------------


class TestScrapeRiftmana:
    def test_extracts_uuid_and_fetches_api(self):
        uuid = "aaaabbbb-1111-2222-3333-ccccddddeeee"
        html_r = MagicMock()
        html_r.text = f'<div data-deck-uuid="{uuid}"></div>'
        api_r = MagicMock()
        api_r.json.return_value = {
            "data": {
                "deck": {
                    "name": "RM Deck",
                    "cards": [
                        {
                            "code": "card-001",
                            "name": "C1",
                            "type": "Unit",
                            "super": None,
                            "quantity": 3,
                            "image": "https://example.com/c1.webp",
                        }
                    ],
                    "sideboard": [],
                }
            }
        }
        with patch("src.rb_scraper.requests.get", side_effect=[html_r, api_r]):
            deck = _scrape_riftmana("https://riftmana.com/decks/my-deck")
        assert deck.name == "RM Deck"
        assert deck.deck_id == uuid
        assert len(deck.cards) == 1
        assert deck.cards[0].card_id == "CARD-001"
        assert deck.cards[0].quantity == 3

    def test_uuid_not_found_raises(self):
        html_r = MagicMock()
        html_r.text = "<html>no uuid here</html>"
        with patch("src.rb_scraper.requests.get", return_value=html_r):
            with pytest.raises(ValueError, match="UUID"):
                _scrape_riftmana("https://riftmana.com/decks/my-deck")


# ---------------------------------------------------------------------------
# Unit tests — _scrape_riftdex
# ---------------------------------------------------------------------------


class TestScrapeRiftdex:
    DECK_UUID = "00000000-1111-2222-3333-444455556666"
    CARD_UUID = "aaaabbbb-0000-0000-0000-111122223333"

    def test_parses_deck_with_card_lookup(self):
        deck_r = MagicMock()
        deck_r.json.return_value = [
            {"name": "RD Deck", "cards": [{"cardId": self.CARD_UUID, "count": 2}]}
        ]
        cards_r = MagicMock()
        cards_r.json.return_value = [
            {
                "id": self.CARD_UUID,
                "card_name": "My Card",
                "card_number": "RD-001",
                "type": "Unit",
                "super": None,
                "image_url": "https://example.com/rd001.webp",
            }
        ]
        with patch("src.rb_scraper.requests.get", side_effect=[deck_r, cards_r]):
            deck = _scrape_riftdex(f"https://riftdex.com/deck/{self.DECK_UUID}")
        assert deck.name == "RD Deck"
        assert deck.cards[0].card_id == "RD-001"
        assert deck.cards[0].quantity == 2

    def test_not_found_raises(self):
        r = MagicMock()
        r.json.return_value = []
        with patch("src.rb_scraper.requests.get", return_value=r):
            with pytest.raises(ValueError, match="No se encontró"):
                _scrape_riftdex(f"https://riftdex.com/deck/{self.DECK_UUID}")

    def test_bad_url_raises(self):
        with pytest.raises(ValueError, match="UUID"):
            _scrape_riftdex("https://riftdex.com/deck/not-a-uuid")


# ---------------------------------------------------------------------------
# Unit tests — download_images (rb_scraper)
# ---------------------------------------------------------------------------


class TestRBDownloadImages:
    def _make_card(self, variant_id: str = "v001") -> RBCard:
        return RBCard(
            card_id="C001",
            variant_id=variant_id,
            name="Card",
            card_type="Unit",
            card_super=None,
            quantity=2,
            image_url=f"https://example.com/{variant_id}.webp",
            section="maindeck",
        )

    def test_downloads_and_saves_image(self, tmp_path):
        card = self._make_card()
        deck = RBDeck(deck_id="d1", name="Test", cards=[card])
        mock_r = MagicMock()
        mock_r.content = b"image_bytes"
        with patch("src.rb_scraper.requests.get", return_value=mock_r):
            result = download_images(deck, tmp_path)
        assert "v001" in result
        assert result["v001"].read_bytes() == b"image_bytes"

    def test_deduplicates_by_variant_id(self, tmp_path):
        card = self._make_card("v001")
        deck = RBDeck(deck_id="d1", name="Test", cards=[card, card])
        mock_r = MagicMock()
        mock_r.content = b"bytes"
        call_count = 0

        def _track(*a, **kw):
            nonlocal call_count
            call_count += 1
            return mock_r

        with patch("src.rb_scraper.requests.get", side_effect=_track):
            result = download_images(deck, tmp_path)
        assert call_count == 1
        assert "v001" in result

    def test_uses_cached_file(self, tmp_path):
        card = self._make_card()
        deck = RBDeck(deck_id="d1", name="Test", cards=[card])
        cached = tmp_path / "v001.webp"
        cached.write_bytes(b"cached")
        with patch("src.rb_scraper.requests.get") as mock_get:
            result = download_images(deck, tmp_path)
        mock_get.assert_not_called()
        assert result["v001"] == cached


# ---------------------------------------------------------------------------
# Unit tests — get_rb_backs fallback
# ---------------------------------------------------------------------------


class TestGetRbBacksFallback:
    def test_generates_fallback_when_files_missing(self, tmp_path):
        with patch("src.rb_scraper._resources_dir", return_value=tmp_path / "missing"):
            backs = get_rb_backs()
        for section in ("legend", "battlefield", "rune", "maindeck"):
            assert section in backs
            assert backs[section].exists()


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
