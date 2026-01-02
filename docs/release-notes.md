# Release Notes

---

## Parquet Live WebDash & DuckDB Viewport

- **Goal**: Move candles/objects to append-only Parquet with compacted dayfiles, and drive the Dash UI from DuckDB/viewport instead of CSV/JSON paths.
- **Status**: Completed
- **Description**: Candles now carry `ts` (int64 ms) + `ts_iso`; 15m dayfiles stamp `global_x`. `storage/viewport.load_viewport` reads parts/dayfiles with DuckDB (`union_by_name`, hive partitioning) and filters objects from the 15m snapshot by price band. The web dashboard was overhauled: Dash tabs render live from Parquet, WS server broadcasts `chart:<TF>` signals, and `chart_updater.py` exports PNGs (with optional notify) without coupling to the UI.

---

## Version 3 Flag System

- **Goal**: Make the flag system ONLY dependent on other candlestick OCHL.
- **Status**: Completed
- **Description**: It uses multiple state files and even has a setting to store the state's in memory (as dictionary) for faster processing speed's.

---

## Market Open/Close API Integration

- **Goal**: Improve logic for handling market holidays and irregular schedules dynamically.
- **Status**: Completed
- **Description**: We use a API that's part of our polygon subcription and we put the code into `data_aquisition.py` and the function is called `is_market_open()`.

---

## Shared State Integration

- **Goal**: Implement a shared state module (`shared_state.py`) for centralized global variable management.
- **Status**: Completed
- **Description**: Created a `shared_state.py` to store `latest_price` and `price_lock` globally. Might add more stuff to it later on.

---

## Enhance Config Management

- **Goal**: Ensure dynamic retrieval of config values during runtime.
- **Status**: Completed
- **Description**: Implemented `read_config()` function. Replaced hardcoded calls with dynamic ones (e.g., `read_config("SYMBOL")`).

---

## WebSocket Error Handling & Switching

- **Goal**: Improve reliability and error handling in WebSocket connections.
- **Status**: Completed
- **Description**: Fixed `ws_connect_v2` for Tradier and Polygon, debugged switching logic. Current WS provider: Tradier. Polygon remains a placeholder/backup; it’s not active today because our plan doesn’t include real-time WS. The connection loop supports multiple providers, but the configured list currently only includes Tradier. *Backup provider: placeholder for future real-time source (Polygon or another) when available.*

---

## Refactor `get_current_price()`

- **Goal**: Handle cases where price data is missing in WebSocket messages.
- **Status**: Completed
- **Description**: Added checks for missing fields and handled invalid messages gracefully. Improved logging for troubleshooting.

---

## Version Control Hygiene

- **Goal**: Exclude sensitive files and unnecessary directories (e.g., `venv`) from version control.
- **Status**: Completed
- **Description**: Removed `venv` from the repo and updated `.gitignore`. Reviewed for sensitive files.
