"""Stable cache keys for image transformations."""

from __future__ import annotations

from pathlib import Path

TRANSFORM_CACHE_VERSION = "v2"


def crop_cache_filename(
    identity: str,
    suffix: str,
    crop_borders: bool,
    trim_size_mm: tuple[float, float],
) -> str:
    """Return a cache name that changes with every output-affecting setting."""
    crop_mode = "crop" if crop_borders else "nocrop"
    width, height = trim_size_mm
    layout = f"{width:g}x{height:g}".replace(".", "_")
    safe_identity = identity.replace("/", "_").replace("\\", "_")
    return f"{safe_identity}_{TRANSFORM_CACHE_VERSION}_{crop_mode}_{layout}{suffix}"


def crop_cache_path(
    cache_dir: Path,
    identity: str,
    raw_path: Path,
    crop_borders: bool,
    trim_size_mm: tuple[float, float],
) -> Path:
    """Return the versioned cache path for a transformed image."""
    suffix = raw_path.suffix.lower() or ".jpg"
    return cache_dir / crop_cache_filename(identity, suffix, crop_borders, trim_size_mm)
