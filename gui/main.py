"""MPCFillToPDF GUI — pick XML(s) and optional local images, run the pipeline,
open the output folder."""
import io
import logging
import math
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import windnd
    _WINDND_AVAILABLE = True
except ImportError:
    _WINDND_AVAILABLE = False

from PIL import Image, ImageTk
from gui.paths import output_dir, work_dir
from src.cancellation import Cancelled
from src.downloader import (
    DownloadPartialError,
    DownloadPermissionError,
    DownloadRateLimitError,
    DownloadTimeoutError,
)
from src.parser import parse, CardOrder
from src.pipeline import run, run_merged, run_locals_only, run_plan
from src.precheck import (
    CARDS_PER_PAGE,
    analyze,
    check_drive_access,
    collect_drive_ids,
    format_merge_info,
    format_warning,
    plan,
    write_manifest,
)
from src.validator import validate, ValidationWarning

_log = logging.getLogger(__name__)


def _notify(title: str, message: str) -> None:
    """Show a system notification (best-effort; silently ignored if plyer is missing)."""
    try:
        from plyer import notification as _n
        _n.notify(title=title, message=message, app_name=APP_TITLE, timeout=8)
    except Exception:
        pass


APP_TITLE = "MPCFillToPDF"
STAGE_LABELS = {
    "verify":   "Verificando XML",
    "download": "Descargando",
    "crop":     "Procesando imágenes",
    "pdf":      "Generando PDF, Páginas",
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


class _ImageTooltip:
    """Floating image preview that appears when the mouse hovers over a widget."""
    _DELAY_MS = 350
    _MAX_W = 240
    _MAX_H = 336

    def __init__(self, widget: tk.Widget, image_path: Path) -> None:
        self._widget = widget
        self._path = image_path
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        self._photo = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<Destroy>", lambda _e: self._hide(), add="+")

    def _schedule(self, event) -> None:
        self._hide()
        self._after_id = self._widget.after(
            self._DELAY_MS,
            lambda: self._show(event.x_root, event.y_root),
        )

    def _on_motion(self, event) -> None:
        if self._tip and self._tip.winfo_exists():
            self._move(event.x_root, event.y_root)

    def _show(self, x_root: int, y_root: int) -> None:
        if not self._widget.winfo_exists():
            return
        try:
            img = Image.open(self._path).convert("RGB")
        except Exception:
            return
        img.thumbnail((self._MAX_W, self._MAX_H), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        parent = self._widget.winfo_toplevel()
        self._tip = tk.Toplevel(parent)
        self._tip.overrideredirect(True)
        self._tip.attributes("-topmost", True)
        border = tk.Frame(self._tip, bg="#444", padx=2, pady=2)
        border.pack()
        tk.Label(border, image=self._photo, bg="#444").pack()
        self._tip.update_idletasks()
        self._move(x_root, y_root)

    def _move(self, x_root: int, y_root: int) -> None:
        if not (self._tip and self._tip.winfo_exists()):
            return
        tw = self._tip.winfo_width()
        th = self._tip.winfo_height()
        sw = self._tip.winfo_screenwidth()
        sh = self._tip.winfo_screenheight()
        x = x_root + 18
        y = y_root + 18
        if x + tw > sw:
            x = x_root - tw - 8
        if y + th > sh:
            y = y_root - th - 8
        self._tip.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _hide(self, _event=None) -> None:
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._tip and self._tip.winfo_exists():
            self._tip.destroy()
        self._tip = None


class PreviewWindow(tk.Toplevel):
    _THUMB_W = 80
    _THUMB_H = 112
    _COLS = 4
    _THUMB_URL = "https://drive.google.com/thumbnail?id={}&sz=w80"
    _SPINNER = ["◐", "◓", "◑", "◒"]

    def __init__(self, parent: tk.Misc, xml_path: Path, order: CardOrder) -> None:
        super().__init__(parent)
        self.title(f"Vista previa — {xml_path.name}")
        self.geometry("700x520")
        self.resizable(True, True)

        self._cancel = threading.Event()
        self._pending: queue.Queue = queue.Queue()
        self._photo_refs: list = []
        self._spinner_frame: int = 0
        self._loading_labels: list[tk.Label] = []
        self._loading_set: set[int] = set()

        placeholder = Image.new("RGB", (self._THUMB_W, self._THUMB_H), (210, 210, 210))
        self._placeholder_photo = ImageTk.PhotoImage(placeholder)

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(frame, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas)
        wid = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(wid, width=e.width))

        def _scroll(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        self.bind("<MouseWheel>", _scroll)
        canvas.bind("<MouseWheel>", _scroll)
        inner.bind("<MouseWheel>", _scroll)

        self._img_labels: list[tk.Label] = []
        for idx, card in enumerate(order.fronts):
            r, c = divmod(idx, self._COLS)
            cell = ttk.Frame(inner, relief=tk.RIDGE, borderwidth=1)
            cell.grid(row=r, column=c, padx=4, pady=4)
            cell.bind("<MouseWheel>", _scroll)

            lbl_img = tk.Label(cell, image=self._placeholder_photo, bg="#d2d2d2")
            lbl_img.pack()
            lbl_img.bind("<MouseWheel>", _scroll)
            self._img_labels.append(lbl_img)

            loading_lbl = tk.Label(
                cell, text=self._SPINNER[0],
                font=("Segoe UI", 9), fg="#888",
            )
            loading_lbl.pack()
            loading_lbl.bind("<MouseWheel>", _scroll)
            self._loading_labels.append(loading_lbl)
            self._loading_set.add(idx)

            name = _ellipsize(card.name, 12) if card.name else "(sin nombre)"
            name_lbl = tk.Label(cell, text=name, font=("Segoe UI", 7),
                                wraplength=self._THUMB_W)
            name_lbl.pack()
            name_lbl.bind("<MouseWheel>", _scroll)
            count = len(card.slots)
            if count > 1:
                count_lbl = tk.Label(cell, text=f"x{count}",
                                     font=("Segoe UI", 7, "bold"), fg="#555")
                count_lbl.pack()
                count_lbl.bind("<MouseWheel>", _scroll)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain)
        self.after(200, self._tick_spinner)

        self._executor = ThreadPoolExecutor(max_workers=4)
        threading.Thread(target=self._load_all, args=(order,), daemon=True).start()

    def _tick_spinner(self) -> None:
        if self._cancel.is_set() or not self._loading_set:
            return
        self._spinner_frame = (self._spinner_frame + 1) % len(self._SPINNER)
        ch = self._SPINNER[self._spinner_frame]
        for idx in self._loading_set:
            if idx < len(self._loading_labels):
                self._loading_labels[idx].configure(text=ch)
        self.after(200, self._tick_spinner)

    def _fetch(self, drive_id: str) -> bytes:
        import requests as _req
        resp = _req.get(self._THUMB_URL.format(drive_id), timeout=(5, 15))
        resp.raise_for_status()
        return resp.content

    def _load_all(self, order: CardOrder) -> None:
        futs = {
            self._executor.submit(self._fetch, card.drive_id): idx
            for idx, card in enumerate(order.fronts)
        }
        for fut in as_completed(futs):
            if self._cancel.is_set():
                break
            idx = futs[fut]
            try:
                self._pending.put((idx, fut.result()))
            except Exception:
                self._pending.put((idx, None))

    def _drain(self) -> None:
        if self._cancel.is_set():
            return
        try:
            while True:
                idx, data = self._pending.get_nowait()
                self._apply(idx, data)
        except queue.Empty:
            pass
        finally:
            if not self._cancel.is_set():
                self.after(80, self._drain)

    def _apply(self, idx: int, data: bytes | None) -> None:
        if idx >= len(self._img_labels):
            return
        self._loading_set.discard(idx)
        if idx < len(self._loading_labels):
            self._loading_labels[idx].pack_forget()
        if data is None:
            return
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.thumbnail((self._THUMB_W, self._THUMB_H), Image.LANCZOS)
            padded = Image.new("RGB", (self._THUMB_W, self._THUMB_H), (210, 210, 210))
            ox = (self._THUMB_W - img.width) // 2
            oy = (self._THUMB_H - img.height) // 2
            padded.paste(img, (ox, oy))
            photo = ImageTk.PhotoImage(padded)
            self._photo_refs.append(photo)
            self._img_labels[idx].configure(image=photo)
        except Exception:
            pass

    def _on_close(self) -> None:
        self._cancel.set()
        self._executor.shutdown(wait=False)
        self.destroy()


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1200x760")
        root.minsize(1000, 660)

        self.xml_paths: list[Path] = []
        self._xml_rows: list[dict] = []
        self._xml_card_counts: dict[Path, int] = {}
        self._xml_orders: dict[Path, CardOrder] = {}
        self._xml_validations: dict[Path, list[ValidationWarning]] = {}
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
        self._dl_speed_str: str = ""
        self._custom_output_dir: Path | None = None

        self._build_ui()
        self.root.after(80, self._drain_events)
        self.root.after(200, self._setup_dnd)

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
            bottom_controls, text="Guardar en el PC las imágenes entre ejecuciones",
            variable=self.keep_cache,
        )
        self.keep_cache_cb.pack(anchor=tk.W)

        ttk.Separator(bottom_controls, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        self.soriano_btn = ttk.Button(
            bottom_controls, text="Generar PDF con traseras (Para copisteria, con espejo horizontal)",
            command=lambda: self._start(fronts_only=False),
        )
        self.soriano_btn.pack(fill=tk.X)
        self.soriano_btn.state(["disabled"])

        self.fronts_only_btn = ttk.Button(
            bottom_controls, text="Generar PDF solo frontales",
            command=lambda: self._start(fronts_only=True),
        )
        self.fronts_only_btn.pack(fill=tk.X, pady=(4, 0))
        self.fronts_only_btn.state(["disabled"])

        self.stop_btn = ttk.Button(bottom_controls, text="Detener", command=self._request_stop)

        self.status_var = tk.StringVar(value="Listo. Selecciona uno o más XML o imágenes locales.")
        ttk.Label(bottom_controls, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X, pady=(10, 2))

        self.progress = ttk.Progressbar(bottom_controls, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)

        out_row = ttk.Frame(bottom_controls)
        out_row.pack(fill=tk.X, pady=(8, 0))
        self.out_dir_var = tk.StringVar(value=str(output_dir()))
        self.out_label = ttk.Label(out_row, textvariable=self.out_dir_var,
                                   foreground="#666", anchor=tk.W)
        self.out_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(out_row, text="Cambiar…", command=self._pick_output_dir,
                   width=9).pack(side=tk.RIGHT, padx=(6, 0))

        self.timing_var = tk.StringVar(value="")
        ttk.Label(
            bottom_controls, textvariable=self.timing_var,
            foreground="#888", anchor=tk.W,
        ).pack(fill=tk.X)

        # Pre-flight summary (updates whenever XMLs / locals change)
        self._preflight_frame = ttk.LabelFrame(bottom_controls, text="Resumen")
        # Initially hidden; _update_preflight shows it when there's content.
        self._preflight_inner = ttk.Frame(self._preflight_frame)
        self._preflight_inner.pack(fill=tk.X, padx=6, pady=4)
        self._preflight_labels: list[ttk.Label] = []

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
        self._xml_drop_frame = xml_frame
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

        dnd_hint = " o arrastra aquí" if _WINDND_AVAILABLE else ""
        self._xml_empty_label = ttk.Label(
            self.xml_inner,
            text=f"(sin XMLs — usa «Seleccionar XMLs…»{dnd_hint})",
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
        self._locals_drop_frame = local_frame
        local_frame.columnconfigure(0, weight=1)
        local_frame.rowconfigure(1, weight=1, uniform="locals")  # backs
        local_frame.rowconfigure(3, weight=2, uniform="locals")  # fronts

        # --- Backs (top) ----------------------------------------------
        backs_hdr = ttk.Frame(local_frame)
        backs_hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        ttk.Label(backs_hdr, text="Traseras (numeradas 1, 2, …):").pack(side=tk.LEFT)
        self._back_crop_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            backs_hdr, text="Recortar todas",
            variable=self._back_crop_all,
            command=self._on_back_crop_all,
        ).pack(side=tk.RIGHT, padx=(8, 0))

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

        dnd_hint = " o arrastra aquí" if _WINDND_AVAILABLE else ""
        self._backs_empty_label = ttk.Label(
            self.backs_inner,
            text=f"(sin traseras — usa «Seleccionar imágenes…»{dnd_hint})",
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

        fronts_hdr = ttk.Frame(fronts_block)
        fronts_hdr.grid(row=0, column=0, sticky="ew", pady=(2, 4))
        self._fronts_header_var = tk.StringVar(value="Frontales (asignar trasera por carta):")
        ttk.Label(fronts_hdr, textvariable=self._fronts_header_var).pack(side=tk.LEFT)
        self._front_crop_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            fronts_hdr, text="Recortar todas",
            variable=self._front_crop_all,
            command=self._on_front_crop_all,
        ).pack(side=tk.RIGHT, padx=(8, 0))

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

        dnd_hint = " o arrastra aquí" if _WINDND_AVAILABLE else ""
        self._fronts_empty_label = ttk.Label(
            self.fronts_inner,
            text=f"(sin frontales — usa «Seleccionar imágenes…»{dnd_hint})",
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
            self.status_var.set(f"{len(self.xml_paths)} XML(s) en cola.")
        self._refresh_generate_state()

    def _remove_xml(self, idx: int) -> None:
        if 0 <= idx < len(self.xml_paths):
            p = self.xml_paths[idx]
            self._xml_card_counts.pop(p, None)
            self._xml_orders.pop(p, None)
            self._xml_validations.pop(p, None)
            del self.xml_paths[idx]
            self._refresh_xml_rows()
            self._refresh_generate_state()

    def _clear_xmls(self) -> None:
        self.xml_paths.clear()
        self._xml_card_counts.clear()
        self._xml_orders.clear()
        self._xml_validations.clear()
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

            card_count = self._xml_card_counts.get(xml_path)
            cards_text = f"{card_count} cartas" if card_count is not None else ""
            ttk.Label(frame, text=cards_text, foreground="#555", width=10, anchor="e").grid(
                row=0, column=1, padx=(0, 8),
            )

            pb = _XmlPb(frame)
            pb.grid(row=0, column=2, padx=(0, 4))
            pb.grid_remove()

            count_var = tk.StringVar(value="")
            count_lbl = ttk.Label(frame, textvariable=count_var, width=9, anchor="e")
            count_lbl.grid(row=0, column=3, padx=(0, 4))
            count_lbl.grid_remove()

            ttk.Button(
                frame, text="▲", width=2,
                command=lambda idx=i: self._move_xml_up(idx),
            ).grid(row=0, column=4, padx=(0, 1))
            ttk.Button(
                frame, text="▼", width=2,
                command=lambda idx=i: self._move_xml_down(idx),
            ).grid(row=0, column=5, padx=(0, 1))
            ttk.Button(
                frame, text="✕", width=2,
                command=lambda idx=i: self._remove_xml(idx),
            ).grid(row=0, column=6, padx=(0, 1))
            ttk.Button(
                frame, text="Ver…", width=4,
                command=lambda p=xml_path: self._show_preview(p),
            ).grid(row=0, column=7, padx=(0, 2))

            xml_warnings = self._xml_validations.get(xml_path, [])
            warn_btn = ttk.Button(
                frame, text="⚠", width=2,
                command=lambda p=xml_path: self._show_xml_warnings(p),
            )
            warn_btn.grid(row=0, column=8, padx=(0, 2))
            if not xml_warnings:
                warn_btn.grid_remove()

            self._xml_rows.append({
                "frame": frame, "pb": pb,
                "count_var": count_var, "count_lbl": count_lbl,
                "warn_btn": warn_btn,
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
            name_lbl = ttk.Label(
                row, text=_ellipsize(back_path.name, FRONT_NAME_WIDTH),
                width=FRONT_NAME_WIDTH + 1, anchor="w",
            )
            name_lbl.pack(side=tk.LEFT, padx=(4, 8))
            _ImageTooltip(name_lbl, back_path)

            crop_var = tk.BooleanVar(value=self.local_back_crop[i])
            ttk.Checkbutton(
                row, text="Recortar bordes extra", variable=crop_var,
                command=lambda idx=i, v=crop_var: self._on_back_crop_change(idx, v),
            ).pack(side=tk.LEFT, padx=(4, 6))

            ttk.Button(
                row, text="✕", width=2,
                command=lambda idx=i: self._remove_back(idx),
            ).pack(side=tk.RIGHT)
            ttk.Button(
                row, text="▼", width=2,
                command=lambda idx=i: self._move_back_down(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))
            ttk.Button(
                row, text="▲", width=2,
                command=lambda idx=i: self._move_back_up(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))

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

    def _on_front_crop_all(self) -> None:
        val = bool(self._front_crop_all.get())
        for i in range(len(self.local_front_crop)):
            self.local_front_crop[i] = val
        self._refresh_front_rows()

    def _on_back_crop_all(self) -> None:
        val = bool(self._back_crop_all.get())
        for i in range(len(self.local_back_crop)):
            self.local_back_crop[i] = val
        self._refresh_back_rows()

    def _refresh_front_rows(self) -> None:
        """Tear down and rebuild the per-front rows so indices/combos stay in
        sync with `self.local_fronts` and `self.local_backs`."""
        for row in self._front_rows:
            row["frame"].destroy()
        self._front_rows.clear()

        if not self.local_fronts:
            self._fronts_empty_label.pack(anchor="w")
            self._fronts_header_var.set("Frontales (asignar trasera por carta):")
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
            front_name_lbl = ttk.Label(
                row, text=_ellipsize(front_path.name, FRONT_NAME_WIDTH),
                width=FRONT_NAME_WIDTH + 1, anchor="w",
            )
            front_name_lbl.pack(side=tk.LEFT, padx=(4, 8))
            _ImageTooltip(front_name_lbl, front_path)

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
            ttk.Button(
                row, text="▼", width=2,
                command=lambda idx=i: self._move_front_down(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))
            ttk.Button(
                row, text="▲", width=2,
                command=lambda idx=i: self._move_front_up(idx),
            ).pack(side=tk.RIGHT, padx=(0, 1))

            self._front_rows.append(
                {"frame": row, "var": var, "combo": combo, "crop_var": crop_var},
            )

        # Keep scrollregion fresh after layout settles.
        self.fronts_inner.update_idletasks()
        self.fronts_canvas.configure(scrollregion=self.fronts_canvas.bbox("all"))

        total = len(self.local_fronts)
        self._fronts_header_var.set(
            f"Frontales (asignar trasera por carta):   Actualmente: {total} cartas"
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Reorder helpers
    # ------------------------------------------------------------------
    def _move_xml_up(self, idx: int) -> None:
        if idx > 0:
            self.xml_paths[idx], self.xml_paths[idx - 1] = self.xml_paths[idx - 1], self.xml_paths[idx]
            self._refresh_xml_rows()

    def _move_xml_down(self, idx: int) -> None:
        if idx < len(self.xml_paths) - 1:
            self.xml_paths[idx], self.xml_paths[idx + 1] = self.xml_paths[idx + 1], self.xml_paths[idx]
            self._refresh_xml_rows()

    def _move_back_up(self, idx: int) -> None:
        if idx > 0:
            self.local_backs[idx], self.local_backs[idx - 1] = self.local_backs[idx - 1], self.local_backs[idx]
            self.local_back_crop[idx], self.local_back_crop[idx - 1] = self.local_back_crop[idx - 1], self.local_back_crop[idx]
            self._refresh_back_rows()
            self._refresh_front_rows()

    def _move_back_down(self, idx: int) -> None:
        if idx < len(self.local_backs) - 1:
            self.local_backs[idx], self.local_backs[idx + 1] = self.local_backs[idx + 1], self.local_backs[idx]
            self.local_back_crop[idx], self.local_back_crop[idx + 1] = self.local_back_crop[idx + 1], self.local_back_crop[idx]
            self._refresh_back_rows()
            self._refresh_front_rows()

    def _move_front_up(self, idx: int) -> None:
        if idx > 0:
            self.local_fronts[idx], self.local_fronts[idx - 1] = self.local_fronts[idx - 1], self.local_fronts[idx]
            self.front_back_paths[idx], self.front_back_paths[idx - 1] = self.front_back_paths[idx - 1], self.front_back_paths[idx]
            self.local_front_crop[idx], self.local_front_crop[idx - 1] = self.local_front_crop[idx - 1], self.local_front_crop[idx]
            self._refresh_front_rows()

    def _move_front_down(self, idx: int) -> None:
        if idx < len(self.local_fronts) - 1:
            self.local_fronts[idx], self.local_fronts[idx + 1] = self.local_fronts[idx + 1], self.local_fronts[idx]
            self.front_back_paths[idx], self.front_back_paths[idx + 1] = self.front_back_paths[idx + 1], self.front_back_paths[idx]
            self.local_front_crop[idx], self.local_front_crop[idx + 1] = self.local_front_crop[idx + 1], self.local_front_crop[idx]
            self._refresh_front_rows()

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_drop(files) -> list[Path]:
        result = []
        for f in files:
            if isinstance(f, bytes):
                try:
                    f = f.decode(sys.getfilesystemencoding())
                except UnicodeDecodeError:
                    f = f.decode("cp1252", errors="replace")
            result.append(Path(str(f)))
        return result

    def _on_drop_xmls(self, files) -> None:
        paths = self._decode_drop(files)
        added = 0
        for pp in paths:
            if pp.suffix.lower() != ".xml":
                continue
            if pp not in self.xml_paths:
                self.xml_paths.append(pp)
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
            self.status_var.set(f"{len(self.xml_paths)} XML(s) en cola.")
        self._refresh_generate_state()

    def _on_drop_backs(self, files) -> None:
        paths = self._decode_drop(files)
        _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
        was_empty = not self.local_backs
        added = False
        for pp in paths:
            if pp.suffix.lower() not in _IMAGE_EXTS:
                continue
            if pp not in self.local_backs:
                self.local_backs.append(pp)
                self.local_back_crop.append(False)
                added = True
        if added:
            if was_empty and self.local_backs:
                first = self.local_backs[0]
                for i, assigned in enumerate(self.front_back_paths):
                    if assigned is None:
                        self.front_back_paths[i] = first
            self._refresh_back_rows()
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _on_drop_fronts(self, files) -> None:
        paths = self._decode_drop(files)
        _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
        default_back = self.local_backs[0] if self.local_backs else None
        added = False
        for pp in paths:
            if pp.suffix.lower() not in _IMAGE_EXTS:
                continue
            if pp not in self.local_fronts:
                self.local_fronts.append(pp)
                self.front_back_paths.append(default_back)
                self.local_front_crop.append(False)
                added = True
        if added:
            self._refresh_front_rows()
            self._refresh_generate_state()

    def _setup_dnd(self) -> None:
        if not _WINDND_AVAILABLE:
            return
        try:
            for w in (self._xml_drop_frame, self.xml_canvas, self.xml_inner):
                windnd.hook_dropfiles(w, func=self._on_drop_xmls)
            for w in (self.backs_canvas, self.backs_inner):
                windnd.hook_dropfiles(w, func=self._on_drop_backs)
            for w in (self.fronts_canvas, self.fronts_inner):
                windnd.hook_dropfiles(w, func=self._on_drop_fronts)
        except Exception:
            pass

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
    def _pick_output_dir(self) -> None:
        chosen = filedialog.askdirectory(
            title="Selecciona la carpeta de salida para los PDFs",
            initialdir=str(self._custom_output_dir or output_dir()),
        )
        if chosen:
            self._custom_output_dir = Path(chosen)
            self.out_dir_var.set(str(self._custom_output_dir))

    def _effective_output_dir(self) -> Path:
        d = self._custom_output_dir or output_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _update_preflight(self) -> None:
        """Refresh the pre-flight summary panel from current XML + local state."""
        for widget in self._preflight_labels:
            widget.destroy()
        self._preflight_labels.clear()

        if not self.xml_paths and not self.local_fronts:
            self._preflight_frame.pack_forget()
            return

        def _row(parts: list[tuple[str, bool]]) -> None:
            """Create one line: list of (text, is_warn) packed left-to-right."""
            frame = ttk.Frame(self._preflight_inner)
            frame.pack(fill=tk.X)
            self._preflight_labels.append(frame)
            for text, is_warn in parts:
                kw = (
                    {"foreground": "#cc0000", "font": ("Segoe UI", 10, "bold")}
                    if is_warn
                    else {"foreground": "#444"}
                )
                ttk.Label(frame, text=text, anchor=tk.W, **kw).pack(side=tk.LEFT)

        xml_total = 0

        for p in self.xml_paths:
            order = self._xml_orders.get(p)
            if order is None:
                _row([(f"• {p.name}: (no se pudo leer)", False)])
                continue
            n = sum(len(card.slots) for card in order.fronts)
            xml_total += n
            rem = n % CARDS_PER_PAGE
            blanks = (CARDS_PER_PAGE - rem) if rem else 0
            if blanks:
                _row([
                    (f"• {p.name}: {n} cartas, ", False),
                    (f"{blanks} huecos", True),
                ])
            else:
                _row([(f"• {p.name}: {n} cartas", False)])

        local_count = len(self.local_fronts)
        if local_count:
            _row([(f"• Locales: {local_count} carta(s)", False)])

        total_cards = xml_total + local_count
        if total_cards:
            pairs = math.ceil(total_cards / CARDS_PER_PAGE)
            rem = total_cards % CARDS_PER_PAGE
            blanks = (CARDS_PER_PAGE - rem) if rem else 0

            bled_dir = work_dir() / "bled"
            cached = len([f for f in bled_dir.iterdir() if f.is_file()]) if bled_dir.exists() else 0
            cache_str = f" · {cached} imagen(es) en caché" if cached else ""

            if blanks:
                _row([
                    (f"Total: {total_cards} cartas · {pairs} par(es) de páginas{cache_str} · ", False),
                    (f"⚠ {blanks} huecos en la última página", True),
                ])
            else:
                _row([(f"Total: {total_cards} cartas · {pairs} par(es) de páginas{cache_str}", False)])

        self._preflight_frame.pack(fill=tk.X, pady=(8, 0))

    def _refresh_generate_state(self) -> None:
        ready = False
        if self.xml_paths:
            ready = True
        elif self.local_fronts and self.local_backs:
            # locals-only requires at least one back (acts as the cardback)
            ready = True
        if ready and not self.running:
            self.soriano_btn.state(["!disabled"])
            self.fronts_only_btn.state(["!disabled"])
        else:
            self.soriano_btn.state(["disabled"])
            self.fronts_only_btn.state(["disabled"])
        self._update_preflight()

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

    def _start(self, fronts_only: bool = False) -> None:
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
            # Show a single confirmation if any XML has validation warnings.
            all_xml_warnings = [
                (p, ws)
                for p in self.xml_paths
                if (ws := self._xml_validations.get(p))
            ]
            if all_xml_warnings:
                lines = []
                for p, ws in all_xml_warnings:
                    for w in ws:
                        lines.append(f"[{p.name}] {w.message}")
                preview = "\n".join(f"• {l}" for l in lines[:10])
                more = f"\n… y {len(lines) - 10} más" if len(lines) > 10 else ""
                if not messagebox.askyesno(
                    APP_TITLE,
                    f"Se encontraron {len(lines)} advertencia(s) en los XML:\n\n"
                    f"{preview}{more}\n\n¿Continuar de todos modos?",
                    icon=messagebox.WARNING,
                ):
                    return

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
        else:
            # Locals-only: warn if total fronts is not a multiple of 9
            total = len(self.local_fronts)
            rem = total % CARDS_PER_PAGE
            if rem:
                blanks = CARDS_PER_PAGE - rem
                s = "hueco" if blanks == 1 else "huecos"
                warning = (
                    f"Aviso: {total} carta(s) no es múltiplo de 9.\n"
                    f"La última página tendrá {blanks} {s} en blanco "
                    "(la imprenta cobra la página entera aunque no esté llena)."
                    "\n\n¿Continuar de todos modos?"
                )
                if not messagebox.askyesno(APP_TITLE, warning, icon=messagebox.WARNING):
                    return

        self.running = True
        self.cancel_event.clear()
        self._dl_speed_str = ""
        self.timing_var.set("")
        self.soriano_btn.state(["disabled"])
        self.fronts_only_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.stop_btn.pack(fill=tk.X, pady=(4, 0), after=self.fronts_only_btn)
        self.progress["value"] = 0
        self.status_var.set("Preparando…")
        self._reset_xml_download_progress()
        self.worker = threading.Thread(
            target=self._work, args=(plan_, reports, fronts_only), daemon=True,
        )
        self.worker.start()

    def _request_stop(self) -> None:
        if not self.running:
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "¿Seguro que quieres detener el proceso en curso?",
            icon=messagebox.WARNING,
        ):
            return
        self.cancel_event.set()
        self.stop_btn.state(["disabled"])
        self.status_var.set("Cancelando…")

    def _work(self, plan_, reports, fronts_only: bool = False) -> None:
        run_dir = None
        wd = None
        try:
            out = self._effective_output_dir()
            wd = work_dir()

            # Checkpoint: notify if cached crops exist from a previous failed run
            bled_dir = wd / "bled"
            if bled_dir.exists():
                cached = [f for f in bled_dir.iterdir() if f.is_file()]
                if cached:
                    self.events.put(("checkpoint_found", len(cached)))

            run_dir = out / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
            run_dir.mkdir(parents=True, exist_ok=True)
            generated: list[Path] = []
            extra_backs = self._resolve_extra_backs()
            crop_map = self._build_crop_map()

            # Phase timing tracking
            _run_start = time.time()
            _phase_first: dict[str, float] = {}
            _phase_done: dict[str, float] = {}

            def _track(stage: str, done: int, total: int) -> None:
                now = time.time()
                if stage not in _phase_first:
                    _phase_first[stage] = now
                if done == total and total > 0:
                    _phase_done[stage] = now

            if plan_ is not None:
                # --- Verify Drive access before downloading ---------------
                xml_paths_flat = [Path(p) for job in plan_.jobs for p in job.xml_paths]
                all_ids = collect_drive_ids(xml_paths_flat)
                raw_dir = wd / "raw"
                to_check = [
                    (did, name) for did, name in all_ids
                    if not list(raw_dir.glob(f"{did}.*"))
                ]
                if to_check:
                    self.events.put(("progress", "verify", 0, len(to_check), "XML seleccionados"))

                    def _verify_cb(done, total):
                        _track("verify", done, total)
                        self.events.put(("progress", "verify", done, total, "XML seleccionados"))

                    inaccessible = check_drive_access(to_check, _verify_cb)

                    if inaccessible and not self.cancel_event.is_set():
                        confirm_event = threading.Event()
                        self.events.put(("verify_warning", inaccessible, confirm_event))
                        while not confirm_event.wait(timeout=0.1):
                            if self.cancel_event.is_set():
                                break

                if self.cancel_event.is_set():
                    self.events.put(("cancelled", run_dir))
                    return

                # label shown during download/crop (global phases)
                _pdf_label = [""]

                def cb(stage, done, total):
                    _track(stage, done, total)
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

                def on_speed_update(speed_mbps: float, eta_sec: float) -> None:
                    self.events.put(("download_speed", speed_mbps, eta_sec))

                pdfs = run_plan(
                    plan_.jobs, run_dir, wd, cb,
                    cancel_event=self.cancel_event,
                    extra_fronts=list(self.local_fronts) or None,
                    extra_backs=list(extra_backs) or None,
                    local_crop_map=dict(crop_map) or None,
                    on_job_pdf_start=on_job_pdf_start,
                    on_xml_download_progress=on_xml_download_progress,
                    on_xml_crop_progress=on_xml_crop_progress,
                    fronts_only=fronts_only,
                    on_speed_update=on_speed_update,
                )
                generated.extend(pdfs)
                manifest = write_manifest(plan_, reports, run_dir)
            else:
                # Locals-only run. Back #1 acts as the default cardback.
                base = "locales"
                self.events.put(("file", 1, 1, f"{base} (solo imágenes locales)"))
                def cb(stage, done, total, _label=base):
                    _track(stage, done, total)
                    self.events.put(("progress", stage, done, total, _label))
                pdfs = run_locals_only(
                    list(self.local_fronts), self.local_backs[0],
                    run_dir, base, wd, cb,
                    cancel_event=self.cancel_event,
                    extra_backs=list(extra_backs),
                    local_crop_map=dict(crop_map),
                    fronts_only=fronts_only,
                )
                generated.extend(pdfs)
                manifest = None

            if not self.keep_cache.get():
                self._cleanup_workdir(wd)

            # Build timing summary
            def _fmt_dur(sec: float) -> str:
                return f"{int(sec) // 60}m {int(sec) % 60}s" if sec >= 60 else f"{sec:.0f}s"

            timing_parts = []
            for stage in ("verify", "download", "crop", "pdf"):
                if stage in _phase_first and stage in _phase_done:
                    dur = _phase_done[stage] - _phase_first[stage]
                    label = {"verify": "Verif.", "download": "Descarga",
                             "crop": "Recorte", "pdf": "PDF"}.get(stage, stage)
                    timing_parts.append(f"{label}: {_fmt_dur(dur)}")
            total_dur = time.time() - _run_start
            timing_str = "  ".join(timing_parts)
            if timing_str:
                timing_str += f"  Total: {_fmt_dur(total_dur)}"

            self.events.put(("done", generated, manifest, run_dir, timing_str))
        except DownloadPartialError as e:
            self.events.put(("partial_download_error", e.permission_errors,
                             e.timeout_errors, e.xml_context, run_dir))
        except DownloadRateLimitError:
            self.events.put(("rate_limit_error", run_dir))
        except DownloadPermissionError as e:
            self.events.put(("permission_error", e.card_name, e.xml_name, e.position, run_dir))
        except DownloadTimeoutError as e:
            self.events.put(("timeout_error", e.card_name, e.xml_name, e.position, run_dir))
        except Cancelled:
            self.events.put(("cancelled", run_dir))
        except Exception as e:
            self.events.put(("error", f"{e}\n\n{traceback.format_exc()}", run_dir))

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
            speed_info = (
                f" — {self._dl_speed_str}" if stage == "download" and self._dl_speed_str else ""
            )
            self.status_var.set(f"{name} — {label}: {done}/{total}{speed_info}")
        elif kind == "download_speed":
            _, speed_mbps, eta_sec = ev
            mins = int(eta_sec) // 60
            secs = int(eta_sec) % 60
            eta_str = f"{mins}:{secs:02d}" if mins > 0 else f"{secs}s"
            self._dl_speed_str = f"{speed_mbps:.1f} MB/s — ETA {eta_str}"
        elif kind == "checkpoint_found":
            _, count = ev
            self.status_var.set(
                f"Se encontraron {count} imagen(es) en caché de una ejecución anterior. "
                "Retomando desde el crop."
            )
        elif kind == "partial_download_error":
            _, perm_errors, timeout_errors, xml_context, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            parts = []
            if perm_errors:
                names = ", ".join(f"«{name}»" for _, name in perm_errors[:3])
                more = f" y {len(perm_errors) - 3} más" if len(perm_errors) > 3 else ""
                parts.append(
                    f"{len(perm_errors)} imagen(es) sin permiso de descarga: {names}{more}.\n"
                    "Pide al creador del proxy que restaure los permisos de Google Drive."
                )
            if timeout_errors:
                names = ", ".join(f"«{name}»" for _, name in timeout_errors[:3])
                more = f" y {len(timeout_errors) - 3} más" if len(timeout_errors) > 3 else ""
                parts.append(
                    f"{len(timeout_errors)} imagen(es) con tiempo de espera agotado: {names}{more}.\n"
                    "Las imágenes descargadas correctamente están en caché. "
                    "Vuelve a intentarlo en unos minutos."
                )
            total_failed = len(perm_errors) + len(timeout_errors)
            self.status_var.set(f"Error: {total_failed} imagen(es) no se pudieron descargar.")
            self._finish_running()
            messagebox.showerror(APP_TITLE, "\n\n".join(parts))
        elif kind == "done":
            _, pdfs, manifest, run_dir, timing_str = ev
            self.progress["value"] = 100
            extra = f" Resumen en {manifest.name}." if manifest else ""
            self.status_var.set(f"Listo. {len(pdfs)} PDF(s) generados en {run_dir.name}.{extra}")
            if timing_str:
                self.timing_var.set(f"Tiempos — {timing_str}")
                _log.info("Phase timings: %s", timing_str)
            self._finish_running()
            _notify(APP_TITLE, f"¡Listo! {len(pdfs)} PDF(s) generados correctamente.")
            self._open_output_folder(run_dir)
        elif kind == "xml_download_progress":
            _, xml_name, done, total = ev
            self._show_xml_download_progress(xml_name, done, total)
        elif kind == "xml_crop_progress":
            _, xml_name, done, total = ev
            self._show_xml_crop_progress(xml_name, done, total)
        elif kind == "verify_warning":
            _, cards, confirm_event = ev
            names = "\n".join(f"  • {name}" for _, name in cards[:8])
            more = f"\n  … y {len(cards) - 8} más" if len(cards) > 8 else ""
            msg = (
                f"{len(cards)} carta(s) sin acceso público en Google Drive:\n\n"
                f"{names}{more}\n\n"
                "El proceso fallará al intentar descargar estas cartas.\n"
                "¿Deseas continuar de todos modos?"
            )
            if not messagebox.askyesno(APP_TITLE, msg, icon=messagebox.WARNING):
                self.cancel_event.set()
            confirm_event.set()
        elif kind == "cancelled":
            _, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            self.progress["value"] = 0
            self.status_var.set("Proceso detenido. Las imágenes descargadas se conservan para retomar.")
            self._finish_running()
        elif kind == "rate_limit_error":
            _, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            self.status_var.set("Error: demasiadas descargas en poco tiempo.")
            self._finish_running()
            messagebox.showerror(
                APP_TITLE,
                "Se están intentando descargar demasiadas imágenes en poco tiempo, "
                "espera un rato y vuelve a intentar.\n\n"
                "Por favor selecciona «Guardar en el PC las imágenes entre ejecuciones» "
                "así evitamos volver a descargarlas cada vez.",
            )
        elif kind == "permission_error":
            _, card_name, xml_name, position, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
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
            _, card_name, xml_name, position, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
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
            _, msg, run_dir = ev
            if run_dir is not None:
                self._cleanup_run_dir(run_dir)
            self.status_var.set("Error durante la generación. Las imágenes en caché se conservan.")
            self._finish_running()
            messagebox.showerror(APP_TITLE, msg)

    def _finish_running(self) -> None:
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
    _wd = work_dir()
    _wd.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[logging.FileHandler(_wd / "gui.log", encoding="utf-8")],
    )
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
