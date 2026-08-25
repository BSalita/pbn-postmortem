"""First-party REST API for cached Calculate-PBN postmortems."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

import pbn_postmortem_service as service


app = FastAPI(title="Calculate-PBN Postmortem API", version="1.0.0")


class SqlRequest(BaseModel):
    sql: str
    key: Optional[str] = None
    limit: int = 500


def _run(callable_, /, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    info = _run(service.dataset_info)
    return {"status": "ok", "service": "pbn-postmortem-api", **info}


@app.get("/pbn/dataset-info")
def dataset_info() -> dict:
    return _run(service.dataset_info)


@app.get("/pbn/games")
def games(limit: int = Query(100, ge=1, le=500)) -> dict:
    rows = _run(service.list_cached_postmortems)[:limit]
    return {"games": rows, "count": len(rows)}


@app.get("/pbn/boards")
def boards(
    key: Optional[str] = Query(None),
    columns: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
) -> dict:
    frame, meta = _run(service.load_postmortem, key)
    selected = [column.strip() for column in columns.split(",")] if columns else None
    return _run(service.board_results, frame, meta, columns=selected, limit=limit)


@app.post("/pbn/sql")
def sql(request: SqlRequest) -> dict:
    frame, meta = _run(service.load_postmortem, request.key)
    result = _run(service.run_sql, frame, request.sql, limit=request.limit)
    result["meta"] = meta
    return result


@app.get("/pbn/schema")
def schema(
    key: Optional[str] = Query(None),
    pattern: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=5000),
) -> dict:
    frame, _meta = _run(service.load_postmortem, key)
    return _run(service.schema_columns, frame, pattern=pattern, limit=limit)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PBN_POSTMORTEM_API_PORT", "8520"))
    print(
        f"[pbn-postmortem-api] start {datetime.now(timezone.utc).isoformat()} port={port}",
        flush=True,
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
