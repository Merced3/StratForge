# Project Structure (reference)

```bash
StratForge/
├── .git/
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
│   │   ├── 0002-parquet-append-and-duckdb-reads.md
│   │   └── 0003-decouple-data-pipeline-from-orchestrator.md
│   ├── api/
│   │   ├── storage-viewport.md
│   │   └── ws_server.md
│   ├── architecture/
│   │   ├── engine-overview.md
│   │   ├── frontend-overview.md
│   │   ├── options-subsystem.md
│   │   ├── orders-and-tracking.md
│   │   └── overview.md
│   ├── configuration/
│   │   └── ticker-and-timeframes.md
│   ├── data/
│   │   ├── candles_schema.md
│   │   ├── emas.md
│   │   ├── markers.md
│   │   ├── objects_schema.md
│   │   ├── storage-system.md
│   │   └── week_performances.md
│   ├── frontend/
│   │   └── web_dash.md
│   ├── overview/
│   │   └── stratforge.md
│   ├── runbooks/
│   │   ├── dashboard-stack.md
│   │   ├── data-pipeline.md
│   │   ├── end-of-day-compaction.md
│   │   ├── frontend-reload.md
│   │   ├── rebuild-ema-state.md
│   │   └── release-guardrails.md
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
├── integrations/
│   ├── __pycache__/
│   ├── discord/
│   │   ├── __pycache__/
│   │   ├── README.md
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── templates.py
│   └── __init__.py
├── legacy/
│   └── options_v1/
│       ├── README.md
│       ├── buy_option.py
│       ├── order_handler.py
│       └── submit_order.py
├── logs/
│   └── terminal_output.log
├── options/
│   ├── __pycache__/
│   ├── __init__.py
│   ├── execution_paper.py
│   ├── execution_tradier.py
│   ├── mock_provider.py
│   ├── order_manager.py
│   ├── position_watcher.py
│   ├── quote_hub.py
│   ├── quote_service.py
│   ├── selection.py
│   └── trade_ledger.py
├── pipeline/
│   ├── __pycache__/
│   ├── __init__.py
│   ├── config.py
│   ├── data_pipeline.py
│   └── state.py
├── runtime/
│   ├── __pycache__/
│   ├── market_bus.py
│   ├── options_strategy_runner.py
│   ├── options_trade_notifier.py
│   └── pipeline_config_loader.py
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
│   ├── options/
│   │   ├── __pycache__/
│   │   ├── __init__.py
│   │   ├── ema_crossover.py
│   │   ├── exit_rules.py
│   │   └── types.py
│   └── __init__.py
├── tests/
│   ├── __pycache__/
│   ├── integrations/
│   │   ├── __pycache__/
│   │   └── test_discord_templates.py
│   ├── options_integration_tests/
│   │   ├── __pycache__/
│   │   ├── conftest.py
│   │   ├── test_order_flow.py
│   │   ├── test_position_watcher_flow.py
│   │   └── test_strategy_runner_flow.py
│   ├── options_unit_tests/
│   │   ├── __pycache__/
│   │   ├── conftest.py
│   │   ├── test_execution_paper.py
│   │   ├── test_execution_tradier.py
│   │   ├── test_exit_rules.py
│   │   ├── test_order_manager.py
│   │   ├── test_position_actions.py
│   │   ├── test_position_watcher.py
│   │   ├── test_quote_hub.py
│   │   ├── test_quote_service.py
│   │   ├── test_selection.py
│   │   └── test_trade_ledger.py
│   ├── order_handling/
│   │   └── frontend_markers/
│   │       ├── __pycache__/
│   │       └── test_add_markers_creates_tf_file.py
│   ├── runtime/
│   │   ├── __pycache__/
│   │   ├── conftest.py
│   │   ├── test_data_pipeline.py
│   │   ├── test_main_loop.py
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
│   ├── conftest.py
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
│   └── repair_candles.py
├── utils/
│   ├── __pycache__/
│   ├── data_utils.py
│   ├── ema_utils.py
│   ├── file_utils.py
│   ├── json_utils.py
│   ├── log_utils.py
│   ├── order_utils.py
│   ├── time_utils.py
│   └── timezone.py
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
│   ├── refresh_client.py
│   └── ws_server.py
├── .gitignore
├── README.md
├── config.json
├── cred-example.py
├── cred.py
├── data_acquisition.py
├── economic_calender_scraper.py
├── error_handler.py
├── main.py
├── objects.py
├── paths.py
├── requirements.txt
├── session.py
├── shared_state.py
└── todo.txt
```

If you want to generate something like this yourself, run:

```bash
python tools/generate_structure.py .
```
