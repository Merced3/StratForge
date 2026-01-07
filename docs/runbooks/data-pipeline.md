# Runbook: Data Pipeline

## Start sequence

1) Orchestrator builds queue/stream.
2) Start feed via `start_feed(symbol, queue)` (wraps `ws_auto_connect` + stop event); call `stop_feed(handle)` to stop.
3) Start pipeline: `run_pipeline(queue, sinks...)` (async task).
4) Verify health: feed connected, pipeline processing (logs), candles written.

## Stop sequence

1) Signal feed stop and await disconnect.
2) Stop pipeline task; flush any open candle; release locks.
3) Confirm no queue backlog; storage last write timestamp recent.

## Health signals

- Feed: connected provider, last tick timestamp, reconnect attempts.
- Pipeline: last candle write per timeframe, partial candle state.
- Backpressure: queue length/latency.
- Storage: last append success.

## Failure handling

- Feed drop: restart feed; pipeline keeps state; log provider rotation.
- Pipeline exception: stop feed, log error, restart pipeline with preserved partial candle if possible.
- Downstream write failure: backoff/retry writes; if persistent, pause feed and alert.

## Provider swap

- Toggle provider config, restart feed; pipeline stays up.

## Replay/backfill (future)

- Use same pipeline entry with a historical tick iterator to regenerate candles/indicators.
