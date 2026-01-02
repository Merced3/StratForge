# Testing - Storage and Runtime

## Runtime tests (`tests/runtime/`)

- `test_main_loop.py`: main loop runs `process_data`, `ws_auto_connect`, and `process_end_of_day` when the session is open; skips work when already closed.
- `test_process_data.py`: consumes a live queue, flushes candles, writes logs, and triggers EMA updates without hanging.
- `test_time_helpers.py`: normalizes session times to New York tz and builds candle schedules with correct offsets.
- `test_wait_until_open.py`: waits for future opens and returns immediately if the target is in the past.
- `test_ws_auto_connect.py`: retries a single provider and rotates across multiple providers on failure (no real WS calls).

## Storage tests (`tests/storage_unit_tests/`)

- `test_parquet_writer.py`: appends candles with correct columns/types (`ts` int64 ms + `ts_iso`).
- `test_compaction.py`: parts -> compacted dayfile; row counts and min/max `ts/ts_iso` preserved; 15m `global_x` monotonic/contiguous.
- `test_objects_storage.py`: snapshot/timeline semantics, status filtering, and basic object IO.
- `test_viewport.py`: mixes parts + dayfiles with dedupe by `(symbol, timeframe, ts)`; price-band filtering; tolerates optional `global_x`.
- `test_csv_to_parquet_days.py`: historical CSV -> day Parquet conversion.

## Other tests

- `tests/order_handling/frontend_markers/test_add_markers_creates_tf_file.py`: marker writes create per-timeframe JSON files.
- See `tests/purpose.md` for broader coverage notes.
