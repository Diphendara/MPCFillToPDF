"""Base HTTP policy for ordinary external deck adapters.

Drive and Scryfall intentionally own specialised transport policies: streamed
downloads/retries and rate limiting respectively. New ordinary deck sources
should use this module instead of calling ``requests`` directly.

Sessions are kept per-thread (``threading.local``) so TCP+TLS connections are
reused (keep-alive) while staying thread-safe: ``requests.Session`` is not
safe to share across threads.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping

import requests

DEFAULT_TIMEOUT = 20

_thread_local = threading.local()


def get_session() -> requests.Session:
    """Return a per-thread ``requests.Session`` (connection reuse, thread-safe)."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


def request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float | tuple[float, float] | tuple[float, None] = DEFAULT_TIMEOUT,
    raise_for_status: bool = True,
    **kwargs: object,
) -> requests.Response:
    """Send an external-adapter request with the project's common timeout policy."""
    response = get_session().request(
        method.upper(), url, headers=dict(headers or {}), timeout=timeout, **kwargs
    )
    if raise_for_status:
        response.raise_for_status()
    return response


def get(url: str, **kwargs: object) -> requests.Response:
    """GET through the shared external-adapter transport seam."""
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: object) -> requests.Response:
    """POST through the shared external-adapter transport seam."""
    return request("POST", url, **kwargs)
