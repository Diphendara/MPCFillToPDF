"""Centralized API endpoints for external TCG services.

All URLs used to fetch deck data, card images, and card databases
from external APIs are defined here for easy maintenance.
"""


class MTGEndpoints:
    """Magic: The Gathering API endpoints."""

    # Deck importers
    MOXFIELD = "https://api2.moxfield.com/v3/decks/all/{deck_id}"
    ARCHIDEKT = "https://archidekt.com/api/decks/{deck_id}/"
    DECKSTATS = "https://deckstats.net/api.php"
    TAPPEDOUT = "https://tappedout.net/mtg-decks/{slug}/?fmt=txt"
    MANABOX = "https://manabox.app/decks/{deck_id}"

    # Scryfall
    SCRYFALL_CARDS = "https://api.scryfall.com/cards/{set_code}/{collector_number}"
    SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
    SCRYFALL_NAMED = "https://api.scryfall.com/cards/named"


class OnePieceEndpoints:
    """One Piece TCG API endpoints."""

    DOTGG_DECK = "https://api.dotgg.gg/cgfw/getdeck?game=onepiece&slug={slug}"
    DOTGG_CARDS = "https://api.dotgg.gg/cgfw/getcards?game=onepiece&mode=indexed"
    DOTGG_IMAGE = "https://static.dotgg.gg/onepiece/cards/{card_id}.webp"
    EGMAN_DECK = "https://egmanevents.com/api/decks/{deck_id}"
    CARDKAIZOKU_DECK = "https://cardkaizoku.com/api/decks/{deck_id}"


class RiftboundEndpoints:
    """Riftbound API endpoints."""

    # dotgg (riftbound.gg)
    DOTGG_DECK = "https://api.dotgg.gg/cgfw/getdeck?game=riftbound&slug={slug}"
    DOTGG_CARDS = "https://api.dotgg.gg/cgfw/getcards?game=riftbound&mode=indexed"
    DOTGG_IMAGE = "https://static.dotgg.gg/riftbound/cards/{code}.webp"

    # Piltover Archive
    PILTOVER_DECK = "https://piltoverarchive.com/api/trpc/deck.get?input={input}"
    PILTOVER_CARDS = "https://piltoverarchive.com/api/trpc/card.list?input={input}"
    PILTOVER_IMAGE = "https://piltoverarchive.com/cards/{card_id}.webp"

    # Other sites
    RIFTMANA_DECK = "https://riftmana.com/api/decks/{uuid}"
    RIFTBINDER_DECK = "https://riftbinder.com/api/decks/{deck_id}"
    RIFTDEX_DECK = "https://riftdex.com/api/decks/{deck_id}"


class LorcanaEndpoints:
    """Lorcana API endpoints."""

    DOTGG_DECK = "https://api.dotgg.gg/cgfw/getdeck?game=lorcana&slug={slug}"
    DOTGG_CARDS = "https://api.dotgg.gg/cgfw/getcards?game=lorcana&mode=indexed"
    DOTGG_IMAGE = "https://static.dotgg.gg/lorcana/cards/{card_id}.webp"
    INKDECKS_DECK = "https://inkdecks.com/api/lorcana/decks/{deck_id}"
    INKDECKS_IMAGE = "https://inkdecks.com/images/lorcana/cards/{card_id}.webp"


class YuGiOhEndpoints:
    """Yu-Gi-Oh! API endpoints."""

    YGOPRODECK_DECK = "https://db.ygoprodeck.com/api/v7/deck.php?id={deck_id}"
    YGOPRODECK_CARD = "https://db.ygoprodeck.com/api/v7/cardinfo.php?id={card_id}"
    YGOPRODECK_IMAGE = "https://images.ygoprodeck.com/images/cards/{card_id}.jpg"
    YUGIOHMETA_DECK = "https://yugiohmeta.com/api/decks/{deck_id}"


class GoogleDriveEndpoints:
    """Google Drive API endpoints for image downloads."""

    DRIVE_IMAGE = "https://lh4.googleusercontent.com/d/{drive_id}=d"
