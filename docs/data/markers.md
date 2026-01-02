# Markers — Schema & Usage

**Path:** `storage/markers/<TF>.json` (e.g., `storage/markers/2M.json`, `5M.json`, `15M.json`). Files are created/appended by `data_acquisition.add_markers()` and used by chart exports/frontend overlays.

## Schema (list of marker objects)

- `event_type` (str): e.g., `buy`, `trim`, `sell`, `sim_trim_lwst`, `sim_trim_avg`, `sim_trim_win`.
- `x` (int/float): candle index on the timeframe.
- `y` (float): price coordinate for the marker.
- `style` (object):
  - `marker` (str): plot symbol (e.g., `^`, `o`, `v`).
  - `color` (str): color name (e.g., `blue`, `red`, `orange`, `yellow`, `green`).
- `percentage` (float | null): optional percentage annotation.

## Example

```json
[
  {"event_type": "buy", "x": 123, "y": 431.25, "style": {"marker": "^", "color": "blue"}, "percentage": 0.0},
  {"event_type": "trim", "x": 140, "y": 435.10, "style": {"marker": "o", "color": "red"}, "percentage": 25.0}
]
```

## Notes

- Timeframe in the filename is upper-case (`2M/5M/15M`).
- Files are append-only; `add_markers()` will create the JSON file if missing.
- Downstream: chart PNG exports and the frontend can overlay markers from these files.
