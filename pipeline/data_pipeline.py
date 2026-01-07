# pipeline/data_pipeline.py
import json, asyncio
from datetime import datetime, timedelta
from utils.time_utils import generate_candlestick_times, add_seconds_to_time
from pipeline.state import reset_day_state
from session import normalize_session_times

def build_candle_schedule(session_open, session_close, timeframes, durations, buffer_secs):
    timestamps = {
        tf: [t.strftime('%H:%M:%S') for t in generate_candlestick_times(
            session_open, session_close, timedelta(seconds=durations[tf]), True)]
        for tf in timeframes
    }
    buffer_timestamps = {tf: [add_seconds_to_time(t, buffer_secs) for t in ts] for tf, ts in timestamps.items()}
    return timestamps, buffer_timestamps

async def run_pipeline(queue, config, deps, sinks, now_fn=None):
    try:
        if now_fn is None:
            now_fn = lambda: datetime.now(config.tz)

        now = now_fn()
        current_candles, candle_counts, start_times = reset_day_state(config.timeframes, now)

        session_open, session_close = normalize_session_times(*deps.get_session_bounds(now.strftime("%Y-%m-%d")))
        if not session_open or not session_close:
            return

        current_day = session_open.date()
        market_open_time = session_open
        market_close_time = session_close
        timestamps, buffer_timestamps = build_candle_schedule(
            market_open_time, market_close_time, config.timeframes, config.durations, config.buffer_secs
        )

        while True:
            now = now_fn()
            f_now = now.strftime('%H:%M:%S')

            if now.date() != current_day:
                session_open, session_close = normalize_session_times(*deps.get_session_bounds(now.strftime("%Y-%m-%d")))
                if not session_open or not session_close:
                    break
                current_day = session_open.date()
                market_open_time = session_open
                market_close_time = session_close
                timestamps, buffer_timestamps = build_candle_schedule(
                    market_open_time, market_close_time, config.timeframes, config.durations, config.buffer_secs
                )
                current_candles, candle_counts, start_times = reset_day_state(config.timeframes, now)

            if now >= market_close_time:
                for timeframe in config.timeframes:
                    candle = current_candles[timeframe]
                    if candle["open"] is not None:
                        candle["timestamp"] = start_times[timeframe].isoformat()
                        sinks.append_candle(config.symbol, timeframe, candle)
                current_candles, candle_counts, start_times = reset_day_state(config.timeframes, now)
                async with deps.latest_price_lock:
                    deps.shared_state.latest_price = None
                break

            message = await queue.get()
            try:
                data = json.loads(message)
                if data.get("type") == "trade":
                    price = float(data.get("price", 0))
                    async with deps.latest_price_lock:
                        deps.shared_state.latest_price = price

                    for timeframe in config.timeframes:
                        candle = current_candles[timeframe]
                        if candle["open"] is None:
                            candle["open"] = candle["high"] = candle["low"] = price
                            start_times[timeframe] = now

                        candle["high"] = max(candle["high"], price)
                        candle["low"] = min(candle["low"], price)
                        candle["close"] = price

                        if (f_now in timestamps[timeframe]) or (f_now in buffer_timestamps[timeframe]):
                            candle["timestamp"] = start_times[timeframe].isoformat()
                            sinks.append_candle(config.symbol, timeframe, candle)
                            candle_counts[timeframe] += 1
                            await sinks.update_ema(candle, timeframe)
                            sinks.refresh_chart(timeframe, chart_type="live")
                            current_candles[timeframe] = {"open": None, "high": None, "low": None, "close": None}

                            if f_now in timestamps[timeframe]:
                                timestamps[timeframe].remove(f_now)
                                buffer_timestamps[timeframe].remove(add_seconds_to_time(f_now, config.buffer_secs))
                            elif f_now in buffer_timestamps[timeframe]:
                                buffer_timestamps[timeframe].remove(f_now)
                                timestamps[timeframe].remove(add_seconds_to_time(f_now, -config.buffer_secs))
            finally:
                queue.task_done()
    except Exception as e:
        await sinks.on_error(e, "data_pipeline", "run_pipeline")
