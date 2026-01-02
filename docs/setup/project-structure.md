# Project Structure (reference)

```bash
StratForg|--├── .git/
├── .github/
│   └── workflows/
│       └── python-ci.yml
├── .pytest_cache/
│   ├── v/
│   │   └── cache/
│   │       ├── lastfailed
│   │       └── nodeids
│   ├── .gitignore
│   ├── CACHEDIR.TAG
│   └── README.md
├── .vscode/
│   └── settings.json
├── __pycache__/
├── docs/
│   ├── adr/
│   │   ├── 0001-separate-frontend-from-backend.md
│   │   └── 0002-parquet-append-and-duckdb-reads.md
│   ├── api/
│   │   ├── storage-viewport.md
│   │   └── ws_server.md
│   ├── architecture/
│   │   ├── frontend-overview.md
│   │   └── overview.md
│   ├── configuration/
│   │   └── ticker-and-timeframes.md
│   ├── data/
│   │   ├── candles_schema.md
│   │   ├── objects_schema.md
│   │   └── storage-system.md
│   ├── frontend/
│   │   └── web_dash.md
│   ├── overview/
│   │   └── stratforge.md
│   ├── runbooks/
│   │   ├── dashboard-stack.md
│   │   ├── end-of-day-compaction.md
│   │   ├── frontend-reload.md
│   │   └── rebuild-ema-state.md
│   ├── setup/
│   │   └── project-structure.md
│   ├── strategies/
│   │   └── README.md
│   ├── testing/
│   │   └── storage_tests.md
│   ├── TOC.md
│   ├── release-notes.md
│   └── roadmap.md
├── indicators/
│   ├── __pycache__/
│   ├── ema_manager.py
│   └── flag_manager.py
├── logs/
│   └── terminal_output.log
├── states/
├── storage/
│   ├── __pycache__/
│   ├── csv/
│   │   ├── SPY_15_minute_candles.csv
│   │   └── order_log.csv
│   ├── data/
│   │   ├── 2m/     # Alot of data
│   │   ├── 5m/     # Alot of data
│   │   └── 15m/    # Alot of data
│   ├── emas/
│   │   ├── 2M.json
│   │   ├── 5M.json
│   │   ├── 15M.json
│   │   └── ema_state.json
│   ├── flags/
│   │   ├── 2M.json
│   │   ├── 5M.json
│   │   └── 15M.json
│   ├── images/
│   │   ├── SPY_2M_chart.png
│   │   ├── SPY_5M_chart.png
│   │   ├── SPY_15M-zone_chart.png
│   │   └── SPY_15M_chart.png
│   ├── markers/
│   │   ├── 2M.json
│   │   ├── 5M.json
│   │   └── 15M.json
│   ├── objects/
│   │   ├── __pycache__/
│   │   ├── current/
│   │   │   └── objects.parquet
│   │   ├── timeline/   # Alot Of Data
│   │   ├── __init__.py
│   │   └── io.py
│   ├── __init__.py
│   ├── duck.py
│   ├── message_ids.json
│   ├── parquet_writer.py
│   ├── viewport.py
│   ├── week_ecom_calendar.json
│   └── week_performances.json
├── strategies/
│   ├── __pycache__/
│   └── trading_strategy.py
├── tests/
│   ├── order_handling/
│   │   └── frontend_markers/
│   │       ├── __pycache__/
│   │       └── test_add_markers_creates_tf_file.py
│   ├── runtime/
│   │   ├── __pycache__/
│   │   ├── conftest.py
│   │   ├── test_main_loop.py
│   │   ├── test_process_data.py
│   │   ├── test_time_helpers.py
│   │   ├── test_wait_until_open.py
│   │   └── test_ws_auto_connect.py
│   ├── storage_unit_tests/
│   │   ├── __pycache__/
│   │   ├── conftest.py
│   │   ├── test_compaction.py
│   │   ├── test_csv_to_parquet_days.py
│   │   ├── test_objects_storage.py
│   │   ├── test_parquet_writer.py
│   │   └── test_viewport.py
│   └── purpose.md
├── tools/
│   ├── __pycache__/
│   ├── __init__.py
│   ├── audit_candles.py
│   ├── candles_io.py
│   ├── compact_parquet.py
│   ├── csv_to_parquet_days.py
│   ├── generate_structure.py
│   ├── normalize_ts_all.py
│   ├── plot_candles.py
│   └── repair_candles.py
├── utils/
│   ├── __pycache__/
│   ├── data_utils.py
│   ├── ema_utils.py
│   ├── file_utils.py
│   ├── json_utils.py
│   ├── log_utils.py
│   ├── order_utils.py
│   └── time_utils.py
├── venv/
├── web_dash/
│   ├── __pycache__/
│   ├── assets/
│   │   ├── __pycache__/
│   │   ├── object_styles.json
│   │   ├── object_styles.py
│   │   └── style.css
│   ├── charts/
│   │   ├── __pycache__/
│   │   ├── live_chart.py
│   │   ├── theme.py
│   │   └── zones_chart.py
│   ├── __init__.py
│   ├── chart_updater.py
│   ├── dash_app.py
│   └── ws_server.py
├── .gitignore
├── README.md
├── buy_option.py
├── config.json
├── cred-example.py
├── cred.py
├── data_acquisition.py
├── economic_calender_scraper.py
├── error_handler.py
├── main.py
├── objects.py
├── order_handler.py
├── paths.py
├── print_discord_messages.py
├── requirements.txt
├── rule_manager.py
├── shared_state.py
├── submit_order.py
└── todo.txt
```

If you want to generate something like this yourself, run:

```bash
python tools/generate_structure.py .
```
