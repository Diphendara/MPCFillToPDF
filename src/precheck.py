"""Pre-flight check: count cards per XML, plan merges to avoid blank slots.

Print shops charge per A4 sheet whether the 3×3 grid is full or not, so we
either merge small XMLs into bigger ones (when the global total is a multiple
of 9) or warn the user before generating any PDF with paid empty slots.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

from src.constants import CARDS_PER_PAGE
from src.parser import parse

_THUMB_CHECK_URL = "https://drive.google.com/thumbnail?id={}&sz=w1"
_CHECK_THREADS = 20
_CHECK_TIMEOUT = (5, 10)


def collect_drive_ids(xml_paths: list[Path]) -> list[tuple[str, str]]:
    """Return unique (drive_id, name) pairs from all XMLs (fronts + backs + cardback)."""
    pairs: dict[str, str] = {}
    for p in xml_paths:
        try:
            order = parse(p)
        except Exception:
            continue
        name_map = {c.drive_id: c.name for c in order.fronts + order.backs}
        for drive_id in order.all_drive_ids():
            pairs.setdefault(drive_id, name_map.get(drive_id, "cardback.jpg"))
    return list(pairs.items())


def check_drive_access(
    id_name_pairs: list[tuple[str, str]],
    progress_callback=None,
) -> list[tuple[str, str]]:
    """Check which Drive IDs are publicly accessible via thumbnail URL.

    Returns a list of (drive_id, name) for images that returned 403/404 —
    those have lost public access and will fail during download.
    Network errors are treated as accessible (transient, not a permission issue).
    progress_callback(done, total) is called after each check.
    """
    if not id_name_pairs:
        return []

    total = len(id_name_pairs)
    inaccessible: list[tuple[str, str]] = []

    def _check(drive_id: str, name: str) -> tuple[str, str, bool]:
        try:
            r = requests.get(
                _THUMB_CHECK_URL.format(drive_id),
                timeout=_CHECK_TIMEOUT,
                stream=True,
            )
            r.close()
            ok = r.status_code < 400
        except Exception:
            ok = True  # network/timeout error → assume accessible, don't false-positive
        return drive_id, name, ok

    done = 0
    with ThreadPoolExecutor(max_workers=_CHECK_THREADS) as ex:
        futures = {ex.submit(_check, did, name): (did, name) for did, name in id_name_pairs}
        for future in as_completed(futures):
            drive_id, name, ok = future.result()
            done += 1
            if not ok:
                inaccessible.append((drive_id, name))
            if progress_callback:
                progress_callback(done, total)

    return inaccessible


@dataclass
class XmlReport:
    path: Path
    cards: int
    blanks: int  # empty slots on the last page (0 if the deck fills the page)

    @property
    def has_blanks(self) -> bool:
        return self.blanks > 0


@dataclass
class PdfJob:
    xml_paths: list[Path]
    base_name: str
    cards: int
    extra_locals: int = 0  # local fronts appended to this job (only on the last job)

    @property
    def is_merged(self) -> bool:
        return len(self.xml_paths) > 1

    @property
    def total_cards(self) -> int:
        return self.cards + self.extra_locals

    @property
    def blanks(self) -> int:
        rem = self.total_cards % CARDS_PER_PAGE
        return (CARDS_PER_PAGE - rem) if rem else 0

    @property
    def has_blanks(self) -> bool:
        return self.blanks > 0

    @property
    def display_name(self) -> str:
        if self.is_merged:
            return self.base_name
        if self.xml_paths:
            return self.xml_paths[0].name
        return self.base_name


def analyze(xml_paths: list[str | Path]) -> list[XmlReport]:
    reports: list[XmlReport] = []
    for p in xml_paths:
        pth = Path(p)
        order = parse(pth)
        n = sum(len(card.slots) for card in order.fronts)
        last = n % CARDS_PER_PAGE
        blanks = (CARDS_PER_PAGE - last) if last else 0
        reports.append(XmlReport(pth, n, blanks))
    return reports


@dataclass
class Plan:
    jobs: list[PdfJob]
    merged_xmls: list[XmlReport]  # which XMLs got fused into a merge job

    @property
    def has_merge(self) -> bool:
        return any(j.is_merged for j in self.jobs)

    @property
    def residual_blanks(self) -> list[PdfJob]:
        return [j for j in self.jobs if j.has_blanks]

    @property
    def has_blanks(self) -> bool:
        return bool(self.residual_blanks)


def plan(reports: list[XmlReport], local_count: int = 0) -> Plan:
    """Decide how XMLs map to PDFs.

    - Each XML whose deck is already a multiple of 9 becomes a solo job.
    - Multiple unaligned XMLs are always fused into a single merged job
      (named `<a>_<b>_..._union`) to consolidate blank slots into one PDF.
    - A single unaligned XML becomes a solo job.
    - `local_count` is the number of local fronts that will be appended to the
      LAST job — included in that job's blank-slot calculation.
    """
    aligned = [r for r in reports if not r.has_blanks]
    unaligned = [r for r in reports if r.has_blanks]

    jobs = [PdfJob([r.path], r.path.stem, r.cards) for r in aligned]
    merged_xmls: list[XmlReport] = []

    if unaligned:
        total_unaligned = sum(r.cards for r in unaligned)
        if len(unaligned) == 1:
            jobs.append(PdfJob([unaligned[0].path], unaligned[0].path.stem, unaligned[0].cards))
        else:
            # Always merge multiple unaligned XMLs to consolidate blank slots into one PDF.
            # Even when the total isn't divisible by 9, merging is better than producing
            # several PDFs each with their own wasted slots.
            ordered = sorted(unaligned, key=lambda r: -r.cards)
            base = "_".join(r.path.stem for r in ordered) + "_union"
            jobs.append(PdfJob([r.path for r in ordered], base, total_unaligned))
            merged_xmls = ordered

    if local_count > 0 and jobs:
        jobs[-1].extra_locals = local_count

    return Plan(jobs, merged_xmls)


def format_merge_info(plan_: Plan) -> str | None:
    if not plan_.has_merge:
        return None
    lines = ["Se fusionarán las siguientes barajas para reducir huecos en blanco:"]
    for job in plan_.jobs:
        if not job.is_merged:
            continue
        names = ", ".join(p.name for p in job.xml_paths)
        lines.append(f"  • {job.base_name}.pdf ← {names}  ({job.cards} cartas)")
    return "\n".join(lines)


def format_warning(plan_: Plan) -> str | None:
    """Warning about blank slots that will be printed."""
    bad = plan_.residual_blanks
    if not bad:
        return None
    lines = [
        "Aviso: los siguientes PDF(s) no son múltiplos de 9.",
        "La última página tendrá huecos en blanco "
        "(la imprenta cobra la página entera aunque no esté llena):",
        "",
    ]
    for j in bad:
        s = "hueco" if j.blanks == 1 else "huecos"
        if j.extra_locals:
            cards_info = f"{j.total_cards} cartas ({j.cards} XML + {j.extra_locals} local(es))"
        else:
            cards_info = f"{j.total_cards} cartas"
        lines.append(f"  • {j.display_name}: {cards_info} → {j.blanks} {s} en blanco")
    return "\n".join(lines)


def write_manifest(
    plan_: Plan,
    reports: list[XmlReport],
    output_dir: Path,
) -> Path | None:
    """Write `resumen.txt` when the plan contains a merge; otherwise remove any
    stale `resumen.txt` left over from a previous run that did have merges."""
    out = output_dir / "resumen.txt"
    if not plan_.has_merge:
        if out.exists():
            out.unlink()
        return None
    counts = {r.path: r.cards for r in reports}
    with out.open("w", encoding="utf-8") as f:
        f.write("Fusiones realizadas para evitar huecos en blanco\n")
        f.write("=" * 50 + "\n\n")
        for job in plan_.jobs:
            if not job.is_merged:
                continue
            f.write(f"PDF: {job.base_name}.pdf  ({job.cards} cartas)\n")
            for p in job.xml_paths:
                n = counts.get(p, 0)
                f.write(f"  - {n} carta(s) de {p.name}\n")
            f.write("\n")
    return out
