"""LorcanaTabMixin — Lorcana tab methods for the App class."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from gui.widgets import APP_TITLE, attach_context_menu, ellipsize
from src.lorcana_scraper import scrape_deck as lorcana_scrape_deck


class LorcanaTabMixin:
    """Methods for the Lorcana scraper tab."""

    def _build_lorcana_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        url_row = ttk.Frame(parent)
        url_row.grid(row=0, column=0, sticky="ew", padx=6, pady=(10, 4))
        url_row.columnconfigure(1, weight=1)
        ttk.Label(
            url_row,
            text="Webs aceptadas: lorcana.gg, inkdecks.com, dreamborn.ink",
            foreground="#999",
            font=("Segoe UI", 8),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(url_row, text="URL del mazo:").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self._lorcana_url_var = tk.StringVar()
        self._lorcana_url_entry = ttk.Entry(url_row, textvariable=self._lorcana_url_var)
        self._lorcana_url_entry.grid(row=1, column=1, sticky="ew")
        self._lorcana_url_entry.bind("<Return>", lambda _e: self._lorcana_load_deck())
        attach_context_menu(self._lorcana_url_entry)
        self._lorcana_load_btn = ttk.Button(
            url_row, text="Añadir", width=7, command=self._lorcana_load_deck
        )
        self._lorcana_load_btn.grid(row=1, column=2, padx=(6, 0))

        self._lorcana_status_var = tk.StringVar(value="")
        ttk.Label(
            url_row, textvariable=self._lorcana_status_var, foreground="#555", anchor="w"
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(2, 0))

        lorcana_list_frame = ttk.Frame(parent)
        lorcana_list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 2))
        lorcana_list_frame.columnconfigure(0, weight=1)
        lorcana_list_frame.rowconfigure(0, weight=1)

        self._lorcana_canvas, self._lorcana_inner, _ = self._build_scrollable_rows(
            lorcana_list_frame
        )
        self._lorcana_canvas.bind(
            "<Enter>", lambda _e: self._bind_mousewheel(self._lorcana_canvas, True)
        )
        self._lorcana_canvas.bind(
            "<Leave>", lambda _e: self._bind_mousewheel(self._lorcana_canvas, False)
        )

        self._lorcana_empty_label = ttk.Label(
            self._lorcana_inner,
            text="(introduce una URL de lorcana.gg, inkdecks.com o dreamborn.ink)",
            foreground="#777",
            padding=(8, 10),
        )
        self._lorcana_empty_label.pack(anchor="w")

        lorcana_btn_row = ttk.Frame(parent)
        lorcana_btn_row.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 6))
        ttk.Button(lorcana_btn_row, text="Vaciar todo", command=self._lorcana_clear).pack(
            side=tk.LEFT
        )

    def _lorcana_load_deck(self) -> None:
        url = self._lorcana_url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Introduce una URL de mazo de Lorcana.")
            return

        self._lorcana_load_btn.state(["disabled"])
        self._lorcana_status_var.set("Cargando mazo…")

        def _fetch():
            try:
                deck = lorcana_scrape_deck(url)
                self.events.put(("lorcana_deck_loaded", deck))
            except Exception as e:
                self.events.put(("lorcana_deck_error", str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _lorcana_refresh_rows(self) -> None:
        for row in self._lorcana_deck_rows:
            row["outer"].destroy()
        self._lorcana_deck_rows.clear()

        if not self._lorcana_decks:
            self._lorcana_empty_label.pack(anchor="w")
            return
        self._lorcana_empty_label.pack_forget()

        source_labels = {
            "lorcana_gg": "lorcana.gg",
            "inkdecks": "inkdecks.com",
            "dreamborn": "dreamborn.ink",
        }

        for idx, deck in enumerate(self._lorcana_decks):
            outer = ttk.Frame(self._lorcana_inner, relief="groove", borderwidth=1)
            outer.pack(fill=tk.X, pady=3, padx=2)
            outer.columnconfigure(0, weight=1)

            summary = ttk.Frame(outer)
            summary.pack(fill=tk.X, padx=6, pady=4)
            summary.columnconfigure(1, weight=1)

            ttk.Label(
                summary,
                text=ellipsize(deck.name, 28),
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(0, 12))

            source_txt = source_labels.get(deck.source, deck.source)
            ttk.Label(
                summary,
                text=source_txt,
                foreground="#555",
                anchor="w",
                font=("Segoe UI", 8),
            ).grid(row=0, column=1, sticky="w")

            ttk.Label(
                summary,
                text=f"{deck.total_slots} cartas",
                foreground="#888",
                anchor="e",
            ).grid(row=0, column=2, sticky="e", padx=(8, 6))

            expanded_var = tk.BooleanVar(value=False)
            toggle_btn = ttk.Button(
                summary,
                text="Detalles ▼",
                width=10,
                command=lambda i=idx: self._lorcana_toggle_details(i),
            )
            toggle_btn.grid(row=0, column=3, padx=(0, 4))

            ttk.Button(
                summary,
                text="✕",
                width=2,
                command=lambda i=idx: self._lorcana_remove_deck(i),
            ).grid(row=0, column=4)

            detail = ttk.Frame(outer)

            for card in deck.cards:
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
                ttk.Label(
                    row_f,
                    text=ellipsize(card.name, 30),
                    anchor="w",
                    width=31,
                ).pack(side=tk.LEFT)
                ttk.Label(
                    row_f,
                    text=card.card_id,
                    foreground="#888",
                    font=("Segoe UI", 8),
                    anchor="w",
                    width=10,
                ).pack(side=tk.LEFT, padx=(4, 0))

            self._lorcana_deck_rows.append(
                {
                    "outer": outer,
                    "detail": detail,
                    "toggle_btn": toggle_btn,
                    "expanded": expanded_var,
                    "deck": deck,
                }
            )

        self._lorcana_inner.update_idletasks()
        self._lorcana_canvas.configure(scrollregion=self._lorcana_canvas.bbox("all"))

    def _lorcana_toggle_details(self, idx: int) -> None:
        if idx >= len(self._lorcana_deck_rows):
            return
        row = self._lorcana_deck_rows[idx]
        expanded = row["expanded"]
        if expanded.get():
            row["detail"].pack_forget()
            row["toggle_btn"].configure(text="Detalles ▼")
            expanded.set(False)
        else:
            row["detail"].pack(fill=tk.X, padx=0, pady=(0, 4))
            row["toggle_btn"].configure(text="Detalles ▲")
            expanded.set(True)
        self._lorcana_inner.update_idletasks()
        self._lorcana_canvas.configure(scrollregion=self._lorcana_canvas.bbox("all"))

    def _lorcana_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._lorcana_decks):
            del self._lorcana_decks[idx]
            self._lorcana_refresh_rows()
            self._refresh_generate_state()

    def _lorcana_clear(self) -> None:
        self._lorcana_decks.clear()
        self._lorcana_url_var.set("")
        self._lorcana_status_var.set("")
        self._lorcana_load_btn.state(["!disabled"])
        self._lorcana_refresh_rows()
        self._refresh_generate_state()
