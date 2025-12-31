# Tests Folder Purpose

This folder holds automated tests for the bot. The aim is to catch regressions early and cover both storage and runtime behavior, with room to grow into strategies, order handling, risk, and any future subsystems. We use **pytest** (with pytest-asyncio where appropriate).

## Scope and intent

- Current focus: storage integrity (Parquet/compaction) and runtime loop/helpers (sessions, scheduling, queues).
- Future focus: strategies, buys/sells, order/risk rules, metrics—add tests here as those features evolve.
- Philosophy: fast, isolated tests that stub external services where possible; integration where needed but kept short.

## Structure

- **storage_unit_tests/**
  - `conftest.py` — shared fixtures for storage tests (common paths, temp dirs, sample data).
  - `test_compaction.py` — daily/monthly compaction: merges part files, preserves row counts/min/max ts/ts_iso, and removes redundant parts; checks 15m `global_x` continuity.
  - `test_csv_to_parquet_days.py` — converts 15m CSVs to daily Parquet; enforces contiguous `global_x`, correct schema, and defaulted volumes.
  - `test_objects_storage.py` — objects-specific storage: monthly rollups, integrity of object snapshots/events, and price-band inclusion/exclusion.
  - `test_parquet_writer.py` — appending candles/objects into Parquet with correct columns/types (ts, ts_iso, OHLCV/object fields).
  - `test_viewport.py` — viewport/window loading: dedupes by (symbol, timeframe, ts), respects price/time filters, and handles optional `global_x`.

- **runtime/**
  - `conftest.py` — dummy config, stubs for external calls (WS, Discord, EMA), counting queue, shared async fixtures.
  - `test_time_helpers.py` — session normalization and candle schedule generation for NYSE bounds.
  - `test_wait_until_open.py` — waits until session open without busy looping; future vs past target handling.
  - `test_process_data.py` — short-session candle processing: trade ingestion, timestamped flushes, task_done accounting, EMA/log writes.
  - `test_main_loop.py` — main loop orchestration: single process_data invocation, WS startup stub, end-of-day flow; skips when already past close.

- `purpose.md` — this file. Explains why tests exist and what they cover.

## Why we test

- Prevent regressions across storage schemas, compaction, and runtime scheduling.
- Validate components in isolation from live data feeds; stub external services by default.
- Keep CI/CD trustworthy and reviews safer as new domains (strategies/orders/risk) are added.

## How to run

```bash
# Run all tests
python -m pytest

# Run a folder
python -m pytest tests/runtime
python -m pytest tests/storage_unit_tests

# Run a single file
python -m pytest tests/runtime/test_process_data.py -s

# PowerShell explicit path example
python -m pytest -q .\tests\runtime\test_process_data.py -s
```
