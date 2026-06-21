"""Tests for src/config.py — Google Drive API key resolution cascade."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import patch

from src.config import get_drive_api_key


class TestGetDriveApiKey:
    def test_returns_none_when_no_config_and_no_bundled(self, tmp_path):
        with patch("src.config._PROJECT_ROOT", tmp_path):
            assert get_drive_api_key() is None

    def test_reads_key_from_config_json(self, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"google_drive_api_key": "AIzaTestKey123"}), encoding="utf-8"
        )
        with patch("src.config._PROJECT_ROOT", tmp_path):
            assert get_drive_api_key() == "AIzaTestKey123"

    def test_ignores_placeholder_key(self, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"google_drive_api_key": "YOUR_API_KEY_HERE"}), encoding="utf-8"
        )
        with patch("src.config._PROJECT_ROOT", tmp_path):
            assert get_drive_api_key() is None

    def test_ignores_empty_key(self, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"google_drive_api_key": ""}), encoding="utf-8"
        )
        with patch("src.config._PROJECT_ROOT", tmp_path):
            assert get_drive_api_key() is None

    def test_missing_key_field_in_json(self, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"other_field": "value"}), encoding="utf-8"
        )
        with patch("src.config._PROJECT_ROOT", tmp_path):
            assert get_drive_api_key() is None

    def test_bundled_key_takes_priority_over_config_json(self, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"google_drive_api_key": "from_config_json"}), encoding="utf-8"
        )
        fake_module = types.ModuleType("src._bundled_key")
        fake_module._get_key = lambda: "bundled_value"
        with patch.dict(sys.modules, {"src._bundled_key": fake_module}):
            with patch("src.config._PROJECT_ROOT", tmp_path):
                assert get_drive_api_key() == "bundled_value"

    def test_empty_bundled_key_falls_through_to_config_json(self, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"google_drive_api_key": "from_config"}), encoding="utf-8"
        )
        fake_module = types.ModuleType("src._bundled_key")
        fake_module._get_key = lambda: ""
        with patch.dict(sys.modules, {"src._bundled_key": fake_module}):
            with patch("src.config._PROJECT_ROOT", tmp_path):
                assert get_drive_api_key() == "from_config"

    def test_strips_whitespace_from_config_key(self, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"google_drive_api_key": "  AIzaSpaced  "}), encoding="utf-8"
        )
        with patch("src.config._PROJECT_ROOT", tmp_path):
            assert get_drive_api_key() == "AIzaSpaced"
