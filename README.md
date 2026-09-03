# Calculate_PBN_Results

Bridge game statistics from a PBN or LIN file (including BBO Hand Viewer `?lin=` / `?linurl=` URLs). The same library path is used by Streamlit, the REST API, and MortyBridgeBot MCP.

## Architecture

```
Streamlit UI  (port 8503)     POST /pbn/generate or sidebar URL
        │
        ▼
Library
  pbn_postmortem_create.py    load PBN/LIN, augment, cache
  pbn_postmortem_service.py   list/load/SQL/schema over cache/
        │
        ▼
REST API  (port 8520)         pbn_postmortem_api_server.py
        │
        ▼
MortyBridgeBot MCP (port 8518)  HTTP client only — never imports this library
```

Augmented dataframes are stored as `cache/df-{key}.parquet` with a `df-{key}.json` sidecar for the source URL.

## Run

```powershell
pip install -U -r requirements.txt
streamlit run calculate_pbn_results_streamlit.py
python pbn_postmortem_api_server.py
```

API: `http://127.0.0.1:8520/health`. MCP tools live in MortyBridgeBot (`PBN_POSTMORTEM_API_BASE_URL`, default `http://127.0.0.1:8520`).

## Tests

```powershell
python -m unittest test_pbn_postmortem_service.py test_pbn_postmortem_create.py
```
