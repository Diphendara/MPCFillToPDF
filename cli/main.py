import argparse
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows consoles default to cp1252 which can't encode characters like ← or •.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

from src.constants import SUPPORTED_IMAGE_EXTS, Stage
from src.downloader import DownloadPermissionError, DownloadTimeoutError
from src.pipeline import run_deck_url, run_locals_only, run_plan
from src.precheck import (
    analyze,
    check_drive_access,
    collect_drive_ids,
    format_warning,
    plan,
    write_manifest,
)


def _validate_local_images(paths: list[str], label: str) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            print(f"Error: {label}: no existe '{pp}'.", file=sys.stderr)
            sys.exit(1)
        if pp.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
            print(
                f"Error: {label}: extensión no soportada '{pp.suffix}' en '{pp.name}'.",
                file=sys.stderr,
            )
            sys.exit(1)
        out.append(pp)
    return out


_stage_started_at: dict[str, float] = {}


def _progress(stage: str, done: int, total: int) -> None:
    labels = {
        Stage.VERIFY: "Verificando",
        Stage.DOWNLOAD: "Descargando",
        Stage.CROP: "Recortando ",
        Stage.PDF: "Generando  ",
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
    for sub in ("raw", "bled", "scryfall"):
        target = workdir / sub
        if target.exists():
            shutil.rmtree(target)


def _print_permission_error(e: DownloadPermissionError) -> None:
    print(file=sys.stderr)
    print(f"Error de descarga: no se pudo obtener «{e.card_name}»", file=sys.stderr)
    if e.xml_name:
        print(f"  Archivo XML: {e.xml_name}", file=sys.stderr)
    if e.position:
        print(f"  Posición en el PDF: {e.position}", file=sys.stderr)
    print(file=sys.stderr)
    print("Esto no es un fallo del programa. Posibles causas:", file=sys.stderr)
    print("  • El archivo solo permite descarga con cuenta de Google", file=sys.stderr)
    print("    («Cualquiera con el enlace» no basta para descarga anónima).", file=sys.stderr)
    print("  • Le han quitado los permisos de acceso público.", file=sys.stderr)
    print("Pide al creador que comparta las imágenes como «Público en Internet».", file=sys.stderr)


def _setup_logging(log_path: Path, verbose: bool) -> None:
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    if verbose:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.DEBUG, format=fmt, handlers=handlers)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convierte todos los .xml de la carpeta de entrada en PDFs en la carpeta de salida."
    )
    parser.add_argument(
        "--xml-dir",
        default="xml",
        help="Carpeta con los XML de MPCFill a procesar (default: xml)",
    )
    parser.add_argument(
        "--out-dir",
        default="out",
        help="Carpeta donde escribir los PDFs (default: out)",
    )
    parser.add_argument(
        "--workdir",
        default="workdir",
        help="Carpeta temporal para imágenes descargadas y recortadas (default: workdir)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="No borrar workdir/raw ni workdir/bled al terminar; útil para iterar sin re-descargar/recortar.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Continuar sin pedir confirmación cuando alguna baraja no sea múltiplo de 9.",
    )
    parser.add_argument(
        "--local-fronts",
        nargs="+",
        default=[],
        metavar="IMG",
        help="Imágenes locales adicionales a usar como fronts. Se añaden al final del último PDF generado.",
    )
    parser.add_argument(
        "--local-backs",
        nargs="+",
        default=[],
        metavar="IMG",
        help="Imágenes locales para los reversos de --local-fronts (emparejadas por orden). "
        "Si hay menos backs que fronts, los faltantes usan el cardback por defecto.",
    )
    parser.add_argument(
        "--local-cardback",
        default=None,
        metavar="IMG",
        help="Imagen local que actúa como cardback (sustituye al <cardback> del XML para los fronts locales). "
        "Obligatorio cuando no hay XMLs.",
    )
    parser.add_argument(
        "--locals-base-name",
        default="locales",
        metavar="NAME",
        help="Nombre base del PDF cuando se genera solo a partir de imágenes locales (default: locales).",
    )
    parser.add_argument(
        "--local-needs-crop",
        action="store_true",
        help="Aplicar el recorte de bleed MPC a las imágenes locales "
        "(por defecto desactivado: se asume que ya están sin borde).",
    )
    parser.add_argument(
        "--fronts-only",
        action="store_true",
        help="Generar solo páginas de frontales (sin páginas de traseras).",
    )
    parser.add_argument(
        "--deck-url",
        metavar="URL",
        help="Importar un mazo de Magic desde una URL compatible y generar su PDF.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Mostrar mensajes de depuración en stderr además de escribirlos en el log.",
    )
    return parser


def _handle_deck_url(args: argparse.Namespace) -> None:
    """Handle the --deck-url flow: import a deck from a URL and generate its PDF."""
    run_dir = Path(args.out_dir) / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(run_dir / "run.log", args.verbose)
    try:
        pdfs = run_deck_url(
            args.deck_url,
            run_dir,
            Path(args.workdir),
            "mazo_url",
            _progress,
            include_sideboard=False,
            fronts_only=args.fronts_only,
        )
    finally:
        if not args.test:
            _cleanup(Path(args.workdir))
    for pdf in pdfs:
        print(f"  -> {pdf}")


def _validate_locals_args(args: argparse.Namespace) -> tuple[list[Path], list[Path], Path | None]:
    """Validate local image arguments and return (fronts, backs, cardback)."""
    local_fronts = _validate_local_images(args.local_fronts, "--local-fronts")
    local_backs = _validate_local_images(args.local_backs, "--local-backs")
    local_cardback = (
        _validate_local_images([args.local_cardback], "--local-cardback")[0]
        if args.local_cardback
        else None
    )

    if local_backs and not local_fronts:
        print("Error: --local-backs requiere --local-fronts.", file=sys.stderr)
        sys.exit(1)
    if len(local_backs) > len(local_fronts):
        print(
            f"Error: hay {len(local_backs)} --local-backs pero solo {len(local_fronts)} "
            "--local-fronts. Los backs se emparejan por orden con los fronts.",
            file=sys.stderr,
        )
        sys.exit(1)
    return local_fronts, local_backs, local_cardback


def _collect_xmls(xml_dir: Path, local_fronts: list[Path]) -> list[Path]:
    """Return the list of XML files to process (empty if missing dir and locals exist)."""
    if not xml_dir.exists():
        if not local_fronts:
            print(f"Error: la carpeta '{xml_dir}' no existe. Créala y añade XMLs.", file=sys.stderr)
            sys.exit(1)
        # Locals-only run: skip the missing xml dir gracefully.
        return []
    return sorted(xml_dir.glob("*.xml"))


def _print_run_summary(
    xmls: list[Path],
    xml_dir: Path,
    local_fronts: list[Path],
    local_backs: list[Path],
    local_cardback: Path | None,
    run_dir: Path,
) -> None:
    if xmls:
        print(f"Encontrados {len(xmls)} XML(s) en '{xml_dir}'.")
    else:
        print(f"Sin XMLs: generando PDF solo con {len(local_fronts)} imagen(es) local(es).")
    if local_fronts:
        loc_msg = f"Imágenes locales: {len(local_fronts)} front(s)"
        if local_backs:
            loc_msg += f", {len(local_backs)} back(s) emparejados"
        if local_cardback:
            loc_msg += f", cardback local: {local_cardback.name}"
        print(loc_msg)
    print(f"Carpeta de salida: {run_dir}")


def _verify_drive_access(xmls: list[Path], workdir: Path, assume_yes: bool) -> bool:
    """Check Drive access for XML cards. Returns True to continue, False to cancel."""
    all_ids = collect_drive_ids(xmls)
    raw_dir = workdir / "raw"
    to_check = [(did, name) for did, name in all_ids if not list(raw_dir.glob(f"{did}.*"))]
    n_cached = len(all_ids) - len(to_check)
    if not to_check:
        if n_cached:
            print(f"\nVerificando XML: omitida ({n_cached} imagen(es) ya en caché)")
        return True

    cache_note = f"  ({n_cached} en caché)" if n_cached else ""
    print(f"\nVerificando XML{cache_note}:")
    _progress(Stage.VERIFY, 0, len(to_check))
    inaccessible = check_drive_access(
        to_check,
        progress_callback=lambda d, t: _progress(Stage.VERIFY, d, t),
    )
    if not inaccessible:
        return True

    print()
    print(f"Aviso: {len(inaccessible)} carta(s) sin acceso público en Google Drive:")
    for _, name in inaccessible:
        print(f"  • {name}")
    if assume_yes:
        return True
    print()
    ans = input("¿Continuar de todos modos? [s/N]: ").strip().lower()
    if ans not in ("s", "si", "sí", "y", "yes"):
        print("Cancelado.")
        return False
    return True


def _confirm_plan_warning(plan_, assume_yes: bool) -> bool:
    """Show plan warning and ask confirmation. Returns True to continue."""
    warning = format_warning(plan_)
    if not warning or assume_yes:
        return True
    print()
    print(warning)
    ans = input("¿Continuar? [s/N]: ").strip().lower()
    if ans not in ("s", "si", "sí", "y", "yes"):
        print("Cancelado.")
        return False
    return True


def _print_timeout_error(e: DownloadTimeoutError) -> None:
    print(file=sys.stderr)
    print(f"Error de descarga (tiempo agotado): «{e.card_name}»", file=sys.stderr)
    if e.xml_name:
        print(f"  Archivo XML: {e.xml_name}", file=sys.stderr)
    if e.position:
        print(f"  Posición en el PDF: {e.position}", file=sys.stderr)
    print(file=sys.stderr)
    print("La descarga no recibió datos durante 30 segundos y se canceló.", file=sys.stderr)
    print("Puede ser un problema temporal de Google Drive o de tu conexión.", file=sys.stderr)
    print("Vuelve a intentarlo en unos minutos.", file=sys.stderr)


def _run_plan_jobs(
    plan_,
    args: argparse.Namespace,
    run_dir: Path,
    workdir: Path,
    local_fronts: list[Path],
    local_backs: list[Path],
) -> list[Path]:
    """Execute the planned jobs and return generated PDFs."""
    job_labels = {
        j.base_name: j.base_name + (" (fusión)" if j.is_merged else "") for j in plan_.jobs
    }

    def on_job_pdf_start(job_idx, total_jobs, job_name):
        label = job_labels.get(job_name, job_name)
        if job_idx == 1 and local_fronts:
            # Only last job gets locals; adjust label if it's also last
            pass
        last_job_name = plan_.jobs[-1].base_name
        if job_name == last_job_name and local_fronts:
            label += f" + {len(local_fronts)} local(es)"
        print(f"\nGenerando PDF: {label}")
        _stage_started_at.clear()

    return run_plan(
        plan_.jobs,
        run_dir,
        workdir,
        _progress,
        cancel_event=None,
        extra_fronts=local_fronts or None,
        extra_backs=local_backs or None,
        local_crop_map={p: args.local_needs_crop for p in (*local_fronts, *local_backs)}
        or None,
        on_job_pdf_start=on_job_pdf_start,
        fronts_only=args.fronts_only,
    )


def _run_locals_only_job(
    args: argparse.Namespace,
    run_dir: Path,
    workdir: Path,
    local_fronts: list[Path],
    local_backs: list[Path],
    local_cardback: Path | None,
) -> list[Path]:
    """Run a single locals-only job (no XMLs) and return generated PDFs."""
    print(f"\nProcesando: {args.locals_base_name} (solo imágenes locales)")
    _stage_started_at.clear()
    all_locals = [*local_fronts, *local_backs]
    if local_cardback is not None:
        all_locals.append(local_cardback)
    return run_locals_only(
        local_fronts,
        local_cardback,
        run_dir,
        args.locals_base_name,
        workdir,
        _progress,
        extra_backs=local_backs or None,
        local_crop_map={p: args.local_needs_crop for p in all_locals},
        fronts_only=args.fronts_only,
    )


def _print_pdfs(pdfs: list[Path]) -> None:
    for p in pdfs:
        size_mb = p.stat().st_size / (1024 * 1024)
        print(f"  -> {p}  ({size_mb:.1f} MB)")


def _execute_plan(
    plan_,
    reports,
    args: argparse.Namespace,
    run_dir: Path,
    workdir: Path,
    local_fronts: list[Path],
    local_backs: list[Path],
    local_cardback: Path | None,
) -> None:
    """Execute the plan (or locals-only job) and handle errors/cleanup."""
    overall_start = time.time()

    try:
        if plan_ is not None:
            pdfs = _run_plan_jobs(plan_, args, run_dir, workdir, local_fronts, local_backs)
        else:
            pdfs = _run_locals_only_job(
                args, run_dir, workdir, local_fronts, local_backs, local_cardback
            )
        _print_pdfs(pdfs)

    except DownloadPermissionError as e:
        _print_permission_error(e)
        sys.exit(1)
    except DownloadTimeoutError as e:
        _print_timeout_error(e)
        sys.exit(1)

    manifest = write_manifest(plan_, reports, run_dir) if plan_ is not None else None
    if manifest:
        print(f"\nResumen de fusiones escrito en: {manifest}")

    total_elapsed = time.time() - overall_start
    print(f"\nTiempo total: {total_elapsed:.1f}s")

    if args.test:
        print("Modo --test: imágenes conservadas en workdir/ (raw y bled).")
    else:
        _cleanup(workdir)
        print("Imágenes temporales (workdir/raw y workdir/bled) eliminadas.")


def _execute_plan(
    plan_,
    reports,
    args: argparse.Namespace,
    run_dir: Path,
    workdir: Path,
    local_fronts: list[Path],
    local_backs: list[Path],
    local_cardback: Path | None,
) -> None:
    """Execute the plan (or locals-only job) and handle errors/cleanup."""
    overall_start = time.time()

    try:
        if plan_ is not None:
            pdfs = _run_plan_jobs(plan_, args, run_dir, workdir, local_fronts, local_backs)
        else:
            pdfs = _run_locals_only_job(
                args, run_dir, workdir, local_fronts, local_backs, local_cardback
            )
        _print_pdfs(pdfs)

    except DownloadPermissionError as e:
        _print_permission_error(e)
        sys.exit(1)
    except DownloadTimeoutError as e:
        _print_timeout_error(e)
        sys.exit(1)

    manifest = write_manifest(plan_, reports, run_dir) if plan_ is not None else None
    if manifest:
        print(f"\nResumen de fusiones escrito en: {manifest}")

    total_elapsed = time.time() - overall_start
    print(f"\nTiempo total: {total_elapsed:.1f}s")

    if args.test:
        print("Modo --test: imágenes conservadas en workdir/ (raw y bled).")
    else:
        _cleanup(workdir)
        print("Imágenes temporales (workdir/raw y workdir/bled) eliminadas.")


def main() -> None:
    args = _build_parser().parse_args()

    if args.deck_url:
        _handle_deck_url(args)
        return

    local_fronts, local_backs, local_cardback = _validate_locals_args(args)

    xml_dir = Path(args.xml_dir)
    out_dir = Path(args.out_dir)
    workdir = Path(args.workdir)

    xmls = _collect_xmls(xml_dir, local_fronts)
    if not xmls and not local_fronts:
        print(f"No hay archivos .xml en '{xml_dir}'.")
        return
    if not xmls and local_fronts and local_cardback is None:
        print(
            "Error: sin XMLs, --local-cardback es obligatorio para definir el reverso por defecto.",
            file=sys.stderr,
        )
        sys.exit(1)

    run_dir = out_dir / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(run_dir / "run.log", args.verbose)

    _print_run_summary(xmls, xml_dir, local_fronts, local_backs, local_cardback, run_dir)

    reports = analyze(xmls) if xmls else []
    for r in reports:
        print(
            f"  - {r.path.name}: {r.cards} cartas"
            + (f"  ({r.blanks} hueco(s) en blanco)" if r.has_blanks else "")
        )

    # --- Verify Drive access before downloading ----------------------------
    if xmls and not _verify_drive_access(xmls, workdir, args.yes):
        return

    plan_ = plan(reports, local_count=len(local_fronts)) if reports else None

    if plan_ is not None and not _confirm_plan_warning(plan_, args.yes):
        return
    print()

    _execute_plan(
        plan_, reports, args, run_dir, workdir, local_fronts, local_backs, local_cardback
    )


if __name__ == "__main__":
    main()
