## 1. UI Implementation

- [x] 1.1 Create the `CleanCacheDialog` popup window class in `gui/main.py` containing three checkboxes for Moxfield/Scryfall, Global Scryfall, and MPCFill cache with proper default states and spacing.
- [x] 1.2 Implement the `_on_clean_cache` method in `WebLoadApp` in `gui/main.py` which instantiates the dialog, waits for acceptance, checks that at least one checkbox is checked, prompts for confirmation, deletes directories, and shows the completion box.
- [x] 1.3 Add and pack the "Limpiar Caché" button in `WebLoadApp._build_ui` in `gui/main.py`.

## 2. Test Implementation

- [x] 2.1 Add unit tests in `tests/test_gui.py` to mock `shutil.rmtree` and verify the deletion logic of `_on_clean_cache` with different selections.

## 3. Documentation

- [x] 3.1 Update `README.md` to describe the new cache clearing functionality and the options dialog.
- [x] 3.2 Update `CLAUDE.md` to document the new `CleanCacheDialog` implementation, its UI layout, and how cache clearing works.

## 4. Git Commit

- [x] 4.1 Commit the completed changes to the local Git repository.
