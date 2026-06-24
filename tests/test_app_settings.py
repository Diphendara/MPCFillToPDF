import json

import pytest

from src.app_settings import (
    DEFAULT_CUT_LINE_COLOR,
    DEFAULT_CUT_LINE_OVER_BACKS,
    DEFAULT_CUT_LINE_OVER_CARDS,
    DEFAULT_CUT_LINE_OVER_FRONTS,
    DEFAULT_CUT_LINE_STYLE,
    DEFAULT_CUT_LINE_WIDTH,
    AppSettings,
    load_settings,
    save_settings,
)


class TestLoadSettings:
    def test_returns_defaults_when_no_file(self, tmp_path):
        s = load_settings(tmp_path)
        assert s.output_dir is None
        assert s.cut_line_color == DEFAULT_CUT_LINE_COLOR
        assert s.cut_line_style == DEFAULT_CUT_LINE_STYLE

    def test_roundtrip(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        s = AppSettings(output_dir=out, cut_line_color="#ff0000", cut_line_style="full")
        save_settings(s, tmp_path)
        loaded = load_settings(tmp_path)
        assert loaded.output_dir == out
        assert loaded.cut_line_color == "#ff0000"
        assert loaded.cut_line_style == "full"

    def test_corrupted_json_returns_defaults(self, tmp_path):
        settings_file = tmp_path / "MPCFillToPDF" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text("{ not valid json }", encoding="utf-8")
        s = load_settings(tmp_path)
        assert s.cut_line_color == DEFAULT_CUT_LINE_COLOR
        assert s.cut_line_style == DEFAULT_CUT_LINE_STYLE

    def test_nonexistent_output_dir_is_ignored(self, tmp_path):
        settings_file = tmp_path / "MPCFillToPDF" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        data = {
            "output_dir": str(tmp_path / "does_not_exist"),
            "cut_line_color": "#000000",
            "cut_line_style": "ticks",
        }
        settings_file.write_text(json.dumps(data), encoding="utf-8")
        s = load_settings(tmp_path)
        assert s.output_dir is None

    def test_invalid_color_falls_back_to_default(self, tmp_path):
        settings_file = tmp_path / "MPCFillToPDF" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        data = {"cut_line_color": "notacolor", "cut_line_style": "ticks"}
        settings_file.write_text(json.dumps(data), encoding="utf-8")
        s = load_settings(tmp_path)
        assert s.cut_line_color == DEFAULT_CUT_LINE_COLOR

    def test_invalid_style_falls_back_to_default(self, tmp_path):
        settings_file = tmp_path / "MPCFillToPDF" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        data = {"cut_line_color": "#000000", "cut_line_style": "unknown"}
        settings_file.write_text(json.dumps(data), encoding="utf-8")
        s = load_settings(tmp_path)
        assert s.cut_line_style == DEFAULT_CUT_LINE_STYLE

    def test_cut_line_width_roundtrip(self, tmp_path):
        s = AppSettings(cut_line_width=2.5)
        save_settings(s, tmp_path)
        assert load_settings(tmp_path).cut_line_width == pytest.approx(2.5)

    def test_cut_line_width_invalid_falls_back(self, tmp_path):
        settings_file = tmp_path / "MPCFillToPDF" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text(json.dumps({"cut_line_width": "bad"}), encoding="utf-8")
        assert load_settings(tmp_path).cut_line_width == DEFAULT_CUT_LINE_WIDTH

    def test_cut_line_width_clamped_to_min(self, tmp_path):
        settings_file = tmp_path / "MPCFillToPDF" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text(json.dumps({"cut_line_width": 0.0}), encoding="utf-8")
        assert load_settings(tmp_path).cut_line_width == pytest.approx(0.1)

    def test_cut_line_width_clamped_to_max(self, tmp_path):
        settings_file = tmp_path / "MPCFillToPDF" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text(json.dumps({"cut_line_width": 99.0}), encoding="utf-8")
        assert load_settings(tmp_path).cut_line_width == pytest.approx(10.0)

    def test_cut_line_over_cards_roundtrip(self, tmp_path):
        s = AppSettings(cut_line_over_cards=True)
        save_settings(s, tmp_path)
        assert load_settings(tmp_path).cut_line_over_cards is True

    def test_cut_line_over_cards_default_is_false(self, tmp_path):
        assert load_settings(tmp_path).cut_line_over_cards == DEFAULT_CUT_LINE_OVER_CARDS

    def test_cut_line_over_fronts_roundtrip(self, tmp_path):
        s = AppSettings(cut_line_over_fronts=False)
        save_settings(s, tmp_path)
        assert load_settings(tmp_path).cut_line_over_fronts is False

    def test_cut_line_over_fronts_default_is_true(self, tmp_path):
        assert load_settings(tmp_path).cut_line_over_fronts == DEFAULT_CUT_LINE_OVER_FRONTS

    def test_cut_line_over_backs_roundtrip(self, tmp_path):
        s = AppSettings(cut_line_over_backs=False)
        save_settings(s, tmp_path)
        assert load_settings(tmp_path).cut_line_over_backs is False

    def test_cut_line_over_backs_default_is_true(self, tmp_path):
        assert load_settings(tmp_path).cut_line_over_backs == DEFAULT_CUT_LINE_OVER_BACKS


class TestSaveSettings:
    def test_creates_parent_dirs(self, tmp_path):
        s = AppSettings()
        save_settings(s, tmp_path)
        assert (tmp_path / "MPCFillToPDF" / "settings.json").exists()

    def test_null_output_dir_saved_as_none(self, tmp_path):
        s = AppSettings(output_dir=None)
        save_settings(s, tmp_path)
        data = json.loads((tmp_path / "MPCFillToPDF" / "settings.json").read_text())
        assert data["output_dir"] is None
