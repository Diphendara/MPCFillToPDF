import os
import shutil
import queue
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image, ImageDraw

from src.downloader import evaluate_image_quality
from src.scryfall import (
    sanitize_filename,
    get_cached_card,
    process_exact_edition,
    process_best_image,
)

# 1. Test Pillow quality check
def test_evaluate_image_quality(tmp_path):
    # Create a sharp image (high variance)
    img_sharp = Image.new("RGB", (100, 100), color="white")
    draw = ImageDraw.Draw(img_sharp)
    draw.rectangle([25, 25, 75, 75], fill="black")
    sharp_path = tmp_path / "sharp.png"
    img_sharp.save(sharp_path)
    
    # Create a smooth image (low variance)
    img_smooth = Image.new("RGB", (100, 100), color="gray")
    smooth_path = tmp_path / "smooth.png"
    img_smooth.save(smooth_path)
    
    q_sharp = evaluate_image_quality(sharp_path, method="pillow")
    q_smooth = evaluate_image_quality(smooth_path, method="pillow")
    
    assert q_sharp > q_smooth
    assert q_smooth < 700.0

# 1.2 Test OpenCV quality check
def test_evaluate_image_quality_opencv(tmp_path):
    # Create a sharp image (high variance)
    img_sharp = Image.new("RGB", (100, 100), color="white")
    draw = ImageDraw.Draw(img_sharp)
    draw.rectangle([25, 25, 75, 75], fill="black")
    sharp_path = tmp_path / "sharp.png"
    img_sharp.save(sharp_path)
    
    # Create a smooth image (low variance)
    img_smooth = Image.new("RGB", (100, 100), color="gray")
    smooth_path = tmp_path / "smooth.png"
    img_smooth.save(smooth_path)
    
    q_sharp = evaluate_image_quality(sharp_path, method="opencv")
    q_smooth = evaluate_image_quality(smooth_path, method="opencv")
    
    assert q_sharp > q_smooth
    assert q_smooth < 1000.0

# 2. Test mutual exclusion behavior
def test_mutual_exclusion():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display available — Tkinter tests skipped")
    
    class FakeApp:
        def __init__(self):
            self.exact_edition = tk.BooleanVar(value=True)
            self.best_image = tk.BooleanVar(value=False)
            
        def _on_exact_edition_changed(self) -> None:
            if self.exact_edition.get():
                self.best_image.set(False)

        def _on_best_image_changed(self) -> None:
            if self.best_image.get():
                self.exact_edition.set(False)
                
    app = FakeApp()
    
    # Check exact_edition -> unchecks best_image
    app.best_image.set(True)
    app.exact_edition.set(True)
    app._on_exact_edition_changed()
    assert not app.best_image.get()
    
    # Check best_image -> unchecks exact_edition
    app.best_image.set(True)
    app._on_best_image_changed()
    assert not app.exact_edition.get()
    
    root.destroy()

# 3. Test caching
def test_caching(tmp_path):
    deck_dir = tmp_path / "deck"
    cache_dir = tmp_path / "cache"
    deck_dir.mkdir()
    cache_dir.mkdir()
    
    prefix = sanitize_filename("Sol Ring") + "_" + sanitize_filename("CMD") + "_" + sanitize_filename("10")
    img = Image.new("RGB", (100, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 90, 90], fill="black")
    
    cache_file = cache_dir / f"{prefix}.png"
    img.save(cache_file)
    
    # Check cache hit above threshold
    q = get_cached_card("Sol Ring", "CMD", "10", is_dfc=False, threshold=50, deck_dir=deck_dir, cache_dir=cache_dir)
    assert q is not None
    assert q >= 50
    assert (deck_dir / f"{prefix}.png").exists()
    
    # Check cache miss below threshold
    (deck_dir / f"{prefix}.png").unlink()
    q2 = get_cached_card("Sol Ring", "CMD", "10", is_dfc=False, threshold=99999, deck_dir=deck_dir, cache_dir=cache_dir)
    assert q2 is None
    assert not (deck_dir / f"{prefix}.png").exists()

# 4. Test DFC quality checks and cache
def test_dfc_caching(tmp_path):
    deck_dir = tmp_path / "deck"
    cache_dir = tmp_path / "cache"
    deck_dir.mkdir()
    cache_dir.mkdir()
    
    prefix = sanitize_filename("Delver") + "_" + sanitize_filename("ISD") + "_" + sanitize_filename("51")
    
    # Create front and back in cache
    img_front = Image.new("RGB", (100, 100), color="white")
    img_back = Image.new("RGB", (100, 100), color="white")
    draw_f = ImageDraw.Draw(img_front)
    draw_b = ImageDraw.Draw(img_back)
    draw_f.rectangle([10, 10, 90, 90], fill="black")
    draw_b.rectangle([10, 10, 90, 90], fill="black")
    
    img_front.save(cache_dir / f"{prefix}_front.png")
    img_back.save(cache_dir / f"{prefix}_back.png")
    
    # Min quality meets threshold
    q = get_cached_card("Delver", "ISD", "51", is_dfc=True, threshold=50, deck_dir=deck_dir, cache_dir=cache_dir)
    assert q is not None
    assert q >= 50
    assert (deck_dir / f"{prefix}_front.png").exists()
    assert (deck_dir / f"{prefix}_back.png").exists()

# 5. Test Fallback logic calls (using mock searches)
@patch("src.scryfall.scryfall_get")
@patch("src.scryfall.evaluate_image_quality")
def test_fallback_logic(mock_quality, mock_get, tmp_path):
    # Setup dynamic mock function for scryfall_get matching (session, url, params=None)
    def mock_scryfall_get(session, url, params=None):
        resp = MagicMock()
        q = params.get("q", "") if params else ""
        
        if "lang:es" in q or "lang:es" in url:
            if "set:CMD cn:10" in q:
                # Exact Spanish print 404
                resp.status_code = 404
            else:
                # Other Spanish prints
                resp.status_code = 200
                resp.json.return_value = {
                    "data": [{
                        "name": "Sol Ring",
                        "set": "ALT",
                        "collector_number": "20",
                        "oracle_id": "fake_oracle_id",
                        "image_uris": {"png": "http://example.com/sol_ring_alt_es.png"}
                    }]
                }
        elif "lang:en" in q or "lang:en" in url:
            # English prints
            resp.status_code = 200
            resp.json.return_value = {
                "data": [{
                    "name": "Sol Ring",
                    "set": "CMD",
                    "collector_number": "10",
                    "oracle_id": "fake_oracle_id",
                    "image_uris": {"png": "http://example.com/sol_ring_en.png"}
                }]
            }
        else:
            # Image download
            resp.status_code = 200
            resp.content = b"fake image bytes"
        return resp
        
    mock_get.side_effect = mock_scryfall_get
    mock_quality.return_value = 120.0
    
    session = MagicMock()
    cancel_event = threading.Event()
    
    deck_dir = tmp_path / "deck"
    cache_dir = tmp_path / "cache"
    deck_dir.mkdir()
    cache_dir.mkdir()
    
    success, reason = process_exact_edition(
        session, "Sol Ring", "CMD", "10", prefer_spanish=True, threshold=100, deck_dir=deck_dir, cache_dir=cache_dir, cancel_event=cancel_event
    )
    
    assert success
    assert mock_get.call_count >= 2

@patch("src.scryfall.scryfall_get")
@patch("src.scryfall.evaluate_image_quality")
def test_exact_edition_failures(mock_quality, mock_get, tmp_path):
    session = MagicMock()
    cancel_event = threading.Event()
    deck_dir = tmp_path / "deck"
    cache_dir = tmp_path / "cache"
    deck_dir.mkdir()
    cache_dir.mkdir()

    # 1. Test Print Not Found on Scryfall
    resp_404 = MagicMock()
    resp_404.status_code = 404
    mock_get.return_value = resp_404
    
    success, reason = process_exact_edition(
        session, "Sol Ring", "CMD", "10", prefer_spanish=False, threshold=100, deck_dir=deck_dir, cache_dir=cache_dir, cancel_event=cancel_event
    )
    assert not success
    assert "Print not found" in reason

    # 2. Test Image Quality Mismatch
    def mock_scryfall_get(session, url, params=None):
        resp = MagicMock()
        if "search" in url:
            resp.status_code = 200
            resp.json.return_value = {
                "data": [{
                    "name": "Sol Ring",
                    "set": "CMD",
                    "collector_number": "10",
                    "oracle_id": "fake_oracle_id",
                    "image_uris": {"png": "http://example.com/sol_ring.png"}
                }]
            }
        else:
            resp.status_code = 200
            resp.content = b"fake image bytes"
        return resp
    mock_get.side_effect = mock_scryfall_get
    mock_quality.return_value = 85.0 # below 100 threshold

    success, reason = process_exact_edition(
        session, "Sol Ring", "CMD", "10", prefer_spanish=False, threshold=100, deck_dir=deck_dir, cache_dir=cache_dir, cancel_event=cancel_event
    )
    assert not success
    assert "Image quality issue" in reason
    assert "Best score was 85.0" in reason

    # 3. Test Connection Error
    import requests
    mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
    
    success, reason = process_exact_edition(
        session, "Sol Ring", "CMD", "10", prefer_spanish=False, threshold=100, deck_dir=deck_dir, cache_dir=cache_dir, cancel_event=cancel_event
    )
    assert not success
    assert "Connection issue" in reason

def test_quality_method_toggle():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display available — Tkinter tests skipped")
        
    class FakeApp:
        def __init__(self):
            self.quality_threshold = tk.StringVar(value="100")
            self.use_opencv_quality = tk.BooleanVar(value=False)
            
        def _on_toggle_quality_method(self) -> None:
            if self.use_opencv_quality.get():
                self.quality_threshold.set("300")
            else:
                self.quality_threshold.set("100")
                
    app = FakeApp()
    
    # Toggle to OpenCV -> threshold changes to 300
    app.use_opencv_quality.set(True)
    app._on_toggle_quality_method()
    assert app.quality_threshold.get() == "300"
    
    # Toggle back to Pillow -> threshold changes to 100
    app.use_opencv_quality.set(False)
    app._on_toggle_quality_method()
    assert app.quality_threshold.get() == "100"
    
    root.destroy()

@patch("src.scryfall.download_image_file")
@patch("src.scryfall.evaluate_image_quality")
def test_quality_evaluation_logging(mock_quality, mock_download, tmp_path):
    import csv
    from src.scryfall import log_quality_evaluation, download_card_from_scryfall_object
    
    deck_dir = tmp_path / "deck"
    cache_dir = tmp_path / "cache"
    deck_dir.mkdir()
    cache_dir.mkdir()
    
    # 1. Test log_quality_evaluation directly
    csv_path = deck_dir / "downloaded_images_quality.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Card Name", "Set", "Collector Number", "File Path", "Method", "Quality Score", "Status"])
        
    log_quality_evaluation(
        deck_dir, "Test Card", "TST", "1", deck_dir / "Test_Card_TST_1.png", "pillow", 123.45, "Accepted"
    )
    
    assert csv_path.exists()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    
    assert len(rows) == 2
    assert rows[0] == ["Card Name", "Set", "Collector Number", "File Path", "Method", "Quality Score", "Status"]
    assert rows[1][0] == "Test Card"
    assert rows[1][1] == "TST"
    assert rows[1][2] == "1"
    assert rows[1][4] == "pillow"
    assert rows[1][5] == "123.45"
    assert rows[1][6] == "Accepted"
    
    # 2. Test get_cached_card caching logs
    prefix = sanitize_filename("Sol Ring") + "_" + sanitize_filename("CMD") + "_" + sanitize_filename("10")
    img = Image.new("RGB", (100, 100), color="white")
    cache_file = cache_dir / f"{prefix}.png"
    img.save(cache_file)
    
    # Reset CSV file
    csv_path.unlink()
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Card Name", "Set", "Collector Number", "File Path", "Method", "Quality Score", "Status"])
        
    # Cache hit
    mock_quality.return_value = 150.0
    q = get_cached_card("Sol Ring", "CMD", "10", is_dfc=False, threshold=100, deck_dir=deck_dir, cache_dir=cache_dir, quality_method="pillow")
    assert q == 150.0
    
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2
    assert rows[1][0] == "Sol Ring"
    assert rows[1][6] == "Cached"
    
    # Cache below threshold
    csv_path.unlink()
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Card Name", "Set", "Collector Number", "File Path", "Method", "Quality Score", "Status"])
    
    q2 = get_cached_card("Sol Ring", "CMD", "10", is_dfc=False, threshold=200, deck_dir=deck_dir, cache_dir=cache_dir, quality_method="pillow")
    assert q2 is None
    
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2
    assert rows[1][0] == "Sol Ring"
    assert rows[1][6] == "Rejected (Below Threshold)"
    
    # 3. Test download_card_from_scryfall_object logs
    def mock_download_image(session, url, dest_path, cancel_event):
        img.save(dest_path)
        return True, ""
    mock_download.side_effect = mock_download_image
    mock_quality.return_value = 95.0
    
    csv_path.unlink()
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Card Name", "Set", "Collector Number", "File Path", "Method", "Quality Score", "Status"])
        
    card_obj = {
        "name": "Black Lotus",
        "set": "2ED",
        "collector_number": "1",
        "image_uris": {"png": "http://example.com/lotus.png"}
    }
    
    session = MagicMock()
    cancel_event = threading.Event()
    
    success, q_val, is_dfc, err = download_card_from_scryfall_object(
        session, card_obj, "Black Lotus", "2ED", "1", deck_dir, cache_dir, cancel_event, threshold=100, quality_method="opencv"
    )
    
    assert success
    assert q_val == 95.0
    
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2
    assert rows[1][0] == "Black Lotus"
    assert rows[1][4] == "opencv"
    assert rows[1][5] == "95.00"
    assert rows[1][6] == "Rejected (Below Threshold)"


