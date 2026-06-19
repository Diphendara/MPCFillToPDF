"""Tests for src/downloader.py — single-image and batch download logic."""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from src.cancellation import Cancelled
from src.downloader import (
    DownloadPartialError,
    DownloadPermissionError,
    DownloadRateLimitError,
    DownloadTimeoutError,
    _is_rate_limit_error,
    download_all,
    download_image,
)

# ─── helpers ────────────────────────────────────────────────────────────────


def _fake_gdown(url: str, path: str, quiet: bool) -> None:
    """Simulate a successful gdown download by writing a tiny file."""
    Path(path).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8)


class _FakeFileURLRetrievalError(Exception):
    """Name detected by the 'FileURLRetrievalError' string check in downloader."""


# ─── _is_rate_limit_error ────────────────────────────────────────────────────


def test_rate_limit_detected_by_status_code():
    exc = requests.HTTPError(response=type("R", (), {"status_code": 429})())
    assert _is_rate_limit_error(exc)


def test_rate_limit_detected_by_503():
    exc = requests.HTTPError(response=type("R", (), {"status_code": 503})())
    assert _is_rate_limit_error(exc)


def test_rate_limit_detected_by_keyword():
    assert _is_rate_limit_error(Exception("429 Too Many Requests"))
    assert _is_rate_limit_error(Exception("quota exceeded"))


def test_rate_limit_not_detected_for_generic_error():
    assert not _is_rate_limit_error(ValueError("something else"))


# ─── download_image ──────────────────────────────────────────────────────────


def test_download_cache_hit_skips_gdown(tmp_path):
    dest = tmp_path / "raw"
    dest.mkdir()
    cached = dest / "DRIVEID.jpg"
    cached.write_bytes(b"cached content")

    with patch("gdown.download") as mock_dl:
        result = download_image("DRIVEID", dest, "card.jpg")
        mock_dl.assert_not_called()

    assert result == cached


def test_download_creates_file(tmp_path):
    with patch("gdown.download", side_effect=_fake_gdown):
        result = download_image("ID001", tmp_path / "raw", "card.jpg")
    assert result.exists()
    assert result.stat().st_size > 0


def test_download_output_named_by_drive_id(tmp_path):
    with patch("gdown.download", side_effect=_fake_gdown):
        result = download_image("MYID", tmp_path / "raw", "something.jpg")
    assert result.name.startswith("MYID")


def test_download_permission_error(tmp_path):
    def _raise(*a, **kw):
        raise _FakeFileURLRetrievalError("no access")

    with patch("gdown.download", side_effect=_raise):
        with pytest.raises(DownloadPermissionError) as exc_info:
            download_image("ID001", tmp_path / "raw", "card.jpg")
    assert exc_info.value.drive_id == "ID001"
    assert exc_info.value.card_name == "card.jpg"


def test_download_timeout_error(tmp_path):
    def _raise(*a, **kw):
        raise requests.exceptions.Timeout("timed out")

    with patch("gdown.download", side_effect=_raise):
        with pytest.raises(DownloadTimeoutError) as exc_info:
            download_image("ID001", tmp_path / "raw", "card.jpg")
    assert exc_info.value.drive_id == "ID001"


def test_download_rate_limit_exhausted(tmp_path):
    with patch("gdown.download", side_effect=Exception("429 Too Many Requests")):
        with patch("time.sleep"):  # skip backoff delays
            with pytest.raises(DownloadRateLimitError):
                download_image("ID001", tmp_path / "raw", "card.jpg")


def test_download_rate_limit_retries_then_succeeds(tmp_path):
    attempts = {"n": 0}

    def _flaky(*a, **kw):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise Exception("503 Service Unavailable")
        _fake_gdown(*a, **kw)

    with patch("gdown.download", side_effect=_flaky):
        with patch("time.sleep"):
            result = download_image("ID001", tmp_path / "raw", "card.jpg")
    assert result.exists()
    assert attempts["n"] == 3


# ─── download_all ────────────────────────────────────────────────────────────


def test_download_all_returns_all_results(tmp_path):
    with patch("gdown.download", side_effect=_fake_gdown):
        results = download_all(
            [("ID1", "a.jpg"), ("ID2", "b.jpg")],
            tmp_path / "raw",
        )
    assert set(results.keys()) == {"ID1", "ID2"}
    for p in results.values():
        assert p.exists()


def test_download_all_empty_list(tmp_path):
    results = download_all([], tmp_path / "raw")
    assert results == {}


def test_download_all_progress_callback_fires_per_image(tmp_path):
    calls = []

    def _cb(done, total):
        calls.append((done, total))

    with patch("gdown.download", side_effect=_fake_gdown):
        download_all(
            [("ID1", "a.jpg"), ("ID2", "b.jpg"), ("ID3", "c.jpg")],
            tmp_path / "raw",
            progress_callback=_cb,
        )

    assert len(calls) == 3
    assert all(t == 3 for _, t in calls)
    assert sorted(d for d, _ in calls) == [1, 2, 3]


def test_download_all_on_image_done_callback(tmp_path):
    done_ids = []

    with patch("gdown.download", side_effect=_fake_gdown):
        download_all(
            [("ID1", "a.jpg"), ("ID2", "b.jpg")],
            tmp_path / "raw",
            on_image_done=done_ids.append,
        )

    assert set(done_ids) == {"ID1", "ID2"}


def test_download_all_cancel_event_raises_cancelled(tmp_path):
    event = threading.Event()
    event.set()

    with patch("gdown.download", side_effect=_fake_gdown):
        with pytest.raises(Cancelled):
            download_all(
                [("ID1", "a.jpg")],
                tmp_path / "raw",
                cancel_event=event,
            )


def test_download_all_propagates_permission_error_as_partial(tmp_path):
    def _raise(*a, **kw):
        raise _FakeFileURLRetrievalError("no access")

    with patch("gdown.download", side_effect=_raise):
        with pytest.raises(DownloadPartialError) as exc_info:
            download_all([("ID1", "a.jpg")], tmp_path / "raw")

    err = exc_info.value
    assert len(err.permission_errors) == 1
    assert err.permission_errors[0] == ("ID1", "a.jpg")
    assert err.timeout_errors == []


def test_download_all_propagates_timeout_error_as_partial(tmp_path):
    def _raise(*a, **kw):
        raise requests.exceptions.Timeout("timeout")

    with patch("gdown.download", side_effect=_raise):
        with patch("time.sleep"):  # skip the retry delay
            with pytest.raises(DownloadPartialError) as exc_info:
                download_all([("ID1", "a.jpg")], tmp_path / "raw")

    err = exc_info.value
    assert len(err.timeout_errors) == 1
    assert err.timeout_errors[0] == ("ID1", "a.jpg")
    assert err.permission_errors == []


def test_download_all_continues_after_partial_failure(tmp_path):
    """Successful downloads complete even when some images fail."""

    def _mixed(url: str, path: str, quiet: bool) -> None:
        if "BAD" in url:
            raise _FakeFileURLRetrievalError("no access")
        Path(path).write_bytes(b"img")

    with patch("gdown.download", side_effect=_mixed):
        with pytest.raises(DownloadPartialError) as exc_info:
            download_all(
                [("GOOD1", "good1.jpg"), ("BAD", "bad.jpg"), ("GOOD2", "good2.jpg")],
                tmp_path / "raw",
            )

    err = exc_info.value
    assert len(err.permission_errors) == 1
    assert err.permission_errors[0][0] == "BAD"
    # Good images still downloaded
    assert (tmp_path / "raw" / "GOOD1.jpg").exists()
    assert (tmp_path / "raw" / "GOOD2.jpg").exists()


def test_download_all_timeout_retry_succeeds(tmp_path):
    """Timed-out images that succeed on retry are NOT included in partial errors."""
    attempts: dict[str, int] = {}

    def _flaky(url: str, path: str, quiet: bool) -> None:
        drive_id = url.split("id=")[1]
        attempts[drive_id] = attempts.get(drive_id, 0) + 1
        if attempts[drive_id] == 1:
            raise requests.exceptions.Timeout("timeout first time")
        Path(path).write_bytes(b"img")

    with patch("gdown.download", side_effect=_flaky):
        with patch("time.sleep"):  # skip retry delay
            results = download_all([("ID1", "a.jpg")], tmp_path / "raw")

    assert "ID1" in results
    assert attempts["ID1"] == 2  # first attempt timed out, retry succeeded
