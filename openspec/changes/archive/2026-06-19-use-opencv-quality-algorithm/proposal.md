## Why

The current Pillow-based Laplacian variance image quality check runs entirely within Pillow's 8-bit unsigned integer limits, clipping intermediate results. Using OpenCV and NumPy allows for a more standard, unclipped double-precision Laplacian calculation, which is faster and yields higher-precision results. Additionally, providing the user with a choice of the quality evaluation method in the GUI allows them to opt for the higher-precision OpenCV/NumPy method or fallback to the Pillow-based method if they prefer, with default quality thresholds automatically adjusted to suit each method.

## What Changes

- Add `opencv-python` and `numpy` as project dependencies.
- Create a new module `src/quality.py` to house the image quality evaluation logic, supporting both Pillow-based and OpenCV/NumPy-based Laplacian variance calculations.
- Add a quality method toggle checkbox to the Moxfield downloader tab in the GUI (labeled "Usar OpenCV y Numpy" or similar).
- Automatically update the default quality threshold in the GUI depending on the selected method (e.g., 100 for Pillow, 300 for OpenCV).
- Propagate the selected quality method parameter from the GUI download triggers to the background downloader and card-processing functions.
- Update the caching, print fallbacks, and double-faced card quality check logic to use the selected quality method.
- Update the downloader test suite to cover the new OpenCV-based quality check, GUI method toggle behavior, and parameter propagation.

## Capabilities

### New Capabilities
<!-- None needed as this is a modification of an existing capability -->

### Modified Capabilities
- `scryfall-downloader`: Adds configuration checkbox for the quality method, dynamically updates default threshold values, and runs the selected evaluation algorithm during image download and cache verification.

## Impact

- **Dependencies**: Adds `opencv-python` and `numpy` to `requirements.txt` and `pyproject.toml`.
- **GUI**: Adds checkbutton for OpenCV quality algorithm and binds threshold value update.
- **Downloader Core**: Updates `download_deck_images`, `process_exact_edition`, `process_best_image`, `get_cached_card`, and `download_card_from_scryfall_object` in `src/scryfall.py` to accept and utilize the selected quality method.
- **API/Functions**: Moves quality calculation to `src/quality.py` and updates `src/downloader.py` and `tests/` accordingly.
