# tests/runtime/test_main_loop.py
import asyncio
from datetime import datetime, timedelta

import pytest
import pytz

import main

pytestmark = pytest.mark.anyio("asyncio")


async def test_main_loop_runs_process_once(dummy_config, monkeypatch):
    now_ny = main.datetime.now(main.new_york_tz).replace(microsecond=0)
    session_open = now_ny - timedelta(seconds=1)  # already open
    session_close = session_open + timedelta(seconds=30)  # safely after now

    called = {"process_data": 0, "process_end_of_day": 0, "ws": 0}

    async def fake_process_data(queue, open_, close_):
        called["process_data"] += 1
        return

    async def fake_ws(queue, provider, symbol):
        called["ws"] += 1

    async def fake_eod():
        called["process_end_of_day"] += 1

    monkeypatch.setattr(main, "process_data", fake_process_data, raising=False)
    monkeypatch.setattr(main, "ws_auto_connect", fake_ws, raising=False)
    monkeypatch.setattr(main, "process_end_of_day", fake_eod, raising=False)
    monkeypatch.setattr(main, "wait_until_market_open", lambda *args, **kwargs: asyncio.sleep(0), raising=False)
    main.websocket_connection = None

    await main.main_loop(session_open, session_close)

    assert called["process_data"] == 1
    assert called["ws"] == 1
    assert called["process_end_of_day"] == 1


async def test_main_loop_skips_if_already_closed(dummy_config, monkeypatch):
    now_ny = main.datetime.now(main.new_york_tz).replace(microsecond=0)
    session_close = now_ny - timedelta(seconds=1)  # already closed
    session_open = session_close - timedelta(seconds=30)

    called = {"process_data": 0}

    async def fake_process_data(queue, open_, close_):
        called["process_data"] += 1

    monkeypatch.setattr(main, "process_data", fake_process_data, raising=False)
    main.websocket_connection = None

    await main.main_loop(session_open, session_close)
    assert called["process_data"] == 0
