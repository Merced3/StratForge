from __future__ import annotations

from typing import List, Optional

from .types import PositionAction, StrategyContext, StrategySignal


IS_ENABLED = True # Set to True to enable this strategy
STRATEGY_BASE_NAME = "candle-ema-break"
MODE = "single"  # "single" or "multi"
SINGLE_TIMEFRAME = "2M"
TIMEFRAMES = ["2M", "5M", "15M"]
STRATEGY_DESCRIPTION = (
    "Triggers when a candle body crosses above/below an EMA and sets direction. "
    "Exits when a candle breaks back through the same EMA to stop out. "
    "Designed to capture immediate momentum off EMA breaks."
)
#STRATEGY_ASSESSMENT = (
#    "Disabled: negative EV with high trade frequency; exits on slower EMAs lag "
#    "and often give back gains. Fires from the hip with not optimal exits."
#)


class CandleEmaBreakStrategy:
    name = STRATEGY_BASE_NAME

    def __init__(self, *, timeframe: str = "2M", name: Optional[str] = None) -> None:
        self.timeframe = timeframe
        if name:
            self.name = name
        self._active_direction: Optional[str] = None
        self._active_ema: Optional[str] = None
        self._pending_stop: bool = False
        self._stop_reason: Optional[str] = None

    def on_candle_close(self, context: StrategyContext) -> Optional[StrategySignal]:
        if context.timeframe != self.timeframe:
            return None

        if not context.ema:
            return None

        candle = context.candle or {}
        open_price = candle.get("open")
        close_price = candle.get("close")
        if open_price is None or close_price is None:
            return None

        if self._active_direction and self._active_ema:
            ema_value = _get_ema_value(context.ema, self._active_ema)
            if ema_value is None:
                return None
            if self._active_direction == "call":
                if _crossed_down(open_price, close_price, ema_value):
                    self._pending_stop = True
                    self._stop_reason = f"Stop: candle broke EMA {self._active_ema} down"
            else:
                if _crossed_up(open_price, close_price, ema_value):
                    self._pending_stop = True
                    self._stop_reason = f"Stop: candle broke EMA {self._active_ema} up"
            return None

        for ema_key in _sorted_ema_keys(context.ema):
            ema_value = _get_ema_value(context.ema, ema_key)
            if ema_value is None:
                continue
            if _crossed_up(open_price, close_price, ema_value):
                self._active_direction = "call"
                self._active_ema = ema_key
                self._pending_stop = False
                self._stop_reason = None
                return StrategySignal(
                    direction="call",
                    reason=f"Candle broke EMA {ema_key} up",
                )
            if _crossed_down(open_price, close_price, ema_value):
                self._active_direction = "put"
                self._active_ema = ema_key
                self._pending_stop = False
                self._stop_reason = None
                return StrategySignal(
                    direction="put",
                    reason=f"Candle broke EMA {ema_key} down",
                )
        return None

    def on_position_update(self, updates):
        if not self._pending_stop or not updates:
            return None
        update = updates[0]
        if update.strategy_tag and not _tag_matches(self.name, update.strategy_tag):
            return None
        self._pending_stop = False
        self._active_direction = None
        self._active_ema = None
        reason = self._stop_reason or "Stop"
        self._stop_reason = None
        return PositionAction(
            action="close",
            position_id=update.position_id,
            reason=reason,
            timeframe=self.timeframe,
        )


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


def _crossed_up(open_price: float, close_price: float, ema_value: float) -> bool:
    return open_price <= ema_value < close_price


def _crossed_down(open_price: float, close_price: float, ema_value: float) -> bool:
    return open_price >= ema_value > close_price


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
            timeframes = [SINGLE_TIMEFRAME] if SINGLE_TIMEFRAME else ["2M"]
        strategies: List[CandleEmaBreakStrategy] = []
        for tf in timeframes:
            if not tf:
                continue
            name = f"{base_name}-{str(tf).lower()}"
            strategies.append(CandleEmaBreakStrategy(timeframe=str(tf), name=name))
        return strategies or CandleEmaBreakStrategy(
            timeframe=SINGLE_TIMEFRAME or "2M",
            name=base_name,
        )
    single_tf = SINGLE_TIMEFRAME or (TIMEFRAMES[0] if TIMEFRAMES else "2M")
    return CandleEmaBreakStrategy(timeframe=single_tf, name=base_name)
