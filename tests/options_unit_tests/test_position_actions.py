import asyncio
from datetime import datetime, timezone

import pytest

from options.position_watcher import PositionUpdate
from options.quote_service import OptionContract, OptionQuote
from runtime.market_bus import MarketEventBus
from runtime.options_strategy_runner import OptionsStrategyRunner
from strategies.options.types import PositionAction


pytestmark = pytest.mark.anyio


class DummyOrderManager:
    def __init__(self, position):
        self._position = position
        self.closed = False

    async def close_position(self, position_id: str):
        if self._position.position_id != position_id:
            return None
        self._position.status = "closed"
        self._position.quantity_open = 0
        self.closed = True
        return None

    async def trim_position(self, position_id: str, quantity: int):
        if self._position.position_id != position_id:
            return None
        self._position.quantity_open = max(0, self._position.quantity_open - quantity)
        return None

    async def add_to_position(self, position_id: str, quantity: int):
        if self._position.position_id != position_id:
            return None
        self._position.quantity_open += quantity
        return None

    def get_position(self, position_id: str):
        if self._position.position_id != position_id:
            return None
        return self._position


class CloseOnUpdateStrategy:
    name = "close-on-update"

    def on_candle_close(self, _context):
        return None

    def on_position_update(self, updates):
        update = updates[0]
        return PositionAction(
            action="close",
            position_id=update.position_id,
            reason="tp",
            timeframe="5M",
        )


async def test_runner_applies_position_action_close():
    contract = OptionContract(
        symbol="SPY",
        option_type="call",
        strike=500.0,
        expiration="20260106",
    )
    quote = OptionQuote(
        contract=contract,
        bid=1.5,
        ask=1.6,
        last=None,
        volume=None,
        open_interest=None,
        updated_at=datetime.now(timezone.utc),
    )
    now = datetime.now(timezone.utc)
    update = PositionUpdate(
        position_id="pos-test",
        contract_key=contract.key,
        quote=quote,
        mark_price=1.5,
        mark_source="bid",
        unrealized_pnl=100.0,
        unrealized_pct=200.0,
        realized_pnl=0.0,
        quantity_open=1,
        avg_entry=1.0,
        status="open",
        strategy_tag="close-on-update",
        updated_at=now,
    )

    position = type("Pos", (), {"position_id": "pos-test", "status": "open", "quantity_open": 1})()
    order_manager = DummyOrderManager(position)

    captured = {}

    def on_closed(pos, _result, reason, timeframe):
        captured["reason"] = reason
        captured["timeframe"] = timeframe

    runner = OptionsStrategyRunner(
        MarketEventBus(),
        order_manager,
        [CloseOnUpdateStrategy()],
        expiration="20260106",
        on_position_closed=on_closed,
    )

    await runner._handle_position_updates([update])

    assert order_manager.closed is True
    assert captured["reason"] == "tp"
    assert captured["timeframe"] == "5M"
