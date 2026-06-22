"""Resolve runtime directories that must live next to the executable.

When frozen by PyInstaller (--onefile), `sys.executable` is the .exe path,
and bundled data is unpacked under `sys._MEIPASS`. We want the user-facing
folders to be persistent siblings of the .exe — never inside the temp
extraction dir — so the user finds their PDFs and cache after the .exe exits.

All output lives under a single "MPCFillToPDF/" root folder next to the .exe:
  MPCFillToPDF/archivos generados/   ← PDFs
  MPCFillToPDF/procesamiento/        ← download cache, logs
"""

import sys
from pathlib import Path


def app_base_dir() -> Path:
    """Directory next to the .exe when frozen; project root otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _mpc_dir() -> Path:
    return app_base_dir() / "MPCFillToPDF"


def output_dir() -> Path:
    return _mpc_dir() / "archivos generados"


def work_dir() -> Path:
    return _mpc_dir() / "procesamiento"
