"""Base classes for TCG row rendering to eliminate code duplication."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gui.decks_tab import DecksTabMixin


class TCGRowRenderer:
    """Base class for TCG row renderers with shared logic."""

    def __init__(self, parent: DecksTabMixin) -> None:
        """Initialize with reference to parent mixin."""
        self.parent = parent

    def _make_qty_updater(
        self,
        card: Any,
        qty_var: tk.IntVar,
        checkvar: tk.BooleanVar,
        sync_callback: Callable[[], None],
    ) -> Callable[[], None]:
        """Create a quantity updater function for a card.

        Args:
            card: The card object to update
            qty_var: The IntVar holding the quantity
            checkvar: The BooleanVar for the checkbox
            sync_callback: Function to call after updating

        Returns:
            A function that updates the card quantity when called
        """

        def _update(*_args: Any) -> None:
            try:
                new_qty = qty_var.get()
                if new_qty == 0:
                    checkvar.set(False)
                    sync_callback()
                elif new_qty >= 1:
                    card.quantity = new_qty
                    checkvar.set(True)
                    sync_callback()
            except tk.TclError:
                pass  # Invalid input, ignore

        return _update

    def _create_qty_spinbox(
        self,
        parent_frame: ttk.Frame,
        card: Any,
        qty_var: tk.IntVar,
        checkvar: tk.BooleanVar,
        sync_callback: Callable[[], None],
        width: int = 4,
    ) -> ttk.Spinbox:
        """Create a quantity spinbox with updater.

        Args:
            parent_frame: The parent frame
            card: The card object
            qty_var: The IntVar holding the quantity
            checkvar: The BooleanVar for the checkbox
            sync_callback: Function to call after updating
            width: Width of the spinbox

        Returns:
            The created Spinbox widget
        """
        updater = self._make_qty_updater(card, qty_var, checkvar, sync_callback)
        spinbox = ttk.Spinbox(
            parent_frame,
            from_=0,
            to=99,
            width=width,
            textvariable=qty_var,
            command=updater,
        )
        spinbox.pack(side=tk.LEFT, padx=(0, 4))
        qty_var.trace_add("write", updater)
        return spinbox

    def _create_card_checkbox(
        self,
        parent_frame: ttk.Frame,
        checkvar: tk.BooleanVar,
        sync_callback: Callable[[], None],
    ) -> ttk.Checkbutton:
        """Create a card selection checkbox.

        Args:
            parent_frame: The parent frame
            checkvar: The BooleanVar for the checkbox
            sync_callback: Function to call after toggling

        Returns:
            The created Checkbutton widget
        """
        checkbox = ttk.Checkbutton(parent_frame, variable=checkvar, command=sync_callback)
        checkbox.pack(side=tk.LEFT)
        return checkbox
