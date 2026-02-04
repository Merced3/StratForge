from datetime import datetime, timezone

import pytest

from options.quote_service import OptionContract, OptionQuote
from runtime.market_bus import CandleCloseEvent, MarketEventBus
from runtime import research_signal_runner as rsr
from strategies_research.types import ResearchContext, ResearchSignal

pytestmark = pytest.mark.anyio


class DummyQuoteService:
    def __init__(self, quote: OptionQuote) -> None:
        self._quote = quote

    def get_snapshot(self):
        return {self._quote.contract.key: self._quote}

    def get_quote(self, contract_key: str):
        if contract_key == self._quote.contract.key:
            return self._quote
        return None


class DummyStrategy:
    name = "ema-crossover"


async def test_candle_close_paths_dedupe(monkeypatch):
    captured = []

    def _capture(event, logger=None):
        captured.append(event)

    def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(rsr, "record_research_path_event", _capture)
    monkeypatch.setattr(rsr, "record_research_signal", _noop)

    contract = OptionContract(symbol="SPY", option_type="call", strike=600.0, expiration="2026-01-27")
    quote = OptionQuote(
        contract=contract,
        bid=0.95,
        ask=1.05,
        last=1.00,
        volume=None,
        open_interest=None,
        updated_at=datetime.now(timezone.utc),
    )
    runner = rsr.ResearchSignalRunner(
        bus=MarketEventBus(),
        quote_service=DummyQuoteService(quote),
        strategies=[],
        expiration="2026-01-27",
    )
    context = ResearchContext(
        symbol="SPY",
        timeframe="2M",
        candle={"close": 600.0},
        ema_history=[],
        timestamp=datetime.now(timezone.utc),
    )
    signal = ResearchSignal(direction="call", reason="test")
    await runner._record_signal(DummyStrategy(), signal, context, runner.quote_service.get_snapshot())

    candle_event = CandleCloseEvent(
        symbol="SPY",
        timeframe="2M",
        candle={"close": 600.0, "timestamp": "2026-01-27T00:00:00+00:00"},
        closed_at=datetime(2026, 1, 27, tzinfo=timezone.utc),
        source="schedule",
    )
    await runner._record_candle_close_paths(candle_event)
    await runner._record_candle_close_paths(candle_event)

    assert len(captured) == 1
    assert captured[0].event_key == "candle_close"


async def test_process_touches_records_events(monkeypatch):
    captured = []

    def _capture(event, logger=None):
        captured.append(event)

    monkeypatch.setattr(rsr, "record_research_path_event", _capture)

    contract = OptionContract(symbol="SPY", option_type="call", strike=600.0, expiration="2026-01-27")
    quote = OptionQuote(
        contract=contract,
        bid=0.95,
        ask=1.05,
        last=1.00,
        volume=None,
        open_interest=None,
        updated_at=datetime.now(timezone.utc),
    )
    runner = rsr.ResearchSignalRunner(
        bus=MarketEventBus(),
        quote_service=DummyQuoteService(quote),
        strategies=[],
        expiration="2026-01-27",
        touch_tolerance=0.5,
    )
    runner._active_signals["sig-1"] = rsr.ActiveSignal(
        signal_id="sig-1",
        strategy_tag="ema-crossover",
        timeframe="2M",
        symbol="SPY",
        contract_key=contract.key,
        option_type="call",
        strike=600.0,
        expiration="2026-01-27",
        variant="13x48-bull",
    )

    def _ema_history(_timeframe):
        return [{"13": 100.0}]

    runner._ema_cache.get_last_two = _ema_history  # type: ignore

    levels = [{"id": "L1", "type": "support", "y": 100.0}]
    zones = [{"id": "Z1", "type": "support", "top": 101.0, "bottom": 99.0}]
    now = datetime(2026, 1, 27, 14, 30, tzinfo=timezone.utc)

    runner._process_touches(100.0, now, zones, levels)
    runner._process_touches(100.0, now, zones, levels)

    keys = sorted({event.event_key for event in captured})
    assert keys == ["ema:13", "level:100.00", "zone:99.00-101.00"]


async def test_signal_tags_include_timeframe(monkeypatch):
    captured = []

    def _capture(event, logger=None):
        captured.append(event)

    def _fake_read_config(key: str):
        if key == "STRATEGY_TAG_INCLUDE_TIMEFRAME":
            return True
        return None

    monkeypatch.setattr(rsr, "record_research_signal", _capture)
    monkeypatch.setattr(rsr, "read_config", _fake_read_config)

    contract = OptionContract(symbol="SPY", option_type="call", strike=600.0, expiration="2026-01-27")
    quote = OptionQuote(
        contract=contract,
        bid=0.95,
        ask=1.05,
        last=1.00,
        volume=None,
        open_interest=None,
        updated_at=datetime.now(timezone.utc),
    )
    runner = rsr.ResearchSignalRunner(
        bus=MarketEventBus(),
        quote_service=DummyQuoteService(quote),
        strategies=[],
        expiration="2026-01-27",
    )
    context = ResearchContext(
        symbol="SPY",
        timeframe="2M",
        candle={"close": 600.0},
        ema_history=[],
        timestamp=datetime.now(timezone.utc),
    )
    signal = ResearchSignal(direction="call", reason="test")

    await runner._record_signal(DummyStrategy(), signal, context, runner.quote_service.get_snapshot())

    assert len(captured) == 1
    assert captured[0].strategy_tag == "ema-crossover-2m"
