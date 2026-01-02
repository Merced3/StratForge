# EMAs — Data Contracts & Flow

## Paths

- Per-timeframe EMAs: `storage/emas/<TF>.json` (e.g., `storage/emas/2M.json`, `5M.json`, `15M.json`).
- EMA state: `storage/emas/ema_state.json`.
- Merged history seed: `storage/csv/merged_ema_<TF>.csv`.

## Schema

- `<TF>.json`: list of snapshots
  - `x` (int): candle index (plotting anchor).
  - `<window>` (float): one key per EMA window from config (e.g., `"13"`, `"48"`, `"200"`), value = latest EMA at that index.
- `ema_state.json`: per timeframe object  
  `{ "<TF>": { "candle_list": [candle dicts], "has_calculated": bool } }`  
  - `candle_list`: buffered candles (dicts with `timestamp/open/high/low/close`) used before 09:45 ET.  
  - `has_calculated`: flipped to true after the first 15 minutes when EMAs are finalized for the day.

## Write path

- `indicators/ema_manager.py:update_ema` controls the lifecycle:
  - **Before 09:45 ET:** buffer candles into `ema_state[tf]["candle_list"]`, rebuild temp EMAs from the buffer only (does not flip `has_calculated`).
  - **At/after 09:45 ET (first time):** rebuild merged history via `get_candle_data_and_merge(...)`, replay buffered candles, flip `has_calculated=True`, clear the buffer.
  - **Rest of session:** append per-candle snapshots to `<TF>.json` using `calculate_save_EMAs`.
- `utils/ema_utils.calculate_save_EMAs` also appends the candle to `storage/csv/merged_ema_<TF>.csv` before recomputing EMA columns and writing the latest snapshot.

## Read path

- `utils/ema_utils.get_last_emas` reads the last snapshot to return EMA values and `x`.
- `utils/ema_utils.read_ema_json` fetches an EMA snapshot by position.

## Notes

- Timeframe names in filenames are upper-case (`2M/5M/15M`).
- Rebuilds use Polygon aggregates via `get_candle_data_and_merge`; on the current plan these are delayed intraday but complete after ~15 minutes.
- `USE_JSON_STATE=True` (in `ema_manager`) persists `ema_state.json`; set to False only if you intentionally want ephemeral in-memory state.
