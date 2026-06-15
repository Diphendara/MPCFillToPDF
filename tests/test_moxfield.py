import pytest
from src.moxfield import is_moxfield_url, extract_deck_id, parse_deck

def test_is_moxfield_url():
    assert is_moxfield_url("https://www.moxfield.com/decks/abc-123") is True
    assert is_moxfield_url("MOXFIELD.COM/DECKS/XYZ") is True
    assert is_moxfield_url("https://google.com") is False
    assert is_moxfield_url("moxfield") is True

def test_extract_deck_id():
    # Valid URLs
    assert extract_deck_id("https://www.moxfield.com/decks/abc_123-xyz") == "abc_123-xyz"
    assert extract_deck_id("moxfield.com/decks/12345") == "12345"
    assert extract_deck_id("https://www.moxfield.com/decks/abc-123/edit") == "abc-123"
    
    # Raw IDs
    assert extract_deck_id("abc_123-xyz") == "abc_123-xyz"
    assert extract_deck_id("  12345  ") == "12345"
    
    # Invalid URLs/Inputs
    assert extract_deck_id("https://google.com") is None
    assert extract_deck_id("") is None

def test_parse_deck():
    mock_json = {
        "name": "Test Deck",
        "format": "commander",
        "createdByUser": {"userName": "TestAuthor"},
        "commanders": {
            "card-id-1": {
                "quantity": 1,
                "card": {
                    "name": "Elesh Norn, Grand Cenobite",
                    "set": "nph",
                    "cn": "9"
                }
            }
        },
        "mainboard": {
            "card-id-2": {
                "quantity": 4,
                "card": {
                    "name": "Plains",
                    "set": "m21",
                    "cn": "260"
                }
            }
        },
        "sideboard": {},
        "tokens": [
            {
                "quantity": 2,
                "card": {
                    "name": "Cat Token",
                    "set": "txmy",
                    "cn": "1"
                }
            },
            {
                # Direct format
                "name": "Soldier Token",
                "set": "txmy",
                "cn": "2",
                "quantity": 1
            }
        ]
    }
    
    parsed = parse_deck(mock_json)
    
    assert parsed["name"] == "Test Deck"
    assert parsed["format"] == "commander"
    assert parsed["author"] == "TestAuthor"
    
    # Check commanders
    assert len(parsed["commanders"]) == 1
    assert parsed["commanders"][0] == {
        "quantity": 1,
        "name": "Elesh Norn, Grand Cenobite",
        "set": "NPH",
        "cn": "9"
    }
    
    # Check mainboard
    assert len(parsed["mainboard"]) == 1
    assert parsed["mainboard"][0] == {
        "quantity": 4,
        "name": "Plains",
        "set": "M21",
        "cn": "260"
    }
    
    # Check sideboard
    assert len(parsed["sideboard"]) == 0
    
    # Check tokens
    assert len(parsed["tokens"]) == 2
    assert parsed["tokens"][0] == {
        "quantity": 2,
        "name": "Cat Token",
        "set": "TXMY",
        "cn": "1"
    }
    assert parsed["tokens"][1] == {
        "quantity": 1,
        "name": "Soldier Token",
        "set": "TXMY",
        "cn": "2"
    }
