"""MPCFillToPDF GUI — pick XML(s) and optional local images, run the pipeline,
open the output folder."""
import os
import queue
import shutil
import threading
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui.paths import output_dir, work_dir
from src.cancellation import Cancelled
from src.downloader import DownloadPermissionError, DownloadTimeoutError
from src.pipeline import run_plan, run_locals_only
from src.precheck import analyze, plan, format_warning, format_merge_info, write_manifest

APP_TITLE = "MPCFillToPDF"
STAGE_LABELS = {
    "download": "Descargando",
    "crop":     "Recortando",
    "pdf":      "Generando PDF",
}

IMAGE_FILETYPES = [
    ("Imágenes", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
    ("Todos", "*.*"),
]

FRONT_NAME_WIDTH = 28  # chars shown before ellipsizing a front filename


def _ellipsize(name: str, width: int) -> str:
    if len(name) <= width:
        return name
    return name[: max(0, width - 1)] + "…"


_PB_DOWNLOAD_COLOR = "#0078d4"  # Windows blue
_PB_CROP_COLOR     = "#2e7d32"  # dark green


class _XmlPb(tk.Canvas):
    """Canvas progress bar with centered text overlay — works on all themes."""
    _W = 130
    _H = 18
    _TROUGH = "#dde5f0"
    _BORDER = "#9aafc7"
    _TEXT   = "#f0f0f0"

    def __init__(self, parent, **kw):
        super().__init__(
            parent, width=self._W, height=self._H,
            bg=self._TROUGH, highlightthickness=1, highlightbackground=self._BORDER,
            **kw,
        )
        self._bar = self.create_rectangle(0, 0, 0, self._H, fill=_PB_DOWNLOAD_COLOR, outline="")
        self._lbl = self.create_text(
            self._W // 2, self._H // 2, text="",
            fill=self._TEXT, font=("Segoe UI", 8),
        )

    def set_progress(self, pct: float, text: str = "", color: str | None = None) -> None:
        if color is not None:
            self.itemconfigure(self._bar, fill=color)
        filled = int(self._W * max(0.0, min(100.0, pct)) / 100)
        self.coords(self._bar, 0, 0, filled, self._H)
        self.itemconfigure(self._lbl, text=text)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1200x760")
        root.minsize(1000, 660)

        self.xml_paths: list[Path] = []
        self._xml_rows: list[dict] = []
        self.local_fronts: list[Path] = []
        self.local_backs: list[Path] = []
        # Per-front back assignment: None = use XML cardback fallback.
        self.front_back_paths: list[Path | None] = []
        # Per-card "needs MPC bleed crop?" — parallel to fronts/backs.
        self.local_front_crop: list[bool] = []
        self.local_back_crop: list[bool] = []
        # Tk widgets per row (parallel to local_fronts / local_backs).
        self._front_rows: list[dict] = []
        self._back_rows: list[dict] = []

        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.running = False
        self.keep_cache = tk.BooleanVar(value=False)

        self._build_ui()
        self.root.after(80, self._drain_events)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        # Contenedor principal que ocupa toda la ventana
        frm = ttk.Frame(self.root)
        frm.pack(fill=tk.BOTH, expand=True, **pad)

        # 1. SECCIÓN INFERIOR (Controles y Progreso)
        # La empaquetamos primero con side=tk.BOTTOM para que "reserve" su espacio
        bottom_controls = ttk.Frame(frm)
        bottom_controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        self.keep_cache_cb = ttk.Checkbutton(
            bottom_controls, text="Conservar caché de imágenes entre ejecuciones",
            variable=self.keep_cache,
        )
        self.keep_cache_cb.pack(anchor=tk.W)

        ttk.Separator(bottom_controls, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        self.generate_btn = ttk.Button(bottom_controls, text="Generar PDF(s)", command=self._start)
        self.generate_btn.pack(fill=tk.X)
        self.generate_btn.state(["disabled"])

        self.stop_btn = ttk.Button(bottom_controls, text="Detener", command=self._request_stop)

        self.status_var = tk.StringVar(value="Listo. Selecciona uno o más XML o imágenes locales.")
        ttk.Label(bottom_controls, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X, pady=(10, 2))

        self.progress = ttk.Progressbar(bottom_controls, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)

        out_text = f"Carpeta de salida: {output_dir()}"
        self.out_label = ttk.Label(bottom_controls, text=out_text, foreground="#666", anchor=tk.W)
        self.out_label.pack(fill=tk.X, pady=(8, 0))

        # 2. SECCIÓN SUPERIOR (Paneles de archivos)
        # Usamos un frame intermedio que ocupará el RESTO del espacio
        top = ttk.Frame(frm)
        top.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        top.columnconfigure(0, weight=1, uniform="cols")
        top.columnconfigure(1, weight=1, uniform="cols")
        top.rowconfigure(0, weight=1)

        self._build_xml_pane(top)
        self._build_locals_pane(top)

    def _build_xml_pane(self, parent: ttk.Frame) -> None:
        xml_frame = ttk.LabelFrame(parent, text="Archivos XML")
        xml_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        xml_frame.columnconfigure(0, weight=1)
        xml_frame.rowconfigure(0, weight=1)

        xml_list_frame = ttk.Frame(xml_frame)
        xml_list_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 2))
        xml_list_frame.columnconfigure(0, weight=1)
        xml_list_frame.rowconfigure(0, weight=1)

        self.xml_canvas, self.xml_inner, self._xml_window = (
            self._build_scrollable_rows(xml_list_frame)
        )
        self.xml_canvas.bind("<Enter>",
                             lambda _e: self._bind_mousewheel(self.xml_canvas, True))
        self.xml_canvas.bind("<Leave>",
                             lambda _e: self._bind_mousewheel(self.xml_canvas, False))

        self._xml_empty_label = ttk.Label(
            self.xml_inner,
            text="(sin XMLs — usa “Seleccionar XMLs…”)",
            foreground="#777", padding=(8, 10),
        )
        self._xml_empty_label.pack(anchor="w")

        xml_btn_row = ttk.Frame(xml_frame)
        xml_btn_row.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(xml_btn_row, text="Seleccionar XMLs…",
                   command=self._pick_xmls).pack(side=tk.LEFT)
        ttk.Button(xml_btn_row, text="Vaciar",
                   command=self._clear_xmls).pack(side=tk.LEFT, padx=6)

    def _build_locals_pane(self, parent: ttk.Frame) -> None:
        local_frame = ttk.LabelFrame(parent, text="Imágenes locales (opcional)")
        local_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        local_frame.columnconfigure(0, weight=1)
        local_frame.rowconfigure(1, weight=1, uniform="locals")  # backs
        local_frame.rowconfigure(3, weight=2, uniform="locals")  # fronts

        # --- Backs (top) ----------------------------------------------
        ttk.Label(local_frame, text="Traseras (numeradas 1, 2, …):").grid(
            row=0, column=0, sticky="w", padx=6, pady=(6, 2))

        backs_block = ttk.Frame(local_frame)
        backs_block.grid(row=1, column=0, sticky="nsew", padx=6)
        backs_block.columnconfigure(0, weight=1)
        backs_block.rowconfigure(0, weight=1)

        self.backs_canvas, self.backs_inner, self._backs_window = (
            self._build_scrollable_rows(backs_block)
        )
        self.backs_canvas.bind("<Enter>",
                               lambda _e: self._bind_mousewheel(self.backs_canvas, True))
        self.backs_canvas.bind("<Leave>",
                               lambda _e: self._bind_mousewheel(self.backs_canvas, False))

        self._backs_empty_label = ttk.Label(
            self.backs_inner,
            text="(sin traseras — usa “Seleccionar imágenes…”)",
            foreground="#777", padding=(8, 10),
        )
        self._backs_empty_label.pack(anchor="w")

        backs_btn_row = ttk.Frame(backs_block)
        backs_btn_row.grid(row=1, column=0, sticky="ew", pady=(2, 6))
        ttk.Button(backs_btn_row, text="Seleccionar imágenes…",
                   command=self._pick_local_backs).pack(side=tk.LEFT)
        ttk.Button(backs_btn_row, text="Vaciar",
                   command=self._clear_local_backs).pack(side=tk.LEFT, padx=6)

        ttk.Separator(local_frame, orient=tk.HORIZONTAL).grid(
            row=2, column=0, sticky="ew", padx=6, pady=(4, 4))

        # --- Fronts (bottom, scrollable rows with per-front back combo) -----
        fronts_block = ttk.Frame(local_frame)
        fronts_block.grid(row=3, column=0, sticky="nsew", padx=6, pady=(0, 6))
        fronts_block.columnconfigure(0, weight=1)
        fronts_block.rowconfigure(1, weight=1)

        ttk.Label(
            fronts_block,
            text="Frontales (asignar trasera por carta):",
        ).grid(row=0, column=0, sticky="w", pady=(2, 4))

        fronts_holder = ttk.Frame(fronts_block)
        fronts_holder.grid(row=1, column=0, sticky="nsew")
        fronts_holder.columnconfigure(0, weight=1)
        fronts_holder.rowconfigure(0, weight=1)

        self.fronts_canvas, self.fronts_inner, self._fronts_window = (
            self._build_scrollable_rows(fronts_holder)
        )
        self.fronts_canvas.bind("<Enter>",
                                lambda _e: self._bind_mousewheel(self.fronts_canvas, True))
        self.fronts_canvas.bind("<Leave>",
                                lambda _e: self._bind_mousewheel(self.fronts_canvas, False))

        self._fronts_empty_label = ttk.Label(
            self.fronts_inner,
            text="(sin frontales — usa “Seleccionar imágenes…”)",
            foreground="#777", padding=(8, 10),
        )
        self._fronts_empty_label.pack(anchor="w")

        fronts_btn_row = ttk.Frame(fronts_block)
        fronts_btn_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(fronts_btn_row, text="Seleccionar imágenes…",
                   command=self._pick_local_fronts).pack(side=tk.LEFT)
        ttk.Button(fronts_btn_row, text="Vaciar",
                   command=self._clear_local_fronts).pack(side=tk.LEFT, padx=6)

    def _build_scrollable_rows(self, parent: ttk.Frame):
        """Create a Canvas + inner Frame pair for a vertically scrolling list
        of per-row widgets. Returns (canvas, inner_frame, window_id)."""
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

    # ------------------------------------------------------------------
    # XML pickers
    # ------------------------------------------------------------------
    def _pick_xmls(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecciona archivos XML de MPCFill",
            filetypes=[("Archivos XML", "*.xml"), ("Todos", "*.*")],
        )
        added = 0
        for p in paths:
            pp = Path(p)
            if pp not in self.xml_paths:
                self.xml_paths.append(pp)
                added += 1
        if added:
            self._refresh_xml_rows()
            self.status_var.set(f"{len(self.xml_paths)} XML(s) en cola.")
        self._refresh_generate_state()

    def _remove_xml(self, idx: int) -> None:
        if 0 <= idx < len(self.xml_paths):
            del self.xml_paths[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    def _clear_xmls(self) -> None:
        self.xml_paths.clear()
        self._refresh_xml_rows()
        self._refresh_generate_state()

    def _refresh_xml_rows(self) -> None:
        for row in self._xml_rows:
            row["frame"].destroy()
        self._xml_rows.clear()

        if not self.xml_paths:
            self._xml_empty_label.pack(anchor="w")
            return
        self._xml_empty_label.pack_forget()

        for i, xml_path in enumerate(self.xml_paths):
            frame = ttk.Frame(self.xml_inner)
            frame.pack(fill=tk.X, pady=1, padx=2)
            frame.columnconfigure(0, weight=1)

            ttk.Label(
                frame, text=_ellipsize(xml_path.name, 32), anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=(4, 8))

            pb = _XmlPb(frame)
            pb.grid(row=0, column=1, padx=(0, 4))
            pb.grid_remove()

            count_var = tk.StringVar(value="")
            count_lbl = ttk.Label(frame, textvariable=count_var, width=9, anchor="e")
            count_lbl.grid(row=0, column=2, padx=(0, 4))
            count_lbl.grid_remove()

            ttk.Button(
                frame, text="✕", width=2,
                command=lambda idx=i: self._remove_xml(idx),
            ).grid(row=0, column=3, padx=(0, 2))

            self._xml_rows.append({
                "frame": frame, "pb": pb,
                "count_var": count_var, "count_lbl": count_lbl,
            })

        self.xml_inner.update_idletasks()
        self.xml_canvas.configure(scrollregion=self.xml_canvas.bbox("all"))

    def _show_xml_download_progress(self, xml_name: str, done: int, total: int) -> None:
        for xml_path, row in zip(self.xml_paths, self._xml_rows):
            if xml_path.name == xml_name:
                pct = (done / total * 100.0) if total else 100.0
                row["pb"].set_progress(pct, "Descargando", color=_PB_DOWNLOAD_COLOR)
                row["count_var"].set(f"{done}/{total}")
                row["pb"].grid()
                row["count_lbl"].grid()
                break

    def _show_xml_crop_progress(self, xml_name: str, done: int, total: int) -> None:
        for xml_path, row in zip(self.xml_paths, self._xml_rows):
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

    # ------------------------------------------------------------------
    # Local back pickers
    # ------------------------------------------------------------------
    def _pick_local_backs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecciona imágenes locales (traseras)",
            filetypes=IMAGE_FILETYPES,
        )
        was_empty = not self.local_backs
        added = False
        for p in paths:
            pp = Path(p)
            if pp not in self.local_backs:
                self.local_backs.append(pp)
                self.local_back_crop.append(False)
                added = True
        if added:
            # Going from 0 → ≥1 backs: auto-assign the new first back to any
            # fronts that don't already have an explicit pick.
            if was_empty and self.local_backs:
                first = self.local_backs[0]
                for i, assigned in enumerate(self.front_back_paths):
                    if assigned is None:
                        self.front_back_paths[i] = first
            self._refresh_back_rows()
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _remove_back(self, idx: int) -> None:
        if not (0 <= idx < len(self.local_backs)):
            return
        removed_path = self.local_backs[idx]
        del self.local_backs[idx]
        del self.local_back_crop[idx]
        for i, assigned in enumerate(self.front_back_paths):
            if assigned == removed_path:
                self.front_back_paths[i] = None
        self._refresh_back_rows()
        self._refresh_front_rows()
        self._refresh_generate_state()

    def _clear_local_backs(self) -> None:
        if not self.local_backs:
            return
        self.local_backs.clear()
        self.local_back_crop.clear()
        # All explicit assignments are now invalid → fall back to default.
        self.front_back_paths = [None] * len(self.front_back_paths)
        self._refresh_back_rows()
        self._refresh_front_rows()
        self._refresh_generate_state()

    def _on_back_crop_change(self, idx: int, var: tk.BooleanVar) -> None:
        if 0 <= idx < len(self.local_back_crop):
            self.local_back_crop[idx] = bool(var.get())

    def _refresh_back_rows(self) -> None:
        for row in self._back_rows:
            row["frame"].destroy()
        self._back_rows.clear()

        if not self.local_backs:
            self._backs_empty_label.pack(anchor="w")
            return
        self._backs_empty_label.pack_forget()

        for i, back_path in enumerate(self.local_backs):
            row = ttk.Frame(self.backs_inner)
            row.pack(fill=tk.X, pady=1, padx=2)

            ttk.Label(row, text=f"{i + 1:>3}.", width=4,
                      anchor="e").pack(side=tk.LEFT)
            ttk.Label(
                row, text=_ellipsize(back_path.name, FRONT_NAME_WIDTH),
                width=FRONT_NAME_WIDTH + 1, anchor="w",
            ).pack(side=tk.LEFT, padx=(4, 8))

            crop_var = tk.BooleanVar(value=self.local_back_crop[i])
            ttk.Checkbutton(
                row, text="Recortar bordes extra", variable=crop_var,
                command=lambda idx=i, v=crop_var: self._on_back_crop_change(idx, v),
            ).pack(side=tk.LEFT, padx=(4, 6))

            ttk.Button(
                row, text="✕", width=2,
                command=lambda idx=i: self._remove_back(idx),
            ).pack(side=tk.RIGHT)

            self._back_rows.append({"frame": row, "crop_var": crop_var})

        self.backs_inner.update_idletasks()
        self.backs_canvas.configure(scrollregion=self.backs_canvas.bbox("all"))

    # ------------------------------------------------------------------
    # Local front pickers + per-row widgets
    # ------------------------------------------------------------------
    def _pick_local_fronts(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecciona imágenes locales (frontales)",
            filetypes=IMAGE_FILETYPES,
        )
        default_back = self.local_backs[0] if self.local_backs else None
        added = False
        for p in paths:
            pp = Path(p)
            if pp not in self.local_fronts:
                self.local_fronts.append(pp)
                self.front_back_paths.append(default_back)
                self.local_front_crop.append(False)
                added = True
        if added:
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _clear_local_fronts(self) -> None:
        if not self.local_fronts:
            return
        self.local_fronts.clear()
        self.front_back_paths.clear()
        self.local_front_crop.clear()
        self._refresh_front_rows()
        self._refresh_generate_state()

    def _remove_front(self, idx: int) -> None:
        if 0 <= idx < len(self.local_fronts):
            del self.local_fronts[idx]
            del self.front_back_paths[idx]
            del self.local_front_crop[idx]
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _on_front_back_change(self, idx: int, var: tk.StringVar) -> None:
        """Combobox callback: maps the displayed choice back to a Path or None."""
        choice = var.get()
        try:
            n = int(choice)
        except (TypeError, ValueError):
            self.front_back_paths[idx] = None  # "—" = no explicit choice
            return
        if 1 <= n <= len(self.local_backs):
            self.front_back_paths[idx] = self.local_backs[n - 1]

    def _on_front_crop_change(self, idx: int, var: tk.BooleanVar) -> None:
        if 0 <= idx < len(self.local_front_crop):
            self.local_front_crop[idx] = bool(var.get())

    def _refresh_front_rows(self) -> None:
        """Tear down and rebuild the per-front rows so indices/combos stay in
        sync with `self.local_fronts` and `self.local_backs`."""
        for row in self._front_rows:
            row["frame"].destroy()
        self._front_rows.clear()

        if not self.local_fronts:
            self._fronts_empty_label.pack(anchor="w")
            return
        self._fronts_empty_label.pack_forget()

        numbered = [str(i) for i in range(1, len(self.local_backs) + 1)]
        combo_values = ["—", *numbered]
        backs_present = bool(numbered)

        for i, front_path in enumerate(self.local_fronts):
            row = ttk.Frame(self.fronts_inner)
            row.pack(fill=tk.X, pady=1, padx=2)

            ttk.Label(row, text=f"{i + 1:>3}.", width=4,
                      anchor="e").pack(side=tk.LEFT)
            ttk.Label(
                row, text=_ellipsize(front_path.name, FRONT_NAME_WIDTH),
                width=FRONT_NAME_WIDTH + 1, anchor="w",
            ).pack(side=tk.LEFT, padx=(4, 8))

            ttk.Label(row, text="Trasera:").pack(side=tk.LEFT)

            # If a previously picked back is no longer in the list, drop the
            # assignment so the combo shows "—" (use XML cardback fallback).
            assigned = self.front_back_paths[i]
            if assigned is not None and assigned not in self.local_backs:
                assigned = None
                self.front_back_paths[i] = None
            var = tk.StringVar()
            if assigned is None:
                var.set("—")
            else:
                var.set(str(self.local_backs.index(assigned) + 1))
            combo = ttk.Combobox(
                row, values=combo_values, textvariable=var,
                state="readonly" if backs_present else "disabled",
                width=4,
            )
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, idx=i, v=var: self._on_front_back_change(idx, v),
            )
            combo.pack(side=tk.LEFT, padx=(4, 6))

            crop_var = tk.BooleanVar(value=self.local_front_crop[i])
            ttk.Checkbutton(
                row, text="Recortar bordes extra", variable=crop_var,
                command=lambda idx=i, v=crop_var: self._on_front_crop_change(idx, v),
            ).pack(side=tk.LEFT, padx=(4, 6))

            ttk.Button(
                row, text="✕", width=2,
                command=lambda idx=i: self._remove_front(idx),
            ).pack(side=tk.RIGHT)

            self._front_rows.append(
                {"frame": row, "var": var, "combo": combo, "crop_var": crop_var},
            )

        # Keep scrollregion fresh after layout settles.
        self.fronts_inner.update_idletasks()
        self.fronts_canvas.configure(scrollregion=self.fronts_canvas.bbox("all"))

    # ------------------------------------------------------------------
    # Mousewheel scroll over the active row list
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Run controls
    # ------------------------------------------------------------------
    def _refresh_generate_state(self) -> None:
        ready = False
        if self.xml_paths:
            ready = True
        elif self.local_fronts and self.local_backs:
            # locals-only requires at least one back (acts as the cardback)
            ready = True
        if ready and not self.running:
            self.generate_btn.state(["!disabled"])
        else:
            self.generate_btn.state(["disabled"])

    def _resolve_extra_backs(self) -> list[Path | None]:
        """One entry per local front: the explicit Path the user chose, or
        `None` to fall back to the XML cardback (or `local_cardback` in
        locals-only mode)."""
        result: list[Path | None] = []
        for i, _ in enumerate(self.local_fronts):
            assigned = (
                self.front_back_paths[i]
                if i < len(self.front_back_paths)
                else None
            )
            result.append(assigned)
        return result

    def _build_crop_map(self) -> dict[Path, bool]:
        """Per-image crop setting for every local image. Same path appearing
        as both a front and a back gets the front's setting last (overrides
        the back's), which is fine — they map to the same on-disk file."""
        m: dict[Path, bool] = {}
        for p, c in zip(self.local_backs, self.local_back_crop):
            m[p] = c
        for p, c in zip(self.local_fronts, self.local_front_crop):
            m[p] = c
        return m

    def _start(self) -> None:
        if self.running:
            return

        if not self.xml_paths and not self.local_fronts:
            messagebox.showerror(APP_TITLE, "Selecciona al menos un XML o imágenes locales.")
            return

        if not self.xml_paths and not self.local_backs:
            messagebox.showerror(
                APP_TITLE,
                "Sin XMLs se necesita al menos un back local "
                "(el primero actúa como reverso por defecto).",
            )
            return

        reports = []
        plan_ = None
        if self.xml_paths:
            try:
                reports = analyze(self.xml_paths)
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"No se pudo analizar el XML:\n{e}")
                return

            plan_ = plan(reports, local_count=len(self.local_fronts))

            merge_info = format_merge_info(plan_)
            if merge_info:
                messagebox.showinfo(APP_TITLE, merge_info)

            warning = format_warning(plan_)
            if warning:
                if not messagebox.askyesno(
                    APP_TITLE,
                    warning + "\n\n¿Continuar de todos modos?",
                    icon=messagebox.WARNING,
                ):
                    return

        self.running = True
        self.cancel_event.clear()
        self.generate_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.stop_btn.pack(fill=tk.X, pady=(4, 0), after=self.generate_btn)
        self.progress["value"] = 0
        self.status_var.set("Preparando…")
        self._reset_xml_download_progress()
        self.worker = threading.Thread(
            target=self._work, args=(plan_, reports), daemon=True,
        )
        self.worker.start()

    def _request_stop(self) -> None:
        if not self.running:
            return
        self.cancel_event.set()
        self.stop_btn.state(["disabled"])
        self.status_var.set("Cancelando…")

    def _work(self, plan_, reports) -> None:
        run_dir = None
        wd = None
        try:
            out = output_dir()
            wd = work_dir()
            run_dir = out / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
            run_dir.mkdir(parents=True, exist_ok=True)
            generated: list[Path] = []
            extra_backs = self._resolve_extra_backs()
            crop_map = self._build_crop_map()
            if plan_ is not None:
                # label shown during download/crop (global phases)
                _pdf_label = [""]

                def cb(stage, done, total):
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

                pdfs = run_plan(
                    plan_.jobs, run_dir, wd, cb,
                    cancel_event=self.cancel_event,
                    extra_fronts=list(self.local_fronts) or None,
                    extra_backs=list(extra_backs) or None,
                    local_crop_map=dict(crop_map) or None,
                    on_job_pdf_start=on_job_pdf_start,
                    on_xml_download_progress=on_xml_download_progress,
                    on_xml_crop_progress=on_xml_crop_progress,
                )
                generated.extend(pdfs)
                manifest = write_manifest(plan_, reports, run_dir)
            else:
                # Locals-only run. Back #1 acts as the default cardback.
                base = "locales"
                self.events.put(("file", 1, 1, f"{base} (solo imágenes locales)"))
                def cb(stage, done, total, _label=base):
                    self.events.put(("progress", stage, done, total, _label))
                pdfs = run_locals_only(
                    list(self.local_fronts), self.local_backs[0],
                    run_dir, base, wd, cb,
                    cancel_event=self.cancel_event,
                    extra_backs=list(extra_backs),
                    local_crop_map=dict(crop_map),
                )
                generated.extend(pdfs)
                manifest = None
            if not self.keep_cache.get():
                self._cleanup_workdir(wd)
            self.events.put(("done", generated, manifest, run_dir))
        except DownloadPermissionError as e:
            self.events.put(("permission_error", e.card_name, e.xml_name, e.position))
        except DownloadTimeoutError as e:
            self.events.put(("timeout_error", e.card_name, e.xml_name, e.position))
        except Cancelled:
            self.events.put(("cancelled", run_dir, wd))
        except Exception as e:
            self.events.put(("error", f"{e}\n\n{traceback.format_exc()}"))

    @staticmethod
    def _cleanup_workdir(wd: Path) -> None:
        for sub in ("raw", "bled"):
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
            self.status_var.set(f"{name} — {label}: {done}/{total}")
        elif kind == "done":
            _, pdfs, manifest, run_dir = ev
            self.progress["value"] = 100
            extra = f" Resumen en {manifest.name}." if manifest else ""
            self.status_var.set(f"Listo. {len(pdfs)} PDF(s) generados en {run_dir.name}.{extra}")
            self._finish_running()
            self._open_output_folder(run_dir)
        elif kind == "xml_download_progress":
            _, xml_name, done, total = ev
            self._show_xml_download_progress(xml_name, done, total)
        elif kind == "xml_crop_progress":
            _, xml_name, done, total = ev
            self._show_xml_crop_progress(xml_name, done, total)
        elif kind == "cancelled":
            _, run_dir, wd = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            if wd is not None and not self.keep_cache.get():
                self._cleanup_workdir(wd)
            self.progress["value"] = 0
            self.status_var.set("Proceso detenido.")
            self._finish_running()
        elif kind == "permission_error":
            _, card_name, xml_name, position = ev
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
            messagebox.showerror(APP_TITLE, "\n\n".join(parts))
        elif kind == "timeout_error":
            _, card_name, xml_name, position = ev
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
            messagebox.showerror(APP_TITLE, "\n\n".join(parts))
        elif kind == "error":
            _, msg = ev
            self.status_var.set("Error durante la generación.")
            self._finish_running()
            messagebox.showerror(APP_TITLE, msg)

    def _finish_running(self) -> None:
        """Return to idle state after done / cancelled / error."""
        self.running = False
        self.worker = None
        self.stop_btn.pack_forget()
        self.stop_btn.state(["!disabled"])
        self._refresh_generate_state()

    def _open_output_folder(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # Windows
        except AttributeError:
            import subprocess
            opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
            subprocess.Popen([opener, str(path)])


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
