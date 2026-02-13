from __future__ import annotations

from typing import List, Optional

from .types import PositionAction, StrategyContext, StrategySignal


STRATEGY_BASE_NAME = "ema-regime-fusion"
MODE = "single"  # "single" or "multi"
SINGLE_TIMEFRAME = "5M"
TIMEFRAMES = ["5M", "15M"] # , "2M"]
FAST_EMA = "13"
SLOW_EMA = "48"
TRAIL_STOP_EMA = FAST_EMA
TREND_MIN_SPREAD_PCT = 0.18
CHOP_MAX_SPREAD_PCT = 0.10
SNAP_SETUP_MAX_BARS = 4
SNAP_MAX_BARS_IN_TRADE = 6
IS_ENABLED = False  # Set to True to enable this strategy
STRATEGY_DESCRIPTION = (
    "Regime-adaptive strategy that trades trend continuation when EMA spread is wide "
    "and mean-reversion snapbacks when EMA spread is compressed. Trend entries use "
    "EMA breaks with adaptive EMA stops; chop entries fade extension/reclaim patterns "
    "with excursion stops and quick exits."
)
STRATEGY_ASSESSMENT = ""


class EmaRegimeFusionStrategy:
    name = STRATEGY_BASE_NAME

    def __init__(
        self,
        *,
        timeframe: str = "5M",
        fast: str = "13",
        slow: str = "48",
        trail_stop_ema: str = "13",
        trend_min_spread_pct: float = 0.18,
        chop_max_spread_pct: float = 0.10,
        snap_setup_max_bars: int = 4,
        snap_max_bars_in_trade: int = 6,
        name: Optional[str] = None,
    ) -> None:
        self.timeframe = timeframe
        self.fast = fast
        self.slow = slow
        self.trail_stop_ema = trail_stop_ema
        self.trend_min_spread_pct = float(trend_min_spread_pct)
        self.chop_max_spread_pct = float(chop_max_spread_pct)
        self.snap_setup_max_bars = int(snap_setup_max_bars)
        self.snap_max_bars_in_trade = int(snap_max_bars_in_trade)
        if name:
            self.name = name

        self._active_mode: Optional[str] = None  # "trend" | "snap"
        self._active_direction: Optional[str] = None  # "call" | "put"
        self._bars_in_trade: int = 0

        self._trend_entry_ema: Optional[str] = None
        self._trend_using_trail: bool = False

        self._snap_stop_level: Optional[float] = None

        self._setup_direction: Optional[str] = None
        self._setup_excursion: Optional[float] = None
        self._setup_bars: int = 0

        self._pending_close: bool = False
        self._close_reason: Optional[str] = None

    def on_candle_close(self, context: StrategyContext) -> Optional[StrategySignal]:
        if context.timeframe != self.timeframe:
            return None

        ema = context.ema or {}
        if not ema:
            return None

        candle = context.candle or {}
        open_price = _to_float(candle.get("open"))
        close_price = _to_float(candle.get("close"))
        if open_price is None or close_price is None:
            return None
        high_price = _resolve_high(candle, open_price, close_price)
        low_price = _resolve_low(candle, open_price, close_price)

        fast_value = _get_ema_value(ema, self.fast)
        slow_value = _get_ema_value(ema, self.slow)
        if fast_value is None or slow_value is None:
            return None

        if self._active_mode and self._active_direction:
            self._bars_in_trade += 1
            if self._active_mode == "trend":
                self._evaluate_trend_trade(
                    ema_snapshot=ema,
                    open_price=open_price,
                    close_price=close_price,
                )
            else:
                self._evaluate_snap_trade(
                    open_price=open_price,
                    close_price=close_price,
                    high_price=high_price,
                    low_price=low_price,
                    slow_value=slow_value,
                )
            return None

        regime = _resolve_regime(
            fast_value=fast_value,
            slow_value=slow_value,
            price=close_price,
            trend_min_spread_pct=self.trend_min_spread_pct,
            chop_max_spread_pct=self.chop_max_spread_pct,
        )

        if regime == "trend":
            self._reset_setup()
            return self._build_trend_entry_signal(
                ema_snapshot=ema,
                open_price=open_price,
                close_price=close_price,
                fast_value=fast_value,
                slow_value=slow_value,
            )

        if regime == "chop":
            return self._build_snap_entry_signal(
                open_price=open_price,
                close_price=close_price,
                high_price=high_price,
                low_price=low_price,
                fast_value=fast_value,
                slow_value=slow_value,
            )

        self._reset_setup()
        return None

    def on_position_update(self, updates):
        if not self._pending_close or not updates:
            return None
        for update in updates:
            if update.strategy_tag and not _tag_matches(self.name, update.strategy_tag):
                continue
            reason = self._close_reason or "Exit"
            self._reset_position()
            return PositionAction(
                action="close",
                position_id=update.position_id,
                reason=reason,
                timeframe=self.timeframe,
            )
        return None

    def _build_trend_entry_signal(
        self,
        *,
        ema_snapshot: dict,
        open_price: float,
        close_price: float,
        fast_value: float,
        slow_value: float,
    ) -> Optional[StrategySignal]:
        direction = _trend_direction(fast_value=fast_value, slow_value=slow_value)
        if not direction:
            return None
        for ema_key in _sorted_ema_keys(ema_snapshot):
            ema_value = _get_ema_value(ema_snapshot, ema_key)
            if ema_value is None:
                continue
            if direction == "call" and _crossed_up(open_price, close_price, ema_value):
                self._activate_trend(direction="call", entry_ema=ema_key)
                return StrategySignal(
                    direction="call",
                    reason=(
                        f"Trend regime: candle broke EMA {ema_key} up with "
                        f"EMA {self.fast}>{self.slow}"
                    ),
                )
            if direction == "put" and _crossed_down(open_price, close_price, ema_value):
                self._activate_trend(direction="put", entry_ema=ema_key)
                return StrategySignal(
                    direction="put",
                    reason=(
                        f"Trend regime: candle broke EMA {ema_key} down with "
                        f"EMA {self.fast}<{self.slow}"
                    ),
                )
        return None

    def _build_snap_entry_signal(
        self,
        *,
        open_price: float,
        close_price: float,
        high_price: float,
        low_price: float,
        fast_value: float,
        slow_value: float,
    ) -> Optional[StrategySignal]:
        if self._setup_direction:
            self._setup_bars += 1
            if self._setup_bars > self.snap_setup_max_bars:
                self._reset_setup()

        self._update_setup(low_price=low_price, high_price=high_price, slow_value=slow_value)

        if self._setup_direction == "call" and _crossed_up(open_price, close_price, fast_value):
            stop_level = self._setup_excursion if self._setup_excursion is not None else low_price
            self._activate_snap(direction="call", stop_level=stop_level)
            self._reset_setup()
            return StrategySignal(
                direction="call",
                reason=(
                    f"Chop regime snapback call: extension below EMA {self.slow}, "
                    f"reclaim above EMA {self.fast}"
                ),
            )

        if self._setup_direction == "put" and _crossed_down(open_price, close_price, fast_value):
            stop_level = self._setup_excursion if self._setup_excursion is not None else high_price
            self._activate_snap(direction="put", stop_level=stop_level)
            self._reset_setup()
            return StrategySignal(
                direction="put",
                reason=(
                    f"Chop regime snapback put: extension above EMA {self.slow}, "
                    f"reclaim below EMA {self.fast}"
                ),
            )
        return None

    def _update_setup(self, *, low_price: float, high_price: float, slow_value: float) -> None:
        extended_down = low_price < slow_value
        extended_up = high_price > slow_value

        if extended_down and not extended_up:
            if self._setup_direction != "call":
                self._setup_direction = "call"
                self._setup_excursion = low_price
                self._setup_bars = 0
            else:
                if self._setup_excursion is None:
                    self._setup_excursion = low_price
                else:
                    self._setup_excursion = min(self._setup_excursion, low_price)
            return

        if extended_up and not extended_down:
            if self._setup_direction != "put":
                self._setup_direction = "put"
                self._setup_excursion = high_price
                self._setup_bars = 0
            else:
                if self._setup_excursion is None:
                    self._setup_excursion = high_price
                else:
                    self._setup_excursion = max(self._setup_excursion, high_price)
            return

        if self._setup_direction == "call" and extended_down:
            if self._setup_excursion is None:
                self._setup_excursion = low_price
            else:
                self._setup_excursion = min(self._setup_excursion, low_price)
            return

        if self._setup_direction == "put" and extended_up:
            if self._setup_excursion is None:
                self._setup_excursion = high_price
            else:
                self._setup_excursion = max(self._setup_excursion, high_price)

    def _evaluate_trend_trade(self, *, ema_snapshot: dict, open_price: float, close_price: float) -> None:
        stop_key = self._resolve_trend_stop_ema_key(ema_snapshot)
        if not stop_key:
            return
        stop_value = _get_ema_value(ema_snapshot, stop_key)
        if stop_value is None:
            return
        if self._active_direction == "call" and _crossed_down(open_price, close_price, stop_value):
            stage = "trail" if self._trend_using_trail else "initial"
            self._queue_close(f"Trend stop ({stage}): broke EMA {stop_key} down")
            return
        if self._active_direction == "put" and _crossed_up(open_price, close_price, stop_value):
            stage = "trail" if self._trend_using_trail else "initial"
            self._queue_close(f"Trend stop ({stage}): broke EMA {stop_key} up")

    def _resolve_trend_stop_ema_key(self, ema_snapshot: dict) -> Optional[str]:
        if not self._trend_entry_ema or not self._active_direction:
            self._trend_using_trail = False
            return None
        entry_value = _get_ema_value(ema_snapshot, self._trend_entry_ema)
        trail_value = _get_ema_value(ema_snapshot, self.trail_stop_ema)
        if entry_value is None or trail_value is None:
            self._trend_using_trail = False
            return self._trend_entry_ema
        if self._active_direction == "call" and trail_value > entry_value:
            self._trend_using_trail = True
            return self.trail_stop_ema
        if self._active_direction == "put" and trail_value < entry_value:
            self._trend_using_trail = True
            return self.trail_stop_ema
        self._trend_using_trail = False
        return self._trend_entry_ema

    def _evaluate_snap_trade(
        self,
        *,
        open_price: float,
        close_price: float,
        high_price: float,
        low_price: float,
        slow_value: float,
    ) -> None:
        if self._pending_close:
            return

        if self._snap_stop_level is not None:
            if self._active_direction == "call" and _crossed_down(open_price, close_price, self._snap_stop_level):
                self._queue_close(f"Snap stop: broke excursion low {self._snap_stop_level:.2f}")
                return
            if self._active_direction == "put" and _crossed_up(open_price, close_price, self._snap_stop_level):
                self._queue_close(f"Snap stop: broke excursion high {self._snap_stop_level:.2f}")
                return

        if self._active_direction == "call" and high_price >= slow_value:
            self._queue_close(f"Snap target: touched EMA {self.slow}")
            return
        if self._active_direction == "put" and low_price <= slow_value:
            self._queue_close(f"Snap target: touched EMA {self.slow}")
            return

        if self._bars_in_trade >= self.snap_max_bars_in_trade:
            self._queue_close(f"Snap timeout: {self.snap_max_bars_in_trade} bars")

    def _activate_trend(self, *, direction: str, entry_ema: str) -> None:
        self._active_mode = "trend"
        self._active_direction = direction
        self._bars_in_trade = 0
        self._trend_entry_ema = entry_ema
        self._trend_using_trail = False
        self._snap_stop_level = None
        self._pending_close = False
        self._close_reason = None

    def _activate_snap(self, *, direction: str, stop_level: Optional[float]) -> None:
        self._active_mode = "snap"
        self._active_direction = direction
        self._bars_in_trade = 0
        self._trend_entry_ema = None
        self._trend_using_trail = False
        self._snap_stop_level = stop_level
        self._pending_close = False
        self._close_reason = None

    def _queue_close(self, reason: str) -> None:
        self._pending_close = True
        self._close_reason = reason

    def _reset_setup(self) -> None:
        self._setup_direction = None
        self._setup_excursion = None
        self._setup_bars = 0

    def _reset_position(self) -> None:
        self._active_mode = None
        self._active_direction = None
        self._bars_in_trade = 0
        self._trend_entry_ema = None
        self._trend_using_trail = False
        self._snap_stop_level = None
        self._pending_close = False
        self._close_reason = None


def _resolve_regime(
    *,
    fast_value: float,
    slow_value: float,
    price: float,
    trend_min_spread_pct: float,
    chop_max_spread_pct: float,
) -> str:
    if price <= 0:
        return "neutral"
    spread_pct = abs(fast_value - slow_value) / price * 100.0
    if spread_pct >= trend_min_spread_pct:
        return "trend"
    if spread_pct <= chop_max_spread_pct:
        return "chop"
    return "neutral"


def _trend_direction(*, fast_value: float, slow_value: float) -> Optional[str]:
    if fast_value > slow_value:
        return "call"
    if fast_value < slow_value:
        return "put"
    return None


def _sorted_ema_keys(ema_snapshot: dict) -> List[str]:
    keys = [key for key in ema_snapshot.keys() if key != "x"]
    return sorted(keys, key=_ema_sort_key)


def _ema_sort_key(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def _get_ema_value(ema_snapshot: dict, key: str) -> Optional[float]:
    value = ema_snapshot.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_high(candle: dict, open_price: float, close_price: float) -> float:
    high_value = _to_float(candle.get("high"))
    if high_value is None:
        return max(open_price, close_price)
    return high_value


def _resolve_low(candle: dict, open_price: float, close_price: float) -> float:
    low_value = _to_float(candle.get("low"))
    if low_value is None:
        return min(open_price, close_price)
    return low_value


def _crossed_up(open_price: float, close_price: float, level: float) -> bool:
    return open_price <= level < close_price


def _crossed_down(open_price: float, close_price: float, level: float) -> bool:
    return open_price >= level > close_price


def _tag_matches(base: str, tag: Optional[str]) -> bool:
    if not tag:
        return False
    if tag == base:
        return True
    return tag.startswith(f"{base}-")


def build_strategy() -> object:
    if not IS_ENABLED:
        return None
    base_name = STRATEGY_BASE_NAME
    mode = str(MODE or "single").lower()
    if mode == "multi":
        timeframes = TIMEFRAMES if isinstance(TIMEFRAMES, list) else []
        if not timeframes:
            timeframes = [SINGLE_TIMEFRAME] if SINGLE_TIMEFRAME else ["5M"]
        strategies: List[EmaRegimeFusionStrategy] = []
        for tf in timeframes:
            if not tf:
                continue
            name = f"{base_name}-{str(tf).lower()}"
            strategies.append(
                EmaRegimeFusionStrategy(
                    timeframe=str(tf),
                    fast=FAST_EMA,
                    slow=SLOW_EMA,
                    trail_stop_ema=TRAIL_STOP_EMA,
                    trend_min_spread_pct=TREND_MIN_SPREAD_PCT,
                    chop_max_spread_pct=CHOP_MAX_SPREAD_PCT,
                    snap_setup_max_bars=SNAP_SETUP_MAX_BARS,
                    snap_max_bars_in_trade=SNAP_MAX_BARS_IN_TRADE,
                    name=name,
                )
            )
        return strategies or EmaRegimeFusionStrategy(
            timeframe=SINGLE_TIMEFRAME or "5M",
            fast=FAST_EMA,
            slow=SLOW_EMA,
            trail_stop_ema=TRAIL_STOP_EMA,
            trend_min_spread_pct=TREND_MIN_SPREAD_PCT,
            chop_max_spread_pct=CHOP_MAX_SPREAD_PCT,
            snap_setup_max_bars=SNAP_SETUP_MAX_BARS,
            snap_max_bars_in_trade=SNAP_MAX_BARS_IN_TRADE,
            name=base_name,
        )
    single_tf = SINGLE_TIMEFRAME or (TIMEFRAMES[0] if TIMEFRAMES else "5M")
    return EmaRegimeFusionStrategy(
        timeframe=single_tf,
        fast=FAST_EMA,
        slow=SLOW_EMA,
        trail_stop_ema=TRAIL_STOP_EMA,
        trend_min_spread_pct=TREND_MIN_SPREAD_PCT,
        chop_max_spread_pct=CHOP_MAX_SPREAD_PCT,
        snap_setup_max_bars=SNAP_SETUP_MAX_BARS,
        snap_max_bars_in_trade=SNAP_MAX_BARS_IN_TRADE,
        name=base_name,
    )
