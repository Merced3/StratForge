# tools/audit_candles.py
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import datetime
import pandas as pd
import pandas_market_calendars as mcal
from typing import Optional
from shared_state import print_log

def _tf_to_minutes(tf: str) -> int:
    """Parse timeframe like '15m' or '5' into minutes."""
    tf = tf.lower().strip()
    if tf.endswith("m"):
        tf = tf[:-1]
    try:
        return int(tf)
    except ValueError:
        raise ValueError(f"Unsupported timeframe '{tf}'. Use minute-based TFs like 15m.")

def _read_day_ts_series(day_path: Path, tz: str = "America/New_York") -> pd.Series:
    """Read a dayfile's ts as tz-aware datetimes, sorted ascending."""
    df = pd.read_parquet(day_path, columns=["ts"]).sort_values("ts")
    ts = df["ts"]
    if pd.api.types.is_integer_dtype(ts) or pd.api.types.is_float_dtype(ts):
        ts = pd.to_datetime(ts, unit="ms", utc=True)
    else:
        ts = pd.to_datetime(ts, utc=True)
    return ts.dt.tz_convert(tz).reset_index(drop=True)

def _get_nyse_session_bounds(day_str: str, tz: str = "America/New_York") -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """Return NYSE market open/close for the given day in requested tz (handles early closes)."""
    try:
        cal = mcal.get_calendar("NYSE")
        sched = cal.schedule(start_date=day_str, end_date=day_str)
        if sched.empty:
            print_log(f"[HEAL] {day_str} is not a NYSE trading day.")
            return None, None
        row = sched.iloc[0]
        return (
            row["market_open"].tz_convert(tz),
            row["market_close"].tz_convert(tz),
        )
    except Exception as e:
        print_log(f"[HEAL] Could not load NYSE schedule for {day_str}: {e}")
        return None, None

def find_missing_days(base: Path, tz="America/New_York", max_age_days: int | None = None) -> list[str]:
    files = sorted(base.glob("*.parquet"))
    have = {p.stem for p in files}
    if not have:
        return []
    start = min(have)
    end = max(have)
    # optional window clamp
    if max_age_days:
        cutoff = (pd.Timestamp("today").normalize() - pd.Timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        start = max(start, cutoff)
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start_date=start, end_date=end)
    expected = {d.strftime("%Y-%m-%d") for d in sched.index}
    return sorted(expected - have)

def _find_missing_intervals(
    ts_series: pd.Series,
    step_minutes: int,
    expected_open: Optional[pd.Timestamp] = None,
    expected_close: Optional[pd.Timestamp] = None,
) -> tuple[list[pd.Timestamp], list[pd.Timestamp]]:
    """Return (missing_in_session, extras_outside_session) for the given timeframe."""
    if ts_series.empty:
        return [], []
    
    ts_series = ts_series.sort_values().reset_index(drop=True)
    step = pd.Timedelta(minutes=step_minutes)
    missing: list[pd.Timestamp] = []
    extras: list[pd.Timestamp] = []

    # Session coverage: from market open up to (but not including) market close.
    if expected_open is not None and expected_close is not None:
        in_session = [t for t in ts_series if expected_open <= t < expected_close]
        extras = [t for t in ts_series if t < expected_open or t >= expected_close]

        expected = pd.date_range(expected_open, expected_close - step, freq=step)
        actual_set = set(in_session)
        missing.extend([t for t in expected if t not in actual_set])
        series_for_cadence = in_session
    else:
        series_for_cadence = list(ts_series)

    if len(series_for_cadence) > 1:
        prev = series_for_cadence[0]
        for curr in series_for_cadence[1:]:
            if curr - prev > step:
                t = prev + step
                while t < curr:
                    missing.append(t)
                    t += step
            prev = curr
        
    return sorted(set(missing)), sorted(set(extras))

def _check_global_x(day_path: Path) -> dict:
    df = pd.read_parquet(day_path, columns=["global_x"]).sort_values("global_x")
    gx = df["global_x"].to_numpy()
    if len(gx) == 0:
        return {"ok": False, "empty": True, "first": None, "last": None, "len": 0}
    contiguous = (gx[1:] - gx[:-1] == 1).all()
    return {
        "ok": contiguous,
        "empty": False,
        "first": int(gx[0]),
        "last": int(gx[-1]),
        "len": len(gx),
    }

def audit_dayfile(day_path: Path, tf_minutes: int, tz: str = "America/New_York") -> dict:
    """Audit one dayfile for cadence, session adherence, and in-file global_x continuity."""
    day_str = day_path.stem
    ts_series = _read_day_ts_series(day_path, tz=tz)
    session_open, session_close = _get_nyse_session_bounds(day_str, tz=tz)
    missing, extras = _find_missing_intervals(
        ts_series,
        step_minutes=tf_minutes,
        expected_open=session_open,
        expected_close=session_close,
    )
    gx_res = _check_global_x(day_path)
    return {
        "day": day_str,
        "path": str(day_path),
        "missing": missing,
        "extras": extras,
        "missing_count": len(missing),
        "extras_count": len(extras),
        "rows": len(ts_series),
        "session_open": session_open,
        "session_close": session_close,
        "gx_ok": gx_res["ok"],
        "gx_first": gx_res.get("first"),
        "gx_last": gx_res.get("last"),
        "gx_len": gx_res.get("len"),
    }

def within_polygon_window(day_str: str, max_age_days: int) -> bool:
    cutoff = pd.Timestamp("today").normalize() - pd.Timedelta(days=max_age_days)
    return pd.to_datetime(day_str) >= cutoff

def _chain_breaks(day_edges: dict[str, tuple[int, int]]) -> list[str]:
    """
    Given {day: (first_gx, last_gx)} sorted by day, return days where the
    first_gx does not equal the expected next global_x from the previous file.
    """
    breaks = []
    expected = None
    for day in sorted(day_edges.keys()):
        first, last = day_edges[day]
        if first is None or last is None:
            expected = None  # skip empty/invalid; reset expectation
            continue
        if expected is not None and first != expected:
            breaks.append(day)
        expected = last + 1
    return breaks

def main():
    ap = argparse.ArgumentParser(description="Audit candle dayfiles for missing/out-of-session bars.")
    ap.add_argument("--root", default="storage/data", help="Root folder containing timeframe dirs (default: storage/data)")
    ap.add_argument("--timeframes", nargs="+", default=["15m"], help="Timeframes to audit (minute-based, e.g., 15m 5m)")
    ap.add_argument("--pattern", default="*.parquet", help="Glob pattern (default: *.parquet)")
    ap.add_argument("--recurse", action="store_true", help="Recurse into subfolders (e.g., part-*.parquet)")
    ap.add_argument("--limit", type=int, default=None, help="Stop after N files per timeframe (debug)")
    ap.add_argument("--tz", default="America/New_York", help="Timezone for session bounds (default: America/New_York)")
    ap.add_argument("--max-age-days", type=int, default=1825, help="Optional window (days) for missing-day check; default 5 years")
    ap.add_argument("--verbose", action="store_true", help="Print per-file results when issues are found")
    args = ap.parse_args()

    root = Path(args.root)
    totals = []
    for tf in args.timeframes:
        tf_minutes = _tf_to_minutes(tf)
        base = root / tf
        if not base.exists():
            print_log(f"[AUDIT] missing timeframe dir: {base}")
            continue

        files = base.rglob(args.pattern) if args.recurse else base.glob(args.pattern)
        scanned = errors = 0
        bad_candles, bad_gx = [], []
        day_edges: dict[str, tuple[int, int]] = {}
        early_closes = 0

        for i, p in enumerate(sorted(files), start=1):
            if args.limit and i > args.limit:
                break
            try:
                res = audit_dayfile(p, tf_minutes, tz=args.tz)
                scanned += 1

                sc = res["session_close"]
                if sc is not None:
                    close_local = sc.tz_convert(args.tz).time()
                    if close_local < datetime.time(16, 0):
                        early_closes += 1

                # stash edges for chain analysis
                day_edges[res["day"]] = (res["gx_first"], res["gx_last"])

                # classify issues
                if res["missing"] or res["extras"]:
                    bad_candles.append(res["day"])
                    if args.verbose:
                        print_log(f"[AUDIT] {res['day']}: missing={res['missing_count']}, extras={res['extras_count']}")
                        #if res["missing"]:
                            #print_log(f"         missing sample: {res['missing'][:3]}")
                        #if res["extras"]:
                            #print_log(f"         extras sample: {res['extras'][:3]}")
                if not res["gx_ok"]:
                    bad_gx.append(res["day"])
                    if args.verbose:
                        print_log(f"[AUDIT] {res['day']}: global_x not contiguous (len={res['gx_len']}, first={res['gx_first']}, last={res['gx_last']})")
            except Exception as e:
                errors += 1
                print_log(f"[AUDIT] error on {p}: {e}")

        chain_breaks = _chain_breaks(day_edges)
        
        missing_days = find_missing_days(base, tz=args.tz, max_age_days=args.max_age_days)
        print_log(f"[AUDIT] missing_dayfiles={len(missing_days)}")
        if args.verbose and missing_days:
            print_log(f"         missing sample: {missing_days[:10]}")
        
        totals.append((tf, scanned, len(bad_candles), len(bad_gx), len(chain_breaks), early_closes, errors))
        print_log(
            f"[AUDIT] tf={tf}: scanned={scanned}, candle_issues={len(bad_candles)}, "
            f"gx_issues={len(bad_gx)}, chain_breaks={len(chain_breaks)}, early_closes={early_closes}, errors={errors}"
        )

    print_log(f"[AUDIT] done. totals={totals}")


if __name__ == "__main__":
    main()
