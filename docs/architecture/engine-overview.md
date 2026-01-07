# Engine Overview

## Runtime services

- Orchestrator: session scheduling, feed/pipeline start-stop, EOD/reporting.
- Feed: websocket/provider rotation, pushes trades to a queue/stream.
- Pipeline: trade→candle aggregation, writes to storage, emits to indicators/charts.
- Indicators/strategy: consume candles/events to produce signals.
- Reporting: Discord notifications, charts, EOD summary.

## Responsibilities (runtime roles)

- Feed (`data_acquisition`): owns provider rotation, session auth, raw websocket connection, and pushes raw messages onto a queue. This is “getting data,” not transforming it.
- Pipeline (`pipeline/`): consumes the queue and turns ticks into candles, then fans out to storage/indicators/charts. It shouldn’t know about websockets or providers.
- Orchestrator (`main.py`): wires the two together, handles session timing, reporting, and shutdown.

## Restartability matrix

- Orchestrator: restart outside market hours; during hours only if feed/pipeline can be resumed.
- Feed: restartable anytime; should reconnect without dropping pipeline state.
- Pipeline: restartable during market hours; resumes candle state from current partial candle.
- Indicators/strategy: restartable; state reconstructed from storage if possible.
- Reporting: restartable; downstream only.

## Event flow (short)

Trade tick → Feed queue → Pipeline builds candles → Storage append + indicator update + chart refresh → Strategy consumes events/signals → Orders/reporting.

## Next steps

- Define interfaces for pipeline inputs/outputs.
- Document start/stop sequencing and health signals (see runbook).
- Add diagrams once interfaces are finalized.
