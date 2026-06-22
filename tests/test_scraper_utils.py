"""Tests for src/scraper_utils.py."""

from PIL import Image

from src.scraper_utils import generate_fallback_back


class TestGenerateFallbackBack:
    def test_creates_file_at_path(self, tmp_path):
        path = tmp_path / "back.png"
        generate_fallback_back(path, "#0A1628", "#B0B8C8")
        assert path.exists()

    def test_returns_the_path(self, tmp_path):
        path = tmp_path / "back.png"
        result = generate_fallback_back(path, "#0A1628", "#B0B8C8")
        assert result == path

    def test_default_size(self, tmp_path):
        path = tmp_path / "back.png"
        generate_fallback_back(path, "#000000", "#FFFFFF")
        img = Image.open(path)
        assert img.size == (480, 670)

    def test_custom_size(self, tmp_path):
        path = tmp_path / "back.png"
        generate_fallback_back(path, "#000000", "#FFFFFF", size=(100, 140))
        img = Image.open(path)
        assert img.size == (100, 140)

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "deep" / "back.png"
        generate_fallback_back(path, "#123456", "#ABCDEF")
        assert path.exists()

    def test_image_is_rgb(self, tmp_path):
        path = tmp_path / "back.png"
        generate_fallback_back(path, "#FF0000", "#00FF00")
        img = Image.open(path)
        assert img.mode == "RGB"

    def test_background_color_applied(self, tmp_path):
        path = tmp_path / "back.png"
        generate_fallback_back(path, "#FF0000", "#000000", size=(50, 70))
        img = Image.open(path)
        cx, cy = img.size[0] // 2, img.size[1] // 2
        r, g, b = img.getpixel((cx, cy))
        assert r > 200
        assert g < 50
        assert b < 50
