import pytest

from integrations.discord.templates import (
    append_trade_update,
    extract_trade_results,
    extract_trade_totals,
    format_trade_add,
    format_trade_close,
    format_trade_open,
    format_trade_trim,
)


def test_extract_trade_totals_from_message():
    message = format_trade_open(
        strategy_name="ema",
        ticker_symbol="SPY",
        strike=500.0,
        option_type="call",
        quantity=2,
        order_price=1.5,
        total_investment=300.0,
        reason="signal",
    )
    message = append_trade_update(message, format_trade_add(1, 150.0, 1.5, "add"))
    message = append_trade_update(message, format_trade_trim(1, 200.0, 2.0, "trim"))
    message = append_trade_update(message, format_trade_trim(2, 220.0, 1.1, "close"))
    message = append_trade_update(
        message,
        format_trade_close(avg_exit=1.4, total_pnl=70.0, percent=15.56, profit_indicator=None),
    )

    totals = extract_trade_totals(message)
    assert totals["total_entry_cost"] == pytest.approx(450.0)
    assert totals["total_exit_qty"] == 3
    assert totals["total_exit_value"] == pytest.approx(420.0)


def test_extract_trade_results_from_summary():
    message = format_trade_open(
        strategy_name="ema",
        ticker_symbol="SPY",
        strike=500.0,
        option_type="call",
        quantity=1,
        order_price=1.0,
        total_investment=100.0,
    )
    message = append_trade_update(
        message,
        format_trade_close(avg_exit=1.2, total_pnl=20.0, percent=20.0, profit_indicator=None),
    )

    results = extract_trade_results(message, "msg-1")
    assert isinstance(results, dict)
    assert results["avg_bid"] == pytest.approx(1.2)
    assert results["total"] == pytest.approx(20.0)
    assert results["percent"] == pytest.approx(20.0)
    assert results["total_investment"] == pytest.approx(100.0)
