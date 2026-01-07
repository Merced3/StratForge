# Web Dashboard Overview (`web_dash/`)

The `web_dash/` folder holds the **Plotly Dash UI** and the FastAPI WebSocket service. The Dash app renders four tabs (Zones history + live 15M/5M/2M) directly from Parquet via storage.viewport; no static images are required for the UI. The WS service only pushes lightweight `chart:<TF>` cues so the Dash client knows when to re-render.

## Quick start (ports & commands)

Start the WS server (port 8000):

```bash
uvicorn web_dash.ws_server:app --host 127.0.0.1 --port 8000
```

Start the Dash app (port 8050):

```bash
python -m web_dash.dash_app
# dash_app.py currently runs on port=8050
```

Optional: force-generate a PNG and broadcast:

```bash
python - <<'PY'
from web_dash.chart_updater import update_chart
update_chart("5M", chart_type="live", notify=True)
PY
```

## Dash Application (`dash_app.py`)

This is the Dash entry point. It reads `TIMEFRAMES/SYMBOL` from `config.json` (TIMEFRAMES are upper-case: 2M/5M/15M) and builds four tabs: "Zones", "15M", "5M", "2M". Each tab has its own `dash_extensions.WebSocket` *(url ws://127.0.0.1:8000/ws/chart-updates)* and a `dcc.Graph`. The graph is seeded immediately with `generate_zones_chart("15M")` for the zones tab or `generate_live_chart(tf)` for live tabs. A pattern-matching callback (refresh_any) re-runs the generator when either (a) the tab receives `chart:<TF>` from the `WS` or (b) the user clicks into that tab. Messages for other TFs are ignored via `dash.exceptions.PreventUpdate`.

## Chart Updater (`chart_updater.py`)

`chart_updater.py` is only for static PNG exports (Discord/sharing) and optional WS notifications. It builds a clean `go.Figure`, writes to `storage/images/SPY_<TF>_chart.png` (or `SPY_<TF>-zone_chart.png` when `chart_type="zones"`), and if `notify=True`, POSTs to `/trigger-chart-update`. It sets `xaxis.type` to date for live charts and category for zones to avoid Plotly rangebreak quirks. The Dash app itself does not depend on this module.

## Refresh Client (`refresh_client.py`)

`refresh_client.py` is the backend helper used by the trading engine to trigger a live refresh. It calls `POST /refresh-chart` asynchronously, which both broadcasts a chart update and regenerates the PNG snapshot. This keeps the engine decoupled from the WS server implementation while still updating charts when candles close.

## WebSocket Server (`ws_server.py`)

The FastAPI service broadcasts lightweight update cues:

* GET/WS `/ws/chart-updates`: on connect, it immediately sends `chart:2M`, `chart:5M`, `chart:15M`, and `chart:zones` so every tab renders once without waiting for backend traffic; then it keeps the socket alive.
* POST `/trigger-chart-update`: body {"timeframe": "5M"} or {"timeframes": ["2M","zones"]}; broadcasts `chart:<tf>` to all clients and returns the client count.
* POST `/refresh-chart`: broadcasts first (as above) and also spawns an async task to run `update_chart(timeframe, chart_type)` in the background to refresh the PNG on disk.
Run this separately on port `8000`; Dash runs on `8050`.

## live_chart.py — Live Candlestick Chart

Builds the intraday candlestick figure as a dcc.Graph:

* **Data**: calls `load_viewport(symbol, tf, t0_iso, t1_iso, include_days=False, include_parts=True)` so it reads Parquet parts only. `bars_limit` comes from `config["LIVE_BARS"][tf]` (default 600, if missing) and the window is anchored by `config["LIVE_ANCHOR"]` ("now" | "latest" | "date:YYYY-MM-DD"; falls back to latest part if "now" is empty).
* **Time handling**: uses `get_timeframe_bounds()` to locate the latest part; converts candle timestamps to ET and stores a naive `_ts_plot` for Plotly.
* **Visuals**: candlesticks with theme colors **(GREEN/RED)**, EMAs merged from `storage/emas/<TF>.json`, and `zones/levels` overlay via `draw_objects(..., variant="live")` restricted to the visible price band.
* **Objects**: `load_viewport(...)` pulls the `15m` snapshot filtered to the visible price band; `draw_objects(..., variant="live")` only overlays what overlaps the current y-range.
* **Layout**: fixed height 700, y-range padded ~5%, legend across the top, range slider off, uirevision per TF so the UI does not reset on each update.

## zones_chart.py — Zones/Levels Historical Chart

Builds the 15M historical zones figure as a dcc.Graph:

* **Window:** defaults to last 10 trading days via `days_window("15m", days)` `(EOD dayfiles only: include_days=True, include_parts=False)`.
* **Time handling:** normalizes candle timestamps to `ET`, drops tz for Plotly, and uses rangebreaks to remove weekends and 16:00-09:30 gaps.
* **Visuals:** candlesticks with day-stripe backgrounds, objects overlay via `draw_objects(..., variant="zones")` using `left/global_x` alignment and the current snapshot filtered by price overlap.
* **Layout:** 700px tall, same theme as live; title says `Historical (15M)` in code.

## Assets Folder (`assets/`)

`assets/style.css` is loaded automatically by Dash. It sets a light background `(#f7f8fa)`, uses the `Inter/system` font stack, and adds padding around `.dash-graph/#zones-graph` so the charts have breathing room. No custom JS is required.

## Real-Time Chart Update Flow

1. **Candle/object writes**: backend appends Parquet parts (and updates snapshots) when a bar closes.
2. **Optional export**: backend can call `await refresh_client.refresh_chart(tf, chart_type)` to refresh PNGs and broadcast updates, or use `update_chart(tf, chart_type, notify=True)` for offline export.
3. **Broadcast**: backend or exporter hits POST `/trigger-chart-update` (or `/refresh-chart`), which sends `chart:<tf>` (and the WS server already seeded all TFs on connect so every tab rendered once).
4. **Dash render**: the tab that matches `<tf>` regenerates its figure (live uses parts-only window anchored by config; zones uses `last-N-day` dayfiles) and the `dcc.Graph` updates in-browser without a page reload.
