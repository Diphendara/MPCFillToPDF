from enum import Enum

COLS = 3
ROWS = 3
CARDS_PER_PAGE = COLS * ROWS

SUPPORTED_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"})


class Stage(str, Enum):
    VERIFY = "verify"
    DOWNLOAD = "download"
    CROP = "crop"
    PDF = "pdf"
