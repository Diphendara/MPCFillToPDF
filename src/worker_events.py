"""Typed events published by background print execution to Tkinter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event


class WorkerEvent:
    """Convert a typed worker event to the GUI's temporary compatibility tuple."""

    def as_legacy_tuple(self) -> tuple:
        raise NotImplementedError


@dataclass(frozen=True)
class ProgressEvent(WorkerEvent):
    stage: str
    done: int
    total: int
    label: str

    def as_legacy_tuple(self) -> tuple:
        return "progress", self.stage, self.done, self.total, self.label


@dataclass(frozen=True)
class FileEvent(WorkerEvent):
    current: int
    total: int
    label: str

    def as_legacy_tuple(self) -> tuple:
        return "file", self.current, self.total, self.label


@dataclass(frozen=True)
class VerificationWarningEvent(WorkerEvent):
    inaccessible: list[tuple[str, str]]
    confirmation: Event

    def as_legacy_tuple(self) -> tuple:
        return "verify_warning", self.inaccessible, self.confirmation


@dataclass(frozen=True)
class RunFinishedEvent(WorkerEvent):
    pdfs: list[Path]
    manifest: Path | None
    run_dir: Path
    timing: str

    def as_legacy_tuple(self) -> tuple:
        return "done", self.pdfs, self.manifest, self.run_dir, self.timing


def normalize_event(event: WorkerEvent | tuple) -> tuple:
    """Keep legacy tab events working while worker execution migrates to types."""
    return event.as_legacy_tuple() if isinstance(event, WorkerEvent) else event
