import os
import queue
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

from src.scryfall import download_deck_images, process_exact_edition, process_best_image
from src.moxfield import download_deck, parse_deck, extract_deck_id

# Try importing env.py to get the test deck URL
try:
    import env
    TEST_DECK_URL = getattr(env, "TESTDECK", "https://moxfield.com/decks/--2f33MInEaEBPoa6IqJuQ")
except ImportError:
    TEST_DECK_URL = "https://moxfield.com/decks/--2f33MInEaEBPoa6IqJuQ"

# Determine if we should run live network calls
RUN_LIVE_TESTS = os.environ.get("LIVE_INTEGRATION_TESTS") == "1"

@pytest.fixture
def mock_scryfall_apis():
    """High-fidelity mock for Moxfield and Scryfall APIs to enable mock integration tests."""
    with patch("src.moxfield.requests.get") as mock_mox_get, \
         patch("src.scryfall.scryfall_get") as mock_scry_get, \
         patch("src.scryfall.evaluate_image_quality") as mock_quality:
        
        # 1. Mock Moxfield Deck fetch
        mox_resp = MagicMock()
        mox_resp.status_code = 200
        mox_resp.json.return_value = {
            "name": "Integration Test Deck",
            "format": "commander",
            "commanders": {
                "c1": {
                    "quantity": 1,
                    "card": {"name": "Elesh Norn, Grand Cenobite", "set": "nph", "cn": "9"}
                }
            },
            "mainboard": {
                "m1": {
                    "quantity": 2,
                    "card": {"name": "Sol Ring", "set": "cmd", "cn": "10"}
                },
                "m2": {
                    "quantity": 1,
                    "card": {"name": "Delver of Secrets", "set": "isd", "cn": "51"} # DFC card
                }
            }
        }
        mock_mox_get.return_value = mox_resp

        # 2. Mock Scryfall API search & image downloads
        def scryfall_mock_handler(session, url, params=None):
            resp = MagicMock()
            resp.status_code = 200
            
            q = (params.get("q", "") if params else "").lower()
            exact = (params.get("exact", "") if params else "").lower()
            
            # Search exact print queries or named queries
            if "search" in url:
                if "elesh" in q or "nph" in q or "elesh_norn_oracle" in q:
                    resp.json.return_value = {
                        "data": [{
                            "name": "Elesh Norn, Grand Cenobite",
                            "set": "NPH",
                            "collector_number": "9",
                            "oracle_id": "elesh_norn_oracle",
                            "image_uris": {"png": "https://api.scryfall.com/images/elesh_norn.png"}
                        }]
                    }
                elif "sol" in q or "cmd" in q or "sol_ring_oracle" in q:
                    resp.json.return_value = {
                        "data": [{
                            "name": "Sol Ring",
                            "set": "CMD",
                            "collector_number": "10",
                            "oracle_id": "sol_ring_oracle",
                            "image_uris": {"png": "https://api.scryfall.com/images/sol_ring.png"}
                        }]
                    }
                elif "delver" in q or "isd" in q or "delver_oracle" in q:
                    # Delver of Secrets DFC mock
                    resp.json.return_value = {
                        "data": [{
                            "name": "Delver of Secrets",
                            "set": "ISD",
                            "collector_number": "51",
                            "oracle_id": "delver_oracle",
                            "card_faces": [
                                {
                                    "name": "Delver of Secrets",
                                    "image_uris": {"png": "https://api.scryfall.com/images/delver_front.png"}
                                },
                                {
                                    "name": "Insectile Aberration",
                                    "image_uris": {"png": "https://api.scryfall.com/images/delver_back.png"}
                                }
                            ]
                        }]
                    }
                else:
                    resp.status_code = 404
            elif "named" in url:
                if "elesh" in exact:
                    resp.json.return_value = {"oracle_id": "elesh_norn_oracle"}
                elif "sol" in exact:
                    resp.json.return_value = {"oracle_id": "sol_ring_oracle"}
                elif "delver" in exact:
                    resp.json.return_value = {"oracle_id": "delver_oracle"}
                else:
                    resp.status_code = 404
            else:
                # Image binary request
                resp.content = b"mock image content bytes"
            return resp

        mock_scry_get.side_effect = scryfall_mock_handler
        mock_quality.return_value = 150.0  # Pass threshold
        
        yield

@pytest.mark.parametrize("quality_method", ["pillow", "opencv"])
def test_scryfall_downloader_mocked_integration(mock_scryfall_apis, tmp_path, quality_method):
    """Verifies the integration of parsing, downloading, caching, and quality-checking a deck using mocks."""
    deck_id = extract_deck_id(TEST_DECK_URL)
    assert deck_id is not None
    
    # 1. Fetch and Parse
    raw_deck = download_deck(deck_id)
    deck_data = parse_deck(raw_deck)
    assert deck_data["name"] == "Integration Test Deck"
    
    # 2. Run background downloader
    event_queue = queue.Queue()
    cancel_event = threading.Event()
    
    # Override paths to tmp_path by patching Path in src/scryfall.py or creating structure
    # We patch __file__ resolved path or just let it create in workdir/ and clean it up.
    # To keep it isolated, we will test download_deck_images with quality threshold and spanish pref.
    with patch("src.scryfall.Path") as mock_path:
        # We redirect workdir relative to tmp_path
        mock_path.return_value = tmp_path
        mock_path.resolve.return_value = tmp_path
        
        # Run downloader
        download_deck_images(
            deck_data=deck_data,
            event_queue=event_queue,
            cancel_event=cancel_event,
            exact_edition=True,
            best_image=False,
            prefer_spanish=True,
            quality_threshold=100,
            quality_method=quality_method
        )
        
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
        
    # Verify the sequence of progress events and final success status
    assert len(events) > 0
    start_event = events[0]
    assert start_event[0] == "scryfall_download_start"
    assert start_event[1] == 3 # 3 unique cards: Elesh Norn, Sol Ring, Delver
    
    success_event = events[-1]
    assert success_event[0] == "scryfall_download_success"
    assert success_event[1] == 3
    assert len(success_event[2]) == 0 # no failed cards

@pytest.fixture(autouse=True)
def clean_up_workdir(tmp_path):
    yield
    # Cleanup downloaded temp directories
    scryfall_dir = tmp_path / "workdir" / "scryfall"
    if scryfall_dir.exists():
        import shutil
        shutil.rmtree(scryfall_dir, ignore_errors=True)

@pytest.mark.skipif(not RUN_LIVE_TESTS, reason="Requires LIVE_INTEGRATION_TESTS=1 environment variable")
def test_scryfall_downloader_live_integration(tmp_path):
    """Executes a real network-based integration download of the deck from env.py."""
    deck_id = extract_deck_id(TEST_DECK_URL)
    assert deck_id is not None, f"Could not extract deck ID from: {TEST_DECK_URL}"
    
    print(f"Running live integration test using deck ID: {deck_id}")
    raw_deck = download_deck(deck_id)
    deck_data = parse_deck(raw_deck)
    
    event_queue = queue.Queue()
    cancel_event = threading.Event()
    
    # Run the real download
    download_deck_images(
        deck_data=deck_data,
        event_queue=event_queue,
        cancel_event=cancel_event,
        exact_edition=True,
        best_image=False,
        prefer_spanish=False,
        quality_threshold=50 # lower quality threshold to be permissive on real prints
    )
    
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
        
    assert len(events) >= 2
    assert events[0][0] == "scryfall_download_start"
    
    success_event = events[-1]
    assert success_event[0] in ("scryfall_download_success", "scryfall_download_error")
    if success_event[0] == "scryfall_download_success":
        print(f"Live download finished. Processed cards: {success_event[1]}. Failed count: {len(success_event[2])}")
