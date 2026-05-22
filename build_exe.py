"""Build a single-file Windows .exe with PyInstaller.

Run:
    pip install pyinstaller
    python build_exe.py

Produces `dist/MPCFillToPDF.exe`. The .exe is portable: drop it in any
folder and it will create `out/` and `workdir/` next to itself.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "MPCFillToPDF"
ENTRY = ROOT / "gui" / "main.py"
ASSETS = ROOT / "src" / "assets"


def main() -> None:
    if shutil.which("pyinstaller") is None:
        print("pyinstaller not found. Install it with: pip install pyinstaller",
              file=sys.stderr)
        sys.exit(1)

    args = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", APP_NAME,
        f"--add-data={ASSETS}{';' if sys.platform == 'win32' else ':'}src/assets",
        # Make sure these packages are bundled even when discovered indirectly
        "--hidden-import=PIL.Image",
        "--hidden-import=reportlab.pdfgen",
        "--hidden-import=gdown",
        str(ENTRY),
    ]
    print("Running:", " ".join(args))
    subprocess.run(args, check=True, cwd=ROOT)
    print(f"\nBuilt: {ROOT / 'dist' / (APP_NAME + '.exe')}")


if __name__ == "__main__":
    main()
