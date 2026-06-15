import re
import logging
import requests

_log = logging.getLogger(__name__)

# Pattern to match moxfield.com/decks/DECK_ID
MOXFIELD_DECK_PATTERN = re.compile(r"moxfield\.com/decks/([a-zA-Z0-9\-_]+)", re.IGNORECASE)

def is_moxfield_url(url: str) -> bool:
    """Check if the given URL contains 'moxfield'."""
    return "moxfield" in url.lower()

def extract_deck_id(url_or_id: str) -> str | None:
    """Extract the Moxfield deck ID from a URL or return it directly if it's already an ID."""
    match = MOXFIELD_DECK_PATTERN.search(url_or_id)
    if match:
        return match.group(1)
    
    # If it's a URL but doesn't match the deck pattern, return None
    if url_or_id.startswith("http://") or url_or_id.startswith("https://"):
        return None
        
    # Otherwise assume it's a raw deck ID
    return url_or_id.strip() if url_or_id.strip() else None

def download_deck(deck_id: str) -> dict:
    """Download the deck JSON from the unofficial Moxfield API."""
    url = f"https://api.moxfield.com/v2/decks/all/{deck_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    
    _log.info(f"Downloading Moxfield deck: {deck_id} from {url}")
    response = requests.get(url, headers=headers, timeout=(10, 30))
    response.raise_for_status()
    
    return response.json()

def parse_deck(deck_json: dict) -> dict:
    """Parse card zones (mainboard, commanders, sideboard, tokens) from Moxfield JSON.
    
    Returns:
        A dict with keys 'name', 'format', 'author', and card lists for each zone.
    """
    deck = {
        "name": deck_json.get("name", "Moxfield Deck"),
        "format": deck_json.get("format", ""),
        "author": deck_json.get("createdByUser", {}).get("userName", "") if deck_json.get("createdByUser") else "",
        "commanders": [],
        "mainboard": [],
        "sideboard": [],
        "tokens": []
    }
    
    def parse_zone_dict(zone_data) -> list:
        cards = []
        if not zone_data:
            return cards
        
        # If it's a dict, iterate values
        items = zone_data.values() if isinstance(zone_data, dict) else zone_data
        
        for item in items:
            if not isinstance(item, dict):
                continue
            card_data = item.get("card", {})
            quantity = item.get("quantity", 1)
            # Some zones (like commanders) might not have quantity but count as 1
            if quantity is None:
                quantity = 1
                
            cards.append({
                "quantity": quantity,
                "name": card_data.get("name", ""),
                "set": card_data.get("set", "").upper(),
                "cn": card_data.get("cn", "")
            })
        return cards

    deck["commanders"] = parse_zone_dict(deck_json.get("commanders"))
    deck["mainboard"] = parse_zone_dict(deck_json.get("mainboard"))
    deck["sideboard"] = parse_zone_dict(deck_json.get("sideboard"))
    
    # Tokens can be structured differently (as seen in some internal formats)
    tokens_data = deck_json.get("tokens", [])
    if isinstance(tokens_data, dict):
        tokens_data = tokens_data.values()
        
    for token in tokens_data:
        if not isinstance(token, dict):
            continue
        # Check if it has a nested 'card' structure or is direct
        if "card" in token:
            card_data = token.get("card", {})
            quantity = token.get("quantity", 1)
        else:
            card_data = token
            quantity = token.get("quantity", 1)
            
        deck["tokens"].append({
            "quantity": quantity if quantity is not None else 1,
            "name": card_data.get("name", ""),
            "set": card_data.get("set", "").upper(),
            "cn": card_data.get("cn", "")
        })
        
    return deck

