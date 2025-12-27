# Project Structure (reference)

```bash
Flag-Zone-Bo├─ .github/
│  └─ workflows/
│     └─ python-ci.yml
├─ docs/
│  ├─ adr/
│  │  ├─ 0001-separate-frontend-from-backend.md
│  │  └─ 0002-parquet-append-and-duckdb-reads.md
│  ├─ api/
│  │  ├─ storage-viewport.md
│  │  └─ ws_server.md
│  ├─ architecture/
│  │  ├─ frontend-overview.md
│  │  └─ overview.md
│  ├─ configuration/
│  │  └─ ticker-and-timeframes.md
│  ├─ data/
│  │  ├─ candles_schema.md
│  │  ├─ objects_schema.md
│  │  └─ storage-system.md
│  ├─ frontend/
│  │  └─ web_dash.md
│  ├─ overview/
│  │  └─ stratforge.md
│  ├─ runbooks/
│  │  ├─ dashboard-stack.md
│  │  ├─ end-of-day-compaction.md
│  │  └─ rebuild-ema-state.md
│  ├─ setup/
│  │  └─ project-structure.md
│  ├─ strategies/
│  │  └─ README.md
│  ├─ testing/
│  │  └─ storage_tests.md
│  ├─ roadmap.md
│  ├─ release-notes.md
│  └─ TOC.md
├─ indicators/                              # ----- Fill -----
├─ logs/                                    # ----- Fill -----
├─ storage/
│  ├─ data/
│  │  ├─ 2m/
│  │  │  ├─ 2025-10-22/
│  │  │  │  ├─ part-20251022_133001.290000-c24f98a7.parquet
│  │  │  │  ├─ ... more candle parts ...
│  │  │  └─ 2025-10-22.parquet              # compacted dayfile (ts, ts_iso; global_x on 15m)
│  │  ├─ 5m/
│  │  └─ 15m/
│  ├─ objects/
│  │  ├─ current/
│  │  │  └─ objects.parquet
│  │  └─ timeline/
│  │     └─ YYYY-MM/
│  │        └─ YYYY-MM-DD.parquet
│  ├─ images/
│  │  ├─ SPY_2M_chart.png
│  │  ├─ SPY_5M_chart.png
│  │  ├─ SPY_15M_chart.png
│  │  └─ SPY_15M-zone_chart.png
│  ├─ emas/
│  │  ├─ 2M.json
│  │  ├─ 5M.json
│  │  ├─ 15M.json
│  │  └─ ema_state.json
│  ├─ flags/
│  │  ├─ 2M.json
│  │  ├─ 5M.json
│  │  └─ 15M.json
│  ├─ markers/
│  │  ├─ 2M.json
│  │  ├─ 5M.json
│  │  └─ 15M.json
│  ├─ csv/
│  │  └─ order_log.csv
│  ├─ __init__.py
│  ├─ duck.py
│  ├─ message_ids.json
│  ├─ parquet_writer.py
│  ├─ viewport.py
│  ├─ week_ecom_calender.json
│  └─ week_performances.json
├─ strategies/
│  └─ trading_strategy.py
├─ test/
│  ├─ storage_unit_tests/
│  │  ├─ conftest.py
│  │  ├─ test_compaction.py
│  │  ├─ test_csv_to_parquet_days.py
│  │  ├─ test_objects_storage.py
│  │  ├─ test_parquet_writer.py
│  │  └─ test_viewport.py
│  └─ purpose.md
├─ tools/
│  ├─ __pycache__/
│  ├─ __init__.py
│  ├─ compact_parquet.py
│  ├─ csv_to_parquet_days.py
│  ├─ generate_structure.py
│  ├─ normalize_ts_all.py
│  └─ plot_candles.py
├─ utils/
│  ├─ __pycache__/
│  ├─ data_utils.py
│  ├─ ema_utils.py
│  ├─ file_utils.py
│  ├─ json_utils.py
│  ├─ log_utils.py
│  ├─ order_utils.py
│  └─ time_utils.py
├─ venv/                                    
├─ web_dash/
│  ├─ __init__.py
│  ├─ dash_app.py
│  ├─ chart_updater.py
│  ├─ ws_server.py
│  ├─ charts/
│  │  ├─ live_chart.py
│  │  ├─ zones_chart.py
│  │  └─ theme.py
│  ├─ assets/
│  │  ├─ style.css
│  │  ├─ object_styles.py
│  │  └─ object_styles.json
│  └─ about_this_dash_folder.txt
├─ .gitignore
├─ buy_option.py
├─ config.json
├─ cred.py # cred-example.py, replace vars - change file name too `cred.py`
├─ data_acquisition.py
├─ economic_calender_scraper.py
├─ error_handler.py
├─ main.py
├─ objects.py
├─ order_handler.py
├─ paths.py
├─ print_discord_messages.py
├─ README.md
├─ requirements.txt
├─ rule_manager.py
├─ sentiment_engine.py
├─ shared_state.py
└─ submit_order.py
```
