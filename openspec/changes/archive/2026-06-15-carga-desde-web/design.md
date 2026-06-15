## Context

The application has a user interface created using `tkinter` and `ttk`. It currently allows selecting XML files from disk using the `Seleccionar XMLs…` button in `gui/main.py`. This change introduces a new button next to it that opens a modal window containing a URL input field, compatibility label, and action buttons.

## Goals / Non-Goals

**Goals:**
- Add a new "Carga desde web" button to the XML file panel layout in `gui/main.py`.
- Implement a modal dialog (`tk.Toplevel`) that prompts the user for a URL.
- Show a compatibility label stating "moxfield" inside the dialog.
- Implement Cancel and Accept logic (Accept simply closes the dialog for now).

**Non-Goals:**
- Implementing the actual web request fetching or URL validation.
- Implementing the Moxfield to XML parser.
- Adding downloaded files to the XML file list (this will be added later).

## Decisions

### Decision: Layout and Dialog Implementation in Tkinter
- **Choice**: Implement the modal dialog as a custom helper function or inline method in `gui/main.py` using `tk.Toplevel`.
- **Alternatives considered**:
  - *Standard `tkinter.simpledialog.askstring`*: Rejected because it doesn't allow custom compatibility labels or custom layouts easily without sub-classing anyway, and we want high control over spacing and layout.
- **Rationale**: Creating a simple `tk.Toplevel` with `transient` and `grab_set` properties ensures it behaves as a proper modal on both Windows/macOS/Linux.

## Risks / Trade-offs

- **Risk**: Modality blocking user interaction.
  - **Mitigation**: Ensure `grab_set()` and dialog lifecycle is correctly managed so the application doesn't freeze or lock up permanently.
