# indicators/ema_manager.py
from shared_state import indent, print_log, safe_read_json, safe_write_json
from data_acquisition import get_candle_data_and_merge
from utils.json_utils import reset_json, initialize_json
from paths import (
    get_ema_path,
    AFTERMARKET_EMA_PATH,
    PREMARKET_EMA_PATH,
    MERGED_EMA_PATH,
    EMA_STATE_PATH,
)
from utils.file_utils import get_current_candle_index
from utils.ema_utils import calculate_save_EMAs
from datetime import datetime, timedelta, time
from utils.timezone import NY_TZ
import os

# -----------------------------
# Configuration
# -----------------------------
USE_JSON_STATE = True  # True = JSON-backed state; False = in-memory ephemeral
MARKET_OPEN = time(9, 30)

# -----------------------------
# State
# -----------------------------
# JSON schema: { "<TF>": { "candle_list": [candle,...], "has_calculated": bool } }
ema_state = safe_read_json(EMA_STATE_PATH, default={}) if USE_JSON_STATE else {}

# ---- Daily reset + schema migration helpers ----

def migrate_ema_state_schema():
    """
    Make whatever is in ema_state.json conform to our simple schema:
    per-TF: { "candle_list": [], "has_calculated": bool }
    - Drop any legacy keys like 'seen_ts'
    - Create missing keys with safe defaults
    - Persist the cleaned structure
    """
    global ema_state
    changed = False
    # If JSON was empty or not loaded (in-memory mode), make sure it's a dict
    if not isinstance(ema_state, dict):
        ema_state = {}
        changed = True

    for tf, st in list(ema_state.items()):
        if not isinstance(st, dict):
            ema_state[tf] = {"candle_list": [], "has_calculated": False}
            changed = True
            continue

        # Enforce keys
        if "candle_list" not in st or not isinstance(st["candle_list"], list):
            st["candle_list"] = []
            changed = True
        if "has_calculated" not in st or not isinstance(st["has_calculated"], bool):
            st["has_calculated"] = False
            changed = True

        # Drop legacy keys
        for legacy_key in ("seen_ts",):
            if legacy_key in st:
                st.pop(legacy_key, None)
                changed = True

    if changed:
        _persist()


def hard_reset_ema_state(selected_timeframes=None):
    """
    Reset both the JSON file and the in-memory dict for the provided timeframes.
    If 'selected_timeframes' is None, reset all known TFs in the file
    (or just initialize the standard ones if the file is empty).
    """
    global ema_state

    if selected_timeframes is None:
        # If we have TFs already in the file, reset those; otherwise create the common set.
        selected_timeframes = list(ema_state.keys()) or ["2M", "5M", "15M"]

    for tf in selected_timeframes:
        ema_state[tf] = {"candle_list": [], "has_calculated": False}

    _persist()
    print_log(f"[EMA STATE] Hard reset for TFs: {', '.join(selected_timeframes)}")

# -----------------------------
# Helper functions
# -----------------------------
def _persist():
    if USE_JSON_STATE:
        safe_write_json(EMA_STATE_PATH, ema_state)

def _ensure_tf(tf: str):
    if tf not in ema_state:
        ema_state[tf] = {"candle_list": [], "has_calculated": False}
        _persist()

def _maybe_daily_reset(tf: str, now_time: time, open_plus_15: time):
    """
    If a new session started and we haven't reset yet:
    - Before 09:45 ET, 'has_calculated' must be False and 'candle_list' empty.
    If yesterday left it True, clear it here automatically.
    """
    st = ema_state[tf]
    if now_time < open_plus_15 and st.get("has_calculated", False):
        st["has_calculated"] = False
        st["candle_list"].clear()
        _persist()

def _append_candle(tf: str, candle: dict):
    """
    Simple append with a tiny guard against exact duplicate of the last entry.
    (No global dedupe; we keep it simple.)
    """
    cl = ema_state[tf]["candle_list"]
    if cl and str(cl[-1].get("timestamp"))[:19] == str(candle.get("timestamp"))[:19]:
        return  # same-timestamp repeat, ignore
    cl.append(candle)
    _persist()

def _remove_merge_artifacts():
    for p in (AFTERMARKET_EMA_PATH, PREMARKET_EMA_PATH, MERGED_EMA_PATH):
        if os.path.exists(p):
            os.remove(p)

def _get_open_plus_15() -> time:
    today = datetime.now(NY_TZ).date()
    mo = datetime.combine(today, MARKET_OPEN)
    return (mo + timedelta(minutes=15)).time()

# -----------------------------
# Main
# -----------------------------
async def update_ema(candle: dict, timeframe: str):
    """
    Update EMA for a given candle/timeframe.

    Behavior:
    - Before 09:45 ET:
        * ensure TF exists, force daily reset if needed
        * buffer candles to ema_state[tf]["candle_list"]
        * rebuild temp EMAs from that buffer (for UI)
        * DO NOT mark 'has_calculated' True yet
    - At/after 09:45 ET:
        * if not finalized yet, bootstrap from buffer (and merged CSV), flip 'has_calculated' True, clear buffer
        * then do incremental update per candle
    """
    _ensure_tf(timeframe)
    st = ema_state[timeframe]

    now_time = datetime.now(NY_TZ).time()
    open_plus_15 = _get_open_plus_15()

    # EMA output file (list of snapshots with 'x' and per-window values)
    ema_path = get_ema_path(timeframe)
    initialize_json(ema_path, [])

    indent_pad = indent(1)

    # ---- PRE 09:45 ET ----
    if now_time < open_plus_15:
        # If yesterday leaked 'has_calculated' = True, clear it now
        _maybe_daily_reset(timeframe, now_time, open_plus_15)

        # Buffer current candle for the temporary EMAs
        _append_candle(timeframe, candle)

        # Keep temp EMAs consistent and isolated
        _remove_merge_artifacts()
        await get_candle_data_and_merge(
            int(timeframe.replace("M", "").replace("m", "")),
            "minute",
            "AFTERMARKET",
            "PREMARKET",
            2,
            timeframe,
        )
        reset_json(ema_path, [])

        # Rebuild temp EMAs from today's buffer only
        clist = st["candle_list"]
        clist_sorted = sorted(clist, key=lambda c: c["timestamp"])
        for i, c in enumerate(clist_sorted):
            await calculate_save_EMAs(c, i, timeframe)

        print_log(f"{indent_pad}[EMA CS] Temp EMA calculated for {timeframe} ({len(clist_sorted)} candles).")
        return

    # ---- AT/AFTER 09:45 ET ----
    if not st.get("has_calculated", False):
        # One-time finalize: get merged history, replay buffer, flip flag, clear buffer
        print_log(f"{indent_pad}[EMA CS] Finalizing EMAs after first 15 minutes for {timeframe}...")
        await get_candle_data_and_merge(
            int(timeframe.replace("M", "").replace("m", "")),
            "minute",
            "AFTERMARKET",
            "PREMARKET",
            2,
            timeframe,
        )
        reset_json(ema_path, [])

        # Replay buffered pre-open/open candles
        clist = st["candle_list"]
        clist_sorted = sorted(clist, key=lambda c: c["timestamp"])
        for i, c in enumerate(clist_sorted):
            await calculate_save_EMAs(c, i, timeframe)

        # Flip & clear
        st["has_calculated"] = True
        st["candle_list"].clear()
        _persist()
        print_log(f"{indent_pad}[EMA CS] Final EMA list calculated for {timeframe}.")

    # Incremental update per live candle for the rest of the session
    await calculate_save_EMAs(candle, get_current_candle_index(timeframe), timeframe)
    print_log(f"{indent_pad}[EMA CS] Updated live EMA for {timeframe}.")
