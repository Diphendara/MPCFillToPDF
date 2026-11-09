"""Tests for src/downloader.py — single-image and batch download logic."""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def _fake_requests_get(url: str, **kwargs) -> MagicMock:
    """Simulate a successful requests.get that returns a tiny JPEG."""
    mock = MagicMock()
    mock.status_code = 200
    mock.raise_for_status.return_value = None
    mock.iter_content.side_effect = lambda chunk_size=None: iter(
        [b"\xff\xd8\xff\xe0" + b"\x00" * 8]
    )
    return mock


def _fake_403(url: str, **kwargs) -> None:
    resp = MagicMock()
    resp.status_code = 403
    raise requests.HTTPError(response=resp)


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


def test_download_cache_hit_skips_request(tmp_path):
    dest = tmp_path / "raw"
    dest.mkdir()
    cached = dest / "DRIVEID.jpg"
    cached.write_bytes(b"cached content")

    with patch("requests.Session.get") as mock_get:
        result = download_image("DRIVEID", dest, "card.jpg")
        mock_get.assert_not_called()

    assert result == cached


def test_download_creates_file(tmp_path):
    with patch("requests.Session.get", side_effect=_fake_requests_get):
        result = download_image("ID001", tmp_path / "raw", "card.jpg")
    assert result.exists()
    assert result.stat().st_size > 0


def test_download_output_named_by_drive_id(tmp_path):
    with patch("requests.Session.get", side_effect=_fake_requests_get):
        result = download_image("MYID", tmp_path / "raw", "something.jpg")
    assert result.name.startswith("MYID")


def test_download_permission_error(tmp_path):
    with patch("requests.Session.get", side_effect=_fake_403):
        with pytest.raises(DownloadPermissionError) as exc_info:
            download_image("ID001", tmp_path / "raw", "card.jpg")
    assert exc_info.value.drive_id == "ID001"
    assert exc_info.value.card_name == "card.jpg"


def test_download_timeout_error(tmp_path):
    def _raise(*args, **kwargs):
        raise requests.exceptions.Timeout("timed out")

    with patch("requests.Session.get", side_effect=_raise):
        with pytest.raises(DownloadTimeoutError) as exc_info:
            download_image("ID001", tmp_path / "raw", "card.jpg")
    assert exc_info.value.drive_id == "ID001"


def test_download_rate_limit_exhausted(tmp_path):
    with patch(
        "requests.Session.get", side_effect=requests.ConnectionError("429 Too Many Requests")
    ):
        with patch("time.sleep"):
            with pytest.raises(DownloadRateLimitError):
                download_image("ID001", tmp_path / "raw", "card.jpg")


def test_download_rate_limit_retries_then_succeeds(tmp_path):
    attempts = {"n": 0}

    def _flaky(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise requests.ConnectionError("503 Service Unavailable")
        return _fake_requests_get(url, **kwargs)

    with patch("requests.Session.get", side_effect=_flaky):
        with patch("time.sleep"):
            result = download_image("ID001", tmp_path / "raw", "card.jpg")
    assert result.exists()
    assert attempts["n"] == 3


# ─── download_all ────────────────────────────────────────────────────────────


def test_download_all_returns_all_results(tmp_path):
    with patch("requests.Session.get", side_effect=_fake_requests_get):
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

    with patch("requests.Session.get", side_effect=_fake_requests_get):
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

    with patch("requests.Session.get", side_effect=_fake_requests_get):
        download_all(
            [("ID1", "a.jpg"), ("ID2", "b.jpg")],
            tmp_path / "raw",
            on_image_done=done_ids.append,
        )

    assert set(done_ids) == {"ID1", "ID2"}


def test_download_all_cancel_event_raises_cancelled(tmp_path):
    event = threading.Event()
    event.set()

    with patch("requests.Session.get", side_effect=_fake_requests_get):
        with pytest.raises(Cancelled):
            download_all(
                [("ID1", "a.jpg")],
                tmp_path / "raw",
                cancel_event=event,
            )


def test_download_all_propagates_permission_error_as_partial(tmp_path):
    with patch("requests.Session.get", side_effect=_fake_403):
        with pytest.raises(DownloadPartialError) as exc_info:
            download_all([("ID1", "a.jpg")], tmp_path / "raw")

    err = exc_info.value
    assert len(err.permission_errors) == 1
    assert err.permission_errors[0] == ("ID1", "a.jpg")
    assert err.timeout_errors == []


def test_download_all_propagates_timeout_error_as_partial(tmp_path):
    def _raise(*args, **kwargs):
        raise requests.exceptions.Timeout("timeout")

    with patch("requests.Session.get", side_effect=_raise):
        with patch("time.sleep"):
            with pytest.raises(DownloadPartialError) as exc_info:
                download_all([("ID1", "a.jpg")], tmp_path / "raw")

    err = exc_info.value
    assert len(err.timeout_errors) == 1
    assert err.timeout_errors[0] == ("ID1", "a.jpg")
    assert err.permission_errors == []


def test_download_all_continues_after_partial_failure(tmp_path):
    """Successful downloads complete even when some images fail."""

    def _mixed(url: str, **kwargs) -> MagicMock:
        if "BAD" in url:
            resp = MagicMock()
            resp.status_code = 403
            raise requests.HTTPError(response=resp)
        return _fake_requests_get(url, **kwargs)

    with patch("requests.Session.get", side_effect=_mixed):
        with pytest.raises(DownloadPartialError) as exc_info:
            download_all(
                [("GOOD1", "good1.jpg"), ("BAD", "bad.jpg"), ("GOOD2", "good2.jpg")],
                tmp_path / "raw",
            )

    err = exc_info.value
    assert len(err.permission_errors) == 1
    assert err.permission_errors[0][0] == "BAD"
    assert (tmp_path / "raw" / "GOOD1.jpg").exists()
    assert (tmp_path / "raw" / "GOOD2.jpg").exists()


def test_download_all_timeout_retry_succeeds(tmp_path):
    """Timed-out images that succeed on retry are NOT included in partial errors."""
    attempts: dict[str, int] = {}

    def _flaky(url: str, **kwargs) -> MagicMock:
        drive_id = url.split("/d/")[1].removesuffix("=d")
        attempts[drive_id] = attempts.get(drive_id, 0) + 1
        if attempts[drive_id] == 1:
            raise requests.exceptions.Timeout("timeout first time")
        return _fake_requests_get(url, **kwargs)

    with patch("requests.Session.get", side_effect=_flaky):
        with patch("time.sleep"):
            results = download_all([("ID1", "a.jpg")], tmp_path / "raw")

    assert "ID1" in results
    assert attempts["ID1"] == 2


# ─── download_image: remaining retry branches ────────────────────────────────


def test_download_connection_error_retries_then_succeeds(tmp_path):
    """Plain ConnectionErrors (not rate limits) are retried with backoff."""
    attempts = {"n": 0}

    def _flaky(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise requests.ConnectionError("connection reset")
        return _fake_requests_get(url, **kwargs)

    with patch("requests.Session.get", side_effect=_flaky):
        with patch("time.sleep"):
            result = download_image("ID001", tmp_path / "raw", "card.jpg")
    assert result.exists()
    assert attempts["n"] == 2


def test_download_connection_error_exhausted_raises_timeout(tmp_path):
    """After exhausting retries, ConnectionError becomes DownloadTimeoutError."""
    with patch("requests.Session.get", side_effect=requests.ConnectionError("conn refused")):
        with patch("time.sleep"):
            with pytest.raises(DownloadTimeoutError):
                download_image("ID001", tmp_path / "raw", "card.jpg")


def test_download_http_error_generic_raises(tmp_path):
    """Non-403/404, non-rate-limit HTTP errors propagate untouched."""

    def _raise_500(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 500
        raise requests.HTTPError("500", response=resp)

    with patch("requests.Session.get", side_effect=_raise_500):
        with patch("time.sleep"):
            with pytest.raises(requests.HTTPError):
                download_image("ID001", tmp_path / "raw", "card.jpg")


def test_download_request_exception_rate_limited_retries(tmp_path):
    """Rate-limit-looking RequestExceptions hit the generic retry branch too."""
    attempts = {"n": 0}

    def _flaky(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise requests.exceptions.ChunkedEncodingError("quota exceeded")
        return _fake_requests_get(url, **kwargs)

    with patch("requests.Session.get", side_effect=_flaky):
        with patch("time.sleep"):
            result = download_image("ID001", tmp_path / "raw", "card.jpg")
    assert result.exists()
    assert attempts["n"] == 2


# ─── download_all: speed callback, retry failure, cancel during retry ────────


def test_download_all_speed_callback_fires(tmp_path):
    """on_speed_update fires once enough bytes and time have accumulated."""
    speeds = []

    def _slow_get(url, **kwargs):
        time.sleep(0.15)  # exceed the 0.1s elapsed threshold
        return _fake_requests_get(url, **kwargs)

    with patch("requests.Session.get", side_effect=_slow_get):
        download_all(
            [("ID1", "a.jpg"), ("ID2", "b.jpg")],
            tmp_path / "raw",
            on_speed_update=lambda mbps, eta: speeds.append((mbps, eta)),
        )

    assert speeds, "speed callback should have fired at least once"


def test_download_all_stat_oserror_is_ignored(tmp_path):
    """A file vanishing between completion and stat must not break the batch."""

    def _fake_get_then_vanish(url, **kwargs):
        mock = _fake_requests_get(url, **kwargs)
        return mock

    real_replace = Path.replace

    def _replace_and_delete(self, target):
        real_replace(self, target)
        target.unlink(missing_ok=True)
        return target

    with patch("requests.Session.get", side_effect=_fake_get_then_vanish):
        with patch.object(Path, "replace", _replace_and_delete):
            results = download_all([("ID1", "a.jpg")], tmp_path / "raw")

    assert "ID1" in results


def test_download_all_timeout_retry_fails_again_raises_partial(tmp_path):
    """An image that times out twice ends up in the partial error's timeout list."""
    with patch("requests.Session.get", side_effect=requests.exceptions.Timeout("always slow")):
        with patch("time.sleep"):
            with pytest.raises(DownloadPartialError) as exc_info:
                download_all([("ID1", "a.jpg")], tmp_path / "raw")

    assert ("ID1", "a.jpg") in exc_info.value.timeout_errors


def test_download_all_cancel_during_retry_breaks(tmp_path):
    """Setting the cancel event before the retry loop stops further retries."""
    cancel = threading.Event()

    def _timeout_once(url, **kwargs):
        cancel.set()  # cancel while the first (and only) attempt is in flight
        raise requests.exceptions.Timeout("timeout")

    with patch("requests.Session.get", side_effect=_timeout_once):
        with patch("time.sleep"):
            with pytest.raises(Cancelled):
                download_all([("ID1", "a.jpg")], tmp_path / "raw", cancel_event=cancel)
