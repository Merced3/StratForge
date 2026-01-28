from tools.analytics_v2.compute_path_metrics import compute_metrics


def test_compute_metrics_tracks_mfe_mae():
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
            {
                "ts": "2026-01-27T00:01:00+00:00",
                "event_key": "candle_close",
                "mark": 1.5,
                "underlying_price": 600.0,
            },
            {
                "ts": "2026-01-27T00:02:00+00:00",
                "event_key": "ema:13",
                "mark": 0.7,
                "underlying_price": 598.0,
            },
        ]
    }

    results = compute_metrics(signals, paths)
    assert len(results) == 1
    row = results[0]
    assert row["mfe"] == 0.5
    assert row["mae"] == -0.3
    assert row["mfe_event_key"] == "candle_close"
    assert row["mae_event_key"] == "ema:13"
    assert row["seconds_to_mfe"] == 60
    assert row["seconds_to_mae"] == 120

