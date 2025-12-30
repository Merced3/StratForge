# tools/repair_candles.py
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import asyncio
import argparse
import pandas as pd
import time
from datetime import date, timedelta
from paths import pretty_path
from shared_state import print_log
from tools.audit_candles import (
    audit_dayfile,
    _tf_to_minutes,
    _chain_breaks,
    find_missing_days,
)
from tools.candles_io import create_daily_15m_parquet

clean_files_active = True # TODO: Set to true once testing (reading/printing) proves stable, fruitful.

def within_polygon_window(day_str: str, max_age_days: int) -> bool:
    cutoff = pd.Timestamp(date.today() - timedelta(days=max_age_days)).normalize()
    return pd.to_datetime(day_str) >= cutoff

def plan_days(base: Path, max_age_days: int):
    """
    Return a sorted list of day paths to keep (within window), and a list to delete (older than window).
    """
    files = sorted(base.glob("*.parquet"))
    keep, delete = [], []
    for p in files:
        day = p.stem
        if within_polygon_window(day, max_age_days):
            keep.append(p)
        else:
            delete.append(p)
    return keep, delete

def reindex_and_rebuild(keep_files, dry_run: bool, backoff_seconds: int):
    """
    Iterate days in chronological order, rebuild each with fresh global_x starting from 0.
    Returns the last global_x assigned.
    """

    next_global = 0
    for p in keep_files:
        day = p.stem
        if dry_run:
            print_log(f"[REPAIR] Would rebuild {day} starting global_x={next_global}, mode=candles-only")
            # still compute expected_next based on existing file length to avoid drift in dry-run
            try:
                df = pd.read_parquet(p, columns=["global_x"])
                length = len(df)
            except Exception:
                length = 0
            next_global += length
            continue

        # Delete existing file before rewrite (if present)
        if p.exists():
            try:
                p.unlink()
                print_log(f"[REPAIR] Deleted {p}")
            except Exception as e:
                print_log(f"[REPAIR] Could not delete {p}: {e}")
                continue

        # Rebuild dayfile with retry/backoff
        while True:
            try:
                asyncio.run(create_daily_15m_parquet(day))  # candles only; keeps timeline untouched
                # Verify length to advance next_global correctly
                df_new = pd.read_parquet(p, columns=["global_x"])
                length = len(df_new)
                print_log(f"[REPAIR] Rebuilt {day} rows={length}")
                next_global += length
                break
            except Exception as e:
                print_log(f"[REPAIR] Error rebuilding {day}: {e} | backing off {backoff_seconds}s then retrying...")
                time.sleep(backoff_seconds)
    return next_global

def main():
    ap = argparse.ArgumentParser(description="Repair candle dayfiles (optionally rewrite) with global_x reset.")
    ap.add_argument("--root", default="storage/data", help="Root folder containing timeframe dirs (default: storage/data)")
    ap.add_argument("--timeframe", default="15m", help="Timeframe to repair (default: 15m)")
    ap.add_argument("--max-age-days", type=int, default=1825, help="Only repair data within this many days (default: 5 years)")
    ap.add_argument("--tz", default="America/New_York", help="Timezone for session bounds (default: America/New_York)")
    ap.add_argument("--backoff-seconds", type=int, default=10, help="Delay between retries when a rebuild fails (default: 10s)")
    args = ap.parse_args()

    tf_minutes = _tf_to_minutes(args.timeframe)
    base = Path(args.root) / args.timeframe

    if not base.exists():
        print_log(f"[REPAIR] missing timeframe dir: {base}")
        return

    # 1) Windowing: decide which to delete vs keep
    keep_files, delete_files = plan_days(base, args.max_age_days)

    # Detect missing dayfiles within window and add them to rebuild list
    missing_days = find_missing_days(base, tz=args.tz, max_age_days=args.max_age_days)
    if missing_days:
        print_log(f"[REPAIR] Missing dayfiles within window: {len(missing_days)}")
        keep_files.extend([base / f"{d}.parquet" for d in missing_days])
        keep_files = sorted(keep_files)

    # 2) Report deletions outside window
    if delete_files:
        print_log(f"[REPAIR] {len(delete_files)} files older than {args.max_age_days} days:")
        for p in delete_files:
            if clean_files_active:
                try:
                    p.unlink()
                    print_log(f"[REPAIR] Deleted `{pretty_path(p)}`")
                except Exception as e:
                    print_log(f"[REPAIR] Could not delete `{pretty_path(p)}`: {e}")
            else:
                print_log(f"[REPAIR] Would delete `{pretty_path(p)}` (inactive)")

    # 3) Audit keep_files to get bad days and earliest rebuild point
    bad_days = []
    day_edges = {}
    for p in keep_files:
        if not p.exists():
            bad_days.append(p.stem)  # missing file flagged for rebuild
            continue
        res = audit_dayfile(p, tf_minutes, tz=args.tz)
        day_edges[res["day"]] = (res["gx_first"], res["gx_last"])
        if res["missing"] or res["extras"] or not res["gx_ok"]:
            bad_days.append(res["day"])

    # Chain breaks based on current files (pre-rebuild)
    chain_breaks = _chain_breaks(day_edges)

    # Determine rebuild start day: earliest of bad_days or chain_breaks
    rebuild_from = None
    if bad_days or chain_breaks:
        rebuild_from = min(bad_days + chain_breaks)
    else:
        print_log("[REPAIR] No issues detected; nothing to do.")
        return

    # Filter keep_files to those on/after rebuild_from
    keep_files_rebuild = [p for p in keep_files if p.stem >= rebuild_from]

    print_log(
        f"[REPAIR] Will rebuild from {rebuild_from} forward "
        f"({len(keep_files_rebuild)} files), mode=candles-only; "
        f"clean_active={clean_files_active}"
    )

    # 4) Rebuild chain from rebuild_from onward, resetting global_x from 0
    # If you want to preserve earlier global_x, you could seed next_global with _last_global_index(...)
    next_global = 0
    # If you wanted to preserve earlier untouched days, set next_global = _last_global_index(...) + 1 here.
    reindex_and_rebuild(keep_files_rebuild, dry_run=not clean_files_active, backoff_seconds=args.backoff_seconds)


if __name__ == "__main__":
    main()

"""
HOW TO USE (safe first):
- Leave clean_files_active = False (default) for a dry run; no deletes or rewrites occur.
- Run: python tools/repair_candles.py --timeframe 15m --max-age-days 1825
  * Logs will show which files would be deleted (older than the window) and which dayfiles would be rebuilt.
- If results look good, set clean_files_active = True in this script and rerun the same command to apply changes.
- Behavior: deletes dayfiles older than the window, then rebuilds from the earliest problematic day forward (candles-only), resetting global_x to be contiguous starting at 0.
"""
