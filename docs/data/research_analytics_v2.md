# Research Analytics v2 Data (Signals, Paths, Metrics, Simulations)

This doc defines the data contracts for the research-only analytics pipeline.
These files are append-only JSONL and are **decoupled from live trading**.

---

## 1) Research signals (`storage/options/analytics/strategy_signals.jsonl`)

One row per **entry signal** (hypothetical trade).

Fields:

- ts: ISO 8601 UTC
- event: "signal"
- signal_id: unique id (sig-<strategy>-<tf>-<ts>-<contract_key>[-variant])
- strategy_tag: string (strategy name)
- timeframe: e.g. "2M"
- symbol: e.g. "SPY"
- option_type: "call" | "put"
- strike: float
- expiration: YYYY-MM-DD
- contract_key: "<symbol>-<call/put>-<strike>-<expiration>"
- underlying_price: float
- entry_mark: float (quote used for entry: ask/mid/last/bid fallback)
- bid: float | null
- ask: float | null
- last: float | null
- reason: string | null
- variant: string | null

Contract:

- Append-only; no edits.
- One signal_id = one "entry" in research.

---

## 2) Research path events (`storage/options/analytics/strategy_paths.jsonl`)

One row per **post-entry event** (candle close, EMA touch, level/zone touch).

Fields:

- ts: ISO 8601 UTC
- event: "candle_close" | "touch"
- event_key:
  - "candle_close"
  - "ema:<period>"
  - "level:<price>"
  - "zone:<low>-<high>"
- signal_id: links to strategy_signals.jsonl
- strategy_tag: string
- timeframe: string
- symbol: string
- option_type: "call" | "put"
- strike: float
- expiration: YYYY-MM-DD
- contract_key: string
- underlying_price: float
- mark: float (quote mark: ask/mid/last/bid fallback)
- bid: float | null
- ask: float | null
- last: float | null
- reason: string | null
- variant: string | null

Contract:

- Append-only; no edits.
- Deduped per signal + event_key + candle bucket.

---

## 3) Path metrics (`storage/options/analytics/path_metrics.jsonl`)

Derived metrics per signal (computed offline).

Fields:

- signal_id
- strategy_tag, timeframe, symbol, option_type, strike, expiration, contract_key
- entry_ts, entry_mark
- event_count
- last_ts
- mfe, mae (absolute, in premium points)
- mfe_pct, mae_pct
- mfe_ts, mae_ts
- mfe_event_key, mae_event_key
- mfe_underlying, mae_underlying
- seconds_to_mfe, seconds_to_mae

---

## 4) Rule simulations (`storage/options/analytics/rule_simulations.jsonl`)

Rule outcomes per signal per rule.

Fields:

- signal_id
- strategy_tag, timeframe, symbol, option_type, strike, expiration, contract_key
- entry_ts, entry_mark
- event_count
- rule_name, rule_type
- exit_reason
- exit_ts, exit_event_key, exit_event_type, exit_underlying, exit_mark
- pnl, pnl_pct
- seconds_in_trade

Contract:

- Output only; regenerable at any time from signals + paths.
