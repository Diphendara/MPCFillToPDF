"""XmlTabMixin — Magic/XML tab methods for the App class."""

from __future__ import annotations

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
    ellipsize,
)
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
        self._refresh_xml_rows()
        self._refresh_generate_state()

    def _refresh_xml_rows(self) -> None:
        for row in self._xml_rows:
            row["frame"].destroy()
        self._xml_rows.clear()

        if not self.state.xml_paths:
            self._xml_empty_label.pack(anchor="w")
            return
        self._xml_empty_label.pack_forget()

        for i, xml_path in enumerate(self.state.xml_paths):
            frame = ttk.Frame(self.xml_inner)
            frame.pack(fill=tk.X, pady=1, padx=2)
            frame.columnconfigure(0, weight=1)

            ttk.Label(
                frame,
                text=ellipsize(xml_path.name, 32),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=(4, 8))

            card_count = self._xml_card_counts.get(xml_path)
            cards_text = f"{card_count} cartas" if card_count is not None else ""
            ttk.Label(frame, text=cards_text, foreground="#555", width=10, anchor="e").grid(
                row=0,
                column=1,
                padx=(0, 8),
            )

            pb = XmlPb(frame)
            pb.grid(row=0, column=2, padx=(0, 4))
            pb.grid_remove()

            count_var = tk.StringVar(value="")
            count_lbl = ttk.Label(frame, textvariable=count_var, width=9, anchor="e")
            count_lbl.grid(row=0, column=3, padx=(0, 4))
            count_lbl.grid_remove()

            ttk.Button(
                frame,
                text="▲",
                width=2,
                command=lambda idx=i: self._move_xml_up(idx),
            ).grid(row=0, column=4, padx=(0, 1))
            ttk.Button(
                frame,
                text="▼",
                width=2,
                command=lambda idx=i: self._move_xml_down(idx),
            ).grid(row=0, column=5, padx=(0, 1))
            ttk.Button(
                frame,
                text="✕",
                width=2,
                command=lambda idx=i: self._remove_xml(idx),
            ).grid(row=0, column=6, padx=(0, 1))
            ttk.Button(
                frame,
                text="Ver…",
                width=4,
                command=lambda p=xml_path: self._show_preview(p),
            ).grid(row=0, column=7, padx=(0, 2))

            xml_warnings = self._xml_validations.get(xml_path, [])
            warn_btn = ttk.Button(
                frame,
                text="⚠",
                width=2,
                command=lambda p=xml_path: self._show_xml_warnings(p),
            )
            warn_btn.grid(row=0, column=8, padx=(0, 2))
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

    def _move_xml_up(self, idx: int) -> None:
        if idx > 0:
            self.state.xml_paths[idx], self.state.xml_paths[idx - 1] = (
                self.state.xml_paths[idx - 1],
                self.state.xml_paths[idx],
            )
            self._refresh_xml_rows()

    def _move_xml_down(self, idx: int) -> None:
        if idx < len(self.state.xml_paths) - 1:
            self.state.xml_paths[idx], self.state.xml_paths[idx + 1] = (
                self.state.xml_paths[idx + 1],
                self.state.xml_paths[idx],
            )
            self._refresh_xml_rows()
