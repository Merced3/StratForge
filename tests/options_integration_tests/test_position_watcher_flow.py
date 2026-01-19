import asyncio
from datetime import datetime, timezone

import pytest

from options.execution_paper import PaperOrderExecutor
from options.order_manager import OptionsOrderManager, Position
from options.position_watcher import PositionWatcher
from options.quote_service import OptionContract, OptionQuote, OptionQuoteService
from runtime.market_bus import MarketEventBus
from runtime.options_strategy_runner import OptionsStrategyRunner


pytestmark = pytest.mark.anyio


class QueueProvider:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = None

    @property
    def queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    async def fetch_quotes(self, symbol: str, expiration: str):
        return await self.queue.get()


class PositionUpdateStrategy:
    name = "test-strategy"

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.updates = []

    def on_candle_close(self, _context):
        return None

    def on_position_update(self, updates):
        self.updates.extend(updates)
        self.event.set()


async def test_position_watcher_routes_updates_to_strategy():
    provider = QueueProvider()
    service = OptionQuoteService(
        provider,
        symbol="SPY",
        expiration="20260106",
        poll_interval=0.01,
    )
    contract = OptionContract(
        symbol="SPY",
        option_type="call",
        strike=500.0,
        expiration="20260106",
    )
    now = datetime.now(timezone.utc)
    position = Position(
        position_id="pos-test",
        contract=contract,
        quantity_open=1,
        avg_entry=1.0,
        realized_pnl=0.0,
        status="open",
        created_at=now,
        updated_at=now,
        strategy_tag="test-strategy",
    )

    watcher = PositionWatcher(service, lambda: [position], refresh_interval=0.0)
    strategy = PositionUpdateStrategy()
    executor = PaperOrderExecutor(service.get_quote)
    order_manager = OptionsOrderManager(service, executor)
    runner = OptionsStrategyRunner(
        MarketEventBus(),
        order_manager,
        [strategy],
        expiration="20260106",
        position_watcher=watcher,
    )

    await service.start()
    await watcher.start()
    runner.start()
    try:
        await asyncio.sleep(0.05)
        quote = OptionQuote(
            contract=contract,
            bid=1.2,
            ask=1.3,
            last=None,
            volume=None,
            open_interest=None,
            updated_at=now,
        )
        await provider.queue.put([quote])
        await asyncio.wait_for(strategy.event.wait(), timeout=1.0)
        assert strategy.updates, "expected strategy to receive position updates"
        update = strategy.updates[0]
        assert update.position_id == "pos-test"
        assert update.strategy_tag == "test-strategy"
        assert update.mark_price == pytest.approx(1.2)
    finally:
        runner.stop()
        await watcher.stop()
        await service.stop()
