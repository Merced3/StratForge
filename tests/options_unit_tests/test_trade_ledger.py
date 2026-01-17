import json
from datetime import datetime, timezone

from options.execution_tradier import OrderSubmitResult
from options.order_manager import Position
from options.quote_service import OptionContract
from options.trade_ledger import build_trade_event, record_trade_event


def _make_position() -> Position:
    contract = OptionContract(
        symbol="SPY",
        option_type="call",
        strike=500.0,
        expiration="20260106",
    )
    now = datetime.now(timezone.utc)
    return Position(
        position_id="pos-test",
        contract=contract,
        quantity_open=2,
        avg_entry=1.25,
        realized_pnl=50.0,
        status="open",
        created_at=now,
        updated_at=now,
        strategy_tag="ema",
    )


def test_record_trade_event_writes_jsonl(tmp_path):
    position = _make_position()
    order_result = OrderSubmitResult(order_id="order-1", status="filled", raw={"fill_price": 1.5})
    event = build_trade_event("open", position, order_result, 2, 1.5, "signal")

    ledger_path = tmp_path / "trade_events.jsonl"
    record_trade_event(event, path=ledger_path)

    payload = ledger_path.read_text().strip()
    data = json.loads(payload)

    assert data["event"] == "open"
    assert data["position_id"] == "pos-test"
    assert data["order_id"] == "order-1"
    assert data["order_status"] == "filled"
    assert data["symbol"] == "SPY"
    assert data["option_type"] == "call"
    assert data["strike"] == 500.0
    assert data["expiration"] == "20260106"
    assert data["strategy_tag"] == "ema"
    assert data["quantity"] == 2
    assert data["fill_price"] == 1.5
    assert data["total_value"] == 300.0
    assert data["realized_pnl"] == 50.0
    assert data["reason"] == "signal"
    assert "ts" in data
