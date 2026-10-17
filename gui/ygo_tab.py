"""Yu-Gi-Oh! tab methods for the App class."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from gui.widgets import APP_TITLE, attach_context_menu, ellipsize
from src.ygo_scraper import scrape_deck as ygo_scrape_deck
from src.text_importer import parse_ygo_text, TextImportError


class YGOTabMixin:
    def _build_yugioh_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
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

        # Text import button
        text_import_row = ttk.Frame(parent)
        text_import_row.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 4))
        text_import_row.columnconfigure(0, weight=1)

        ttk.Label(
            text_import_row,
            text="ó",
            foreground="#999",
            font=("Segoe UI", 9),
        ).grid(row=0, column=0, pady=(0, 4))

        self._ygo_import_text_btn = ttk.Button(
            text_import_row,
            text="📋 Añadir desde texto",
            command=self._ygo_show_text_import_dialog,
            width=25
        )
        self._ygo_import_text_btn.grid(row=1, column=0)

        list_frame = ttk.Frame(parent)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 2))
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
            detail = ttk.Frame(outer)
            expanded = tk.BooleanVar(value=False)
            selected_ids = getattr(deck, "selected_card_ids", {card.card_id for card in deck.cards})
            card_vars: dict[int, tk.BooleanVar] = {}

            def _sync_selection(d=deck, vars=card_vars) -> None:
                d.selected_card_ids = {card_id for card_id, var in vars.items() if var.get()}
                self._refresh_generate_state()

            for card in sorted(deck.cards, key=lambda c: c.name.casefold()):
                row = ttk.Frame(detail)
                row.pack(fill=tk.X, padx=(12, 4))
                card_vars[card.card_id] = tk.BooleanVar(value=card.card_id in selected_ids)
                ttk.Checkbutton(
                    row, variable=card_vars[card.card_id], command=_sync_selection
                ).pack(side=tk.LEFT)
                ttk.Label(row, text=f"x{card.quantity}", width=4, anchor=tk.E).pack(side=tk.LEFT)
                ttk.Label(row, text=ellipsize(card.name, 28), width=29, anchor=tk.W).pack(
                    side=tk.LEFT
                )
                ttk.Label(row, text=card.zone, foreground="#888").pack(side=tk.LEFT)

            def _toggle() -> None:
                if expanded.get():
                    detail.pack_forget()
                    toggle_btn.configure(text="Cartas v")
                    expanded.set(False)
                else:
                    detail.pack(fill=tk.X, padx=0, pady=(0, 4))
                    toggle_btn.configure(text="Cartas ^")
                    expanded.set(True)
                self._ygo_inner.update_idletasks()
                self._ygo_canvas.configure(scrollregion=self._ygo_canvas.bbox("all"))

            toggle_btn = ttk.Button(summary, text="Cartas v", width=10, command=_toggle)
            toggle_btn.pack(side=tk.RIGHT, padx=(0, 5))
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

    def _ygo_show_text_import_dialog(self) -> None:
        """Show a dialog to import a Yu-Gi-Oh deck from pasted text."""
        dialog = tk.Toplevel()
        dialog.title("Importar mazo Yu-Gi-Oh desde texto")
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        main_frame = ttk.Frame(dialog, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame,
            text="Pega la lista de cartas (una por línea):",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 4))

        ttk.Label(
            main_frame,
            text="Formato: Cantidad Nombre  ó  Cantidad Nombre (SET)",
            foreground="#666",
            font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(0, 8))

        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9))
        text_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=text_scroll.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        example = "3 Blue-Eyes White Dragon\n1 Dark Magician (LOB)\n2 Mirror Force"
        text_widget.insert("1.0", example)
        text_widget.config(foreground="#999")

        def _on_focus_in(event):
            if text_widget.get("1.0", tk.END).strip() == example:
                text_widget.delete("1.0", tk.END)
                text_widget.config(foreground="#000")

        text_widget.bind("<FocusIn>", _on_focus_in)
        text_widget.focus_set()

        status_var = tk.StringVar(value="")
        status_label = ttk.Label(main_frame, textvariable=status_var, foreground="#d32f2f")
        status_label.pack(anchor="w", pady=(0, 8))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        def _do_import():
            text = text_widget.get("1.0", tk.END).strip()
            if not text or text == example:
                status_var.set("⚠️ Pega una lista de cartas primero")
                return

            status_var.set("Importando...")
            dialog.update()

            def _import():
                try:
                    deck = parse_ygo_text(text)
                    self.events.put(("ygo_deck_loaded", deck))
                    dialog.after(0, dialog.destroy)
                except TextImportError as e:
                    dialog.after(0, lambda: status_var.set(f"❌ {e}"))
                except Exception as e:
                    dialog.after(0, lambda: status_var.set(f"❌ Error: {e}"))

            threading.Thread(target=_import, daemon=True).start()

        ttk.Button(btn_frame, text="Importar", command=_do_import).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.RIGHT)

        text_widget.bind("<Control-Return>", lambda _e: _do_import())
