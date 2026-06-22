from unittest.mock import MagicMock, patch

import pytest

from src.deck_importer import (
    DeckCard,
    DeckImportError,
    FetchedDeck,
    _astro_find,
    _astro_val,
    _manabox_extract_props,
    fetch_deck,
)

_MOXFIELD_FIXTURE = {
    "name": "Test Deck",
    "boards": {
        "mainboard": {
            "cards": {
                "a1": {
                    "quantity": 4,
                    "card": {"name": "Lightning Bolt", "set": "ltr", "cn": "152"},
                },
                "a2": {
                    "quantity": 1,
                    "card": {"name": "Forest", "set": "m21", "cn": "295"},
                },
            }
        },
        "commanders": {"cards": {}},
        "companions": {"cards": {}},
        "sideboard": {
            "cards": {
                "b1": {
                    "quantity": 2,
                    "card": {"name": "Naturalize", "set": "m21", "cn": "196"},
                }
            }
        },
    },
}

_MOXFIELD_FIXTURE_WITH_COMPANION = {
    "name": "Companion Deck",
    "boards": {
        "mainboard": {"cards": {}},
        "commanders": {"cards": {}},
        "companions": {
            "cards": {
                "c1": {
                    "quantity": 1,
                    "card": {"name": "Lurrus of the Dream-Den", "set": "iko", "cn": "226"},
                }
            }
        },
        "sideboard": {"cards": {}},
    },
}

_ARCHIDEKT_FIXTURE = {
    "name": "Archidekt Test",
    "cards": [
        {
            "quantity": 4,
            "categories": ["Mainboard"],
            "card": {
                "oracleCard": {"name": "Counterspell"},
                "edition": {"editioncode": "ice"},
                "collectorNumber": "57",
            },
        },
        {
            "quantity": 2,
            "categories": ["Sideboard"],
            "card": {
                "oracleCard": {"name": "Negate"},
                "edition": {"editioncode": "m21"},
                "collectorNumber": "60",
            },
        },
        {
            "quantity": 1,
            "categories": ["Maybeboard"],
            "card": {
                "oracleCard": {"name": "Skipped"},
                "edition": {"editioncode": "m21"},
                "collectorNumber": "1",
            },
        },
    ],
}


class TestMoxfieldFetch:
    def _mock_resp(self, data):
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        return resp

    def test_extracts_mainboard_cards(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_MOXFIELD_FIXTURE)
        ):
            result = fetch_deck("https://www.moxfield.com/decks/ABC123")
        main = [c for c in result.cards if c.zone == "main"]
        assert len(main) == 2
        bolt = next(c for c in main if c.name == "Lightning Bolt")
        assert bolt.set_code == "ltr"
        assert bolt.collector_number == "152"
        assert bolt.quantity == 4

    def test_extracts_sideboard_cards(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_MOXFIELD_FIXTURE)
        ):
            result = fetch_deck("https://www.moxfield.com/decks/ABC123")
        side = [c for c in result.cards if c.zone == "side"]
        assert len(side) == 1
        assert side[0].name == "Naturalize"
        assert side[0].quantity == 2

    def test_extracts_deck_name(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_MOXFIELD_FIXTURE)
        ):
            result = fetch_deck("https://www.moxfield.com/decks/ABC123")
        assert result.name == "Test Deck"

    def test_extracts_companion_as_main(self):
        with patch(
            "src.deck_importer.requests.get",
            return_value=self._mock_resp(_MOXFIELD_FIXTURE_WITH_COMPANION),
        ):
            result = fetch_deck("https://www.moxfield.com/decks/ABC123")
        assert len(result.cards) == 1
        assert result.cards[0].name == "Lurrus of the Dream-Den"
        assert result.cards[0].zone == "main"
        assert result.cards[0].collector_number == "226"

    def test_raises_on_http_error(self):
        import requests as req

        with patch("src.deck_importer.requests.get", side_effect=req.RequestException("404")):
            with pytest.raises(DeckImportError, match="Moxfield"):
                fetch_deck("https://www.moxfield.com/decks/BAD")


class TestArchidektFetch:
    def _mock_resp(self, data):
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        return resp

    def test_extracts_mainboard_cards(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_ARCHIDEKT_FIXTURE)
        ):
            result = fetch_deck("https://archidekt.com/decks/12345/my-deck")
        main = [c for c in result.cards if c.zone == "main"]
        assert len(main) == 1
        assert main[0].name == "Counterspell"
        assert main[0].set_code == "ice"
        assert main[0].collector_number == "57"
        assert main[0].quantity == 4

    def test_extracts_sideboard_cards(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_ARCHIDEKT_FIXTURE)
        ):
            result = fetch_deck("https://archidekt.com/decks/12345/my-deck")
        side = [c for c in result.cards if c.zone == "side"]
        assert len(side) == 1
        assert side[0].name == "Negate"

    def test_extracts_deck_name(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_ARCHIDEKT_FIXTURE)
        ):
            result = fetch_deck("https://archidekt.com/decks/12345/my-deck")
        assert result.name == "Archidekt Test"

    def test_skips_maybeboard(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_ARCHIDEKT_FIXTURE)
        ):
            result = fetch_deck("https://archidekt.com/decks/12345/my-deck")
        names = [c.name for c in result.cards]
        assert "Skipped" not in names


class TestUrlDetection:
    def test_invalid_url_raises(self):
        with pytest.raises(DeckImportError, match="no reconocida"):
            fetch_deck("https://deckstats.net/decks/123")

    def test_moxfield_url_detected(self):
        with patch("src.deck_importer._fetch_moxfield", return_value=FetchedDeck("", [])) as mock:
            fetch_deck("https://www.moxfield.com/decks/XYZ-abc")
            mock.assert_called_once_with("XYZ-abc")

    def test_archidekt_url_detected(self):
        with patch("src.deck_importer._fetch_archidekt", return_value=FetchedDeck("", [])) as mock:
            fetch_deck("https://archidekt.com/decks/99999/name")
            mock.assert_called_once_with("99999")

    def test_deckstats_url_detected(self):
        with patch("src.deck_importer._fetch_deckstats", return_value=FetchedDeck("", [])) as mock:
            fetch_deck("https://deckstats.net/decks/12345/67890-burn")
            mock.assert_called_once_with("12345", "67890")

    def test_tappedout_url_detected(self):
        with patch("src.deck_importer._fetch_tappedout", return_value=FetchedDeck("", [])) as mock:
            fetch_deck("https://tappedout.net/mtg-decks/my-deck/")
            mock.assert_called_once_with("my-deck")

    def test_manabox_url_detected(self):
        with patch("src.deck_importer._fetch_manabox", return_value=FetchedDeck("", [])) as mock:
            fetch_deck("https://manabox.app/decks/abc123")
            mock.assert_called_once_with("abc123")


_DECKSTATS_FIXTURE = {
    "name": "Deckstats Test",
    "sections": [
        {
            "name": "Creatures",
            "cards": [
                {"amount": 4, "name": "Goblin Guide"},
                {"amount": 2, "name": "Monastery Swiftspear"},
            ],
        },
        {
            "name": "Spells",
            "cards": [
                {"amount": 4, "name": "Lightning Bolt"},
            ],
        },
    ],
    "sideboard": [
        {"amount": 2, "name": "Eidolon of the Great Revel"},
    ],
}

_TAPPEDOUT_TEXT = """\
4 Lightning Bolt
2 Goblin Guide
// sideboard
SB: 2 Pyroclasm
SB: 1 Smash to Smithereens
"""

_MANABOX_PROPS_JSON = (
    '{"deck":[0,{"name":[0,"Manabox Test"],'
    '"cards":[1,[[0,{"name":[0,"Whirlpool Warrior"],"setId":[0,"apc"],'
    '"collectorNumber":[0,"36"],"quantity":[0,2],"boardCategory":[0,3]}],'
    '[0,{"name":[0,"Negate"],"setId":[0,"m21"],'
    '"collectorNumber":[0,"60"],"quantity":[0,1],"boardCategory":[0,1]}]]]}]}'
)
_MANABOX_HTML = (
    "<html><body>"
    '<astro-island props="' + _MANABOX_PROPS_JSON.replace('"', "&quot;") + '"></astro-island>'
    "</body></html>"
)


class TestDeckstatsFetch:
    def _mock_resp(self, data):
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        return resp

    def test_extracts_mainboard_from_sections(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_DECKSTATS_FIXTURE)
        ):
            result = fetch_deck("https://deckstats.net/decks/12345/67890-burn")
        main = [c for c in result.cards if c.zone == "main"]
        assert len(main) == 3
        bolt = next(c for c in main if c.name == "Lightning Bolt")
        assert bolt.quantity == 4
        assert bolt.set_code == ""

    def test_extracts_sideboard(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_DECKSTATS_FIXTURE)
        ):
            result = fetch_deck("https://deckstats.net/decks/12345/67890-burn")
        side = [c for c in result.cards if c.zone == "side"]
        assert len(side) == 1
        assert side[0].name == "Eidolon of the Great Revel"

    def test_extracts_deck_name(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp(_DECKSTATS_FIXTURE)
        ):
            result = fetch_deck("https://deckstats.net/decks/12345/67890-burn")
        assert result.name == "Deckstats Test"

    def test_raises_on_http_error(self):
        import requests as req

        with patch("src.deck_importer.requests.get", side_effect=req.RequestException("timeout")):
            with pytest.raises(DeckImportError, match="Deckstats"):
                fetch_deck("https://deckstats.net/decks/12345/67890-burn")


class TestTappedoutFetch:
    def _mock_resp(self, text):
        resp = MagicMock()
        resp.text = text
        resp.raise_for_status.return_value = None
        return resp

    def test_extracts_main_cards(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp(_TAPPEDOUT_TEXT)):
            result = fetch_deck("https://tappedout.net/mtg-decks/burn-deck/")
        main = [c for c in result.cards if c.zone == "main"]
        assert len(main) == 2
        bolt = next(c for c in main if c.name == "Lightning Bolt")
        assert bolt.quantity == 4
        assert bolt.set_code == ""

    def test_extracts_sideboard_lines(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp(_TAPPEDOUT_TEXT)):
            result = fetch_deck("https://tappedout.net/mtg-decks/burn-deck/")
        side = [c for c in result.cards if c.zone == "side"]
        assert len(side) == 2
        assert any(c.name == "Pyroclasm" for c in side)
        assert any(c.name == "Smash to Smithereens" for c in side)

    def test_deck_name_from_slug(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp(_TAPPEDOUT_TEXT)):
            result = fetch_deck("https://tappedout.net/mtg-decks/burn-deck/")
        assert "Burn" in result.name

    def test_skips_comment_lines(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp(_TAPPEDOUT_TEXT)):
            result = fetch_deck("https://tappedout.net/mtg-decks/burn-deck/")
        assert all(c.name != "sideboard" for c in result.cards)

    def test_raises_on_empty_response(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp("")):
            with pytest.raises(DeckImportError):
                fetch_deck("https://tappedout.net/mtg-decks/empty-deck/")


class TestManaboxFetch:
    def _mock_resp(self, text):
        resp = MagicMock()
        resp.text = text
        resp.raise_for_status.return_value = None
        return resp

    def test_extracts_main_cards(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp(_MANABOX_HTML)):
            result = fetch_deck("https://manabox.app/decks/abc123")
        main = [c for c in result.cards if c.zone == "main"]
        assert len(main) == 1
        assert main[0].name == "Whirlpool Warrior"
        assert main[0].set_code == "apc"
        assert main[0].collector_number == "36"
        assert main[0].quantity == 2

    def test_extracts_sideboard_cards(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp(_MANABOX_HTML)):
            result = fetch_deck("https://manabox.app/decks/abc123")
        side = [c for c in result.cards if c.zone == "side"]
        assert len(side) == 1
        assert side[0].name == "Negate"
        assert side[0].set_code == "m21"

    def test_extracts_deck_name(self):
        with patch("src.deck_importer.requests.get", return_value=self._mock_resp(_MANABOX_HTML)):
            result = fetch_deck("https://manabox.app/decks/abc123")
        assert result.name == "Manabox Test"

    def test_raises_on_missing_data(self):
        with patch(
            "src.deck_importer.requests.get", return_value=self._mock_resp("<html>no data</html>")
        ):
            with pytest.raises(DeckImportError):
                fetch_deck("https://manabox.app/decks/abc123")


class TestManaboxHelpers:
    def test_astro_val_unwraps_type0(self):
        assert _astro_val([0, "hello"]) == "hello"
        assert _astro_val([0, 42]) == 42
        assert _astro_val("plain") == "plain"

    def test_astro_val_unwraps_type1_array(self):
        result = _astro_val([1, [[0, "a"], [0, "b"]]])
        assert result == ["a", "b"]

    def test_astro_val_type1_nested_dicts(self):
        result = _astro_val([1, [[0, {"x": [0, 1]}], [0, {"x": [0, 2]}]]])
        assert result == [{"x": [0, 1]}, {"x": [0, 2]}]

    def test_astro_find_nested(self):
        data = {"a": [0, {"b": [0, {"cards": [0, [1, 2, 3]]}]}]}
        result = _astro_find(data, "cards")
        assert result == [1, 2, 3]

    def test_astro_find_not_found(self):
        assert _astro_find({"x": [0, 1]}, "missing") is None

    def test_manabox_extract_props_returns_encoded_value(self):
        html = '<astro-island props="{&quot;cards&quot;:[0,[]]}"></astro-island>'
        result = _manabox_extract_props(html)
        assert result == "{&quot;cards&quot;:[0,[]]}"

    def test_manabox_extract_props_missing_returns_empty(self):
        assert _manabox_extract_props("<html>no data</html>") == ""


class TestSideboardFiltering:
    def test_main_and_side_zones_returned(self):
        with patch(
            "src.deck_importer.requests.get",
            return_value=MagicMock(json=lambda: _MOXFIELD_FIXTURE, raise_for_status=lambda: None),
        ):
            result = fetch_deck("https://www.moxfield.com/decks/X")
        zones = {c.zone for c in result.cards}
        assert "main" in zones
        assert "side" in zones

    def test_deck_card_dataclass_fields(self):
        card = DeckCard("Test", "m21", "1", 3, "main")
        assert card.name == "Test"
        assert card.set_code == "m21"
        assert card.collector_number == "1"
        assert card.quantity == 3
        assert card.zone == "main"
