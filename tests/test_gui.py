"""Tests for gui/main.py — state management and logic without rendering.

Tkinter is instantiated headlessly (window withdrawn).  Tests are skipped
automatically when no display is available (e.g. headless CI).
"""

import tkinter as tk

import pytest

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


# ---------------------------------------------------------------------------
# _build_crop_map
# ---------------------------------------------------------------------------


class TestBuildCropMap:
    def test_empty_returns_empty(self, app):
        assert app._build_crop_map() == {}

    def test_back_crop_true(self, app, tmp_path):
        p = make_rgb_image(tmp_path / "back.jpg")
        app.state.local_backs.append(p)
        app.state.local_back_crop.append(True)
        m = app._build_crop_map()
        assert m.get(p) is True

    def test_back_crop_false(self, app, tmp_path):
        p = make_rgb_image(tmp_path / "back.jpg")
        app.state.local_backs.append(p)
        app.state.local_back_crop.append(False)
        m = app._build_crop_map()
        assert m.get(p) is False

    def test_front_overrides_back_for_same_path(self, app, tmp_path):
        """When a path appears as both back and front, front's setting wins."""
        p = make_rgb_image(tmp_path / "shared.jpg")
        app.state.local_backs.append(p)
        app.state.local_back_crop.append(True)
        app.state.local_fronts.append(p)
        app.state.front_back_paths.append(p)
        app.state.local_front_crop.append(False)
        assert app._build_crop_map()[p] is False

    def test_multiple_items(self, app, tmp_path):
        for i in range(3):
            p = make_rgb_image(tmp_path / f"img{i}.jpg")
            app.state.local_fronts.append(p)
            app.state.front_back_paths.append(None)
            app.state.local_front_crop.append(bool(i % 2))
        m = app._build_crop_map()
        fronts = app.state.local_fronts
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
        app.state.local_fronts.append(make_rgb_image(tmp_path / "front.jpg"))
        app.state.front_back_paths.append(back)
        assert app._resolve_extra_backs() == [back]

    def test_none_assignment_passes_through(self, app, tmp_path):
        app.state.local_fronts.append(make_rgb_image(tmp_path / "front.jpg"))
        app.state.front_back_paths.append(None)
        assert app._resolve_extra_backs() == [None]

    def test_mixed_assignments(self, app, tmp_path):
        back = make_rgb_image(tmp_path / "back.jpg")
        for i in range(3):
            app.state.local_fronts.append(make_rgb_image(tmp_path / f"f{i}.jpg"))
            app.state.front_back_paths.append(back if i == 1 else None)
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
        app.state.xml_paths.append(xml)
        app.running = False
        app._refresh_generate_state()
        assert "disabled" not in str(app.soriano_btn.state())

    def test_disabled_fronts_alone_no_backs(self, app, tmp_path):
        app.state.local_fronts.append(make_rgb_image(tmp_path / "f.jpg"))
        app.state.front_back_paths.append(None)
        app.state.local_front_crop.append(False)
        app.running = False
        app._refresh_generate_state()
        assert "disabled" in str(app.soriano_btn.state())

    def test_enabled_fronts_with_backs(self, app, tmp_path):
        front = make_rgb_image(tmp_path / "f.jpg")
        back = make_rgb_image(tmp_path / "b.jpg")
        app.state.local_fronts.append(front)
        app.state.front_back_paths.append(back)
        app.state.local_front_crop.append(False)
        app.state.local_backs.append(back)
        app.state.local_back_crop.append(False)
        app.running = False
        app._refresh_generate_state()
        assert "disabled" not in str(app.soriano_btn.state())

    def test_disabled_while_running(self, app, tmp_path):
        xml = make_xml(
            tmp_path / "t.xml",
            fronts=[{"id": "F1", "name": "C1", "slots": "0"}],
        )
        app.state.xml_paths.append(xml)
        app.running = True
        app._refresh_generate_state()
        assert "disabled" in str(app.soriano_btn.state())


# ---------------------------------------------------------------------------
# Batch crop toggle (_on_front_crop_all / _on_back_crop_all)
# ---------------------------------------------------------------------------


class TestCropAllToggle:
    def test_set_all_fronts_true(self, app, tmp_path):
        for i in range(4):
            app.state.local_fronts.append(make_rgb_image(tmp_path / f"f{i}.jpg"))
            app.state.front_back_paths.append(None)
            app.state.local_front_crop.append(False)
        app._front_crop_all.set(True)
        app._on_front_crop_all()
        assert all(app.state.local_front_crop)

    def test_clear_all_fronts(self, app, tmp_path):
        for i in range(3):
            app.state.local_fronts.append(make_rgb_image(tmp_path / f"f{i}.jpg"))
            app.state.front_back_paths.append(None)
            app.state.local_front_crop.append(True)
        app._front_crop_all.set(False)
        app._on_front_crop_all()
        assert not any(app.state.local_front_crop)

    def test_set_all_backs_true(self, app, tmp_path):
        for i in range(3):
            p = make_rgb_image(tmp_path / f"b{i}.jpg")
            app.state.local_backs.append(p)
            app.state.local_back_crop.append(False)
        app._back_crop_all.set(True)
        app._on_back_crop_all()
        assert all(app.state.local_back_crop)

    def test_clear_all_backs(self, app, tmp_path):
        for i in range(3):
            p = make_rgb_image(tmp_path / f"b{i}.jpg")
            app.state.local_backs.append(p)
            app.state.local_back_crop.append(True)
        app._back_crop_all.set(False)
        app._on_back_crop_all()
        assert not any(app.state.local_back_crop)

    def test_toggle_empty_list_is_noop(self, app):
        app._front_crop_all.set(True)
        app._on_front_crop_all()  # should not raise
        assert app.state.local_front_crop == []


# ---------------------------------------------------------------------------
# Individual crop-change callbacks
# ---------------------------------------------------------------------------


class TestCropChange:
    def test_front_crop_change(self, app, tmp_path):
        app.state.local_fronts.append(make_rgb_image(tmp_path / "f.jpg"))
        app.state.front_back_paths.append(None)
        app.state.local_front_crop.append(False)
        var = tk.BooleanVar(value=True)
        app._on_front_crop_change(0, var)
        assert app.state.local_front_crop[0] is True

    def test_back_crop_change(self, app, tmp_path):
        app.state.local_backs.append(make_rgb_image(tmp_path / "b.jpg"))
        app.state.local_back_crop.append(False)
        var = tk.BooleanVar(value=True)
        app._on_back_crop_change(0, var)
        assert app.state.local_back_crop[0] is True

    def test_crop_change_out_of_range_is_noop(self, app):
        var = tk.BooleanVar(value=True)
        app._on_front_crop_change(99, var)  # no IndexError
