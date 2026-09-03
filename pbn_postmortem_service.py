"""Headless access to cached Calculate-PBN augmented dataframes.

The Streamlit app (calculate_pbn_results_streamlit.py) persists each fully
augmented board-results dataframe to cache/df-{key}.parquet right after
augmentation, where key is a sanitized stem + short hash of the source PBN
URL (see url_to_cache_key / save_augmented_df_to_cache in the app). A sidecar
df-{key}.json records the original URL. This module is the shared,
Streamlit-free core exposed through MortyBridgeBot: it enumerates those
parquets and runs DuckDB SQL against the dataframe registered as 'self',
mirroring how the app's SQL favorites work.

Unlike the ACBL/ffbridge postmortem services there is no player
personalization step: PBN files rarely carry player ids, so the app bakes
all-true Boards_I_Played/... flags into the saved dataframe.

Env:
  PBN_POSTMORTEM_CACHE_DIR  cache directory (default ./cache next to this file)
"""

import hashlib
import json
import os
import pathlib
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import polars as pl

_APP_DIR = pathlib.Path(__file__).resolve().parent
CACHE_DIR = pathlib.Path(os.environ.get("PBN_POSTMORTEM_CACHE_DIR", str(_APP_DIR / "cache")))

CON_REGISTER_NAME = "self"
DEFAULT_SQL_ROW_LIMIT = 500
MAX_SQL_ROW_LIMIT = 2000
MAX_SCHEMA_COLUMNS = 1000

_CACHE_FILE_RE = re.compile(r"^df-(?P<key>.+)\.parquet$")

# Default column set for the per-board summary tool; intersected with the
# actual dataframe columns since PBN sources vary in what they carry.
BOARD_SUMMARY_COLUMNS = [
    "Board", "Contract", "Declarer_Direction", "Declarer_Name",
    "Result", "Tricks", "Score_NS", "Score_EW", "Pct_NS", "Pct_EW",
    "MP_NS", "MP_EW", "Par_NS", "ParContract", "Room", "PBN",
]


def _sidecar_url(key: str) -> Optional[str]:
    sidecar = CACHE_DIR / f"df-{key}.json"
    if not sidecar.is_file():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8")).get("url")
    except (json.JSONDecodeError, OSError):
        return None


def list_cached_postmortems() -> List[Dict[str, Any]]:
    """Cached augmented PBN dataframes (newest file first)."""
    out: List[Dict[str, Any]] = []
    if not CACHE_DIR.is_dir():
        return out
    for f in CACHE_DIR.glob("df-*.parquet"):
        m = _CACHE_FILE_RE.match(f.name)
        if m is None:
            continue
        key = m.group("key")
        stat = f.stat()
        out.append(
            {
                "key": key,
                "url": _sidecar_url(key),
                "file": f.name,
                "size_bytes": stat.st_size,
                "cached_at": stat.st_mtime,
            }
        )
    out.sort(key=lambda d: d["cached_at"], reverse=True)
    return out


def dataset_info() -> Dict[str, Any]:
    cached = list_cached_postmortems()
    return {
        "cache_dir": str(CACHE_DIR),
        "cached_postmortems": len(cached),
        "keys": [c["key"] for c in cached],
        "note": (
            "Augmented dataframes are produced by POST /pbn/generate "
            "(PBN, LIN, or a BBO Hand Viewer ?lin= / ?linurl= URL) or by the "
            "Streamlit app (https://pbn.postmortem.chat/?url=...). This service "
            "reads the parquet cache."
        ),
    }


def url_to_cache_key(url: str) -> str:
    """Stable, filesystem-safe cache key: sanitized stem plus a short hash of
    the full URL so distinct URLs with the same filename do not collide."""
    stem = re.sub(r'[^A-Za-z0-9._]+', '_', pathlib.Path(url).stem).strip('_')[:60] or 'pbn'
    return f"{stem}-{hashlib.md5(url.encode('utf-8')).hexdigest()[:8]}"


def save_augmented_df_to_cache(df: Any, url: str) -> pathlib.Path:
    """Persist the augmented dataframe. A sidecar df-{key}.json records the
    source URL since it cannot be reconstructed from the sanitized filename."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = url_to_cache_key(url)
    cache_file = CACHE_DIR / f'df-{key}.parquet'
    df.write_parquet(cache_file)
    meta = {'url': url, 'cached_at': datetime.now(timezone.utc).isoformat()}
    (CACHE_DIR / f'df-{key}.json').write_text(json.dumps(meta), encoding='utf-8')
    with _df_cache_lock:
        _df_cache.clear()
    return cache_file


def _resolve_cache_file(key: Optional[str] = None) -> Tuple[pathlib.Path, Dict[str, Any]]:
    cached = list_cached_postmortems()
    if not cached:
        raise FileNotFoundError(
            "No cached PBN postmortem. Generate one first by loading "
            "https://pbn.postmortem.chat/?url=<PBN url>."
        )
    if key is None:
        entry = cached[0]  # newest cache file
    else:
        # Accept the cache key or the original source URL.
        entry = next((c for c in cached if c["key"] == key or c["url"] == key), None)
        if entry is None:
            raise FileNotFoundError(
                f"No cached PBN postmortem for key or URL {key!r}. "
                f"Cached keys: {[c['key'] for c in cached]}"
            )
    return CACHE_DIR / entry["file"], entry


# Small in-process cache keyed by (path, mtime); a few frames resident at most.
_df_cache: Dict[Tuple[str, float], pl.DataFrame] = {}
_df_cache_lock = threading.Lock()
_DF_CACHE_MAX = 4


def _read_parquet_cached(path: pathlib.Path) -> pl.DataFrame:
    key = (str(path), path.stat().st_mtime)
    with _df_cache_lock:
        if key in _df_cache:
            return _df_cache[key]
    df = pl.read_parquet(path)
    with _df_cache_lock:
        if len(_df_cache) >= _DF_CACHE_MAX:
            _df_cache.pop(next(iter(_df_cache)))
        _df_cache[key] = df
    return df


def load_postmortem(key: Optional[str] = None) -> Tuple[pl.DataFrame, Dict[str, Any]]:
    """Load a cached augmented PBN dataframe (latest when key is None).
    Returns (df, meta)."""
    path, entry = _resolve_cache_file(key)
    df = _read_parquet_cached(path)
    meta = {
        "key": entry["key"],
        "url": entry["url"],
        "cache_file": entry["file"],
        "board_count": df.height,
        "game_date": str(df["Date"].first()) if "Date" in df.columns else None,
    }
    return df, meta


def run_sql(df: pl.DataFrame, sql: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """Run DuckDB SQL against the dataframe registered as 'self'."""
    limit = max(1, min(limit or DEFAULT_SQL_ROW_LIMIT, MAX_SQL_ROW_LIMIT))
    sql = sql.strip().rstrip(";")
    # Same convenience as the app's ShowDataFrameTable: allow DuckDB's
    # FROM-first syntax by prepending the table when it is not referenced.
    if f"from {CON_REGISTER_NAME}" not in sql.lower():
        sql = f"FROM {CON_REGISTER_NAME} " + sql
    # external access off: only the registered dataframe is queryable.
    con = duckdb.connect(config={"enable_external_access": "false"})
    try:
        con.register(CON_REGISTER_NAME, df)
        result = con.execute(sql).pl()
    finally:
        con.close()
    truncated = result.height > limit
    result = result.head(limit)
    return {
        "sql": sql,
        "columns": result.columns,
        "rows": result.to_dicts(),
        "row_count": result.height,
        "truncated": truncated,
    }


def board_results(
    df: pl.DataFrame,
    meta: Dict[str, Any],
    columns: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Per-board rows of the cached augmented dataframe."""
    limit = max(1, min(limit or DEFAULT_SQL_ROW_LIMIT, MAX_SQL_ROW_LIMIT))
    wanted = columns or BOARD_SUMMARY_COLUMNS
    missing = [c for c in wanted if c not in df.columns]
    selected = [c for c in wanted if c in df.columns]
    if not selected:
        raise ValueError(f"None of the requested columns exist. Missing: {missing}")
    if "Board" in df.columns:
        df = df.sort("Board")
    df = df.select(selected).head(limit)
    return {
        "meta": meta,
        "columns": selected,
        "missing_columns": missing,
        "rows": df.to_dicts(),
        "row_count": df.height,
    }


def schema_columns(df: pl.DataFrame, pattern: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """Column names (with dtypes) of the augmented dataframe, optionally
    filtered by a case-insensitive regex. The frame has thousands of columns,
    hence the cap."""
    limit = max(1, min(limit or MAX_SCHEMA_COLUMNS, MAX_SCHEMA_COLUMNS))
    names = sorted(df.columns)
    if pattern:
        rx = re.compile(pattern, re.IGNORECASE)
        names = [c for c in names if rx.search(c)]
    truncated = len(names) > limit
    names = names[:limit]
    dtypes = dict(zip(df.columns, (str(t) for t in df.dtypes)))
    return {
        "total_columns": df.width,
        "matched_columns": len(names),
        "truncated": truncated,
        "columns": {c: dtypes[c] for c in names},
    }
