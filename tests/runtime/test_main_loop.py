# tests/runtime/test_main_loop.py
import asyncio
from datetime import datetime, timedelta

import pytest
import pytz
from types import SimpleNamespace
from contextlib import suppress

import main

pytestmark = pytest.mark.anyio("asyncio")


async def test_main_loop_runs_process_once(dummy_config, monkeypatch):
    now_ny = main.datetime.now(main.new_york_tz).replace(microsecond=0)
    session_open = now_ny - timedelta(seconds=1)  # already open
    session_close = session_open + timedelta(seconds=30)  # safely after now

    called = {"run_pipeline": 0, "process_end_of_day": 0, "ws": 0}

    async def fake_run_pipeline(*_args, **_kwargs):
        called["run_pipeline"] += 1

    async def fake_start_feed(symbol, queue):
        called["ws"] += 1
        # return a handle with a no-op task and event
        stop_event = asyncio.Event()
        task = asyncio.create_task(asyncio.sleep(0))
        return SimpleNamespace(task=task, stop_event=stop_event)

    async def fake_stop_feed(handle):
        handle.stop_event.set()
        handle.task.cancel()
        with suppress(asyncio.CancelledError):
            await handle.task

    async def fake_eod(*_args, **_kwargs):
        called["process_end_of_day"] += 1

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline, raising=False)
    monkeypatch.setattr(main, "start_feed", fake_start_feed, raising=False)
    monkeypatch.setattr(main, "stop_feed", fake_stop_feed, raising=False)
    monkeypatch.setattr(main, "process_end_of_day", fake_eod, raising=False)
    monkeypatch.setattr(main, "wait_until_market_open", lambda *args, **kwargs: asyncio.sleep(0), raising=False)
    await main.main_loop(session_open, session_close)

    assert called["run_pipeline"] == 1
    assert called["ws"] == 1
    assert called["process_end_of_day"] == 1


async def test_main_loop_skips_if_already_closed(dummy_config, monkeypatch):
    now_ny = main.datetime.now(main.new_york_tz).replace(microsecond=0)
    session_close = now_ny - timedelta(seconds=1)  # already closed
    session_open = session_close - timedelta(seconds=30)

    called = {"run_pipeline": 0}

    async def fake_run_pipeline(*_args, **_kwargs):
        called["run_pipeline"] += 1

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline, raising=False)
    await main.main_loop(session_open, session_close)
    assert called["run_pipeline"] == 0
