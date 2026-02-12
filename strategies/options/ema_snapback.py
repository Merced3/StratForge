from __future__ import annotations

from typing import List, Optional

from .types import PositionAction, StrategyContext, StrategySignal


STRATEGY_BASE_NAME = "ema-snapback"
MODE = "single"  # "single" or "multi"
SINGLE_TIMEFRAME = "5M"
TIMEFRAMES = ["2M", "5M", "15M"]
FAST_EMA = "13"
SLOW_EMA = "48"
CHOP_MAX_SPREAD_PCT = 0.12
SETUP_MAX_BARS = 4
MAX_BARS_IN_TRADE = 6
IS_ENABLED = False  # Set to True to enable this strategy
STRATEGY_DESCRIPTION = (
    "Mean-reversion strategy for choppy conditions. Looks for extension beyond the slow EMA "
    "and enters on a snapback through the fast EMA. Uses excursion low/high as stop and exits "
    "on slow EMA touch or max bars in trade."
)
STRATEGY_ASSESSMENT = ""


class EmaSnapbackStrategy:
    name = STRATEGY_BASE_NAME

    def __init__(
        self,
        *,
        timeframe: str = "5M",
        fast: str = "13",
        slow: str = "48",
        chop_max_spread_pct: float = 0.12,
        setup_max_bars: int = 4,
        max_bars_in_trade: int = 6,
        name: Optional[str] = None,
    ) -> None:
        self.timeframe = timeframe
        self.fast = fast
        self.slow = slow
        self.chop_max_spread_pct = float(chop_max_spread_pct)
        self.setup_max_bars = int(setup_max_bars)
        self.max_bars_in_trade = int(max_bars_in_trade)
        if name:
            self.name = name

        self._pending_direction: Optional[str] = None
        self._pending_excursion: Optional[float] = None
        self._pending_bars: int = 0

        self._active_direction: Optional[str] = None
        self._stop_level: Optional[float] = None
        self._bars_in_trade: int = 0
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

        if self._active_direction:
            self._bars_in_trade += 1
            self._evaluate_active_trade(
                open_price=open_price,
                close_price=close_price,
                high_price=high_price,
                low_price=low_price,
                slow_value=slow_value,
            )
            return None

        if not _is_chop(
            fast_value=fast_value,
            slow_value=slow_value,
            price=close_price,
            max_spread_pct=self.chop_max_spread_pct,
        ):
            self._reset_setup()
            return None

        if self._pending_direction:
            self._pending_bars += 1
            if self._pending_bars > self.setup_max_bars:
                self._reset_setup()

        self._update_setup(
            low_price=low_price,
            high_price=high_price,
            slow_value=slow_value,
        )

        if self._pending_direction == "call" and _crossed_up(open_price, close_price, fast_value):
            stop_level = self._pending_excursion if self._pending_excursion is not None else low_price
            self._activate_position(direction="call", stop_level=stop_level)
            self._reset_setup()
            return StrategySignal(
                direction="call",
                reason=(
                    f"Snapback call: extension below EMA {self.slow}, "
                    f"reclaim above EMA {self.fast}"
                ),
            )

        if self._pending_direction == "put" and _crossed_down(open_price, close_price, fast_value):
            stop_level = self._pending_excursion if self._pending_excursion is not None else high_price
            self._activate_position(direction="put", stop_level=stop_level)
            self._reset_setup()
            return StrategySignal(
                direction="put",
                reason=(
                    f"Snapback put: extension above EMA {self.slow}, "
                    f"reclaim below EMA {self.fast}"
                ),
            )

        return None

    def on_position_update(self, updates):
        if not self._pending_close or not updates:
            return None
        update = updates[0]
        if update.strategy_tag and not _tag_matches(self.name, update.strategy_tag):
            return None
        reason = self._close_reason or "Exit"
        self._reset_position()
        return PositionAction(
            action="close",
            position_id=update.position_id,
            reason=reason,
            timeframe=self.timeframe,
        )

    def _update_setup(self, *, low_price: float, high_price: float, slow_value: float) -> None:
        extended_down = low_price < slow_value
        extended_up = high_price > slow_value

        if extended_down and not extended_up:
            if self._pending_direction != "call":
                self._pending_direction = "call"
                self._pending_excursion = low_price
                self._pending_bars = 0
            else:
                if self._pending_excursion is None:
                    self._pending_excursion = low_price
                else:
                    self._pending_excursion = min(self._pending_excursion, low_price)
            return

        if extended_up and not extended_down:
            if self._pending_direction != "put":
                self._pending_direction = "put"
                self._pending_excursion = high_price
                self._pending_bars = 0
            else:
                if self._pending_excursion is None:
                    self._pending_excursion = high_price
                else:
                    self._pending_excursion = max(self._pending_excursion, high_price)
            return

        if self._pending_direction == "call" and extended_down:
            if self._pending_excursion is None:
                self._pending_excursion = low_price
            else:
                self._pending_excursion = min(self._pending_excursion, low_price)
            return

        if self._pending_direction == "put" and extended_up:
            if self._pending_excursion is None:
                self._pending_excursion = high_price
            else:
                self._pending_excursion = max(self._pending_excursion, high_price)

    def _evaluate_active_trade(
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

        if self._stop_level is not None:
            if self._active_direction == "call" and _crossed_down(open_price, close_price, self._stop_level):
                self._queue_close(f"Stop: broke excursion low {self._stop_level:.2f}")
                return
            if self._active_direction == "put" and _crossed_up(open_price, close_price, self._stop_level):
                self._queue_close(f"Stop: broke excursion high {self._stop_level:.2f}")
                return

        if self._active_direction == "call" and high_price >= slow_value:
            self._queue_close(f"Target: touched EMA {self.slow}")
            return
        if self._active_direction == "put" and low_price <= slow_value:
            self._queue_close(f"Target: touched EMA {self.slow}")
            return

        if self._bars_in_trade >= self.max_bars_in_trade:
            self._queue_close(f"Timeout: {self.max_bars_in_trade} bars in trade")

    def _activate_position(self, *, direction: str, stop_level: Optional[float]) -> None:
        self._active_direction = direction
        self._stop_level = stop_level
        self._bars_in_trade = 0
        self._pending_close = False
        self._close_reason = None

    def _queue_close(self, reason: str) -> None:
        self._pending_close = True
        self._close_reason = reason

    def _reset_setup(self) -> None:
        self._pending_direction = None
        self._pending_excursion = None
        self._pending_bars = 0

    def _reset_position(self) -> None:
        self._active_direction = None
        self._stop_level = None
        self._bars_in_trade = 0
        self._pending_close = False
        self._close_reason = None


def _is_chop(*, fast_value: float, slow_value: float, price: float, max_spread_pct: float) -> bool:
    if price <= 0:
        return False
    spread_pct = abs(fast_value - slow_value) / price * 100.0
    return spread_pct <= max_spread_pct


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


def _get_ema_value(ema_snapshot: dict, key: str) -> Optional[float]:
    value = ema_snapshot.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        strategies: List[EmaSnapbackStrategy] = []
        for tf in timeframes:
            if not tf:
                continue
            name = f"{base_name}-{str(tf).lower()}"
            strategies.append(
                EmaSnapbackStrategy(
                    timeframe=str(tf),
                    fast=FAST_EMA,
                    slow=SLOW_EMA,
                    chop_max_spread_pct=CHOP_MAX_SPREAD_PCT,
                    setup_max_bars=SETUP_MAX_BARS,
                    max_bars_in_trade=MAX_BARS_IN_TRADE,
                    name=name,
                )
            )
        return strategies or EmaSnapbackStrategy(
            timeframe=SINGLE_TIMEFRAME or "5M",
            fast=FAST_EMA,
            slow=SLOW_EMA,
            chop_max_spread_pct=CHOP_MAX_SPREAD_PCT,
            setup_max_bars=SETUP_MAX_BARS,
            max_bars_in_trade=MAX_BARS_IN_TRADE,
            name=base_name,
        )
    single_tf = SINGLE_TIMEFRAME or (TIMEFRAMES[0] if TIMEFRAMES else "5M")
    return EmaSnapbackStrategy(
        timeframe=single_tf,
        fast=FAST_EMA,
        slow=SLOW_EMA,
        chop_max_spread_pct=CHOP_MAX_SPREAD_PCT,
        setup_max_bars=SETUP_MAX_BARS,
        max_bars_in_trade=MAX_BARS_IN_TRADE,
        name=base_name,
    )
