## Why

Reorganizing the application's entry points and separating the local XML/image generation from the Moxfield web deck loading will improve usability. As we add more complex features, a clean splash screen launcher and dedicated interfaces will prevent UI clutter and set the stage for step-by-step feature growth.

## What Changes

- Introduce a new splash screen window upon launching, displaying a logo and two options: "MPCFill" and "Web Load".
- **BREAKING**: Reorganize the original MPCFill window to remove the "Carga desde web" button and "Cartas Importadas" pane.
- Create a new, dedicated "Web Load" workspace window mimicking the MPCFill layout (left side: Moxfield URL input/loader and scrollable imported cards text pane; right side: optional local images; bottom side: generation buttons, progress, and status bar).
- Modify the exit logic so that closing either MPCFill or Web Load closes the entire application.

## Capabilities

### New Capabilities
- `splash-screen-launcher`: Launch the application into a splash screen displaying a logo and buttons to choose between MPCFill and Web Load.
- `web-load-window`: Provide a dedicated Web Load workspace window to paste Moxfield URLs, load deck contents, display imported cards, configure local images, and track status.

### Modified Capabilities
- `carga-desde-web`: Remove web load functionality from the main MPCFill window.
- `main-window-card-display`: Remove the imported card display pane from the main MPCFill window.

## Impact

- `gui/main.py`: Significant refactoring to extract window layout building blocks, handle multi-window management and lifecycle, and implement the splash screen and Web Load layouts.
- `src/assets/`: Add a logo image for the splash screen launcher.
