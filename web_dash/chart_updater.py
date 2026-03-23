# web_dash/chart_updater.py
from datetime import datetime, timedelta
from threading import Lock
import time

from paths import get_chart_path
import plotly.graph_objects as go
import plotly.io as pio
from web_dash.charts.live_chart import generate_live_chart
from web_dash.charts.zones_chart import generate_zones_chart
import httpx
from shared_state import print_log

_EXPORT_LOCK = Lock()
_EXPORT_FAILURE_COOLDOWN_SECONDS = 600
_export_disabled_until_monotonic = 0.0

def _as_figure(component_or_figure):
    """Accepts dcc.Graph, dict, or Figure and returns a real go.Figure."""
    fig_like = getattr(component_or_figure, "figure", component_or_figure)
    return go.Figure(fig_like)

def update_chart(timeframe="2M", chart_type="live", notify=False):
    """
    Saves a snapshot of a chart based on timeframe and chart type.
    chart_type: "live" (2M/5M/15M) or "zones".
    """
    # Build a clean figure for static export
    if chart_type == "zones":
        fig = _as_figure(generate_zones_chart("15m"))
        out = get_chart_path(timeframe, zone_type=True)

        # Guardrails for zones (categorical x)
        fig.update_layout(
            template=None,
            uirevision=None,
            xaxis=dict(type="linear"),
        )
    elif chart_type == "live":
        fig = _as_figure(generate_live_chart(timeframe))
        out = get_chart_path(timeframe)

        # Guardrails for live (numeric x)
        fig.update_layout(
            template=None,
            uirevision=None,
            xaxis=dict(type="linear"),
        )
    else:
        raise ValueError(f"[update_chart] Invalid chart_type: {chart_type}")

    out.parent.mkdir(parents=True, exist_ok=True)
    if _export_cooldown_active():
        return False

    try:
        with _EXPORT_LOCK:
            if _export_cooldown_active():
                return False
            pio.write_image(fig, str(out), format="png", width=1400, height=700, engine="kaleido")
    except Exception as exc:
        _set_export_cooldown()
        retry_at = datetime.now() + timedelta(seconds=_EXPORT_FAILURE_COOLDOWN_SECONDS)
        print_log(
            "[update_chart] PNG export failed; pausing chart image saves until "
            f"{retry_at.strftime('%H:%M:%S')}. {type(exc).__name__}: {exc}"
        )
        return False

    _clear_export_cooldown()

    if notify:
        tfs = ["zones"] if chart_type == "zones" else [timeframe]
        try:
            httpx.post("http://127.0.0.1:8000/trigger-chart-update", json={"timeframes": tfs})
        except Exception as e:
            print(f"[update_chart] WS notify failed: {e}")
    return True


def _export_cooldown_active() -> bool:
    return time.monotonic() < _export_disabled_until_monotonic


def _set_export_cooldown() -> None:
    global _export_disabled_until_monotonic
    _export_disabled_until_monotonic = time.monotonic() + _EXPORT_FAILURE_COOLDOWN_SECONDS


def _clear_export_cooldown() -> None:
    global _export_disabled_until_monotonic
    _export_disabled_until_monotonic = 0.0
