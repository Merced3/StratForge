# WebSocket Broadcast Service (`ws_server.py`)

**Purpose:** Tiny FastAPI service that pushes chart update signals to all connected Dash clients. It runs separately from the Dash app so the trading engine can notify the UI without coupling to it.

## How it fits

- Port `8000` (default) for this service; Dash runs on `8050`.
- Backend (or PNG exporter) calls an HTTP endpoint here when a bar closes or a chart is regenerated.
- All connected Dash tabs listen on the WS endpoint and re-render the matching chart when they receive `chart:<TF>`.

## Endpoints

### WebSocket: `GET /ws/chart-updates`

- On connect, immediately sends four seed messages so every tab renders once:  
  `chart:2M`, `chart:5M`, `chart:15M`, `chart:zones`.
- Then keeps the socket alive (heartbeat via sleep loop).
- Message format: plain text strings `chart:<TF>` where `<TF>` is one of `2M|5M|15M|zones`.

### HTTP: `POST /trigger-chart-update`

- Body (either shape):

  ```json
  { "timeframe": "5M" }
  ```

  or

  ```json
  { "timeframes": ["2M", "zones"] }
  ```

- Behavior: broadcasts `chart:<tf>` for each entry to all live WS clients.
- Response: `{"status": "broadcasted", "timeframes": [...], "clients": <count>}`.

### HTTP: `POST /refresh-chart`

- Body fields:
  - `timeframe` (e.g., `"5M"`)
  - `chart_type` (`"live"` or `"zones"`)
- Behavior:
  1) Broadcasts like `/trigger-chart-update` (so UI refreshes immediately).  
  2) Spawns a background task to run `update_chart(timeframe, chart_type)` to regenerate the PNG snapshot on disk.
- Response: `{"status": "saved-and-broadcast", "timeframes": [...], "clients": <count>}`.

## Typical flow

1) A candle closes (or objects snapshot changes).  
2) Backend calls `POST /trigger-chart-update` with the affected timeframe(s).  
3) WS server sends `chart:<TF>` to all connected dashboards.  
4) Dash callback for that TF reruns `generate_live_chart()` or `generate_zones_chart()` and updates the `dcc.Graph` in-browser.  
5) (Optional) If you also want fresh PNGs for Discord/export, call `POST /refresh-chart` or run `update_chart(..., notify=True)`; the UI still updates via the broadcast.

## Quickstart commands

Start the WS server (port 8000):

```bash
uvicorn web_dash.ws_server:app --host 127.0.0.1 --port 8000
```

Trigger a live chart refresh for 5M:

```bash
curl -X POST http://127.0.0.1:8000/trigger-chart-update \
  -H "Content-Type: application/json" \
  -d '{"timeframe":"5M"}'
```

Refresh PNG and broadcast (5M live):

```bash
curl -X POST http://127.0.0.1:8000/refresh-chart \
  -H "Content-Type: application/json" \
  -d '{"timeframe":"5M","chart_type":"live"}'
```

## Notes and tips

- Timeframe casing: use upper-case (`2M`, `5M`, `15M`, `zones`) to match config and Dash tabs.
- If Dash is not running, broadcasts are harmless no-ops; reconnecting later will still receive the seed messages.
- Run WS server and Dash separately so restarting the UI does not impact the trading loop.

---

## Data acquisition WS client (`ws_auto_connect` notes)

- Providers are defined in `data_acquisition.PROVIDERS` with `enabled` flags; currently only Tradier is enabled. Polygon is kept as a placeholder/backup for future real-time access.
- Tradier requires a session ID; `get_session_id()` is called before connecting and retries if missing.
- Connection settings: `ping_interval=20s`, `ping_timeout=30s`, retry interval = 1s on failure.
- On failure, the client rotates through the enabled provider list; with a single provider it simply retries that one.
- Market-open checks use Polygon’s `v1/marketstatus/now` API in `is_market_open()`; this is independent of live WS ingestion.
