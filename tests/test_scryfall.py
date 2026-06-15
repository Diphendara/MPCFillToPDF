import queue
import threading
import pytest
from src.scryfall import download_deck_images

def test_download_deck_images_success():
    deck_data = {
        "commanders": [{"name": "Elesh Norn", "quantity": 1}],
        "mainboard": [{"name": "Plains", "quantity": 4}],
        "sideboard": [],
        "tokens": []
    }
    event_queue = queue.Queue()
    cancel_event = threading.Event()
    
    # Run synchronously in main thread for testing
    download_deck_images(deck_data, event_queue, cancel_event)
    
    # Collect all events
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
        
    assert len(events) == 4
    
    # First event should be start
    assert events[0][0] == "scryfall_download_start"
    assert events[0][1] == 2  # 2 unique card entries: Elesh Norn, Plains
    
    # Progress events
    assert events[1][0] == "scryfall_download_progress"
    assert events[1][1] == 1
    assert events[1][2] == 2
    assert events[1][3] == 50
    assert events[1][4] == "Elesh Norn"
    
    assert events[2][0] == "scryfall_download_progress"
    assert events[2][1] == 2
    assert events[2][2] == 2
    assert events[2][3] == 100
    assert events[2][4] == "Plains"
    
    # Success event
    assert events[3][0] == "scryfall_download_success"
    assert events[3][1] == 2

def test_download_deck_images_empty():
    deck_data = {
        "commanders": [],
        "mainboard": [],
        "sideboard": [],
        "tokens": []
    }
    event_queue = queue.Queue()
    cancel_event = threading.Event()
    
    download_deck_images(deck_data, event_queue, cancel_event)
    
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
        
    assert len(events) == 2
    assert events[0] == ("scryfall_download_start", 0)
    assert events[1][:2] == ("scryfall_download_success", 0)

def test_download_deck_images_cancelled():
    deck_data = {
        "commanders": [{"name": "Elesh Norn", "quantity": 1}],
        "mainboard": [{"name": "Plains", "quantity": 4}],
        "sideboard": [],
        "tokens": []
    }
    event_queue = queue.Queue()
    cancel_event = threading.Event()
    cancel_event.set()  # Cancel immediately
    
    download_deck_images(deck_data, event_queue, cancel_event)
    
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
        
    # Should only put scryfall_download_start and then return because of cancellation
    assert len(events) == 1
    assert events[0] == ("scryfall_download_start", 2)

def test_download_deck_images_error():
    # Pass invalid data (None) to trigger an exception
    event_queue = queue.Queue()
    cancel_event = threading.Event()
    
    download_deck_images(None, event_queue, cancel_event)
    
    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
        
    assert len(events) == 1
    assert events[0][0] == "scryfall_download_error"
    assert "object is not iterable" in events[0][1] or "TypeError" in events[0][1] or "NoneType" in events[0][1]
