from datetime import datetime, timezone

import pytest

from options.position_watcher import PositionUpdate
from options.quote_service import OptionContract, OptionQuote
from strategies.options.exit_rules import ProfitTargetPlan, ProfitTargetStep


def _make_update(position_id: str, pct: float, qty: int) -> PositionUpdate:
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
    return PositionUpdate(
        position_id=position_id,
        contract_key=contract.key,
        quote=quote,
        mark_price=1.5,
        mark_source="bid",
        unrealized_pnl=100.0,
        unrealized_pct=pct,
        realized_pnl=0.0,
        quantity_open=qty,
        avg_entry=1.0,
        status="open",
        strategy_tag="ema",
        updated_at=now,
    )


def test_profit_target_plan_trim_then_close():
    plan = ProfitTargetPlan(
        [
            ProfitTargetStep(target_pct=100.0, action="trim", fraction=0.5),
            ProfitTargetStep(target_pct=200.0, action="close"),
        ]
    )

    first_update = _make_update("pos-1", pct=120.0, qty=4)
    actions = plan.evaluate_update(first_update, timeframe="15M")
    assert len(actions) == 1
    assert actions[0].action == "trim"
    assert actions[0].quantity == 2
    assert actions[0].timeframe == "15M"

    second_update = _make_update("pos-1", pct=220.0, qty=2)
    actions = plan.evaluate_update(second_update, timeframe="15M")
    assert len(actions) == 1
    assert actions[0].action == "close"


def test_profit_target_plan_fraction_rounds_up_min_one():
    plan = ProfitTargetPlan([ProfitTargetStep(target_pct=50.0, action="trim", fraction=0.25)])

    update = _make_update("pos-2", pct=60.0, qty=3)
    actions = plan.evaluate_update(update)
    assert len(actions) == 1
    assert actions[0].action == "trim"
    assert actions[0].quantity == 1


def test_profit_target_plan_fixed_quantity_trim():
    plan = ProfitTargetPlan([ProfitTargetStep(target_pct=50.0, action="trim", quantity=2)])

    update = _make_update("pos-3", pct=60.0, qty=5)
    actions = plan.evaluate_update(update)
    assert len(actions) == 1
    assert actions[0].action == "trim"
    assert actions[0].quantity == 2


def test_profit_target_plan_trim_exceeding_quantity_closes():
    plan = ProfitTargetPlan([ProfitTargetStep(target_pct=50.0, action="trim", quantity=5)])

    update = _make_update("pos-4", pct=60.0, qty=3)
    actions = plan.evaluate_update(update)
    assert len(actions) == 1
    assert actions[0].action == "close"
    assert actions[0].quantity is None


def test_profit_target_plan_trim_skips_if_would_close():
    plan = ProfitTargetPlan(
        [
            ProfitTargetStep(
                target_pct=100.0,
                action="trim",
                fraction=0.5,
                allow_full_close=False,
            ),
            ProfitTargetStep(target_pct=200.0, action="close"),
        ]
    )

    update = _make_update("pos-5b", pct=120.0, qty=1)
    actions = plan.evaluate_update(update)
    assert actions == []

    second_update = _make_update("pos-5b", pct=220.0, qty=1)
    actions = plan.evaluate_update(second_update)
    assert len(actions) == 1
    assert actions[0].action == "close"


def test_profit_target_plan_fires_only_once_per_step():
    plan = ProfitTargetPlan([ProfitTargetStep(target_pct=100.0, action="trim", fraction=0.5)])

    first = _make_update("pos-5", pct=120.0, qty=4)
    actions = plan.evaluate_update(first)
    assert len(actions) == 1

    second = _make_update("pos-5", pct=150.0, qty=3)
    actions = plan.evaluate_update(second)
    assert actions == []


def test_profit_target_plan_resets_after_close():
    plan = ProfitTargetPlan([ProfitTargetStep(target_pct=100.0, action="trim", fraction=0.5)])

    update = _make_update("pos-6", pct=120.0, qty=4)
    actions = plan.evaluate_update(update)
    assert len(actions) == 1

    closed = _make_update("pos-6", pct=0.0, qty=0)
    closed = closed.__class__(**{**closed.__dict__, "status": "closed"})
    plan.evaluate_update(closed)

    reopened = _make_update("pos-6", pct=120.0, qty=4)
    actions = plan.evaluate_update(reopened)
    assert len(actions) == 1
