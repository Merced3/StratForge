# Release Guardrails (Easy-to-Change)

- No new globals; prefer injected dependencies.
- Every long-lived component has start/stop APIs.
- Log: feed connect/disconnect, pipeline start/stop, last candle per TF.
- Tests: trade→candle happy path, partial candle flush at close, restart/resume path.
- Backpressure: monitor queue depth; drop/slow if thresholds breached (future).
- Rollback: ability to stop feed/pipeline without affecting orchestrator schedule.
