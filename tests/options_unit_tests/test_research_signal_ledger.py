import json

from options.research_signal_ledger import ResearchSignalEvent, record_research_signal


def test_record_research_signal_writes_jsonl(tmp_path):
    path = tmp_path / "strategy_signals.jsonl"
    event = ResearchSignalEvent(
        ts="2026-01-27T00:00:00+00:00",
        event="signal",
        signal_id="sig-ema-2M-1",
        strategy_tag="ema-crossover",
        timeframe="2M",
        symbol="SPY",
        option_type="call",
        strike=600.0,
        expiration="2026-01-27",
        contract_key="SPY-call-600-2026-01-27",
        underlying_price=599.0,
        entry_mark=1.23,
        bid=1.20,
        ask=1.26,
        last=1.24,
        reason="13 crossed above 48",
        variant="13x48-bull",
    )

    record_research_signal(event, path=path)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["signal_id"] == "sig-ema-2M-1"
    assert payload["entry_mark"] == 1.23
    assert payload["strategy_tag"] == "ema-crossover"

