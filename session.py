# session.py
import asyncio
import cred
import aiohttp
import pandas_market_calendars as mcal
from datetime import datetime
from shared_state import print_log
from utils.timezone import NY_TZ_NAME

def normalize_session_times(session_open, session_close):
    if not session_open or not session_close:
        return None, None
    to_dt = lambda ts: ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    return to_dt(session_open), to_dt(session_close)

def get_session_bounds(day_str: str):
    raw_open, raw_close = _nyse_session(day_str)
    return normalize_session_times(raw_open, raw_close)

def _nyse_session(day_str: str):
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start_date=day_str, end_date=day_str)
    if sched.empty:
        return None, None
    row = sched.iloc[0]
    # keep tz-aware NY times
    return (
        row["market_open"].tz_convert(NY_TZ_NAME),
        row["market_close"].tz_convert(NY_TZ_NAME),
    )

async def is_market_open():
    """Check if the stock market is open today using Polygon.io API."""
    url = "https://api.polygon.io/v1/marketstatus/now"
    params = {"apiKey": cred.POLYGON_API_KEY}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    print_log(f"\n[DATA_AQUISITION] 'is_market_open()' DATA: \n{data}\n")
                    market_status = data.get("market", "closed")
                    return market_status in ["open", "extended-hours"]
                else:
                    print_log(f"[ERROR] Polygon API request failed with status {response.status}: {await response.text()}")
                    return False
    except Exception as e:
        print_log(f"[ERROR] Exception in is_market_open: {e}")
        return False

async def wait_until_market_open(target_time, tz):
    print_log(f"Waiting for market open at {target_time.strftime('%H:%M:%S')}...")
    while True:
        now = datetime.now(tz)
        remaining = (target_time - now).total_seconds()
        if remaining <= 0.2:
            break
        # sleep in larger chunks until the last second
        await asyncio.sleep(min(remaining - 0.1, 1.0))
    print_log("Market open hit; starting...")
