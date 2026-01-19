import asyncio
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.anyio

from options.order_manager import Position
from options.position_watcher import PositionWatcher
from options.quote_service import OptionContract, OptionQuote, OptionQuoteService


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


async def test_position_watcher_emits_updates():
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
        quantity_open=2,
        avg_entry=1.0,
        realized_pnl=12.5,
        status="open",
        created_at=now,
        updated_at=now,
        strategy_tag="flag_zone",
    )

    def positions_provider():
        return [position]

    watcher = PositionWatcher(service, positions_provider, refresh_interval=0.0)
    _, updates_queue = watcher.register_queue()

    await service.start()
    await watcher.start()
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
        updates = await asyncio.wait_for(updates_queue.get(), timeout=1)
        assert len(updates) == 1
        update = updates[0]
        assert update.position_id == "pos-test"
        assert update.contract_key == contract.key
        assert update.strategy_tag == "flag_zone"
        assert update.mark_source == "bid"
        assert update.mark_price == pytest.approx(1.2)
        assert update.realized_pnl == pytest.approx(12.5)
        assert update.unrealized_pnl == pytest.approx((1.2 - 1.0) * 2 * 100)
        assert update.unrealized_pct == pytest.approx(((1.2 - 1.0) / 1.0) * 100)
    finally:
        await watcher.stop()
        await service.stop()
