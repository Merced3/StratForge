# tests\runtime\test_wait_until_open.py
import time

import pytest
import pytz

import main

pytestmark = pytest.mark.anyio("asyncio")


async def test_wait_until_market_open_future():
    tz = pytz.timezone("America/New_York")
    target = main.datetime.now(tz) + main.timedelta(seconds=0.3)
    start = time.monotonic()
    await main.wait_until_market_open(target, tz)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15  # allow small jitter


async def test_wait_until_market_open_past():
    tz = pytz.timezone("America/New_York")
    target = main.datetime.now(tz) - main.timedelta(seconds=1)
    start = time.monotonic()
    await main.wait_until_market_open(target, tz)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05  # should return immediately
