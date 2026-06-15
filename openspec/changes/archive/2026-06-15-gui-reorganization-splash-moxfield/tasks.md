## 1. Asset Setup

- [x] 1.1 Copy launcher logo image from artifacts directory to `src/assets/launcher_logo.png`

## 2. Reorganize Original App in gui/main.py

- [x] 2.1 Remove "Carga desde web" button from the XML controls in `App`
- [x] 2.2 Remove "Cartas Importadas (Moxfield)" text pane from `App`
- [x] 2.3 Strip unused Moxfield background downloader methods from `App`

## 3. Implement Launcher and WebLoadApp

- [x] 3.1 Implement the `Launcher` splash screen class in `gui/main.py` displaying the logo and two choice buttons
- [x] 3.2 Implement the `WebLoadApp` class in `gui/main.py` with URL input/loader, imported cards pane, local images frame, and bottom bar controls
- [x] 3.3 Update the `main()` function in `gui/main.py` to launch `Launcher` first, store the selection, and run the chosen application (MPCFill or Web Load) in the main loop

## 4. Testing & Verification

- [x] 4.1 Write unit tests for the `Launcher` class in `tests/test_gui.py`
- [x] 4.2 Write unit tests for the `WebLoadApp` class in `tests/test_gui.py`
- [x] 4.3 Run the full test suite using `pytest` to verify all tests pass

## 5. Documentation & Commit

- [x] 5.1 Update `README.md` with descriptions of the new splash launcher and Web Load features
- [x] 5.2 Update `CLAUDE.md` to explain the new file structures, Launcher/WebLoadApp classes, and run commands
- [x] 5.3 Commit all change files to the local Git repository
