# tests\runtime\conftest.py
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import List, Dict, Any

import pytest
import pytz

# Ensure project root is on sys.path for CI runners that don't add it automatically
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Lightweight fake-cred stub so imports succeed in CI where secrets file is absent.
if "cred" not in sys.modules:
    fake_cred = ModuleType("cred")
    fake_cred.DISCORD_TOKEN = "test-token"
    fake_cred.DISCORD_CHANNEL_ID = 0
    fake_cred.DISCORD_CLIENT_SECRET = ""
    fake_cred.DISCORD_APPLICATION_ID = 0
    fake_cred.DISCORD_PUBLIC_KEY = ""
    fake_cred.TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN = ""
    fake_cred.TRADIER_BROKERAGE_BASE_URL = "https://api.tradier.com/v1/"
    fake_cred.TRADIER_BROKERAGE_STREAMING_URL = "https://stream.tradier.com/v1/"
    fake_cred.TRADIER_WEBSOCKET_URL = "wss://ws.tradier.com/v1/"
    fake_cred.TRADIER_BROKERAGE_ACCOUNT_NUMBER = ""
    fake_cred.TRADIER_SANDBOX_ACCOUNT_NUMBER = ""
    fake_cred.TRADIER_SANDBOX_ACCESS_TOKEN = ""
    fake_cred.TRADIER_SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1/"
    fake_cred.RM_TRADIER_ACCESS_TOKEN = ""
    fake_cred.PT_TRADIER_ACCOUNT_NUM = ""
    fake_cred.PT_TRADIER_ACCESS_TOKEN = ""
    fake_cred.TRADING_ECONOMICS_API_KEY = ""
    fake_cred.POLYGON_API_KEY = ""
    fake_cred.POLYGON_AUTHORIZATION = ""
    fake_cred.POLYGON_ACCESS_KEY_ID = ""
    fake_cred.POLYGON_SECRET_ACCESS_KEY = ""
    fake_cred.POLYGON_S3_ENPOINT = "https://files.polygon.io"
    fake_cred.POLYGON_BUCKET = "flatfiles"
    fake_cred.EODHD_API_TOKEN = ""
    sys.modules["cred"] = fake_cred

import main


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
    return pytz.timezone("America/New_York")


@pytest.fixture
def dummy_config(monkeypatch, ny_tz):
    """Patch main module globals/config to deterministic test values."""
    # Minimal config
    monkeypatch.setattr(main, "TIMEFRAMES", ["1M"], raising=False)
    monkeypatch.setattr(main, "CANDLE_BUFFER", 0, raising=False)
    monkeypatch.setattr(main, "SYMBOL", "TEST", raising=False)
    monkeypatch.setattr(main, "CANDLE_DURATION", {"1M": 1}, raising=False)  # 1-second candles for tests

    # Reset state each test
    main.reset_day_state(now=datetime.now(ny_tz))

    # Stub out external effects
    monkeypatch.setattr(main, "write_to_log", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(main, "append_candle", lambda *args, **kwargs: None, raising=False)

    async def _noop_async(*args, **kwargs):
        return None

    async def _return_1000(*args, **kwargs):
        return 1000.0

    monkeypatch.setattr(main, "update_ema", _noop_async, raising=False)
    monkeypatch.setattr(main, "refresh_chart", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(main, "get_account_balance", _return_1000, raising=False)
    monkeypatch.setattr(main, "setup_economic_news_message", lambda *args, **kwargs: "", raising=False)
    monkeypatch.setattr(main, "send_file_discord", _noop_async, raising=False)
    monkeypatch.setattr(main, "print_discord", _noop_async, raising=False)
    monkeypatch.setattr(main, "print_log", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(main, "ws_auto_connect", _noop_async, raising=False)
    monkeypatch.setattr(main, "process_end_of_day", _noop_async, raising=False)
    monkeypatch.setattr(main, "is_market_open", lambda *args, **kwargs: True, raising=False)
    monkeypatch.setattr(main, "ensure_economic_calendar_data", _noop_async, raising=False)

    # Stub read_config to known defaults
    def _fake_read_config(key: str):
        mapping = {
            "REAL_MONEY_ACTIVATED": False,
            "START_OF_DAY_BALANCE": 1000.0,
            "TIMEFRAMES": ["1M"],
            "CANDLE_BUFFER": 0,
            "SYMBOL": "TEST",
        }
        return mapping[key]

    monkeypatch.setattr(main, "read_config", _fake_read_config, raising=False)


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
