from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.anyio

from options.execution_paper import PaperOrderExecutor, PaperOrderError
from options.execution_tradier import OptionOrderRequest
from options.quote_service import OptionContract, OptionQuote


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


async def test_paper_executor_market_fill_buy():
    quotes = {
        "SPY-call-500.0-20260106": _make_quote("SPY", "call", 500.0, "20260106", bid=1.0, ask=1.2, last=1.1),
    }

    executor = PaperOrderExecutor(quotes.get)
    request = OptionOrderRequest(
        symbol="SPY",
        option_type="call",
        strike=500.0,
        expiration="20260106",
        quantity=1,
        side="buy_to_open",
    )
    result = await executor.submit_option_order(request)
    status = await executor.get_order_status(result.order_id)

    assert status.status == "filled"
    assert status.avg_fill_price == 1.2


async def test_paper_executor_market_fill_sell():
    quotes = {
        "SPY-put-490.0-20260106": _make_quote("SPY", "put", 490.0, "20260106", bid=0.8, ask=0.9, last=0.85),
    }

    executor = PaperOrderExecutor(quotes.get)
    request = OptionOrderRequest(
        symbol="SPY",
        option_type="put",
        strike=490.0,
        expiration="20260106",
        quantity=2,
        side="sell_to_close",
    )
    result = await executor.submit_option_order(request)
    status = await executor.get_order_status(result.order_id)

    assert status.status == "filled"
    assert status.avg_fill_price == 0.8
    assert status.filled_quantity == 2


async def test_paper_executor_limit_rejects_when_not_crossed():
    quotes = {
        "SPY-call-500.0-20260106": _make_quote("SPY", "call", 500.0, "20260106", bid=1.0, ask=1.2, last=1.1),
    }

    executor = PaperOrderExecutor(quotes.get)
    request = OptionOrderRequest(
        symbol="SPY",
        option_type="call",
        strike=500.0,
        expiration="20260106",
        quantity=1,
        side="buy_to_open",
        order_type="limit",
        limit_price=1.0,
    )
    result = await executor.submit_option_order(request)
    status = await executor.get_order_status(result.order_id)

    assert status.status == "rejected"


async def test_paper_executor_missing_quote():
    executor = PaperOrderExecutor(lambda _: None)
    request = OptionOrderRequest(
        symbol="SPY",
        option_type="call",
        strike=500.0,
        expiration="20260106",
        quantity=1,
        side="buy_to_open",
    )
    result = await executor.submit_option_order(request)
    assert result.status == "rejected"

    with pytest.raises(PaperOrderError):
        await executor.get_order_status("missing-order")
