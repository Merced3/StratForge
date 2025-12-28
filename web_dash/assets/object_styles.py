# web_dash/assets/object_styles.py
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import pandas as pd

# ---- Styles loader ---------------------------------------------------------

CONFIG_PATH = Path(__file__).with_name("object_styles.json")

@dataclass(frozen=True)
class _Style:
    line: str
    fill: str
    level_opacity: float
    zone_opacity: float
    level_width: float

class _Styles:
    def __init__(self, cfg: Dict[str, Any], variant: str):
        default = cfg.get("default", {})
        variant_cfg = cfg.get("variants", {}).get(variant, {})
        self._types = cfg.get("types", {})
        self._base = {
            "line": default.get("line", "#6b7280"),
            "fill": default.get("fill", "#94a3b8"),
            "level_opacity": default.get("level_opacity", 0.7),
            "zone_opacity": variant_cfg.get("zone_opacity", default.get("zone_opacity", 0.12)),
            "level_width": variant_cfg.get("level_width", 1.0),
        }

    def for_type(self, obj_type: str | None) -> _Style:
        tcfg = self._types.get(str(obj_type), {})
        merged = {**self._base, **tcfg}
        return _Style(**merged)

@lru_cache(maxsize=16)
def load_object_styles(variant: str = "zones") -> _Styles:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return _Styles(cfg, variant)

# ---- global_x → timestamp helpers + drawing -------------------------------

def _gx_lookup(df_c: pd.DataFrame) -> pd.Series:
    """Return Series indexed by global_x with _ts_plot as values."""
    if "global_x" not in df_c or df_c["global_x"].isna().all():
        return pd.Series(dtype="datetime64[ns]")
    return (
        df_c.dropna(subset=["global_x"])
            .drop_duplicates("global_x")
            .set_index("global_x")["_ts_plot"]
    )

def _start_ts_from_left(gx_ts: pd.Series, left):
    if gx_ts.empty or pd.isna(left):
        return None
    idx = gx_ts.index.to_numpy()
    pos = idx.searchsorted(int(left), side="left")
    if pos >= len(idx):
        return None
    return gx_ts.iloc[pos]

def draw_objects(fig, df_o: pd.DataFrame, df_c: pd.DataFrame, tf_minutes: int, variant: str = "zones", gx_ts_override=None):
    """
    Draws levels/zones using object 'left' aligned to candle global_x.
    df_c must have '_ts_plot' and (ideally) 'global_x'.
    If gx_ts_override is provided, use that mapping instead of df_c.
    """
    if df_o.empty:
        return
    
    styles = load_object_styles(variant)

    if variant == "live":
        if df_c.empty or "_ts_plot" not in df_c:
            return
        start_ts = df_c["_ts_plot"].iloc[0]
        end_ts = df_c["_ts_plot"].iloc[-1] + pd.Timedelta(minutes=tf_minutes)
    else:
        gx_ts = gx_ts_override if gx_ts_override is not None else _gx_lookup(df_c)
        if gx_ts.empty or df_c.empty:
            return
        is_numeric = pd.api.types.is_numeric_dtype(gx_ts)
        start_ts = None  # per-object via `_start_ts_from_left()`
        end_ts = (float(gx_ts.max()) + 1.0) if is_numeric else df_c["_ts_plot"].iloc[-1] + pd.Timedelta(minutes=tf_minutes)

    for _, obj in df_o.iterrows():
        if variant == "live":
            start = start_ts
        else:
            start = _start_ts_from_left(gx_ts, obj.get("left"))
        
        if start is None or end_ts is None:
            continue  # object starts outside this viewport

        st = styles.for_type(obj.get("type"))
        if pd.notna(obj.get("y")):
            y = float(obj["y"])
            fig.add_shape(type="line", x0=start, x1=end_ts, y0=y, y1=y,
                          xref="x", yref="y", line=dict(color=st.line, width=st.level_width),
                          layer="above")
            fig.add_scatter(x=[start], y=[y], mode="markers",
                            marker=dict(size=6, color=st.line), showlegend=False, hoverinfo="skip")
        elif pd.notna(obj.get("top")) and pd.notna(obj.get("bottom")):
            y0, y1 = sorted([float(obj["top"]), float(obj["bottom"])])
            fig.add_shape(type="rect", x0=start, x1=end_ts, y0=y0, y1=y1,
                          xref="x", yref="y", line=dict(width=0),
                          fillcolor=st.fill, opacity=st.zone_opacity, layer="below")
