# tools/candles_io.py
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.timezone import NY_TZ
from tools.normalize_ts_all import normalize_file
from utils.json_utils import read_config


# Guard heavy/runtime-only deps so import works in CI/tests
try:
    from data_acquisition import get_certain_candle_data  # used only in live flows
except Exception:  # catches ModuleNotFoundError for cred inside data_acquisition
    def get_certain_candle_data(*args, **kwargs):
        raise RuntimeError("data_acquisition/get_certain_candle_data unavailable in CI/tests")

try:
    import cred  # runtime secrets
except ModuleNotFoundError:
    cred = None  # fine for tests; any runtime path that needs cred must handle None


from shared_state import print_log
import pandas as pd
from paths import pretty_path, DATA_DIR

def _parquet_has_column(path: Path, col: str) -> bool:
    """Fast schema check without loading the whole file."""
    try:
        import pyarrow.parquet as pq
        return col in pq.ParquetFile(path).schema.names
    except Exception:
        # Fallback: try reading just the column; if it fails, it's missing.
        try:
            df = pd.read_parquet(path, columns=[col])
            return col in df.columns
        except Exception:
            return False

def _last_global_index(tf: str, day: str) -> int:
    """Find last known global_x before this day."""
    tf_dir = DATA_DIR / tf
    # All previous daily parquet files
    prev = sorted(tf_dir.glob("*.parquet"))
    prev_days = [p for p in prev if p.stem < day]
    if not prev_days:
        return -1
    last_file = prev_days[-1]
    if not _parquet_has_column(last_file, "global_x"):
        return -1
    
    try:
        # Read only the needed column
        df = pd.read_parquet(last_file, columns=["global_x"])
        if len(df) == 0:
            return -1
        return int(df["global_x"].max())
    except Exception:
        return -1

async def create_daily_15m_parquet(file_day_name: str):
    """
    Pull 15M MARKET candles for the given day (NY time) from Polygon and write:
        storage/data/15m/<YYYY-MM-DD>.parquet
    Schema/Order:
        symbol, timeframe, ts, open, high, low, close, volume, global_x

    If `day` is None, uses today's NY trading day via get_dates(1, True).
    Returns the output file Path.
    """

    symbol = read_config("SYMBOL")
    tf_label = "15M"
    
    # 2) Pull 15M MARKET candles for that day(s)
    start_str = end_str = file_day_name #start_str, end_str = get_dates(1, True)
    df = await get_certain_candle_data(
        cred.POLYGON_API_KEY,
        symbol,
        15, "minute",
        start_str, end_str,
        None,
        market_type="MARKET",
        indent_lvl=0
    )
    if df is None or df.empty:
        print_log(f"[create_daily_15m_parquet] No data for {file_day_name}.")
        return None

    df.sort_values("timestamp", inplace=True)

    print_log(f"[create_daily_15m_parquet] Pulled '{len(df)}' rows for '{file_day_name}'.\n\n{df}\n")

    # 3) Ensure tz-aware NY timestamps -> ISO with offset for 'ts'
    #    (data_acquisition already converts to NY tz)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(NY_TZ)
    # We filter in NY time, but we STORE in UTC (ts epoch ms + ts_iso Z)
    # to avoid DST ambiguity, keep ordering/global_x stable, and align with normalize_ts_all.
    ts_iso = df["timestamp"].apply(lambda ts: ts.isoformat())

    # 4) Build output DataFrame in required order
    volume_series = pd.Series(0, index=df.index, dtype="float64") # force all-zero volume as float64
    out_df = pd.DataFrame({
        "symbol":   symbol,
        "timeframe": tf_label,
        "ts":        ts_iso,
        "open":      df["open"].astype(float),
        "high":      df["high"].astype(float),
        "low":       df["low"].astype(float),
        "close":     df["close"].astype(float),
        "volume":    volume_series,
    })

    # 5) Stamp continuous global_x for 15m by peeking at last file
    out_dir = DATA_DIR / "15m"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{file_day_name}.parquet"

    last_global = _last_global_index(tf_label.lower(), file_day_name)
    start_gx = last_global + 1
    out_df["global_x"] = range(start_gx, start_gx + len(out_df))

    # 6) Atomic-ish write
    tmp = out_file.with_suffix(out_file.suffix + ".tmp")
    out_df.to_parquet(tmp, index=False)
    tmp.replace(out_file)

    try:
        res = normalize_file(out_file, dry_run=False, verbose=False)
        if res.get("ok"):
            print_log(f"[normalize] {('changed' if res.get('changed') else 'no-op')} → {pretty_path(out_file)}")
    except Exception as e:
        print_log(f"[normalize] WARN: could not normalize {pretty_path(out_file)}: {e}")

    # 7) Verify
    check = pd.read_parquet(out_file)
    ok = (
        len(check) == len(out_df)
        and check["ts"].min() == out_df["ts"].min()
        and check["ts"].max() == out_df["ts"].max()
        and check["global_x"].is_monotonic_increasing
        and int(check["global_x"].iloc[0]) == start_gx
        and int(check["global_x"].iloc[-1]) == start_gx + len(out_df) - 1
    )
    print_log(f"[create_daily_15m_parquet] → {'OK' if ok else 'WARN'} "
              f"{len(out_df)} rows → `{pretty_path(out_file)}`")
    return out_file
