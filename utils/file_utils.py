# utils/file_utils.py, General file system utilities
from datetime import datetime, timezone
from paths import DATA_DIR

def get_current_candle_index(timeframe: str) -> int:
    """
    Returns the zero-based index of the most recent candle for the given timeframe
    by counting intraday part parquet files (storage/data/<tf>/<day>/part-*.parquet).
    Timeframe should be one of: '2M', '5M', '15M', etc.
    """
    tf_dir = DATA_DIR / timeframe.lower()
    # Use NY date to align with trading session folders; fall back to latest available folder.
    day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_dir = tf_dir / day_str

    if not day_dir.exists():
        try:
            day_dir = max((p for p in tf_dir.iterdir() if p.is_dir()), default=None)
        except FileNotFoundError:
            day_dir = None

    if not day_dir or not day_dir.exists():
        return 0

    part_count = len(list(day_dir.glob("part-*.parquet")))
    return part_count - 1 if part_count > 0 else 0
