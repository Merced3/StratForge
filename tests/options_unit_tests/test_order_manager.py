from datetime import datetime, timezone

import pytest

from options.execution_paper import PaperOrderExecutor
from options.order_manager import OptionsOrderManager
from options.quote_service import OptionContract, OptionQuote
from options.selection import SelectionRequest


class SnapshotQuoteService:
    def __init__(self, quotes):
        self._quotes = {q.contract.key: q for q in quotes}

    def get_snapshot(self):
        return dict(self._quotes)

    def get_quote(self, contract_key):
        return self._quotes.get(contract_key)


def _make_quote(symbol, option_type, strike, expiration, bid, ask, last=None):
    contract = OptionContract(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
    )
    return OptionQuote(
        contract=contract,
        bid=bid,
        ask=ask,
        last=last,
        volume=None,
        open_interest=None,
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.anyio
async def test_order_manager_buy_and_sell():
    quotes = [
        _make_quote("SPY", "call", 101.0, "20260106", bid=0.2, ask=0.25),
        _make_quote("SPY", "call", 102.0, "20260106", bid=0.3, ask=0.4),
    ]
    service = SnapshotQuoteService(quotes)
    executor = PaperOrderExecutor(service.get_quote)
    manager = OptionsOrderManager(service, executor)

    request = SelectionRequest(
        symbol="SPY",
        option_type="call",
        expiration="20260106",
        underlying_price=100.0,
        max_otm=5.0,
    )

    buy_result = await manager.buy(request, quantity=1)
    assert buy_result.order_id
    buy_context = manager.get_context(buy_result.order_id)
    assert buy_context is not None
    assert buy_context.side == "buy_to_open"

    sell_result = await manager.sell(buy_context.contract, quantity=1)
    sell_context = manager.get_context(sell_result.order_id)
    assert sell_context is not None
    assert sell_context.side == "sell_to_close"
