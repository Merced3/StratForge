import json

from options.research_path_ledger import ResearchPathEvent, record_research_path_event


def test_record_research_path_event_writes_jsonl(tmp_path):
    path = tmp_path / "strategy_paths.jsonl"
    event = ResearchPathEvent(
        ts="2026-01-27T00:00:10+00:00",
        event="candle_close",
        event_key="candle_close",
        signal_id="sig-ema-2M-1",
        strategy_tag="ema-crossover",
        timeframe="2M",
        symbol="SPY",
        option_type="call",
        strike=600.0,
        expiration="2026-01-27",
        contract_key="SPY-call-600-2026-01-27",
        underlying_price=599.5,
        mark=1.10,
        bid=1.05,
        ask=1.15,
        last=1.12,
        reason="close:buffer",
        variant="13x48-bull",
    )

    record_research_path_event(event, path=path)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["signal_id"] == "sig-ema-2M-1"
    assert payload["event_key"] == "candle_close"
    assert payload["mark"] == 1.10
