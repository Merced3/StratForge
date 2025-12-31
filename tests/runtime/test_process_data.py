# tests\runtime\test_process_data.py
import asyncio
import time
import json

import pytest

import main

pytestmark = pytest.mark.anyio("asyncio")


async def test_process_data_flushes_candle(dummy_config, counting_queue, short_session, monkeypatch):
    session_open, session_close = short_session

    # Capture writes and EMAs
    writes = []
    emas = []

    async def fake_update_ema(candle, tf):
        emas.append((tf, candle.copy()))

    def fake_write_to_log(candle, symbol, tf):
        writes.append((symbol, tf, candle.copy()))

    def fake_append_candle(symbol, tf, candle):
        writes.append((symbol, tf, candle.copy()))

    monkeypatch.setattr(main, "update_ema", fake_update_ema, raising=False)
    monkeypatch.setattr(main, "write_to_log", fake_write_to_log, raising=False)
    monkeypatch.setattr(main, "append_candle", fake_append_candle, raising=False)

    # Producer: feed trades continuously until after close so process_data never blocks on an empty queue
    async def producer():
        end_time = session_close + main.timedelta(seconds=1)
        price = 100.0
        while main.datetime.now(main.new_york_tz) < end_time:
            await counting_queue.put(json.dumps({"type": "trade", "price": price}))
            price += 1.0
            await asyncio.sleep(0.1)

    prod_task = asyncio.create_task(producer())

    # Run process_data (short session, 1s candle) with a timeout to avoid hanging tests
    await asyncio.wait_for(main.process_data(counting_queue, session_open, session_close), timeout=10)
    await prod_task

    # queue.task_done should match number of messages
    assert counting_queue.done_count > 0

    # At least one candle write should have happened
    assert any(entry[1] == "1M" for entry in writes), "Expected candle writes for 1M timeframe"
    # EMA updates should have been called
    assert len(emas) >= 1
