from utils.json_utils import read_config
from utils.timezone import NY_TZ

TIMEFRAME_SECONDS = {
    "1M": 60, "2M": 120, "3M": 180, "5M": 300,
    "15M": 900, "30M": 1800, "1H": 3600,
}

def load_pipeline_config():
    tfs = read_config("TIMEFRAMES")
    durations = {tf: TIMEFRAME_SECONDS[tf] for tf in tfs}
    return {
        "timeframes": tfs,
        "durations": durations,
        "buffer_secs": read_config("CANDLE_BUFFER"),
        "symbol": read_config("SYMBOL"),
        "tz": NY_TZ,
    }
