# objects.py
from __future__ import annotations
import argparse
from typing import Optional
import pandas as pd
from shared_state import print_log
import asyncio
from pathlib import Path
from datetime import datetime
from utils.data_utils import get_dates
from utils.json_utils import read_config
from pathlib import Path
from paths import pretty_path, TIMELINE_OBJECTS_DIR, DATA_DIR, CURRENT_OBJECTS_PATH
from storage.objects.io import (      # Parquet-backed storage helpers
    append_timeline_events,
    upsert_current_objects,
    _enforce_schema,
    write_current_objects,
    load_current_objects
)
from tools.audit_candles import _get_nyse_session_bounds, _read_day_ts_series, _find_missing_intervals
from tools.candles_io import create_daily_15m_parquet

# What zones mean:
# 🔁 Support = “Too few sellers to push lower”
# 🔁 Resistance = “Too few buyers to push higher”

_display_cache = {"current": 0, "objects": []}  # Global cache to track current step & objects

# ───🔸 CORE DAY PROCESSING ───────────────────────────────────────────────

def _process_one_day(day_df: pd.DataFrame,
                     day_ts: pd.Timestamp,
                     global_offset: int,
                     all_zone_objects: list,
                     all_lvl_objects: list) -> tuple[list, list]:
    """
    Process ONE trading day and update timeline/snapshot via add_timeline_step()
    using your existing primitives. Returns updated (all_zone_objects, all_lvl_objects).
    """
    if day_df.empty:
        return all_zone_objects, all_lvl_objects

    current_day = day_df.index[0].normalize()
    day_range = day_df["high"].max() - day_df["low"].min()

    info = read_day_candles_and_distribute(day_df, current_day, global_offset)
    new_levels = get_levels(info["high_pos"], info["low_pos"], ts=day_ts)
    print_log(f"\n[{current_day.date()} (id, lvl)] "
              f"{new_levels[0]['type']}: ({new_levels[0]['id']}, {new_levels[0]['y']}) | "
              f"{new_levels[1]['type']}: ({new_levels[1]['id']}, {new_levels[1]['y']})")

    # Structures -> timeline only (snapshot disabled in add_timeline_step call)
    get_structures(info['structures'], save_to_steps=False, ts=day_ts)

    # Validate previous objects against today's new levels
    zone_to_remove, lvl_to_remove = validate_intraday_zones_lvls(all_zone_objects, all_lvl_objects, new_levels, ts=day_ts)
    if zone_to_remove:
        keep = {z['id'] for z in zone_to_remove}
        all_zone_objects = [z for z in all_zone_objects if z['id'] not in keep]
    if lvl_to_remove:
        keep = {l['id'] for l in lvl_to_remove}
        all_lvl_objects = [l for l in all_lvl_objects if l['id'] not in keep]

    # Build today’s zones and append to global sets
    today_zones = build_zones(new_levels, info['structures'], day_range, info['starter_zone_data'], ts=day_ts)
    all_zone_objects.extend(today_zones)
    all_lvl_objects.extend(new_levels)

    return all_zone_objects, all_lvl_objects

def read_day_candles_and_distribute(candle_data, current_date, global_offset=0, rolling_window=3):
    """
    Reads all candles ONCE and distributes data to all downstream functions 
    like get_levels(), get_structures(), etc. This optimizes performance and 
    ensures consistent offset-adjusted indexing.
    """

    # === Filter for Current Day ===
    day_data = candle_data[candle_data.index.normalize() == current_date]
    if day_data.empty:
        return []
    
    # === High & Low of Day (Levels) ===
    high_y = day_data["high"].max()
    low_y = day_data["low"].min()
    high_idx = day_data["high"].idxmax()
    low_idx = day_data["low"].idxmin()
    high_x = candle_data.index.get_loc(high_idx) + global_offset
    low_x = candle_data.index.get_loc(low_idx) + global_offset

    # === Body Tops & Bottoms (for swing detection) ===
    bodies_top = day_data[['open', 'close']].max(axis=1).tolist()
    bodies_bot = day_data[['open', 'close']].min(axis=1).tolist()

    swing_highs = []
    swing_lows = []

    for i in range(rolling_window, len(day_data) - rolling_window):
        is_swing_high = all(
            bodies_top[i] > bodies_top[i - j] and bodies_top[i] > bodies_top[i + j]
            for j in range(1, rolling_window + 1)
        )
        is_swing_low = all(
            bodies_bot[i] < bodies_bot[i - j] and bodies_bot[i] < bodies_bot[i + j]
            for j in range(1, rolling_window + 1)
        )
        if is_swing_high:
            swing_highs.append((i + global_offset, bodies_top[i]))
        if is_swing_low:
            swing_lows.append((i + global_offset, bodies_bot[i]))

    # === Close Trend Line ===
    closes = day_data["close"].tolist()
    trend_line = [
        (global_offset, closes[0]),
        (global_offset + len(closes) - 1, closes[-1])
    ]

    # === Candle Body Tops/Bottoms for Starter Zone Logic ===
    wick_ranges = []
    body_positions = []
    hbc = [None, None]  # Highest Bottom Candle (X, Y)
    ltc = [None, None]  # Lowest Top Candle (X, Y)

    for local_index, (_, candle) in enumerate(day_data.iterrows()):
        c_global_index = local_index + global_offset
        body_top = max(candle.open, candle.close)
        body_bot = min(candle.open, candle.close)

        # Save all body pairs
        body_positions.append((c_global_index, body_top, body_bot))

        # Save for wick-based structure detection
        wick_ranges.append({
            "top": body_top,
            "bottom": body_bot,
            "high": candle.high,
            "low": candle.low,
        })
        
        # Update HBC
        if hbc[1] is None or body_bot > hbc[1]:
            hbc = [c_global_index, body_bot]

        # Update LTC
        if ltc[1] is None or body_top < ltc[1]:
            ltc = [c_global_index, body_top]
    
    return {
        "high_pos": [high_x, high_y],
        "low_pos": [low_x, low_y],
        "structures": {
            "swings_high": swing_highs,
            "swings_low": swing_lows,
            "trendline": trend_line,
        },
        "wick_ranges": wick_ranges,
        "starter_zone_data": {
            "body_candle_positions": body_positions,
            "hbc": hbc,
            "ltc": ltc
        },
        "raw_day_data": day_data.reset_index(drop=False),  # This is a 'just in case' thing.
    }

# ───🔸 TOP-LEVEL WORKFLOWS ───────────────────────────────────────────────

def update_timeline_with_objects(limit_days: Optional[int] = None,
                                 newest_first: bool = True):
    """
    Backfill objects by scanning 15m day parquet files.
    limit_days: if set, only process that many days.
      - newest_first=True  -> take the N most recent days
      - newest_first=False -> take the earliest N days
    """
    tf_dir = DATA_DIR / "15m"
    day_files = sorted(tf_dir.glob("*.parquet"), key=lambda p: p.stem)
    if not day_files:
        print_log("[ERROR] No 15m day Parquet files found.")
        return
    
    # limit which days we run
    if limit_days is not None and limit_days > 0:
        day_files = (day_files[-limit_days:] if newest_first else day_files[:limit_days])

    all_lvl_objects, all_zone_objects = [], []
    global_offset = 0

    for p in day_files:
        df_day = pd.read_parquet(
            p, columns=["ts","open","close","high","low","global_x"]
        ).sort_values("ts")

        # 🔧 Normalize ts (epoch ms OR ISO-with-tz → UTC pandas Timestamp)
        ts_col = df_day["ts"]
        if pd.api.types.is_integer_dtype(ts_col) or pd.api.types.is_float_dtype(ts_col):
            # epoch ms → UTC
            df_day["ts"] = pd.to_datetime(ts_col, unit="ms", utc=True)
        else:
            # strings / datetime-like → UTC
            df_day["ts"] = pd.to_datetime(ts_col, utc=True)

        # 🔧 The file name is the most robust source of the trading day
        day_str = p.stem                               # e.g. "2020-05-26"
        day_ts  = pd.to_datetime(day_str).tz_localize("UTC")

        # (optional) sanity if you like:
        # assert df_day["ts"].dt.normalize().nunique() == 1, "dayfile spans multiple days?"
        # Maybe, will keep it here just incase.
        
        # Make an index like your CSV path expects
        day_df = df_day.rename(columns={"ts": "timestamp"}).copy()
        day_df["timestamp"] = pd.to_datetime(day_df["timestamp"])
        day_df.set_index("timestamp", inplace=True)

        # Use the day’s real global start (fast, accurate)
        if "global_x" in df_day.columns and not df_day.empty:
            global_offset = int(df_day["global_x"].min())

        all_zone_objects, all_lvl_objects = _process_one_day(
            day_df, day_ts, global_offset, all_zone_objects, all_lvl_objects
        )

def process_end_of_day_15m_candles_for_objects() -> None:
    """
    Runs after end_of_day_compaction().
    Loads the latest 15m day Parquet, derives day_ts + global_offset,
    and processes exactly one trading day into timeline + current snapshot.
    """
    try:
        tf_dir = DATA_DIR / "15m"
        day_files = sorted(tf_dir.glob("*.parquet"), key=lambda p: p.stem)
        if not day_files:
            print_log("[EOD] No 15m day Parquet files found.")
            return

        latest_path = day_files[-1]                  # e.g. .../15m/2025-09-23.parquet
        day_str = latest_path.stem                   # "2025-09-23"
        day_ts  = pd.to_datetime(day_str).tz_localize("UTC")

        # Read only what we need; `global_x` gives us the exact global offset
        cols = ["ts", "open", "high", "low", "close", "global_x"]
        df_day = pd.read_parquet(latest_path, columns=cols).sort_values("ts")

        # Normalize ts → UTC pandas datetime (handles int64 ms or string ISO)
        ts_col = df_day["ts"]
        if pd.api.types.is_integer_dtype(ts_col) or pd.api.types.is_float_dtype(ts_col):
            df_day["ts"] = pd.to_datetime(ts_col, unit="ms", utc=True)
        else:
            df_day["ts"] = pd.to_datetime(ts_col, utc=True)

        # Index + shape expected by your downstream pipeline
        day_df = df_day.rename(columns={"ts": "timestamp"}).copy()
        day_df.set_index("timestamp", inplace=True)

        if day_df.empty:
            print_log("[EOD] Latest 15m dayfile is empty — skipping.")
            return

        # Use true global offset from the Parquet (added during compaction)
        if "global_x" in df_day.columns and not df_day.empty:
            global_offset = int(df_day["global_x"].min())
        else:
            # Fallback (shouldn’t normally happen after compaction)
            global_offset = 0
    
        # Load current snapshot → pass into one-day processor
        prev_zones, prev_lvls = get_objects()
        _process_one_day(day_df, day_ts, global_offset, prev_zones, prev_lvls)
        
        print_log(f"[EOD] Objects processed for {day_str} (offset={global_offset}).")
    except Exception as e:
        print_log(f"[EOD] Error: {e}")

# ───🔸 OBJECT GENERATION ─────────────────────────────────────────────────

def get_structures(structures, save_to_steps=False, ts=None):
    
    if save_to_steps:
        serial = _next_object_serial_from_parquet()

        # Save to timeline as "structure" action
        structure_objects = []
        for s_type, points in structures.items():
            if not points:
                continue
            structure_objects.append({
                "id": f"{serial:05d}",
                "type": "structure",
                "subtype": s_type,
                "points": points  # list of (x, y)
            })
            serial+=1

        add_timeline_step(structure_objects, "create", "Extracted basic structure (swings, trend)", ts=ts)

def get_levels(high_pos, low_pos, ts=None):
    # Create two level objects
    levels = [
        {"type": "resistance", "left": high_pos[0], "y": high_pos[1]},
        {"type": "support", "left": low_pos[0], "y": low_pos[1]}
    ]
    levels = create_level_objects(levels)

    add_timeline_step(levels, "create", "Logged raw daily high/low levels", ts=ts)
    return levels

def create_level_objects(levels):
    """Returns a object list (2) with appended levels. The levels are the highest high and lowest low of the day."""
    serial = _next_object_serial_from_parquet()

    # Handle single dictionary
    if isinstance(levels, dict):
        levels = [levels]

    # Defensive: not a list of dicts = crash early
    if not isinstance(levels, list) or not all(isinstance(lvl, dict) for lvl in levels):
        raise ValueError("`levels` must be a dict or a list of dicts")

    lvl_list = []
    for lvl in levels:
        lvl_obj = {
            "id": f"{serial:05d}",
            "type": lvl["type"],
            "left": lvl["left"],
            "y": lvl["y"],
        }
        serial += 1
        lvl_list.append(lvl_obj)

    # Return single object if input was a dict
    return lvl_list[0] if len(lvl_list) == 1 else lvl_list

def build_zones(new_levels, structures, day_range, starter_zone_data, ts=None):
    zones = []

    resistance_level_y = next((lvl['y'] for lvl in new_levels if 'resistance' in lvl['type']), None)
    support_level_y = next((lvl['y'] for lvl in new_levels if 'support' in lvl['type']), None)

    hbc = starter_zone_data["hbc"] # Highest Bottom Candle, either min('open' or 'close'), but its the highest out of them all, formated (X, Y)
    ltc = starter_zone_data["ltc"] # Lowest Top Candle, either max('open' or 'close'), but its the lowest one out of them all, formated (X, Y)
    body_top_bottom_pairs = starter_zone_data["body_candle_positions"]

    # Fill top/bottom arrays
    all_c_body_tops = [(x, top) for x, top, _ in body_top_bottom_pairs]
    all_c_body_bottoms = [(x, bot) for x, _, bot in body_top_bottom_pairs]

    # NOW filter
    filtered_top_bodies = [(x, y) for x, y in all_c_body_tops if y > hbc[1]] # if candle in list isn't above the highest bottom body candle value, remove it.
    filtered_top_bodies.append(hbc) # Optional
    filtered_bottom_bodies = [(x, y) for x, y in all_c_body_bottoms if y < ltc[1]] # if candle in list isn't below the lowest top body candle value, remove it.
    filtered_bottom_bodies.append(ltc) # Optional

    RB_XY = None # Resistance Bottom (X, Y)
    ST_XY = None # Support Top (X, Y)
    percent_threshold = [0.06, 0.30] # aka 6% and 30%, possible overfitting but its fine.
    r_message = None
    s_message = None

    # RESISTANCE
    if structures["swings_high"]: # 'structural' mode
        RB_XY = max(structures['swings_high'], key=lambda x: x[1]) # current highest anchor
        anchor_level_dist_ratio = abs(RB_XY[1] - resistance_level_y) / day_range
        
        if not (percent_threshold[0] <= anchor_level_dist_ratio <= percent_threshold[1]): # 'body based' mode, Just incase: or highest_body_top[1] > RB_XY[1]
            RB_XY = min(filtered_top_bodies, key=lambda x: x[1]) if filtered_top_bodies else hbc
            r_message = f"Body-Based Mode: {RB_XY} (SVF) Size: {anchor_level_dist_ratio:.3f}" # SVF = Switched, Validation Failed
        else:
            r_message = f"Structural Mode: {RB_XY} | Size: {anchor_level_dist_ratio:.3f}"
    elif not structures["swings_high"]: # 'body based' mode
        RB_XY = min(filtered_top_bodies, key=lambda x: x[1]) if filtered_top_bodies else hbc
        r_message = f"Body Based Mode: {RB_XY}"
    print_log(f"[RESISTANCE ZONE BOTTOM] {r_message}")
    
    # SUPPORT
    if structures["swings_low"]: # 'structural' mode
        ST_XY = min(structures["swings_low"], key=lambda x: x[1])
        anchor_level_dist_ratio = abs(ST_XY[1] - support_level_y) / day_range
        
        if not (percent_threshold[0] <= anchor_level_dist_ratio <= percent_threshold[1]): # 'body based' mode, Just incase:  or lowest_body_bot[1] < ST_XY[1]
            ST_XY = max(filtered_bottom_bodies, key=lambda x: x[1]) if filtered_bottom_bodies else ltc
            s_message = f"Body-Based Mode: {ST_XY} (SVF) Size: {anchor_level_dist_ratio:.3f}" # SVF = Switched, Validation Failed
        else:
            s_message = f"Structural Mode: {ST_XY} | Size: {anchor_level_dist_ratio:.3f}"
    elif not structures["swings_low"]: # 'body based' mode
        ST_XY = max(filtered_bottom_bodies, key=lambda x: x[1]) if filtered_bottom_bodies else ltc
        s_message = f"Body Based Mode: {ST_XY}"
    print_log(f"[   SUPPORT ZONE TOP   ] {s_message}") # spaces are to match up with the '[RESISTANCE ZONE BOTTOM]' looks better in terminal
        
    # Create Zones
    for lvl in new_levels:
        candle_zone_index = ST_XY[0] if "support" in lvl['type'] else RB_XY[0]
        candle_top_or_bottom = ST_XY[1] if "support" in lvl['type'] else RB_XY[1]
        zones.append({
            "type": lvl['type'],
            "left": min(lvl["left"], candle_zone_index),
            "top": lvl["y"] if "resistance" in lvl['type'] else candle_top_or_bottom,
            "bottom": lvl["y"] if "support" in lvl['type'] else candle_top_or_bottom,
        })

    zone_objects = create_zone_objects(zones)
    add_timeline_step(zone_objects, "create", "Created zone from wick ranges + daily high/low", ts=ts)

    return zone_objects

def create_zone_objects(zones):
    """Returns a object list with appended zones, works weather you have one zone or muliple"""
    
    serial = _next_object_serial_from_parquet()

    object_list = []
    for zone in zones:
        entry = {
            "id": f"{serial:05d}",
            "type": zone["type"],
            "left": zone["left"],
            "top": zone["top"],
            "bottom": zone["bottom"]
        }
        serial += 1
        object_list.append(entry)
    return object_list

def validate_intraday_zones_lvls(all_zones, all_lvls, new_levels, ts=None):
    delete_ids = []
    delete_id_set = set()
    log_origin = "VIZL" # Validate Intraday Zones Levels
    
    print_log(f"[{log_origin}] Starting with {len(all_zones)} zones and {len(all_lvls)} levels")

    if not new_levels:
        print_log(f"[{log_origin}] No new levels provided — skipping validation.")
        return [], []

    level_high = max(lvl['y'] for lvl in new_levels if lvl['type'] == 'resistance')
    level_low = min(lvl['y'] for lvl in new_levels if lvl['type'] == 'support')
    
    # === ZONE VALIDATION ===
    for zone in all_zones:
        if zone['id'] in delete_id_set:
            continue
        z_top = float(zone.get('top', float('-inf')))
        z_bot = float(zone.get('bottom', float('inf')))

        # Entire day range inside zone
        if level_high <= z_top and level_low >= z_bot:
            delete_ids.append((zone['id'], "Zone Encompasses Day Range"))
            delete_id_set.add(zone['id'])

        # Zone fully inside new intraday range
        elif z_top <= level_high and z_bot >= level_low:
            delete_ids.append((zone['id'], "Zone Inbetween IntraDay"))
            delete_id_set.add(zone['id'])

        # Partial overlap
        elif (level_high >= z_top >= level_low) or (level_high >= z_bot >= level_low):
            delete_ids.append((zone['id'], "Zone Overlap's IntraDay"))
            delete_id_set.add(zone['id'])

    # === LEVEL VALIDATION ===
    for lvl in all_lvls:
        if lvl['id'] in delete_id_set:
            continue
        y = lvl["y"]
        if level_low <= y <= level_high:
            delete_ids.append((lvl["id"], "Level Inbetween IntraDay"))
            delete_id_set.add(lvl["id"])
    
    if delete_ids:
        log_object_removal(delete_ids, reason="Removed from `validate_intraday_zones()`", ts=ts)

    zones_to_remove = [z for z in all_zones if z['id'] in delete_id_set]
    lvls_to_remove = [l for l in all_lvls if l['id'] in delete_id_set]
    return zones_to_remove, lvls_to_remove  # ✅ Only the bad ones

# ───🔸 STORAGE BRIDGE (PARQUET) ──────────────────────────────────────────

def add_timeline_step(objects, action, reason, *, ts=None, write_snapshot=True):
    ts = pd.to_datetime(ts) if ts is not None else datetime.utcnow()

    # derive the trading day (UTC date or use market tz if you want)
    day_str = ts.strftime("%Y-%m-%d")

    # compute next day_step from that day's parquet only
    day_file = (TIMELINE_OBJECTS_DIR / day_str[:7] / f"{day_str}.parquet")
    if day_file.exists():
        try:
            last = pd.read_parquet(day_file, columns=["day_step"])["day_step"].max()
            day_step = int(last) + 1 if pd.notna(last) else 1
        except Exception:
            day_step = 1
    else:
        day_step = 1
        
    symbol = read_config('SYMBOL') # So that we don't have to read config a bunch of times.
    rows = []
    for obj in (objects if isinstance(objects, list) else [objects]):
        status = obj.get("status") or "active" if action == "create" else obj.get("status")
        rows.append({
            "day_step": day_step,
            "ts": ts,
            "action": action,
            "reason": reason,
            "object_id": obj.get("id"),
            "type": obj.get("type"),
            # Use your object’s x as global_x (or pass explicit global_x if you prefer)
            "global_x": obj.get("global_x", obj.get("left")),
            "left": obj.get("left"),
            "y": obj.get("y"),
            "top": obj.get("top"),
            "bottom": obj.get("bottom"),
            "status": status,
            "individual_reason": obj.get("individual_reason"),
            "symbol": symbol,
            "timeframe": "15m",
        })
    
    if rows:
        append_timeline_events(pd.DataFrame(rows))              # writes to timeline/YYYY-MM/DD.parquet
        if write_snapshot:
            upsert_current_objects(pd.DataFrame(rows).rename(columns={"object_id": "id"}))

def log_object_removal(object_ids_with_reason, reason="removal", ts=None):
    objects = [{"id": oid, "status": "removed", "individual_reason": why} for oid, why in object_ids_with_reason]
    add_timeline_step(objects, "remove", reason, ts=ts) # Will i get any errors here?

def _next_object_serial_from_parquet() -> int:
    """Read current snapshot and return next numeric id (max + 1)."""
    try:
        df = load_current_objects(columns=["id"])
        if not df.empty:
            as_int = pd.to_numeric(df["id"], errors="coerce")
            mx = int(as_int.dropna().max()) if not as_int.isna().all() else 0
            return mx + 1
    except Exception:
        pass
    return 1

def rebuild_snapshot_from_timeline(
    *,
    max_step: Optional[int] = None,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    keep_removed: Optional[bool] = False,
    dry_run: Optional[bool] = False,
):
    parts = sorted(Path(TIMELINE_OBJECTS_DIR).rglob("*.parquet"))
    if not parts:
        print(f"[rebuild] No timeline parquet files under {TIMELINE_OBJECTS_DIR}")
        return None

    tdfs = []
    for p in parts:
        df = pd.read_parquet(p)
        if "step" not in df.columns and "day_step" in df.columns:
            df = df.rename(columns={"day_step": "step"})
        if "step" not in df.columns:
            continue
        df["step"] = pd.to_numeric(df["step"], errors="coerce")
        df = df[df["step"].notna()]
        if max_step is not None:
            df = df[df["step"] <= max_step]
        if symbol:
            df = df[df.get("symbol") == symbol]
        if timeframe:
            df = df[df.get("timeframe") == timeframe]
        if not df.empty:
            tdfs.append(df)

    if not tdfs:
        print("[rebuild] No timeline rows after filtering")
        return None

    tl = pd.concat(tdfs, ignore_index=True)
    if "ts" in tl.columns:
        tl["ts"] = pd.to_datetime(tl["ts"], errors="coerce")

    # Normalize missing status on remove actions so pruning works
    if "action" in tl.columns and "status" in tl.columns:
        tl.loc[(tl["action"] == "remove") & tl["status"].isna(), "status"] = "removed"

    # Sort chronologically so the last event per object is the newest even when day_step resets daily
    if "ts" in tl.columns:
        tl = tl.sort_values(["object_id", "ts", "step"])
    else:
        tl = tl.sort_values(["object_id", "step"])

    keep_cols = [
        "object_id","type","left","y","top","bottom","status",
        "symbol","timeframe","created_ts","updated_ts","created_step","updated_step"
    ]
    keep_cols = [c for c in keep_cols if c in tl.columns]
    snap = (
        tl[keep_cols + ["step"]]
        .groupby("object_id", sort=False)
        .last()
        .reset_index()
        .rename(columns={"object_id": "id"})
    )

    if not keep_removed and "status" in snap.columns:
        snap = snap[snap["status"].fillna("active") != "removed"]

    snap = _enforce_schema(snap)

    if dry_run:
        print(f"[DRY RUN] would write {len(snap)} rows to `{pretty_path(CURRENT_OBJECTS_PATH)}`")
        return snap

    write_current_objects(snap)
    print(f"[rebuild] wrote {len(snap)} rows to `{pretty_path(CURRENT_OBJECTS_PATH)}`")
    return snap
# ───🔸 EXTERNAL HELPERS / UI HOOKS ───────────────────────────────────────

def get_objects():
    """
    Returns (zones, levels) from the *Parquet snapshot* if present,
    otherwise falls back to objects.json (legacy).
    """
    symbol = read_config('SYMBOL')

    try:
        cols = ["id","type","left","y","top","bottom","status","symbol","timeframe"]
        df = load_current_objects(columns=cols)
        if not df.empty:
            # normalize / filter
            df = df[(df["symbol"] == symbol) & (df["timeframe"] == "15m")]
            df = df[df["status"].fillna("active") != "removed"]

            zones, levels = [], []
            for r in df.itertuples(index=False):
                row = dict(zip(cols, r))
                if pd.notna(row.get("y")):
                    levels.append({
                        "id": row["id"], "type": row["type"],
                        "left": int(row["left"]), "y": float(row["y"]),
                    })
                elif pd.notna(row.get("top")) and pd.notna(row.get("bottom")):
                    zones.append({
                        "id": row["id"], "type": row["type"],
                        "left": int(row["left"]),
                        "top": float(row["top"]), "bottom": float(row["bottom"]),
                    })
            return zones, levels
    except Exception:
        pass
    return [], []   # <- ensure callers always get two lists

def _rebuild_current_snapshot_asof_day(cutoff_day: str) -> None:
    """
    Rebuild CURRENT snapshot from all timeline files with YYYY-MM-DD <= cutoff_day.
    Ignores 'step' vs 'day_step' and uses time ordering to pick each object's last state.
    """
    # collect all timeline parts up to cutoff day
    parts = [p for p in TIMELINE_OBJECTS_DIR.rglob("*.parquet") if p.stem <= cutoff_day]
    if not parts:
        # write empty snapshot
        write_current_objects(pd.DataFrame(columns=[
            "id","type","left","y","top","bottom","status","symbol","timeframe",
            "created_ts","updated_ts","created_step","updated_step"
        ]))
        print_log(f"[HEAL] No timeline <= {cutoff_day}; wrote empty current snapshot.")
        return

    cols_keep = [
        "object_id","type","left","y","top","bottom","status","symbol","timeframe",
        "ts","created_ts","updated_ts","created_step","updated_step",
        "day_step","step"
    ]
    tdfs = []
    for p in sorted(parts):
        try:
            df = pd.read_parquet(p)
            # keep only known columns but tolerate missing ones
            for c in cols_keep:
                if c not in df.columns:
                    df[c] = pd.NA
            df = df[cols_keep]

            # normalize types
            df["ts"] = (pd.to_datetime(df["ts"], utc=True, errors="coerce")
                        .fillna(pd.NaT))
            for c in ["left","y","top","bottom","created_ts","updated_ts",
                      "created_step","updated_step","day_step","step"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df["object_id"] = df["object_id"].astype("string")

            # prefer explicit symbol/timeframe, fill if missing
            sym = read_config("SYMBOL")
            df["symbol"] = df["symbol"].astype("string").fillna(sym)
            df["timeframe"] = df["timeframe"].astype("string").fillna("15m")

            tdfs.append(df)
        except Exception as e:
            print_log(f"[HEAL] Skipping timeline part {pretty_path(p)}: {e}")

    if not tdfs:
        write_current_objects(pd.DataFrame(columns=[
            "id","type","left","y","top","bottom","status","symbol","timeframe",
            "created_ts","updated_ts","created_step","updated_step"
        ]))
        print_log(f"[HEAL] No readable timeline <= {cutoff_day}; wrote empty current snapshot.")
        return

    tl = pd.concat(tdfs, ignore_index=True)

    # ordering: by ts, then by per-day step (whichever exists), then by object_id
    step_col = "day_step" if "day_step" in tl.columns else "step"
    if step_col not in tl.columns:
        tl[step_col] = pd.NA
    tl = tl.sort_values(["object_id", "ts", step_col]).reset_index(drop=True)

    # final state per object up to cutoff_day, # do NOT aggregate 'object_id' itself; it’s the group key
    keep_cols = ["type","left","y","top","bottom","status","symbol",
             "timeframe","created_ts","updated_ts","created_step","updated_step"]

    snap = (tl.groupby("object_id")[keep_cols]
            .last()
            .reset_index()
            .rename(columns={"object_id": "id"}))

    # drop removed
    if "status" in snap.columns:
        snap = snap[snap["status"].fillna("active") != "removed"]

    write_current_objects(snap)
    print_log(f"[HEAL] Rebuilt current snapshot from timeline ≤ {cutoff_day} "
              f"with {len(snap)} active objects.")

def _clean_day_state(day_str: str) -> None:
    """
    Remove today's broken artifacts and rebuild current snapshot as-of the day before.
    """
    # 1) remove today's 15m parquet
    day_path = DATA_DIR / "15m" / f"{day_str}.parquet"
    if day_path.exists():
        try:
            day_path.unlink()
            print_log(f"[HEAL] Deleted bad 15m dayfile → {pretty_path(day_path)}")
        except Exception as e:
            print_log(f"[HEAL] Could not delete {pretty_path(day_path)}: {e}")

    # 2) remove today's timeline file
    tl_path = TIMELINE_OBJECTS_DIR / day_str[:7] / f"{day_str}.parquet"
    if tl_path.exists():
        try:
            tl_path.unlink()
            print_log(f"[HEAL] Deleted timeline for {day_str} → {pretty_path(tl_path)}")
        except Exception as e:
            print_log(f"[HEAL] Could not delete {pretty_path(tl_path)}: {e}")

    # 3) rebuild current snapshot up to the previous day... i think
    prev_day = (pd.to_datetime(day_str) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        _rebuild_current_snapshot_asof_day(prev_day)
    except Exception as e:
        print_log(f"[HEAL] Snapshot rebuild error (continuing anyway): {e}")

async def pull_and_replace_15m(days_back: int = 1, day_override: Optional[str] = None):
    """
    Auto-heal for today's 15m data:
      1) Detect gaps in the latest trading day's 15m parquet
      2) If gaps/missing, clean today's artifacts and rebuild
      3) Re-pull dayfile from Polygon (create_daily_15m_parquet)
      4) Re-run EOD object processing
    """
    # Determine target day 
    if day_override:
        day_str = day_override
    else:
        _, day_str = get_dates(days_back, True) # latest trading day, e.g. ('2025-10-03', '2025-10-03')
    day_path = DATA_DIR / "15m" / f"{day_str}.parquet"

    print_log(f"[HEAL] Checking 15m data for target day: `{day_str}`")

    gaps = []
    missing = []
    extras = []
    session_open, session_close = _get_nyse_session_bounds(day_str)
    print_log(f"[HEAL] Expected NYSE session: {session_open} to {session_close}")
    if day_path.exists():
        ts_series = _read_day_ts_series(day_path)
        missing, extras = _find_missing_intervals(
            ts_series,
            step_minutes=15,
            expected_open=session_open,
            expected_close=session_close,
        )
        if extras:
            print_log(f"[HEAL] Found {len(extras)} out-of-session 15m bars (first={extras[0]}, last={extras[-1]})")
        gaps = missing + extras
    else:
        print_log(f"[HEAL] No dayfile for {day_str} — treating as missing.")
        gaps = [None]  # force repair

    if gaps:
        # 1) clean current-day artifacts (timeline + snapshot rewind + remove 15m dayfile)
        _clean_day_state(day_str)

        # 2) rebuild the 15m dayfile from Polygon
        await create_daily_15m_parquet(day_str)

        # 3) regenerate objects for the day from the fresh file
        process_end_of_day_15m_candles_for_objects()

        # 4) final sanity
        try:
            ts_series2 = _read_day_ts_series(day_path)
            post_missing, post_extras = _find_missing_intervals(
                ts_series2,
                step_minutes=15,
                expected_open=session_open,
                expected_close=session_close,
            )
            if post_missing or post_extras:
                print_log(f"[HEAL] WARN: Gaps after repair — missing={len(post_missing)}, extras={len(post_extras)}")
            else:
                print_log(f"[HEAL] Repair complete for {day_str} (no gaps).")
        except Exception:
            # If we can't read it here, the EOD step will surface issues
            pass
    else:
        print_log(f"[HEAL] {day_str} looks complete — no action needed.")

"""
HOW TO RUN & RECOVER (15m dayfiles, timeline, current snapshot)

EVERYDAY PROCESSING
- Process ALL days (full rebuild/backfill):
    `python objects.py`
- Process ONLY today’s dayfile (your EOD path):
    `python objects.py eod`
- Backfill the LATEST N days (quick catch-up; example shows 3):
    `python objects.py backfill --limit-days 3`
- Backfill the EARLIEST N days (smoke test from the start; example shows 5):
    `python objects.py backfill --limit-days 5 --oldest-first`

AUTO-HEAL A SPECIFIC DAY (bad/missing 15m candles → repair timeline/current)
- Recommended (explicit date; safest, esp. after midnight):
    `python objects.py pull-replace --day YYYY-MM-DD`
    Example:
    `python objects.py pull-replace --day 2025-10-20`
- Alternative (relative day; “latest trading day”):
    `python objects.py pull-replace --days-back 1`

WHAT “PULL-REPLACE” DOES

1. Reads `storage/data/15m/<DAY>.parquet` and checks 15-minute cadence in America/New_York time (half-days are OK).

2. If gaps/missing:
    - Deletes ONLY these two files for that exact DAY:
        storage/data/15m/<YYYY-MM-DD>.parquet
        storage/objects/timeline/<YYYY-MM>/<YYYY-MM-DD>.parquet
    - Rebuilds the CURRENT snapshot as-of the PREVIOUS day from your timeline history.
    - Re-pulls fresh 15m candles from Polygon and writes:
        storage/data/15m/<YYYY-MM-DD>.parquet
        (auto-normalized: ts=int64 epoch ms UTC, ts_iso=ISO8601 Z; volume forced to 0.0; global_x continued)
        Terminal: `python objects.py pull-replace --day YYYY-MM-DD`
    - Re-runs the normal EOD object processing for that day.
    - Re-checks cadence and logs “Repair complete … (no gaps)”.

3. Safety: it never touches any other days. Prefer --day YYYY-MM-DD to avoid ambiguity around midnight.

STANDALONE: REBUILD JUST A SINGLE 15m DAYFILE (no healer/EOD)
- Create the parquet only (keeps everything else untouched):
    `python objects.py create-dayfile --day YYYY-MM-DD`
  Example:
    `python objects.py create-dayfile --day 2025-10-20`
- Overwrite if a file already exists:
    `python objects.py create-dayfile --day 2025-10-20 --overwrite`
- After creating a dayfile, you can (optionally) run:
    `python objects.py eod`

OPTIONAL: NORMALIZE DAYFILES FROM THE CLI (one-off)
- Dry run (see what would change) for one day:
    `python tools/normalize_ts_all.py --root storage/data --timeframes 15m --pattern 2025-10-20.parquet --verbose --dry-run`
- Normalize that day for real:
    `python tools/normalize_ts_all.py --root storage/data --timeframes 15m --pattern 2025-10-20.parquet --verbose`
- Normalize EVERYTHING (slower):
    Dry run:
        `python tools/normalize_ts_all.py --root storage/data --recurse --verbose --dry-run`
    Do it:
        `python tools/normalize_ts_all.py --root storage/data --recurse --verbose`

NUCLEAR OPTION (full rebuild of timeline + current)
- Only if you truly want a clean slate. Remove all timeline files:
    (Windows PowerShell)
    Remove-Item -Recurse -Force .\storage\objects\timeline
- Remove current snapshot:
    Remove-Item -Force .\storage\objects\current.parquet
- Run full backfill:
    python objects.py

TIPS / NOTES
- Dayfiles are stored in UTC (ts epoch ms + ts_iso Z). We filter in America/New_York first, then write UTC to avoid DST ambiguity (daylight savings transitions, Fall-back and Spring-forward) and keep global_x/order consistent.
- After midnight, ALWAYS prefer: python objects.py pull-replace --day YYYY-MM-DD
- Volumes in 15m dayfiles are intentionally 0.0 to match historical format.
- Market open assumed 09:30 America/New_York; cadence check uses 15-minute steps, so half-days are handled naturally.
- The healer’s snapshot rebuild uses ALL timeline events up to the PREVIOUS day (no “step” pitfalls), then today’s EOD runs on top.
- create_daily_15m_parquet auto-normalizes the file (ts + ts_iso), sorts by ts, preserves schema, and continues global_x correctly.
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Objects backfill / EOD helpers")
    sub = parser.add_subparsers(dest="cmd")

    bf = sub.add_parser("backfill", help="Process multiple days of 15m parquet data")
    bf.add_argument("--limit-days", type=int, default=None, help="Only process this many days")
    bf.add_argument("--oldest-first", action="store_true", help="Process earliest N days instead of latest")

    eod = sub.add_parser("eod", help="Process only the most recent day")

    pr = sub.add_parser("pull-replace", help="Fetch 15m from Polygon and replace storage for that day")
    pr.add_argument("--days-back", type=int, default=1, help="How many days back to fetch (default 1)")
    pr.add_argument("--day", help="YYYY-MM-DD override for the day to heal")

    cd = sub.add_parser("create-dayfile", help="Create/replace one 15m parquet for a specific day (no EOD/healer)")
    cd.add_argument("--day", required=True, help="YYYY-MM-DD to fetch (e.g. 2025-10-20)")
    cd.add_argument("--overwrite", action="store_true", help="If set, delete existing dayfile before writing")

    rs = sub.add_parser("rebuild-snapshot", help="Rebuild current snapshot from timeline parquet files")
    rs.add_argument("--max-step", type=int, default=None, help="Optional inclusive step cutoff")
    rs.add_argument("--symbol", default=None, help="Optional symbol filter")
    rs.add_argument("--timeframe", default=None, help="Optional timeframe filter")
    rs.add_argument("--keep-removed", action="store_true", help="Keep rows with status=removed")
    rs.add_argument("--dry-run", action="store_true", help="Report only; do not write objects.parquet")

    args = parser.parse_args()

    if args.cmd == "backfill":
        update_timeline_with_objects(limit_days=args.limit_days, newest_first=not args.oldest_first)
    elif args.cmd == "eod":
        process_end_of_day_15m_candles_for_objects()
    elif args.cmd == "pull-replace":
        asyncio.run(pull_and_replace_15m(days_back=args.days_back, day_override=args.day))
    elif args.cmd == "rebuild-snapshot":
        rebuild_snapshot_from_timeline(
            max_step=args.max_step,
            symbol=args.symbol,
            timeframe=args.timeframe,
            keep_removed=args.keep_removed,
            dry_run=args.dry_run,
        )
    else:
        # default behavior (backfill everything)
        update_timeline_with_objects()
