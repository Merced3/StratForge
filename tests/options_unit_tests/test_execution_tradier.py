import pytest

pytestmark = pytest.mark.anyio

from options.execution_tradier import OptionOrderRequest, TradierOrderExecutor
from options.execution_tradier import _build_option_symbol


def test_build_option_symbol():
    symbol = _build_option_symbol("SPY", "call", 500.0, "20260106")
    assert symbol == "SPY260106C00500000"


async def test_tradier_limit_requires_price():
    executor = TradierOrderExecutor(
        session=None,
        base_url="https://api.tradier.com/v1",
        account_id="test",
        access_token="token",
    )
    request = OptionOrderRequest(
        symbol="SPY",
        option_type="call",
        strike=500.0,
        expiration="20260106",
        quantity=1,
        side="buy_to_open",
        order_type="limit",
        limit_price=None,
    )
    with pytest.raises(ValueError):
        await executor.submit_option_order(request)
