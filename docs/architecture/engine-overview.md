# Engine Overview

## Runtime services

- Orchestrator: session scheduling, feed/pipeline start-stop, EOD/reporting.
- Orchestrator: uses `web_dash.refresh_client` to trigger chart refreshes when needed.
- Feed: websocket/provider rotation, pushes trades to a queue/stream.
- Pipeline: trade-to-candle aggregation, writes to storage, emits to indicators.
- Market bus: in-process candle-close events for strategy consumers.
- Indicators/strategy: consume events to produce signals.
- Options runner: listens to the market bus and routes signals into options execution.
- Position watcher: streams mark prices for open options positions.
- Reporting: Discord notifications, chart markers, trade ledger, EOD summary.

## Responsibilities (runtime roles)

- Feed (`data_acquisition`): owns provider rotation, session auth, raw websocket connection, and pushes raw messages onto a queue. This is "getting data," not transforming it.
- Pipeline (`pipeline/`): consumes the queue and turns ticks into candles, then fans out to storage/indicators/charts. It shouldn't know about websockets or providers.
- Orchestrator (`main.py`): wires the two together, handles session timing, reporting, and shutdown.

## Restartability matrix

- Orchestrator: restart outside market hours; during hours only if feed/pipeline can be resumed.
- Feed: restartable anytime; should reconnect without dropping pipeline state.
- Pipeline: trade-to-candle aggregation, writes to storage, emits to indicators.
- Market bus: in-process candle-close events for strategy consumers.
- Indicators/strategy: consume events to produce signals.
- Options runner: listens to the market bus and routes signals into options execution.
- Reporting: restartable; downstream only (ledger is append-only, Discord is display-only).

## Event flow (short)

Trade tick -> Feed queue -> Pipeline builds candles -> Storage append + indicator update -> Market bus -> Strategies -> Orders -> Position watcher -> Trade ledger + Discord + chart refresh.

## Next steps

- Define interfaces for pipeline inputs/outputs.
- Document start/stop sequencing and health signals (see runbook).
- Add diagrams once interfaces are finalized.
