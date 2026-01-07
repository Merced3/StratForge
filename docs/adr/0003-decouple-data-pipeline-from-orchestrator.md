# ADR 0003: Decouple Data Pipeline From Orchestrator

## Status

Accepted
**Note**: Feed start/stop wrappers implemented via `start_feed/stop_feed` wrapping `ws_auto_connect`.

## Context

`main.py` currently owns session scheduling, websocket lifecycle, trade→candle aggregation, indicator updates, chart refreshes, and EOD reporting. This coupling makes changes risky and restarts hard during market hours.

## Decision

- Create a `data_pipeline` module that consumes a stream of trade ticks and emits candle events, writing to storage and updating indicators/charts via injected interfaces.
- Keep websocket/provider rotation inside `data_acquisition` behind `start_feed(symbol, queue)` / `stop_feed()`, eliminating direct `should_close` toggles.
- Keep `main.py` as orchestrator: session timing, lifecycle control, EOD/reporting; no candle mutation logic.
- Expose start/stop APIs for feed and pipeline so they can be restarted independently during market hours.

## Scope

Market-hours runtime only; does not change storage format or strategy logic yet.

## Consequences

- Pros: smaller failure domains; restartable feed/pipeline; clearer ownership; easier unit tests for trade→candle and lifecycle.
- Cons: requires async interfaces and explicit backpressure handling; modest refactor effort; more modules to wire.
- Follow-up: strategy/indicator workers to consume events instead of shared globals; add replay/backfill entry points that reuse the pipeline.

## Alternatives Considered

- Leave as-is: fastest now but keeps brittle coupling.
- Full event bus/pub-sub: powerful but overkill for current scope.

## References

- Roadmap “Decoupling the data pipeline”
- Runbook `docs/runbooks/data-pipeline.md`
