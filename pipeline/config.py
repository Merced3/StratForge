from dataclasses import dataclass
from typing import Callable, Awaitable, Any
import pytz

@dataclass
class PipelineConfig:
    timeframes: list
    durations: dict
    buffer_secs: int
    symbol: str
    tz: Any = pytz.timezone("America/New_York")

@dataclass
class PipelineDeps:
    get_session_bounds: Callable[[str], Any]
    latest_price_lock: Any
    shared_state: Any

@dataclass
class PipelineSinks:
    append_candle: Callable[[str, str, dict], Any]
    update_ema: Callable[[dict, str], Awaitable[None]]
    refresh_chart: Callable[[str, str], Awaitable[None]]
    on_error: Callable[[Exception, str, str], Awaitable[None]]
