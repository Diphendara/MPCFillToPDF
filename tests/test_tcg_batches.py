"""Tests for src/tcg_batches.py — batch adapters for TCG decks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.lorcana_scraper import LocanaDeck, LorcanaCard
from src.op_scraper import OPCard, OPDeck
from src.rb_scraper import RBCard, RBDeck
from src.tcg_batches import (
    LorcanaBatchAdapter,
    OnePieceBatchAdapter,
    RiftboundBatchAdapter,
    YugiohBatchAdapter,
)
from src.ygo_scraper import YGOCard, YGODeck


def _make_rb_card(
    card_id: str,
    name: str,
    section: str = "maindeck",
    quantity: int = 1,
    variant_id: str | None = None,
) -> RBCard:
    """Helper to create a Riftbound card for testing."""
    return RBCard(
        card_id=card_id,
        variant_id=variant_id or card_id,
        name=name,
        card_type="Unit",
        card_super=None,
        quantity=quantity,
        image_url=f"https://example.com/{card_id}.webp",
        section=section,
    )


def _make_rb_deck(
    name: str,
    cards: list[RBCard],
    deck_id: str = "test-deck",
) -> RBDeck:
    """Helper to create a Riftbound deck for testing."""
    return RBDeck(deck_id=deck_id, name=name, cards=cards)


class TestRiftboundBatchAdapter:
    """Tests for RiftboundBatchAdapter."""

    def test_empty_decks_returns_empty_batch(self, tmp_path: Path) -> None:
        """Empty deck list returns empty PrintBatch."""
        adapter = RiftboundBatchAdapter(
            decks=(),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        batch = adapter.prepare()
        assert batch.name == "Riftbound"
        assert batch.fronts == []
        assert batch.backs == []

    def test_filters_sideboard_when_excluded(self, tmp_path: Path) -> None:
        """Sideboard cards are excluded when include_sideboard=False."""
        main_card = _make_rb_card("OGN-001", "Main Card", "maindeck", 3)
        side_card = _make_rb_card("OGN-002", "Side Card", "sideboard", 2, "OGN-002_sb")
        deck = _make_rb_deck("Test Deck", [main_card, side_card])

        adapter = RiftboundBatchAdapter(
            decks=((deck, True, False),),  # include_runes=True, include_sideboard=False
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )

        with (
            patch("src.tcg_batches.rb_download") as mock_download,
            patch("src.tcg_batches.rb_expand") as mock_expand,
            patch("src.tcg_batches.get_rb_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([], [])
            mock_backs.return_value = {"maindeck": tmp_path / "back.png"}

            adapter.prepare()

            # Check that the deck passed to download had sideboard filtered
            call_args = mock_download.call_args
            filtered_deck = call_args[0][0]
            assert len(filtered_deck.cards) == 1
            assert filtered_deck.cards[0].name == "Main Card"

    def test_includes_sideboard_when_enabled(self, tmp_path: Path) -> None:
        """Sideboard cards are included when include_sideboard=True."""
        main_card = _make_rb_card("OGN-001", "Main Card", "maindeck", 3)
        side_card = _make_rb_card("OGN-002", "Side Card", "sideboard", 2, "OGN-002_sb")
        deck = _make_rb_deck("Test Deck", [main_card, side_card])

        adapter = RiftboundBatchAdapter(
            decks=((deck, True, True),),  # include_runes=True, include_sideboard=True
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )

        with (
            patch("src.tcg_batches.rb_download") as mock_download,
            patch("src.tcg_batches.rb_expand") as mock_expand,
            patch("src.tcg_batches.get_rb_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([], [])
            mock_backs.return_value = {"maindeck": tmp_path / "back.png"}

            adapter.prepare()

            # Check that the deck passed to download included sideboard
            call_args = mock_download.call_args
            filtered_deck = call_args[0][0]
            assert len(filtered_deck.cards) == 2

    def test_filters_runes_when_excluded(self, tmp_path: Path) -> None:
        """Rune cards are passed to expand with include_runes flag."""
        rune_card = _make_rb_card("OGN-R01", "Mind Rune", "rune", 6)
        main_card = _make_rb_card("OGN-001", "Main Card", "maindeck", 3)
        deck = _make_rb_deck("Test Deck", [rune_card, main_card])

        adapter = RiftboundBatchAdapter(
            decks=((deck, False, True),),  # include_runes=False, include_sideboard=True
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )

        with (
            patch("src.tcg_batches.rb_download") as mock_download,
            patch("src.tcg_batches.rb_expand") as mock_expand,
            patch("src.tcg_batches.get_rb_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([], [])
            mock_backs.return_value = {"maindeck": tmp_path / "back.png"}

            adapter.prepare()

            # Check that expand was called with include_runes=False
            call_kwargs = mock_expand.call_args[1]
            assert call_kwargs["include_runes"] is False

    def test_selected_card_ids_filtering(self, tmp_path: Path) -> None:
        """Only selected cards are included when selected_card_ids is set."""
        card1 = _make_rb_card("OGN-001", "Card 1", "maindeck", 1)
        card2 = _make_rb_card("OGN-002", "Card 2", "maindeck", 1)
        deck = _make_rb_deck("Test Deck", [card1, card2])
        # Simulate user selecting only card1
        deck.selected_card_ids = {"OGN-001"}

        adapter = RiftboundBatchAdapter(
            decks=((deck, True, True),),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )

        with (
            patch("src.tcg_batches.rb_download") as mock_download,
            patch("src.tcg_batches.rb_expand") as mock_expand,
            patch("src.tcg_batches.get_rb_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([], [])
            mock_backs.return_value = {"maindeck": tmp_path / "back.png"}

            adapter.prepare()

            # Check that only selected card was downloaded
            call_args = mock_download.call_args
            filtered_deck = call_args[0][0]
            assert len(filtered_deck.cards) == 1
            assert filtered_deck.cards[0].card_id == "OGN-001"

    def test_multiple_decks_combined(self, tmp_path: Path) -> None:
        """Multiple decks are combined into a single batch."""
        deck1 = _make_rb_deck("Deck 1", [_make_rb_card("OGN-001", "Card 1")])
        deck2 = _make_rb_deck("Deck 2", [_make_rb_card("OGN-002", "Card 2")])

        adapter = RiftboundBatchAdapter(
            decks=((deck1, True, True), (deck2, True, True)),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )

        with (
            patch("src.tcg_batches.rb_download") as mock_download,
            patch("src.tcg_batches.rb_expand") as mock_expand,
            patch("src.tcg_batches.get_rb_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([Path("f1.png")], [None])
            mock_backs.return_value = {"maindeck": tmp_path / "back.png"}

            batch = adapter.prepare()

            assert batch.name == "Riftbound"
            assert mock_download.call_count == 2
            assert mock_expand.call_count == 2


def _make_ygo_card(card_id: int, name: str, quantity: int = 1, zone: str = "main") -> YGOCard:
    """Helper to create a Yu-Gi-Oh! card for testing."""
    return YGOCard(card_id=card_id, name=name, quantity=quantity, zone=zone)


class TestYugiohBatchAdapter:
    """Tests for YugiohBatchAdapter."""

    def test_empty_decks_returns_empty_batch(self, tmp_path: Path) -> None:
        """Empty deck list returns empty PrintBatch."""
        adapter = YugiohBatchAdapter(
            decks=(),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        batch = adapter.prepare()
        assert batch.name == "yugioh_proxies"
        assert batch.fronts == []

    def test_sideboard_excluded_when_include_side_false(self, tmp_path: Path) -> None:
        """Side deck cards are not expanded when include_side=False."""
        deck = YGODeck(
            name="Test",
            deck_id="d1",
            cards=[
                _make_ygo_card(1, "Blue-Eyes White Dragon", 3, "main"),
                _make_ygo_card(2, "Effect Veiler", 2, "side"),
            ],
        )
        adapter = YugiohBatchAdapter(
            decks=((deck, False),),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.ygo_download") as mock_download,
            patch("src.tcg_batches.ygo_expand") as mock_expand,
            patch("src.tcg_batches.get_ygo_back") as mock_back,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = []
            mock_back.return_value = tmp_path / "back.png"
            adapter.prepare()
            include_side = mock_expand.call_args[0][2]
            assert include_side is False

    def test_sideboard_included_when_include_side_true(self, tmp_path: Path) -> None:
        """Side deck cards are expanded when include_side=True."""
        deck = YGODeck(
            name="Test",
            deck_id="d1",
            cards=[
                _make_ygo_card(1, "Blue-Eyes White Dragon", 3, "main"),
                _make_ygo_card(2, "Effect Veiler", 2, "side"),
            ],
        )
        adapter = YugiohBatchAdapter(
            decks=((deck, True),),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.ygo_download") as mock_download,
            patch("src.tcg_batches.ygo_expand") as mock_expand,
            patch("src.tcg_batches.get_ygo_back") as mock_back,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = []
            mock_back.return_value = tmp_path / "back.png"
            adapter.prepare()
            include_side = mock_expand.call_args[0][2]
            assert include_side is True

    def test_selected_card_ids_filtering(self, tmp_path: Path) -> None:
        """Only selected cards are downloaded when selected_card_ids is set."""
        deck = YGODeck(
            name="Test",
            deck_id="d1",
            cards=[
                _make_ygo_card(1, "Blue-Eyes White Dragon", 1),
                _make_ygo_card(2, "Dark Magician", 1),
            ],
        )
        deck.selected_card_ids = {1}
        adapter = YugiohBatchAdapter(
            decks=((deck, True),),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.ygo_download") as mock_download,
            patch("src.tcg_batches.ygo_expand") as mock_expand,
            patch("src.tcg_batches.get_ygo_back") as mock_back,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = []
            mock_back.return_value = tmp_path / "back.png"
            adapter.prepare()
            filtered_deck = mock_download.call_args[0][0]
            assert len(filtered_deck.cards) == 1
            assert filtered_deck.cards[0].card_id == 1

    def test_multiple_decks_combined(self, tmp_path: Path) -> None:
        """Multiple decks are downloaded and expanded into one batch."""
        deck1 = YGODeck(name="D1", deck_id="d1", cards=[_make_ygo_card(1, "Card 1")])
        deck2 = YGODeck(name="D2", deck_id="d2", cards=[_make_ygo_card(2, "Card 2")])
        adapter = YugiohBatchAdapter(
            decks=((deck1, True), (deck2, True)),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.ygo_download") as mock_download,
            patch("src.tcg_batches.ygo_expand") as mock_expand,
            patch("src.tcg_batches.get_ygo_back") as mock_back,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = [Path("f1.png")]
            mock_back.return_value = tmp_path / "back.png"
            batch = adapter.prepare()
            assert batch.name == "yugioh_proxies"
            assert mock_download.call_count == 2
            assert mock_expand.call_count == 2


def _make_op_card(
    card_id: str,
    name: str,
    quantity: int = 1,
    is_leader: bool = False,
) -> OPCard:
    """Helper to create a One Piece card for testing."""
    return OPCard(card_id=card_id, name=name, quantity=quantity, is_leader=is_leader, colors=[])


def _make_op_deck(name: str, cards: list[OPCard], slug: str = "test-deck") -> OPDeck:
    """Helper to create a One Piece deck for testing."""
    return OPDeck(name=name, slug=slug, cards=cards)


class TestOnePieceBatchAdapter:
    """Tests for OnePieceBatchAdapter."""

    def test_empty_decks_returns_empty_batch(self, tmp_path: Path) -> None:
        """Empty deck list returns empty PrintBatch."""
        adapter = OnePieceBatchAdapter(
            decks=(),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        batch = adapter.prepare()
        assert batch.name == "One Piece"
        assert batch.fronts == []

    def test_selected_card_ids_filtering(self, tmp_path: Path) -> None:
        """Only selected cards are downloaded when selected_card_ids is set."""
        deck = _make_op_deck(
            "Test",
            [
                _make_op_card("OP01-001", "Zoro"),
                _make_op_card("OP01-002", "Nami"),
            ],
        )
        deck.selected_card_ids = {"OP01-001"}
        adapter = OnePieceBatchAdapter(
            decks=(deck,),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.op_download") as mock_download,
            patch("src.tcg_batches.op_expand") as mock_expand,
            patch("src.tcg_batches.get_op_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([], [])
            mock_backs.return_value = (tmp_path / "std.png", tmp_path / "leader.png")
            adapter.prepare()
            filtered_deck = mock_download.call_args[0][0]
            assert len(filtered_deck.cards) == 1
            assert filtered_deck.cards[0].card_id == "OP01-001"

    def test_leader_back_resolved_per_deck(self, tmp_path: Path) -> None:
        """Decks with a leader get the leader-specific back for expansion."""
        leader = _make_op_card("OP01-000", "Luffy", 1, is_leader=True)
        deck = _make_op_deck("Test", [leader, _make_op_card("OP01-001", "Zoro")])
        adapter = OnePieceBatchAdapter(
            decks=(deck,),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.op_download") as mock_download,
            patch("src.tcg_batches.op_expand") as mock_expand,
            patch("src.tcg_batches.get_op_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([], [])
            std_back = tmp_path / "std.png"
            leader_back = tmp_path / "leader.png"
            mock_backs.return_value = (std_back, leader_back)
            adapter.prepare()
            resolved_leader_back = mock_expand.call_args[0][2]
            assert resolved_leader_back == leader_back

    def test_multiple_decks_combined(self, tmp_path: Path) -> None:
        """Multiple decks are downloaded and expanded into one batch."""
        deck1 = _make_op_deck("D1", [_make_op_card("OP01-001", "Zoro")], slug="d1")
        deck2 = _make_op_deck("D2", [_make_op_card("OP01-002", "Nami")], slug="d2")
        adapter = OnePieceBatchAdapter(
            decks=(deck1, deck2),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.op_download") as mock_download,
            patch("src.tcg_batches.op_expand") as mock_expand,
            patch("src.tcg_batches.get_op_backs") as mock_backs,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([Path("f1.png")], [None])
            mock_backs.return_value = (tmp_path / "std.png", tmp_path / "leader.png")
            batch = adapter.prepare()
            assert batch.name == "One Piece"
            assert mock_download.call_count == 2
            assert mock_expand.call_count == 2


def _make_lorcana_card(card_id: str, name: str, quantity: int = 1) -> LorcanaCard:
    """Helper to create a Lorcana card for testing."""
    return LorcanaCard(
        card_id=card_id,
        name=name,
        quantity=quantity,
        image_url=f"https://example.com/{card_id}.webp",
    )


class TestLorcanaBatchAdapter:
    """Tests for LorcanaBatchAdapter."""

    def test_empty_decks_returns_empty_batch(self, tmp_path: Path) -> None:
        """Empty deck list returns empty PrintBatch."""
        adapter = LorcanaBatchAdapter(
            decks=(),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        batch = adapter.prepare()
        assert batch.name == "Lorcana"
        assert batch.fronts == []

    def test_selected_card_ids_filtering(self, tmp_path: Path) -> None:
        """Only selected cards are downloaded when selected_card_ids is set."""
        deck = LocanaDeck(
            deck_id="d1",
            name="Test",
            cards=[
                _make_lorcana_card("1", "Elsa - Snow Queen"),
                _make_lorcana_card("2", "Mickey Mouse"),
            ],
        )
        deck.selected_card_ids = {"1"}
        adapter = LorcanaBatchAdapter(
            decks=(deck,),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.lorcana_download") as mock_download,
            patch("src.tcg_batches.lorcana_expand") as mock_expand,
            patch("src.tcg_batches.get_lorcana_back") as mock_back,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([], [])
            mock_back.return_value = tmp_path / "back.png"
            adapter.prepare()
            filtered_deck = mock_download.call_args[0][0]
            assert len(filtered_deck.cards) == 1
            assert filtered_deck.cards[0].card_id == "1"

    def test_multiple_decks_combined(self, tmp_path: Path) -> None:
        """Multiple decks are downloaded and expanded into one batch."""
        deck1 = LocanaDeck(deck_id="d1", name="D1", cards=[_make_lorcana_card("1", "Elsa")])
        deck2 = LocanaDeck(deck_id="d2", name="D2", cards=[_make_lorcana_card("2", "Mickey")])
        adapter = LorcanaBatchAdapter(
            decks=(deck1, deck2),
            work_dir=tmp_path,
            cancel_event=None,
            report_progress=MagicMock(),
        )
        with (
            patch("src.tcg_batches.lorcana_download") as mock_download,
            patch("src.tcg_batches.lorcana_expand") as mock_expand,
            patch("src.tcg_batches.get_lorcana_back") as mock_back,
        ):
            mock_download.return_value = {}
            mock_expand.return_value = ([Path("f1.png")], [None])
            mock_back.return_value = tmp_path / "back.png"
            batch = adapter.prepare()
            assert batch.name == "Lorcana"
            assert mock_download.call_count == 2
            assert mock_expand.call_count == 2
