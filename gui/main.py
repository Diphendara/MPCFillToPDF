"""MPCFillToPDF GUI — pick XML(s), run the pipeline, open the output folder."""
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
from src.pipeline import run, run_merged
from src.precheck import analyze, plan, format_warning, format_merge_info, write_manifest

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
        self.cancel_event = threading.Event()
        self.running = False
        self.keep_cache = tk.BooleanVar(value=False)

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
        self.pick_btn = ttk.Button(btn_row, text="Seleccionar XMLs…", command=self._pick_xmls)
        self.pick_btn.pack(side=tk.LEFT)
        self.remove_btn = ttk.Button(btn_row, text="Quitar selección", command=self._remove_selected)
        self.remove_btn.pack(side=tk.LEFT, padx=6)
        self.clear_btn = ttk.Button(btn_row, text="Vaciar", command=self._clear)
        self.clear_btn.pack(side=tk.LEFT)

        self.keep_cache_cb = ttk.Checkbutton(
            frm, text="Conservar caché de imágenes entre ejecuciones",
            variable=self.keep_cache,
        )
        self.keep_cache_cb.pack(anchor=tk.W, pady=(10, 0))

        ttk.Separator(frm, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        self.generate_btn = ttk.Button(frm, text="Generar PDF(s)", command=self._start)
        self.generate_btn.pack(fill=tk.X)
        self.generate_btn.state(["disabled"])

        # Stop button: only packed while a run is in progress.
        self.stop_btn = ttk.Button(frm, text="Detener", command=self._request_stop)

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
        if self.xml_paths and not self.running:
            self.generate_btn.state(["!disabled"])
        else:
            self.generate_btn.state(["disabled"])

    def _start(self) -> None:
        if not self.xml_paths or self.running:
            return

        try:
            reports = analyze(self.xml_paths)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"No se pudo analizar el XML:\n{e}")
            return

        plan_ = plan(reports)

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
        out = output_dir()
        wd = work_dir()
        run_dir = out / datetime.now().strftime("%d_%m_%Y_%H-%M-%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        generated: list[Path] = []
        try:
            jobs = plan_.jobs
            for i, job in enumerate(jobs, start=1):
                if self.cancel_event.is_set():
                    raise Cancelled()
                label = job.base_name + (" (fusión)" if job.is_merged else "")
                self.events.put(("file", i, len(jobs), label))
                def cb(stage, done, total, _label=label):
                    self.events.put(("progress", stage, done, total, _label))
                if job.is_merged:
                    pdfs = run_merged(
                        job.xml_paths, run_dir, job.base_name, wd, cb,
                        cancel_event=self.cancel_event,
                    )
                else:
                    pdfs = run(
                        job.xml_paths[0], run_dir, wd, cb,
                        cancel_event=self.cancel_event,
                    )
                generated.extend(pdfs)
            manifest = write_manifest(plan_, reports, run_dir)
            if not self.keep_cache.get():
                self._cleanup_workdir(wd)
            self.events.put(("done", generated, manifest, run_dir))
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
        elif kind == "cancelled":
            _, run_dir, wd = ev
            # Always drop the run_dir so partial PDFs don't confuse the user.
            self._cleanup_run_dir(run_dir)
            # Drop cached raw/bled images only if the user didn't ask to keep them.
            if not self.keep_cache.get():
                self._cleanup_workdir(wd)
            self.progress["value"] = 0
            self.status_var.set("Proceso detenido.")
            self._finish_running()
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
