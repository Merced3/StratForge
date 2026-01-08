# web_dash/charts/zones_chart.py
from __future__ import annotations
import re
from dash import dcc
import plotly.graph_objs as go
import pandas as pd
from utils.json_utils import read_config
from storage.viewport import load_viewport, days_window
from web_dash.assets.object_styles import draw_objects
from web_dash.charts.theme import apply_layout, GREEN, RED
from utils.timezone import NY_TZ_NAME

TZ = NY_TZ_NAME

def _tf_minutes(tf: str) -> int:
    # robust: "15m", "15M" -> 15; "2m" -> 2
    m = re.search(r"(\d+)\s*[mM]", tf)
    return int(m.group(1)) if m else 15

def _add_day_bands(fig: go.Figure, x_pos: pd.Series, dates: pd.Series, opacity=0.40):
    dates = pd.Series(dates)
    for i, d in enumerate(pd.unique(dates)):
        mask = dates == d
        if not mask.any():
            continue
        x0 = float(x_pos[mask].min()) - 0.5
        x1 = float(x_pos[mask].max()) + 0.5
        color = "#f1f3f5" if i % 2 == 0 else "#ffffff"
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, opacity=opacity,
                      layer="below", line_width=0)

def generate_zones_chart(timeframe: str = "15m", days: int = 10):
    symbol = read_config("SYMBOL")
    t0, t1, picked = days_window(timeframe, days)

    # 1) Don't pull parts, only dayfiles (parts for live chart)
    df_c, df_o = load_viewport(
        symbol=symbol, timeframe=timeframe,
        t0_iso=t0, t1_iso=t1,
        include_days=True, include_parts=False,
    )

    # --- debug: counts per ET day before trimming ---
    ts_et_raw = pd.to_datetime(df_c["ts"], utc=True, errors="coerce").dt.tz_convert(TZ)
    pre_counts_c = pd.Series(ts_et_raw.dt.date).value_counts().sort_index()
    
    # objects structure: Columns: [object_id, id, type, left, y, top, bottom, status, symbol, timeframe]
    if "ts" in df_o.columns: # We need to change this, not just the if statement but the contents inside to better handle what we want to display in terminal, best fit.
        ts_et_o = pd.to_datetime(df_o["ts"], utc=True, errors="coerce").dt.tz_convert(TZ)
        pre_counts_o = pd.Series(ts_et_o.dt.date).value_counts().sort_index()

    # Empty case
    if df_c.empty:
        empty = go.Figure().update_layout(
            title=f"{symbol} -- Zones ({timeframe}) -- no data",
            height=700, xaxis_rangeslider_visible=False
        )
        return dcc.Graph(figure=empty, style={"height": "700px"})
    
    # Normalize time → ET and make it NAIVE for Plotly/rangebreaks; do not trim rows
    ts_local = pd.to_datetime(df_c["ts"], errors="coerce").dt.tz_localize("America/Chicago")
    ts_et = ts_local.dt.tz_convert(TZ)
    ts_plot = ts_et.dt.tz_localize(None)
    df_c = df_c.assign(_ts_plot=ts_plot, _et_date=ts_plot.dt.date)  # _et_date only for debug/stats

    # Integer x positions (zero-based). Prefer global_x when available.
    if "global_x" in df_c and df_c["global_x"].notna().any():
        first_gx = int(df_c["global_x"].dropna().iloc[0])
        x_int = (df_c["global_x"].ffill().bfill() - first_gx).astype(int)
    else:
        x_int = pd.Series(range(len(df_c)), index=df_c.index)
    df_c = df_c.assign(_x_int=x_int)

    # Map original global_x -> integer x for object alignment
    gx_map = (
        df_c.dropna(subset=["global_x", "_x_int"])
            .drop_duplicates("global_x")
            .set_index("global_x")["_x_int"]
    )

    # 4) Candles
    # Use naive ET timestamps so rangebreaks don’t remove midday bars
    hovertext = [
        f"{ts:%b %d %Y %H:%M}<br>O {o}<br>H {h}<br>L {l}<br>C {c}"
        for ts, o, h, l, c in zip(df_c["_ts_plot"], df_c["open"], df_c["high"], df_c["low"], df_c["close"])
    ]
    fig = go.Figure(go.Candlestick(
        x=df_c["_x_int"],
        open=df_c["open"], high=df_c["high"], low=df_c["low"], close=df_c["close"],
        increasing_line_color=GREEN, decreasing_line_color=RED,
        increasing_fillcolor=GREEN, decreasing_fillcolor=RED,
        hovertext=hovertext,
        hoverinfo="text",
        name="Price",
    ))

    # 5) Remove gaps + add day stripes + overlay objects
    _add_day_bands(fig, df_c["_x_int"], df_c["_et_date"])
    draw_objects(fig, df_o, df_c, _tf_minutes(timeframe), variant="zones", gx_ts_override=gx_map)

    # Integer axis with date ticks at the first bar of each day
    day_ticks = df_c.groupby("_et_date")["_x_int"].first()
    fig.update_xaxes(
        type="linear",
        tickmode="array",
        tickvals=day_ticks.values,
        ticktext=pd.to_datetime(day_ticks.index).strftime("%b %d"),
        showgrid=False,
    )
    
    # 6) Layout polish
    apply_layout(fig, title=f"{symbol} -- Historical ({timeframe.upper()})", uirevision="zones")

    return dcc.Graph(figure=fig, style={"height": "700px"})
