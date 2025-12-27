# StratForge — Single‑Asset, Multi‑Strategy Trading Engine

**StratForge** is a single‑asset trading engine that can host **multiple strategies** simultaneously (e.g., Flag Zone, Momentum, Trend, Mean Reversion). While the default symbol in this repository is **SPY**, the engine is **ticker‑agnostic** so long as your data provider/websocket supports the symbol you configure.

* **Single‑asset by design**: one symbol at a time → simpler state, faster decisions.
* **Multi‑strategy host**: strategies run side‑by‑side on shared market state.
* **Self‑learning ready**: storage + contracts are built for later ML components.
* **Docs first**: storage contracts, runbooks, and ADRs live under `docs/`.

## Capabilities

* Live data acquisition and candle building (2m/5m/15m …)
* Event‑sourced **objects** (zones, levels, markers, flags) in Parquet
* Plotly Dash UI + FastAPI WS broadcasts
* Strategy registry and shared indicators (EMA, etc.)
* Append‑only Parquet writes with end‑of‑day compaction (DuckDB reads)

## See also

* Storage overview: `docs/data/storage-system.md`
* Architecture overview: `docs/architecture/overview.md`
* Configuring symbol/timeframes: `docs/configuration/ticker-and-timeframes.md`
* Strategies index: `docs/strategies/README.md`
