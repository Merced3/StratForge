# web_dash/charts/live_chart.py
from __future__ import annotations
import json
import re
import pandas as pd
import plotly.graph_objs as go
from dash import dcc

from utils.json_utils import read_config
from storage.viewport import load_viewport, get_timeframe_bounds
from web_dash.charts.theme import apply_layout, GREEN, RED
from web_dash.assets.object_styles import draw_objects

from paths import get_ema_path, get_markers_path
from utils.ema_utils import load_ema_json
from utils.timezone import NY_TZ_NAME

_BAR_MINUTES_RE = re.compile(r"(\d+)\s*[mM]")
TZ = NY_TZ_NAME

def _bar_minutes(tf: str) -> int:
    m = _BAR_MINUTES_RE.match(str(tf))
    return int(m.group(1)) if m else 1  # default to 1 minute if weird tf

def _coerce_pos_int(val, default: int) -> int:
    try:
        n = int(float(val))
        return n if n > 0 else default
    except (TypeError, ValueError):
        return default

def _pick_bars_limit(timeframe: str, default: int = 600) -> int:
    cfg = read_config("LIVE_BARS") or {}
    v = cfg.get(timeframe) or cfg.get(timeframe.upper()) or cfg.get(timeframe.lower())
    return _coerce_pos_int(v, default)

def _load_markers(timeframe: str):
    """Load per-timeframe markers JSON; return list or empty list on any issue."""
    path = get_markers_path(timeframe.upper())
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []

def generate_live_chart(timeframe: str):
    tf = timeframe.lower()
    symbol = read_config("SYMBOL")
    bars_limit = _pick_bars_limit(tf, default=600)
    tf_min = _bar_minutes(tf)
    #print(f"\n[live_chart] timeframe: {tf}")

    anchor = str(read_config("LIVE_ANCHOR")).lower()  # 'now' | 'latest'

    # If we have any parts at all, capture their latest ts for a fallback
    _min_ts, latest_parts_ts, _nparts = get_timeframe_bounds(
        timeframe=tf,
        include_days=False,
        include_parts=True,
    )

    if anchor == "latest" and latest_parts_ts is not None:
        t1 = latest_parts_ts
    else:
        t1 = pd.Timestamp.now()
    t0 = t1 - pd.Timedelta(minutes=bars_limit * tf_min)

    df_candles, df_objects = load_viewport(
        symbol=symbol, 
        timeframe=tf,
        t0_iso=t0.isoformat(),
        t1_iso=t1.isoformat(),
        include_days=False,    # LIVE = parts only
        include_parts=True,
    )

    # fallback: if 'now' produced 0 rows but we DO have parts, re-anchor to latest
    if df_candles.empty and latest_parts_ts is not None and anchor != "latest":
        t1 = latest_parts_ts
        t0 = t1 - pd.Timedelta(minutes=bars_limit * tf_min)
        df_candles, _ = load_viewport(
            symbol=symbol,
            timeframe=tf,
            t0_iso=t0.isoformat(),
            t1_iso=t1.isoformat(),
            include_days=False,
            include_parts=True,
        )

    if df_candles.empty:
        fig = go.Figure()
        fig.update_layout(
            title=f"Live {timeframe} Chart - No candle data",
            xaxis_title="", yaxis_title="", height=700
        )
        return dcc.Graph(figure=fig, style={"height": "700px"})

    # Normalize/clean + tail
    df_candles = df_candles.copy()
    df_candles["timestamp"] = pd.to_datetime(df_candles["ts"], errors="coerce")
    df_candles = df_candles.dropna(subset=["timestamp"]).sort_values("timestamp")
    if bars_limit:
        df_candles = df_candles.tail(bars_limit).reset_index(drop=True)

    # _ts_plot (naive ET) for both candles and objects
    ts = pd.to_datetime(df_candles["ts"], errors="coerce")
    if ts.dt.tz is None:
        ts_local = ts.dt.tz_localize("America/Chicago")
    else:
        ts_local = ts.dt.tz_convert("America/Chicago")
    ts_et = ts_local.dt.tz_convert(TZ)
    df_candles["_ts_plot"] = ts_et.dt.tz_localize(None)

    # Integer x positions (simple 0..N-1 for live parts)
    x_vals = pd.Series(range(len(df_candles)), index=df_candles.index)
    df_candles["_x_int"] = x_vals
    x_min, x_max = int(x_vals.min()), int(x_vals.max())

    # --- plot ---
    fig = go.Figure()
    candlex = df_candles["_x_int"].to_numpy()
    hovertext = [
        f"{ts:%b %d %Y %H:%M}<br>O {o}<br>H {h}<br>L {l}<br>C {c}"
        for ts, o, h, l, c in zip(df_candles["_ts_plot"], df_candles["open"], df_candles["high"], df_candles["low"], df_candles["close"])
    ]
    fig.add_trace(go.Candlestick(
        x=candlex,
        open=df_candles["open"], high=df_candles["high"],
        low=df_candles["low"], close=df_candles["close"],
        increasing_line_color=GREEN, decreasing_line_color=RED,
        increasing_fillcolor=GREEN, decreasing_fillcolor=RED,
        hovertext=hovertext, hoverinfo="text",
        name="Price",
    ))

    # Draw EMAs
    ema_path = get_ema_path(timeframe.upper())
    ema_raw = load_ema_json(ema_path)
    ema_df = pd.DataFrame(ema_raw) if isinstance(ema_raw, list) else pd.DataFrame()
    if not ema_df.empty and "x" in ema_df.columns:
        ema_df = ema_df.copy()
        ema_df["x"] = pd.to_numeric(ema_df["x"], errors="coerce")
        ema_df = ema_df.dropna(subset=["x"]).sort_values("x")

        # Align EMA x-values so the latest EMA lines up with the latest candle in view
        base_x = float(ema_df["x"].max()) - (len(df_candles) - 1)
        ema_df["_x_int"] = ema_df["x"] - base_x
        ema_df = ema_df[ema_df["_x_int"].between(x_min - 2, x_max + 2)]

        ema_colors = {str(w): color for w, color in (read_config("EMAS") or [])}
        value_cols = [c for c in ema_df.columns if c not in {"x", "_x_int", "ts", "timestamp"}]
        for col in value_cols:
            y_vals = pd.to_numeric(ema_df[col], errors="coerce")
            if y_vals.isna().all():
                continue
            fig.add_trace(go.Scatter(
                x=ema_df["_x_int"], y=y_vals,
                mode="lines", name=str(col).upper(),
                line=dict(width=1.4, color=ema_colors.get(str(col), "#1d4ed8")),
                yaxis="y",
                hovertemplate=f"{str(col).upper()} EMA: %{{y:.2f}}<extra></extra>",
            ))

    # Draw objects (zones/levels)
    draw_objects(fig, df_objects, df_candles, tf_min, variant="live")

    # Draw markers (per-timeframe JSON; x-axis is integer-based)
    markers = _load_markers(timeframe)
    if markers:
        df_m = pd.DataFrame(markers)
        if not df_m.empty and "x" in df_m and "y" in df_m:
            df_m = df_m.copy()
            df_m["x"] = pd.to_numeric(df_m["x"], errors="coerce")
            df_m["y"] = pd.to_numeric(df_m["y"], errors="coerce")
            df_m = df_m.dropna(subset=["x", "y"]).sort_values("x")

            symbol_map = {"^": "triangle-up", "v": "triangle-down", "o": "circle"}
            legend_seen = set()
            for _, row in df_m.iterrows():
                style = row.get("style") or {}
                marker_symbol = symbol_map.get(style.get("marker"), "circle")
                marker_color = style.get("color", "#2563eb")
                event = str(row.get("event_type", "marker")).upper()
                showleg = event not in legend_seen
                legend_seen.add(event)

                hover = f"{event}<br>Candle: {int(row.get('x', 0))}<br>Price: %{{y:.2f}}"

                fig.add_trace(go.Scatter(
                    x=[row["x"]],
                    y=[row["y"]],
                    mode="markers",
                    marker=dict(symbol=marker_symbol, size=10, color=marker_color, line=dict(width=1, color="#111")),
                    name=event,
                    hovertemplate=hover + "<extra></extra>",
                    showlegend=showleg,
                ))

    # Build readable time ticks on integer axis
    tickvals = []
    ticktext = []
    if len(df_candles) > 0:
        max_ticks = 8
        n = len(df_candles)
        step = max(1, int(round(n / max_ticks))) if n > max_ticks else 1
        idxs = list(range(0, n, step))
        if idxs[-1] != n - 1:
            idxs.append(n - 1)
        tickvals = df_candles["_x_int"].iloc[idxs].tolist()
        ticktext = df_candles["_ts_plot"].iloc[idxs].dt.strftime("%H:%M").tolist()
        fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)

    # Layout: key on the right, focus y-range on candles only
    visible_min = float(df_candles["low"].min())
    visible_max = float(df_candles["high"].max())
    span = max(visible_max - visible_min, 0.0)
    pad = max(span * 0.05, 0.05)

    apply_layout(fig, title=f"{symbol} - Live ({timeframe.upper()})", uirevision=f"live-{timeframe}")
    fig.update_xaxes(type="linear")
    fig.update_yaxes(range=[visible_min - pad, visible_max + pad], autorange=False)
    fig.update_traces(cliponaxis=True, selector=dict(type="scatter"))

    return dcc.Graph(figure=fig, style={"height": "700px"})
