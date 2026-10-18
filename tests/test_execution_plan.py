"""Tests for src/execution_plan.py — print run planning."""

from __future__ import annotations

from pathlib import Path

from src.execution_plan import build_combined_print_run, standalone_print_batches
from src.print_batch import PrintBatch


class TestBuildCombinedPrintRun:
    """Tests for build_combined_print_run function."""

    def test_empty_batches_returns_empty_run(self) -> None:
        """Empty batch list returns empty combined run."""
        result = build_combined_print_run([])
        assert result.fronts == []
        assert result.backs == []
        assert result.crop_map == {}
        assert result.default_back is None
        assert result.base_name == "combinado"

    def test_single_batch_combined(self, tmp_path: Path) -> None:
        """Single batch is combined correctly."""
        front = tmp_path / "front1.png"
        back = tmp_path / "back1.png"
        batch = PrintBatch(
            "test",
            [front],
            [back],
            {front: False, back: False},
            back,
        )
        result = build_combined_print_run([batch])
        assert result.fronts == [front]
        assert result.backs == [back]
        assert result.default_back == back
        assert result.base_name == "test"

    def test_multiple_batches_combined(self, tmp_path: Path) -> None:
        """Multiple batches are combined in order."""
        front1 = tmp_path / "front1.png"
        front2 = tmp_path / "front2.png"
        back = tmp_path / "back.png"
        batch1 = PrintBatch("batch1", [front1], [back], {front1: False}, back)
        batch2 = PrintBatch("batch2", [front2], [back], {front2: False}, back)
        result = build_combined_print_run([batch1, batch2])
        assert result.fronts == [front1, front2]
        assert result.backs == [back, back]
        assert result.base_name == "batch1_batch2"

    def test_separate_pdf_batches_excluded(self, tmp_path: Path) -> None:
        """Batches with separate_pdf=True are excluded from combined run."""
        front1 = tmp_path / "front1.png"
        front2 = tmp_path / "front2.png"
        back = tmp_path / "back.png"
        batch1 = PrintBatch("batch1", [front1], [back], {front1: False}, back)
        batch2 = PrintBatch("batch2", [front2], [back], {front2: False}, back, separate_pdf=True)
        result = build_combined_print_run([batch1, batch2])
        assert result.fronts == [front1]
        assert result.base_name == "batch1"

    def test_default_back_from_first_active_batch(self, tmp_path: Path) -> None:
        """Default back comes from first batch with fronts."""
        front = tmp_path / "front.png"
        back1 = tmp_path / "back1.png"
        back2 = tmp_path / "back2.png"
        batch1 = PrintBatch("batch1", [], [], {}, back1)  # Empty
        batch2 = PrintBatch("batch2", [front], [back2], {front: False}, back2)
        result = build_combined_print_run([batch1, batch2])
        assert result.default_back == back2


class TestStandalonePrintBatches:
    """Tests for standalone_print_batches function."""

    def test_empty_list_returns_empty(self) -> None:
        """Empty list returns empty list."""
        assert standalone_print_batches([]) == []

    def test_filters_separate_pdf_with_fronts(self, tmp_path: Path) -> None:
        """Only batches with separate_pdf=True and fronts are returned."""
        front = tmp_path / "front.png"
        back = tmp_path / "back.png"
        batch1 = PrintBatch("batch1", [front], [back], {front: False}, back, separate_pdf=True)
        batch2 = PrintBatch("batch2", [front], [back], {front: False}, back, separate_pdf=False)
        batch3 = PrintBatch("batch3", [], [], {}, back, separate_pdf=True)  # No fronts
        result = standalone_print_batches([batch1, batch2, batch3])
        assert len(result) == 1
        assert result[0].name == "batch1"
