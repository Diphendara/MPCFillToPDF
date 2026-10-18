"""Constants and type aliases for the application."""

from collections.abc import Callable
from enum import Enum

COLS = 3
ROWS = 3
CARDS_PER_PAGE = COLS * ROWS

SUPPORTED_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"})


class Stage(str, Enum):
    """Processing stages for progress tracking."""

    VERIFY = "verify"
    DOWNLOAD = "download"
    CROP = "crop"
    PDF = "pdf"


ProgressCallback = Callable[[int, int], None] | None
StageCallback = Callable[[str, int, int], None] | None
JobPdfStartCallback = Callable[[int, int, str], None] | None
SpeedCallback = Callable[[float, float], None] | None
ImageDoneCallback = Callable[[str], None] | None


class UIConstants:
    """UI-related constants for the tkinter GUI (widget sizes, padding, etc.)."""

    SPINBOX_WIDTH = 4
    BUTTON_WIDTH = 10
    LABEL_WIDTH = 25
    ENTRY_WIDTH = 40
    COMBOBOX_WIDTH = 20
    ICON_SIZE = 16
    PAD_SMALL = 2
    PAD_MEDIUM = 4
    PAD_LARGE = 8
