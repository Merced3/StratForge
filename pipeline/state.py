# pipeline/state.py
# helpers for candle state init/reset/flush so `data_pipeline.py` stays lean.

def reset_day_state(timeframes, now):
    return (
        {tf: {"open": None, "high": None, "low": None, "close": None} for tf in timeframes},
        {tf: 0 for tf in timeframes},
        {tf: now for tf in timeframes},
    )
