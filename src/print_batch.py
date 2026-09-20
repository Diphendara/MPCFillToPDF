"""Normalized printable-card inputs produced by local and web adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pdf_generator import CardLayout


@dataclass
class PrintBatch:
    """Parallel printable cards plus their complete print-destination policy."""

    name: str
    fronts: list[Path] = field(default_factory=list)
    backs: list[Path | None] = field(default_factory=list)
    crop_map: dict[Path, bool] = field(default_factory=dict)
    default_back: Path | None = None
    layout: CardLayout | None = None
    separate_pdf: bool = False

    def extend_into(
        self, fronts: list[Path], backs: list[Path | None], crop_map: dict[Path, bool]
    ) -> None:
        """Append this batch while keeping the parallel front/back interface aligned."""
        fronts.extend(self.fronts)
        backs.extend(self.backs)
        crop_map.update(self.crop_map)


def combine_batches(
    batches: list[PrintBatch],
) -> tuple[list[Path], list[Path | None], dict[Path, bool]]:
    """Combine batches in caller order, preserving front/back index pairing."""
    fronts: list[Path] = []
    backs: list[Path | None] = []
    crop_map: dict[Path, bool] = {}
    for batch in batches:
        batch.extend_into(fronts, backs, crop_map)
    if len(fronts) != len(backs):
        raise ValueError("Cada frontal debe conservar un reverso emparejado.")
    return fronts, backs, crop_map
