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
    _card_rows,
    _decode_ydke_part,
    _fetch_cards_by_names,
    _fetch_names,
    _parse_meta_page,
    _parse_shared_deck_page,
    _parse_ygoprodeck_page,
    _scrape_legacy_deck,
    download_images,
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
        with patch("src.ygo_scraper.http_get", return_value=response):
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
        with patch("src.ygo_scraper.http_get", return_value=response) as get:
            with patch("src.ygo_scraper._fetch_names", return_value={1: "Alpha"}):
                deck = scrape_deck(source_url)
        assert deck.name == "Hero Frog"
        assert (
            get.call_args.args[0] == "https://edisonformat.net/data/ydk/structure/Hero%20Frog.ydk"
        )


class TestFetchNames:
    """Tests for _fetch_names batching via the YGOPRODeck API."""

    def test_batches_ids_in_groups_of_40(self):
        """More than 40 ids trigger a second API call."""
        ids = list(range(1, 81))  # 80 ids -> 2 batches
        responses = []
        for batch in (ids[:40], ids[40:]):
            resp = MagicMock()
            resp.json.return_value = {
                "data": [{"id": card_id, "name": f"Card {card_id}"} for card_id in batch]
            }
            responses.append(resp)
        with patch("src.ygo_scraper.http_get", side_effect=responses) as get:
            names = _fetch_names(ids)
        assert get.call_count == 2
        assert len(names) == 80
        assert names[1] == "Card 1"
        assert names[80] == "Card 80"

    def test_empty_ids_no_api_call(self):
        """An empty id list skips the API entirely."""
        with patch("src.ygo_scraper.http_get") as get:
            assert _fetch_names([]) == {}
        get.assert_not_called()


class TestFetchCardsByNames:
    """Tests for _fetch_cards_by_names name resolution."""

    def test_resolves_names_casefolded(self):
        """Names are keyed casefolded with (id, canonical name) values."""
        resp = MagicMock()
        resp.json.return_value = {
            "data": [
                {"id": 89631139, "name": "Blue-Eyes White Dragon"},
                {"id": 46986414, "name": "Dark Magician"},
            ]
        }
        with patch("src.ygo_scraper.http_get", return_value=resp) as get:
            resolved = _fetch_cards_by_names(["blue-eyes white dragon", "Dark Magician"])
        assert get.call_count == 1
        assert resolved["blue-eyes white dragon"] == (89631139, "Blue-Eyes White Dragon")
        assert resolved["dark magician"] == (46986414, "Dark Magician")

    def test_batches_names_in_groups_of_20(self):
        """More than 20 names trigger a second API call."""
        names = [f"Card {i}" for i in range(41)]  # 41 names -> 3 batches
        responses = []
        for batch in (names[:20], names[20:40], names[40:]):
            resp = MagicMock()
            resp.json.return_value = {
                "data": [
                    {"id": i, "name": name}
                    for i, name in enumerate(batch, start=1)
                    if name in batch
                ]
            }
            responses.append(resp)
        with patch("src.ygo_scraper.http_get", side_effect=responses) as get:
            _fetch_cards_by_names(names)
        assert get.call_count == 3


class TestCardRows:
    """Tests for _card_rows quantity aggregation."""

    def test_aggregates_repeated_ids_into_quantities(self):
        """Repeated ids in a zone collapse into one card with a quantity."""
        parts = [("main", [1, 1, 2]), ("side", [3])]
        names = {1: "Alpha", 2: "Beta", 3: "Gamma"}
        cards = _card_rows(parts, names)
        by_id = {c.card_id: c for c in cards}
        assert by_id[1].quantity == 2
        assert by_id[1].zone == "main"
        assert by_id[2].quantity == 1
        assert by_id[3].zone == "side"

    def test_unknown_id_falls_back_to_string_id(self):
        """Ids without a resolved name use the id as the card name."""
        cards = _card_rows([("main", [99])], {})
        assert cards[0].name == "99"


class TestSharedDeckPage:
    """Tests for _parse_shared_deck_page YDKE extraction."""

    def test_embedded_ydke_wins_over_card_links(self):
        """A page exposing ydke:// is parsed via parse_ydke, not card links."""
        card_id = 89631139
        packed = struct.pack("<I", card_id)
        ydke = "ydke://" + base64.b64encode(packed).decode() + "!!!"
        page_html = f'<div data-deck="{ydke}"><a href="/card/1">Alpha</a></div>'
        with patch("src.ygo_scraper._fetch_names", return_value={card_id: "Blue-Eyes"}):
            deck = _parse_shared_deck_page(page_html, "https://yugiohmeta.com/decks/top-deck")
        assert deck.name == "top-deck"
        assert deck.cards[0].card_id == card_id

    def test_page_without_ydke_falls_back_to_card_links(self):
        """A page without ydke:// falls back to _parse_meta_page parsing."""
        page_html = '<a href="https://db.ygoprodeck.com/card/1">Alpha</a>'
        with patch("src.ygo_scraper._parse_meta_page", wraps=_parse_meta_page) as meta:
            # _parse_meta_page raises when the page has no deck cards, which
            # proves the fallback path was taken instead of YDKE parsing.
            with pytest.raises(ValueError, match="No se encontraron cartas"):
                _parse_shared_deck_page(page_html, "https://yugiohmeta.com/decks/x")
        meta.assert_called_once()


class TestDownloadImages:
    """Tests for download_images URL mapping."""

    def test_downloads_unique_ids_once(self, tmp_path):
        """Each unique card id is downloaded exactly once with int keys."""
        deck = YGODeck(
            name="Test",
            deck_id="d1",
            cards=[
                YGOCard(card_id=1, name="Alpha", quantity=3, zone="main"),
                YGOCard(card_id=1, name="Alpha", quantity=2, zone="extra"),
                YGOCard(card_id=2, name="Beta", quantity=1, zone="main"),
            ],
        )
        downloaded = {"1": tmp_path / "1.jpg", "2": tmp_path / "2.jpg"}
        with (
            patch("src.ygo_scraper.download_url_images", return_value=downloaded) as dl,
        ):
            result = download_images(deck, tmp_path)
        url_map = dl.call_args.args[0]
        assert set(url_map) == {"1", "2"}  # deduplicated
        assert result == {1: tmp_path / "1.jpg", 2: tmp_path / "2.jpg"}


class TestScrapeDeckRouting:
    """Tests for scrape_deck URL routing."""

    def test_edison_host_routed_to_edison_scraper(self):
        """edisonformat.net URLs use the Edison scraper."""
        with patch("src.ygo_scraper._scrape_edison_deck") as edison:
            scrape_deck("https://edisonformat.net/deckbuilder?event=a&deck=b")
        edison.assert_called_once()

    def test_other_hosts_routed_to_supported_scraper(self):
        """Non-Edison URLs use the generic supported-builders scraper."""
        with patch("src.ygo_scraper._scrape_supported_deck") as supported:
            scrape_deck("https://ygoprodeck.com/decks/abc")
        supported.assert_called_once()

    def test_ydke_string_bypasses_routing(self):
        """A raw ydke:// string is parsed directly without any HTTP call."""
        packed = struct.pack("<I", 89631139)
        ydke = "ydke://" + base64.b64encode(packed).decode() + "!!!"
        with patch("src.ygo_scraper.http_get") as get:
            with patch("src.ygo_scraper._fetch_names", return_value={89631139: "Blue-Eyes"}):
                deck = scrape_deck(ydke)
        get.assert_not_called()
        assert deck.cards[0].name == "Blue-Eyes"


class TestLegacyDeckErrors:
    """Tests for _scrape_legacy_deck error paths."""

    def test_unsupported_url_raises(self):
        """A non-YGOPRODeck URL raises a helpful error."""
        with pytest.raises(ValueError, match="YGOPRODeck"):
            _scrape_legacy_deck("https://example.com/decks/abc")

    def test_page_without_ydke_raises(self):
        """A YGOPRODeck page without an embedded YDKE raises."""
        resp = MagicMock()
        resp.text = "<html>no deck here</html>"
        with patch("src.ygo_scraper.http_get", return_value=resp):
            with pytest.raises(ValueError, match="Export Deck"):
                _scrape_legacy_deck("https://ygoprodeck.com/decks/abc")
