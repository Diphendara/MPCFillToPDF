## Context

The current image quality check uses Pillow's `ImageFilter.Kernel` to compute a 3x3 Laplacian, which operates on 8-bit unsigned integer data types. This clips negative values to 0, which reduces the mathematical variance of the filter output. The default threshold is set to 100. Introducing OpenCV and NumPy enables double-precision float-based Laplacian variance calculation without clipping, which is more standard and precise.

## Goals / Non-Goals

**Goals:**
- Add `opencv-python` and `numpy` as project dependencies.
- Create a new module `src/quality.py` containing both Pillow-based and OpenCV/NumPy-based quality algorithms to isolate mathematical operations.
- Update `gui/main.py` to add a checkbox for selecting OpenCV/NumPy quality calculations and update the default threshold dynamically (100 for Pillow, 300 for OpenCV/NumPy).
- Propagate the quality method parameter to all download, validation, fallback, and caching functions.
- Update tests to cover the new OpenCV algorithm and the quality method propagation.

**Non-Goals:**
- Completely deprecate Pillow quality calculations (Pillow remains available as an optional method).
- Rewrite other image handling in the project to use OpenCV.

## Decisions

### 1. Dedicated `src/quality.py` file
- **Rationale**: Isolates the numerical image processing logic from both the GUI code and the Scryfall API orchestrations.
- **Alternatives considered**: Keeping it in `src/downloader.py`. However, `downloader.py` focuses on downloads and multi-threading, so separating the quality math is cleaner.

### 2. Checkbox in Tkinter GUI and default value updates
- **Rationale**: Pillow and OpenCV Laplacian calculations produce values on different scales because Pillow clips negative intermediate values to 0. OpenCV keeps them as negative float64 values, resulting in variances roughly 3x larger. Updating default thresholds automatically (100 for Pillow, 300 for OpenCV) when toggled prevents user confusion.
- **Alternatives considered**: Keeping a single threshold. However, this would result in either Pillow failing all checks or OpenCV passing everything since they operate on different scales.

### 3. Dynamic import handling in `src/quality.py`
- **Rationale**: Ensures the code handles missing dependencies gracefully (logging a warning and falling back to Pillow or raising a descriptive exception) to aid debugging during setup.

## Risks / Trade-offs

- **[Risk]**: Increased dependency footprint with OpenCV and NumPy.
  - **Mitigation**: These libraries are widely used and supported across all platforms (Windows, macOS, Linux) and will be added via `uv` package management.
- **[Risk]**: Mismatch in threshold scales.
  - **Mitigation**: The GUI automatically updates the entry field default value when the method is toggled, and the input validation remains active.
