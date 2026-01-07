# tests\runtime\test_time_helpers.py
from datetime import datetime, timedelta

import pandas as pd
import pytz

from session import normalize_session_times
from pipeline.data_pipeline import build_candle_schedule


def test_normalize_session_times_with_pandas_timestamp():
    ny = pytz.timezone("America/New_York")
    ts = pd.Timestamp("2025-01-02 09:30:00", tz=ny)
    open_dt, close_dt = normalize_session_times(ts, ts + pd.Timedelta(hours=6, minutes=30))
    assert open_dt.tzinfo.zone == ny.zone
    assert close_dt.tzinfo.zone == ny.zone
    assert open_dt.hour == 9 and close_dt.hour == 16


def test_normalize_session_times_none_safe():
    assert normalize_session_times(None, None) == (None, None)


def test_build_candle_schedule_basic():
    ny = pytz.timezone("America/New_York")
    session_open = ny.localize(datetime(2025, 1, 2, 9, 30, 0))
    session_close = session_open + timedelta(minutes=2)
    timeframes = ["1M"]
    durations = {"1M": 60}
    buffer_secs = 5

    timestamps, buffer_ts = build_candle_schedule(session_open, session_close, timeframes, durations, buffer_secs)
    # 9:31:00 and 9:32:00 expected (exclude_first=True in generate_candlestick_times)
    assert timestamps["1M"][0].startswith("09:31:")
    assert len(timestamps["1M"]) == 2
    assert buffer_ts["1M"][0].startswith("09:31:")
    # buffer should be 5 seconds ahead of timestamps (09:31:05)
    assert buffer_ts["1M"][0].endswith("05")
