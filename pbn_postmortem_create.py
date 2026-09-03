"""Headless PBN/LIN load and augmentation (library create layer).

Streamlit and the FastAPI server both call this. MCP never imports it;
MortyBridgeBot reaches generate only through POST /pbn/generate.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import fsspec
import polars as pl
from endplay.parsers import lin, pbn
from endplay.types import Board

import pbn_postmortem_service as service

_APP_DIR = pathlib.Path(__file__).resolve().parent
_LIN_BODY_MARKERS = ('pn|', 'md|', 'qx|', 'vg|', 'mb|', 'sv|', 'ah|')
_FETCH_SCHEMES = ('http', 'https', 'file', 's3', 'gs', 'ftp')
DEFAULT_SD_SAMPLES = 10
RECOMMENDED_BOARD_MAX = 100


def _ensure_mlbridge_on_path() -> None:
    for path in (_APP_DIR, _APP_DIR.parent, _APP_DIR.parent.parent):
        if (path / 'mlBridge').is_dir():
            text = str(path)
            if text not in sys.path:
                sys.path.append(text)
            return
    raise FileNotFoundError(
        f"mlBridge not found next to {_APP_DIR}, {_APP_DIR.parent}, or {_APP_DIR.parent.parent}"
    )


def _first_query_value(query: str, *names: str) -> Optional[str]:
    if not query:
        return None
    qs = parse_qs(query, keep_blank_values=True)
    for name in names:
        values = qs.get(name)
        if values and str(values[0]).strip():
            return values[0]
    return None


def looks_like_lin_body(text: str) -> bool:
    if not text or '|' not in text:
        return False
    lowered = text.lstrip().lower()
    return any(marker in lowered for marker in _LIN_BODY_MARKERS)


def lin_payload_from_url(url: str) -> Optional[str]:
    """Return the LIN document embedded in ?lin= , or None."""
    value = _first_query_value(urlparse(url).query, 'lin')
    if value and looks_like_lin_body(value):
        return value
    return None


def lin_fetch_url_from_url(url: str) -> Optional[str]:
    """Return a LIN file URL from ?linurl= or from ?lin= pointing at a file."""
    parsed = urlparse(url)
    linurl = _first_query_value(parsed.query, 'linurl')
    if linurl:
        return linurl.strip()
    value = _first_query_value(parsed.query, 'lin')
    if not value or looks_like_lin_body(value):
        return None
    stripped = value.strip()
    if stripped.lower().endswith('.lin') or stripped.startswith(('http://', 'https://', 'file://')):
        return stripped
    return None


def input_suffix(url: str) -> str:
    """File suffix of a local path or of the URL path (ignores query string)."""
    parsed = urlparse(url)
    if parsed.scheme in _FETCH_SCHEMES:
        return pathlib.Path(parsed.path).suffix.lower()
    return pathlib.Path(url).suffix.lower()


def display_path_for_source(url: str, suffix: str) -> pathlib.Path:
    """Filesystem-safe stem used as the boards-dict key / cache display name."""
    if not suffix.startswith('.'):
        suffix = '.' + suffix
    parsed = urlparse(url)
    if parsed.scheme in ('http', 'https'):
        stem = pathlib.Path(parsed.path).stem or 'source'
        return pathlib.Path(stem + suffix)
    path = pathlib.Path(url)
    if path.suffix.lower() != suffix:
        return path.with_suffix(suffix)
    return path


def _read_text(url: str) -> str:
    of = fsspec.open(url, mode='r', encoding='utf-8')
    with of as handle:
        return handle.read()


def _parse_boards(file_data: str, kind: str, source: str) -> List[Board]:
    try:
        boards = lin.loads(file_data) if kind == 'lin' else pbn.loads(file_data)
    except Exception as exc:
        raise ValueError(f"Error parsing {kind.upper()} data from {source}: {exc}") from exc
    if not boards:
        raise ValueError(f"{source} has no boards.")
    return boards


def load_boards_from_source(url: str) -> Tuple[List[Board], pathlib.Path, str]:
    """Load endplay boards from a PBN/LIN file or a BBO Hand Viewer URL."""
    url = (url or '').strip()
    if not url:
        raise ValueError("A PBN, LIN, or BBO Hand Viewer URL is required.")

    lin_text = lin_payload_from_url(url)
    if lin_text:
        path_url = display_path_for_source(url, '.lin')
        return _parse_boards(lin_text, 'lin', url), path_url, 'lin'

    lin_remote = lin_fetch_url_from_url(url)
    if lin_remote:
        path_url = display_path_for_source(lin_remote, '.lin')
        try:
            file_data = _read_text(lin_remote)
        except Exception as exc:
            raise ValueError(f"Error opening or reading {lin_remote}: {exc}") from exc
        return _parse_boards(file_data, 'lin', lin_remote), path_url, 'lin'

    suffix = input_suffix(url)
    if suffix not in ('.pbn', '.lin'):
        if suffix in ('.html', '.htm', '') and ('lin=' in url.lower() or 'linurl=' in url.lower()):
            raise ValueError(
                "Could not find LIN data in the URL. For BBO Hand Viewer use "
                "?lin=<lin body> or ?linurl=<lin file url>."
            )
        raise ValueError(
            f"Unsupported file type: {suffix or pathlib.Path(url).suffix}. "
            "Use a .pbn/.lin file or a BBO Hand Viewer URL with ?lin= or ?linurl=."
        )
    kind = suffix.lstrip('.')
    try:
        file_data = _read_text(url)
    except Exception as exc:
        raise ValueError(f"Error opening or reading {url}: {exc}") from exc
    path_url = display_path_for_source(url, suffix)
    return _parse_boards(file_data, kind, url), path_url, kind


def boards_to_mlbridge_df(boards: List[Board], path_url: pathlib.Path) -> pl.DataFrame:
    _ensure_mlbridge_on_path()
    from mlBridge import mlBridgeEndplayLib

    df = mlBridgeEndplayLib.endplay_boards_to_df({path_url: boards})
    return mlBridgeEndplayLib.convert_endplay_df_to_mlBridge_df(df)


def apply_default_board_flags(df: pl.DataFrame) -> pl.DataFrame:
    """PBN/LIN sources rarely have player ids; bake all-true personalization flags."""
    df = df.with_columns(
        pl.lit(True).alias('Boards_I_Played'),
        pl.lit(True).alias('Boards_I_Declared'),
        pl.lit(True).alias('Boards_Partner_Declared'),
    )
    df = df.with_columns(
        pl.col('Boards_I_Played').alias('Boards_We_Played'),
        pl.col('Boards_I_Played').alias('Our_Boards'),
        (pl.col('Boards_I_Declared') | pl.col('Boards_Partner_Declared')).alias('Boards_We_Declared'),
    )
    contract = pl.col('Contract') if 'Contract' in df.columns else pl.lit('PASS')
    return df.with_columns(
        (
            pl.col('Boards_I_Played')
            & ~pl.col('Boards_We_Declared')
            & contract.ne('PASS')
        ).alias('Boards_Opponent_Declared'),
    )


def augment_boards_df(
    df: pl.DataFrame,
    sd_samples: int = DEFAULT_SD_SAMPLES,
    progress: Optional[Any] = None,
    lock_func: Optional[Callable[..., pl.DataFrame]] = None,
) -> pl.DataFrame:
    _ensure_mlbridge_on_path()
    from mlBridge.mlBridgeAugmentLib import AllAugmentations

    sd_samples = max(1, min(int(sd_samples), 1000))
    augmenter = AllAugmentations(
        df,
        None,
        sd_productions=sd_samples,
        progress=progress,
        lock_func=lock_func,
    )
    df, _hrs = augmenter.perform_all_augmentations()
    return df


def generate_postmortem(
    url: str,
    *,
    sd_samples: int = DEFAULT_SD_SAMPLES,
    force: bool = False,
    progress: Optional[Any] = None,
    lock_func: Optional[Callable[..., pl.DataFrame]] = None,
) -> Tuple[pl.DataFrame, Dict[str, Any]]:
    """Load, augment, and cache one PBN/LIN/Hand Viewer source. Returns (df, meta)."""
    url = (url or '').strip()
    if not url:
        raise ValueError("A PBN, LIN, or BBO Hand Viewer URL is required.")
    sd_samples = max(1, min(int(sd_samples), 1000))
    key = service.url_to_cache_key(url)
    if not force:
        try:
            df, meta = service.load_postmortem(key)
            meta = {**meta, 'cached': True, 'sd_samples': sd_samples}
            return df, meta
        except FileNotFoundError:
            pass

    boards, path_url, kind = load_boards_from_source(url)
    warning = None
    if len(boards) > RECOMMENDED_BOARD_MAX:
        warning = (
            f"{url} has {len(boards)} boards. More than {RECOMMENDED_BOARD_MAX} "
            "boards may result in instability."
        )
    df = boards_to_mlbridge_df(boards, path_url)
    df = augment_boards_df(df, sd_samples=sd_samples, progress=progress, lock_func=lock_func)
    df = apply_default_board_flags(df)
    service.save_augmented_df_to_cache(df, url)
    _df, meta = service.load_postmortem(key)
    meta = {
        **meta,
        'cached': False,
        'kind': kind,
        'sd_samples': sd_samples,
        'board_count': df.height,
    }
    if warning:
        meta['warning'] = warning
    return df, meta
