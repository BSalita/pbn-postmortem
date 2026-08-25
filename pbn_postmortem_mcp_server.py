"""MCP server exposing Calculate-PBN augmented deal data.

Transport: streamable HTTP (endpoint /mcp) on PBN_POSTMORTEM_MCP_PORT
(default 8513), stateless with JSON responses so plain HTTP clients and
cloudflared work without session affinity. Same pattern as
Bridge_Game_Postmortem_Chatbot/acbl_postmortem_mcp_server.py.

Every tool calls the first-party Calculate-PBN REST API. This MCP process
does not import report libraries, read parquet, or download third-party data.

Deployment: calculate-pbn-mcp container, started by
../7nt/postmortem_start.ps1. GET /health is used by the wslc watchdog and
deploy health checks.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

import requests

PBN_POSTMORTEM_MCP_PORT = int(os.environ.get("PBN_POSTMORTEM_MCP_PORT", "8513"))
PBN_POSTMORTEM_API_BASE_URL = os.environ.get(
    "PBN_POSTMORTEM_API_BASE_URL", "http://127.0.0.1:8520"
).rstrip("/")
_TIMEOUT_S = 300

mcp = MCPServer("pbn-postmortem")


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.get(
        f"{PBN_POSTMORTEM_API_BASE_URL}{path}",
        params={key: value for key, value in (params or {}).items() if value is not None},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json()


def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(
        f"{PBN_POSTMORTEM_API_BASE_URL}{path}",
        json=payload,
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json()


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness probe for the wslc watchdog / deploy health check."""
    return JSONResponse({"service": "calculate-pbn-mcp", "api": _get("/health")})


@mcp.tool()
def pbn_postmortem_dataset_info() -> Dict[str, Any]:
    """Summary of the Calculate-PBN cache: how many augmented PBN dataframes
    are cached, their keys, and how new ones get generated."""
    return _get("/pbn/dataset-info")


@mcp.tool()
def pbn_postmortem_games(limit: int = 100) -> Dict[str, Any]:
    """List cached Calculate-PBN games (newest first). Each entry has the
    cache key, the source PBN URL, and cache timestamps. A game must appear
    here before the boards/sql/schema tools can query it."""
    return _get("/pbn/games", {"limit": max(1, min(limit, 500))})


@mcp.tool()
def pbn_postmortem_boards(
    key: Optional[str] = None,
    columns: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Per-board results for one cached Calculate-PBN game: contract,
    declarer, result, tricks, scores, matchpoint percentages, and the deal
    (PBN).

    key: cache key or source PBN URL from pbn_postmortem_games; omit for the
    most recently cached game.
    columns: optional comma-separated column names to override the default
    summary set (discover names with pbn_postmortem_schema).
    """
    return _get(
        "/pbn/boards",
        {"key": key, "columns": columns, "limit": limit},
    )


@mcp.tool()
def pbn_postmortem_sql(
    sql: str,
    key: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """Run a DuckDB SQL query against one cached Calculate-PBN game,
    registered as table 'self' (one row per board result, thousands of
    augmented columns: double-dummy, par, single-dummy expected values, HCP,
    ...).

    'FROM self' is prepended when the query does not reference it, so both
    'SELECT ... FROM self ...' and DuckDB's 'SELECT ...' shorthand work.
    Unlike the ACBL/ffbridge postmortem MCPs there is no player
    personalization: PBN files rarely carry player ids, so helper columns
    like Boards_I_Played exist but are all true unless the source had ids.
    key: cache key or source PBN URL; omit for the most recently cached game.
    """
    return _post("/pbn/sql", {"key": key, "sql": sql, "limit": limit})


@mcp.tool()
def pbn_postmortem_schema(
    key: Optional[str] = None,
    pattern: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """Column names and dtypes of one cached Calculate-PBN dataframe. The
    frame has thousands of augmented columns, so pass a case-insensitive
    regex pattern (e.g. 'Pct|Score', '^DD_', 'Par') to search for relevant
    ones before writing pbn_postmortem_sql queries."""
    return _get(
        "/pbn/schema",
        {"key": key, "pattern": pattern, "limit": limit},
    )


if __name__ == "__main__":
    print(
        f"[calculate-pbn-mcp] start {datetime.now(timezone.utc).isoformat()} "
        f"on :{PBN_POSTMORTEM_MCP_PORT}; api -> {PBN_POSTMORTEM_API_BASE_URL}",
        flush=True,
    )
    # Stateless + JSON responses: plain request/response tools, no session
    # affinity needed behind cloudflared, and curl-testable.
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=PBN_POSTMORTEM_MCP_PORT,
        stateless_http=True,
        json_response=True,
    )
