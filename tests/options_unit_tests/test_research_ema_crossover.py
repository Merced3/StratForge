from datetime import datetime, timezone

from strategies_research.signals.ema_crossover import EmaCrossoverSignal
from strategies_research.types import ResearchContext


def _context(history, timeframe="2M"):
    return ResearchContext(
        symbol="SPY",
        timeframe=timeframe,
        candle={"close": 600.0},
        ema_history=history,
        timestamp=datetime(2026, 1, 27, tzinfo=timezone.utc),
    )


def test_ema_crossover_detects_bullish_cross():
    strategy = EmaCrossoverSignal(cross_pairs=[(13, 48)])
    history = [
        {"13": 1.0, "48": 2.0, "200": 10.0},
        {"13": 3.0, "48": 2.5, "200": 10.0},
    ]
    signals = strategy.on_candle_close(_context(history))
    assert any(s.direction == "call" and s.variant == "13x48-bull" for s in signals)


def test_ema_crossover_detects_bearish_cross():
    strategy = EmaCrossoverSignal(cross_pairs=[(13, 48)])
    history = [
        {"13": 5.0, "48": 4.0, "200": 1.0},
        {"13": 3.0, "48": 4.5, "200": 1.0},
    ]
    signals = strategy.on_candle_close(_context(history))
    assert any(s.direction == "put" and s.variant == "13x48-bear" for s in signals)


def test_ema_crossover_requires_two_snapshots():
    strategy = EmaCrossoverSignal(cross_pairs=[(13, 48)])
    signals = strategy.on_candle_close(_context([{"13": 1.0, "48": 2.0, "200": 3.0}]))
    assert signals == []


def test_ema_crossover_timeframe_filter():
    strategy = EmaCrossoverSignal(cross_pairs=[(13, 48)], timeframes=["5M"])
    history = [
        {"13": 1.0, "48": 2.0, "200": 10.0},
        {"13": 3.0, "48": 2.5, "200": 10.0},
    ]
    signals = strategy.on_candle_close(_context(history, timeframe="2M"))
    assert signals == []
