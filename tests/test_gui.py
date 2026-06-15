"""Tests for gui/main.py — state management and logic without rendering.

Tkinter is instantiated headlessly (window withdrawn).  Tests are skipped
automatically when no display is available (e.g. headless CI).
"""
import tkinter as tk
import pytest
from pathlib import Path

from tests.conftest import make_rgb_image, make_xml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tk_root():
    """One Tk root per test module — creating/destroying it per-test is slow."""
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        root.destroy()
    except tk.TclError:
        pytest.skip("No display available — Tkinter tests skipped")


@pytest.fixture
def app(tk_root):
    """Fresh App instance; GUI state is reset by the fixture."""
    from gui.main import App
    a = App(tk_root)
    yield a
    # Clean up widgets added during the test
    for w in tk_root.winfo_children():
        try:
            w.destroy()
        except Exception:
            pass


@pytest.fixture
def web_load_app(tk_root):
    """Fresh WebLoadApp instance; GUI state is reset by the fixture."""
    from gui.main import WebLoadApp
    a = WebLoadApp(tk_root)
    yield a
    # Clean up widgets added during the test
    for w in tk_root.winfo_children():
        try:
            w.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# _build_crop_map
# ---------------------------------------------------------------------------

class TestBuildCropMap:
    def test_empty_returns_empty(self, app):
        assert app._build_crop_map() == {}

    def test_back_crop_true(self, app, tmp_path):
        p = make_rgb_image(tmp_path / "back.jpg")
        app.local_backs.append(p)
        app.local_back_crop.append(True)
        m = app._build_crop_map()
        assert m.get(p) is True

    def test_back_crop_false(self, app, tmp_path):
        p = make_rgb_image(tmp_path / "back.jpg")
        app.local_backs.append(p)
        app.local_back_crop.append(False)
        m = app._build_crop_map()
        assert m.get(p) is False

    def test_front_overrides_back_for_same_path(self, app, tmp_path):
        """When a path appears as both back and front, front's setting wins."""
        p = make_rgb_image(tmp_path / "shared.jpg")
        app.local_backs.append(p)
        app.local_back_crop.append(True)
        app.local_fronts.append(p)
        app.front_back_paths.append(p)
        app.local_front_crop.append(False)
        assert app._build_crop_map()[p] is False

    def test_multiple_items(self, app, tmp_path):
        for i in range(3):
            p = make_rgb_image(tmp_path / f"img{i}.jpg")
            app.local_fronts.append(p)
            app.front_back_paths.append(None)
            app.local_front_crop.append(bool(i % 2))
        m = app._build_crop_map()
        fronts = app.local_fronts
        assert m[fronts[0]] is False
        assert m[fronts[1]] is True
        assert m[fronts[2]] is False


# ---------------------------------------------------------------------------
# _resolve_extra_backs
# ---------------------------------------------------------------------------

class TestResolveExtraBacks:
    def test_no_fronts_returns_empty(self, app):
        assert app._resolve_extra_backs() == []

    def test_explicit_back(self, app, tmp_path):
        back = make_rgb_image(tmp_path / "back.jpg")
        app.local_fronts.append(make_rgb_image(tmp_path / "front.jpg"))
        app.front_back_paths.append(back)
        assert app._resolve_extra_backs() == [back]

    def test_none_assignment_passes_through(self, app, tmp_path):
        app.local_fronts.append(make_rgb_image(tmp_path / "front.jpg"))
        app.front_back_paths.append(None)
        assert app._resolve_extra_backs() == [None]

    def test_mixed_assignments(self, app, tmp_path):
        back = make_rgb_image(tmp_path / "back.jpg")
        for i in range(3):
            app.local_fronts.append(make_rgb_image(tmp_path / f"f{i}.jpg"))
            app.front_back_paths.append(back if i == 1 else None)
        result = app._resolve_extra_backs()
        assert result == [None, back, None]


# ---------------------------------------------------------------------------
# _refresh_generate_state
# ---------------------------------------------------------------------------

class TestGenerateState:
    def test_disabled_when_nothing_loaded(self, app):
        app._refresh_generate_state()
        assert "disabled" in str(app.soriano_btn.state())
        assert "disabled" in str(app.fronts_only_btn.state())

    def test_enabled_with_xml(self, app, tmp_path):
        xml = make_xml(
            tmp_path / "t.xml",
            fronts=[{"id": "F1", "name": "C1", "slots": "0"}],
        )
        app.xml_paths.append(xml)
        app.running = False
        app._refresh_generate_state()
        assert "disabled" not in str(app.soriano_btn.state())

    def test_disabled_fronts_alone_no_backs(self, app, tmp_path):
        app.local_fronts.append(make_rgb_image(tmp_path / "f.jpg"))
        app.front_back_paths.append(None)
        app.local_front_crop.append(False)
        app.running = False
        app._refresh_generate_state()
        assert "disabled" in str(app.soriano_btn.state())

    def test_enabled_fronts_with_backs(self, app, tmp_path):
        front = make_rgb_image(tmp_path / "f.jpg")
        back = make_rgb_image(tmp_path / "b.jpg")
        app.local_fronts.append(front)
        app.front_back_paths.append(back)
        app.local_front_crop.append(False)
        app.local_backs.append(back)
        app.local_back_crop.append(False)
        app.running = False
        app._refresh_generate_state()
        assert "disabled" not in str(app.soriano_btn.state())

    def test_disabled_while_running(self, app, tmp_path):
        xml = make_xml(
            tmp_path / "t.xml",
            fronts=[{"id": "F1", "name": "C1", "slots": "0"}],
        )
        app.xml_paths.append(xml)
        app.running = True
        app._refresh_generate_state()
        assert "disabled" in str(app.soriano_btn.state())


# ---------------------------------------------------------------------------
# Batch crop toggle (_on_front_crop_all / _on_back_crop_all)
# ---------------------------------------------------------------------------

class TestCropAllToggle:
    def test_set_all_fronts_true(self, app, tmp_path):
        for i in range(4):
            app.local_fronts.append(make_rgb_image(tmp_path / f"f{i}.jpg"))
            app.front_back_paths.append(None)
            app.local_front_crop.append(False)
        app._front_crop_all.set(True)
        app._on_front_crop_all()
        assert all(app.local_front_crop)

    def test_clear_all_fronts(self, app, tmp_path):
        for i in range(3):
            app.local_fronts.append(make_rgb_image(tmp_path / f"f{i}.jpg"))
            app.front_back_paths.append(None)
            app.local_front_crop.append(True)
        app._front_crop_all.set(False)
        app._on_front_crop_all()
        assert not any(app.local_front_crop)

    def test_set_all_backs_true(self, app, tmp_path):
        for i in range(3):
            p = make_rgb_image(tmp_path / f"b{i}.jpg")
            app.local_backs.append(p)
            app.local_back_crop.append(False)
        app._back_crop_all.set(True)
        app._on_back_crop_all()
        assert all(app.local_back_crop)

    def test_clear_all_backs(self, app, tmp_path):
        for i in range(3):
            p = make_rgb_image(tmp_path / f"b{i}.jpg")
            app.local_backs.append(p)
            app.local_back_crop.append(True)
        app._back_crop_all.set(False)
        app._on_back_crop_all()
        assert not any(app.local_back_crop)

    def test_toggle_empty_list_is_noop(self, app):
        app._front_crop_all.set(True)
        app._on_front_crop_all()  # should not raise
        assert app.local_front_crop == []


# ---------------------------------------------------------------------------
# Individual crop-change callbacks
# ---------------------------------------------------------------------------

class TestCropChange:
    def test_front_crop_change(self, app, tmp_path):
        app.local_fronts.append(make_rgb_image(tmp_path / "f.jpg"))
        app.front_back_paths.append(None)
        app.local_front_crop.append(False)
        var = tk.BooleanVar(value=True)
        app._on_front_crop_change(0, var)
        assert app.local_front_crop[0] is True

    def test_back_crop_change(self, app, tmp_path):
        app.local_backs.append(make_rgb_image(tmp_path / "b.jpg"))
        app.local_back_crop.append(False)
        var = tk.BooleanVar(value=True)
        app._on_back_crop_change(0, var)
        assert app.local_back_crop[0] is True

    def test_crop_change_out_of_range_is_noop(self, app):
        var = tk.BooleanVar(value=True)
        app._on_front_crop_change(99, var)  # no IndexError


# ---------------------------------------------------------------------------
# Moxfield GUI importing
# ---------------------------------------------------------------------------

class TestMoxfieldGUI:
    def test_display_imported_cards(self, web_load_app):
        content = "1 Plains\n4 Black Lotus"
        web_load_app._display_imported_cards(content)
        text_val = web_load_app.imported_text.get("1.0", "end-1c")
        assert text_val == content
        assert web_load_app.imported_text.cget("state") == "disabled"

    def test_handle_moxfield_success(self, web_load_app):
        web_load_app.events.put(("moxfield_success", "My Moxfield Deck", "1 Black Lotus\n1 Mox Ruby"))
        web_load_app._drain_events()
        assert "My Moxfield Deck" in web_load_app.status_var.get()
        assert web_load_app.imported_text.get("1.0", "end-1c") == "1 Black Lotus\n1 Mox Ruby"
        assert web_load_app.progress["value"] == 100

    def test_handle_moxfield_error(self, web_load_app):
        import tkinter.messagebox as messagebox
        original_showerror = messagebox.showerror
        called_error = []
        messagebox.showerror = lambda title, message: called_error.append((title, message))
        
        try:
            web_load_app.events.put(("moxfield_error", "Connection timed out"))
            web_load_app._drain_events()
            assert "Connection timed out" in web_load_app.status_var.get()
            assert web_load_app.progress["value"] == 0
            assert len(called_error) == 1
            assert "Connection timed out" in called_error[0][1]
        finally:
            messagebox.showerror = original_showerror


# ---------------------------------------------------------------------------
# Scryfall Downloader GUI
# ---------------------------------------------------------------------------

class TestScryfallGUI:
    def test_initial_state(self, web_load_app):
        # The button should be disabled initially
        state = web_load_app.scryfall_download_btn.state()
        assert "disabled" in state

    def test_moxfield_success_enables_button(self, web_load_app):
        mock_deck = {"name": "Test Deck", "mainboard": []}
        web_load_app.events.put(("moxfield_success", "Test Deck", "1 Plains", mock_deck))
        web_load_app._drain_events()
        
        assert web_load_app.deck_data == mock_deck
        state = web_load_app.scryfall_download_btn.state()
        assert "disabled" not in state

    def test_clear_moxfield_disables_button(self, web_load_app):
        web_load_app.deck_data = {"name": "Test Deck"}
        web_load_app.scryfall_download_btn.state(["!disabled"])
        
        web_load_app._clear_moxfield()
        assert web_load_app.deck_data is None
        state = web_load_app.scryfall_download_btn.state()
        assert "disabled" in state

    def test_download_progress_events(self, web_load_app):
        # Start download
        web_load_app.events.put(("scryfall_download_start", 10))
        web_load_app._drain_events()
        assert web_load_app.running is True
        assert "disabled" in web_load_app.scryfall_download_btn.state()
        assert "disabled" in web_load_app.load_btn.state()
        assert web_load_app.progress["value"] == 0

        # Progress update
        web_load_app.events.put(("scryfall_download_progress", 5, 10, 50, "Plains"))
        web_load_app._drain_events()
        assert web_load_app.progress["value"] == 50
        assert "Plains" in web_load_app.status_var.get()

        # Success event
        import tkinter.messagebox as messagebox
        original_showinfo = messagebox.showinfo
        called_info = []
        messagebox.showinfo = lambda title, message: called_info.append((title, message))
        try:
            web_load_app.events.put(("scryfall_download_success", 10))
            web_load_app._drain_events()
            assert web_load_app.running is False
            assert "disabled" not in web_load_app.load_btn.state()
            assert web_load_app.progress["value"] == 100
            assert len(called_info) == 1
        finally:
            messagebox.showinfo = original_showinfo


# ---------------------------------------------------------------------------
# Launcher GUI
# ---------------------------------------------------------------------------

class TestLauncher:
    def test_launcher_choose_mpcfill(self, tk_root):
        from gui.main import Launcher
        launcher = Launcher(tk_root)
        launcher._choose_mpcfill()
        assert launcher.choice == "mpcfill"

    def test_launcher_choose_web_load(self, tk_root):
        from gui.main import Launcher
        launcher = Launcher(tk_root)
        launcher._choose_web_load()
        assert launcher.choice == "webload"


class TestCleanCache:
    def test_clean_cache_blocked_while_running(self, web_load_app):
        import tkinter.messagebox as messagebox
        from unittest.mock import patch
        
        web_load_app.running = True
        
        with patch.object(messagebox, "showerror") as mock_error:
            web_load_app._on_clean_cache()
            mock_error.assert_called_once()
            
    def test_clean_cache_cancelled(self, web_load_app):
        from unittest.mock import patch, MagicMock
        import gui.main
        
        web_load_app.running = False
        
        # Mock dialog to return accepted = False
        mock_dialog = MagicMock()
        mock_dialog.accepted = False
        
        with patch("gui.main.CleanCacheDialog", return_value=mock_dialog), \
             patch("shutil.rmtree") as mock_rmtree:
            web_load_app._on_clean_cache()
            mock_rmtree.assert_not_called()
            
    def test_clean_cache_no_selection_warning(self, web_load_app):
        from unittest.mock import patch, MagicMock
        import gui.main
        import tkinter.messagebox as messagebox
        
        web_load_app.running = False
        
        # Mock dialog to return accepted = True but no options selected
        mock_dialog = MagicMock()
        mock_dialog.accepted = True
        mock_dialog.scryfall_deck_var.get.return_value = False
        mock_dialog.scryfall_cache_var.get.return_value = False
        mock_dialog.mpcfill_cache_var.get.return_value = False
        
        with patch("gui.main.CleanCacheDialog", return_value=mock_dialog), \
             patch.object(messagebox, "showwarning") as mock_warning, \
             patch("shutil.rmtree") as mock_rmtree:
            web_load_app._on_clean_cache()
            mock_warning.assert_called_once_with("Sin selección", "Debes seleccionar al menos un elemento para limpiar.", parent=web_load_app.root)
            mock_rmtree.assert_not_called()
            
    def test_clean_cache_confirmed_deletion(self, web_load_app):
        from unittest.mock import patch, MagicMock
        import gui.main
        import tkinter.messagebox as messagebox
        from pathlib import Path
        
        web_load_app.running = False
        
        mock_dialog = MagicMock()
        mock_dialog.accepted = True
        mock_dialog.scryfall_deck_var.get.return_value = True
        mock_dialog.scryfall_cache_var.get.return_value = True
        mock_dialog.mpcfill_cache_var.get.return_value = False
        
        with patch("gui.main.CleanCacheDialog", return_value=mock_dialog), \
             patch.object(messagebox, "askyesno", return_value=True) as mock_confirm, \
             patch.object(messagebox, "showinfo") as mock_info, \
             patch("shutil.rmtree") as mock_rmtree, \
             patch("gui.main.work_dir", return_value=Path("/dummy/workdir")):
            web_load_app._on_clean_cache()
            
            mock_confirm.assert_called_once()
            assert mock_rmtree.call_count == 2
            mock_rmtree.assert_any_call(Path("/dummy/workdir/scryfall"), ignore_errors=True)
            mock_rmtree.assert_any_call(Path("/dummy/workdir/scryfall_cache"), ignore_errors=True)
            mock_info.assert_called_once()

    def test_refresh_generate_state_with_downloads(self, web_load_app, tmp_path):
        from unittest.mock import patch
        
        web_load_app.deck_data = {
            "name": "My Deck",
            "id": "12345"
        }
        
        # Test case 1: Folder does not exist or has no PNGs -> buttons disabled
        with patch("gui.main.work_dir", return_value=tmp_path):
            web_load_app._refresh_generate_state()
            assert "disabled" in web_load_app.soriano_btn.state()
            assert "disabled" in web_load_app.fronts_only_btn.state()
            
        # Test case 2: Folder exists and contains a PNG -> buttons enabled
        deck_dir = tmp_path / "scryfall" / "My_Deck_12345"
        deck_dir.mkdir(parents=True, exist_ok=True)
        (deck_dir / "card.png").write_text("dummy image data")
        
        with patch("gui.main.work_dir", return_value=tmp_path):
            web_load_app._refresh_generate_state()
            assert "disabled" not in web_load_app.soriano_btn.state()
            assert "disabled" not in web_load_app.fronts_only_btn.state()

    def test_start_validation_missing_deck(self, web_load_app):
        from unittest.mock import patch
        import tkinter.messagebox as messagebox
        import gui.main
        
        web_load_app.deck_data = None
        with patch.object(messagebox, "showerror") as mock_error:
            web_load_app._start(fronts_only=True)
            mock_error.assert_called_once_with(gui.main.APP_TITLE, "Primero debes cargar un mazo de Moxfield.")

    def test_start_validation_missing_cardback_duplex(self, web_load_app):
        from unittest.mock import patch
        import tkinter.messagebox as messagebox
        import gui.main
        
        web_load_app.deck_data = {"name": "Test", "id": "123"}
        web_load_app.local_backs = []
        with patch.object(messagebox, "showerror") as mock_error:
            web_load_app._start(fronts_only=False)
            mock_error.assert_called_once()
            assert "lista de Traseras" in mock_error.call_args[0][1]

    def test_start_validation_missing_images_on_disk(self, web_load_app, tmp_path):
        from unittest.mock import patch
        import tkinter.messagebox as messagebox
        import gui.main
        
        web_load_app.deck_data = {
            "name": "Test Deck",
            "id": "123",
            "mainboard": [{"name": "Plains", "set": "unp", "cn": "1", "quantity": 1}]
        }
        web_load_app.zone_mainboard.set(True)
        web_load_app.local_backs = [Path("dummy_back.jpg")]
        
        # Folder is empty, so Plains.png is missing on disk
        with patch("gui.main.work_dir", return_value=tmp_path), \
             patch.object(messagebox, "showerror") as mock_error:
            web_load_app._start(fronts_only=False)
            mock_error.assert_called_once()
            assert "Faltan imágenes" in mock_error.call_args[0][1]
            assert "Plains" in mock_error.call_args[0][1]

    def test_work_duplex_mapping_and_pipeline_run(self, web_load_app, tmp_path):
        from unittest.mock import patch
        from pathlib import Path
        
        # Setup mock deck with 1 single-faced card and 1 DFC
        web_load_app.deck_data = {
            "name": "Test Deck",
            "id": "123",
            "mainboard": [
                {"name": "Plains", "set": "unp", "cn": "1", "quantity": 2},
                {"name": "Delver", "set": "isd", "cn": "51", "quantity": 1}
            ]
        }
        web_load_app.zone_mainboard.set(True)
        
        # Populate files in tmp_path
        deck_dir = tmp_path / "scryfall" / "Test_Deck_123"
        deck_dir.mkdir(parents=True, exist_ok=True)
        
        plains_img = deck_dir / "Plains_UNP_1.png"
        plains_img.write_text("plains")
        
        delver_front = deck_dir / "Delver_ISD_51_front.png"
        delver_front.write_text("delver front")
        delver_back = deck_dir / "Delver_ISD_51_back.png"
        delver_back.write_text("delver back")
        
        # Add local manual front/back cards
        local_front = tmp_path / "my_custom_front.jpg"
        local_front.write_text("front")
        local_back = tmp_path / "my_custom_back.jpg"
        local_back.write_text("back")
        
        web_load_app.local_fronts = [local_front]
        web_load_app.local_backs = [local_back]
        web_load_app.front_back_paths = [local_back]
        web_load_app.local_front_crop = [True]
        web_load_app.local_back_crop = [True]
        
        with patch("gui.main.work_dir", return_value=tmp_path), \
             patch("gui.main.output_dir", return_value=tmp_path), \
             patch("gui.main.run_locals_only") as mock_run_locals:
            
            web_load_app._work(fronts_only=False)
            
            # Verify run_locals_only is called with correct parameters
            mock_run_locals.assert_called_once()
            args, kwargs = mock_run_locals.call_args
            
            # combined_fronts: 2x Plains, 1x Delver front, 1x local_front
            assert args[0] == [plains_img, plains_img, delver_front, local_front]
            
            # default_cardback: first in local_backs
            assert args[1] == local_back
            
            # extra_backs: 2x None (Plains), 1x Delver back, 1x local_back
            assert kwargs["extra_backs"] == [None, None, delver_back, local_back]
            
            # crop_map: False for Scryfall, True for local front and back
            crop_map = kwargs["local_crop_map"]
            assert crop_map[plains_img] is False
            assert crop_map[delver_front] is False
            assert crop_map[delver_back] is False
            assert crop_map[local_front] is True
            assert crop_map[local_back] is True




