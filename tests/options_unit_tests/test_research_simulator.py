from tools.analytics_v2.simulate_rules import simulate_rules


def test_simulate_tp_sl_rule():
    signals = {
        "sig-1": {
            "signal_id": "sig-1",
            "strategy_tag": "ema-crossover",
            "timeframe": "2M",
            "symbol": "SPY",
            "option_type": "call",
            "strike": 600.0,
            "expiration": "2026-01-27",
            "contract_key": "SPY-call-600-2026-01-27",
            "ts": "2026-01-27T00:00:00+00:00",
            "entry_mark": 1.0,
        }
    }
    paths = {
        "sig-1": [
            {"ts": "2026-01-27T00:01:00+00:00", "event_key": "candle_close", "mark": 1.6},
            {"ts": "2026-01-27T00:02:00+00:00", "event_key": "ema:13", "mark": 0.7},
        ]
    }
    rules = [{"name": "tp50_sl30", "type": "tp_sl", "tp_pct": 0.5, "sl_pct": -0.3}]

    results = simulate_rules(signals, paths, rules)
    assert len(results) == 1
    row = results[0]
    assert row["exit_reason"] == "tp"
    assert row["exit_event_key"] == "candle_close"
    assert row["pnl"] == 0.6


def test_simulate_touch_rule():
    signals = {
        "sig-1": {
            "signal_id": "sig-1",
            "strategy_tag": "ema-crossover",
            "timeframe": "2M",
            "symbol": "SPY",
            "option_type": "call",
            "strike": 600.0,
            "expiration": "2026-01-27",
            "contract_key": "SPY-call-600-2026-01-27",
            "ts": "2026-01-27T00:00:00+00:00",
            "entry_mark": 1.0,
        }
    }
    paths = {
        "sig-1": [
            {"ts": "2026-01-27T00:01:00+00:00", "event_key": "level:600.00", "mark": 1.2},
            {"ts": "2026-01-27T00:02:00+00:00", "event_key": "ema:13", "mark": 1.1},
        ]
    }
    rules = [{"name": "exit_levels", "type": "touch", "event_prefixes": ["level:"]}]

    results = simulate_rules(signals, paths, rules)
    assert len(results) == 1
    row = results[0]
    assert row["exit_reason"] == "touch"
    assert row["exit_event_key"] == "level:600.00"
