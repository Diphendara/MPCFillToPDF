"""Execution models for printable batches that need their own PDF run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event

from src.pdf_generator import CardLayout
from src.pipeline import run_print_batch
from src.print_batch import PrintBatch


@dataclass(frozen=True)
class StandalonePrintRun:
    """A normalized batch rendered separately from the standard combined run."""

    batch: PrintBatch
    layout: CardLayout | None = None

    def render(
        self,
        output_dir: Path,
        work_dir: Path,
        progress_callback,
        cancel_event: Event | None,
        *,
        fronts_only: bool,
        **pdf_options,
    ) -> list[Path]:
        if not self.batch.fronts or self.batch.default_back is None:
            return []
        if self.layout is not None:
            batch = PrintBatch(
                self.batch.name,
                self.batch.fronts,
                self.batch.backs,
                self.batch.crop_map,
                self.batch.default_back,
                self.layout,
                self.batch.separate_pdf,
            )
        else:
            batch = self.batch
        return run_print_batch(
            batch,
            output_dir,
            work_dir,
            progress_callback,
            cancel_event,
            fronts_only=fronts_only,
            **pdf_options,
        )
