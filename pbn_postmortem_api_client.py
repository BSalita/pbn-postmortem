"""HTTP client for the Calculate-PBN postmortem API.

MCP (via MortyBridgeBot) and other callers use this instead of importing the
library. Configure with PBN_POSTMORTEM_API_BASE_URL (default http://127.0.0.1:8520).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

PBN_POSTMORTEM_API_BASE_URL = os.environ.get(
    "PBN_POSTMORTEM_API_BASE_URL", "http://127.0.0.1:8520"
).rstrip("/")
_TIMEOUT_S = 300


class PbnApiClientError(RuntimeError):
    def __init__(self, detail: str, status_code: Optional[int] = None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout_s: float = _TIMEOUT_S,
) -> Any:
    url = f"{PBN_POSTMORTEM_API_BASE_URL}{path}"
    try:
        resp = requests.request(
            method,
            url,
            params={k: v for k, v in (params or {}).items() if v is not None},
            json=json,
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        raise PbnApiClientError(
            f"PBN postmortem API unreachable at {PBN_POSTMORTEM_API_BASE_URL}: {exc}"
        ) from exc
    if not resp.ok:
        try:
            body = resp.json()
            detail = body.get("detail") or resp.text
        except ValueError:
            detail = resp.text
        raise PbnApiClientError(str(detail), status_code=resp.status_code)
    return resp.json()


def health() -> Dict[str, Any]:
    return _request("GET", "/health", timeout_s=2)


def dataset_info() -> Dict[str, Any]:
    return _request("GET", "/pbn/dataset-info")


def games(limit: int = 100) -> Dict[str, Any]:
    return _request("GET", "/pbn/games", {"limit": limit})


def boards(
    key: Optional[str] = None,
    columns: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    return _request(
        "GET",
        "/pbn/boards",
        {"key": key, "columns": columns, "limit": limit},
    )


def sql(sql: str, key: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
    return _request("POST", "/pbn/sql", json={"key": key, "sql": sql, "limit": limit})


def schema(
    key: Optional[str] = None,
    pattern: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    return _request(
        "GET",
        "/pbn/schema",
        {"key": key, "pattern": pattern, "limit": limit},
    )


def generate(
    url: str,
    sd_samples: int = 10,
    force: bool = False,
) -> Dict[str, Any]:
    return _request(
        "POST",
        "/pbn/generate",
        json={"url": url, "sd_samples": sd_samples, "force": force},
    )
