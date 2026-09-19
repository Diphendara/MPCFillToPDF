from pathlib import Path

import pytest
from PIL import Image

from src.execution_plan import build_combined_print_run, standalone_print_batches
from src.pdf_generator import YUGIOH_LAYOUT
from src.print_batch import PrintBatch, combine_batches
from src.print_run import StandalonePrintRun


def test_combine_batches_preserves_front_back_pairing():
    front_a, front_b = Path("a.jpg"), Path("b.jpg")
    back_a, back_b = Path("ra.jpg"), Path("rb.jpg")

    fronts, backs, crop_map = combine_batches(
        [
            PrintBatch("first", [front_a], [back_a], {front_a: False}),
            PrintBatch("second", [front_b], [back_b], {front_b: True}),
        ]
    )

    assert fronts == [front_a, front_b]
    assert backs == [back_a, back_b]
    assert crop_map == {front_a: False, front_b: True}


def test_combine_batches_rejects_misaligned_pairs():
    with pytest.raises(ValueError, match="emparejado"):
        combine_batches([PrintBatch("invalid", [Path("a.jpg")], [])])


def test_build_combined_print_run_uses_first_available_default_back():
    local = PrintBatch("locales", [Path("local.jpg")], [None], {})
    imported = PrintBatch("importado", [Path("card.jpg")], [Path("back.jpg")], {}, Path("back.jpg"))

    run = build_combined_print_run([local, imported])

    assert run.fronts == [Path("local.jpg"), Path("card.jpg")]
    assert run.backs == [None, Path("back.jpg")]
    assert run.default_back == Path("back.jpg")
    assert run.base_name == "locales_importado"


def test_separate_batch_is_not_combined_with_standard_run():
    standard = PrintBatch("locales", [Path("local.jpg")], [Path("back.jpg")])
    separate = PrintBatch("yugioh", [Path("ygo.jpg")], [Path("ygo_back.jpg")], separate_pdf=True)

    combined = build_combined_print_run([standard, separate])

    assert combined.fronts == [Path("local.jpg")]
    assert standalone_print_batches([standard, separate]) == [separate]


def test_yugioh_standalone_batch_generates_its_own_pdf_with_real_images(tmp_path):
    front = tmp_path / "front.jpg"
    back = tmp_path / "back.jpg"
    Image.new("RGB", (590, 860), "navy").save(front)
    Image.new("RGB", (3012, 4210), "brown").save(back)
    batch = PrintBatch(
        "yugioh_proxies",
        [front],
        [back],
        {front: False, back: False},
        back,
        YUGIOH_LAYOUT,
        True,
    )

    outputs = StandalonePrintRun(batch).render(
        tmp_path / "out", tmp_path / "work", None, None, fronts_only=False
    )

    assert len(outputs) == 1
    assert outputs[0].read_bytes().startswith(b"%PDF")
