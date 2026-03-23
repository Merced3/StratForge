from pathlib import Path

import plotly.graph_objects as go

from web_dash import chart_updater


def test_update_chart_pauses_exports_after_failure(monkeypatch, tmp_path):
    calls = []
    logs = []

    monkeypatch.setattr(chart_updater, "generate_live_chart", lambda _timeframe: go.Figure())
    monkeypatch.setattr(chart_updater, "get_chart_path", lambda _timeframe, zone_type=False: tmp_path / "chart.png")
    monkeypatch.setattr(chart_updater, "print_log", logs.append)

    def _fail_write(*_args, **_kwargs):
        calls.append("write")
        raise RuntimeError("browser failed")

    monkeypatch.setattr(chart_updater.pio, "write_image", _fail_write)
    chart_updater._clear_export_cooldown()

    try:
        assert chart_updater.update_chart("2M") is False
        assert chart_updater.update_chart("2M") is False
    finally:
        chart_updater._clear_export_cooldown()

    assert calls == ["write"]
    assert any("PNG export failed" in message for message in logs)
