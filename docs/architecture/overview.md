# Architecture Overview

> **Purpose:** A map-of-maps. Start here to jump to each subsystem.

## Frontend (Dash + WS)

- **Read this first:** `docs/architecture/frontend-overview.md`
- Live charts from Parquet; WebSocket `chart:<TF>` signals trigger re-render.

## Storage & Data

- Candles (parts → dayfile) and Objects (timeline → snapshot):  
  `docs/data/storage-system.md`
- API for fetching a window of candles + objects:  
  `docs/api/storage-viewport.md`

## Engine (future)

- Strategy loop, signals, state machines: *(coming soon)* `docs/architecture/engine-overview.md`
- Orders & tracking (brokers, fills, P&L): *(coming soon)* `docs/architecture/orders-and-tracking.md`

## Configuration

- Symbol & timeframes (what we build and display):  
  `docs/configuration/ticker-and-timeframes.md`

---

### Quick dataflow (one line)

Market stream → build candles → **write Parquet parts** → compaction (dayfile) → Dash loads from Parquet → WS `chart:<TF>` refresh.
