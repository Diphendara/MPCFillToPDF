from unittest.mock import MagicMock, patch

import pytest

from src.deck_importer import DeckCard
from src.scryfall import ScryfallCard, ScryfallError, download_deck_images, fetch_card

_NORMAL_CARD_JSON = {
    "image_uris": {
        "large": "https://cards.scryfall.io/large/front/0/0/abc.jpg",
    }
}

_MDFC_CARD_JSON = {
    "card_faces": [
        {"image_uris": {"large": "https://cards.scryfall.io/large/front/1/1/face0.jpg"}},
        {"image_uris": {"large": "https://cards.scryfall.io/large/back/1/1/face1.jpg"}},
    ]
}


def _mock_resp(json_data, status=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    resp.content = b"IMAGEDATA"
    resp.status_code = status
    return resp


class TestFetchCardNormal:
    def setup_method(self):
        import src.scryfall as sf

        sf._cache.clear()

    def test_returns_front_url_and_no_back(self):
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)):
            card = fetch_card("ltr", "152")
        assert card.front_url == "https://cards.scryfall.io/large/front/0/0/abc.jpg"
        assert card.back_url is None

    def test_result_is_scryfall_card_instance(self):
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)):
            card = fetch_card("m21", "1")
        assert isinstance(card, ScryfallCard)

    def test_raises_scryfall_error_on_http_error(self):
        import requests as req

        err = req.HTTPError(response=MagicMock(status_code=404))
        with patch("src.scryfall._throttled_get", side_effect=err):
            with pytest.raises(ScryfallError, match="no encontrada"):
                fetch_card("bad", "0")


class TestFetchCardMDFC:
    def setup_method(self):
        import src.scryfall as sf

        sf._cache.clear()

    def test_returns_both_face_urls(self):
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(_MDFC_CARD_JSON)):
            card = fetch_card("khm", "200")
        assert "face0" in card.front_url
        assert card.back_url is not None
        assert "face1" in card.back_url

    def test_front_is_card_faces_zero(self):
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(_MDFC_CARD_JSON)):
            card = fetch_card("khm", "200")
        assert card.front_url == _MDFC_CARD_JSON["card_faces"][0]["image_uris"]["large"]
        assert card.back_url == _MDFC_CARD_JSON["card_faces"][1]["image_uris"]["large"]


class TestFetchCardCaching:
    def setup_method(self):
        import src.scryfall as sf

        sf._cache.clear()

    def test_second_call_does_not_hit_network(self):
        with patch(
            "src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)
        ) as mock_get:
            fetch_card("ltr", "10")
            fetch_card("ltr", "10")
        assert mock_get.call_count == 1

    def test_cache_keyed_by_set_and_number(self):
        with patch(
            "src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)
        ) as mock_get:
            fetch_card("ltr", "10")
            fetch_card("m21", "10")
        assert mock_get.call_count == 2


class TestDownloadCardImages:
    def setup_method(self):
        import src.scryfall as sf

        sf._cache.clear()

    def test_file_cache_prevents_redownload(self, tmp_path):
        existing = tmp_path / "ltr_10.jpg"
        existing.write_bytes(b"cached")
        card = DeckCard("Bolt", "ltr", "10", 1, "main")
        with (
            patch(
                "src.scryfall.fetch_card",
                return_value=ScryfallCard("https://example.com/ltr_10.jpg", None),
            ),
            patch("src.scryfall._throttled_get") as mock_get,
        ):
            from src.scryfall import download_card_images

            front, back = download_card_images(card, tmp_path)
        mock_get.assert_not_called()
        assert front == existing
        assert back is None

    def test_downloads_front_when_missing(self, tmp_path):
        card = DeckCard("Bolt", "ltr", "152", 1, "main")
        with (
            patch(
                "src.scryfall.fetch_card",
                return_value=ScryfallCard("https://example.com/img.jpg", None),
            ),
            patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)),
        ):
            from src.scryfall import download_card_images

            front, back = download_card_images(card, tmp_path)
        assert front.exists()
        assert front.read_bytes() == b"IMAGEDATA"
        assert back is None

    def test_downloads_mdfc_back(self, tmp_path):
        card = DeckCard("Fable", "mid", "141", 1, "main")
        with (
            patch(
                "src.scryfall.fetch_card",
                return_value=ScryfallCard(
                    "https://example.com/front.jpg",
                    "https://example.com/back.jpg",
                ),
            ),
            patch("src.scryfall._throttled_get", return_value=_mock_resp(_MDFC_CARD_JSON)),
        ):
            from src.scryfall import download_card_images

            front, back = download_card_images(card, tmp_path)
        assert back is not None
        assert back.exists()
        assert "_back" in back.name


class TestDownloadDeckImages:
    def setup_method(self):
        import src.scryfall as sf

        sf._cache.clear()

    def test_returns_ordered_results(self, tmp_path):
        cards = [
            DeckCard("A", "m21", "1", 1, "main"),
            DeckCard("B", "m21", "2", 1, "main"),
            DeckCard("C", "m21", "3", 1, "main"),
        ]
        side_effects = [
            (tmp_path / "m21_1.jpg", None),
            (tmp_path / "m21_2.jpg", None),
            (tmp_path / "m21_3.jpg", None),
        ]
        for p, _ in side_effects:
            p.write_bytes(b"x")

        with patch("src.scryfall.download_card_images", side_effect=side_effects):
            results = download_deck_images(cards, tmp_path)

        assert len(results) == 3
        names = [c.name for c, _, _ in results]
        assert names == ["A", "B", "C"]
