# Frontend Architecture Overview

> **Purpose:** Fast re-onboard map — who talks to whom, what gets written where, and how charts update in real time.

```bash
             ┌────────────────────────────────────────────────────────┐
             │                        Backend                         │
             │                                                        │
Market Data  │  ws_auto_connect (Tradier/Polygon)  →  process_data    │
 (Trades) ───┼── streams → build candles → write Parquet parts (per timeframe) │
             │                ↑ latest_price in shared_state          │
             │                └→ update_ema → (optional) chart_updater PNG      │
             └────────────────────────────────────────────────────────┘
                                │               ▲
                                │ HTTP trigger  │ WebSocket push
                                ▼               │
             ┌────────────────────────────────────────────────────────┐
             │                        Services                        │
             │  FastAPI (ws_server):                                  │
             │   - POST /trigger-chart-update → broadcast "chart:TF"  │
             │   - WS /ws/chart-updates → clients subscribe           │
             └────────────────────────────────────────────────────────┘
                                │
                                ▼
             ┌────────────────────────────────────────────────────────┐
             │                         UI (Dash)                      │
             │  Tabs: Zones (15M history), Live 15M/5M/2M charts      │
             │  On WS message "chart:TF" → regenerates that figure    │
             └────────────────────────────────────────────────────────┘
```

## Module breakdown

* **Data acquisition**: websocket client, candle builder, EMA updates
* **Storage**: Parquet parts → daily/monthly compaction; DuckDB for reads
* **Objects**: event-sourced zones/levels/markers/flags (append-only timeline) + materialized **current snapshot** for fast reads
* **Services**: FastAPI WS broadcaster; Dash client subscriptions
* **Strategies**: run against shared state; produce signals/orders

### Data flow & storage locations

* Candles: `storage/data/<tf>/<YYYY-MM-DD>/part-*.parquet` → compacted `<YYYY-MM-DD>.parquet`
* Objects:
  * Snapshot (UI/viewport reads): `storage/objects/current/objects.parquet`
  * Timeline (append-only events): `storage/objects/timeline/YYYY-MM/YYYY-MM-DD.parquet`
* EMA / flags / markers: optional JSON/CSV exports under `storage/<name>/` (for sharing/debug), not required by the UI
