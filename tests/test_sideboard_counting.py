"""Tests for sideboard counting across all TCGs."""

from src.rb_scraper import RBCard, RBDeck
from src.ygo_scraper import YGOCard, YGODeck


class TestRiftboundSideboard:
    """Verify Riftbound sideboard counting."""

    def test_total_slots_excludes_sideboard(self):
        deck = RBDeck(
            name="Test",
            deck_id="test-1",
            cards=[
                RBCard("c1", "Card 1", 3, "maindeck"),
                RBCard("c2", "Card 2", 2, "maindeck"),
                RBCard("s1", "Side 1", 2, "sideboard"),
                RBCard("s2", "Side 2", 1, "sideboard"),
            ],
        )
        assert deck.total_slots == 5  # 3 + 2
        assert deck.side_slots == 3  # 2 + 1
        assert deck.total_slots_with_side == 8  # 5 + 3

    def test_empty_sideboard(self):
        deck = RBDeck(
            name="Test",
            deck_id="test-2",
            cards=[
                RBCard("c1", "Card 1", 3, "maindeck"),
            ],
        )
        assert deck.total_slots == 3
        assert deck.side_slots == 0
        assert deck.total_slots_with_side == 3


class TestYugiohSideboard:
    """Verify Yu-Gi-Oh sideboard counting."""

    def test_total_slots_excludes_side_by_default(self):
        deck = YGODeck(
            name="Test",
            deck_id="test-1",
            cards=[
                YGOCard(1, "Main Card", 3, "main"),
                YGOCard(2, "Extra Card", 2, "extra"),
                YGOCard(3, "Side Card", 2, "side"),
            ],
        )
        assert deck.total_slots(include_side=False) == 5  # 3 + 2
        assert deck.total_slots(include_side=True) == 7  # 5 + 2

    def test_side_slots_property(self):
        deck = YGODeck(
            name="Test",
            deck_id="test-2",
            cards=[
                YGOCard(1, "Main Card", 3, "main"),
                YGOCard(3, "Side Card 1", 2, "side"),
                YGOCard(4, "Side Card 2", 1, "side"),
            ],
        )
        assert deck.side_slots == 3  # 2 + 1


class TestMTGSideboard:
    """Verify MTG sideboard counting via active_count."""

    def test_active_count_respects_include_side(self):
        from gui.main import MTGUrlDeck

        class MockCard:
            def __init__(self, name, quantity, zone):
                self.name = name
                self.quantity = quantity
                self.zone = zone

        deck = MTGUrlDeck(
            url="https://moxfield.com/decks/test",
            cards=[
                MockCard("Main 1", 4, "main"),
                MockCard("Main 2", 2, "main"),
                MockCard("Side 1", 3, "side"),
                MockCard("Token 1", 1, "token"),
            ],
            name="Test Deck",
        )
        deck.include_side = False
        deck.include_tokens = False
        deck.selected_card_ids = None  # Select all

        assert deck.active_count == 6  # 4 + 2

        deck.include_side = True
        assert deck.active_count == 9  # 6 + 3

        deck.include_tokens = True
        assert deck.active_count == 10  # 9 + 1

    def test_active_count_with_selection(self):
        from gui.main import MTGUrlDeck

        class MockCard:
            def __init__(self, name, quantity, zone):
                self.name = name
                self.quantity = quantity
                self.zone = zone

        card1 = MockCard("Main 1", 4, "main")
        card2 = MockCard("Main 2", 2, "main")

        deck = MTGUrlDeck(
            url="https://moxfield.com/decks/test",
            cards=[card1, card2],
            name="Test Deck",
        )
        deck.include_side = False
        deck.include_tokens = False
        deck.selected_card_ids = {id(card1)}  # Only select first card

        assert deck.active_count == 4  # Only card1
