"""Build a single-file Windows .exe with PyInstaller.

Run:
    pip install pyinstaller
    python build_exe.py

Produces `dist/MPCFillToPDF.exe`. The .exe is portable: drop it in any
folder and it will create `out/` and `workdir/` next to itself.

SmartScreen / antivirus false positives
---------------------------------------
This build embeds Windows version metadata via `version_file.txt`, which
reduces (but does not eliminate) the "unknown publisher" SmartScreen prompt
on first launch.

To reduce false positives further, you can rebuild PyInstaller's bootloader
from source so it has a unique hash that AV vendors don't yet flag:

    # One-time setup (requires a C compiler; on Windows install
    # "Visual Studio Build Tools" with the C++ workload).
    git clone https://github.com/pyinstaller/pyinstaller.git
    cd pyinstaller/bootloader
    python ./waf all
    cd ..
    pip install --upgrade .

After that, run `python build_exe.py` as usual.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "MPCFillToPDF"
ENTRY = ROOT / "gui" / "main.py"
ASSETS = ROOT / "src" / "assets"
VERSION_FILE = ROOT / "version_file.txt"


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
        f"--version-file={VERSION_FILE}",
        f"--add-data={ASSETS}{';' if sys.platform == 'win32' else ':'}src/assets",
        # Make sure these packages are bundled even when discovered indirectly
        "--hidden-import=PIL.Image",
        "--hidden-import=reportlab.pdfgen",
        "--hidden-import=gdown",
        "--hidden-import=windnd",
        str(ENTRY),
    ]
    print("Running:", " ".join(args))
    subprocess.run(args, check=True, cwd=ROOT)
    print(f"\nBuilt: {ROOT / 'dist' / (APP_NAME + '.exe')}")


if __name__ == "__main__":
    main()
