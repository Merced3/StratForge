# Runbook – Rebuild EMA State / EMA CSV

**Goal** Rebuild EMA tails from historical candles when EMA files are missing/stale.

## Steps

1. Call `get_candle_data_and_merge()` for the timeframe you need.
2. This function fetches premarket + backfills full-day candles until it meets the max EMA window, computes EMAs, and writes the merged CSV to `storage/csv/merged_ema_<TF>.csv`.
3. UI reads `storage/emas/<TF>.json` for plotting; strategies compute EMAs during the live loop as candles finalize.

### Notes

- Useful after schema migrations or clearing corrupted EMA files.
- The point of the rebuild is because of my current polygon subcription plan as I cannot get ema data live because that is expensive so I have to build it using the $30/m plan which has the 15 minute delay to whenever it gives me the data. The data is complete and accurate after the first 15 minutes of market open.
