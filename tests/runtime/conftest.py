# tests\runtime\conftest.py
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from contextlib import suppress

import pytest

import main
from runtime import pipeline_config_loader
from utils.timezone import NY_TZ


class CountingQueue(asyncio.Queue):
    """Queue that counts task_done calls for assertions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.done_count = 0

    def task_done(self):
        self.done_count += 1
        return super().task_done()


@pytest.fixture
def ny_tz():
    return NY_TZ


@pytest.fixture
def dummy_config(monkeypatch, ny_tz):
    """Patch main module globals/config to deterministic test values."""
    # Minimal config
    monkeypatch.setattr(main, "CANDLE_BUFFER", 0, raising=False)
    monkeypatch.setattr(main, "CANDLE_DURATION", {"1M": 1}, raising=False)  # 1-second candles for tests

    # Stub out external effects
    monkeypatch.setattr(main, "initialize_csv_order_log", lambda *args, **kwargs: None, raising=False)

    async def _noop_async(*args, **kwargs):
        return None

    async def _return_1000(*args, **kwargs):
        return 1000.0

    monkeypatch.setattr(main, "update_ema", _noop_async, raising=False)
    monkeypatch.setattr(main, "refresh_chart", _noop_async, raising=False)
    monkeypatch.setattr(main, "get_account_balance", _return_1000, raising=False)
    monkeypatch.setattr(main, "setup_economic_news_message", lambda *args, **kwargs: "", raising=False)
    monkeypatch.setattr(main, "send_file_discord", _noop_async, raising=False)
    monkeypatch.setattr(main, "print_discord", _noop_async, raising=False)
    monkeypatch.setattr(main, "print_log", lambda *args, **kwargs: None, raising=False)
    async def _fake_start_feed(*args, **kwargs):
        return SimpleNamespace(task=asyncio.create_task(_noop_async()), stop_event=asyncio.Event())

    async def _fake_stop_feed(handle):
        handle.stop_event.set()
        handle.task.cancel()
        with suppress(asyncio.CancelledError):
            await handle.task

    monkeypatch.setattr(main, "start_feed", _fake_start_feed, raising=False)
    monkeypatch.setattr(main, "stop_feed", _fake_stop_feed, raising=False)
    monkeypatch.setattr(main, "process_end_of_day", _noop_async, raising=False)
    monkeypatch.setattr(main, "is_market_open", lambda *args, **kwargs: True, raising=False)
    monkeypatch.setattr(main, "ensure_economic_calendar_data", _noop_async, raising=False)

    # Stub read_config to known defaults
    def _fake_read_config(key: str):
        mapping = {
            "REAL_MONEY_ACTIVATED": False,
            "START_OF_DAY_BALANCE": 1000.0,
            "START_OF_DAY_DATE": "",
            "TIMEFRAMES": ["1M"],
            "CANDLE_BUFFER": 0,
            "SYMBOL": "TEST",
        }
        return mapping[key]

    monkeypatch.setattr(main, "read_config", _fake_read_config, raising=False)
    monkeypatch.setattr(pipeline_config_loader, "read_config", _fake_read_config, raising=False)

    # Ensure shared_state.latest_price is reset between tests
    import shared_state
    shared_state.latest_price = None


@pytest.fixture
async def counting_queue():
    return CountingQueue()


@pytest.fixture
def anyio_backend():
    """Force anyio-based tests to use asyncio backend (avoids trio when main relies on asyncio constructs)."""
    return "asyncio"

@pytest.fixture
def short_session(ny_tz):
    """Provide a short session window a few seconds long for fast tests."""
    start = datetime.now(ny_tz).replace(microsecond=0)
    end = start + timedelta(seconds=4)
    return start, end


def make_trade(price: float) -> str:
    """Helper to build a trade message payload as JSON string."""
    import json

    return json.dumps({"type": "trade", "price": price})
