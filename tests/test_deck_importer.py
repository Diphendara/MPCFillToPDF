from unittest.mock import MagicMock, patch

import pytest

from src.deck_importer import DeckCard, DeckImportError, FetchedDeck, fetch_deck

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
