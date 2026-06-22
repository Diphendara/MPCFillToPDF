"""RBTabMixin — Riftbound tab methods for the App class."""

from __future__ import annotations

import threading
import time
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from gui.paths import work_dir
from gui.widgets import APP_TITLE, attach_context_menu, ellipsize
from src.pipeline import run_locals_only
from src.rb_scraper import download_images as rb_download
from src.rb_scraper import expand_deck as rb_expand
from src.rb_scraper import get_rb_backs
from src.rb_scraper import scrape_deck as rb_scrape_deck

_SECTION_LABELS = {
    "legend": "Leyenda",
    "champion": "Campeón",
    "battlefield": "Campo de batalla",
    "rune": "Runa",
    "maindeck": "Mazo principal",
    "sideboard": "Sideboard",
}


class RBTabMixin:
    """Methods for the Riftbound scraper tab."""

    def _build_riftbound_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        url_row = ttk.Frame(parent)
        url_row.grid(row=0, column=0, sticky="ew", padx=6, pady=(10, 4))
        url_row.columnconfigure(1, weight=1)
        ttk.Label(
            url_row,
            text="Webs aceptadas: piltoverarchive.com, riftbound.gg, riftmana.com, riftbinder.com, riftdex.com",
            foreground="#999",
            font=("Segoe UI", 8),
            wraplength=450,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(url_row, text="URL del mazo:").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self._rb_url_var = tk.StringVar()
        self._rb_url_entry = ttk.Entry(url_row, textvariable=self._rb_url_var)
        self._rb_url_entry.grid(row=1, column=1, sticky="ew")
        self._rb_url_entry.bind("<Return>", lambda _e: self._rb_load_deck())
        attach_context_menu(self._rb_url_entry)
        self._rb_load_btn = ttk.Button(url_row, text="Añadir", width=7, command=self._rb_load_deck)
        self._rb_load_btn.grid(row=1, column=2, padx=(6, 0))

        self._rb_status_var = tk.StringVar(value="")
        ttk.Label(url_row, textvariable=self._rb_status_var, foreground="#555", anchor="w").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(2, 0)
        )

        rb_list_frame = ttk.Frame(parent)
        rb_list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 2))
        rb_list_frame.columnconfigure(0, weight=1)
        rb_list_frame.rowconfigure(0, weight=1)

        self._rb_canvas, self._rb_inner, _ = self._build_scrollable_rows(rb_list_frame)
        self._rb_canvas.bind("<Enter>", lambda _e: self._bind_mousewheel(self._rb_canvas, True))
        self._rb_canvas.bind("<Leave>", lambda _e: self._bind_mousewheel(self._rb_canvas, False))

        self._rb_empty_label = ttk.Label(
            self._rb_inner,
            text="(introduce una URL de piltoverarchive.com, riftbound.gg, riftmana.com, riftbinder.com o riftdex.com)",
            foreground="#777",
            padding=(8, 10),
        )
        self._rb_empty_label.pack(anchor="w")

        rb_btn_row = ttk.Frame(parent)
        rb_btn_row.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 6))
        ttk.Button(rb_btn_row, text="Vaciar todo", command=self._rb_clear).pack(side=tk.LEFT)

    def _rb_load_deck(self) -> None:
        url = self._rb_url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Introduce una URL de mazo de Riftbound.")
            return

        self._rb_load_btn.state(["disabled"])
        self._rb_status_var.set("Cargando mazo…")

        def _fetch():
            try:
                deck = rb_scrape_deck(url)
                self.events.put(("rb_deck_loaded", deck))
            except Exception as e:
                self.events.put(("rb_deck_error", str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _rb_refresh_rows(self) -> None:
        for row in self._rb_deck_rows:
            row["outer"].destroy()
        self._rb_deck_rows.clear()

        if not self._rb_decks:
            self._rb_empty_label.pack(anchor="w")
            return
        self._rb_empty_label.pack_forget()

        for idx, deck in enumerate(self._rb_decks):
            outer = ttk.Frame(self._rb_inner, relief="groove", borderwidth=1)
            outer.pack(fill=tk.X, pady=3, padx=2)
            outer.columnconfigure(0, weight=1)

            summary = ttk.Frame(outer)
            summary.pack(fill=tk.X, padx=6, pady=4)
            summary.columnconfigure(1, weight=1)

            ttk.Label(
                summary, text=ellipsize(deck.name, 28), font=("Segoe UI", 9, "bold"), anchor="w"
            ).grid(row=0, column=0, sticky="w", padx=(0, 12))

            by_sec = deck.by_section()
            sec_parts = [
                f"{_SECTION_LABELS.get(s, s)}: {sum(c.quantity for c in cards)}"
                for s, cards in by_sec.items()
                if cards
            ]
            ttk.Label(
                summary,
                text="  |  ".join(sec_parts),
                foreground="#555",
                anchor="w",
                font=("Segoe UI", 8),
            ).grid(row=0, column=1, sticky="w")

            ttk.Label(
                summary, text=f"{deck.total_slots} cartas", foreground="#888", anchor="e"
            ).grid(row=0, column=2, sticky="e", padx=(8, 6))

            print_runes_var = tk.BooleanVar(value=True)
            has_runes = bool(by_sec.get("rune"))
            runes_cb = ttk.Checkbutton(
                summary,
                text="imprimir runas",
                variable=print_runes_var,
            )
            if not has_runes:
                runes_cb.state(["disabled"])
            runes_cb.grid(row=0, column=3, padx=(4, 8))

            expanded_var = tk.BooleanVar(value=False)
            toggle_btn = ttk.Button(
                summary,
                text="Detalles ▼",
                width=10,
                command=lambda i=idx: self._rb_toggle_details(i),
            )
            toggle_btn.grid(row=0, column=4, padx=(0, 4))

            ttk.Button(
                summary,
                text="✕",
                width=2,
                command=lambda i=idx: self._rb_remove_deck(i),
            ).grid(row=0, column=5)

            detail = ttk.Frame(outer)

            for section, cards in by_sec.items():
                if not cards:
                    continue
                sec_lbl = _SECTION_LABELS.get(section, section)
                ttk.Label(
                    detail,
                    text=f"── {sec_lbl} ──",
                    foreground="#888",
                    font=("Segoe UI", 8, "italic"),
                    padding=(12, 2, 0, 0),
                ).pack(anchor="w")
                for card in cards:
                    row_f = ttk.Frame(detail)
                    row_f.pack(fill=tk.X, pady=0, padx=(12, 4))
                    ttk.Label(
                        row_f,
                        text=f"x{card.quantity}",
                        foreground="#444",
                        font=("Segoe UI", 8),
                        width=4,
                        anchor="e",
                    ).pack(side=tk.LEFT, padx=(0, 6))
                    ttk.Label(row_f, text=ellipsize(card.name, 26), anchor="w", width=27).pack(
                        side=tk.LEFT
                    )
                    ttk.Label(
                        row_f,
                        text=card.card_type,
                        foreground="#888",
                        font=("Segoe UI", 8),
                        anchor="w",
                        width=12,
                    ).pack(side=tk.LEFT, padx=(4, 0))

            self._rb_deck_rows.append(
                {
                    "outer": outer,
                    "detail": detail,
                    "toggle_btn": toggle_btn,
                    "expanded": expanded_var,
                    "deck": deck,
                    "print_runes_var": print_runes_var,
                }
            )

        self._rb_inner.update_idletasks()
        self._rb_canvas.configure(scrollregion=self._rb_canvas.bbox("all"))

    def _rb_toggle_details(self, idx: int) -> None:
        if idx >= len(self._rb_deck_rows):
            return
        row = self._rb_deck_rows[idx]
        expanded = row["expanded"]
        if expanded.get():
            row["detail"].pack_forget()
            row["toggle_btn"].configure(text="Detalles ▼")
            expanded.set(False)
        else:
            row["detail"].pack(fill=tk.X, padx=0, pady=(0, 4))
            row["toggle_btn"].configure(text="Detalles ▲")
            expanded.set(True)
        self._rb_inner.update_idletasks()
        self._rb_canvas.configure(scrollregion=self._rb_canvas.bbox("all"))

    def _rb_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._rb_decks):
            del self._rb_decks[idx]
            self._rb_refresh_rows()
            self._refresh_generate_state()

    def _rb_clear(self) -> None:
        self._rb_decks.clear()
        self._rb_url_var.set("")
        self._rb_status_var.set("")
        self._rb_load_btn.state(["!disabled"])
        self._rb_refresh_rows()
        self._refresh_generate_state()

    def _start_rb(self, fronts_only: bool = False) -> None:
        print_runes_flags = [row["print_runes_var"].get() for row in self._rb_deck_rows]
        self.running = True
        self.cancel_event.clear()
        self._dl_speed_str = ""
        self.timing_var.set("")
        self.soriano_btn.state(["disabled"])
        self.fronts_only_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.stop_btn.pack(fill=tk.X, pady=(4, 0), after=self.fronts_only_btn)
        self.progress["value"] = 0
        self.status_var.set("Preparando Riftbound…")
        self.worker = threading.Thread(
            target=self._work_rb,
            args=(fronts_only, print_runes_flags),
            daemon=True,
        )
        self.worker.start()

    def _work_rb(
        self, fronts_only: bool = False, print_runes_flags: list[bool] | None = None
    ) -> None:
        run_dir = None
        try:
            decks = self._rb_decks
            if not decks:
                raise ValueError("No hay mazos de Riftbound cargados.")

            out = self._effective_output_dir()
            wd = work_dir()
            run_dir = out / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
            run_dir.mkdir(parents=True, exist_ok=True)

            _run_start = time.time()
            label = " + ".join(d.name for d in decks)

            rb_raw_dir = wd / "rb_raw"
            total_unique = sum(len({c.variant_id for c in d.cards}) for d in decks)
            self.events.put(("progress", "download", 0, total_unique, label))

            image_map: dict[str, Path] = {}
            done_dl_offset = 0

            for deck in decks:
                _offset = done_dl_offset

                def _dl_progress(done, total, _off=_offset):
                    self.events.put(("progress", "download", _off + done, total_unique, label))

                partial = rb_download(
                    deck,
                    rb_raw_dir,
                    cancel_event=self.cancel_event,
                    progress_cb=_dl_progress,
                )
                image_map.update(partial)
                done_dl_offset += len({c.variant_id for c in deck.cards})

                if self.cancel_event.is_set():
                    self.events.put(("cancelled", run_dir))
                    return

            backs = get_rb_backs()

            all_fronts: list[Path] = []
            all_backs: list[Path | None] = []
            for idx, deck in enumerate(decks):
                include_runes = (
                    print_runes_flags[idx]
                    if print_runes_flags and idx < len(print_runes_flags)
                    else True
                )
                fronts, per_backs = rb_expand(deck, image_map, backs, include_runes=include_runes)
                all_fronts.extend(fronts)
                all_backs.extend(per_backs)

            if not all_fronts:
                raise ValueError("No se pudieron expandir las cartas.")

            default_back = backs.get("maindeck") or next(iter(backs.values()))
            all_back_paths = set(backs.values())
            crop_map = {p: False for p in set(all_fronts) | all_back_paths}

            base_name = "_".join(d.deck_id[:8] for d in decks)[:60]
            self.events.put(("file", 1, 1, label))

            _phase_first: dict[str, float] = {}
            _phase_done: dict[str, float] = {}

            def cb(stage, done, total):
                now = time.time()
                if stage not in _phase_first:
                    _phase_first[stage] = now
                if done == total and total > 0:
                    _phase_done[stage] = now
                self.events.put(("progress", stage, done, total, label))

            pdfs = run_locals_only(
                all_fronts,
                default_back,
                run_dir,
                base_name,
                wd,
                cb,
                cancel_event=self.cancel_event,
                extra_backs=all_backs,
                local_crop_map=crop_map,
                fronts_only=fronts_only,
            )

            def _fmt_dur(sec: float) -> str:
                return f"{int(sec) // 60}m {int(sec) % 60}s" if sec >= 60 else f"{sec:.0f}s"

            timing_parts = []
            for stage in ("download", "crop", "pdf"):
                if stage in _phase_first and stage in _phase_done:
                    dur = _phase_done[stage] - _phase_first[stage]
                    lbl = {"download": "Descarga", "crop": "Recorte", "pdf": "PDF"}.get(
                        stage, stage
                    )
                    timing_parts.append(f"{lbl}: {_fmt_dur(dur)}")
            total_dur = time.time() - _run_start
            timing_str = "  ".join(timing_parts)
            if timing_str:
                timing_str += f"  Total: {_fmt_dur(total_dur)}"

            self.events.put(("done", pdfs, None, run_dir, timing_str))

        except Exception as e:
            self.events.put(("error", f"{e}\n\n{traceback.format_exc()}", run_dir))
