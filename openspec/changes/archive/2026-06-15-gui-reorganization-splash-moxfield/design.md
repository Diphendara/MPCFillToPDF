## Context

Currently, the application starts directly into the main MPCFill GUI window. The main window contains a "Carga desde web" button which opens a modal dialog to load Moxfield URLs, and displays the imported card contents in a pane at the bottom-left. To support expanding Moxfield integrations and cleaner organization, this change separates the launcher, the original MPCFill interface, and a new dedicated Moxfield "Web Load" workspace interface.

## Goals / Non-Goals

**Goals:**
- Create a splash screen launcher window upon application startup with a logo and two options: "MPCFill" and "Web Load".
- Remove Moxfield import and display capabilities from the main MPCFill window.
- Create a dedicated "Web Load" workspace window with a layout similar to MPCFill, but containing a URL input field, a "Cargar" button, and the scrollable imported cards text pane on the left, with local images on the right and placeholders for generation on the bottom.
- Ensure closing either the MPCFill or Web Load workspace window exits the application completely.

**Non-Goals:**
- Implementing the actual PDF generation from the Moxfield deck list in the Web Load window (that will be implemented in subsequent iterations; the generation buttons in the Web Load window will remain as placeholders).
- Modifying the underlying CLI or parser components.

## Decisions

### 1. Tkinter Window Lifecycle & Transition
- **Option A (Hidden root)**: Keep the splash screen window as the main `Tk()` root and hide/withdraw it when launching a workspace window, showing it again or destroying it on close.
- **Option B (Sequential main loops)**: The launcher runs as the first `Tk()` instance. When the user makes a choice, the launcher window is destroyed (`root.destroy()`), storing the choice. The launcher's event loop exits, and `main()` starts a brand new, clean `Tk()` instance for either `App` or `WebLoadApp`.
- **Decision**: **Option B** is chosen. It keeps the two application windows completely decoupled, avoids parent/child window hierarchy issues, and provides a clean exit path. Closing the chosen workspace window terminates its mainloop and cleanly exits the Python process.

### 2. File and Class Structure
- The launcher will be defined in a new class `Launcher` inside `gui/main.py`.
- The new Web Load workspace will be defined in a new class `WebLoadApp` inside `gui/main.py`.
- The existing `App` class in `gui/main.py` will be stripped of the "Carga desde web" button and Moxfield imported cards pane.
- Shared styles or initialization steps (like setting up the `vista` theme and work directories) will reside in the `main()` function in `gui/main.py`.

### 3. Logo Asset
- A new visual asset `launcher_logo.png` will be copied to `src/assets/launcher_logo.png`.
- This logo will be loaded using PIL/Tkinter in the splash screen `Launcher`.
- Since PyInstaller's `build_exe.py` already bundles the entire `src/assets` folder, this asset will automatically package without build script modifications.

## Risks / Trade-offs

- **[Risk] Multiple event loops in one process run** -> Closing a Tk root and starting another in the same process can sometimes cause minor issue with window focus on macOS.
  - *Mitigation*: We will use explicit focus calls (`root.focus_force()`) on the newly created main window.
