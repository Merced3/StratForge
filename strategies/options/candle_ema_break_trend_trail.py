from __future__ import annotations

from typing import List, Optional

from .types import PositionAction, StrategyContext, StrategySignal


STRATEGY_BASE_NAME = "candle-ema-break-trend-trail"
MODE = "multi"  # "single" or "multi"
SINGLE_TIMEFRAME = "5M"
TIMEFRAMES = ["5M", "15M"] # , "2M"] 
FAST_EMA = "13"
SLOW_EMA = "48"
TRAIL_STOP_EMA = FAST_EMA
IS_ENABLED = True  # Set to True to enable this strategy
STRATEGY_DESCRIPTION = (
    "Candle/EMA break entries filtered by trend alignment (fast vs slow EMA). "
    "Uses the crossed EMA as the initial stop, then switches stop control to a faster "
    "EMA once it moves beyond the entry EMA in-trend to reduce giveback."
)
STRATEGY_ASSESSMENT = ""


class CandleEmaBreakTrendTrailStrategy:
    name = STRATEGY_BASE_NAME

    def __init__(
        self,
        *,
        timeframe: str = "2M",
        fast: str = "13",
        slow: str = "48",
        trail_stop_ema: str = "13",
        name: Optional[str] = None,
    ) -> None:
        self.timeframe = timeframe
        self.fast = fast
        self.slow = slow
        self.trail_stop_ema = trail_stop_ema
        if name:
            self.name = name
        self._active_direction: Optional[str] = None
        self._entry_ema: Optional[str] = None
        self._trail_armed: bool = False
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

        if self._active_direction and self._entry_ema:
            stop_ema_key = self._resolve_stop_ema_key(context.ema)
            if not stop_ema_key:
                return None
            stop_ema_value = _get_ema_value(context.ema, stop_ema_key)
            if stop_ema_value is None:
                return None
            if self._active_direction == "call":
                if _crossed_down(open_price, close_price, stop_ema_value):
                    stage = "trail" if self._trail_armed else "initial"
                    self._pending_stop = True
                    self._stop_reason = (
                        f"Stop ({stage}): candle broke EMA {stop_ema_key} down"
                    )
            else:
                if _crossed_up(open_price, close_price, stop_ema_value):
                    stage = "trail" if self._trail_armed else "initial"
                    self._pending_stop = True
                    self._stop_reason = (
                        f"Stop ({stage}): candle broke EMA {stop_ema_key} up"
                    )
            return None

        trend_direction = _trend_direction(context.ema, self.fast, self.slow)
        if not trend_direction:
            return None

        for ema_key in _sorted_ema_keys(context.ema):
            ema_value = _get_ema_value(context.ema, ema_key)
            if ema_value is None:
                continue
            if trend_direction == "call" and _crossed_up(open_price, close_price, ema_value):
                self._activate_position(direction="call", entry_ema=ema_key)
                return StrategySignal(
                    direction="call",
                    reason=(
                        f"Candle broke EMA {ema_key} up with fast EMA "
                        f"{self.fast} above slow EMA {self.slow}"
                    ),
                )
            if trend_direction == "put" and _crossed_down(open_price, close_price, ema_value):
                self._activate_position(direction="put", entry_ema=ema_key)
                return StrategySignal(
                    direction="put",
                    reason=(
                        f"Candle broke EMA {ema_key} down with fast EMA "
                        f"{self.fast} below slow EMA {self.slow}"
                    ),
                )
        return None

    def on_position_update(self, updates):
        if not updates:
            return None

        if not self._pending_stop:
            return None

        update = updates[0]
        if update.strategy_tag and not _tag_matches(self.name, update.strategy_tag):
            return None

        reason = self._stop_reason or "Stop"
        self._pending_stop = False
        self._stop_reason = None
        self._active_direction = None
        self._entry_ema = None
        self._trail_armed = False
        return PositionAction(
            action="close",
            position_id=update.position_id,
            reason=reason,
            timeframe=self.timeframe,
        )

    def _activate_position(self, *, direction: str, entry_ema: str) -> None:
        self._active_direction = direction
        self._entry_ema = entry_ema
        self._trail_armed = False
        self._pending_stop = False
        self._stop_reason = None

    def _resolve_stop_ema_key(self, ema_snapshot: dict) -> Optional[str]:
        self._trail_armed = self._should_use_trail_stop(ema_snapshot)
        if self._trail_armed:
            trail_value = _get_ema_value(ema_snapshot, self.trail_stop_ema)
            if trail_value is not None:
                return self.trail_stop_ema
        return self._entry_ema

    def _should_use_trail_stop(self, ema_snapshot: dict) -> bool:
        if not self._entry_ema or not self._active_direction:
            return False
        entry_value = _get_ema_value(ema_snapshot, self._entry_ema)
        trail_value = _get_ema_value(ema_snapshot, self.trail_stop_ema)
        if entry_value is None or trail_value is None:
            return False
        if self._active_direction == "call":
            return trail_value > entry_value
        if self._active_direction == "put":
            return trail_value < entry_value
        return False


def _trend_direction(ema_snapshot: dict, fast: str, slow: str) -> Optional[str]:
    fast_value = _get_ema_value(ema_snapshot, fast)
    slow_value = _get_ema_value(ema_snapshot, slow)
    if fast_value is None or slow_value is None:
        return None
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
        strategies: List[CandleEmaBreakTrendTrailStrategy] = []
        for tf in timeframes:
            if not tf:
                continue
            name = f"{base_name}-{str(tf).lower()}"
            strategies.append(
                CandleEmaBreakTrendTrailStrategy(
                    timeframe=str(tf),
                    fast=FAST_EMA,
                    slow=SLOW_EMA,
                    trail_stop_ema=TRAIL_STOP_EMA,
                    name=name,
                )
            )
        return strategies or CandleEmaBreakTrendTrailStrategy(
            timeframe=SINGLE_TIMEFRAME or "2M",
            fast=FAST_EMA,
            slow=SLOW_EMA,
            trail_stop_ema=TRAIL_STOP_EMA,
            name=base_name,
        )
    single_tf = SINGLE_TIMEFRAME or (TIMEFRAMES[0] if TIMEFRAMES else "2M")
    return CandleEmaBreakTrendTrailStrategy(
        timeframe=single_tf,
        fast=FAST_EMA,
        slow=SLOW_EMA,
        trail_stop_ema=TRAIL_STOP_EMA,
        name=base_name,
    )
