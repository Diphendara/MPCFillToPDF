"""Tests for src/downloader.py — single-image and batch download logic."""
import threading
from pathlib import Path
from unittest.mock import patch, call

import pytest
import requests

from src.cancellation import Cancelled
from src.downloader import (
    DownloadPermissionError,
    DownloadTimeoutError,
    DownloadRateLimitError,
    download_all,
    download_image,
    _is_rate_limit_error,
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


def test_download_all_propagates_permission_error(tmp_path):
    def _raise(*a, **kw):
        raise _FakeFileURLRetrievalError("no access")

    with patch("gdown.download", side_effect=_raise):
        with pytest.raises(DownloadPermissionError):
            download_all([("ID1", "a.jpg")], tmp_path / "raw")


def test_download_all_propagates_timeout_error(tmp_path):
    def _raise(*a, **kw):
        raise requests.exceptions.Timeout("timeout")

    with patch("gdown.download", side_effect=_raise):
        with pytest.raises(DownloadTimeoutError):
            download_all([("ID1", "a.jpg")], tmp_path / "raw")


def test_download_all_cancels_pending_futures_on_error(tmp_path):
    """When one download fails, pending (not-yet-started) futures are cancelled,
    so the total number of gdown calls is capped near the thread-pool size."""
    from src.downloader import THREADS

    started = []

    def _fail_first(url: str, path: str, quiet: bool) -> None:
        started.append(url)
        if "ID00" in url:
            raise requests.exceptions.Timeout("timeout")
        _fake_gdown(url, path, quiet)

    n_tasks = 30  # well above THREADS so many tasks would be pending
    pairs = [(f"ID{i:02d}", f"card{i}.jpg") for i in range(n_tasks)]

    with patch("gdown.download", side_effect=_fail_first):
        with pytest.raises(DownloadTimeoutError):
            download_all(pairs, tmp_path / "raw")

    # Without cancel, all 30 would eventually run; with cancel, at most
    # THREADS more can complete after the failing one was submitted.
    assert len(started) <= THREADS + 2
