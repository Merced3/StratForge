from datetime import timedelta
from pathlib import Path

import pytest

from tools.analytics_trade_ledger import _compute_metrics, _load_positions


def _fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "trade_events_sample.jsonl"


def test_load_positions_extracts_summary_fields():
    positions = _load_positions(_fixture_path())
    by_id = {position.position_id: position for position in positions}

    assert len(by_id) == 3

    pos1 = by_id["pos-1"]
    assert pos1.strategy_tag == "flag_zone"
    assert pos1.symbol == "SPY"
    assert pos1.option_type == "call"
    assert pos1.opened_at.isoformat() == "2026-01-20T14:30:00+00:00"
    assert pos1.closed_at.isoformat() == "2026-01-20T15:00:00+00:00"
    assert pos1.first_event_at.isoformat() == "2026-01-20T14:30:00+00:00"
    assert pos1.last_event_at.isoformat() == "2026-01-20T15:00:00+00:00"
    assert pos1.realized_pnl == 120.0
    assert pos1.hold_time == timedelta(minutes=30)
    assert pos1.entry_cost == pytest.approx(320.0)

    pos2 = by_id["pos-2"]
    assert pos2.strategy_tag == "flag_zone"
    assert pos2.symbol == "SPY"
    assert pos2.option_type == "put"
    assert pos2.hold_time == timedelta(minutes=15)
    assert pos2.realized_pnl == -60.0
    assert pos2.entry_cost == pytest.approx(140.0)

    pos3 = by_id["pos-3"]
    assert pos3.strategy_tag == "breakout"
    assert pos3.symbol == "SPY"
    assert pos3.option_type == "call"
    assert pos3.closed_at is None
    assert pos3.hold_time is None
    assert pos3.first_event_at.isoformat() == "2026-01-20T16:00:00+00:00"
    assert pos3.last_event_at.isoformat() == "2026-01-20T16:05:00+00:00"
    assert pos3.entry_cost == pytest.approx(190.0)


def test_compute_metrics_from_fixture():
    positions = _load_positions(_fixture_path())
    metrics = _compute_metrics(positions)

    assert metrics["positions"] == 3
    assert metrics["closed"] == 2
    assert metrics["open"] == 1
    assert metrics["first_trade_date"] == "2026-01-20"
    assert metrics["last_trade_date"] == "2026-01-20"
    assert metrics["trade_days"] == 1
    assert metrics["trades_per_day"] == pytest.approx(2.0)
    assert metrics["call_count"] == 1
    assert metrics["put_count"] == 1
    assert metrics["call_pct"] == pytest.approx(0.5)
    assert metrics["put_pct"] == pytest.approx(0.5)
    assert metrics["top_symbol"] == "SPY"
    assert metrics["top_symbol_count"] == 2
    assert metrics["top_symbol_pct"] == pytest.approx(1.0)
    assert metrics["sample_flag"] == "2 trades (LOW)"
    assert metrics["pnl_total"] == 60.0
    assert metrics["entry_cost"] == pytest.approx(460.0)
    assert metrics["pnl_per_dollar"] == pytest.approx(60.0 / 460.0)
    assert metrics["expectancy"] == pytest.approx(30.0)
    assert metrics["win_rate"] == pytest.approx(0.5)
    assert metrics["avg_win"] == pytest.approx(120.0)
    assert metrics["avg_loss"] == pytest.approx(-60.0)
    assert metrics["avg_hold"].total_seconds() == pytest.approx(1350.0)
