"""Tests for src/api_endpoints.py — centralized endpoint constants."""

from src.api_endpoints import (
    GoogleDriveEndpoints,
    LorcanaEndpoints,
    MTGEndpoints,
    OnePieceEndpoints,
    RiftboundEndpoints,
    YuGiOhEndpoints,
)


def test_mtg_endpoints_are_https_and_templated():
    for url in (v for k, v in vars(MTGEndpoints).items() if not k.startswith("_")):
        if isinstance(url, str):
            assert url.startswith("https://")
    assert MTGEndpoints.MOXFIELD.format(deck_id="abc").endswith("/abc")
    assert MTGEndpoints.SCRYFALL_CARDS.format(set_code="neo", collector_number="1")


def test_one_piece_endpoints_are_https_and_templated():
    for url in (v for k, v in vars(OnePieceEndpoints).items() if not k.startswith("_")):
        if isinstance(url, str):
            assert url.startswith("https://")
    assert OnePieceEndpoints.DOTGG_DECK.format(slug="my-slug")


def test_riftbound_endpoints_are_https_and_templated():
    for url in (v for k, v in vars(RiftboundEndpoints).items() if not k.startswith("_")):
        if isinstance(url, str):
            assert url.startswith("https://")
    assert RiftboundEndpoints.DOTGG_IMAGE.format(code="UNL-118")


def test_lorcana_endpoints_are_https_and_templated():
    for url in (v for k, v in vars(LorcanaEndpoints).items() if not k.startswith("_")):
        if isinstance(url, str):
            assert url.startswith("https://")
    assert LorcanaEndpoints.INKDECKS_DECK.format(deck_id="123")


def test_yugioh_endpoints_are_https_and_templated():
    for url in (v for k, v in vars(YuGiOhEndpoints).items() if not k.startswith("_")):
        if isinstance(url, str):
            assert url.startswith("https://")
    assert YuGiOhEndpoints.YGOPRODECK_IMAGE.format(card_id="46986414")


def test_google_drive_endpoint_is_https_and_templated():
    assert GoogleDriveEndpoints.DRIVE_IMAGE.startswith("https://")
    assert GoogleDriveEndpoints.DRIVE_IMAGE.format(drive_id="XYZ")
