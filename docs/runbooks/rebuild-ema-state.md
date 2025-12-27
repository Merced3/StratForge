# Runbook – Rebuild EMA State / EMA CSV

**Goal** Rebuild EMA tails from historical candles when EMA files are missing/stale.

## Steps

1. Call `get_candle_data_and_merge()` for the timeframe you need.
2. This function fetches premarket + backfills full-day candles until it meets the max EMA window, computes EMAs, and writes the merged CSV to `storage/csv/merged_ema_<TF>.csv`.
3. UI reads `storage/emas/<TF>.json` for plotting; strategies compute EMAs during the live loop as candles finalize.

### Notes

- Useful after schema migrations or clearing corrupted EMA files.
