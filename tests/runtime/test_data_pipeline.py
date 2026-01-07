# tests/runtime/test_data_pipeline.py
# target the package functions.

# tests/runtime/test_data_pipeline.py
import asyncio, json
import pytest
import pytz
from datetime import datetime, timedelta
from types import SimpleNamespace
from pipeline.config import PipelineConfig, PipelineDeps, PipelineSinks
import pipeline.data_pipeline as dp

class Recorder:
    def __init__(self): self.calls = []
    def __call__(self, *args, **kwargs): self.calls.append((args, kwargs))

@pytest.mark.anyio
async def test_pipeline_closes_candle(monkeypatch):
    tz = pytz.timezone("America/New_York")
    base = tz.localize(datetime(2024, 1, 2, 9, 30, 0))

    # Fake time progression
    times = iter([
        base,                      # init
        base,                      # first loop (process trade, flush at t=0)
        base + timedelta(seconds=2),  # triggers market_close exit before next queue get
    ])
    now_fn = lambda: next(times)

    # Fake schedule: close at 09:30:02
    monkeypatch.setattr(dp, "generate_candlestick_times", lambda *a, **k: [base, base + timedelta(seconds=2)])

    config = PipelineConfig(timeframes=["1M"], durations={"1M": 2}, buffer_secs=0, symbol="SPY", tz=tz)
    deps = PipelineDeps(
        get_session_bounds=lambda _: (base, base + timedelta(seconds=2)),
        latest_price_lock=asyncio.Lock(),
        shared_state=SimpleNamespace(latest_price=None),
    )
    append_rec = Recorder()
    update_rec = Recorder()
    refresh_rec = Recorder()
    sinks = PipelineSinks(
        append_candle=append_rec,
        update_ema=lambda c, tf: asyncio.sleep(0),
        refresh_chart=lambda tf, chart_type="live": None,
        on_error=lambda e, mod, fn: asyncio.sleep(0),
    )

    q = asyncio.Queue()
    await q.put(json.dumps({"type": "trade", "price": 100.0}))

    await dp.run_pipeline(q, config, deps, sinks, now_fn=now_fn)

    assert append_rec.calls, "append_candle should be called"
    args, _ = append_rec.calls[0]
    assert args[0] == "SPY" and args[1] == "1M"
    candle = args[2]
    assert candle["open"] == candle["high"] == candle["low"] == candle["close"] == 100.0

