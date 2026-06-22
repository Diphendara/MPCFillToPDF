"""Standalone GUI helper widgets, constants, and utility functions."""

from __future__ import annotations

import io
import queue
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import ttk

try:
    import windnd as _windnd  # noqa: F401

    WINDND_AVAILABLE = True
except ImportError:
    WINDND_AVAILABLE = False

from PIL import Image, ImageTk

from src.constants import Stage
from src.parser import CardOrder

APP_TITLE = "MPCFillToPDF"
STAGE_LABELS = {
    Stage.VERIFY: "Verificando XML",
    Stage.DOWNLOAD: "Descargando",
    Stage.CROP: "Procesando imágenes",
    Stage.PDF: "Generando PDF, Páginas",
}
IMAGE_FILETYPES = [
    ("Imágenes", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
    ("Todos", "*.*"),
]
FRONT_NAME_WIDTH = 28

_PB_DOWNLOAD_COLOR = "#0078d4"
_PB_CROP_COLOR = "#2e7d32"


def ellipsize(name: str, width: int) -> str:
    if len(name) <= width:
        return name
    return name[: max(0, width - 1)] + "…"


def notify(title: str, message: str) -> None:
    """Show a system notification (best-effort; silently ignored if plyer/osascript is missing)."""
    if sys.platform == "darwin":
        try:
            import subprocess

            script = (
                "on run argv\n"
                "  display notification (item 2 of argv) with title (item 1 of argv)\n"
                "end run"
            )
            subprocess.run(
                ["osascript", "-e", script, title, message],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            from plyer import notification as _n

            _n.notify(title=title, message=message, app_name=APP_TITLE, timeout=8)
        except Exception:
            pass



def attach_context_menu(widget: tk.Widget) -> None:
    """Attach a right-click context menu (cut/copy/paste/select all) to an Entry or Text widget."""
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Cortar", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Copiar", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Pegar", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(
        label="Seleccionar todo", command=lambda: widget.event_generate("<<SelectAll>>")
    )
    widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))


def load_tab_icon(name: str, size: tuple[int, int] = (20, 20)) -> ImageTk.PhotoImage | None:
    if getattr(sys, "frozen", False):
        icons_dir = Path(getattr(sys, "_MEIPASS", "")) / "icons"
    else:
        icons_dir = Path(__file__).resolve().parent.parent / "icons"
    path = icons_dir / f"{name}.png"
    if not path.exists():
        return None
    try:
        img = Image.open(path).convert("RGBA")
        img = img.resize(size, Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


class XmlPb(tk.Canvas):
    """Canvas progress bar with centered text overlay — works on all themes."""

    _W = 130
    _H = 18
    _TROUGH = "#dde5f0"
    _BORDER = "#9aafc7"
    _TEXT = "#f0f0f0"

    def __init__(self, parent, **kw):
        super().__init__(
            parent,
            width=self._W,
            height=self._H,
            bg=self._TROUGH,
            highlightthickness=1,
            highlightbackground=self._BORDER,
            **kw,
        )
        self._bar = self.create_rectangle(0, 0, 0, self._H, fill=_PB_DOWNLOAD_COLOR, outline="")
        self._lbl = self.create_text(
            self._W // 2,
            self._H // 2,
            text="",
            fill=self._TEXT,
            font=("Segoe UI", 8),
        )

    def set_progress(self, pct: float, text: str = "", color: str | None = None) -> None:
        if color is not None:
            self.itemconfigure(self._bar, fill=color)
        filled = int(self._W * max(0.0, min(100.0, pct)) / 100)
        self.coords(self._bar, 0, 0, filled, self._H)
        self.itemconfigure(self._lbl, text=text)


class ImageTooltip:
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
                cell,
                text=self._SPINNER[0],
                font=("Segoe UI", 9),
                fg="#888",
            )
            loading_lbl.pack()
            loading_lbl.bind("<MouseWheel>", _scroll)
            self._loading_labels.append(loading_lbl)
            self._loading_set.add(idx)

            name = ellipsize(card.name, 12) if card.name else "(sin nombre)"
            name_lbl = tk.Label(cell, text=name, font=("Segoe UI", 7), wraplength=self._THUMB_W)
            name_lbl.pack()
            name_lbl.bind("<MouseWheel>", _scroll)
            count = len(card.slots)
            if count > 1:
                count_lbl = tk.Label(
                    cell, text=f"x{count}", font=("Segoe UI", 7, "bold"), fg="#555"
                )
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
