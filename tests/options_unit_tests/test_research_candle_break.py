from datetime import datetime, timezone

from strategies_research.signals.candle_break import CandleEmaBreakSignal
from strategies_research.types import ResearchContext


def test_candle_break_signal_cross_up():
    signal = CandleEmaBreakSignal()
    context = ResearchContext(
        symbol="SPY",
        timeframe="2M",
        candle={"open": 99.0, "close": 101.0},
        ema_history=[{"13": 100.0}],
        timestamp=datetime.now(timezone.utc),
    )

    results = signal.on_candle_close(context)

    assert len(results) == 1
    assert results[0].direction == "call"
    assert results[0].variant == "13-up"


def test_candle_break_signal_cross_down():
    signal = CandleEmaBreakSignal()
    context = ResearchContext(
        symbol="SPY",
        timeframe="2M",
        candle={"open": 101.0, "close": 99.0},
        ema_history=[{"13": 100.0}],
        timestamp=datetime.now(timezone.utc),
    )

    results = signal.on_candle_close(context)

    assert len(results) == 1
    assert results[0].direction == "put"
    assert results[0].variant == "13-down"
