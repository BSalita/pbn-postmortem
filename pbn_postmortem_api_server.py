"""First-party REST API for cached postmortem-pbn dataframes."""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

import pbn_postmortem_create as create
import pbn_postmortem_service as service


app = FastAPI(title="postmortem-pbn API", version="1.0.0")


class SqlRequest(BaseModel):
    sql: str
    key: Optional[str] = None
    url: Optional[str] = None
    limit: int = 500


class BoardsRequest(BaseModel):
    key: Optional[str] = None
    url: Optional[str] = None
    columns: Optional[str] = None
    limit: int = 100


class SchemaRequest(BaseModel):
    key: Optional[str] = None
    url: Optional[str] = None
    pattern: Optional[str] = None
    limit: int = 200


class GenerateRequest(BaseModel):
    url: str
    sd_samples: int = 10
    force: bool = False


def _run(callable_, /, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _frame(key: Optional[str] = None, url: Optional[str] = None):
    """Load a cached game, or generate when key/url is a PBN/LIN/BBO source."""
    source = create.source_url_from_key_or_url(key, url)
    if source:
        return create.generate_postmortem(source)
    return service.load_postmortem((key or url or None))


@app.get("/health")
def health() -> dict:
    info = _run(service.dataset_info)
    return {"status": "ok", "service": "postmortem-pbn-api", **info}


@app.get("/pbn/dataset-info")
def dataset_info() -> dict:
    return _run(service.dataset_info)


@app.get("/pbn/games")
def games(limit: int = Query(100, ge=1, le=500)) -> dict:
    rows = _run(service.list_cached_postmortems)[:limit]
    return {"games": rows, "count": len(rows)}


def _board_payload(key: Optional[str], url: Optional[str], columns: Optional[str], limit: int) -> dict:
    frame, meta = _run(_frame, key, url)
    selected = [column.strip() for column in columns.split(",")] if columns else None
    return _run(service.board_results, frame, meta, columns=selected, limit=limit)


@app.get("/pbn/boards")
def boards_get(
    key: Optional[str] = Query(None),
    columns: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
) -> dict:
    return _board_payload(key, None, columns, limit)


@app.post("/pbn/boards")
def boards_post(request: BoardsRequest) -> dict:
    return _board_payload(request.key, request.url, request.columns, request.limit)


@app.post("/pbn/sql")
def sql(request: SqlRequest) -> dict:
    frame, meta = _run(_frame, request.key, request.url)
    result = _run(service.run_sql, frame, request.sql, limit=request.limit)
    result["meta"] = meta
    return result


@app.get("/pbn/schema")
def schema_get(
    key: Optional[str] = Query(None),
    pattern: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=5000),
) -> dict:
    frame, _meta = _run(_frame, key, None)
    return _run(service.schema_columns, frame, pattern=pattern, limit=limit)


@app.post("/pbn/schema")
def schema_post(request: SchemaRequest) -> dict:
    frame, _meta = _run(_frame, request.key, request.url)
    return _run(service.schema_columns, frame, pattern=request.pattern, limit=request.limit)


@app.get("/pbn/parquet")
def parquet(key: Optional[str] = Query(None)) -> Response:
    frame, meta = _run(service.load_postmortem, key)
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    filename = meta.get("cache_file") or "postmortem-pbn.parquet"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.apache.parquet",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.post("/pbn/generate")
def generate(request: GenerateRequest) -> dict:
    try:
        _df, meta = create.generate_postmortem(
            request.url,
            sd_samples=request.sd_samples,
            force=request.force,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return meta


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PBN_POSTMORTEM_API_PORT", "8520"))
    print(
        f"[postmortem-pbn-api] start {datetime.now(timezone.utc).isoformat()} port={port}",
        flush=True,
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
