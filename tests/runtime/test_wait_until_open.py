# tests\runtime\test_wait_until_open.py
import time

import pytest
import main
from utils.timezone import NY_TZ

pytestmark = pytest.mark.anyio("asyncio")


async def test_wait_until_market_open_future():
    target = main.datetime.now(NY_TZ) + main.timedelta(seconds=0.3)
    start = time.monotonic()
    await main.wait_until_market_open(target, NY_TZ)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15  # allow small jitter


async def test_wait_until_market_open_past():
    target = main.datetime.now(NY_TZ) - main.timedelta(seconds=1)
    start = time.monotonic()
    await main.wait_until_market_open(target, NY_TZ)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05  # should return immediately
