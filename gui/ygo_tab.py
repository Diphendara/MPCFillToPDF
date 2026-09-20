"""Yu-Gi-Oh! tab methods for the App class."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from gui.widgets import APP_TITLE, attach_context_menu, ellipsize
from src.ygo_scraper import scrape_deck as ygo_scrape_deck


class YGOTabMixin:
    def _build_yugioh_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        url_row = ttk.Frame(parent)
        url_row.grid(row=0, column=0, sticky="ew", padx=6, pady=(10, 4))
        url_row.columnconfigure(1, weight=1)
        ttk.Label(
            url_row,
            text="Pega YDKE o una URL de YGOPRODeck, Master Duel Meta, Yu-Gi-Oh! Meta o Edison.",
            foreground="#999",
            font=("Segoe UI", 8),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(url_row, text="Mazo:").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self._ygo_url_var = tk.StringVar()
        entry = ttk.Entry(url_row, textvariable=self._ygo_url_var)
        entry.grid(row=1, column=1, sticky="ew")
        entry.bind("<Return>", lambda _event: self._ygo_load_deck())
        attach_context_menu(entry)
        self._ygo_load_btn = ttk.Button(
            url_row, text="Añadir", width=7, command=self._ygo_load_deck
        )
        self._ygo_load_btn.grid(row=1, column=2, padx=(6, 0))
        self._ygo_status_var = tk.StringVar()
        ttk.Label(url_row, textvariable=self._ygo_status_var, foreground="#555").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(2, 0)
        )

        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 2))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self._ygo_canvas, self._ygo_inner, _ = self._build_scrollable_rows(list_frame)
        self._ygo_canvas.bind(
            "<Enter>", lambda _event: self._bind_mousewheel(self._ygo_canvas, True)
        )
        self._ygo_canvas.bind(
            "<Leave>", lambda _event: self._bind_mousewheel(self._ygo_canvas, False)
        )
        self._ygo_empty_label = ttk.Label(
            self._ygo_inner,
            text="(añade un mazo Yu-Gi-Oh! para imprimirlo en su rejilla específica)",
            foreground="#777",
            padding=(8, 10),
        )
        self._ygo_empty_label.pack(anchor="w")
        ttk.Button(parent, text="Vaciar todo", command=self._ygo_clear).grid(
            row=2, column=0, sticky="w", padx=6, pady=(2, 6)
        )

    def _ygo_load_deck(self) -> None:
        value = self._ygo_url_var.get().strip()
        if not value:
            messagebox.showwarning(APP_TITLE, "Introduce una URL compatible o una cadena YDKE.")
            return
        self._ygo_load_btn.state(["disabled"])
        self._ygo_status_var.set("Cargando mazo…")

        def _fetch() -> None:
            try:
                self.events.put(("ygo_deck_loaded", ygo_scrape_deck(value)))
            except Exception as exc:
                self.events.put(("ygo_deck_error", str(exc)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _ygo_refresh_rows(self) -> None:
        for row in self._ygo_deck_rows:
            row["outer"].destroy()
        self._ygo_deck_rows.clear()
        if not self._ygo_decks:
            self._ygo_empty_label.pack(anchor="w")
            return
        self._ygo_empty_label.pack_forget()
        for idx, deck in enumerate(self._ygo_decks):
            outer = ttk.Frame(self._ygo_inner, relief="groove", borderwidth=1)
            outer.pack(fill=tk.X, padx=2, pady=3)
            summary = ttk.Frame(outer)
            summary.pack(fill=tk.X, padx=6, pady=4)
            ttk.Label(summary, text=ellipsize(deck.name, 28), font=("Segoe UI", 9, "bold")).pack(
                side=tk.LEFT
            )
            include_side = tk.BooleanVar(value=False)
            side_label = f"Incluir Side ({deck.side_slots})" if deck.side_slots else "Sin Side Deck"
            ttk.Checkbutton(
                summary,
                text=side_label,
                variable=include_side,
                state=tk.NORMAL if deck.side_slots else tk.DISABLED,
            ).pack(side=tk.RIGHT)
            ttk.Button(
                summary, text="✕", width=2, command=lambda i=idx: self._ygo_remove_deck(i)
            ).pack(side=tk.RIGHT, padx=(0, 5))
            ttk.Label(summary, text=f"{deck.total_slots()} Main/Extra", foreground="#888").pack(
                side=tk.RIGHT, padx=(0, 8)
            )
            self._ygo_deck_rows.append({"outer": outer, "include_side_var": include_side})
        self._ygo_inner.update_idletasks()
        self._ygo_canvas.configure(scrollregion=self._ygo_canvas.bbox("all"))

    def _ygo_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._ygo_decks):
            del self._ygo_decks[idx]
            self._ygo_refresh_rows()
            self._refresh_generate_state()

    def _ygo_clear(self) -> None:
        self._ygo_decks.clear()
        self._ygo_url_var.set("")
        self._ygo_status_var.set("")
        self._ygo_load_btn.state(["!disabled"])
        self._ygo_refresh_rows()
        self._refresh_generate_state()
