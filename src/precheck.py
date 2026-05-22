"""Pre-flight check: count cards per XML, plan merges to avoid blank slots.

Print shops charge per A4 sheet whether the 3×3 grid is full or not, so we
either merge small XMLs into bigger ones (when the global total is a multiple
of 9) or warn the user before generating any PDF with paid empty slots.
"""
from dataclasses import dataclass
from pathlib import Path

from src.parser import parse

CARDS_PER_PAGE = 9


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

    @property
    def is_merged(self) -> bool:
        return len(self.xml_paths) > 1


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
    merged_xmls: list[XmlReport]   # which XMLs got fused into a merge job
    residual_blanks: list[XmlReport]  # XMLs that still produce PDFs with blanks

    @property
    def has_merge(self) -> bool:
        return any(j.is_merged for j in self.jobs)

    @property
    def has_blanks(self) -> bool:
        return bool(self.residual_blanks)


def plan(reports: list[XmlReport]) -> Plan:
    """Decide how XMLs map to PDFs.

    - Each XML whose deck is already a multiple of 9 becomes a solo job.
    - All unaligned XMLs are checked: if their combined total is a multiple
      of 9 they are fused into a single merged job (named `<a>_<b>_..._union`).
    - Otherwise each unaligned XML becomes a solo job and `residual_blanks`
      lists those that will print blank slots.
    """
    aligned   = [r for r in reports if not r.has_blanks]
    unaligned = [r for r in reports if r.has_blanks]

    jobs = [PdfJob([r.path], r.path.stem, r.cards) for r in aligned]

    if not unaligned:
        return Plan(jobs, [], [])

    total_unaligned = sum(r.cards for r in unaligned)
    if total_unaligned % CARDS_PER_PAGE == 0:
        ordered = sorted(unaligned, key=lambda r: -r.cards)
        base = "_".join(r.path.stem for r in ordered) + "_union"
        jobs.append(PdfJob([r.path for r in ordered], base, total_unaligned))
        return Plan(jobs, ordered, [])

    for r in unaligned:
        jobs.append(PdfJob([r.path], r.path.stem, r.cards))
    return Plan(jobs, [], unaligned)


def format_merge_info(plan_: Plan) -> str | None:
    if not plan_.has_merge:
        return None
    lines = ["Se fusionarán las siguientes barajas para evitar huecos en blanco:"]
    for job in plan_.jobs:
        if not job.is_merged:
            continue
        names = ", ".join(p.name for p in job.xml_paths)
        lines.append(f"  • {job.base_name}.pdf ← {names}  ({job.cards} cartas)")
    return "\n".join(lines)


def format_warning(reports_or_plan) -> str | None:
    """Warning about blank slots that will be printed. Accepts either a list
    of reports (legacy) or a Plan (new)."""
    if isinstance(reports_or_plan, Plan):
        bad = reports_or_plan.residual_blanks
    else:
        bad = [r for r in reports_or_plan if r.has_blanks]
    if not bad:
        return None
    lines = [
        "Aviso: las siguientes barajas no son múltiplos de 9.",
        "La última página de cada PDF tendrá huecos en blanco "
        "(la imprenta cobra la página entera aunque no esté llena):",
        "",
    ]
    for r in bad:
        s = "hueco" if r.blanks == 1 else "huecos"
        lines.append(f"  • {r.path.name}: {r.cards} cartas → {r.blanks} {s} en blanco")
    return "\n".join(lines)


def write_manifest(
    plan_: Plan,
    reports: list[XmlReport],
    output_dir: Path,
) -> Path | None:
    """Write `fusiones.txt` when the plan contains a merge; otherwise remove any
    stale `fusiones.txt` left over from a previous run that did have merges."""
    out = output_dir / "fusiones.txt"
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
