# tools/compact_parquet.py
from pathlib import Path
import sys

# Ensure repo root (where paths.py AND utils lives) is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import paths  # centralized paths
import argparse
import pandas as pd
from tools.candles_io import _last_global_index

"""
How you’ll use it:

- After close (daily): 
python tools/compact_parquet.py --timeframe 2m --day 2025-09-02
python tools/compact_parquet.py --timeframe 5m --day 2025-09-02
python tools/compact_parquet.py --timeframe 15m --day 2025-09-02

- Month-end (or weekly):
python tools/compact_parquet.py --timeframe 15m --month 2025-09

*If you want to keep parts, add `--keep-parts` flag*
python tools/compact_parquet.py --timeframe 2m --day 2025-09-02 --keep-parts
python tools/compact_parquet.py --timeframe 15m --month 2025-09 --keep-parts
"""

def end_of_day_compaction(day: str, TFs: list = ("2m", "5m", "15m")) -> None:
    for tf in TFs:
        res = compact_day(tf, day, delete_parts=True)
        print(f"[compact {tf} {day}] -> {res}")

def _write_atomic(df: pd.DataFrame, out_file: Path):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_file.with_suffix(out_file.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(out_file)  # atomic-ish on same volume

def compact_day(timeframe: str, day: str, delete_parts: bool = True) -> dict:
    """
    Merge storage/data/<tf>/<YYYY-MM-DD>/part-*.parquet -> storage/data/<tf>/<YYYY-MM-DD>.parquet
    Then (optionally) delete the parts folder.
    """
    tf = timeframe.lower()
    day_dir = paths.DATA_DIR / tf / day
    parts = sorted(day_dir.glob("part-*.parquet"))
    if not parts:
        return {"ok": False, "reason": f"no parts for {tf} {day}"}

    # Read and concat all parts
    dfs = [pd.read_parquet(p) for p in parts]
    df_all = pd.concat(dfs, ignore_index=True) # pd.concat(dfs, ignore_index=True).sort_values("ts")
    
   # Choose best sort key (prefer int64 ms 'ts'; else fall back to 'ts_iso')
    if "ts" in df_all.columns and pd.api.types.is_integer_dtype(df_all["ts"]):
        sort_key = "ts"
    elif "ts_iso" in df_all.columns:
        sort_key = "ts_iso"
    else:
        # last resort: keep input order (shouldn’t happen with our writers)
        sort_key = None

    if sort_key:
        df_all = df_all.sort_values(sort_key)
    
    # If this is 15m, stamp contiguous global_x continuing from previous day
    start_gx = end_gx = None
    if tf == "15m":
        last_idx = _last_global_index(tf, day) # -1 if none
        start = last_idx + 1
        df_all["global_x"] = range(start, start + len(df_all))
        start_gx = int(df_all["global_x"].iloc[0])
        end_gx   = int(df_all["global_x"].iloc[-1])

    # Basic verification (handle both ts or ts_iso)
    row_count = len(df_all)
    if "ts" in df_all.columns:
        ts_min = df_all["ts"].min()
        ts_max = df_all["ts"].max()
    elif "ts_iso" in df_all.columns:
        ts_min = df_all["ts_iso"].min()
        ts_max = df_all["ts_iso"].max()
    else:
        ts_min = ts_max = None

    # Single atomic write
    out = paths.DATA_DIR / tf / f"{day}.parquet"
    _write_atomic(df_all, out)

    # Verify write-back by re-reading
    df_check = pd.read_parquet(out)
    ok = len(df_check) == row_count
    if ts_min is not None:
        key = "ts" if "ts" in df_all.columns else "ts_iso"
        ok = ok and (df_check[key].min() == ts_min) and (df_check[key].max() == ts_max)

    # Extra verification for 15m global_x (only if we stamped it)
    if tf == "15m" and "global_x" in df_all.columns:
        gx_ok = (
            df_check["global_x"].is_monotonic_increasing
            and int(df_check["global_x"].iloc[0]) == start_gx
            and int(df_check["global_x"].iloc[-1]) == end_gx
            and (end_gx - start_gx + 1) == row_count
        )
        ok = ok and gx_ok
        
    # Cleanup
    if ok and delete_parts:
        for p in parts:
            p.unlink()
        try:
            day_dir.rmdir()  # only if empty
        except OSError:
            pass

    res = {"ok": ok, "rows": row_count, "out": str(out)}
    if tf == "15m" and start_gx is not None:
        res.update({"start_global_x": start_gx, "end_global_x": end_gx})
    return res

def compact_month_objects(timeframe: str, year_month: str, delete_parts: bool = True) -> dict:
    """
    Merge storage/objects/<tf>/<YYYY-MM>/part-*.parquet -> storage/objects/<tf>/<YYYY-MM>/events.parquet
    """
    tf = timeframe.lower()
    month_dir = paths.OBJECTS_DIR / tf / year_month
    parts = sorted(month_dir.glob("part-*.parquet"))
    if not parts:
        return {"ok": False, "reason": f"no parts for {tf} {year_month}"}

    dfs = [pd.read_parquet(p) for p in parts]
    df_all = pd.concat(dfs, ignore_index=True).sort_values("event_ts")

    out = month_dir / "events.parquet"
    _write_atomic(df_all, out)

    df_check = pd.read_parquet(out)
    ok = len(df_check) == len(df_all)

    if ok and delete_parts:
        for p in parts:
            p.unlink()

    return {"ok": ok, "rows": len(df_all), "out": str(out)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", required=True, help="e.g. 2m, 5m, 15m")
    ap.add_argument("--day", help="YYYY-MM-DD (for candles)")
    ap.add_argument("--month", help="YYYY-MM (for objects)")
    ap.add_argument("--keep-parts", action="store_true", help="do not delete part-*.parquet")
    args = ap.parse_args()

    if args.day:
        res = compact_day(args.timeframe, args.day, delete_parts=not args.keep_parts)
        print(res)
    if args.month:
        res = compact_month_objects(args.timeframe, args.month, delete_parts=not args.keep_parts)
        print(res)
