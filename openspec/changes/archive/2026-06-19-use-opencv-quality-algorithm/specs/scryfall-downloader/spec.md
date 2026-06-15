## MODIFIED Requirements

### Requirement: Scryfall downloader GUI settings
The GUI SHALL display checkboxes to configure the download behavior under the URL input:
- "Usar edición exacta del mazo"
- "Preferir versión en Español"
- "Mejor imagen disponible"
The "Usar edición exacta del mazo" and "Mejor imagen disponible" checkboxes SHALL be mutually exclusive. If one is checked, the other SHALL automatically be unchecked.
The GUI SHALL also display checkboxes for card zones with "Comandantes" and "Mazo Principal" checked by default, and "Banquillo (Sideboard)" and "Tokens / Fichas" unchecked by default.
The GUI SHALL display a checkbox (labeled "Usar algoritmo OpenCV") allowing the user to select either the OpenCV/NumPy-based quality calculation method (when checked) or the Pillow-based method (when unchecked).
The GUI SHALL display a text entry to configure the quality threshold. When the quality method checkbox state changes, the quality threshold entry SHALL automatically be updated with the method's default value:
- 100 if the Pillow method is selected (checkbox unchecked).
- 300 if the OpenCV/NumPy method is selected (checkbox checked).
The entry field SHALL validate that the input is a positive integer.

#### Scenario: Mutually exclusive checkboxes
- **WHEN** the user checks "Mejor imagen disponible"
- **THEN** the "Usar edición exacta del mazo" checkbox is unchecked.

#### Scenario: Default zone selection
- **WHEN** the Moxfield deck loading tab is displayed
- **THEN** "Comandantes" and "Mazo Principal" are checked, and "Banquillo" and "Tokens / Fichas" are unchecked.

#### Scenario: Quality method toggling updates default threshold
- **WHEN** the user checks the "Usar algoritmo OpenCV" checkbox
- **THEN** the quality threshold text entry is automatically set to "300".
- **WHEN** the user unchecks the "Usar algoritmo OpenCV" checkbox
- **THEN** the quality threshold text entry is automatically set to "100".

### Requirement: Pillow-based image quality evaluation
The downloader SHALL compute a quality score for each downloaded card image using either a Pillow-based Laplacian variance check or an OpenCV/NumPy-based Laplacian variance check, depending on the method configured in the GUI.
- **Pillow method**: The image is converted to grayscale, a 3x3 Laplacian filter kernel `[0, 1, 0, 1, -4, 1, 0, 1, 0]` is applied, and the variance of pixel intensities is calculated. Due to 8-bit unsigned integer clipping in Pillow's intermediate representation, negative values are clipped to 0.
- **OpenCV/NumPy method**: The image is loaded in grayscale, the Laplacian is computed using double-precision (`cv2.CV_64F`) without clipping, and the variance of these unclipped values is calculated.
If the computed quality score is lower than the configured user threshold, the image SHALL be considered of inadequate quality.

#### Scenario: Image quality check passes
- **WHEN** the Pillow method is configured, and the image's computed Laplacian variance is 150 (greater than the threshold of 100)
- **THEN** the quality check passes and the image is accepted.
- **WHEN** the OpenCV method is configured, and the image's computed Laplacian variance is 450 (greater than the threshold of 300)
- **THEN** the quality check passes and the image is accepted.
