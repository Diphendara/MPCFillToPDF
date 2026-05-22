"""MPCFillToPDF GUI — pick XML(s), run the pipeline, open the output folder."""
import os
import queue
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui.paths import app_base_dir, output_dir, work_dir
from src.pipeline import run

APP_TITLE = "MPCFillToPDF"
STAGE_LABELS = {
    "download": "Descargando",
    "crop":     "Recortando",
    "pdf":      "Generando PDF",
}


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.geometry("600x460")
        root.minsize(520, 420)

        self.xml_paths: list[Path] = []
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.keep_cache = tk.BooleanVar(value=True)

        self._build_ui()
        self.root.after(80, self._drain_events)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root)
        frm.pack(fill=tk.BOTH, expand=True, **pad)

        ttk.Label(frm, text="Archivos XML seleccionados:").pack(anchor=tk.W)

        list_frame = ttk.Frame(frm)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 6))
        self.listbox = tk.Listbox(list_frame, height=8, activestyle="none")
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Seleccionar XMLs…", command=self._pick_xmls).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Quitar selección", command=self._remove_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Vaciar", command=self._clear).pack(side=tk.LEFT)

        ttk.Checkbutton(
            frm, text="Conservar caché de imágenes entre ejecuciones",
            variable=self.keep_cache,
        ).pack(anchor=tk.W, pady=(10, 0))

        ttk.Separator(frm, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        self.generate_btn = ttk.Button(frm, text="Generar PDF(s)", command=self._start)
        self.generate_btn.pack(fill=tk.X)
        self.generate_btn.state(["disabled"])

        self.status_var = tk.StringVar(value="Listo. Selecciona uno o más XML.")
        ttk.Label(frm, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X, pady=(10, 2))

        self.progress = ttk.Progressbar(frm, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)

        out_text = f"Carpeta de salida: {output_dir()}"
        ttk.Label(frm, text=out_text, foreground="#666", anchor=tk.W).pack(fill=tk.X, pady=(10, 0))

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
                self.listbox.insert(tk.END, pp.name)
                added += 1
        if added:
            self.status_var.set(f"{len(self.xml_paths)} archivo(s) en cola.")
        self._refresh_generate_state()

    def _remove_selected(self) -> None:
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
            del self.xml_paths[idx]
        self._refresh_generate_state()

    def _clear(self) -> None:
        self.listbox.delete(0, tk.END)
        self.xml_paths.clear()
        self.status_var.set("Listo. Selecciona uno o más XML.")
        self._refresh_generate_state()

    def _refresh_generate_state(self) -> None:
        if self.xml_paths and (self.worker is None or not self.worker.is_alive()):
            self.generate_btn.state(["!disabled"])
        else:
            self.generate_btn.state(["disabled"])

    def _start(self) -> None:
        if not self.xml_paths or (self.worker and self.worker.is_alive()):
            return
        self.generate_btn.state(["disabled"])
        self.progress["value"] = 0
        self.status_var.set("Preparando…")
        files = list(self.xml_paths)
        self.worker = threading.Thread(target=self._work, args=(files,), daemon=True)
        self.worker.start()

    def _work(self, files: list[Path]) -> None:
        out = output_dir()
        wd = work_dir()
        generated: list[Path] = []
        try:
            for i, xml_path in enumerate(files, start=1):
                self.events.put(("file", i, len(files), xml_path.name))
                def cb(stage, done, total, _xml=xml_path.name):
                    self.events.put(("progress", stage, done, total, _xml))
                pdfs = run(xml_path, out, wd, cb)
                generated.extend(pdfs)
            if not self.keep_cache.get():
                self._cleanup_workdir(wd)
            self.events.put(("done", generated))
        except Exception as e:
            self.events.put(("error", f"{e}\n\n{traceback.format_exc()}"))

    @staticmethod
    def _cleanup_workdir(wd: Path) -> None:
        import shutil
        for sub in ("raw", "bled"):
            target = wd / sub
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

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
            _, pdfs = ev
            self.progress["value"] = 100
            self.status_var.set(f"Listo. {len(pdfs)} PDF(s) generados.")
            self._refresh_generate_state()
            self._open_output_folder()
        elif kind == "error":
            _, msg = ev
            self.status_var.set("Error durante la generación.")
            self._refresh_generate_state()
            messagebox.showerror(APP_TITLE, msg)

    def _open_output_folder(self) -> None:
        path = str(output_dir())
        try:
            os.startfile(path)  # Windows
        except AttributeError:
            import subprocess
            opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
            subprocess.Popen([opener, path])


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
