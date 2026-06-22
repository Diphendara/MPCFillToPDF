"""XmlTabMixin — Magic/XML tab methods for the App class."""

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
)
from src.deck_importer import DeckImportError, fetch_deck
from src.parser import parse
from src.precheck import analyze
from src.validator import validate


class XmlTabMixin:
    """Methods for the Magic/XML tab and XML file management."""

    def _build_magic_tab(self, parent: ttk.Frame) -> None:
        self._xml_drop_frame = parent
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        xml_list_frame = ttk.Frame(parent)
        xml_list_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 2))
        xml_list_frame.columnconfigure(0, weight=1)
        xml_list_frame.rowconfigure(0, weight=1)

        self.xml_canvas, self.xml_inner, self._xml_window = self._build_scrollable_rows(
            xml_list_frame
        )
        self.xml_canvas.bind("<Enter>", lambda _e: self._bind_mousewheel(self.xml_canvas, True))
        self.xml_canvas.bind("<Leave>", lambda _e: self._bind_mousewheel(self.xml_canvas, False))

        dnd_hint = " o arrastra aquí" if WINDND_AVAILABLE else ""
        self._xml_empty_label = ttk.Label(
            self.xml_inner,
            text=f"(sin XMLs — usa «Seleccionar XMLs…»{dnd_hint})",
            foreground="#777",
            padding=(8, 10),
        )
        self._xml_empty_label.pack(anchor="w")

        xml_btn_row = ttk.Frame(parent)
        xml_btn_row.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(xml_btn_row, text="Seleccionar XMLs…", command=self._pick_xmls).pack(
            side=tk.LEFT
        )
        ttk.Button(xml_btn_row, text="Añadir desde URL", command=self._open_url_dialog).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(xml_btn_row, text="Vaciar", command=self._clear_xmls).pack(side=tk.LEFT, padx=6)

    def _pick_xmls(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecciona archivos XML de MPCFill",
            filetypes=[("Archivos XML", "*.xml"), ("Todos", "*.*")],
        )
        added = 0
        for p in paths:
            pp = Path(p)
            if pp not in self.state.xml_paths:
                self.state.xml_paths.append(pp)
                added += 1
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
        if added:
            self._refresh_xml_rows()
            self.status_var.set(f"{len(self.state.xml_paths)} XML(s) en cola.")
        self._refresh_generate_state()

    def _on_drop_xmls(self, files) -> None:
        paths = self._decode_drop(files)
        added = 0
        for pp in paths:
            if pp.suffix.lower() != ".xml":
                continue
            if pp not in self.state.xml_paths:
                self.state.xml_paths.append(pp)
                added += 1
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
        if added:
            self._refresh_xml_rows()
            self.status_var.set(f"{len(self.state.xml_paths)} XML(s) en cola.")
        self._refresh_generate_state()

    def _remove_xml(self, idx: int) -> None:
        if 0 <= idx < len(self.state.xml_paths):
            p = self.state.xml_paths[idx]
            self._xml_card_counts.pop(p, None)
            self._xml_orders.pop(p, None)
            self._xml_validations.pop(p, None)
            del self.state.xml_paths[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    def _clear_xmls(self) -> None:
        self.state.xml_paths.clear()
        self._xml_card_counts.clear()
        self._xml_orders.clear()
        self._xml_validations.clear()
        self.state.mtg_url_decks.clear()
        self._refresh_xml_rows()
        self._refresh_generate_state()

    def _refresh_xml_rows(self) -> None:
        for row in self._xml_rows:
            row["frame"].destroy()
        self._xml_rows.clear()
        for row in self._mtg_deck_rows:
            row["frame"].destroy()
        self._mtg_deck_rows.clear()

        if not self.state.xml_paths and not self.state.mtg_url_decks:
            self._xml_empty_label.pack(anchor="w")
            return
        self._xml_empty_label.pack_forget()

        for i, xml_path in enumerate(self.state.xml_paths):
            frame = ttk.Frame(self.xml_inner)
            frame.pack(fill=tk.X, pady=1, padx=2)
            frame.columnconfigure(0, weight=3)
            frame.columnconfigure(2, weight=7)

            ttk.Label(
                frame,
                text=ellipsize(xml_path.name, 32),
                anchor="w",
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

        numbered = [str(j + 1) for j in range(len(self.state.local_backs))]
        back_combo_values = ["default", *numbered]

        for i, deck in enumerate(self.state.mtg_url_decks):
            frame = ttk.Frame(self.xml_inner)
            frame.pack(fill=tk.X, pady=1, padx=2)
            frame.columnconfigure(0, weight=3)
            frame.columnconfigure(2, weight=7)

            ttk.Label(
                frame,
                text=ellipsize(deck.display_name, 32),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=(4, 0))

            ttk.Label(frame, text=" - ").grid(row=0, column=1)

            right = ttk.Frame(frame)
            right.grid(row=0, column=2, sticky="ew")

            main_count = sum(c.quantity for c in deck.cards if c.zone == "main")
            side_count = sum(c.quantity for c in deck.cards if c.zone == "side")
            count_text = f"{main_count} cartas" + (f" +{side_count} side" if side_count else "")
            ttk.Label(right, text=count_text, foreground="#555", anchor="w").grid(
                row=0, column=0, sticky="w", padx=(0, 6)
            )

            col = 1
            if side_count:
                side_var = tk.BooleanVar(value=deck.include_side)

                def _toggle_side(idx=i, var=side_var):
                    self.state.mtg_url_decks[idx].include_side = var.get()
                    self._refresh_generate_state()

                ttk.Checkbutton(
                    right, text="Incluir sideboard", variable=side_var, command=_toggle_side
                ).grid(row=0, column=col, padx=(0, 4))
                col += 1

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

            self._mtg_deck_rows.append({"frame": frame})

        self.xml_inner.update_idletasks()
        self.xml_canvas.configure(scrollregion=self.xml_canvas.bbox("all"))

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

    def _open_url_dialog(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Añadir mazo desde URL")
        dlg.geometry("480x190")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.columnconfigure(0, weight=1)
        self._mtg_url_dialog = dlg

        ttk.Label(
            dlg,
            text="Ten en cuenta que al usar esta opción puede que las imágenes tengan menos calidad que las de MPCFill",
            foreground="#b86000",
            font=("Segoe UI", 8),
            wraplength=440,
        ).pack(anchor="w", padx=10, pady=(10, 2))

        ttk.Label(
            dlg,
            text="Webs aceptadas: moxfield.com, archidekt.com, deckstats.net, tappedout.net, manabox.app",
            foreground="#999",
            font=("Segoe UI", 8),
            wraplength=440,
            justify="left",
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

        status_lbl = ttk.Label(dlg, textvariable=status_var, foreground="#555")
        status_lbl.pack(anchor="w", padx=10, pady=(6, 0))

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=10, pady=(6, 10))

        def _do_import():
            url = url_var.get().strip()
            if not url:
                return
            import_btn.state(["disabled"])
            status_var.set("Cargando…")

            def _run():
                try:
                    result = fetch_deck(url)
                    self.events.put(("mtg_url_loaded", url, result.cards, False, result.name))
                except DeckImportError as exc:
                    self.events.put(("mtg_url_error", str(exc)))
                except Exception as exc:
                    self.events.put(("mtg_url_error", f"Error inesperado: {exc}"))

            threading.Thread(target=_run, daemon=True).start()

        import_btn = ttk.Button(btn_row, text="Importar", command=_do_import)
        import_btn.pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Cancelar", command=dlg.destroy).pack(side=tk.RIGHT)
        url_entry.bind("<Return>", lambda _e: _do_import())
        self._mtg_import_btn = import_btn
