import asyncio
import json
import time
from datetime import datetime, timezone

import pytest

from options.execution_paper import PaperOrderExecutor
from options.mock_provider import SyntheticOptionsProvider, SyntheticQuoteConfig
from options.order_manager import OptionsOrderManager
from options.quote_service import OptionQuoteService
from runtime.market_bus import CandleCloseEvent, MarketEventBus
from runtime.options_strategy_runner import OptionsStrategyRunner
from strategies.options.ema_crossover import EmaCrossoverStrategy

import runtime.options_strategy_runner as runner_mod


pytestmark = pytest.mark.anyio


def _write_ema(path, fast, slow):
    payload = [{"13": fast, "48": slow, "x": 0}]
    path.write_text(json.dumps(payload), encoding="utf-8")


async def _wait_for(predicate, timeout=1.0):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def test_strategy_runner_opens_and_flips(tmp_path, monkeypatch):
    ema_path = tmp_path / "15M.json"
    _write_ema(ema_path, fast=10.0, slow=5.0)
    monkeypatch.setattr(runner_mod, "get_ema_path", lambda _tf: ema_path)

    config = SyntheticQuoteConfig(
        underlying_price=500.0,
        strike_step=1.0,
        strikes_each_side=5,
        price_jitter=0.0,
        spread_pct=0.02,
        min_spread=0.01,
        time_value_atm=0.4,
        time_value_decay=0.02,
        min_time_value=0.1,
        seed=123,
    )
    provider = SyntheticOptionsProvider("SPY", "20260106", config)
    service = OptionQuoteService(
        provider,
        symbol="SPY",
        expiration="20260106",
        poll_interval=0.01,
    )
    _, queue = service.register_queue(contract_ids=None, maxsize=1)
    await service.start()
    try:
        await asyncio.wait_for(queue.get(), timeout=1.0)

        bus = MarketEventBus()
        executor = PaperOrderExecutor(service.get_quote)
        order_manager = OptionsOrderManager(service, executor)
        strategy = EmaCrossoverStrategy()
        runner = OptionsStrategyRunner(
            bus,
            order_manager,
            [strategy],
            expiration="20260106",
        )
        runner.start()
        try:
            event = CandleCloseEvent(
                symbol="SPY",
                timeframe="15M",
                candle={"close": 500.0},
                closed_at=datetime.now(timezone.utc),
                source="test",
            )
            await bus.publish_candle_close(event)
            opened = await _wait_for(
                lambda: any(p.status == "open" for p in order_manager.list_positions().values())
            )
            assert opened, "expected an open position after bullish crossover"

            _write_ema(ema_path, fast=5.0, slow=10.0)
            event = CandleCloseEvent(
                symbol="SPY",
                timeframe="15M",
                candle={"close": 500.0},
                closed_at=datetime.now(timezone.utc),
                source="test",
            )
            await bus.publish_candle_close(event)
            flipped = await _wait_for(
                lambda: any(
                    p.status == "open" and p.contract.option_type == "put"
                    for p in order_manager.list_positions().values()
                )
            )
            assert flipped, "expected an open put after bearish crossover"
        finally:
            runner.stop()
    finally:
        await service.stop()
