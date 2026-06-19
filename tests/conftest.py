"""Shared fixtures for all test modules."""

from pathlib import Path

import pytest
from PIL import Image


def make_rgb_image(
    path: Path, width: int = 200, height: int = 280, color: tuple = (180, 100, 60)
) -> Path:
    """Write a tiny solid-colour JPEG to *path* and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), color).save(str(path), format="JPEG")
    return path


def make_xml(
    path: Path,
    fronts: list[dict],
    backs: list[dict] | None = None,
    cardback_id: str = "CB001",
    quantity: int = 9,
) -> Path:
    """Write a minimal MPCFill XML to *path* and return it.

    Each entry in *fronts* / *backs* is a dict with keys 'id', 'name', 'slots'
    (slots is a comma-separated string like "0,1,2").
    """

    def _cards(items):
        parts = []
        for c in items or []:
            parts.append(
                f"        <card>"
                f"<id>{c['id']}</id>"
                f"<name>{c.get('name', c['id'])}</name>"
                f"<slots>{c['slots']}</slots>"
                f"</card>"
            )
        return "\n".join(parts)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f"<order>\n"
        f"    <details><quantity>{quantity}</quantity></details>\n"
        f"    <fronts>\n{_cards(fronts)}\n    </fronts>\n"
        f"    <backs>\n{_cards(backs)}\n    </backs>\n"
        f"    <cardback>{cardback_id}</cardback>\n"
        f"</order>\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def img(tmp_path) -> Path:
    """A single tiny JPEG image."""
    return make_rgb_image(tmp_path / "card.jpg")


@pytest.fixture
def img_factory(tmp_path):
    """Factory: img_factory(name, width, height, color) → Path."""

    def _make(name="card.jpg", width=200, height=280, color=(180, 100, 60)):
        return make_rgb_image(tmp_path / name, width, height, color)

    return _make


@pytest.fixture
def xml_factory(tmp_path):
    """Factory: xml_factory(fronts, backs, cardback_id, quantity, name) → Path."""

    def _make(fronts, backs=None, cardback_id="CB001", quantity=9, name="test"):
        return make_xml(tmp_path / f"{name}.xml", fronts, backs, cardback_id, quantity)

    return _make
