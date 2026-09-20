"""Domain planning for normalized print batches, independent of Tkinter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.print_batch import PrintBatch, combine_batches


@dataclass(frozen=True)
class CombinedPrintRun:
    """The standard run assembled from local and imported-card batches."""

    fronts: list[Path]
    backs: list[Path | None]
    crop_map: dict[Path, bool]
    default_back: Path | None
    base_name: str


def build_combined_print_run(batches: list[PrintBatch]) -> CombinedPrintRun:
    """Combine batches in input order and derive the default back and PDF name."""
    combined_batches = [batch for batch in batches if not batch.separate_pdf]
    fronts, backs, crop_map = combine_batches(combined_batches)
    active = [batch for batch in combined_batches if batch.fronts]
    default_back = next((batch.default_back for batch in active if batch.default_back), None)
    return CombinedPrintRun(
        fronts,
        backs,
        crop_map,
        default_back,
        "_".join(batch.name for batch in active) or "combinado",
    )


def standalone_print_batches(batches: list[PrintBatch]) -> list[PrintBatch]:
    """Return non-empty batches that own a separate PDF destination."""
    return [batch for batch in batches if batch.separate_pdf and batch.fronts]
