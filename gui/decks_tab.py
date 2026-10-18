"""Unified decks panel — all TCGs in a single view.

Replaces the old per-TCG tabs (Magic/XML, One Piece, Riftbound, Lorcana,
Yu-Gi-Oh) with one panel where every imported deck is listed together,
tagged with its TCG icon.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui.widgets import (
    _PB_CROP_COLOR,
    _PB_DOWNLOAD_COLOR,
    APP_TITLE,
    WINDND_AVAILABLE,
    PreviewWindow,
    XmlPb,
    attach_context_menu,
    ellipsize,
    load_tab_icon,
)
from src.deck_importer import DeckImportError, fetch_deck
from src.parser import parse
from src.precheck import analyze
from src.validator import validate

_SECTION_LABELS = {
    "legend": "Leyenda",
    "champion": "Campeón",
    "battlefield": "Campo de batalla",
    "rune": "Runa",
    "maindeck": "Mazo principal",
    "sideboard": "Sideboard",
}


class DecksTabMixin:
    """Unified deck list: XMLs + all TCG decks in one scrollable panel."""

    # ─────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_decks_panel(self, parent: ttk.Frame) -> None:
        """Build the unified decks panel (left side of the main window)."""
        self._xml_drop_frame = parent
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # TCG icons (kept as attributes to avoid garbage collection)
        self._mtg_icon_img = load_tab_icon("mtg_icon")
        self._op_icon_img = load_tab_icon("op_icon")
        self._rb_icon_img = load_tab_icon("riftbound_icon")
        self._lorcana_icon_img = load_tab_icon("lorcana_icon")
        self._ygo_icon_img = load_tab_icon("yugioh_icon")

        # Import buttons row
        btn_row = ttk.Frame(parent)
        btn_row.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))

        ttk.Button(btn_row, text="Seleccionar XMLs…", command=self._pick_xmls).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="🌐 Añadir desde URL", command=self._open_url_dialog).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(
            btn_row,
            text="📋 Añadir desde texto",
            command=self._show_universal_import_dialog,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_row, text="Vaciar", command=self._clear_all_decks).pack(side=tk.LEFT, padx=6)

        # Deck list (scrollable)
        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 6))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._decks_canvas, self._decks_inner, _ = self._build_scrollable_rows(list_frame)
        self._decks_canvas.bind(
            "<Enter>", lambda _e: self._bind_mousewheel(self._decks_canvas, True)
        )
        self._decks_canvas.bind(
            "<Leave>", lambda _e: self._bind_mousewheel(self._decks_canvas, False)
        )

        # Backwards-compatible aliases (xml rows live in the same canvas)
        self.xml_canvas = self._decks_canvas
        self.xml_inner = self._decks_inner

        dnd_hint = " o arrastra aquí" if WINDND_AVAILABLE else ""
        self._decks_empty_label = ttk.Label(
            self._decks_inner,
            text=f"(sin mazos — usa los botones de arriba{dnd_hint})",
            foreground="#777",
            padding=(8, 10),
        )
        self._decks_empty_label.pack(anchor="w")
        # Alias used by _refresh_xml_rows
        self._xml_empty_label = self._decks_empty_label

    # ─────────────────────────────────────────────────────────────────────
    # Universal URL import (all TCGs)
    # ─────────────────────────────────────────────────────────────────────

    def _open_url_dialog(self) -> None:
        """Universal URL import dialog with automatic TCG detection from domain."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Añadir mazo desde URL")
        dlg.geometry("520x420")
        dlg.resizable(False, False)
        dlg.grab_set()
        self._mtg_url_dialog = dlg  # kept for the mtg_url_loaded handler

        ttk.Label(
            dlg,
            text="Pega la URL del mazo:",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 4))

        # Detection result label
        detection_var = tk.StringVar(value="")
        ttk.Label(
            dlg,
            textvariable=detection_var,
            foreground="#1565C0",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(0, 4))

        self._build_accepted_urls_frame(dlg)

        ttk.Label(
            dlg,
            text="Ten en cuenta que al usar esta opción puede que las imágenes "
            "tengan menos calidad que las de MPCFill",
            foreground="#b86000",
            font=("Segoe UI", 8),
            wraplength=490,
        ).pack(anchor="w", padx=10, pady=(0, 2))

        url_frame = ttk.Frame(dlg)
        url_frame.pack(fill=tk.X, padx=10)
        url_frame.columnconfigure(1, weight=1)
        ttk.Label(url_frame, text="URL:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=url_var)
        url_entry.grid(row=0, column=1, sticky="ew")
        attach_context_menu(url_entry)
        url_entry.focus_set()

        status_var = tk.StringVar(value="")
        self._mtg_url_status_var = status_var
        ttk.Label(dlg, textvariable=status_var, foreground="#555").pack(
            anchor="w", padx=10, pady=(6, 0)
        )

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=10, pady=(6, 10))

        # Auto-detect TCG from URL
        detected_tcg = [None]  # Use list to allow modification in nested function

        def _detect_tcg_from_url(*_args):
            tcg, message = self._detect_tcg_for_url(url_var.get())
            detected_tcg[0] = tcg
            detection_var.set(message)

        url_var.trace_add("write", _detect_tcg_from_url)

        import_btn = ttk.Button(btn_row, text="Importar", command=lambda: _do_import())
        import_btn.pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Cancelar", command=dlg.destroy).pack(side=tk.RIGHT)

        def _do_import():
            self._do_url_import(dlg, url_var, status_var, detected_tcg[0], import_btn)

        import_btn.configure(command=_do_import)
        url_entry.bind("<Return>", lambda _e: _do_import())
        self._mtg_import_btn = import_btn

    @staticmethod
    def _build_accepted_urls_frame(dlg) -> None:
        urls_frame = ttk.LabelFrame(dlg, text="Webs aceptadas", padding=8)
        urls_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        sections = [
            (
                "🎴 Magic: The Gathering:",
                "moxfield.com • archidekt.com • deckstats.net • tappedout.net • manabox.app",
            ),
            ("🏴‍☠️ One Piece:", "onepiece.gg • egmanevents.com • cardkaizoku.com"),
            (
                "⚔️ Riftbound:",
                "piltoverarchive.com • riftbound.gg • riftmana.com • riftbinder.com • riftdex.com",
            ),
            ("✨ Lorcana:", "lorcana.gg • inkdecks.com"),
            ("🎲 Yu-Gi-Oh:", "ygoprodeck.com • yugiohmeta.com • cadena YDKE"),
        ]
        for i, (title, domains) in enumerate(sections):
            ttk.Label(
                urls_frame,
                text=title,
                font=("Segoe UI", 8, "bold"),
                foreground="#555",
            ).pack(anchor="w")
            pady = (0, 4) if i < len(sections) - 1 else (0, 0)
            ttk.Label(
                urls_frame,
                text=domains,
                foreground="#777",
                font=("Segoe UI", 8),
            ).pack(anchor="w", padx=(16, 0), pady=pady)

    @staticmethod
    def _detect_tcg_for_url(url: str) -> tuple[str | None, str]:
        """Detect TCG from URL; return (tcg_name_or_None, detection_message)."""
        url = url.strip().lower()
        if not url:
            return None, ""

        mtg_domains = [
            "moxfield.com",
            "archidekt.com",
            "deckstats.net",
            "tappedout.net",
            "manabox.app",
        ]
        op_domains = ["onepiece.gg", "egmanevents.com", "cardkaizoku.com"]
        rb_domains = [
            "piltoverarchive.com",
            "riftbound.gg",
            "riftmana.com",
            "riftbinder.com",
            "riftdex.com",
        ]
        lorcana_domains = ["lorcana.gg", "inkdecks.com"]
        ygo_domains = ["ygoprodeck.com", "yugiohmeta.com"]

        if any(d in url for d in mtg_domains):
            return "MTG", "🎴 Detectado: Magic: The Gathering"
        if any(d in url for d in op_domains):
            return "One Piece", "🏴‍☠️ Detectado: One Piece"
        if any(d in url for d in rb_domains):
            return "Riftbound", "⚔️ Detectado: Riftbound"
        if any(d in url for d in lorcana_domains):
            return "Lorcana", "✨ Detectado: Lorcana"
        if any(d in url for d in ygo_domains) or url.startswith("ydke://"):
            return "Yu-Gi-Oh", "🎲 Detectado: Yu-Gi-Oh"
        return None, "❌ URL no reconocida. Verifica que sea de una web aceptada."

    def _do_url_import(self, dlg, url_var, status_var, tcg, import_btn) -> None:
        url = url_var.get().strip()
        if not url:
            status_var.set("⚠️ Introduce una URL")
            return
        if not tcg:
            status_var.set("⚠️ URL no reconocida. Verifica que sea de una web aceptada.")
            return
        import_btn.state(["disabled"])
        status_var.set("Cargando…")

        def _run():
            try:
                self._dispatch_url_import(tcg, url)
                dlg.after(0, dlg.destroy)
            except DeckImportError as exc:
                self.events.put(("mtg_url_error", str(exc)))
            except Exception as exc:
                self.events.put(("deck_url_error", (tcg, str(exc))))

        threading.Thread(target=_run, daemon=True).start()

    def _dispatch_url_import(self, tcg: str, url: str) -> None:
        """Run the appropriate scraper for the detected TCG and push the event."""
        if tcg == "MTG":
            result = fetch_deck(url)
            self.events.put(("mtg_url_loaded", url, result.cards, False, result.name))
        elif tcg == "One Piece":
            from src.op_scraper import scrape_deck as op_scrape_deck

            self.events.put(("op_deck_loaded", op_scrape_deck(url)))
        elif tcg == "Riftbound":
            from src.rb_scraper import scrape_deck as rb_scrape_deck

            self.events.put(("rb_deck_loaded", rb_scrape_deck(url)))
        elif tcg == "Lorcana":
            from src.lorcana_scraper import scrape_deck as lorcana_scrape_deck

            self.events.put(("lorcana_deck_loaded", lorcana_scrape_deck(url)))
        elif tcg == "Yu-Gi-Oh":
            from src.ygo_scraper import scrape_deck as ygo_scrape_deck

            self.events.put(("ygo_deck_loaded", ygo_scrape_deck(url)))

    # ─────────────────────────────────────────────────────────────────────
    # XML file management (unchanged logic, rows live in the unified list)
    # ─────────────────────────────────────────────────────────────────────

    def _add_xml_path(self, pp: Path) -> bool:
        """Add a single XML path and compute its metadata. Returns True if added."""
        if pp in self.state.xml_paths:
            return False
        self.state.xml_paths.append(pp)
        if pp not in self._xml_card_counts:
            try:
                rpts = analyze([pp])
                if rpts:
                    self._xml_card_counts[pp] = rpts[0].cards
            except Exception:
                pass
        if pp not in self._xml_orders:
            try:
                self._xml_orders[pp] = parse(pp)
            except Exception:
                pass
        if pp not in self._xml_validations:
            try:
                self._xml_validations[pp] = validate(pp)
            except Exception:
                self._xml_validations[pp] = []
        return True

    def _after_xmls_added(self, added: int) -> None:
        if added:
            self._refresh_xml_rows()
            self.status_var.set(f"{len(self.state.xml_paths)} XML(s) en cola.")
        self._refresh_generate_state()

    def _pick_xmls(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecciona archivos XML de MPCFill",
            filetypes=[("Archivos XML", "*.xml"), ("Todos", "*.*")],
        )
        added = 0
        for p in paths:
            if self._add_xml_path(Path(p)):
                added += 1
        self._after_xmls_added(added)

    def _on_drop_xmls(self, files) -> None:
        paths = self._decode_drop(files)
        added = 0
        for pp in paths:
            if pp.suffix.lower() != ".xml":
                continue
            if self._add_xml_path(pp):
                added += 1
        self._after_xmls_added(added)

    def _remove_xml(self, idx: int) -> None:
        if 0 <= idx < len(self.state.xml_paths):
            p = self.state.xml_paths[idx]
            self._xml_card_counts.pop(p, None)
            self._xml_orders.pop(p, None)
            self._xml_validations.pop(p, None)
            del self.state.xml_paths[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    def _clear_all_decks(self) -> None:
        """Clear XMLs and every TCG deck from the unified list."""
        self.state.xml_paths.clear()
        self._xml_card_counts.clear()
        self._xml_orders.clear()
        self._xml_validations.clear()
        self.state.mtg_url_decks.clear()
        self._op_decks.clear()
        self._rb_decks.clear()
        self._lorcana_decks.clear()
        self._ygo_decks.clear()
        self._refresh_xml_rows()
        self._refresh_generate_state()

    # ─────────────────────────────────────────────────────────────────────
    # Unified rows refresh
    # ─────────────────────────────────────────────────────────────────────

    def _refresh_xml_rows(self) -> None:
        """Rebuild the unified list: XMLs first, then every TCG deck."""
        for row in self._xml_rows:
            row["frame"].destroy()
        self._xml_rows.clear()
        for row in self._mtg_deck_rows:
            row["frame"].destroy()
        self._mtg_deck_rows.clear()
        for row in self._op_deck_rows:
            row["outer"].destroy()
        self._op_deck_rows.clear()
        for row in self._rb_deck_rows:
            row["outer"].destroy()
        self._rb_deck_rows.clear()
        for row in self._lorcana_deck_rows:
            row["outer"].destroy()
        self._lorcana_deck_rows.clear()
        for row in self._ygo_deck_rows:
            row["outer"].destroy()
        self._ygo_deck_rows.clear()

        empty = (
            not self.state.xml_paths
            and not self.state.mtg_url_decks
            and not self._op_decks
            and not self._rb_decks
            and not self._lorcana_decks
            and not self._ygo_decks
        )
        if empty:
            self._decks_empty_label.pack(anchor="w")
            return
        self._decks_empty_label.pack_forget()

        self._render_xml_rows()
        self._render_mtg_rows()
        self._render_op_rows()
        self._render_rb_rows()
        self._render_lorcana_rows()
        self._render_ygo_rows()

        self._decks_inner.update_idletasks()
        self._decks_canvas.configure(scrollregion=self._decks_canvas.bbox("all"))
        # Reset scroll to top after refresh to avoid misalignment
        self._decks_canvas.yview_moveto(0)

    # Compatibility shims: each TCG refresh just rebuilds the unified list
    def _op_refresh_rows(self) -> None:
        self._refresh_xml_rows()

    def _rb_refresh_rows(self) -> None:
        self._refresh_xml_rows()

    def _lorcana_refresh_rows(self) -> None:
        self._refresh_xml_rows()

    def _ygo_refresh_rows(self) -> None:
        self._refresh_xml_rows()

    # ── XML rows ──────────────────────────────────────────────────────────

    def _render_xml_rows(self) -> None:
        for i, xml_path in enumerate(self.state.xml_paths):
            frame = ttk.Frame(self._decks_inner)
            frame.pack(fill=tk.X, pady=1, padx=2)
            frame.columnconfigure(0, weight=3)
            frame.columnconfigure(2, weight=7)

            ttk.Label(
                frame,
                text=ellipsize(xml_path.name, 32),
                anchor="w",
                image=self._mtg_icon_img,
                compound=tk.LEFT,
            ).grid(row=0, column=0, sticky="ew", padx=(4, 0))

            ttk.Label(frame, text=" - ").grid(row=0, column=1)

            right = ttk.Frame(frame)
            right.grid(row=0, column=2, sticky="ew")

            card_count = self._xml_card_counts.get(xml_path)
            cards_text = f"{card_count} cartas" if card_count is not None else ""
            ttk.Label(right, text=cards_text, foreground="#555", anchor="w").grid(
                row=0, column=0, sticky="w", padx=(0, 6)
            )

            pb = XmlPb(right)
            pb.grid(row=0, column=1, padx=(0, 4))
            pb.grid_remove()

            count_var = tk.StringVar(value="")
            count_lbl = ttk.Label(right, textvariable=count_var, width=9, anchor="w")
            count_lbl.grid(row=0, column=2, padx=(0, 4))
            count_lbl.grid_remove()

            ttk.Button(
                right,
                text="Ver cartas",
                command=lambda p=xml_path: self._show_preview(p),
            ).grid(row=0, column=4, padx=(0, 2))
            ttk.Button(
                right,
                text="✕",
                width=2,
                command=lambda idx=i: self._remove_xml(idx),
            ).grid(row=0, column=3, padx=(0, 1))

            xml_warnings = self._xml_validations.get(xml_path, [])
            warn_btn = ttk.Button(
                right,
                text="⚠",
                width=2,
                command=lambda p=xml_path: self._show_xml_warnings(p),
            )
            warn_btn.grid(row=0, column=5, padx=(0, 2))
            if not xml_warnings:
                warn_btn.grid_remove()

            self._xml_rows.append(
                {
                    "frame": frame,
                    "pb": pb,
                    "count_var": count_var,
                    "count_lbl": count_lbl,
                    "warn_btn": warn_btn,
                }
            )

    # ── MTG deck rows ─────────────────────────────────────────────────────

    def _render_mtg_card_row(self, detail, deck, card, selected_ids, card_vars) -> None:
        """Render a single card row (checkbox + quantity + name + zone)."""
        card_row = ttk.Frame(detail)
        card_row.pack(fill=tk.X, padx=(12, 4))
        card_vars[id(card)] = tk.BooleanVar(value=id(card) in selected_ids)

        def _sync_cards(d=deck, vars=card_vars):
            d.selected_card_ids = {card_id for card_id, var in vars.items() if var.get()}
            self._refresh_generate_state()

        ttk.Checkbutton(card_row, variable=card_vars[id(card)], command=_sync_cards).pack(
            side=tk.LEFT
        )

        qty_var = tk.IntVar(value=card.quantity)

        def _make_qty_updater(c=card, var=qty_var, checkvar=card_vars[id(card)]):
            def _update(*_args):
                try:
                    new_qty = var.get()
                    if new_qty == 0:
                        checkvar.set(False)
                        _sync_cards()
                    elif new_qty >= 1:
                        c.quantity = new_qty
                        checkvar.set(True)
                        _sync_cards()
                except tk.TclError:
                    pass  # Invalid input, ignore

            return _update

        qty_spinbox = ttk.Spinbox(
            card_row,
            from_=0,
            to=99,
            width=4,
            textvariable=qty_var,
            command=_make_qty_updater(),
        )
        qty_spinbox.pack(side=tk.LEFT, padx=(0, 4))
        qty_var.trace_add("write", _make_qty_updater())

        ttk.Label(card_row, text=ellipsize(card.name, 28), width=29, anchor="w").pack(side=tk.LEFT)
        ttk.Label(card_row, text=card.zone, foreground="#888").pack(side=tk.LEFT)

    def _render_mtg_detail(self, outer, i, deck, side_count) -> tuple:
        """Build the detail frame with sideboard/tokens toggles and card rows."""
        detail = ttk.Frame(outer)
        controls = ttk.Frame(detail)
        controls.pack(fill=tk.X, padx=(12, 4), pady=(0, 4))
        expanded = tk.BooleanVar(value=False)

        if side_count:
            side_var = tk.BooleanVar(value=deck.include_side)

            def _toggle_side(idx=i, var=side_var):
                self.state.mtg_url_decks[idx].include_side = var.get()
                self._refresh_generate_state()

            ttk.Checkbutton(
                controls, text="Incluir sideboard", variable=side_var, command=_toggle_side
            ).pack(side=tk.LEFT, padx=(12, 8), pady=(0, 4))

        token_var = tk.BooleanVar(value=deck.include_tokens)

        def _toggle_tokens(idx=i, var=token_var):
            self.state.mtg_url_decks[idx].include_tokens = var.get()
            self._refresh_generate_state()

        ttk.Checkbutton(
            controls,
            text="Incluir tokens y extras",
            variable=token_var,
            command=_toggle_tokens,
        ).pack(side=tk.LEFT, padx=(12, 8), pady=(0, 4))

        selected_ids = deck.selected_card_ids
        if selected_ids is None:
            selected_ids = {id(card) for card in deck.cards}
        card_vars: dict[int, tk.BooleanVar] = {}

        for card in sorted(deck.cards, key=lambda c: c.name.casefold()):
            self._render_mtg_card_row(detail, deck, card, selected_ids, card_vars)

        return detail, expanded

    def _render_mtg_rows(self) -> None:
        numbered = [str(j + 1) for j in range(len(self.state.local_backs))]
        back_combo_values = ["default", *numbered]

        for i, deck in enumerate(self.state.mtg_url_decks):
            outer = ttk.Frame(self._decks_inner, relief="groove", borderwidth=1)
            outer.pack(fill=tk.X, pady=1, padx=2)
            frame = ttk.Frame(outer)
            frame.pack(fill=tk.X)
            frame.columnconfigure(0, weight=3)
            frame.columnconfigure(2, weight=7)

            ttk.Label(
                frame,
                text=ellipsize(deck.display_name, 32),
                anchor="w",
                image=self._mtg_icon_img,
                compound=tk.LEFT,
            ).grid(row=0, column=0, sticky="ew", padx=(4, 0))

            ttk.Label(frame, text=" - ").grid(row=0, column=1)

            right = ttk.Frame(frame)
            right.grid(row=0, column=2, sticky="ew")

            main_count = sum(c.quantity for c in deck.cards if c.zone == "main")
            side_count = sum(c.quantity for c in deck.cards if c.zone == "side")
            token_count = sum(c.quantity for c in deck.cards if c.zone == "token")
            count_text = f"{main_count} cartas" + (f" +{side_count} side" if side_count else "")
            count_text += f" +{token_count} tokens/extras" if token_count else ""
            ttk.Label(right, text=count_text, foreground="#555", anchor="w").grid(
                row=0, column=0, sticky="w", padx=(0, 6)
            )

            col = 1
            if deck.back_path is not None and deck.back_path not in self.state.local_backs:
                deck.back_path = None

            back_var = tk.StringVar()
            if deck.back_path is None:
                back_var.set("default")
            else:
                back_var.set(str(self.state.local_backs.index(deck.back_path) + 1))

            ttk.Label(right, text="Traseras:").grid(row=0, column=col, padx=(0, 2))
            col += 1
            back_combo = ttk.Combobox(
                right,
                values=back_combo_values,
                textvariable=back_var,
                state="readonly" if numbered else "disabled",
                width=4,
            )
            back_combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, idx=i, v=back_var: self._on_mtg_back_change(idx, v),
            )
            back_combo.grid(row=0, column=col, padx=(0, 4))
            col += 1

            ttk.Button(
                right,
                text="✕",
                width=2,
                command=lambda idx=i: self._remove_mtg_deck(idx),
            ).grid(row=0, column=col, padx=(0, 2))
            col += 1

            detail, expanded = self._render_mtg_detail(outer, i, deck, side_count)

            extras_btn = ttk.Button(
                right,
                text="Cartas ▼",
                width=10,
                command=lambda idx=i: self._toggle_mtg_extras(idx),
            )
            extras_btn.grid(row=0, column=col)

            self._mtg_deck_rows.append(
                {
                    "frame": outer,
                    "detail": detail,
                    "extras_btn": extras_btn,
                    "expanded": expanded,
                }
            )

    def _toggle_mtg_extras(self, idx: int) -> None:
        if idx >= len(self._mtg_deck_rows):
            return
        row = self._mtg_deck_rows[idx]
        detail = row["detail"]
        extras_btn = row["extras_btn"]
        expanded = row["expanded"]
        if detail is None or extras_btn is None or expanded is None:
            return
        if expanded.get():
            detail.pack_forget()
            extras_btn.configure(text="Cartas ▼")
            expanded.set(False)
        else:
            detail.pack(fill=tk.X, padx=(12, 4), pady=(0, 4))
            extras_btn.configure(text="Cartas ▲")
            expanded.set(True)
        self._decks_inner.update_idletasks()
        self._decks_canvas.configure(scrollregion=self._decks_canvas.bbox("all"))

    def _remove_mtg_deck(self, idx: int) -> None:
        if 0 <= idx < len(self.state.mtg_url_decks):
            del self.state.mtg_url_decks[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    def _on_mtg_back_change(self, deck_idx: int, var: tk.StringVar) -> None:
        if deck_idx >= len(self.state.mtg_url_decks):
            return
        choice = var.get()
        try:
            n = int(choice)
        except (TypeError, ValueError):  # "default" or any non-numeric value
            self.state.mtg_url_decks[deck_idx].back_path = None
            return
        if 1 <= n <= len(self.state.local_backs):
            self.state.mtg_url_decks[deck_idx].back_path = self.state.local_backs[n - 1]

    # ── One Piece deck rows ───────────────────────────────────────────────

    def _render_op_rows(self) -> None:
        for idx, deck in enumerate(self._op_decks):
            leader = deck.leader

            outer = ttk.Frame(self._decks_inner, relief="groove", borderwidth=1)
            outer.pack(fill=tk.X, pady=3, padx=2)
            outer.columnconfigure(0, weight=1)

            summary = ttk.Frame(outer)
            summary.pack(fill=tk.X, padx=6, pady=4)
            summary.columnconfigure(1, weight=1)

            ttk.Label(
                summary,
                text=ellipsize(deck.name, 22),
                font=("Segoe UI", 9, "bold"),
                anchor="w",
                image=self._op_icon_img,
                compound=tk.LEFT,
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

            detail = self._render_op_detail(outer, deck)

            self._op_deck_rows.append(
                {
                    "outer": outer,
                    "detail": detail,
                    "toggle_btn": toggle_btn,
                    "expanded": expanded_var,
                    "deck": deck,
                }
            )

    def _render_op_card_row(self, detail, card, selected_ids, card_vars, sync_fn) -> None:
        """Render a single One Piece card row."""
        row_f = ttk.Frame(detail)
        card_vars[card.card_id] = tk.BooleanVar(value=card.card_id in selected_ids)
        ttk.Checkbutton(row_f, variable=card_vars[card.card_id], command=sync_fn).pack(
            side=tk.LEFT, padx=(0, 2)
        )
        row_f.pack(fill=tk.X, pady=0, padx=(12, 4))

        qty_var = tk.IntVar(value=card.quantity)

        def _make_qty_updater(c=card, var=qty_var, checkvar=card_vars[card.card_id]):
            def _update(*_args):
                try:
                    new_qty = var.get()
                    if new_qty == 0:
                        checkvar.set(False)
                        sync_fn()
                    elif new_qty >= 1:
                        c.quantity = new_qty
                        checkvar.set(True)
                        sync_fn()
                except tk.TclError:
                    pass  # Invalid input, ignore

            return _update

        qty_spinbox = ttk.Spinbox(
            row_f,
            from_=0,
            to=99,
            width=4,
            textvariable=qty_var,
            command=_make_qty_updater(),
        )
        qty_spinbox.pack(side=tk.LEFT, padx=(0, 6))
        qty_var.trace_add("write", _make_qty_updater())

        if card.is_leader:
            ttk.Label(
                row_f,
                text="LÍDER",
                foreground="#1565C0",
                font=("Segoe UI", 8, "bold"),
                width=7,
                anchor="w",
            ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Label(row_f, text=ellipsize(card.name, 24), anchor="w", width=25).pack(side=tk.LEFT)
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

    def _render_op_detail(self, outer, deck):
        """Build the OP detail frame with per-card rows."""
        detail = ttk.Frame(outer)
        selected_ids = getattr(deck, "selected_card_ids", {card.card_id for card in deck.cards})
        card_vars: dict[str, tk.BooleanVar] = {}

        def _sync_selection(d=deck, vars=card_vars) -> None:
            d.selected_card_ids = {card_id for card_id, var in vars.items() if var.get()}
            self._refresh_generate_state()

        for card in sorted(deck.cards, key=lambda c: c.name.casefold()):
            self._render_op_card_row(detail, card, selected_ids, card_vars, _sync_selection)

        return detail

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
        self._decks_inner.update_idletasks()
        self._decks_canvas.configure(scrollregion=self._decks_canvas.bbox("all"))

    def _op_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._op_decks):
            del self._op_decks[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    # ── Riftbound deck rows ───────────────────────────────────────────────

    def _render_rb_card_row(self, detail, card, selected_ids, card_vars, sync_fn) -> None:
        """Render a single Riftbound card row."""
        row_f = ttk.Frame(detail)
        row_f.pack(fill=tk.X, pady=0, padx=(12, 4))
        card_vars[card.variant_id] = tk.BooleanVar(value=card.variant_id in selected_ids)
        ttk.Checkbutton(row_f, variable=card_vars[card.variant_id], command=sync_fn).pack(
            side=tk.LEFT, padx=(0, 2)
        )

        qty_var = tk.IntVar(value=card.quantity)

        def _make_qty_updater(c=card, var=qty_var, checkvar=card_vars[card.variant_id]):
            def _update(*_args):
                try:
                    new_qty = var.get()
                    if new_qty == 0:
                        checkvar.set(False)
                        sync_fn()
                    elif new_qty >= 1:
                        c.quantity = new_qty
                        checkvar.set(True)
                        sync_fn()
                except tk.TclError:
                    pass  # Invalid input, ignore

            return _update

        qty_spinbox = ttk.Spinbox(
            row_f,
            from_=0,
            to=99,
            width=4,
            textvariable=qty_var,
            command=_make_qty_updater(),
        )
        qty_spinbox.pack(side=tk.LEFT, padx=(0, 6))
        qty_var.trace_add("write", _make_qty_updater())

        name_frame = ttk.Frame(row_f)
        name_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(row_f, text=ellipsize(card.name, 24), anchor="w", font=("Segoe UI", 8)).pack(
            side=tk.LEFT
        )

        ttk.Label(
            row_f,
            text=f"({card.card_id})",
            foreground="#666",
            font=("Consolas", 7),
            anchor="w",
        ).pack(side=tk.LEFT, padx=(4, 0))

    def _render_rb_detail(self, outer, deck, by_sec):
        """Build the RB detail frame with per-section card rows."""
        detail = ttk.Frame(outer)
        selected_ids = getattr(deck, "selected_card_ids", {card.variant_id for card in deck.cards})
        card_vars: dict[str, tk.BooleanVar] = {}

        def _sync_selection(d=deck, vars=card_vars) -> None:
            d.selected_card_ids = {card_id for card_id, var in vars.items() if var.get()}
            self._refresh_generate_state()

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
            for card in sorted(cards, key=lambda c: c.name.casefold()):
                self._render_rb_card_row(detail, card, selected_ids, card_vars, _sync_selection)

        return detail

    def _render_rb_rows(self) -> None:
        for idx, deck in enumerate(self._rb_decks):
            outer = ttk.Frame(self._decks_inner, relief="groove", borderwidth=1)
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
                image=self._rb_icon_img,
                compound=tk.LEFT,
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

            # Sideboard checkbox
            include_sideboard_var = tk.BooleanVar(value=False)
            has_sideboard = bool(by_sec.get("sideboard"))
            sideboard_cb = ttk.Checkbutton(
                summary,
                text="incluir sideboard",
                variable=include_sideboard_var,
                command=self._refresh_generate_state,
            )
            if not has_sideboard:
                sideboard_cb.state(["disabled"])
            sideboard_cb.grid(row=0, column=4, padx=(4, 8))

            expanded_var = tk.BooleanVar(value=False)
            toggle_btn = ttk.Button(
                summary,
                text="Detalles ▼",
                width=10,
                command=lambda i=idx: self._rb_toggle_details(i),
            )
            toggle_btn.grid(row=0, column=5, padx=(0, 4))

            ttk.Button(
                summary,
                text="✕",
                width=2,
                command=lambda i=idx: self._rb_remove_deck(i),
            ).grid(row=0, column=6)

            detail = self._render_rb_detail(outer, deck, by_sec)

            self._rb_deck_rows.append(
                {
                    "outer": outer,
                    "detail": detail,
                    "toggle_btn": toggle_btn,
                    "expanded": expanded_var,
                    "deck": deck,
                    "print_runes_var": print_runes_var,
                    "include_sideboard_var": include_sideboard_var,
                }
            )

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
        self._decks_inner.update_idletasks()
        self._decks_canvas.configure(scrollregion=self._decks_canvas.bbox("all"))

    def _rb_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._rb_decks):
            del self._rb_decks[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    # ── Lorcana deck rows ─────────────────────────────────────────────────

    def _render_lorcana_rows(self) -> None:
        source_labels = {
            "lorcana_gg": "lorcana.gg",
            "inkdecks": "inkdecks.com",
        }

        for idx, deck in enumerate(self._lorcana_decks):
            outer = ttk.Frame(self._decks_inner, relief="groove", borderwidth=1)
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
                image=self._lorcana_icon_img,
                compound=tk.LEFT,
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
            selected_ids = getattr(deck, "selected_card_ids", {card.card_id for card in deck.cards})
            card_vars: dict[str, tk.BooleanVar] = {}

            def _sync_selection(d=deck, vars=card_vars) -> None:
                d.selected_card_ids = {card_id for card_id, var in vars.items() if var.get()}
                self._refresh_generate_state()

            for card in sorted(deck.cards, key=lambda c: c.name.casefold()):
                row_f = ttk.Frame(detail)
                card_vars[card.card_id] = tk.BooleanVar(value=card.card_id in selected_ids)
                ttk.Checkbutton(
                    row_f, variable=card_vars[card.card_id], command=_sync_selection
                ).pack(side=tk.LEFT, padx=(0, 2))
                row_f.pack(fill=tk.X, pady=0, padx=(12, 4))

                qty_var = tk.IntVar(value=card.quantity)

                def _make_qty_updater(c=card, var=qty_var, checkvar=card_vars[card.card_id]):
                    def _update(*_args):
                        try:
                            new_qty = var.get()
                            if new_qty == 0:
                                checkvar.set(False)
                                _sync_selection()
                            elif new_qty >= 1:
                                c.quantity = new_qty
                                checkvar.set(True)
                                _sync_selection()
                        except tk.TclError:
                            pass  # Invalid input, ignore

                    return _update

                qty_spinbox = ttk.Spinbox(
                    row_f,
                    from_=0,
                    to=99,
                    width=4,
                    textvariable=qty_var,
                    command=_make_qty_updater(),
                )
                qty_spinbox.pack(side=tk.LEFT, padx=(0, 6))
                qty_var.trace_add("write", _make_qty_updater())

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
        self._decks_inner.update_idletasks()
        self._decks_canvas.configure(scrollregion=self._decks_canvas.bbox("all"))

    def _lorcana_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._lorcana_decks):
            del self._lorcana_decks[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    # ── Yu-Gi-Oh deck rows ────────────────────────────────────────────────

    def _render_ygo_rows(self) -> None:
        for idx, deck in enumerate(self._ygo_decks):
            outer = ttk.Frame(self._decks_inner, relief="groove", borderwidth=1)
            outer.pack(fill=tk.X, padx=2, pady=3)
            summary = ttk.Frame(outer)
            summary.pack(fill=tk.X, padx=6, pady=4)
            ttk.Label(
                summary,
                text=ellipsize(deck.name, 28),
                font=("Segoe UI", 9, "bold"),
                image=self._ygo_icon_img,
                compound=tk.LEFT,
            ).pack(side=tk.LEFT)
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

                qty_var = tk.IntVar(value=card.quantity)

                def _make_qty_updater(c=card, var=qty_var, checkvar=card_vars[card.card_id]):
                    def _update(*_args):
                        try:
                            new_qty = var.get()
                            if new_qty == 0:
                                checkvar.set(False)
                                _sync_selection()
                            elif new_qty >= 1:
                                c.quantity = new_qty
                                checkvar.set(True)
                                _sync_selection()
                        except tk.TclError:
                            pass  # Invalid input, ignore

                    return _update

                qty_spinbox = ttk.Spinbox(
                    row, from_=0, to=99, width=4, textvariable=qty_var, command=_make_qty_updater()
                )
                qty_spinbox.pack(side=tk.LEFT, padx=(0, 4))
                qty_var.trace_add("write", _make_qty_updater())

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
                self._decks_inner.update_idletasks()
                self._decks_canvas.configure(scrollregion=self._decks_canvas.bbox("all"))

            toggle_btn = ttk.Button(summary, text="Cartas v", width=10, command=_toggle)
            toggle_btn.pack(side=tk.RIGHT, padx=(0, 5))
            self._ygo_deck_rows.append({"outer": outer, "include_side_var": include_side})

    def _ygo_remove_deck(self, idx: int) -> None:
        if 0 <= idx < len(self._ygo_decks):
            del self._ygo_decks[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    # ── XML progress / preview helpers (unchanged) ────────────────────────

    def _show_xml_download_progress(self, xml_name: str, done: int, total: int) -> None:
        for xml_path, row in zip(self.state.xml_paths, self._xml_rows):
            if xml_path.name == xml_name:
                pct = (done / total * 100.0) if total else 100.0
                row["pb"].set_progress(pct, "Descargando", color=_PB_DOWNLOAD_COLOR)
                row["count_var"].set(f"{done}/{total}")
                row["pb"].grid()
                row["count_lbl"].grid()
                break

    def _show_xml_crop_progress(self, xml_name: str, done: int, total: int) -> None:
        for xml_path, row in zip(self.state.xml_paths, self._xml_rows):
            if xml_path.name == xml_name:
                pct = (done / total * 100.0) if total else 100.0
                row["pb"].set_progress(pct, "Recortando", color=_PB_CROP_COLOR)
                row["count_var"].set(f"{done}/{total}")
                row["pb"].grid()
                row["count_lbl"].grid()
                break

    def _reset_xml_download_progress(self) -> None:
        for row in self._xml_rows:
            row["pb"].set_progress(0, "")
            row["count_var"].set("")
            row["pb"].grid_remove()
            row["count_lbl"].grid_remove()

    def _show_preview(self, xml_path: Path) -> None:
        order = self._xml_orders.get(xml_path)
        if order is None:
            messagebox.showinfo(APP_TITLE, "No hay datos de cartas para esta XML.")
            return
        PreviewWindow(self.root, xml_path, order)

    def _show_xml_warnings(self, xml_path: Path) -> None:
        warnings = self._xml_validations.get(xml_path, [])
        if not warnings:
            return
        msg = "\n".join(f"• {w.message}" for w in warnings)
        messagebox.showwarning(
            APP_TITLE,
            f"Advertencias en {xml_path.name}:\n\n{msg}",
        )
