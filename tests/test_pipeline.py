"""Tests for src/pipeline.py — end-to-end orchestration.

Downloads are always mocked; crop and PDF generation use real (tiny) images
so the full pipeline chain is exercised without network access.
"""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from src.cancellation import Cancelled
from src.deck_importer import DeckCard, FetchedDeck
from src.downloader import DownloadPermissionError
from src.parser import parse
from src.pipeline import (
    _build_crop_tasks,
    _build_slot_maps,
    _local_synthetic_id,
    run,
    run_deck_url,
    run_locals_only,
    run_merged,
    run_plan,
)
from src.precheck import analyze
from src.precheck import plan as make_plan
from src.scryfall import ScryfallError
from tests.conftest import make_rgb_image, make_xml

# ─── helpers ────────────────────────────────────────────────────────────────

W, H = 200, 280  # image dimensions chosen to survive MPC bleed crop


def _img(path: Path, color=(180, 80, 40)) -> Path:
    return make_rgb_image(path, W, H, color)


def _one_card_xml(tmp_path: Path, name: str = "deck") -> Path:
    return make_xml(
        tmp_path / f"{name}.xml",
        fronts=[{"id": "FRONT01", "name": "Test Card", "slots": "0"}],
        cardback_id="BACK01",
    )


def _fake_download_all(raw_dir: Path, img_color=(180, 80, 40)):
    """Return a monkeypatch replacement for download_all that writes tiny JPEGs."""

    def _impl(
        pairs,
        dest_dir,
        progress_callback=None,
        cancel_event=None,
        on_image_done=None,
        on_speed_update=None,
    ):
        result = {}
        for did, name in pairs:
            p = dest_dir / f"{did}.jpg"
            p.parent.mkdir(parents=True, exist_ok=True)
            _img(p, img_color)
            result[did] = p
        total = len(pairs)
        for i, (did, _) in enumerate(pairs, 1):
            if on_image_done:
                on_image_done(did)
            if progress_callback:
                progress_callback(i, total)
        return result

    return _impl


# ─── initial progress events (bug-fix regression) ───────────────────────────


def test_run_plan_fires_download_zero_event_before_downloads(tmp_path):
    """progress_callback("download", 0, N) must be the FIRST download event."""
    xml = _one_card_xml(tmp_path)
    reports = analyze([xml])
    p = make_plan(reports)

    events = []

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        run_plan(
            p.jobs,
            tmp_path / "out",
            tmp_path / "work",
            progress_callback=lambda s, d, t: events.append((s, d, t)),
        )

    dl_events = [(s, d, t) for s, d, t in events if s == "download"]
    assert dl_events, "No download events recorded"
    assert dl_events[0][1] == 0, "First download event must have done=0"


def test_run_plan_fires_crop_zero_event_before_crops(tmp_path):
    """progress_callback("crop", 0, N) must be the FIRST crop event."""
    xml = _one_card_xml(tmp_path)
    reports = analyze([xml])
    p = make_plan(reports)

    events = []

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        run_plan(
            p.jobs,
            tmp_path / "out",
            tmp_path / "work",
            progress_callback=lambda s, d, t: events.append((s, d, t)),
        )

    crop_events = [(s, d, t) for s, d, t in events if s == "crop"]
    assert crop_events, "No crop events recorded"
    assert crop_events[0][1] == 0, "First crop event must have done=0"


def test_run_plan_download_zero_total_matches_image_count(tmp_path):
    """The total in the first download event must equal the number of unique Drive IDs."""
    xml = _one_card_xml(tmp_path)  # 2 IDs: FRONT01 + BACK01
    reports = analyze([xml])
    p = make_plan(reports)

    events = []

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        run_plan(
            p.jobs,
            tmp_path / "out",
            tmp_path / "work",
            progress_callback=lambda s, d, t: events.append((s, d, t)),
        )

    first_dl = next(e for e in events if e[0] == "download")
    assert first_dl == ("download", 0, 2)  # FRONT01 + BACK01


# ─── run_plan — basic correctness ────────────────────────────────────────────


def test_run_plan_produces_pdf(tmp_path):
    xml = _one_card_xml(tmp_path)
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        results = run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    assert len(results) == 1
    assert results[0].exists()
    assert results[0].stat().st_size > 0


def test_run_plan_produces_one_pdf_per_job(tmp_path):
    xml1 = make_xml(
        tmp_path / "a.xml",
        fronts=[{"id": f"FA{i}", "name": f"A{i}", "slots": str(i)} for i in range(9)],
        cardback_id="CBA",
    )
    xml2 = make_xml(
        tmp_path / "b.xml",
        fronts=[{"id": f"FB{i}", "name": f"B{i}", "slots": str(i)} for i in range(9)],
        cardback_id="CBB",
    )
    reports = analyze([xml1, xml2])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        results = run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    assert len(results) == 2


def test_run_plan_fronts_only(tmp_path):
    xml = _one_card_xml(tmp_path)
    reports = analyze([xml])
    p = make_plan(reports)

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        r_both = run_plan(p.jobs, tmp_path / "out_both", tmp_path / "work_both", fronts_only=False)
        r_fronts = run_plan(p.jobs, tmp_path / "out_f", tmp_path / "work_f", fronts_only=True)

    assert r_fronts[0].stat().st_size < r_both[0].stat().st_size


# ─── run_plan — cancellation ─────────────────────────────────────────────────


def test_run_plan_cancel_before_download_raises(tmp_path):
    xml = _one_card_xml(tmp_path)
    reports = analyze([xml])
    p = make_plan(reports)
    event = threading.Event()
    event.set()

    with pytest.raises(Cancelled):
        run_plan(p.jobs, tmp_path / "out", tmp_path / "work", cancel_event=event)


# ─── run_plan — error propagation ────────────────────────────────────────────


def test_run_plan_propagates_permission_error(tmp_path):
    xml = _one_card_xml(tmp_path)
    reports = analyze([xml])
    p = make_plan(reports)

    def _raise_perm(*a, **kw):
        raise DownloadPermissionError("FRONT01", "Test Card")

    with patch("src.pipeline.download_all", side_effect=_raise_perm):
        with pytest.raises(DownloadPermissionError) as exc_info:
            run_plan(p.jobs, tmp_path / "out", tmp_path / "work")

    # context (xml_name, position) should be attached
    assert exc_info.value.xml_name != "" or exc_info.value.position >= 0


# ─── run_plan — extra local fronts ───────────────────────────────────────────


def test_run_plan_with_extra_local_fronts(tmp_path):
    xml = _one_card_xml(tmp_path)
    reports = analyze([xml])
    p = make_plan(reports, local_count=1)

    local_front = _img(tmp_path / "local_front.jpg")

    with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
        results = run_plan(
            p.jobs,
            tmp_path / "out",
            tmp_path / "work",
            extra_fronts=[local_front],
        )

    assert len(results) == 1
    assert results[0].exists()


# ─── run_locals_only ─────────────────────────────────────────────────────────


def test_run_locals_only_produces_pdf(tmp_path):
    front = _img(tmp_path / "front.jpg")
    cardback = _img(tmp_path / "back.jpg", color=(40, 80, 180))

    results = run_locals_only(
        extra_fronts=[front],
        local_cardback=cardback,
        output_dir=tmp_path / "out",
        base_name="locals",
        work_dir=tmp_path / "work",
    )

    assert len(results) == 1
    assert results[0].exists()
    assert results[0].stat().st_size > 0


def test_run_locals_only_fronts_only(tmp_path):
    front = _img(tmp_path / "front.jpg")
    cardback = _img(tmp_path / "back.jpg", color=(40, 80, 180))

    r_both = run_locals_only(
        [front],
        cardback,
        tmp_path / "out_both",
        "locals",
        tmp_path / "work_both",
        fronts_only=False,
    )
    r_fronts = run_locals_only(
        [front],
        cardback,
        tmp_path / "out_f",
        "locals",
        tmp_path / "work_f",
        fronts_only=True,
    )

    assert r_fronts[0].stat().st_size < r_both[0].stat().st_size


def test_run_locals_only_requires_at_least_one_front(tmp_path):
    cardback = _img(tmp_path / "back.jpg")
    with pytest.raises(ValueError, match="front"):
        run_locals_only([], cardback, tmp_path / "out", "locals", tmp_path / "work")


def test_run_locals_only_with_explicit_backs(tmp_path):
    front1 = _img(tmp_path / "f1.jpg")
    front2 = _img(tmp_path / "f2.jpg")
    back1 = _img(tmp_path / "b1.jpg", color=(60, 60, 200))
    cardback = _img(tmp_path / "cb.jpg", color=(200, 60, 60))

    results = run_locals_only(
        extra_fronts=[front1, front2],
        local_cardback=cardback,
        output_dir=tmp_path / "out",
        base_name="locals",
        work_dir=tmp_path / "work",
        extra_backs=[back1, None],  # front2 falls back to cardback
    )

    assert len(results) >= 1
    assert results[0].exists()


# ─── _local_synthetic_id ─────────────────────────────────────────────────────


def test_local_synthetic_id_stable(tmp_path):
    p = tmp_path / "image.jpg"
    p.write_bytes(b"x")
    assert _local_synthetic_id(p) == _local_synthetic_id(p)


def test_local_synthetic_id_different_files(tmp_path):
    p1 = tmp_path / "a.jpg"
    p2 = tmp_path / "b.jpg"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    assert _local_synthetic_id(p1) != _local_synthetic_id(p2)


def test_local_synthetic_id_starts_with_local(tmp_path):
    p = tmp_path / "image.jpg"
    p.write_bytes(b"x")
    assert _local_synthetic_id(p).startswith("local_")


# ─── _build_slot_maps ────────────────────────────────────────────────────────


class TestBuildSlotMaps:
    def test_single_xml_assigns_slots_from_zero(self, tmp_path):
        xml = make_xml(
            tmp_path / "deck.xml",
            fronts=[
                {"id": "F001", "name": "Card1", "slots": "0"},
                {"id": "F002", "name": "Card2", "slots": "1"},
            ],
            cardback_id="CB001",
            quantity=2,
        )
        order = parse(xml)
        front_map, back_map, id_name, _, _, next_slot = _build_slot_maps([xml], [order], 0)
        assert next_slot == 2
        assert front_map[0] == "F001"
        assert front_map[1] == "F002"
        assert back_map[0] == "CB001"
        assert back_map[1] == "CB001"

    def test_two_xmls_get_consecutive_slots(self, tmp_path):
        xml1 = make_xml(
            tmp_path / "a.xml",
            fronts=[{"id": "F001", "name": "A", "slots": "0"}],
            cardback_id="CB001",
            quantity=1,
        )
        xml2 = make_xml(
            tmp_path / "b.xml",
            fronts=[{"id": "F002", "name": "B", "slots": "0"}],
            cardback_id="CB002",
            quantity=1,
        )
        front_map, back_map, _, _, _, next_slot = _build_slot_maps(
            [xml1, xml2], [parse(xml1), parse(xml2)], 0
        )
        assert next_slot == 2
        assert front_map[0] == "F001"
        assert front_map[1] == "F002"
        assert back_map[0] == "CB001"
        assert back_map[1] == "CB002"

    def test_respects_starting_next_slot(self, tmp_path):
        xml = make_xml(
            tmp_path / "deck.xml",
            fronts=[{"id": "F001", "name": "A", "slots": "0"}],
            cardback_id="CB001",
            quantity=1,
        )
        front_map, _, _, _, _, next_slot = _build_slot_maps([xml], [parse(xml)], 5)
        assert 5 in front_map
        assert front_map[5] == "F001"
        assert next_slot == 6

    def test_id_name_map_includes_all_ids(self, tmp_path):
        xml = make_xml(
            tmp_path / "deck.xml",
            fronts=[{"id": "F001", "name": "TestCard", "slots": "0"}],
            cardback_id="CB001",
            quantity=1,
        )
        _, _, id_name, _, _, _ = _build_slot_maps([xml], [parse(xml)], 0)
        assert "F001" in id_name
        assert "CB001" in id_name

    def test_empty_xml_list_returns_empty_maps(self):
        front_map, back_map, _, _, _, next_slot = _build_slot_maps([], [], 0)
        assert front_map == {}
        assert back_map == {}
        assert next_slot == 0


# ─── run / run_merged ────────────────────────────────────────────────────────


class TestRun:
    def test_produces_pdf_for_single_xml(self, tmp_path):
        xml = _one_card_xml(tmp_path)
        with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
            results = run(xml, tmp_path / "out", tmp_path / "work")
        assert len(results) == 1
        assert results[0].exists()
        assert results[0].suffix == ".pdf"

    def test_output_named_after_xml_stem(self, tmp_path):
        xml = make_xml(
            tmp_path / "my_cards.xml",
            fronts=[{"id": "F1", "name": "C", "slots": "0"}],
            cardback_id="CB",
            quantity=1,
        )
        with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
            results = run(xml, tmp_path / "out", tmp_path / "work")
        assert "my_cards" in results[0].stem


class TestRunMerged:
    def test_merged_combines_slots_from_two_xmls(self, tmp_path):
        xml1 = make_xml(
            tmp_path / "deck1.xml",
            fronts=[{"id": f"F1_{i}", "name": f"A{i}", "slots": str(i)} for i in range(9)],
            cardback_id="CB1",
        )
        xml2 = make_xml(
            tmp_path / "deck2.xml",
            fronts=[{"id": f"F2_{i}", "name": f"B{i}", "slots": str(i)} for i in range(9)],
            cardback_id="CB2",
        )
        with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
            results = run_merged(
                [xml1, xml2],
                tmp_path / "out",
                "merged",
                tmp_path / "work",
            )
        assert len(results) == 1
        assert results[0].exists()
        assert "merged" in results[0].stem

    def test_merged_pdf_is_larger_than_single(self, tmp_path):
        xml1 = make_xml(
            tmp_path / "a.xml",
            fronts=[{"id": "F1", "name": "A", "slots": "0"}],
            cardback_id="CB1",
            quantity=1,
        )
        xml2 = make_xml(
            tmp_path / "b.xml",
            fronts=[{"id": "F2", "name": "B", "slots": "0"}],
            cardback_id="CB2",
            quantity=1,
        )
        with patch("src.pipeline.download_all", side_effect=_fake_download_all(tmp_path / "raw")):
            single = run(xml1, tmp_path / "out_s", tmp_path / "work_s")
            merged = run_merged([xml1, xml2], tmp_path / "out_m", "merged", tmp_path / "work_m")
        assert merged[0].stat().st_size > single[0].stat().st_size


# ─── _build_crop_tasks ───────────────────────────────────────────────────────


class TestBuildCropTasks:
    def test_remote_id_crop_true(self, tmp_path):
        raw = tmp_path / "ABC123.jpg"
        raw.touch()
        tasks = _build_crop_tasks({"ABC123": raw}, tmp_path / "bled", {}, {})
        assert len(tasks) == 1
        did, _, bled_p, crop = tasks[0]
        assert did == "ABC123"
        assert crop is True
        assert bled_p.name == "ABC123.jpg"

    def test_local_id_with_crop_true(self, tmp_path):
        local = tmp_path / "local.jpg"
        local.touch()
        lid = "local_abc"
        tasks = _build_crop_tasks({lid: local}, tmp_path / "bled", {lid: local}, {local: True})
        _, _, bled_p, crop = tasks[0]
        assert crop is True
        assert "_nocrop" not in bled_p.name

    def test_local_id_with_crop_false(self, tmp_path):
        local = tmp_path / "local.jpg"
        local.touch()
        lid = "local_abc"
        tasks = _build_crop_tasks({lid: local}, tmp_path / "bled", {lid: local}, {local: False})
        _, _, bled_p, crop = tasks[0]
        assert crop is False
        assert "_nocrop" in bled_p.name

    def test_local_id_missing_from_crop_map_defaults_to_no_crop(self, tmp_path):
        local = tmp_path / "local.jpg"
        local.touch()
        lid = "local_abc"
        tasks = _build_crop_tasks({lid: local}, tmp_path / "bled", {lid: local}, {})
        _, _, bled_p, crop = tasks[0]
        assert crop is False
        assert "_nocrop" in bled_p.name

    def test_empty_input_returns_empty(self):
        tasks = _build_crop_tasks({}, Path("bled"), {}, {})
        assert tasks == []

    def test_bled_path_placed_in_bled_dir(self, tmp_path):
        raw = tmp_path / "X.jpg"
        raw.touch()
        bled_dir = tmp_path / "bled"
        tasks = _build_crop_tasks({"X": raw}, bled_dir, {}, {})
        _, _, bled_p, _ = tasks[0]
        assert bled_p.parent == bled_dir


# ─── run_deck_url ────────────────────────────────────────────────────────────


class TestRunDeckUrl:
    def _make_resources(self, tmp_path: Path) -> Path:
        res = tmp_path / "resources"
        mtg_back = res / "backs" / "mtg" / "back.jpg"
        mtg_back.parent.mkdir(parents=True, exist_ok=True)
        make_rgb_image(mtg_back)
        return res

    def _simple_deck(self) -> FetchedDeck:
        return FetchedDeck(
            name="Test Deck",
            cards=[DeckCard("Lightning Bolt", "lea", "1", 2, "main")],
        )

    def test_produces_pdf(self, tmp_path):
        res = self._make_resources(tmp_path)
        front = make_rgb_image(tmp_path / "front.jpg")
        deck = self._simple_deck()
        dl_result = [(deck.cards[0], front, None)]

        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.download_deck_images", return_value=dl_result),
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            results = run_deck_url(
                "https://moxfield.com/decks/abc",
                tmp_path / "out",
                tmp_path / "work",
                "test_deck",
            )
        assert len(results) == 1
        assert results[0].exists()
        assert results[0].stat().st_size > 0

    def test_sideboard_excluded_by_default(self, tmp_path):
        res = self._make_resources(tmp_path)
        front = make_rgb_image(tmp_path / "front.jpg")
        deck = FetchedDeck(
            name="Test",
            cards=[
                DeckCard("Main Card", "lea", "1", 1, "main"),
                DeckCard("Side Card", "lea", "2", 2, "side"),
            ],
        )
        dl_result = [(deck.cards[0], front, None)]

        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.download_deck_images", return_value=dl_result) as mock_dl,
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            run_deck_url("https://moxfield.com/decks/abc", tmp_path / "out", tmp_path / "work", "t")
        passed = mock_dl.call_args[0][0]
        assert all(c.zone == "main" for c in passed)

    def test_sideboard_included_when_flag_set(self, tmp_path):
        res = self._make_resources(tmp_path)
        front1 = make_rgb_image(tmp_path / "f1.jpg")
        front2 = make_rgb_image(tmp_path / "f2.jpg")
        deck = FetchedDeck(
            name="Test",
            cards=[
                DeckCard("Main Card", "lea", "1", 1, "main"),
                DeckCard("Side Card", "lea", "2", 1, "side"),
            ],
        )
        dl_result = [(deck.cards[0], front1, None), (deck.cards[1], front2, None)]

        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.download_deck_images", return_value=dl_result) as mock_dl,
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            run_deck_url(
                "https://moxfield.com/decks/abc",
                tmp_path / "out",
                tmp_path / "work",
                "t",
                include_sideboard=True,
            )
        passed = mock_dl.call_args[0][0]
        assert len(passed) == 2

    def test_empty_deck_after_filter_raises(self, tmp_path):
        res = self._make_resources(tmp_path)
        deck = FetchedDeck(
            name="Test",
            cards=[DeckCard("Side Card", "lea", "2", 1, "side")],
        )
        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            with pytest.raises(ValueError, match="cartas"):
                run_deck_url(
                    "https://moxfield.com/decks/abc", tmp_path / "out", tmp_path / "work", "t"
                )

    def test_scryfall_error_converts_to_value_error(self, tmp_path):
        res = self._make_resources(tmp_path)
        deck = self._simple_deck()
        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.download_deck_images", side_effect=ScryfallError("rate limit")),
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            with pytest.raises(ValueError, match="Scryfall"):
                run_deck_url(
                    "https://moxfield.com/decks/abc", tmp_path / "out", tmp_path / "work", "t"
                )

    def test_cancellation_after_download_raises(self, tmp_path):
        res = self._make_resources(tmp_path)
        front = make_rgb_image(tmp_path / "front.jpg")
        deck = self._simple_deck()
        cancel = threading.Event()
        cancel.set()
        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.download_deck_images", return_value=[(deck.cards[0], front, None)]),
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            with pytest.raises(Cancelled):
                run_deck_url(
                    "https://moxfield.com/decks/abc",
                    tmp_path / "out",
                    tmp_path / "work",
                    "t",
                    cancel_event=cancel,
                )

    def test_mdfc_back_path_used(self, tmp_path):
        res = self._make_resources(tmp_path)
        front = make_rgb_image(tmp_path / "front.jpg")
        back_face = make_rgb_image(tmp_path / "back_face.jpg", color=(80, 180, 80))
        deck = FetchedDeck(
            name="Test",
            cards=[DeckCard("Delver of Secrets", "isd", "51", 1, "main")],
        )
        dl_result = [(deck.cards[0], front, back_face)]
        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.download_deck_images", return_value=dl_result),
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            results = run_deck_url(
                "https://moxfield.com/decks/abc", tmp_path / "out", tmp_path / "work", "t"
            )
        assert results[0].exists()

    def test_progress_callback_fires_download_zero_first(self, tmp_path):
        res = self._make_resources(tmp_path)
        front = make_rgb_image(tmp_path / "front.jpg")
        deck = self._simple_deck()
        events = []
        with (
            patch("src.pipeline.fetch_deck", return_value=deck),
            patch("src.pipeline.download_deck_images", return_value=[(deck.cards[0], front, None)]),
            patch("src.pipeline.resources_dir", return_value=res),
        ):
            run_deck_url(
                "https://moxfield.com/decks/abc",
                tmp_path / "out",
                tmp_path / "work",
                "t",
                progress_callback=lambda s, d, t: events.append((s, d, t)),
            )
        dl_events = [(s, d, t) for s, d, t in events if s == "download"]
        assert dl_events, "No download events fired"
        assert dl_events[0][1] == 0
