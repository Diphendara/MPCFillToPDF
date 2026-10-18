"""Tests for src/http_client.py — HTTP transport policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.http_client import DEFAULT_TIMEOUT, get, post, request


class TestRequest:
    """Tests for request function."""

    def test_get_request_uses_default_timeout(self) -> None:
        """GET request uses default timeout."""
        with patch("src.http_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_get.return_value = mock_response
            request("GET", "https://example.com")
            mock_get.assert_called_once_with(
                "https://example.com", headers={}, timeout=DEFAULT_TIMEOUT
            )

    def test_post_request_uses_default_timeout(self) -> None:
        """POST request uses default timeout."""
        with patch("src.http_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_post.return_value = mock_response
            request("POST", "https://example.com")
            mock_post.assert_called_once_with(
                "https://example.com", headers={}, timeout=DEFAULT_TIMEOUT
            )

    def test_custom_headers_and_timeout(self) -> None:
        """Custom headers and timeout are passed through."""
        with patch("src.http_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_get.return_value = mock_response
            request(
                "GET",
                "https://example.com",
                headers={"Authorization": "Bearer token"},
                timeout=30,
            )
            mock_get.assert_called_once_with(
                "https://example.com",
                headers={"Authorization": "Bearer token"},
                timeout=30,
            )

    def test_raise_for_status_enabled_by_default(self) -> None:
        """raise_for_status is called by default."""
        with patch("src.http_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_get.return_value = mock_response
            request("GET", "https://example.com")
            mock_response.raise_for_status.assert_called_once()

    def test_raise_for_status_disabled(self) -> None:
        """raise_for_status can be disabled."""
        with patch("src.http_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_get.return_value = mock_response
            request("GET", "https://example.com", raise_for_status=False)
            mock_response.raise_for_status.assert_not_called()

    def test_method_case_insensitive(self) -> None:
        """Method is case-insensitive."""
        with patch("src.http_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_get.return_value = mock_response
            request("get", "https://example.com")
            mock_get.assert_called_once()


class TestGet:
    """Tests for get convenience function."""

    def test_get_calls_request_with_get(self) -> None:
        """get() calls request with GET method."""
        with patch("src.http_client.request") as mock_request:
            mock_response = MagicMock()
            mock_request.return_value = mock_response
            get("https://example.com")
            mock_request.assert_called_once_with("GET", "https://example.com")


class TestPost:
    """Tests for post convenience function."""

    def test_post_calls_request_with_post(self) -> None:
        """post() calls request with POST method."""
        with patch("src.http_client.request") as mock_request:
            mock_response = MagicMock()
            mock_request.return_value = mock_response
            post("https://example.com")
            mock_request.assert_called_once_with("POST", "https://example.com")
