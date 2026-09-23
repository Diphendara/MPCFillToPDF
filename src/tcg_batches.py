"""Adapters that turn imported TCG decks into normalized printable batches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from typing import Protocol

from src.deck_importer import DeckCard
from src.lorcana_scraper import LocanaDeck, get_lorcana_back
from src.lorcana_scraper import download_images as lorcana_download
from src.lorcana_scraper import expand_deck as lorcana_expand
from src.op_scraper import OPDeck, get_op_backs
from src.op_scraper import download_images as op_download
from src.op_scraper import expand_deck as op_expand
from src.pdf_generator import YUGIOH_LAYOUT
from src.print_batch import PrintBatch
from src.rb_scraper import RBDeck, get_rb_backs
from src.rb_scraper import download_images as rb_download
from src.rb_scraper import expand_deck as rb_expand
from src.scryfall import download_deck_images as scryfall_download
from src.ygo_scraper import YGODeck, get_ygo_back
from src.ygo_scraper import download_images as ygo_download
from src.ygo_scraper import expand_deck as ygo_expand

ProgressReporter = Callable[[str, int, int, str], None]


class MtgDeck(Protocol):
    """GUI-selected Magic deck interface consumed by the Magic adapter."""

    cards: list[DeckCard]
    back_path: Path | None

    def includes(self, card: DeckCard) -> bool: ...


class TcgBatchAdapter(Protocol):
    """Adapter interface for a TCG that can join the standard print run."""

    def prepare(self) -> PrintBatch: ...


@dataclass(frozen=True)
class YugiohBatchAdapter:
    """Normalize Yu-Gi-Oh! decks while preserving their separate print run."""

    decks: tuple[tuple[YGODeck, bool], ...]
    work_dir: Path
    cancel_event: Event | None
    report_progress: ProgressReporter

    def prepare(self) -> PrintBatch:
        if not self.decks:
            return PrintBatch("yugioh_proxies")
        total = sum(len({card.card_id for card in deck.cards}) for deck, _ in self.decks)
        self.report_progress("download", 0, total, "Yu-Gi-Oh!")
        fronts: list[Path] = []
        downloaded = 0
        for deck, include_side in self.decks:
            selected = getattr(deck, "selected_card_ids", None)
            if selected is not None:
                deck = replace(
                    deck, cards=[card for card in deck.cards if card.card_id in selected]
                )
            offset = downloaded

            def _progress(done: int, _total: int, *, _offset=offset) -> None:
                self.report_progress("download", _offset + done, total, "Yu-Gi-Oh!")

            image_map = ygo_download(
                deck,
                self.work_dir / "ygo_raw",
                cancel_event=self.cancel_event,
                progress_cb=_progress,
            )
            fronts.extend(ygo_expand(deck, image_map, include_side))
            downloaded += len({card.card_id for card in deck.cards})
        back = get_ygo_back()
        return PrintBatch(
            "yugioh_proxies",
            fronts,
            [back] * len(fronts),
            {path: False for path in {*fronts, back}},
            back,
            YUGIOH_LAYOUT,
            True,
        )


@dataclass(frozen=True)
class OnePieceBatchAdapter:
    decks: tuple[OPDeck, ...]
    work_dir: Path
    cancel_event: Event | None
    report_progress: ProgressReporter

    def prepare(self) -> PrintBatch:
        if not self.decks:
            return PrintBatch("One Piece")
        label = " + ".join(deck.name for deck in self.decks)
        total = sum(len({card.card_id for card in deck.cards}) for deck in self.decks)
        self.report_progress("download", 0, total, f"One Piece – {label}")
        image_map: dict[str, Path] = {}
        downloaded = 0
        for deck in self.decks:
            selected = getattr(deck, "selected_card_ids", None)
            if selected is not None:
                deck = replace(
                    deck, cards=[card for card in deck.cards if card.card_id in selected]
                )
            offset = downloaded

            def _progress(done: int, _total: int, *, _offset=offset) -> None:
                self.report_progress("download", _offset + done, total, f"One Piece – {label}")

            image_map.update(
                op_download(
                    deck,
                    self.work_dir / "op_raw",
                    cancel_event=self.cancel_event,
                    progress_cb=_progress,
                )
            )
            downloaded += len({card.card_id for card in deck.cards})
        standard_back, leader_back = get_op_backs()
        leader_backs = {
            deck.leader.card_id: leader_back for deck in self.decks if deck.leader is not None
        }
        fronts: list[Path] = []
        backs: list[Path | None] = []
        for deck in self.decks:
            leader = deck.leader
            resolved_leader_back = leader_backs.get(leader.card_id) if leader else None
            deck_fronts, deck_backs = op_expand(
                deck, image_map, resolved_leader_back, standard_back
            )
            fronts.extend(deck_fronts)
            backs.extend(standard_back if back is None else back for back in deck_backs)
        crop_map = {path: False for path in set(fronts) | {standard_back, *leader_backs.values()}}
        return PrintBatch("One Piece", fronts, backs, crop_map, standard_back)


@dataclass(frozen=True)
class RiftboundBatchAdapter:
    decks: tuple[tuple[RBDeck, bool], ...]
    work_dir: Path
    cancel_event: Event | None
    report_progress: ProgressReporter

    def prepare(self) -> PrintBatch:
        if not self.decks:
            return PrintBatch("Riftbound")
        label = " + ".join(deck.name for deck, _ in self.decks)
        total = sum(len({card.variant_id for card in deck.cards}) for deck, _ in self.decks)
        self.report_progress("download", 0, total, f"Riftbound – {label}")
        image_map: dict[str, Path] = {}
        downloaded = 0
        for deck, _ in self.decks:
            selected = getattr(deck, "selected_card_ids", None)
            if selected is not None:
                deck = replace(
                    deck, cards=[card for card in deck.cards if card.variant_id in selected]
                )
            offset = downloaded

            def _progress(done: int, _total: int, *, _offset=offset) -> None:
                self.report_progress("download", _offset + done, total, f"Riftbound – {label}")

            image_map.update(
                rb_download(
                    deck,
                    self.work_dir / "rb_raw",
                    cancel_event=self.cancel_event,
                    progress_cb=_progress,
                )
            )
            downloaded += len({card.variant_id for card in deck.cards})
        back_by_section = get_rb_backs()
        default_back = back_by_section.get("maindeck") or next(iter(back_by_section.values()))
        fronts: list[Path] = []
        backs: list[Path | None] = []
        for deck, include_runes in self.decks:
            deck_fronts, deck_backs = rb_expand(
                deck, image_map, back_by_section, include_runes=include_runes
            )
            fronts.extend(deck_fronts)
            backs.extend(default_back if back is None else back for back in deck_backs)
        crop_map = {path: False for path in set(fronts) | set(back_by_section.values())}
        return PrintBatch("Riftbound", fronts, backs, crop_map, default_back)


@dataclass(frozen=True)
class LorcanaBatchAdapter:
    decks: tuple[LocanaDeck, ...]
    work_dir: Path
    cancel_event: Event | None
    report_progress: ProgressReporter

    def prepare(self) -> PrintBatch:
        if not self.decks:
            return PrintBatch("Lorcana")
        label = " + ".join(deck.name for deck in self.decks)
        total = sum(len({card.card_id for card in deck.cards}) for deck in self.decks)
        self.report_progress("download", 0, total, f"Lorcana – {label}")
        image_map: dict[str, Path] = {}
        downloaded = 0
        for deck in self.decks:
            selected = getattr(deck, "selected_card_ids", None)
            if selected is not None:
                deck = replace(
                    deck, cards=[card for card in deck.cards if card.card_id in selected]
                )
            offset = downloaded

            def _progress(done: int, _total: int, *, _offset=offset) -> None:
                self.report_progress("download", _offset + done, total, f"Lorcana – {label}")

            image_map.update(
                lorcana_download(
                    deck,
                    self.work_dir / "lorcana_raw",
                    cancel_event=self.cancel_event,
                    progress_cb=_progress,
                )
            )
            downloaded += len({card.card_id for card in deck.cards})
        default_back = get_lorcana_back()
        fronts: list[Path] = []
        backs: list[Path | None] = []
        for deck in self.decks:
            deck_fronts, deck_backs = lorcana_expand(deck, image_map)
            fronts.extend(deck_fronts)
            backs.extend(default_back if back is None else back for back in deck_backs)
        crop_map = {path: False for path in set(fronts) | {default_back}}
        return PrintBatch("Lorcana", fronts, backs, crop_map, default_back)


@dataclass(frozen=True)
class MagicBatchAdapter:
    decks: tuple[MtgDeck, ...]
    work_dir: Path
    default_back: Path
    local_backs: tuple[Path, ...]
    cancel_event: Event | None
    report_progress: ProgressReporter

    def prepare(self) -> PrintBatch:
        if not self.decks:
            return PrintBatch("magic_url")
        cards_with_deck: list[tuple[DeckCard, MtgDeck]] = []
        for deck in self.decks:
            cards_with_deck.extend(
                sorted(
                    ((card, deck) for card in deck.cards if deck.includes(card)),
                    key=lambda item: item[0].name.casefold(),
                )
            )
        cards = [card for card, _ in cards_with_deck]
        label = f"Magic – {len(self.decks)} mazo(s)"
        self.report_progress("download", 0, len(cards), label)

        def _progress(done: int, total: int) -> None:
            self.report_progress("download", done, total, label)

        results = scryfall_download(
            cards, self.work_dir / "scryfall", _progress, cancel_event=self.cancel_event
        )
        local_backs = set(self.local_backs)
        fronts: list[Path] = []
        backs: list[Path | None] = []
        all_backs = {self.default_back}
        for (card, front, downloaded_back), (_, deck) in zip(results, cards_with_deck):
            resolved_back = downloaded_back or (
                deck.back_path if deck.back_path in local_backs else self.default_back
            )
            all_backs.add(resolved_back)
            fronts.extend([front] * card.quantity)
            backs.extend([resolved_back] * card.quantity)
        crop_map = {path: False for path in set(fronts) | all_backs if path not in local_backs}
        return PrintBatch("magic_url", fronts, backs, crop_map, self.default_back)
