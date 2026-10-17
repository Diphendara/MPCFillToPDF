"""Universal text import dialog with TCG selection."""

import threading
import tkinter as tk
from tkinter import ttk

from gui.widgets import load_tab_icon
from src.text_importer import (
    TextImportError,
    build_riftbound_deck_from_text,
    parse_lorcana_text,
    parse_mtg_text,
    parse_op_text,
    parse_ygo_text,
)

# TCG definitions: key, display name, icon name, example format
TCGS = [
    ("Riftbound", "Riftbound", "riftbound_icon", "3 Sabotage (OGN-156)"),
    ("MTG", "Magic: The Gathering", "mtg_icon", "1 Lightning Bolt (LEA)"),
    ("Lorcana", "Lorcana", "lorcana_icon", "4 Elsa - Snow Queen"),
    ("One Piece", "One Piece", "op_icon", "2xOP04-016_r1"),
    ("Yu-Gi-Oh", "Yu-Gi-Oh", "yugioh_icon", "3 Blue-Eyes White Dragon"),
]

FORMAT_HINTS = {
    "Riftbound": "Formato: Cantidad Nombre (SET-NUMERO)\nEjemplo: 3 Sabotage (OGN-156)",
    "MTG": "Formato: Cantidad Nombre [(SET) [NUMERO]] [*F*]\nEjemplo: 1 Lightning Bolt (LEA)",
    "Lorcana": "Formato: Cantidad Nombre [(Numero)]\nEjemplo: 4 Elsa - Snow Queen",
    "One Piece": "Formato: CantidadxCODIGO o Cantidad Nombre (CODIGO|Leader)\nEjemplo: 2xOP04-016_r1",
    "Yu-Gi-Oh": "Formato: Cantidad Nombre [(SET)]\nEjemplo: 3 Blue-Eyes White Dragon",
}


class UniversalImportDialog:
    """Dialog for importing deck lists: paste text, pick TCG, import."""

    def __init__(self, parent, events_queue):
        self.parent = parent
        self.events = events_queue
        self.dialog = None
        self.text_widget = None
        self.status_var = None
        self.hint_var = None
        self.selected_tcg = None
        self._icon_refs = []  # Keep references to avoid garbage collection

    def show(self):
        """Show the import dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Importar lista desde texto")
        self.dialog.geometry("700x620")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        main_frame = ttk.Frame(self.dialog, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        ttk.Label(
            main_frame,
            text="📋 Importar lista de cartas",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        ttk.Label(
            main_frame,
            text="Pega tu lista de cartas y pulsa Importar.",
            foreground="#666",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 8))

        # Text area
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.text_widget = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            height=14,
        )
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame, command=self.text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_widget.config(yscrollcommand=scrollbar.set)

        # TCG selection frame
        select_frame = ttk.LabelFrame(
            main_frame,
            text="Selecciona el TCG de la lista que has pegado",
            padding=8,
        )
        select_frame.pack(fill=tk.X, pady=(0, 8))

        buttons_frame = ttk.Frame(select_frame)
        buttons_frame.pack(fill=tk.X)

        for key, display_name, icon_name, _example in TCGS:
            icon = load_tab_icon(icon_name, size=(24, 24))
            self._icon_refs.append(icon)

            btn = ttk.Button(
                buttons_frame,
                text=display_name,
                image=icon,
                compound=tk.LEFT,
                command=lambda k=key: self._select_tcg(k),
            )
            btn.pack(side=tk.LEFT, padx=4, pady=2)

        # Format hint label
        self.hint_var = tk.StringVar(value="")
        ttk.Label(
            select_frame,
            textvariable=self.hint_var,
            foreground="#555",
            font=("Consolas", 8),
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(6, 0))

        # Status label
        self.status_var = tk.StringVar(value="")
        ttk.Label(
            main_frame,
            textvariable=self.status_var,
            foreground="#d32f2f",
        ).pack(anchor="w", pady=(0, 8))

        # Bottom buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame,
            text="📥 Importar",
            command=self._do_import,
        ).pack(side=tk.RIGHT, padx=(4, 0))

        ttk.Button(
            btn_frame,
            text="Cancelar",
            command=self.dialog.destroy,
        ).pack(side=tk.RIGHT)

        self.text_widget.bind("<Control-Return>", lambda _e: self._do_import())
        self.text_widget.focus_set()

    def _select_tcg(self, tcg_key: str):
        """Handle TCG selection."""
        self.selected_tcg = tcg_key
        self.hint_var.set(FORMAT_HINTS.get(tcg_key, ""))
        self.status_var.set(f"✅ TCG seleccionado: {tcg_key}")

    def _do_import(self):
        """Import the deck list."""
        text = self.text_widget.get("1.0", tk.END).strip()

        if not text:
            self.status_var.set("⚠️ Pega una lista de cartas primero")
            return

        if not self.selected_tcg:
            self.status_var.set("⚠️ Selecciona el TCG de tu lista")
            return

        tcg = self.selected_tcg
        self.status_var.set("Importando...")
        self.dialog.update()

        def _import():
            try:
                if tcg == "Riftbound":
                    deck = build_riftbound_deck_from_text(text, deck_name="Imported from text")
                    self.events.put(("rb_deck_loaded", deck))
                elif tcg == "MTG":
                    result = parse_mtg_text(text)
                    self.events.put(("mtg_url_loaded", "", result.cards, False, result.name))
                elif tcg == "Lorcana":
                    deck = parse_lorcana_text(text)
                    self.events.put(("lorcana_deck_loaded", deck))
                elif tcg == "One Piece":
                    deck = parse_op_text(text)
                    self.events.put(("op_deck_loaded", deck))
                elif tcg == "Yu-Gi-Oh":
                    deck = parse_ygo_text(text)
                    self.events.put(("ygo_deck_loaded", deck))

                self.dialog.after(0, self.dialog.destroy)
            except TextImportError as exc:
                error_msg = str(exc)
                self.dialog.after(0, lambda msg=error_msg: self.status_var.set(f"❌ {msg}"))
            except Exception as exc:
                error_msg = str(exc)
                self.dialog.after(0, lambda msg=error_msg: self.status_var.set(f"❌ Error: {msg}"))

        threading.Thread(target=_import, daemon=True).start()
