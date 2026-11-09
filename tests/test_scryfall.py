from unittest.mock import MagicMock, patch

import pytest

from src.deck_importer import DeckCard
from src.scryfall import (
    ScryfallCard,
    ScryfallError,
    download_deck_images,
    fetch_card,
    fetch_card_by_name,
    fetch_related_tokens,
)


@pytest.fixture(autouse=True)
def _isolate_disk_cache(tmp_path, monkeypatch):
    """Redirect the Scryfall disk cache to a temp dir so tests don't share state."""
    import src.scryfall as sf

    monkeypatch.setattr(sf, "_DISK_CACHE_DIR", tmp_path / "scryfall_cache")
    sf._cache.clear()
    sf._name_cache.clear()


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


class TestFetchRelatedTokens:
    def test_includes_token_extras_from_the_same_scryfall_relation(self):
        source = {
            "all_parts": [
                {
                    "component": "token",
                    "id": "token-id",
                    "name": "Soldier",
                    "type_line": "Token Creature — Soldier",
                },
                {
                    "component": "token",
                    "id": "emblem-id",
                    "name": "Elspeth Emblem",
                    "type_line": "Emblem — Elspeth",
                },
                {"component": "combo_piece", "id": "other-id", "name": "Not included"},
            ]
        }
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(source)):
            tokens = fetch_related_tokens(["source-id"])
        assert [(card.name, card.scryfall_id) for card in tokens] == [
            ("Soldier", "token-id"),
            ("Elspeth Emblem", "emblem-id"),
        ]


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


class TestFetchCardByName:
    def setup_method(self):
        import src.scryfall as sf

        sf._name_cache.clear()

    def test_returns_set_and_collector_number(self):
        data = {"set": "LTR", "collector_number": "152"}
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(data)):
            set_code, cn = fetch_card_by_name("Lightning Bolt")
        assert set_code == "ltr"
        assert cn == "152"

    def test_result_cached_on_second_call(self):
        data = {"set": "M21", "collector_number": "295"}
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(data)) as mock_get:
            fetch_card_by_name("Forest")
            fetch_card_by_name("Forest")
        assert mock_get.call_count == 1

    def test_cache_case_insensitive(self):
        data = {"set": "m21", "collector_number": "295"}
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(data)) as mock_get:
            fetch_card_by_name("Forest")
            fetch_card_by_name("FOREST")
        assert mock_get.call_count == 1

    def test_raises_scryfall_error_on_http_error(self):
        import requests as req

        err = req.HTTPError(response=MagicMock(status_code=404))
        with patch("src.scryfall._throttled_get", side_effect=err):
            with pytest.raises(ScryfallError, match="no encontrada"):
                fetch_card_by_name("Nonexistent Card XYZZY")

    def test_set_code_lowercased(self):
        data = {"set": "LTR", "collector_number": "1"}
        with patch("src.scryfall._throttled_get", return_value=_mock_resp(data)):
            set_code, _ = fetch_card_by_name("Gandalf")
        assert set_code == set_code.lower()


class TestDownloadCardImagesNameResolution:
    def setup_method(self):
        import src.scryfall as sf

        sf._cache.clear()
        sf._name_cache.clear()

    def test_resolves_name_only_card(self, tmp_path):
        card = DeckCard("Lightning Bolt", "", "", 1, "main")
        with (
            patch("src.scryfall.fetch_card_by_name", return_value=("ltr", "152")) as mock_name,
            patch(
                "src.scryfall.fetch_card",
                return_value=ScryfallCard("https://example.com/img.jpg", None),
            ),
            patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)),
        ):
            from src.scryfall import download_card_images

            front, back = download_card_images(card, tmp_path)
        mock_name.assert_called_once_with("Lightning Bolt")
        assert front.exists()
        assert back is None

    def test_retries_by_name_when_the_source_printing_is_missing(self, tmp_path):
        card = DeckCard("Rahilda, Wanted Cutthroat", "vow", "A-63", 1, "main")
        with (
            patch(
                "src.scryfall.fetch_card",
                side_effect=[
                    ScryfallError("missing printing"),
                    ScryfallCard("https://example.com/img.jpg", None),
                ],
            ) as mock_card,
            patch("src.scryfall.fetch_card_by_name", return_value=("vow", "63")) as mock_name,
            patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)),
        ):
            from src.scryfall import download_card_images

            front, back = download_card_images(card, tmp_path)
        assert mock_card.call_args_list[1].args == ("vow", "63")
        mock_name.assert_called_once_with("Rahilda, Wanted Cutthroat")
        assert front.exists()
        assert back is None

    def test_skips_name_resolution_when_set_and_number_present(self, tmp_path):
        card = DeckCard("Lightning Bolt", "ltr", "152", 1, "main")
        with (
            patch("src.scryfall.fetch_card_by_name") as mock_name,
            patch(
                "src.scryfall.fetch_card",
                return_value=ScryfallCard("https://example.com/img.jpg", None),
            ),
            patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)),
        ):
            from src.scryfall import download_card_images

            download_card_images(card, tmp_path)
        mock_name.assert_not_called()


class TestThrottledGet:
    """Tests for _throttled_get retry and rate-limit handling."""

    def test_returns_response_when_ok(self):
        import src.scryfall as sf

        resp = _mock_resp(_NORMAL_CARD_JSON)
        with patch("src.scryfall.get_session") as session:
            session.return_value.get.return_value = resp
            result = sf._throttled_get("https://api.scryfall.com/x")
        assert result is resp

    def test_retries_on_429_with_retry_after_header(self):
        """A 429 response is retried after the Retry-After delay."""

        import src.scryfall as sf

        limited = _mock_resp(_NORMAL_CARD_JSON, status=429)
        limited.headers = {"Retry-After": "0.01"}
        ok = _mock_resp(_NORMAL_CARD_JSON)
        sleeps: list[float] = []
        with (
            patch("src.scryfall.get_session") as session,
            patch("src.scryfall.time.sleep", side_effect=sleeps.append),
        ):
            session.return_value.get.side_effect = [limited, ok]
            result = sf._throttled_get("https://api.scryfall.com/x")
        assert result is ok
        assert session.return_value.get.call_count == 2
        assert 0.01 in sleeps

    def test_raises_after_exhausting_429_retries(self):
        """Persistent 429s eventually raise the last response error path."""
        import src.scryfall as sf

        limited = _mock_resp(_NORMAL_CARD_JSON, status=429)
        limited.headers = {"Retry-After": "0.01"}
        with (
            patch("src.scryfall.get_session") as session,
            patch("src.scryfall.time.sleep"),
        ):
            session.return_value.get.return_value = limited
            result = sf._throttled_get("https://api.scryfall.com/x")
        # After exhausting retries the last response is returned (caller raises)
        assert result is limited
        assert session.return_value.get.call_count == 1 + len(sf._RETRY_DELAYS)

    def test_retries_on_connection_error_then_succeeds(self):
        """A connection error is retried and succeeds on the second attempt."""
        import requests

        import src.scryfall as sf

        ok = _mock_resp(_NORMAL_CARD_JSON)
        with (
            patch("src.scryfall.get_session") as session,
            patch("src.scryfall.time.sleep"),
        ):
            session.return_value.get.side_effect = [
                requests.ConnectionError("boom"),
                ok,
            ]
            result = sf._throttled_get("https://api.scryfall.com/x")
        assert result is ok

    def test_raises_when_connection_errors_exhausted(self):
        """Persistent connection errors propagate after all retries."""
        import requests

        import src.scryfall as sf

        with (
            patch("src.scryfall.get_session") as session,
            patch("src.scryfall.time.sleep"),
            pytest.raises(requests.ConnectionError),
        ):
            session.return_value.get.side_effect = requests.ConnectionError("boom")
            sf._throttled_get("https://api.scryfall.com/x")


class TestFetchCardById:
    """Tests for fetch_card_by_id and _card_from_id_response."""

    def test_normal_card_returns_front_only(self):
        import src.scryfall as sf

        with patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)):
            card = sf.fetch_card_by_id("uuid-123")
        assert card.front_url.endswith("abc.jpg")
        assert card.back_url is None

    def test_mdfc_card_returns_both_faces(self):
        import src.scryfall as sf

        with patch("src.scryfall._throttled_get", return_value=_mock_resp(_MDFC_CARD_JSON)):
            card = sf.fetch_card_by_id("uuid-456")
        assert card.front_url.endswith("face0.jpg")
        assert card.back_url is not None and card.back_url.endswith("face1.jpg")

    def test_disk_cache_prevents_second_network_call(self):
        import src.scryfall as sf

        with patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)) as tg:
            sf.fetch_card_by_id("uuid-789")
            sf.fetch_card_by_id("uuid-789")
        assert tg.call_count == 1

    def test_http_error_raises_scryfall_error(self):
        import requests

        import src.scryfall as sf

        with patch(
            "src.scryfall._throttled_get",
            side_effect=requests.HTTPError("404"),
        ):
            with pytest.raises(ScryfallError, match="no encontrada"):
                sf.fetch_card_by_id("uuid-bad")

    def test_unexpected_response_format_raises(self):
        import src.scryfall as sf

        with patch("src.scryfall._throttled_get", return_value=_mock_resp({"foo": "bar"})):
            with pytest.raises(ScryfallError, match="inesperado"):
                sf.fetch_card_by_id("uuid-weird")

    def test_disk_cache_write_failure_is_not_fatal(self, tmp_path):
        """A cache write OSError inside _disk_cache_put does not break the fetch."""
        import src.scryfall as sf

        with (
            patch("src.scryfall._throttled_get", return_value=_mock_resp(_NORMAL_CARD_JSON)),
            patch("src.scryfall.json.dump", side_effect=OSError("disk full")),
        ):
            card = sf.fetch_card_by_id("uuid-cache-fail")
        assert card.front_url.endswith("abc.jpg")


class TestFetchRelatedTokens:
    """Extra tests for fetch_related_tokens edge cases."""

    def test_network_error_for_one_card_does_not_abort_the_rest(self):
        import requests

        good = {
            "all_parts": [
                {"id": "src-1", "type_line": "Creature", "name": "Source"},
                {
                    "id": "tok-1",
                    "type_line": "Token Creature — Beast",
                    "name": "Beast",
                },
            ]
        }
        responses = [
            requests.ConnectionError("boom"),
            _mock_resp(good),
        ]
        with patch("src.scryfall._throttled_get", side_effect=responses):
            tokens = fetch_related_tokens(["bad-id", "good-id"])
        assert [t.name for t in tokens] == ["Beast"]

    def test_empty_and_blank_ids_are_skipped(self):
        with patch("src.scryfall._throttled_get") as tg:
            assert fetch_related_tokens(["", ""]) == []
        tg.assert_not_called()
