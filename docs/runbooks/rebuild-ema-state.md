# Runbook: Rebuild EMA State / EMA CSV

**Goal:** Restore EMA files/state when they are missing, corrupted, or out of sync with the live loop.

## What the EMA pipeline does

- State is stored in `storage/emas/ema_state.json` (per timeframe: `{"candle_list": [], "has_calculated": false}`) when `USE_JSON_STATE=True` in `indicators/ema_manager.py`.
- Per-timeframe EMA outputs are in `storage/emas/<TF>.json`.
- Seed history is written to `storage/csv/merged_ema_<TF>.csv` by `get_candle_data_and_merge()`, which pulls premarket plus prior days until it reaches the max EMA window from config.
- Before 09:45 ET: candles buffer into `candle_list`; temp EMAs are rebuilt from that buffer (does **not** flip `has_calculated`).
- At/after 09:45 ET: it rebuilds once from merged history + buffered candles, flips `has_calculated=True`, clears the buffer, then updates incrementally on each candle.

## When to run this

- EMA files are missing or obviously wrong in the UI/plots.
- EMA window settings changed and you need fresh seeds.
- Schema drift in `ema_state.json` (after code changes or manual edits).

## Steps

1) **Stop the live loop** (avoid concurrent writes).
2) **Reset state (recommended):**
   - Delete or clear `storage/emas/ema_state.json`, or call `hard_reset_ema_state(["2M","5M","15M"])`.
   - Delete stale `storage/emas/<TF>.json` and `storage/csv/merged_ema_<TF>.csv` if present.
3) **Rebuild merged history per TF** (writes `storage/csv/merged_ema_<TF>.csv` using Polygon aggs):

   ```bash
   python - <<'PY'
   from data_acquisition import get_candle_data_and_merge
   for tf in ["2M", "5M", "15M"]:
       interval = int(tf.replace("M", ""))
       get_candle_data_and_merge(interval, "minute", "AFTERMARKET", "PREMARKET", 1, tf)
   PY
   ```

4) **Restart the app**. Before 09:45 ET it will buffer and emit temp EMAs; at/after 09:45 ET it will finalize once and continue incrementally.

## Notes

- This uses Polygon aggregate data; on the current plan it is delayed intraday but complete after the first 15 minutes.
- If you only want to wipe today's buffer, set `has_calculated` to `false` and clear `candle_list` for that TF in `ema_state.json`.
- Keep `USE_JSON_STATE=True` unless you intentionally want ephemeral in-memory state.
