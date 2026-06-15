## Context

The application creates multiple cache folders under the `workdir` directory, including:
- `workdir/raw/` and `workdir/bled/` for MPCFill downloads and crops.
- `workdir/scryfall/` for individual Moxfield deck download folders.
- `workdir/scryfall_cache/` for global Scryfall image cache.

Currently, there is no interface control to manually purge these cache files from the application. The user has requested a clean button to delete these cache files from the Web Load (Moxfield) screen, allowing selective deletion of cache folders with a confirmation step.

## Goals / Non-Goals

**Goals:**
- Add a "Limpiar Caché" button in the bottom pane of the Web Load window (`WebLoadApp`).
- Open a custom Tkinter `Toplevel` dialog when the button is clicked, containing checkboxes to choose which folders to delete:
  - Moxfield/Scryfall deck downloads (`workdir/scryfall`) - default: Checked.
  - Global Scryfall image cache (`workdir/scryfall_cache`) - default: Checked.
  - MPCFill raw downloads and cropped images (`workdir/raw` and `workdir/bled`) - default: Unchecked.
- Require confirmation before deleting any files.
- Display a success message box once files have been deleted.
- Handle directory deletions safely, ensuring no crashes occur if files are locked.

**Non-Goals:**
- Deleting other files inside `workdir/` (like `gui.log`) which are actively written to and locked by the logging system.
- Adding a clean button to the main MPCFill screen or Launcher screen (based on explicit user feedback).

## Decisions

### 1. Placement of the Button
- **Decision:** Place the "Limpiar Caché" button in the bottom controls of the `WebLoadApp` layout, packed right below the "Descargar imágenes de Scryfall" button.
- **Rationale:** This groups it with the other action buttons in the bottom panel and makes it highly visible on the Web Load screen.

### 2. Selective Deletion Dialog
- **Decision:** Implement a custom modal dialog class `CleanCacheDialog` inheriting from `tk.Toplevel`.
- **Rationale:** This keeps the dialog code clean, self-contained, and allows centering it properly relative to the parent application window. Using checkboxes enables user choice as requested.

### 3. Deletion Implementation
- **Decision:** Use `shutil.rmtree` with `ignore_errors=True` to clear the selected directories.
- **Rationale:** This is already the standard way directories are deleted in this codebase (e.g. in `_cleanup_workdir`), avoiding runtime exceptions if individual files are locked or transient.

## Risks / Trade-offs

- **[Risk]** User deletes cache files while a download or compilation is currently in progress.
  - **Mitigation:** The clean button is disabled or runs checks to ensure no active worker thread is running, or we display a warning. (Actually, we can check if `self.running` is True, and if so, warn the user or block cache clearing).
- **[Risk]** Locking conflicts on Windows if files are open.
  - **Mitigation:** Using `ignore_errors=True` guarantees that the application will not crash.
