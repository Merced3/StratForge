# paths.py
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Config
CONFIG_PATH = BASE / 'config.json'                                      # This is very needed, this is the control pannel of this whole program, values in this can change how the program runs LIVE.

# Logs
LOGS_DIR = BASE / 'logs'                                                # This holds anything log-wise
CANDLE_LOGS = {                                                         # This is very needed, theses are all candles displayed and used in not-only strategies but on the frontend as well.
    "2M": LOGS_DIR / 'SPY_2M.log',
    "5M": LOGS_DIR / 'SPY_5M.log',
    "15M": LOGS_DIR / 'SPY_15M.log'
}
TERMINAL_LOG = LOGS_DIR / 'terminal_output.log'                         # This is where all logs are saved while the program is running. This helps us to look back in history to see how the program as a whole handled specific things at specific times.

# Storage
STORAGE_DIR = BASE / 'storage'                                          # this holds any sensitive data, most of the stuff below is in this folder.
DATA_DIR = STORAGE_DIR / 'data'                                         # This is needed, this is where all parquet files are stored.
MARKERS_DIR = STORAGE_DIR / 'markers'                                   # Per-timeframe marker files for the frontend (e.g., 2M.json/5M.json)

# Objects folder
OBJECTS_DIR = STORAGE_DIR / 'objects'                                   # The `storage/objects/` folder contains zones and levels calculated by `objects.py`. We consider Zones and Levels as objects.
CURRENT_OBJECTS_DIR = OBJECTS_DIR / 'current'                           # This is needed, this is where all current objects are stored, these are the objects used in frontend (displaying) and most importantly in trading strategies.
TIMELINE_OBJECTS_DIR = OBJECTS_DIR / 'timeline'                         # This is needed, this is where all previous days objects are stored, these are not used in live trading but is for (not yet used) in the sim enviroment and `tools/plot_candles.py` to display previous days objects and hopefully, the zones historical frontend chart (one day, not yet).
CURRENT_OBJECTS_PATH = CURRENT_OBJECTS_DIR / "objects.parquet"
OBJECTS_PATH = OBJECTS_DIR / 'objects.json'                             # This is needed, this is not only used in main-live functionality but in sim enviroment as well. `web_dash/charts/zones_chart.py` uses this to plot zones and levels which are objects saved in this very file. We also use it to display objects in the sim enviroment which is `tools/plot_objects.py`.
TIMELINE_PATH = OBJECTS_DIR / 'timeline.json'                           # This is needed, this is a timeline of all objects created from previous days, we used `SPY_15_MINUTE_CANDLES_PATH` and `objects.py` to calculate the objects history and it shows the history in `tools/plot_candles.py`. Its not used though in the `web_dash/charts/zones_chart.py`. This is mainly a simulation tools history, using it to display to `tools/plot_candles.py` (hand built zones/levels simulation).

# EMA directory + dynamic EMA path retrieval
EMAS_DIR = STORAGE_DIR / 'emas'                                         # This is needed by `ema_manager.py`
EMA_STATE_PATH = EMAS_DIR / "ema_state.json"                            # This is needed by `ema_manager.py`, this is for figuring out if were past the first 15 minutes of market open beacuse were on polygons cheap plan and they have 15 min delayed data, after the first 15 mins were back to the live-correct data.
def get_ema_path(timeframe: str):                                       # This is needed by `ema_manager.py`, to get the path of the EMA file for every specific timeframe.
    return EMAS_DIR / f"{timeframe}.json"

def get_markers_path(timeframe: str):                                   # Resolve per-timeframe marker JSON path (e.g., storage/markers/2M.json)
    return MARKERS_DIR / f"{timeframe.upper()}.json"

# JSONs                                                                 # Everything below this line is no longer needed, but later development will require the replacement of these in a working fashion, EMA's is a good example of what I had to replace `EMAs.json` with.
LINE_DATA_PATH = STORAGE_DIR / 'line_data.json'                         # No longer needed, worked in older version, newer version require different timeframe flags hence the 'flags' folder which replaces this
MARKERS_PATH = STORAGE_DIR / 'markers.json'                             # No longer needed, worked in older version, newer version require different timeframe markers hence the 'markers' folder which replaces this
ORDER_CANDLE_TYPE_PATH = STORAGE_DIR / 'order_candle_type.json'         # No longer needed, worked in older version, newer version doesn't require this
PRIORITY_CANDLES_PATH = STORAGE_DIR / 'priority_candles.json'           # No longer needed, worked in older version, newer version doesn't require this
MESSAGE_IDS_PATH = STORAGE_DIR / 'message_ids.json'                     # This is needed, this records all message ID's sent to discord the same day, doesn't remember anything greater than the current day its running. After market ends it resets to zero meaning `{}`.
WEEK_ECOM_CALENDER_PATH = STORAGE_DIR / 'week_ecom_calendar.json'       # This is needed for the weekly economic calendar events. This is being used to fetch major, relevant events for the current week. So it knows if it should take trades or not at certian times where news can alter the trades results.

# CSVs
CSV_DIR = STORAGE_DIR / 'csv'
ORDER_LOG_PATH = CSV_DIR / 'order_log.csv'                              # This is needed for logging all orders made during the trading session. For further study later on.
SPY_15_MINUTE_CANDLES_PATH = CSV_DIR / 'SPY_15_minute_candles.csv'      # This is needed for 2 reasons; 1) this is previous days 15 min candles to not only plot previous history but used to calulate zones and levels, 2) As a backup of the parquet data, just in case something goes wrong with the parquet data, this is a quick way to get the data back.
AFTERMARKET_EMA_PATH = CSV_DIR / f"SPY_2_minute_AFTERMARKET.csv"        # IDK if these are used, I do see them used in `indicators/ema_manager.py` but I don't know if this is used in practice or is just ghost code, if it is I will remove it in the future.
PREMARKET_EMA_PATH = CSV_DIR / f"SPY_2_minute_PREMARKET.csv"            # IDK if these are used, I do see them used in `indicators/ema_manager.py` but I don't know if this is used in practice or is just ghost code, if it is I will remove it in the future.
MERGED_EMA_PATH = CSV_DIR / f"SPY_MERGED.csv"                           # IDK if these are used, I do see them used in `indicators/ema_manager.py` but I don't know if this is used in practice or is just ghost code, if it is I will remove it in the future.

def get_merged_ema_csv_path(timeframe: str):                            # This is needed, its used in `data_acquisition.py` from the function `get_candle_data_and_merge()` which is called in `indicators/ema_manager.py` in the function `update_ema()`. This is used to get the merged candles of premarket, aftermarket and regular market hours for EMA calculations.
    return CSV_DIR / f"merged_ema_{timeframe}.csv"

# STATES
STATES_DIR = BASE / 'states'                                            # This is needed and not needed, this is for the flagging setup, but this only works for on-disk for a singular timeframe (at-the-time 2M), we have everything saved in memory so this is mainly for testing or debugging

# PHOTOS (Images/Charts)
IMAGES_DIR = STORAGE_DIR / 'images'                                     # This folder is for cleanliness of photos, to be later sent to discord for me to view when im not home at the computer.
SPY_2M_CHART_PATH = IMAGES_DIR / 'SPY_2M_chart.png'                     # Live chart
SPY_5M_CHART_PATH = IMAGES_DIR / 'SPY_5M_chart.png'                     # Live chart
SPY_15M_CHART_PATH = IMAGES_DIR / 'SPY_15M_chart.png'                   # Live chart
SPY_15M_ZONE_CHART_PATH = IMAGES_DIR / 'SPY_15M-zone_chart.png'         # Historical chart (Zones and levels)

def get_chart_path(timeframe: str, zone_type: bool = False) -> Path:
    """
    Returns the path to the chart image for a given timeframe.
    
    Example:
      get_chart_path("2M")          → storage/images/SPY_2M_chart.png
      get_chart_path("15M", True)   → storage/images/SPY_15M-zone_chart.png
    """
    suffix = "-zone" if zone_type else ""
    return IMAGES_DIR / f"SPY_{timeframe}{suffix}_chart.png"


def pretty_path(path: Path, short: bool = True):                        # We print alot of stuff in terminal and a long path string is pointless and a pretty version of the path is more readable in terminal logs.
    from paths import BASE
    try:
        return path.relative_to(BASE) if not short else path.name
    except ValueError:
        return path.name
