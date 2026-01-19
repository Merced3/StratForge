from datetime import datetime, timezone

from options.selection import (
    DEFAULT_SELECTOR_REGISTRY,
    PriceRangeOtmSelector,
    SelectionRequest,
    SelectorRegistry,
    select_contract,
)
from options.quote_service import OptionContract, OptionQuote


def _make_quote(symbol, option_type, strike, expiration, bid, ask):
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
        last=None,
        volume=None,
        open_interest=None,
        updated_at=datetime.now(timezone.utc),
    )


def test_price_range_selector_pick():
    quotes = [
        _make_quote("SPY", "call", 101.0, "20260106", bid=0.2, ask=0.25),
        _make_quote("SPY", "call", 102.0, "20260106", bid=0.3, ask=0.4),
        _make_quote("SPY", "call", 103.0, "20260106", bid=0.35, ask=0.6),
    ]
    request = SelectionRequest(
        symbol="SPY",
        option_type="call",
        expiration="20260106",
        underlying_price=100.0,
        max_otm=5.0,
    )
    result = select_contract(quotes, request)
    assert result is not None
    assert result.quote.contract.strike == 102.0
    assert result.reason == "price-range"


def test_price_range_selector_fallback():
    quotes = [
        _make_quote("SPY", "call", 101.0, "20260106", bid=0.05, ask=0.08),
        _make_quote("SPY", "call", 102.0, "20260106", bid=0.06, ask=0.09),
    ]
    request = SelectionRequest(
        symbol="SPY",
        option_type="call",
        expiration="20260106",
        underlying_price=100.0,
        max_otm=5.0,
    )
    result = select_contract(quotes, request)
    assert result is not None
    assert result.reason == "fallback-cheapest"
    assert result.quote.contract.strike == 101.0


def test_price_range_selector_respects_max_otm():
    quotes = [
        _make_quote("SPY", "call", 102.0, "20260106", bid=0.3, ask=0.4),
        _make_quote("SPY", "call", 106.0, "20260106", bid=0.4, ask=0.45),
    ]
    request = SelectionRequest(
        symbol="SPY",
        option_type="call",
        expiration="20260106",
        underlying_price=100.0,
        max_otm=3.0,
    )
    result = select_contract(quotes, request)
    assert result is not None
    assert result.quote.contract.strike == 102.0


def test_selector_registry():
    registry = SelectorRegistry()
    registry.register(PriceRangeOtmSelector())
    assert "price-range-otm" in registry.list_names()

    quotes = [
        _make_quote("SPY", "put", 98.0, "20260106", bid=0.3, ask=0.45),
    ]
    request = SelectionRequest(
        symbol="SPY",
        option_type="put",
        expiration="20260106",
        underlying_price=100.0,
        max_otm=5.0,
    )
    result = select_contract(quotes, request, registry=registry)
    assert result is not None
