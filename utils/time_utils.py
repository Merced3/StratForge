# utils/time_utils.py, Candlestick time calc, add_seconds_to_time, etc.
from __future__ import annotations
from typing import Union
import pandas as pd

from datetime import datetime, timedelta
import time

from pathlib import Path
from typing import Optional, Iterable
from utils.timezone import NY_TZ

# ───🔹 CANDLESTICK TIMESTAMP-MATCH FOR MAIN SCRIPT ────────────────────────

def generate_candlestick_times(start_time, end_time, interval, exclude_first=False):
    start = NY_TZ.localize(datetime.combine(datetime.today(), start_time.time()))
    end = NY_TZ.localize(datetime.combine(datetime.today(), end_time.time()))
    
    times = []
    while start <= end:
        times.append(start)
        start += interval
        
    if exclude_first and times:
        return times[1:]  # Skip the first timestamp (09:30:00)
    return times

def add_seconds_to_time(time_str, seconds):
    time_obj = datetime.strptime(time_str, '%H:%M:%S')
    new_time_obj = time_obj + timedelta(seconds=seconds)
    return new_time_obj.strftime('%H:%M:%S')

# ───🔹 TS CONVERSION HELPERS ─────────────────────────────────────────────

def to_ms(val: Union[str, int, float, pd.Timestamp]) -> int:
    """
    Convert ISO string / pandas Timestamp / seconds / ms to int64 ms (UTC-aware).
    - ISO strings or Timestamps -> epoch ms
    - Numbers: assume seconds if < 10^12, else already ms
    """
    if isinstance(val, pd.Timestamp):
        ts = val
    elif isinstance(val, (int, float)):
        # seconds vs ms
        ts = pd.to_datetime(int(val * 1000 if val < 1_000_000_000_000 else val), unit="ms", utc=True)
    else:
        # string like "2025-09-22T15:15:00.505969-04:00"
        ts = pd.to_datetime(val, utc=True)

    # return epoch ms (int)
    return int(ts.value // 1_000_000)

def to_iso(ms: int) -> str:
    """int64 ms -> ISO8601 string with 'Z' (UTC)."""
    return pd.to_datetime(ms, unit="ms", utc=True).isoformat().replace("+00:00", "Z")
