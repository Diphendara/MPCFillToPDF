"""MPCFillToPDF GUI — pick XML(s) and optional local images, run the pipeline,
open the output folder."""

import logging
import math
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import windnd

    _WINDND_AVAILABLE = True
except ImportError:
    _WINDND_AVAILABLE = False

from gui.locals_tab import LocalsTabMixin
from gui.lorcana_tab import LorcanaTabMixin
from gui.op_tab import OPTabMixin
from gui.paths import output_dir, work_dir
from gui.rb_tab import RBTabMixin
from gui.widgets import (
    APP_TITLE,
    STAGE_LABELS,
    attach_context_menu,
    ellipsize,
    load_tab_icon,
    notify,
)
from gui.xml_tab import XmlTabMixin
from src.cancellation import Cancelled
from src.constants import CARDS_PER_PAGE, Stage
from src.deck_importer import DeckCard
from src.downloader import (
    DownloadPartialError,
    DownloadPermissionError,
    DownloadRateLimitError,
    DownloadTimeoutError,
)
from src.lorcana_scraper import LocanaDeck, get_lorcana_back
from src.lorcana_scraper import download_images as lorcana_download
from src.lorcana_scraper import expand_deck as lorcana_expand
from src.op_scraper import OPDeck, get_op_backs
from src.op_scraper import download_images as op_download
from src.op_scraper import expand_deck as op_expand
from src.parser import CardOrder
from src.pipeline import run_locals_only, run_plan
from src.precheck import (
    analyze,
    check_drive_access,
    collect_drive_ids,
    format_warning,
    plan,
    write_manifest,
)
from src.rb_scraper import RBDeck, get_rb_backs
from src.rb_scraper import download_images as rb_download
from src.rb_scraper import expand_deck as rb_expand
from src.scraper_utils import resources_dir
from src.scryfall import download_deck_images as scryfall_download
from src.validator import ValidationWarning

_log = logging.getLogger(__name__)


@dataclass
class MtgUrlDeck:
    url: str
    cards: list[DeckCard]
    include_side: bool = False
    name: str = ""
    back_path: Path | None = None

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        try:
            platform = self.url.split("/")[2].replace("www.", "")
            slug = self.url.rstrip("/").split("/")[-1]
            return f"{platform}/{slug}"
        except IndexError:
            return self.url[:40]

    @property
    def active_count(self) -> int:
        return sum(c.quantity for c in self.cards if c.zone == "main" or self.include_side)


@dataclass
class AppState:
    xml_paths: list[Path] = field(default_factory=list)
    local_fronts: list[Path] = field(default_factory=list)
    local_backs: list[Path] = field(default_factory=list)
    front_back_paths: list[Path | None] = field(default_factory=list)
    local_front_crop: list[bool] = field(default_factory=list)
    local_back_crop: list[bool] = field(default_factory=list)
    mtg_url_decks: list[MtgUrlDeck] = field(default_factory=list)


class App(XmlTabMixin, OPTabMixin, RBTabMixin, LorcanaTabMixin, LocalsTabMixin):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1200x760")
        root.minsize(1000, 660)

        self.state = AppState()
        self._xml_rows: list[dict] = []
        self._xml_card_counts: dict[Path, int] = {}
        self._xml_orders: dict[Path, CardOrder] = {}
        self._xml_validations: dict[Path, list[ValidationWarning]] = {}
        self._mtg_deck_rows: list[dict] = []
        self._front_rows: list[dict] = []
        self._back_rows: list[dict] = []

        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.running = False
        self.keep_cache = tk.BooleanVar(value=False)
        self._dl_speed_str: str = ""
        self._custom_output_dir: Path | None = None

        self._op_decks: list[OPDeck] = []
        self._op_deck_rows: list[dict] = []

        self._rb_decks: list[RBDeck] = []
        self._rb_deck_rows: list[dict] = []

        self._lorcana_decks: list[LocanaDeck] = []
        self._lorcana_deck_rows: list[dict] = []

        self._build_ui()
        self.root.after(80, self._drain_events)
        self.root.after(200, self._setup_dnd)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root)
        frm.pack(fill=tk.BOTH, expand=True, **pad)

        bottom_controls = ttk.Frame(frm)
        bottom_controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        self.keep_cache_cb = ttk.Checkbutton(
            bottom_controls,
            text="Guardar en el PC las imágenes entre ejecuciones",
            variable=self.keep_cache,
        )
        self.keep_cache_cb.pack(anchor=tk.W)

        ttk.Separator(bottom_controls, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        self.soriano_btn = ttk.Button(
            bottom_controls,
            text="Generar PDF con traseras (Para copisteria, con espejo horizontal)",
            command=lambda: self._start(fronts_only=False),
        )
        self.soriano_btn.pack(fill=tk.X)
        self.soriano_btn.state(["disabled"])

        self.fronts_only_btn = ttk.Button(
            bottom_controls,
            text="Generar PDF solo frontales",
            command=lambda: self._start(fronts_only=True),
        )
        self.fronts_only_btn.pack(fill=tk.X, pady=(4, 0))
        self.fronts_only_btn.state(["disabled"])

        self.stop_btn = ttk.Button(bottom_controls, text="Detener", command=self._request_stop)

        self.status_var = tk.StringVar(value="Listo. Selecciona uno o más XML o imágenes locales.")
        ttk.Label(bottom_controls, textvariable=self.status_var, anchor=tk.W).pack(
            fill=tk.X, pady=(10, 2)
        )

        self.progress = ttk.Progressbar(bottom_controls, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)

        out_row = ttk.Frame(bottom_controls)
        out_row.pack(fill=tk.X, pady=(8, 0))
        self.out_dir_var = tk.StringVar(value=str(output_dir()))
        self.out_label = ttk.Label(
            out_row, textvariable=self.out_dir_var, foreground="#666", anchor=tk.W
        )
        self.out_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(out_row, text="Cambiar…", command=self._pick_output_dir, width=9).pack(
            side=tk.RIGHT, padx=(6, 0)
        )

        self.timing_var = tk.StringVar(value="")
        ttk.Label(
            bottom_controls,
            textvariable=self.timing_var,
            foreground="#888",
            anchor=tk.W,
        ).pack(fill=tk.X)

        self._preflight_frame = ttk.LabelFrame(bottom_controls, text="Resumen")
        self._preflight_inner = ttk.Frame(self._preflight_frame)
        self._preflight_inner.pack(fill=tk.X, padx=6, pady=4)
        self._preflight_labels: list[ttk.Label] = []

        top = ttk.Frame(frm)
        top.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        top.columnconfigure(0, weight=1, uniform="cols")
        top.columnconfigure(1, weight=1, uniform="cols")
        top.rowconfigure(0, weight=1)

        self._build_xml_pane(top)
        self._build_locals_pane(top)

    def _build_xml_pane(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._game_notebook = notebook

        self._mtg_icon_img = load_tab_icon("mtg_icon")
        self._op_icon_img = load_tab_icon("op_icon")
        self._rb_icon_img = load_tab_icon("riftbound_icon")
        self._lorcana_icon_img = load_tab_icon("lorcana_icon")

        magic_frame = ttk.Frame(notebook)
        magic_kw: dict = {"text": " Magic"}
        if self._mtg_icon_img:
            magic_kw["image"] = self._mtg_icon_img
            magic_kw["compound"] = "left"
        notebook.add(magic_frame, **magic_kw)
        self._build_magic_tab(magic_frame)

        op_frame = ttk.Frame(notebook)
        op_kw: dict = {"text": " One Piece"}
        if self._op_icon_img:
            op_kw["image"] = self._op_icon_img
            op_kw["compound"] = "left"
        notebook.add(op_frame, **op_kw)
        self._build_onepiece_tab(op_frame)

        rb_frame = ttk.Frame(notebook)
        rb_kw: dict = {"text": " Riftbound"}
        if self._rb_icon_img:
            rb_kw["image"] = self._rb_icon_img
            rb_kw["compound"] = "left"
        notebook.add(rb_frame, **rb_kw)
        self._build_riftbound_tab(rb_frame)

        lorcana_frame = ttk.Frame(notebook)
        lorcana_kw: dict = {"text": " Lorcana"}
        if self._lorcana_icon_img:
            lorcana_kw["image"] = self._lorcana_icon_img
            lorcana_kw["compound"] = "left"
        notebook.add(lorcana_frame, **lorcana_kw)
        self._build_lorcana_tab(lorcana_frame)

    def _build_scrollable_rows(self, parent: ttk.Frame):
        """Create a Canvas + inner Frame for a vertically scrolling list of rows."""
        holder = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=1)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        canvas = tk.Canvas(holder, highlightthickness=0, background="#ffffff")
        scrollbar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window_id, width=e.width),
        )
        return canvas, inner, window_id

    @staticmethod
    def _decode_drop(files) -> list[Path]:
        result = []
        for f in files:
            if isinstance(f, bytes):
                try:
                    f = f.decode(sys.getfilesystemencoding())
                except UnicodeDecodeError:
                    f = f.decode("cp1252", errors="replace")
            result.append(Path(str(f)))
        return result

    def _setup_dnd(self) -> None:
        if not _WINDND_AVAILABLE:
            return
        try:
            for w in (self._xml_drop_frame, self.xml_canvas, self.xml_inner):
                windnd.hook_dropfiles(w, func=self._on_drop_xmls)
            for w in (self.backs_canvas, self.backs_inner):
                windnd.hook_dropfiles(w, func=self._on_drop_backs)
            for w in (self.fronts_canvas, self.fronts_inner):
                windnd.hook_dropfiles(w, func=self._on_drop_fronts)
        except Exception:
            pass

    def _bind_mousewheel(self, canvas: tk.Canvas, on: bool) -> None:
        if on:
            self._active_scroll_canvas = canvas
            canvas.bind_all("<MouseWheel>", self._on_mousewheel)
            canvas.bind_all("<Button-4>", self._on_mousewheel)
            canvas.bind_all("<Button-5>", self._on_mousewheel)
        else:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
            self._active_scroll_canvas = None

    def _on_mousewheel(self, event) -> None:
        canvas = getattr(self, "_active_scroll_canvas", None)
        if canvas is None:
            return
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")
        else:
            canvas.yview_scroll(int(-event.delta / 120), "units")

    def _pick_output_dir(self) -> None:
        chosen = filedialog.askdirectory(
            title="Selecciona la carpeta de salida para los PDFs",
            initialdir=str(self._custom_output_dir or output_dir()),
        )
        if chosen:
            self._custom_output_dir = Path(chosen)
            self.out_dir_var.set(str(self._custom_output_dir))

    def _effective_output_dir(self) -> Path:
        d = self._custom_output_dir or output_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _update_preflight(self) -> None:
        for widget in self._preflight_labels:
            widget.destroy()
        self._preflight_labels.clear()

        if (
            not self.state.xml_paths
            and not self.state.local_fronts
            and not self._op_decks
            and not self._rb_decks
            and not self._lorcana_decks
            and not self.state.mtg_url_decks
        ):
            self._preflight_frame.pack_forget()
            return

        def _row(parts: list[tuple[str, str]]) -> None:
            frame = ttk.Frame(self._preflight_inner)
            frame.pack(fill=tk.X)
            self._preflight_labels.append(frame)
            for text, style in parts:
                if style == "warn":
                    kw: dict = {"foreground": "#cc0000", "font": ("Segoe UI", 10, "bold")}
                elif style == "bold":
                    kw = {"foreground": "#444", "font": ("Segoe UI", 10, "bold")}
                else:
                    kw = {"foreground": "#444"}
                ttk.Label(frame, text=text, anchor=tk.W, **kw).pack(side=tk.LEFT)

        xml_total = 0

        for p in self.state.xml_paths:
            order = self._xml_orders.get(p)
            if order is None:
                _row([(f"• {p.name}: (no se pudo leer)", "normal")])
                continue
            n = sum(len(card.slots) for card in order.fronts)
            xml_total += n
            _row(
                [
                    (f"• {p.name}: ", "normal"),
                    (f"{n}", "bold"),
                    (" cartas", "normal"),
                ]
            )

        for deck in self._op_decks:
            n = deck.total_slots
            xml_total += n
            _row(
                [
                    (f"• One Piece – {ellipsize(deck.name, 22)}: ", "normal"),
                    (f"{n}", "bold"),
                    (" cartas", "normal"),
                ]
            )

        for deck in self._rb_decks:
            n = deck.total_slots
            xml_total += n
            _row(
                [
                    (f"• Riftbound – {ellipsize(deck.name, 22)}: ", "normal"),
                    (f"{n}", "bold"),
                    (" cartas", "normal"),
                ]
            )

        for deck in self._lorcana_decks:
            n = deck.total_slots
            xml_total += n
            _row(
                [
                    (f"• Lorcana – {ellipsize(deck.name, 22)}: ", "normal"),
                    (f"{n}", "bold"),
                    (" cartas", "normal"),
                ]
            )

        for deck in self.state.mtg_url_decks:
            n = deck.active_count
            xml_total += n
            _row(
                [
                    (f"• Magic – {ellipsize(deck.display_name, 28)}: ", "normal"),
                    (f"{n}", "bold"),
                    (" cartas", "normal"),
                ]
            )

        local_count = len(self.state.local_fronts)
        if local_count:
            _row(
                [
                    ("• Locales: ", "normal"),
                    (f"{local_count}", "bold"),
                    (" carta(s)", "normal"),
                ]
            )

        total_cards = xml_total + local_count
        if total_cards:
            pairs = math.ceil(total_cards / CARDS_PER_PAGE)
            rem = total_cards % CARDS_PER_PAGE
            blanks = (CARDS_PER_PAGE - rem) if rem else 0

            bled_dir = work_dir() / "bled"
            cached = len([f for f in bled_dir.iterdir() if f.is_file()]) if bled_dir.exists() else 0
            cache_str = f" · {cached} imagen(es) en caché" if cached else ""

            if blanks:
                _row(
                    [
                        ("Total: ", "normal"),
                        (f"{total_cards}", "bold"),
                        (f" cartas · {pairs} par(es) de páginas{cache_str} · ", "normal"),
                        (f"⚠ {blanks} huecos en la última página", "warn"),
                    ]
                )
            else:
                _row(
                    [
                        ("Total: ", "normal"),
                        (f"{total_cards}", "bold"),
                        (f" cartas · {pairs} par(es) de páginas{cache_str}", "normal"),
                    ]
                )

        self._preflight_frame.pack(fill=tk.X, pady=(8, 0))

    def _refresh_generate_state(self) -> None:
        ready = (
            bool(self.state.xml_paths)
            or (self.state.local_fronts and self.state.local_backs)
            or self._op_decks
            or self._rb_decks
            or self._lorcana_decks
            or bool(self.state.mtg_url_decks)
        )
        if ready and not self.running:
            self.soriano_btn.state(["!disabled"])
            self.fronts_only_btn.state(["!disabled"])
        else:
            self.soriano_btn.state(["disabled"])
            self.fronts_only_btn.state(["disabled"])
        self._update_preflight()

    def _resolve_extra_backs(self) -> list[Path | None]:
        return [
            self.state.front_back_paths[i] if i < len(self.state.front_back_paths) else None
            for i in range(len(self.state.local_fronts))
        ]

    def _build_crop_map(self) -> dict[Path, bool]:
        m: dict[Path, bool] = {}
        for p, c in zip(self.state.local_backs, self.state.local_back_crop):
            m[p] = c
        for p, c in zip(self.state.local_fronts, self.state.local_front_crop):
            m[p] = c
        return m

    def _start(self, fronts_only: bool = False) -> None:
        if self.running:
            return

        if (
            not self.state.xml_paths
            and not self.state.local_fronts
            and not self._op_decks
            and not self._rb_decks
            and not self._lorcana_decks
            and not self.state.mtg_url_decks
        ):
            messagebox.showerror(
                APP_TITLE,
                "Selecciona al menos un XML, imágenes locales, o un mazo de "
                "One Piece, Riftbound, Lorcana o desde una URL.",
            )
            return

        if not self.state.xml_paths and self.state.local_fronts and not self.state.local_backs:
            messagebox.showerror(
                APP_TITLE,
                "Sin XMLs se necesita al menos un back local "
                "(el primero actúa como reverso por defecto).",
            )
            return

        reports = []
        plan_ = None
        if self.state.xml_paths:
            all_xml_warnings = [
                (p, ws) for p in self.state.xml_paths if (ws := self._xml_validations.get(p))
            ]
            if all_xml_warnings:
                lines = []
                for p, ws in all_xml_warnings:
                    for w in ws:
                        lines.append(f"[{p.name}] {w.message}")
                preview = "\n".join(f"• {line}" for line in lines[:10])
                more = f"\n… y {len(lines) - 10} más" if len(lines) > 10 else ""
                if not messagebox.askyesno(
                    APP_TITLE,
                    f"Se encontraron {len(lines)} advertencia(s) en los XML:\n\n"
                    f"{preview}{more}\n\n¿Continuar de todos modos?",
                    icon=messagebox.WARNING,
                ):
                    return

            try:
                reports = analyze(self.state.xml_paths)
            except Exception as e:
                self._show_error_dialog(f"No se pudo analizar el XML:\n{e}")
                return

            plan_ = plan(reports, local_count=len(self.state.local_fronts))

            if format_warning(plan_):
                combined_total = (
                    sum(r.cards for r in reports)
                    + len(self.state.local_fronts)
                    + sum(d.total_slots for d in self._op_decks)
                    + sum(d.total_slots for d in self._rb_decks)
                    + sum(d.total_slots for d in self._lorcana_decks)
                    + sum(d.active_count for d in self.state.mtg_url_decks)
                )
                combined_rem = combined_total % CARDS_PER_PAGE
                if combined_rem != 0:
                    combined_blanks = CARDS_PER_PAGE - combined_rem
                    s = "hueco" if combined_blanks == 1 else "huecos"
                    combined_warning = (
                        f"Aviso: {combined_total} carta(s) en total no es múltiplo de 9.\n"
                        f"La última página tendrá {combined_blanks} {s} en blanco "
                        "(la imprenta cobra la página entera aunque no esté llena)."
                    )
                    if not messagebox.askyesno(
                        APP_TITLE,
                        combined_warning + "\n\n¿Continuar de todos modos?",
                        icon=messagebox.WARNING,
                    ):
                        return
        else:
            total = (
                len(self.state.local_fronts)
                + sum(d.total_slots for d in self._op_decks)
                + sum(d.total_slots for d in self._rb_decks)
                + sum(d.total_slots for d in self._lorcana_decks)
                + sum(d.active_count for d in self.state.mtg_url_decks)
            )
            rem = total % CARDS_PER_PAGE
            if rem:
                blanks = CARDS_PER_PAGE - rem
                s = "hueco" if blanks == 1 else "huecos"
                warning = (
                    f"Aviso: {total} carta(s) no es múltiplo de 9.\n"
                    f"La última página tendrá {blanks} {s} en blanco "
                    "(la imprenta cobra la página entera aunque no esté llena)."
                    "\n\n¿Continuar de todos modos?"
                )
                if not messagebox.askyesno(APP_TITLE, warning, icon=messagebox.WARNING):
                    return

        self.running = True
        self.cancel_event.clear()
        self._dl_speed_str = ""
        self.timing_var.set("")
        self.soriano_btn.state(["disabled"])
        self.fronts_only_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.stop_btn.pack(fill=tk.X, pady=(4, 0), after=self.fronts_only_btn)
        self.progress["value"] = 0
        self.status_var.set("Preparando…")
        self._reset_xml_download_progress()
        self.worker = threading.Thread(
            target=self._work,
            args=(plan_, reports, fronts_only),
            daemon=True,
        )
        self.worker.start()

    def _request_stop(self) -> None:
        if not self.running:
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "¿Seguro que quieres detener el proceso en curso?",
            icon=messagebox.WARNING,
        ):
            return
        self.cancel_event.set()
        self.stop_btn.state(["disabled"])
        self.status_var.set("Cancelando…")

    def _work(self, plan_, reports, fronts_only: bool = False) -> None:
        run_dir = None
        wd = None
        try:
            out = self._effective_output_dir()
            wd = work_dir()

            bled_dir = wd / "bled"
            if bled_dir.exists():
                cached = [f for f in bled_dir.iterdir() if f.is_file()]
                if cached:
                    self.events.put(("checkpoint_found", len(cached)))

            run_dir = out / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
            run_dir.mkdir(parents=True, exist_ok=True)
            generated: list[Path] = []
            extra_backs = self._resolve_extra_backs()
            crop_map = self._build_crop_map()

            _run_start = time.time()
            _phase_first: dict[str, float] = {}
            _phase_done: dict[str, float] = {}

            def _track(stage: str, done: int, total: int) -> None:
                now = time.time()
                if stage not in _phase_first:
                    _phase_first[stage] = now
                if done == total and total > 0:
                    _phase_done[stage] = now

            op_fronts: list[Path] = []
            op_backs_resolved: list[Path] = []
            op_crop_extra: dict[Path, bool] = {}
            op_standard_back: Path | None = None

            if self._op_decks:
                op_raw_dir = wd / "op_raw"
                op_label = " + ".join(d.name for d in self._op_decks)
                op_total_unique = sum(len({c.card_id for c in d.cards}) for d in self._op_decks)
                self.events.put(
                    ("progress", "download", 0, op_total_unique, f"One Piece – {op_label}")
                )
                image_map_op: dict[str, Path] = {}
                done_dl_op = 0
                for deck in self._op_decks:
                    _off_op = done_dl_op

                    def _op_prog(done, total, _o=_off_op, _t=op_total_unique, _lbl=op_label):
                        _track("download", _o + done, _t)
                        self.events.put(
                            ("progress", "download", _o + done, _t, f"One Piece – {_lbl}")
                        )

                    part = op_download(
                        deck, op_raw_dir, cancel_event=self.cancel_event, progress_cb=_op_prog
                    )
                    image_map_op.update(part)
                    done_dl_op += len({c.card_id for c in deck.cards})
                    if self.cancel_event.is_set():
                        self.events.put(("cancelled", run_dir))
                        return
                op_standard_back, op_leader_back_res = get_op_backs()
                leader_backs_op: dict[str, Path] = {}
                for deck in self._op_decks:
                    if deck.leader and deck.leader.card_id not in leader_backs_op:
                        leader_backs_op[deck.leader.card_id] = op_leader_back_res
                for deck in self._op_decks:
                    lb = leader_backs_op.get(deck.leader.card_id) if deck.leader else None
                    fronts_op, backs_op = op_expand(deck, image_map_op, lb, op_standard_back)
                    op_fronts.extend(fronts_op)
                    op_backs_resolved.extend(op_standard_back if b is None else b for b in backs_op)
                op_all_back_paths = {op_standard_back} | set(leader_backs_op.values())
                op_crop_extra = {p: False for p in set(op_fronts) | op_all_back_paths}

            rb_fronts: list[Path] = []
            rb_backs_resolved: list[Path] = []
            rb_crop_extra: dict[Path, bool] = {}
            rb_default_back: Path | None = None

            if self._rb_decks:
                rb_raw_dir = wd / "rb_raw"
                rb_label = " + ".join(d.name for d in self._rb_decks)
                rb_total_unique = sum(len({c.variant_id for c in d.cards}) for d in self._rb_decks)
                self.events.put(
                    ("progress", "download", 0, rb_total_unique, f"Riftbound – {rb_label}")
                )
                image_map_rb: dict[str, Path] = {}
                done_dl_rb = 0
                for deck in self._rb_decks:
                    _off_rb = done_dl_rb

                    def _rb_prog(done, total, _o=_off_rb, _t=rb_total_unique, _lbl=rb_label):
                        _track("download", _o + done, _t)
                        self.events.put(
                            ("progress", "download", _o + done, _t, f"Riftbound – {_lbl}")
                        )

                    part = rb_download(
                        deck, rb_raw_dir, cancel_event=self.cancel_event, progress_cb=_rb_prog
                    )
                    image_map_rb.update(part)
                    done_dl_rb += len({c.variant_id for c in deck.cards})
                    if self.cancel_event.is_set():
                        self.events.put(("cancelled", run_dir))
                        return
                rb_backs_map = get_rb_backs()
                rb_default_back = rb_backs_map.get("maindeck") or next(iter(rb_backs_map.values()))
                rb_all_back_paths = set(rb_backs_map.values())
                print_runes_flags = [row["print_runes_var"].get() for row in self._rb_deck_rows]
                for idx, deck in enumerate(self._rb_decks):
                    include_runes = print_runes_flags[idx] if idx < len(print_runes_flags) else True
                    fronts_rb, backs_rb = rb_expand(
                        deck, image_map_rb, rb_backs_map, include_runes=include_runes
                    )
                    rb_fronts.extend(fronts_rb)
                    rb_backs_resolved.extend(rb_default_back if b is None else b for b in backs_rb)
                rb_crop_extra = {p: False for p in set(rb_fronts) | rb_all_back_paths}

            lorcana_fronts: list[Path] = []
            lorcana_backs_resolved: list[Path | None] = []
            lorcana_crop_extra: dict[Path, bool] = {}
            lorcana_default_back: Path | None = None

            if self._lorcana_decks:
                lorcana_raw_dir = wd / "lorcana_raw"
                lorcana_label = " + ".join(d.name for d in self._lorcana_decks)
                lorcana_total_unique = sum(
                    len({c.card_id for c in d.cards}) for d in self._lorcana_decks
                )
                self.events.put(
                    (
                        "progress",
                        "download",
                        0,
                        lorcana_total_unique,
                        f"Lorcana – {lorcana_label}",
                    )
                )
                image_map_lorcana: dict[str, Path] = {}
                done_dl_lorcana = 0
                for deck in self._lorcana_decks:
                    _off_lorcana = done_dl_lorcana

                    def _lorcana_prog(
                        done, total, _o=_off_lorcana, _t=lorcana_total_unique, _lbl=lorcana_label
                    ):
                        _track("download", _o + done, _t)
                        self.events.put(
                            ("progress", "download", _o + done, _t, f"Lorcana – {_lbl}")
                        )

                    part = lorcana_download(
                        deck,
                        lorcana_raw_dir,
                        cancel_event=self.cancel_event,
                        progress_cb=_lorcana_prog,
                    )
                    image_map_lorcana.update(part)
                    done_dl_lorcana += len({c.card_id for c in deck.cards})
                    if self.cancel_event.is_set():
                        self.events.put(("cancelled", run_dir))
                        return
                lorcana_back = get_lorcana_back()
                lorcana_default_back = lorcana_back
                for deck in self._lorcana_decks:
                    fronts_lorcana, backs_lorcana = lorcana_expand(deck, image_map_lorcana)
                    lorcana_fronts.extend(fronts_lorcana)
                    lorcana_backs_resolved.extend(
                        lorcana_back if b is None else b for b in backs_lorcana
                    )
                lorcana_crop_extra = {p: False for p in set(lorcana_fronts) | {lorcana_back}}

            mtg_fronts: list[Path] = []
            mtg_backs_resolved: list[Path] = []
            mtg_crop_extra: dict[Path, bool] = {}
            mtg_default_back: Path | None = None

            if self.state.mtg_url_decks:
                mtg_default_back = resources_dir() / "backs" / "mtg" / "back.jpg"
                scryfall_dir = wd / "scryfall"
                mtg_cards_with_deck: list[tuple[DeckCard, MtgUrlDeck]] = []
                for _deck in self.state.mtg_url_decks:
                    for c in _deck.cards:
                        if c.zone == "main" or _deck.include_side:
                            mtg_cards_with_deck.append((c, _deck))
                mtg_cards_all = [c for c, _ in mtg_cards_with_deck]
                mtg_label = f"Magic – {len(self.state.mtg_url_decks)} mazo(s)"
                self.events.put(("progress", "download", 0, len(mtg_cards_all), mtg_label))

                def _mtg_prog(done: int, total: int) -> None:
                    _track("download", done, total)
                    self.events.put(("progress", "download", done, total, mtg_label))

                dl_results = scryfall_download(
                    mtg_cards_all, scryfall_dir, _mtg_prog, cancel_event=self.cancel_event
                )

                if self.cancel_event.is_set():
                    self.events.put(("cancelled", run_dir))
                    return

                local_back_set = set(self.state.local_backs)
                all_mtg_back_paths: set[Path] = {mtg_default_back}
                for (card, front_path, back_path), (_, deck) in zip(
                    dl_results, mtg_cards_with_deck
                ):
                    if back_path is not None:
                        resolved_back = back_path
                    elif deck.back_path in local_back_set:
                        resolved_back = deck.back_path
                    else:
                        resolved_back = mtg_default_back
                    all_mtg_back_paths.add(resolved_back)
                    for _ in range(card.quantity):
                        mtg_fronts.append(front_path)
                        mtg_backs_resolved.append(resolved_back)
                mtg_crop_extra = {
                    p: False
                    for p in set(mtg_fronts) | all_mtg_back_paths
                    if p not in local_back_set
                }

            all_extra_fronts = (
                list(self.state.local_fronts) + op_fronts + rb_fronts + lorcana_fronts + mtg_fronts
            )
            all_extra_backs: list[Path | None] = (
                list(extra_backs)
                + op_backs_resolved
                + rb_backs_resolved
                + lorcana_backs_resolved
                + mtg_backs_resolved
            )
            all_crop_map = {
                **crop_map,
                **op_crop_extra,
                **rb_crop_extra,
                **lorcana_crop_extra,
                **mtg_crop_extra,
            }

            if plan_ is not None:
                xml_paths_flat = [Path(p) for job in plan_.jobs for p in job.xml_paths]
                all_ids = collect_drive_ids(xml_paths_flat)
                raw_dir = wd / "raw"
                to_check = [
                    (did, name) for did, name in all_ids if not list(raw_dir.glob(f"{did}.*"))
                ]
                if to_check:
                    self.events.put(
                        ("progress", Stage.VERIFY, 0, len(to_check), "XML seleccionados")
                    )

                    def _verify_cb(done, total):
                        _track(Stage.VERIFY, done, total)
                        self.events.put(
                            ("progress", Stage.VERIFY, done, total, "XML seleccionados")
                        )

                    inaccessible = check_drive_access(to_check, _verify_cb)

                    if inaccessible and not self.cancel_event.is_set():
                        confirm_event = threading.Event()
                        self.events.put(("verify_warning", inaccessible, confirm_event))
                        while not confirm_event.wait(timeout=0.1):
                            if self.cancel_event.is_set():
                                break

                if self.cancel_event.is_set():
                    self.events.put(("cancelled", run_dir))
                    return

                _pdf_label = [""]

                def cb(stage, done, total):
                    _track(stage, done, total)
                    name = _pdf_label[0] if stage == "pdf" else "Todas las imágenes"
                    self.events.put(("progress", stage, done, total, name))

                def on_job_pdf_start(job_idx, total_jobs, job_name):
                    job = next((j for j in plan_.jobs if j.base_name == job_name), None)
                    label = job_name + (" (fusión)" if job and job.is_merged else "")
                    _pdf_label[0] = label
                    self.events.put(("file", job_idx, total_jobs, label))

                def on_xml_download_progress(xml_name, done, total):
                    self.events.put(("xml_download_progress", xml_name, done, total))

                def on_xml_crop_progress(xml_name, done, total):
                    self.events.put(("xml_crop_progress", xml_name, done, total))

                def on_speed_update(speed_mbps: float, eta_sec: float) -> None:
                    self.events.put(("download_speed", speed_mbps, eta_sec))

                pdfs = run_plan(
                    plan_.jobs,
                    run_dir,
                    wd,
                    cb,
                    cancel_event=self.cancel_event,
                    extra_fronts=all_extra_fronts or None,
                    extra_backs=all_extra_backs or None,
                    local_crop_map=all_crop_map or None,
                    on_job_pdf_start=on_job_pdf_start,
                    on_xml_download_progress=on_xml_download_progress,
                    on_xml_crop_progress=on_xml_crop_progress,
                    fronts_only=fronts_only,
                    on_speed_update=on_speed_update,
                )
                generated.extend(pdfs)
                manifest = write_manifest(plan_, reports, run_dir)
            else:
                if not all_extra_fronts:
                    raise ValueError("No hay cartas para generar.")
                if self.state.local_fronts and self.state.local_backs:
                    default_back: Path = self.state.local_backs[0]
                elif op_standard_back is not None:
                    default_back = op_standard_back
                elif rb_default_back is not None:
                    default_back = rb_default_back
                elif lorcana_default_back is not None:
                    default_back = lorcana_default_back
                elif mtg_default_back is not None:
                    default_back = mtg_default_back
                else:
                    raise ValueError("No se encontró reverso por defecto.")
                parts = [
                    p
                    for p in [
                        "locales" if self.state.local_fronts else None,
                        "One Piece" if op_fronts else None,
                        "Riftbound" if rb_fronts else None,
                        "Lorcana" if lorcana_fronts else None,
                        "magic_url" if mtg_fronts else None,
                    ]
                    if p
                ]
                base = "_".join(parts) if parts else "combinado"
                self.events.put(("file", 1, 1, base))

                def cb(stage, done, total, _label=base):
                    _track(stage, done, total)
                    self.events.put(("progress", stage, done, total, _label))

                pdfs = run_locals_only(
                    all_extra_fronts,
                    default_back,
                    run_dir,
                    base,
                    wd,
                    cb,
                    cancel_event=self.cancel_event,
                    extra_backs=all_extra_backs,
                    local_crop_map=all_crop_map,
                    fronts_only=fronts_only,
                )
                generated.extend(pdfs)
                manifest = None

            if not self.keep_cache.get():
                self._cleanup_workdir(wd)

            def _fmt_dur(sec: float) -> str:
                return f"{int(sec) // 60}m {int(sec) % 60}s" if sec >= 60 else f"{sec:.0f}s"

            timing_parts = []
            for stage in (Stage.VERIFY, Stage.DOWNLOAD, Stage.CROP, Stage.PDF):
                if stage in _phase_first and stage in _phase_done:
                    dur = _phase_done[stage] - _phase_first[stage]
                    label = {
                        Stage.VERIFY: "Verif.",
                        Stage.DOWNLOAD: "Descarga",
                        Stage.CROP: "Recorte",
                        Stage.PDF: "PDF",
                    }.get(stage, stage)
                    timing_parts.append(f"{label}: {_fmt_dur(dur)}")
            total_dur = time.time() - _run_start
            timing_str = "  ".join(timing_parts)
            if timing_str:
                timing_str += f"  Total: {_fmt_dur(total_dur)}"

            self.events.put(("done", generated, manifest, run_dir, timing_str))
        except DownloadPartialError as e:
            self.events.put(
                (
                    "partial_download_error",
                    e.permission_errors,
                    e.timeout_errors,
                    e.xml_context,
                    run_dir,
                )
            )
        except DownloadRateLimitError:
            self.events.put(("rate_limit_error", run_dir))
        except DownloadPermissionError as e:
            self.events.put(("permission_error", e.card_name, e.xml_name, e.position, run_dir))
        except DownloadTimeoutError as e:
            self.events.put(("timeout_error", e.card_name, e.xml_name, e.position, run_dir))
        except Cancelled:
            self.events.put(("cancelled", run_dir))
        except Exception as e:
            self.events.put(("error", f"{e}\n\n{traceback.format_exc()}", run_dir))

    @staticmethod
    def _cleanup_workdir(wd: Path) -> None:
        for sub in ("raw", "bled", "op_raw", "rb_raw", "lorcana_raw", "scryfall"):
            target = wd / sub
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

    @staticmethod
    def _cleanup_run_dir(run_dir: Path) -> None:
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)

    def _drain_events(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                self._handle(ev)
        except queue.Empty:
            pass
        finally:
            self.root.after(80, self._drain_events)

    def _handle(self, ev: tuple) -> None:
        kind = ev[0]
        if kind == "file":
            _, i, n, name = ev
            self.status_var.set(f"[{i}/{n}] {name}")
        elif kind == "progress":
            _, stage, done, total, name = ev
            label = STAGE_LABELS.get(stage, stage)
            pct = (done / total * 100.0) if total else 0
            self.progress["value"] = pct
            speed_info = (
                f" — {self._dl_speed_str}" if stage == "download" and self._dl_speed_str else ""
            )
            self.status_var.set(f"{name} — {label}: {done}/{total}{speed_info}")
        elif kind == "download_speed":
            _, speed_mbps, eta_sec = ev
            mins = int(eta_sec) // 60
            secs = int(eta_sec) % 60
            eta_str = f"{mins}:{secs:02d}" if mins > 0 else f"{secs}s"
            self._dl_speed_str = f"{speed_mbps:.1f} MB/s — ETA {eta_str}"
        elif kind == "checkpoint_found":
            _, count = ev
            self.status_var.set(
                f"Se encontraron {count} imagen(es) en caché de una ejecución anterior. "
                "Retomando desde el crop."
            )
        elif kind == "partial_download_error":
            _, perm_errors, timeout_errors, xml_context, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            parts = []
            if perm_errors:
                names = ", ".join(f"«{name}»" for _, name in perm_errors[:3])
                more = f" y {len(perm_errors) - 3} más" if len(perm_errors) > 3 else ""
                parts.append(
                    f"{len(perm_errors)} imagen(es) sin permiso de descarga: {names}{more}.\n"
                    "Pide al creador del proxy que restaure los permisos de Google Drive."
                )
            if timeout_errors:
                names = ", ".join(f"«{name}»" for _, name in timeout_errors[:3])
                more = f" y {len(timeout_errors) - 3} más" if len(timeout_errors) > 3 else ""
                parts.append(
                    f"{len(timeout_errors)} imagen(es) con tiempo de espera agotado: {names}{more}.\n"
                    "Las imágenes descargadas correctamente están en caché. "
                    "Vuelve a intentarlo en unos minutos."
                )
            total_failed = len(perm_errors) + len(timeout_errors)
            self.status_var.set(f"Error: {total_failed} imagen(es) no se pudieron descargar.")
            self._finish_running()
            self._show_error_dialog("\n\n".join(parts))
        elif kind == "done":
            _, pdfs, manifest, run_dir, timing_str = ev
            self.progress["value"] = 100
            extra = f" Resumen en {manifest.name}." if manifest else ""
            self.status_var.set(f"Listo. {len(pdfs)} PDF(s) generados en {run_dir.name}.{extra}")
            if timing_str:
                self.timing_var.set(f"Tiempos — {timing_str}")
                _log.info("Phase timings: %s", timing_str)
            self._finish_running()
            notify(APP_TITLE, f"¡Listo! {len(pdfs)} PDF(s) generados correctamente.")
            self._open_output_folder(run_dir)
        elif kind == "xml_download_progress":
            _, xml_name, done, total = ev
            self._show_xml_download_progress(xml_name, done, total)
        elif kind == "xml_crop_progress":
            _, xml_name, done, total = ev
            self._show_xml_crop_progress(xml_name, done, total)
        elif kind == "verify_warning":
            _, cards, confirm_event = ev
            names = "\n".join(f"  • {name}" for _, name in cards[:8])
            more = f"\n  … y {len(cards) - 8} más" if len(cards) > 8 else ""
            msg = (
                f"{len(cards)} carta(s) sin acceso público en Google Drive:\n\n"
                f"{names}{more}\n\n"
                "El proceso fallará al intentar descargar estas cartas.\n"
                "¿Deseas continuar de todos modos?"
            )
            if not messagebox.askyesno(APP_TITLE, msg, icon=messagebox.WARNING):
                self.cancel_event.set()
            confirm_event.set()
        elif kind == "cancelled":
            _, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            self.progress["value"] = 0
            self.status_var.set(
                "Proceso detenido. Las imágenes descargadas se conservan para retomar."
            )
            self._finish_running()
        elif kind == "rate_limit_error":
            _, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            self.status_var.set("Error: demasiadas descargas en poco tiempo.")
            self._finish_running()
            self._show_error_dialog(
                "Se están intentando descargar demasiadas imágenes en poco tiempo, "
                "espera un rato y vuelve a intentar.\n\n"
                "Por favor selecciona «Guardar en el PC las imágenes entre ejecuciones» "
                "así evitamos volver a descargarlas cada vez."
            )
        elif kind == "permission_error":
            _, card_name, xml_name, position, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            parts = [f"Se ha fallado descargando «{card_name}»"]
            if xml_name:
                parts[0] += f" en el {xml_name}"
            if position:
                parts[0] += f" que está en la posición {position}."
            else:
                parts[0] += "."
            parts.append(
                "Esto no es un fallo del programa: le han quitado los permisos "
                "de acceso público a la imagen en Google Drive.\n"
                "Pide al creador del proxy que restaure los permisos."
            )
            self.status_var.set("Error de descarga.")
            self._finish_running()
            self._show_error_dialog("\n\n".join(parts))
        elif kind == "timeout_error":
            _, card_name, xml_name, position, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            parts = [f"Se ha agotado el tiempo de espera descargando «{card_name}»"]
            if xml_name:
                parts[0] += f" en el {xml_name}"
            if position:
                parts[0] += f" que está en la posición {position}."
            else:
                parts[0] += "."
            parts.append(
                "La descarga no recibió datos durante 30 segundos y se canceló.\n"
                "Puede ser un problema temporal de Google Drive o de tu conexión.\n"
                "Vuelve a intentarlo en unos minutos."
            )
            self.status_var.set("Error de descarga (tiempo agotado).")
            self._finish_running()
            self._show_error_dialog("\n\n".join(parts))
        elif kind == "op_deck_loaded":
            _, deck = ev
            if not any(d.slug == deck.slug for d in self._op_decks):
                self._op_decks.append(deck)
                self._op_refresh_rows()
                self._refresh_generate_state()
            self._op_url_var.set("")
            self._op_status_var.set(f"Añadido: {deck.name}")
            self._op_load_btn.state(["!disabled"])
        elif kind == "op_deck_error":
            _, msg = ev
            self._op_status_var.set("Error al cargar el mazo.")
            self._op_load_btn.state(["!disabled"])
            self._show_error_dialog(msg)
        elif kind == "rb_deck_loaded":
            _, deck = ev
            if not any(d.deck_id == deck.deck_id for d in self._rb_decks):
                self._rb_decks.append(deck)
                self._rb_refresh_rows()
                self._refresh_generate_state()
            self._rb_url_var.set("")
            self._rb_status_var.set(f"Añadido: {deck.name}")
            self._rb_load_btn.state(["!disabled"])
        elif kind == "rb_deck_error":
            _, msg = ev
            self._rb_status_var.set("Error al cargar el mazo.")
            self._rb_load_btn.state(["!disabled"])
            self._show_error_dialog(msg)
        elif kind == "lorcana_deck_loaded":
            _, deck = ev
            if not any(d.deck_id == deck.deck_id for d in self._lorcana_decks):
                self._lorcana_decks.append(deck)
                self._lorcana_refresh_rows()
                self._refresh_generate_state()
            self._lorcana_url_var.set("")
            self._lorcana_status_var.set(f"Añadido: {deck.name}")
            self._lorcana_load_btn.state(["!disabled"])
        elif kind == "lorcana_deck_error":
            _, msg = ev
            self._lorcana_status_var.set("Error al cargar el mazo.")
            self._lorcana_load_btn.state(["!disabled"])
            self._show_error_dialog(msg)
        elif kind == "mtg_url_loaded":
            _, url, cards, include_side, deck_name = ev
            self.state.mtg_url_decks.append(MtgUrlDeck(url, cards, include_side, name=deck_name))
            dlg = getattr(self, "_mtg_url_dialog", None)
            if dlg and dlg.winfo_exists():
                dlg.destroy()
            self._mtg_url_dialog = None
            self._refresh_xml_rows()
            self._refresh_generate_state()
        elif kind == "mtg_url_error":
            _, msg = ev
            status_var = getattr(self, "_mtg_url_status_var", None)
            import_btn = getattr(self, "_mtg_import_btn", None)
            if status_var:
                status_var.set(f"✗ {msg}")
            if import_btn:
                try:
                    import_btn.state(["!disabled"])
                except Exception:
                    pass
        elif kind == "error":
            _, msg, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            self.status_var.set("Error durante la generación. Las imágenes en caché se conservan.")
            self._finish_running()
            self._show_error_dialog(msg)

    def _show_error_dialog(self, message: str) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title(f"{APP_TITLE} — Error")
        dlg.geometry("600x340")
        dlg.resizable(True, True)
        dlg.grab_set()

        ttk.Label(dlg, text="Error", font=("Segoe UI", 11, "bold"), foreground="#cc0000").pack(
            anchor="w", padx=12, pady=(10, 4)
        )

        frame = ttk.Frame(dlg)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        txt = tk.Text(
            frame,
            wrap=tk.WORD,
            relief=tk.SUNKEN,
            borderwidth=1,
            font=("Consolas", 9),
            state=tk.NORMAL,
        )
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        txt.insert("1.0", message)
        txt.configure(state=tk.DISABLED)
        attach_context_menu(txt)

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=12, pady=(0, 10))

        def _copy():
            dlg.clipboard_clear()
            dlg.clipboard_append(message)
            copy_btn.configure(text="✓ Copiado")
            dlg.after(2000, lambda: copy_btn.configure(text="Copiar al portapapeles"))

        copy_btn = ttk.Button(btn_row, text="Copiar al portapapeles", command=_copy)
        copy_btn.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Cerrar", command=dlg.destroy).pack(side=tk.RIGHT)

    def _finish_running(self) -> None:
        self.running = False
        self.worker = None
        self.stop_btn.pack_forget()
        self.stop_btn.state(["!disabled"])
        self._refresh_generate_state()

    def _open_output_folder(self, path: Path) -> None:
        try:
            os.startfile(str(path))
        except AttributeError:
            import subprocess

            opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
            subprocess.Popen([opener, str(path)])


def _setup_logging() -> None:
    if getattr(sys, "frozen", False):
        try:
            from gui._build_flags import DEBUG_LOGGING
        except ImportError:
            DEBUG_LOGGING = False
        if not DEBUG_LOGGING:
            return
    wd = work_dir()
    wd.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[logging.FileHandler(wd / "gui.log", encoding="utf-8")],
    )


def main() -> None:
    _setup_logging()
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
