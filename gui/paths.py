"""Resolve runtime directories that must live next to the executable.

When frozen by PyInstaller (--onefile), `sys.executable` is the .exe path,
and bundled data is unpacked under `sys._MEIPASS`. We want `out/` and
`workdir/` to be persistent folders next to the .exe — never inside the
temp extraction dir — so the user finds their PDFs and cache after the
.exe exits.
"""

import sys
from pathlib import Path


def app_base_dir() -> Path:
    """Directory next to the .exe when frozen; project root otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def output_dir() -> Path:
    p = app_base_dir() / "out"
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_dir() -> Path:
    p = app_base_dir() / "workdir"
    p.mkdir(parents=True, exist_ok=True)
    return p
