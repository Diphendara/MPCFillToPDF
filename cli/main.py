import argparse
import shutil
import sys
import time
from pathlib import Path

from src.pipeline import run


_stage_started_at: dict[str, float] = {}


def _progress(stage: str, done: int, total: int) -> None:
    labels = {
        "download": "Descargando",
        "crop":     "Recortando ",
        "pdf":      "Generando  ",
    }
    label = labels.get(stage, stage)
    if stage not in _stage_started_at or done == 1:
        _stage_started_at[stage] = time.time()
    elapsed = time.time() - _stage_started_at[stage]
    bar_len = 30
    filled = int(bar_len * done / total)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r{label}: [{bar}] {done}/{total}  ({elapsed:5.1f}s)", end="", flush=True)
    if done == total:
        print()


def _cleanup(workdir: Path) -> None:
    for sub in ("raw", "bled"):
        target = workdir / sub
        if target.exists():
            shutil.rmtree(target)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte todos los .xml de la carpeta de entrada en PDFs en la carpeta de salida."
    )
    parser.add_argument(
        "--xml-dir", default="xml",
        help="Carpeta con los XML de MPCFill a procesar (default: xml)",
    )
    parser.add_argument(
        "--out-dir", default="out",
        help="Carpeta donde escribir los PDFs (default: out)",
    )
    parser.add_argument(
        "--workdir", default="workdir",
        help="Carpeta temporal para imágenes descargadas y recortadas (default: workdir)",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="No borrar workdir/raw ni workdir/bled al terminar; útil para iterar sin re-descargar/recortar.",
    )
    args = parser.parse_args()

    xml_dir = Path(args.xml_dir)
    out_dir = Path(args.out_dir)
    workdir = Path(args.workdir)

    if not xml_dir.exists():
        print(f"Error: la carpeta '{xml_dir}' no existe. Créala y añade XMLs.", file=sys.stderr)
        sys.exit(1)

    xmls = sorted(xml_dir.glob("*.xml"))
    if not xmls:
        print(f"No hay archivos .xml en '{xml_dir}'.")
        return

    print(f"Encontrados {len(xmls)} XML(s) en '{xml_dir}'.")
    overall_start = time.time()

    for xml_path in xmls:
        print(f"\nProcesando: {xml_path.name}")
        _stage_started_at.clear()
        pdfs = run(xml_path, out_dir, workdir, _progress)
        for p in pdfs:
            size_mb = p.stat().st_size / (1024 * 1024)
            print(f"  -> {p}  ({size_mb:.1f} MB)")

    total_elapsed = time.time() - overall_start
    print(f"\nTiempo total: {total_elapsed:.1f}s")

    if args.test:
        print("Modo --test: imágenes conservadas en workdir/ (raw y bled).")
    else:
        _cleanup(workdir)
        print("Imágenes temporales (workdir/raw y workdir/bled) eliminadas.")


if __name__ == "__main__":
    main()
