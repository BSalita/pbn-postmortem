# postmortem-pbn

GitHub: https://github.com/BSalita/pbn-postmortem

Bridge game statistics from a PBN or LIN file (including BBO Hand Viewer `?lin=` / `?linurl=` URLs). Same architecture as the ACBL and ffbridge postmortems: Streamlit and MortyBridgeMCP are HTTP clients of the REST API. Only the API process imports the library.

## Architecture

```
Streamlit UI  (port 8503)          pbn_postmortem_api_client
MortyBridgeMCP (port 8518)         HTTP client only
        │
        ▼
REST API  (port 8520)              pbn_postmortem_api_server.py
        │
        ▼
Library
  pbn_postmortem_create.py         load PBN/LIN, augment, cache
  pbn_postmortem_service.py        list/load/SQL/schema/parquet over cache/
```

Augmented dataframes are stored as `cache/df-{key}.parquet` with a `df-{key}.json` sidecar for the source URL.

## Run

```powershell
pip install -U -r requirements.txt
python pbn_postmortem_api_server.py
streamlit run postmortem_pbn_streamlit.py
```

API health: `http://127.0.0.1:8520/health` (`service`: `postmortem-pbn-api`).

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Process health and cache summary |
| GET | `/pbn/dataset-info` | Cache directory and keys |
| GET | `/pbn/games` | Cached games, newest first |
| GET | `/pbn/boards` | Per-board summary (`key`, `columns`, `limit`) |
| POST | `/pbn/sql` | DuckDB SQL against table `self` |
| GET | `/pbn/schema` | Column names and dtypes |
| GET | `/pbn/parquet` | Full augmented dataframe |
| POST | `/pbn/generate` | Load a PBN/LIN/Hand Viewer URL, augment, cache |

MCP tools live in MortyBridgeMCP (`PBN_POSTMORTEM_API_BASE_URL`, default `http://127.0.0.1:8520`): `pbn_postmortem_dataset_info`, `pbn_postmortem_games`, `pbn_postmortem_boards`, `pbn_postmortem_sql`, `pbn_postmortem_schema`, `pbn_postmortem_generate`.

A chatbot given a BBO Hand Viewer URL should pass that full URL as `url` to `pbn_postmortem_boards` or `pbn_postmortem_sql`. The API generates and caches the postmortem if needed (POST body, never a GET query string — `?lin=` values are too long). Do not fetch the Hand Viewer HTML page.

## Tests

```powershell
python -m unittest test_pbn_postmortem_service.py test_pbn_postmortem_create.py test_pbn_postmortem_api.py test_pbn_streamlit_api_boundary.py
```
