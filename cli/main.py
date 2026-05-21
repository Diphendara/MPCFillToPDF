import argparse
import sys
from pathlib import Path

from src.pipeline import run


def _progress(stage: str, done: int, total: int) -> None:
    labels = {"download": "Descargando", "crop": "Recortando"}
    label = labels.get(stage, stage)
    bar_len = 30
    filled = int(bar_len * done / total)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r{label}: [{bar}] {done}/{total}", end="", flush=True)
    if done == total:
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte un XML de MPCFill en un PDF listo para imprimir."
    )
    parser.add_argument("xml", help="Ruta al archivo XML de MPCFill")
    parser.add_argument(
        "-o", "--output", default="output.pdf", help="Ruta del PDF de salida (default: output.pdf)"
    )
    parser.add_argument(
        "--workdir", default="workdir", help="Carpeta temporal para imágenes (default: workdir)"
    )
    args = parser.parse_args()

    xml_path = Path(args.xml)
    if not xml_path.exists():
        print(f"Error: no se encontró el archivo '{xml_path}'", file=sys.stderr)
        sys.exit(1)

    print(f"Procesando: {xml_path}")
    run(xml_path, args.output, args.workdir, _progress)
    print(f"\nPDF generado: {args.output}")


if __name__ == "__main__":
    main()
