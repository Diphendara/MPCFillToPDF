"""Base HTTP policy for ordinary external deck adapters.

Drive and Scryfall intentionally own specialised transport policies: streamed
downloads/retries and rate limiting respectively. New ordinary deck sources
should use this module instead of calling ``requests`` directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

DEFAULT_TIMEOUT = 20


def request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: Any = DEFAULT_TIMEOUT,
    raise_for_status: bool = True,
    **kwargs: Any,
) -> requests.Response:
    """Send an external-adapter request with the project's common timeout policy."""
    method = method.upper()
    if method == "GET":
        response = requests.get(url, headers=dict(headers or {}), timeout=timeout, **kwargs)
    elif method == "POST":
        response = requests.post(url, headers=dict(headers or {}), timeout=timeout, **kwargs)
    else:
        response = requests.request(
            method, url, headers=dict(headers or {}), timeout=timeout, **kwargs
        )
    if raise_for_status:
        response.raise_for_status()
    return response


def get(url: str, **kwargs: Any) -> requests.Response:
    """GET through the shared external-adapter transport seam."""
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    """POST through the shared external-adapter transport seam."""
    return request("POST", url, **kwargs)
