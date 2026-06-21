"""OPTabMixin — One Piece tab methods for the App class."""

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
from src.op_scraper import download_images as op_download
from src.op_scraper import expand_deck as op_expand
from src.op_scraper import get_op_backs
from src.op_scraper import scrape_deck as op_scrape_deck
from src.pipeline import run_locals_only


class OPTabMixin:
    """Methods for the One Piece scraper tab."""

    def _build_onepiece_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        url_row = ttk.Frame(parent)
        url_row.grid(row=0, column=0, sticky="ew", padx=6, pady=(10, 4))
        url_row.columnconfigure(1, weight=1)
        ttk.Label(
            url_row,
            text="Webs aceptadas: onepiece.gg, egmanevents.com, cardkaizoku.com",
            foreground="#999",
            font=("Segoe UI", 8),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(url_row, text="URL del mazo:").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self._op_url_var = tk.StringVar()
        self._op_url_entry = ttk.Entry(url_row, textvariable=self._op_url_var)
        self._op_url_entry.grid(row=1, column=1, sticky="ew")
        self._op_url_entry.bind("<Return>", lambda _e: self._op_load_deck())
        attach_context_menu(self._op_url_entry)
        self._op_load_btn = ttk.Button(url_row, text="Añadir", width=7, command=self._op_load_deck)
        self._op_load_btn.grid(row=1, column=2, padx=(6, 0))

        self._op_status_var = tk.StringVar(value="")
        ttk.Label(url_row, textvariable=self._op_status_var, foreground="#555", anchor="w").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(2, 0)
        )

        op_list_frame = ttk.Frame(parent)
        op_list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 2))
        op_list_frame.columnconfigure(0, weight=1)
        op_list_frame.rowconfigure(0, weight=1)

        self._op_canvas, self._op_inner, _ = self._build_scrollable_rows(op_list_frame)
        self._op_canvas.bind("<Enter>", lambda _e: self._bind_mousewheel(self._op_canvas, True))
        self._op_canvas.bind("<Leave>", lambda _e: self._bind_mousewheel(self._op_canvas, False))

        self._op_empty_label = ttk.Label(
            self._op_inner,
            text="(introduce una URL de mazo y haz clic en «Añadir»)",
            foreground="#777",
            padding=(8, 10),
        )
        self._op_empty_label.pack(anchor="w")

        op_btn_row = ttk.Frame(parent)
        op_btn_row.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 6))
        ttk.Button(op_btn_row, text="Vaciar todo", command=self._op_clear).pack(side=tk.LEFT)

    def _op_load_deck(self) -> None:
        url = self._op_url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Introduce una URL de mazo de One Piece.")
            return

        self._op_load_btn.state(["disabled"])
        self._op_status_var.set("Cargando mazo…")

        def _fetch():
            try:
                deck = op_scrape_deck(url)
                self.events.put(("op_deck_loaded", deck))
            except Exception as e:
                self.events.put(("op_deck_error", str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _op_refresh_rows(self) -> None:
        for row in self._op_deck_rows:
            row["outer"].destroy()
        self._op_deck_rows.clear()

        if not self._op_decks:
            self._op_empty_label.pack(anchor="w")
            return
        self._op_empty_label.pack_forget()

        for idx, deck in enumerate(self._op_decks):
            leader = deck.leader

            outer = ttk.Frame(self._op_inner, relief="groove", borderwidth=1)
            outer.pack(fill=tk.X, pady=3, padx=2)
            outer.columnconfigure(0, weight=1)

            summary = ttk.Frame(outer)
            summary.pack(fill=tk.X, padx=6, pady=4)
            summary.columnconfigure(1, weight=1)

            ttk.Label(
                summary, text=ellipsize(deck.name, 22), font=("Segoe UI", 9, "bold"), anchor="w"
            ).grid(row=0, column=0, sticky="w", padx=(0, 12))

            if leader:
                color_txt = " / ".join(leader.colors)
                leader_txt = f"Líder: {ellipsize(leader.name, 18)}  ({color_txt})"
            else:
                leader_txt = "(sin líder)"
            ttk.Label(summary, text=leader_txt, foreground="#555", anchor="w").grid(
                row=0, column=1, sticky="w"
            )

            ttk.Label(
                summary, text=f"{deck.total_slots} cartas", foreground="#888", anchor="e"
            ).grid(row=0, column=2, sticky="e", padx=(8, 6))

            expanded_var = tk.BooleanVar(value=False)
            toggle_btn = ttk.Button(
                summary,
                text="Detalles ▼",
                width=10,
                command=lambda i=idx: self._op_toggle_details(i),
            )
            toggle_btn.grid(row=0, column=3, padx=(0, 4))

            ttk.Button(
                summary,
                text="✕",
                width=2,
                command=lambda i=idx: self._op_remove_deck(i),
            ).grid(row=0, column=4)

            detail = ttk.Frame(outer)

            for card in deck.cards:
                row_f = ttk.Frame(detail)
                row_f.pack(fill=tk.X, pady=0, padx=(12, 4))

                if card.is_leader:
                    badge_text, badge_fg = "LÍDER", "#1565C0"
                    badge_font = ("Segoe UI", 8, "bold")
                else:
                    badge_text, badge_fg = f"x{card.quantity}", "#444"
                    badge_font = ("Segoe UI", 8)
                ttk.Label(
                    row_f,
                    text=badge_text,
                    foreground=badge_fg,
                    font=badge_font,
                    width=6,
                    anchor="e",
                ).pack(side=tk.LEFT, padx=(0, 6))
                ttk.Label(row_f, text=ellipsize(card.name, 24), anchor="w", width=25).pack(
                    side=tk.LEFT
                )
                ttk.Label(
                    row_f,
                    text=card.card_id,
                    foreground="#888",
                    font=("Segoe UI", 8),
                    anchor="w",
                    width=10,
                ).pack(side=tk.LEFT, padx=(4, 0))
                if card.colors:
                    ttk.Label(
                        row_f, text=" / ".join(card.colors), foreground="#555", font=("Segoe UI", 8)
                    ).pack(side=tk.LEFT, padx=(6, 0))

            self._op_deck_rows.append(
                {
                    "outer": outer,
                    "detail": detail,
                    "toggle_btn": toggle_btn,
                    "expanded": expanded_var,
                    "deck": deck,
                }
            )

        self._op_inner.update_idletasks()
        self._op_canvas.configure(scrollregion=self._op_canvas.bbox("all"))

    def _op_toggle_details(self, idx: int) -> None:
        if idx >= len(self._op_deck_rows):
            return
        row = self._op_deck_rows[idx]
        expanded = row["expanded"]
        if expanded.get():
            row["detail"].pack_forget()
            row["toggle_btn"].configure(text="Detalles ▼")
            expanded.set(False)
        else:
            row["detail"].pack(fill=tk.X, padx=0, pady=(0, 4))
            row["toggle_btn"].configure(text="Detalles ▲")
            expanded.set(True)
        self._op_inner.update_idletasks()
        self._op_canvas.configure(scrollregion=self._op_canvas.bbox("all"))

    def _op_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._op_decks):
            del self._op_decks[idx]
            self._op_refresh_rows()
            self._refresh_generate_state()

    def _op_clear(self) -> None:
        self._op_decks.clear()
        self._op_url_var.set("")
        self._op_status_var.set("")
        self._op_load_btn.state(["!disabled"])
        self._op_refresh_rows()
        self._refresh_generate_state()

    def _start_op(self, fronts_only: bool = False) -> None:
        self.running = True
        self.cancel_event.clear()
        self._dl_speed_str = ""
        self.timing_var.set("")
        self.soriano_btn.state(["disabled"])
        self.fronts_only_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.stop_btn.pack(fill=tk.X, pady=(4, 0), after=self.fronts_only_btn)
        self.progress["value"] = 0
        self.status_var.set("Preparando One Piece…")
        self.worker = threading.Thread(
            target=self._work_op,
            args=(fronts_only,),
            daemon=True,
        )
        self.worker.start()

    def _work_op(self, fronts_only: bool = False) -> None:
        run_dir = None
        try:
            decks = self._op_decks
            if not decks:
                raise ValueError("No hay mazos de One Piece cargados.")

            out = self._effective_output_dir()
            wd = work_dir()
            run_dir = out / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
            run_dir.mkdir(parents=True, exist_ok=True)

            _run_start = time.time()
            label = " + ".join(d.name for d in decks)

            op_raw_dir = wd / "op_raw"
            total_unique = sum(len({c.card_id for c in d.cards}) for d in decks)
            self.events.put(("progress", "download", 0, total_unique, label))

            image_map: dict[str, Path] = {}
            done_dl_offset = 0

            for deck in decks:
                _offset = done_dl_offset

                def _dl_progress(done, total, _off=_offset):
                    self.events.put(("progress", "download", _off + done, total_unique, label))

                partial = op_download(
                    deck,
                    op_raw_dir,
                    cancel_event=self.cancel_event,
                    progress_cb=_dl_progress,
                )
                image_map.update(partial)
                done_dl_offset += len({c.card_id for c in deck.cards})

                if self.cancel_event.is_set():
                    self.events.put(("cancelled", run_dir))
                    return

            standard_back, leader_back_res = get_op_backs()

            leader_backs: dict[str, Path] = {}
            for deck in decks:
                leader = deck.leader
                if leader and leader.card_id not in leader_backs:
                    leader_backs[leader.card_id] = leader_back_res

            all_fronts: list[Path] = []
            all_backs: list[Path | None] = []
            for deck in decks:
                leader = deck.leader
                lb = leader_backs.get(leader.card_id) if leader else None
                fronts, backs = op_expand(deck, image_map, lb, standard_back)
                all_fronts.extend(fronts)
                all_backs.extend(backs)

            if not all_fronts:
                raise ValueError("No se pudieron expandir las cartas.")

            all_back_paths = {standard_back} | set(leader_backs.values())
            crop_map = {p: False for p in set(all_fronts) | all_back_paths}

            base_name = "_".join(d.slug for d in decks)[:60]
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
                standard_back,
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
