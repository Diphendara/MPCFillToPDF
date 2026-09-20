"""Tests for the Yu-Gi-Oh! YDKE importer."""

import base64
import struct
from unittest.mock import MagicMock, patch

import pytest

from src.scraper_utils import bundled_back
from src.ygo_scraper import (
    YGOCard,
    YGODeck,
    _adapter_for_host,
    _decode_ydke_part,
    _parse_meta_page,
    _parse_ygoprodeck_page,
    expand_deck,
    get_ygo_back,
    parse_ydk,
    parse_ydke,
    scrape_deck,
)


def _encode(*card_ids: int) -> str:
    return base64.b64encode(struct.pack(f"<{len(card_ids)}I", *card_ids)).decode()


def test_get_ygo_back_uses_the_bundled_proxy_asset():
    back = get_ygo_back()

    assert back.name == "back.jpg"
    assert back.parent.name == "yugioh"
    assert back.exists()


def test_bundled_back_discovers_supported_image_extensions():
    assert bundled_back("yugioh") == get_ygo_back()


def test_url_adapters_classify_each_supported_builder():
    assert _adapter_for_host("ygoprodeck.com") is not None
    assert _adapter_for_host("www.masterduelmeta.com") is not None
    assert _adapter_for_host("www.yugiohmeta.com") is not None
    assert _adapter_for_host("unsupported.example") is None


class TestYdkeParsing:
    def test_decode_ydke_part_decodes_little_endian_card_ids(self):
        assert _decode_ydke_part(_encode(46986414, 89631139)) == [46986414, 89631139]

    def test_invalid_ydke_part_raises_value_error(self):
        with pytest.raises(ValueError):
            _decode_ydke_part("not-base64")

    def test_parse_ydke_keeps_main_extra_and_side_quantities(self):
        value = f"ydke://{_encode(1, 1, 2)}!{_encode(3)}!{_encode(4, 4)}!"
        response = MagicMock()
        response.json.return_value = {
            "data": [
                {"id": 1, "name": "Alpha"},
                {"id": 2, "name": "Beta"},
                {"id": 3, "name": "Gamma"},
                {"id": 4, "name": "Delta"},
            ]
        }
        with patch("src.ygo_scraper.requests.get", return_value=response):
            deck = parse_ydke(value, name="Prueba")
        assert deck.name == "Prueba"
        assert {(card.card_id, card.zone): card.quantity for card in deck.cards} == {
            (1, "main"): 2,
            (2, "main"): 1,
            (3, "extra"): 1,
            (4, "side"): 2,
        }
        assert deck.total_slots() == 4
        assert deck.total_slots(include_side=True) == 6
        assert deck.side_slots == 2


class TestExpandDeck:
    def test_expands_main_and_extra_but_not_side_by_default(self, tmp_path):
        alpha = tmp_path / "alpha.jpg"
        beta = tmp_path / "beta.jpg"
        side = tmp_path / "side.jpg"
        for path in (alpha, beta, side):
            path.touch()
        deck = YGODeck(
            "Prueba",
            "id",
            [
                YGOCard(1, "Zeta", 2, "main"),
                YGOCard(2, "Alpha", 1, "extra"),
                YGOCard(3, "Side", 1, "side"),
            ],
        )
        result = expand_deck(deck, {1: alpha, 2: beta, 3: side})
        assert result == [alpha, alpha, beta]
        assert expand_deck(deck, {1: alpha, 2: beta, 3: side}, include_side=True) == [
            alpha,
            alpha,
            beta,
            side,
        ]


class TestPublicDeckPages:
    def test_ygoprodeck_page_reads_main_extra_and_side(self):
        page = """
        <script>
        var maindeckjs = '["1", "1", "2"]';
        var extradeckjs = '["3"]';
        var sidedeckjs = '["4"]';
        var deckname = "Test Deck";
        var deckid = '123';
        </script>
        """
        names = {1: "Alpha", 2: "Beta", 3: "Gamma", 4: "Delta"}
        with patch("src.ygo_scraper._fetch_names", return_value=names):
            deck = _parse_ygoprodeck_page(page, "https://ygoprodeck.com/deck/test")
        assert deck.name == "Test Deck"
        assert deck.deck_id == "123"
        assert {(card.card_id, card.zone): card.quantity for card in deck.cards} == {
            (1, "main"): 2,
            (2, "main"): 1,
            (3, "extra"): 1,
            (4, "side"): 1,
        }

    def test_meta_page_resolves_repeated_card_links(self):
        page = (
            '<title>Meta deck</title><a href="/cards/Alpha"></a>'
            '<a href="/cards/Alpha"></a><a href="/cards/Beta"></a>'
        )
        resolved = {"alpha": (1, "Alpha"), "beta": (2, "Beta")}
        with patch("src.ygo_scraper._fetch_cards_by_names", return_value=resolved):
            deck = _parse_meta_page(page, "https://www.masterduelmeta.com/top-decks/test")
        assert deck.name == "Meta deck"
        assert {(card.card_id, card.zone): card.quantity for card in deck.cards} == {
            (1, "main"): 2,
            (2, "main"): 1,
        }


class TestEdisonFormat:
    def test_parse_ydk_keeps_main_extra_and_side_quantities(self):
        content = "#created by Edison\n#main\n1\n1\n#extra\n2\n!side\n3\n3\n"
        with patch(
            "src.ygo_scraper._fetch_names", return_value={1: "Alpha", 2: "Beta", 3: "Gamma"}
        ):
            deck = parse_ydk(content, "Hero Frog", "example")
        assert {(card.card_id, card.zone): card.quantity for card in deck.cards} == {
            (1, "main"): 2,
            (2, "extra"): 1,
            (3, "side"): 2,
        }

    def test_edison_url_fetches_its_ydk_file(self):
        source_url = "https://edisonformat.net/deckbuilder?event=structure&deck=Hero%20Frog"
        response = MagicMock()
        response.text = "#main\n1\n#extra\n!side\n"
        with patch("src.ygo_scraper.requests.get", return_value=response) as get:
            with patch("src.ygo_scraper._fetch_names", return_value={1: "Alpha"}):
                deck = scrape_deck(source_url)
        assert deck.name == "Hero Frog"
        assert (
            get.call_args.args[0] == "https://edisonformat.net/data/ydk/structure/Hero%20Frog.ydk"
        )
