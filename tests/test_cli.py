"""Tests for cli/main.py — argument validation and output logic."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import make_rgb_image, make_xml


# ---------------------------------------------------------------------------
# _validate_local_images
# ---------------------------------------------------------------------------

def test_validate_nonexistent_file_exits(tmp_path):
    from cli.main import _validate_local_images
    with pytest.raises(SystemExit) as exc:
        _validate_local_images([str(tmp_path / "missing.jpg")], "--local-fronts")
    assert exc.value.code == 1


def test_validate_unsupported_extension_exits(tmp_path):
    p = tmp_path / "file.doc"
    p.write_bytes(b"data")
    from cli.main import _validate_local_images
    with pytest.raises(SystemExit) as exc:
        _validate_local_images([str(p)], "--local-fronts")
    assert exc.value.code == 1


def test_validate_valid_image_returns_path(tmp_path):
    p = make_rgb_image(tmp_path / "card.jpg")
    from cli.main import _validate_local_images
    result = _validate_local_images([str(p)], "--local-fronts")
    assert result == [p]


def test_validate_multiple_valid_images(tmp_path):
    paths = [make_rgb_image(tmp_path / f"img{i}.jpg") for i in range(3)]
    from cli.main import _validate_local_images
    result = _validate_local_images([str(p) for p in paths], "--local-fronts")
    assert result == paths


@pytest.mark.parametrize("ext", [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"])
def test_validate_all_supported_extensions(tmp_path, ext):
    p = tmp_path / f"file{ext}"
    p.write_bytes(b"\xff\xd8\xff")  # minimal bytes
    from cli.main import _validate_local_images
    result = _validate_local_images([str(p)], "--local-fronts")
    assert result == [p]


# ---------------------------------------------------------------------------
# _progress
# ---------------------------------------------------------------------------

def test_progress_shows_stage_label(capsys):
    from cli.main import _progress, _stage_started_at
    _stage_started_at.clear()
    _progress("download", 3, 10)
    out = capsys.readouterr().out
    assert "Descargando" in out
    assert "3/10" in out


def test_progress_newline_when_complete(capsys):
    from cli.main import _progress, _stage_started_at
    _stage_started_at.clear()
    _progress("crop", 5, 5)
    out = capsys.readouterr().out
    assert out.endswith("\n")


def test_progress_no_newline_mid_run(capsys):
    from cli.main import _progress, _stage_started_at
    _stage_started_at.clear()
    _progress("download", 3, 10)
    out = capsys.readouterr().out
    assert not out.endswith("\n")


def test_progress_verify_label(capsys):
    from cli.main import _progress, _stage_started_at
    _stage_started_at.clear()
    _progress("verify", 1, 5)
    out = capsys.readouterr().out
    assert "Verificando" in out


# ---------------------------------------------------------------------------
# main() — argument-level validation (no network / no pipeline)
# ---------------------------------------------------------------------------

def test_main_missing_xml_dir_exits_when_no_locals(tmp_path):
    """xml/ doesn't exist and no --local-fronts → exit 1."""
    with patch.object(sys, "argv", [
        "cli",
        f"--xml-dir={tmp_path / 'nonexistent'}",
        f"--out-dir={tmp_path / 'out'}",
        f"--workdir={tmp_path / 'work'}",
    ]):
        with pytest.raises(SystemExit) as exc:
            from cli import main as cli_module
            import importlib
            importlib.reload(cli_module)
            cli_module.main()
        assert exc.value.code == 1


def test_main_empty_xml_dir_returns_without_pdf(tmp_path, capsys):
    """xml/ exists but is empty → print message, no error."""
    xml_dir = tmp_path / "xml"
    xml_dir.mkdir()
    out_dir = tmp_path / "out"

    with patch.object(sys, "argv", [
        "cli",
        f"--xml-dir={xml_dir}",
        f"--out-dir={out_dir}",
        f"--workdir={tmp_path / 'work'}",
    ]):
        from cli import main as cli_module
        import importlib
        importlib.reload(cli_module)
        cli_module.main()

    out = capsys.readouterr().out
    assert "No hay archivos" in out


def test_main_locals_only_missing_cardback_exits(tmp_path):
    """--local-fronts without --local-cardback (no XML) → exit 1."""
    front = make_rgb_image(tmp_path / "front.jpg")

    with patch.object(sys, "argv", [
        "cli",
        f"--xml-dir={tmp_path / 'nonexistent'}",
        f"--out-dir={tmp_path / 'out'}",
        f"--workdir={tmp_path / 'work'}",
        f"--local-fronts={front}",
    ]):
        with pytest.raises(SystemExit) as exc:
            from cli import main as cli_module
            import importlib
            importlib.reload(cli_module)
            cli_module.main()
        assert exc.value.code == 1


def test_main_more_backs_than_fronts_exits(tmp_path):
    """--local-backs count > --local-fronts count → exit 1."""
    front = make_rgb_image(tmp_path / "front.jpg")
    back1 = make_rgb_image(tmp_path / "back1.jpg")
    back2 = make_rgb_image(tmp_path / "back2.jpg")

    # nargs="+" collects multiple values from a single flag occurrence.
    with patch.object(sys, "argv", [
        "cli",
        f"--xml-dir={tmp_path / 'nonexistent'}",
        f"--out-dir={tmp_path / 'out'}",
        f"--workdir={tmp_path / 'work'}",
        "--local-fronts", str(front),
        "--local-backs", str(back1), str(back2),
        f"--local-cardback={back1}",
    ]):
        with pytest.raises(SystemExit) as exc:
            from cli import main as cli_module
            import importlib
            importlib.reload(cli_module)
            cli_module.main()
        assert exc.value.code == 1
