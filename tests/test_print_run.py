"""Tests for src/print_run.py — standalone print run execution."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from src.print_batch import PrintBatch
from src.print_run import StandalonePrintRun


class TestStandalonePrintRun:
    """Tests for StandalonePrintRun class."""

    def test_render_with_empty_fronts_returns_empty(self, tmp_path: Path) -> None:
        """Empty fronts list returns empty result."""
        batch = PrintBatch("test", [], [], {}, None)
        run = StandalonePrintRun(batch)
        result = run.render(tmp_path, tmp_path, MagicMock(), None, fronts_only=False)
        assert result == []

    def test_render_with_no_default_back_returns_empty(self, tmp_path: Path) -> None:
        """Missing default back returns empty result."""
        front = tmp_path / "front.png"
        batch = PrintBatch("test", [front], [], {front: False}, None)
        run = StandalonePrintRun(batch)
        result = run.render(tmp_path, tmp_path, MagicMock(), None, fronts_only=False)
        assert result == []

    def test_render_calls_run_print_batch(self, tmp_path: Path) -> None:
        """render() calls run_print_batch with correct args."""
        front = tmp_path / "front.png"
        back = tmp_path / "back.png"
        batch = PrintBatch("test", [front], [back], {front: False}, back)
        run = StandalonePrintRun(batch)
        mock_callback = MagicMock()
        cancel_event = Event()

        with patch("src.print_run.run_print_batch") as mock_run:
            mock_run.return_value = [tmp_path / "output.pdf"]
            result = run.render(tmp_path, tmp_path, mock_callback, cancel_event, fronts_only=True)
            mock_run.assert_called_once_with(
                batch, tmp_path, tmp_path, mock_callback, cancel_event, fronts_only=True
            )
            assert result == [tmp_path / "output.pdf"]

    def test_render_with_custom_layout(self, tmp_path: Path) -> None:
        """Custom layout is applied to batch."""
        front = tmp_path / "front.png"
        back = tmp_path / "back.png"
        batch = PrintBatch("test", [front], [back], {front: False}, back)
        custom_layout = MagicMock()
        run = StandalonePrintRun(batch, layout=custom_layout)

        with patch("src.print_run.run_print_batch") as mock_run:
            mock_run.return_value = []
            run.render(tmp_path, tmp_path, MagicMock(), None, fronts_only=False)
            # Check that a new batch was created with custom layout
            call_args = mock_run.call_args
            called_batch = call_args[0][0]
            assert called_batch.layout == custom_layout
