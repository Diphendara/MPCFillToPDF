"""LocalsTabMixin — local image panel methods for the App class."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from gui.widgets import FRONT_NAME_WIDTH, IMAGE_FILETYPES, WINDND_AVAILABLE, ImageTooltip, ellipsize
from src.constants import SUPPORTED_IMAGE_EXTS


class LocalsTabMixin:
    """Methods for the local images pane (backs + fronts with per-card back assignment)."""

    def _build_locals_pane(self, parent: ttk.Frame) -> None:
        local_frame = ttk.LabelFrame(parent, text="Imágenes locales (opcional)")
        local_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self._locals_drop_frame = local_frame
        local_frame.columnconfigure(0, weight=1)
        local_frame.rowconfigure(1, weight=1, uniform="locals")
        local_frame.rowconfigure(3, weight=2, uniform="locals")

        backs_hdr = ttk.Frame(local_frame)
        backs_hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        ttk.Label(backs_hdr, text="Traseras (numeradas 1, 2, …):").pack(side=tk.LEFT)
        self._back_crop_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            backs_hdr,
            text="Recortar todas",
            variable=self._back_crop_all,
            command=self._on_back_crop_all,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        backs_block = ttk.Frame(local_frame)
        backs_block.grid(row=1, column=0, sticky="nsew", padx=6)
        backs_block.columnconfigure(0, weight=1)
        backs_block.rowconfigure(0, weight=1)

        self.backs_canvas, self.backs_inner, self._backs_window = self._build_scrollable_rows(
            backs_block
        )
        self.backs_canvas.bind("<Enter>", lambda _e: self._bind_mousewheel(self.backs_canvas, True))
        self.backs_canvas.bind(
            "<Leave>", lambda _e: self._bind_mousewheel(self.backs_canvas, False)
        )

        dnd_hint = " o arrastra aquí" if WINDND_AVAILABLE else ""
        self._backs_empty_label = ttk.Label(
            self.backs_inner,
            text=f"(sin traseras — usa «Seleccionar imágenes…»{dnd_hint})",
            foreground="#777",
            padding=(8, 10),
        )
        self._backs_empty_label.pack(anchor="w")

        backs_btn_row = ttk.Frame(backs_block)
        backs_btn_row.grid(row=1, column=0, sticky="ew", pady=(2, 6))
        ttk.Button(
            backs_btn_row, text="Seleccionar imágenes…", command=self._pick_local_backs
        ).pack(side=tk.LEFT)
        ttk.Button(backs_btn_row, text="Vaciar", command=self._clear_local_backs).pack(
            side=tk.LEFT, padx=6
        )

        ttk.Separator(local_frame, orient=tk.HORIZONTAL).grid(
            row=2, column=0, sticky="ew", padx=6, pady=(4, 4)
        )

        fronts_block = ttk.Frame(local_frame)
        fronts_block.grid(row=3, column=0, sticky="nsew", padx=6, pady=(0, 6))
        fronts_block.columnconfigure(0, weight=1)
        fronts_block.rowconfigure(1, weight=1)

        fronts_hdr = ttk.Frame(fronts_block)
        fronts_hdr.grid(row=0, column=0, sticky="ew", pady=(2, 4))
        self._fronts_header_var = tk.StringVar(value="Frontales (asignar trasera por carta):")
        ttk.Label(fronts_hdr, textvariable=self._fronts_header_var).pack(side=tk.LEFT)
        self._front_crop_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            fronts_hdr,
            text="Recortar todas",
            variable=self._front_crop_all,
            command=self._on_front_crop_all,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        fronts_holder = ttk.Frame(fronts_block)
        fronts_holder.grid(row=1, column=0, sticky="nsew")
        fronts_holder.columnconfigure(0, weight=1)
        fronts_holder.rowconfigure(0, weight=1)

        self.fronts_canvas, self.fronts_inner, self._fronts_window = self._build_scrollable_rows(
            fronts_holder
        )
        self.fronts_canvas.bind(
            "<Enter>", lambda _e: self._bind_mousewheel(self.fronts_canvas, True)
        )
        self.fronts_canvas.bind(
            "<Leave>", lambda _e: self._bind_mousewheel(self.fronts_canvas, False)
        )

        dnd_hint = " o arrastra aquí" if WINDND_AVAILABLE else ""
        self._fronts_empty_label = ttk.Label(
            self.fronts_inner,
            text=f"(sin frontales — usa «Seleccionar imágenes…»{dnd_hint})",
            foreground="#777",
            padding=(8, 10),
        )
        self._fronts_empty_label.pack(anchor="w")

        fronts_btn_row = ttk.Frame(fronts_block)
        fronts_btn_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(
            fronts_btn_row, text="Seleccionar imágenes…", command=self._pick_local_fronts
        ).pack(side=tk.LEFT)
        ttk.Button(fronts_btn_row, text="Vaciar", command=self._clear_local_fronts).pack(
            side=tk.LEFT, padx=6
        )

    def _pick_local_backs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecciona imágenes locales (traseras)",
            filetypes=IMAGE_FILETYPES,
        )
        was_empty = not self.state.local_backs
        added = False
        for p in paths:
            pp = Path(p)
            if pp not in self.state.local_backs:
                self.state.local_backs.append(pp)
                self.state.local_back_crop.append(False)
                added = True
        if added:
            if was_empty and self.state.local_backs:
                first = self.state.local_backs[0]
                for i, assigned in enumerate(self.state.front_back_paths):
                    if assigned is None:
                        self.state.front_back_paths[i] = first
            self._refresh_back_rows()
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _remove_back(self, idx: int) -> None:
        if not (0 <= idx < len(self.state.local_backs)):
            return
        removed_path = self.state.local_backs[idx]
        del self.state.local_backs[idx]
        del self.state.local_back_crop[idx]
        for i, assigned in enumerate(self.state.front_back_paths):
            if assigned == removed_path:
                self.state.front_back_paths[i] = None
        self._refresh_back_rows()
        self._refresh_front_rows()
        self._refresh_generate_state()

    def _clear_local_backs(self) -> None:
        if not self.state.local_backs:
            return
        self.state.local_backs.clear()
        self.state.local_back_crop.clear()
        self.state.front_back_paths = [None] * len(self.state.front_back_paths)
        self._refresh_back_rows()
        self._refresh_front_rows()
        self._refresh_generate_state()

    def _on_back_crop_change(self, idx: int, var: tk.BooleanVar) -> None:
        if 0 <= idx < len(self.state.local_back_crop):
            self.state.local_back_crop[idx] = bool(var.get())

    def _refresh_back_rows(self) -> None:
        for row in self._back_rows:
            row["frame"].destroy()
        self._back_rows.clear()

        if not self.state.local_backs:
            self._backs_empty_label.pack(anchor="w")
            return
        self._backs_empty_label.pack_forget()

        for i, back_path in enumerate(self.state.local_backs):
            row = ttk.Frame(self.backs_inner)
            row.pack(fill=tk.X, pady=1, padx=2)

            ttk.Label(row, text=f"{i + 1:>3}.", width=4, anchor="e").pack(side=tk.LEFT)
            name_lbl = ttk.Label(
                row,
                text=ellipsize(back_path.name, FRONT_NAME_WIDTH),
                width=FRONT_NAME_WIDTH + 1,
                anchor="w",
            )
            name_lbl.pack(side=tk.LEFT, padx=(4, 8))
            ImageTooltip(name_lbl, back_path)

            crop_var = tk.BooleanVar(value=self.state.local_back_crop[i])
            ttk.Checkbutton(
                row,
                text="Recortar bordes extra",
                variable=crop_var,
                command=lambda idx=i, v=crop_var: self._on_back_crop_change(idx, v),
            ).pack(side=tk.LEFT, padx=(4, 6))

            ttk.Button(
                row,
                text="✕",
                width=2,
                command=lambda idx=i: self._remove_back(idx),
            ).pack(side=tk.RIGHT)
            ttk.Button(
                row,
                text="▼",
                width=2,
                command=lambda idx=i: self._move_back_down(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))
            ttk.Button(
                row,
                text="▲",
                width=2,
                command=lambda idx=i: self._move_back_up(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))

            self._back_rows.append({"frame": row, "crop_var": crop_var})

        self.backs_inner.update_idletasks()
        self.backs_canvas.configure(scrollregion=self.backs_canvas.bbox("all"))

    def _pick_local_fronts(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecciona imágenes locales (frontales)",
            filetypes=IMAGE_FILETYPES,
        )
        default_back = self.state.local_backs[0] if self.state.local_backs else None
        added = False
        for p in paths:
            pp = Path(p)
            if pp not in self.state.local_fronts:
                self.state.local_fronts.append(pp)
                self.state.front_back_paths.append(default_back)
                self.state.local_front_crop.append(False)
                added = True
        if added:
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _clear_local_fronts(self) -> None:
        if not self.state.local_fronts:
            return
        self.state.local_fronts.clear()
        self.state.front_back_paths.clear()
        self.state.local_front_crop.clear()
        self._refresh_front_rows()
        self._refresh_generate_state()

    def _remove_front(self, idx: int) -> None:
        if 0 <= idx < len(self.state.local_fronts):
            del self.state.local_fronts[idx]
            del self.state.front_back_paths[idx]
            del self.state.local_front_crop[idx]
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _on_front_back_change(self, idx: int, var: tk.StringVar) -> None:
        """Combobox callback: maps the displayed choice back to a Path or None."""
        choice = var.get()
        try:
            n = int(choice)
        except (TypeError, ValueError):
            self.state.front_back_paths[idx] = None
            return
        if 1 <= n <= len(self.state.local_backs):
            self.state.front_back_paths[idx] = self.state.local_backs[n - 1]

    def _on_front_crop_change(self, idx: int, var: tk.BooleanVar) -> None:
        if 0 <= idx < len(self.state.local_front_crop):
            self.state.local_front_crop[idx] = bool(var.get())

    def _on_front_crop_all(self) -> None:
        val = bool(self._front_crop_all.get())
        for i in range(len(self.state.local_front_crop)):
            self.state.local_front_crop[i] = val
        self._refresh_front_rows()

    def _on_back_crop_all(self) -> None:
        val = bool(self._back_crop_all.get())
        for i in range(len(self.state.local_back_crop)):
            self.state.local_back_crop[i] = val
        self._refresh_back_rows()

    def _refresh_front_rows(self) -> None:
        for row in self._front_rows:
            row["frame"].destroy()
        self._front_rows.clear()

        if not self.state.local_fronts:
            self._fronts_empty_label.pack(anchor="w")
            self._fronts_header_var.set("Frontales (asignar trasera por carta):")
            return
        self._fronts_empty_label.pack_forget()

        numbered = [str(i) for i in range(1, len(self.state.local_backs) + 1)]
        combo_values = ["—", *numbered]
        backs_present = bool(numbered)

        for i, front_path in enumerate(self.state.local_fronts):
            row = ttk.Frame(self.fronts_inner)
            row.pack(fill=tk.X, pady=1, padx=2)

            ttk.Label(row, text=f"{i + 1:>3}.", width=4, anchor="e").pack(side=tk.LEFT)
            front_name_lbl = ttk.Label(
                row,
                text=ellipsize(front_path.name, FRONT_NAME_WIDTH),
                width=FRONT_NAME_WIDTH + 1,
                anchor="w",
            )
            front_name_lbl.pack(side=tk.LEFT, padx=(4, 8))
            ImageTooltip(front_name_lbl, front_path)

            ttk.Label(row, text="Trasera:").pack(side=tk.LEFT)

            assigned = self.state.front_back_paths[i]
            if assigned is not None and assigned not in self.state.local_backs:
                assigned = None
                self.state.front_back_paths[i] = None
            var = tk.StringVar()
            if assigned is None:
                var.set("—")
            else:
                var.set(str(self.state.local_backs.index(assigned) + 1))
            combo = ttk.Combobox(
                row,
                values=combo_values,
                textvariable=var,
                state="readonly" if backs_present else "disabled",
                width=4,
            )
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, idx=i, v=var: self._on_front_back_change(idx, v),
            )
            combo.pack(side=tk.LEFT, padx=(4, 6))

            crop_var = tk.BooleanVar(value=self.state.local_front_crop[i])
            ttk.Checkbutton(
                row,
                text="Recortar bordes extra",
                variable=crop_var,
                command=lambda idx=i, v=crop_var: self._on_front_crop_change(idx, v),
            ).pack(side=tk.LEFT, padx=(4, 6))

            ttk.Button(
                row,
                text="✕",
                width=2,
                command=lambda idx=i: self._remove_front(idx),
            ).pack(side=tk.RIGHT)
            ttk.Button(
                row,
                text="▼",
                width=2,
                command=lambda idx=i: self._move_front_down(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))
            ttk.Button(
                row,
                text="▲",
                width=2,
                command=lambda idx=i: self._move_front_up(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))

            self._front_rows.append(
                {"frame": row, "var": var, "combo": combo, "crop_var": crop_var},
            )

        self.fronts_inner.update_idletasks()
        self.fronts_canvas.configure(scrollregion=self.fronts_canvas.bbox("all"))

        total = len(self.state.local_fronts)
        self._fronts_header_var.set(
            f"Frontales (asignar trasera por carta):   Actualmente: {total} cartas"
        )

    def _move_back_up(self, idx: int) -> None:
        if idx > 0:
            self.state.local_backs[idx], self.state.local_backs[idx - 1] = (
                self.state.local_backs[idx - 1],
                self.state.local_backs[idx],
            )
            self.state.local_back_crop[idx], self.state.local_back_crop[idx - 1] = (
                self.state.local_back_crop[idx - 1],
                self.state.local_back_crop[idx],
            )
            self._refresh_back_rows()
            self._refresh_front_rows()

    def _move_back_down(self, idx: int) -> None:
        if idx < len(self.state.local_backs) - 1:
            self.state.local_backs[idx], self.state.local_backs[idx + 1] = (
                self.state.local_backs[idx + 1],
                self.state.local_backs[idx],
            )
            self.state.local_back_crop[idx], self.state.local_back_crop[idx + 1] = (
                self.state.local_back_crop[idx + 1],
                self.state.local_back_crop[idx],
            )
            self._refresh_back_rows()
            self._refresh_front_rows()

    def _move_front_up(self, idx: int) -> None:
        if idx > 0:
            self.state.local_fronts[idx], self.state.local_fronts[idx - 1] = (
                self.state.local_fronts[idx - 1],
                self.state.local_fronts[idx],
            )
            self.state.front_back_paths[idx], self.state.front_back_paths[idx - 1] = (
                self.state.front_back_paths[idx - 1],
                self.state.front_back_paths[idx],
            )
            self.state.local_front_crop[idx], self.state.local_front_crop[idx - 1] = (
                self.state.local_front_crop[idx - 1],
                self.state.local_front_crop[idx],
            )
            self._refresh_front_rows()

    def _move_front_down(self, idx: int) -> None:
        if idx < len(self.state.local_fronts) - 1:
            self.state.local_fronts[idx], self.state.local_fronts[idx + 1] = (
                self.state.local_fronts[idx + 1],
                self.state.local_fronts[idx],
            )
            self.state.front_back_paths[idx], self.state.front_back_paths[idx + 1] = (
                self.state.front_back_paths[idx + 1],
                self.state.front_back_paths[idx],
            )
            self.state.local_front_crop[idx], self.state.local_front_crop[idx + 1] = (
                self.state.local_front_crop[idx + 1],
                self.state.local_front_crop[idx],
            )
            self._refresh_front_rows()

    def _on_drop_backs(self, files) -> None:
        paths = self._decode_drop(files)
        was_empty = not self.state.local_backs
        added = False
        for pp in paths:
            if pp.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
                continue
            if pp not in self.state.local_backs:
                self.state.local_backs.append(pp)
                self.state.local_back_crop.append(False)
                added = True
        if added:
            if was_empty and self.state.local_backs:
                first = self.state.local_backs[0]
                for i, assigned in enumerate(self.state.front_back_paths):
                    if assigned is None:
                        self.state.front_back_paths[i] = first
            self._refresh_back_rows()
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _on_drop_fronts(self, files) -> None:
        paths = self._decode_drop(files)
        default_back = self.state.local_backs[0] if self.state.local_backs else None
        added = False
        for pp in paths:
            if pp.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
                continue
            if pp not in self.state.local_fronts:
                self.state.local_fronts.append(pp)
                self.state.front_back_paths.append(default_back)
                self.state.local_front_crop.append(False)
                added = True
        if added:
            self._refresh_front_rows()
            self._refresh_generate_state()
