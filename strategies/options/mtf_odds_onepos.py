from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .types import PositionAction, StrategyContext, StrategySignal


STRATEGY_BASE_NAME = "mtf-odds-onepos"
MODE = "single"  # kept for compatibility; strategy enforces one-instance behavior
SINGLE_TIMEFRAME = "2M"
TIMEFRAMES = ["2M", "5M", "15M"]
SIGNAL_TIMEFRAME = "2M"
FAST_EMA = "13"
SLOW_EMA = "48"
TIMEFRAME_WEIGHTS: List[Tuple[str, float]] = [("2M", 1.0), ("5M", 1.5), ("15M", 2.0)]
ODDS_DECAY = 0.80
ENTRY_THRESHOLD = 4.0
EXIT_NEUTRAL_THRESHOLD = 0.80
EXIT_REVERSE_THRESHOLD = 2.0
MAX_BARS_IN_TRADE = 8
IMPULSE_MIN_BODY_RATIO = 0.55
IS_ENABLED = True
STRATEGY_DESCRIPTION = (
    "Single-position multi-timeframe odds engine. Every closed candle contributes weighted "
    "bull/bear evidence (2M/5M/15M), smoothed into an odds score. Entries trigger on the "
    "signal timeframe only, with higher-timeframe bias checks. Exits occur on odds fade/reversal, "
    "signal-timeframe EMA stop breaks, or a max-bars timeout."
)
STRATEGY_ASSESSMENT = ""


class MtfOddsOnePosStrategy:
    name = STRATEGY_BASE_NAME

    def __init__(
        self,
        *,
        signal_timeframe: str = "2M",
        monitored_timeframes: Optional[Sequence[str]] = None,
        fast: str = "13",
        slow: str = "48",
        weights: Optional[Sequence[Tuple[str, float]]] = None,
        odds_decay: float = 0.80,
        entry_threshold: float = 4.0,
        exit_neutral_threshold: float = 0.80,
        exit_reverse_threshold: float = 2.0,
        max_bars_in_trade: int = 8,
        impulse_min_body_ratio: float = 0.55,
        name: Optional[str] = None,
    ) -> None:
        self.signal_timeframe = _norm_tf(signal_timeframe)
        monitored = list(monitored_timeframes or [self.signal_timeframe])
        normalized = [_norm_tf(tf) for tf in monitored if tf]
        if self.signal_timeframe not in normalized:
            normalized.append(self.signal_timeframe)
        self.monitored_timeframes = normalized
        self._monitored_set = set(normalized)
        self.fast = fast
        self.slow = slow
        self.weight_by_tf = _build_weight_map(weights or TIMEFRAME_WEIGHTS)
        self.odds_decay = float(odds_decay)
        self.entry_threshold = float(entry_threshold)
        self.exit_neutral_threshold = float(exit_neutral_threshold)
        self.exit_reverse_threshold = float(exit_reverse_threshold)
        self.max_bars_in_trade = int(max_bars_in_trade)
        self.impulse_min_body_ratio = float(impulse_min_body_ratio)
        if name:
            self.name = name

        self._odds: float = 0.0
        self._bias_by_tf: Dict[str, Optional[str]] = {}

        self._active_direction: Optional[str] = None
        self._bars_in_trade: int = 0
        self._pending_close: bool = False
        self._close_reason: Optional[str] = None

    def on_candle_close(self, context: StrategyContext) -> Optional[StrategySignal]:
        tf = _norm_tf(context.timeframe)
        if tf not in self._monitored_set:
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

        card_score = _card_score(
            open_price=open_price,
            close_price=close_price,
            high_price=high_price,
            low_price=low_price,
            fast_value=fast_value,
            slow_value=slow_value,
            impulse_min_body_ratio=self.impulse_min_body_ratio,
        )
        weight = self.weight_by_tf.get(tf, 1.0)
        self._odds = (self._odds * self.odds_decay) + (card_score * weight)
        self._bias_by_tf[tf] = _trend_direction(fast_value, slow_value)

        if self._active_direction:
            if tf == self.signal_timeframe:
                self._bars_in_trade += 1
                self._evaluate_signal_tf_stop(
                    open_price=open_price,
                    close_price=close_price,
                    fast_value=fast_value,
                )
            self._evaluate_odds_exit()
            return None

        if tf != self.signal_timeframe:
            return None
        if not self._has_full_bias_snapshot():
            return None

        bullish_votes, bearish_votes = self._bias_votes()
        bias_15m = self._bias_by_tf.get(_norm_tf("15M"))

        if (
            self._odds >= self.entry_threshold
            and bullish_votes >= bearish_votes
            and bias_15m != "put"
        ):
            self._activate_position("call")
            return StrategySignal(
                direction="call",
                reason=(
                    f"Odds long: score={self._odds:.2f}, votes={bullish_votes}/{bearish_votes}, "
                    f"signal_tf={self.signal_timeframe}"
                ),
            )

        if (
            self._odds <= -self.entry_threshold
            and bearish_votes >= bullish_votes
            and bias_15m != "call"
        ):
            self._activate_position("put")
            return StrategySignal(
                direction="put",
                reason=(
                    f"Odds short: score={self._odds:.2f}, votes={bullish_votes}/{bearish_votes}, "
                    f"signal_tf={self.signal_timeframe}"
                ),
            )
        return None

    def on_position_update(self, updates):
        if not self._pending_close or not updates:
            return None
        for update in updates:
            if update.strategy_tag and not _tag_matches(self.name, update.strategy_tag):
                continue
            reason = self._close_reason or "Exit"
            self._reset_position_state()
            return PositionAction(
                action="close",
                position_id=update.position_id,
                reason=reason,
                timeframe=self.signal_timeframe,
            )
        return None

    def _has_full_bias_snapshot(self) -> bool:
        for tf in self.monitored_timeframes:
            bias = self._bias_by_tf.get(tf)
            if bias not in ("call", "put"):
                return False
        return True

    def _bias_votes(self) -> Tuple[int, int]:
        bullish = 0
        bearish = 0
        for tf in self.monitored_timeframes:
            bias = self._bias_by_tf.get(tf)
            if bias == "call":
                bullish += 1
            elif bias == "put":
                bearish += 1
        return bullish, bearish

    def _activate_position(self, direction: str) -> None:
        self._active_direction = direction
        self._bars_in_trade = 0
        self._pending_close = False
        self._close_reason = None

    def _evaluate_signal_tf_stop(
        self,
        *,
        open_price: float,
        close_price: float,
        fast_value: float,
    ) -> None:
        if self._pending_close:
            return
        if self._active_direction == "call" and _crossed_down(open_price, close_price, fast_value):
            self._queue_close(f"Stop: {self.signal_timeframe} candle broke EMA {self.fast} down")
            return
        if self._active_direction == "put" and _crossed_up(open_price, close_price, fast_value):
            self._queue_close(f"Stop: {self.signal_timeframe} candle broke EMA {self.fast} up")
            return
        if self._bars_in_trade >= self.max_bars_in_trade:
            self._queue_close(f"Timeout: {self.max_bars_in_trade} bars on {self.signal_timeframe}")

    def _evaluate_odds_exit(self) -> None:
        if self._pending_close or not self._active_direction:
            return
        if abs(self._odds) <= self.exit_neutral_threshold:
            self._queue_close(f"Odds faded to neutral ({self._odds:.2f})")
            return
        if self._active_direction == "call" and self._odds <= -self.exit_reverse_threshold:
            self._queue_close(f"Odds reversed bearish ({self._odds:.2f})")
            return
        if self._active_direction == "put" and self._odds >= self.exit_reverse_threshold:
            self._queue_close(f"Odds reversed bullish ({self._odds:.2f})")

    def _queue_close(self, reason: str) -> None:
        self._pending_close = True
        self._close_reason = reason

    def _reset_position_state(self) -> None:
        self._active_direction = None
        self._bars_in_trade = 0
        self._pending_close = False
        self._close_reason = None


def _card_score(
    *,
    open_price: float,
    close_price: float,
    high_price: float,
    low_price: float,
    fast_value: float,
    slow_value: float,
    impulse_min_body_ratio: float,
) -> float:
    score = 0.0

    trend = _trend_direction(fast_value, slow_value)
    if trend == "call":
        score += 1.0
    elif trend == "put":
        score -= 1.0

    if close_price > fast_value:
        score += 1.0
    elif close_price < fast_value:
        score -= 1.0

    score += _impulse_card(
        open_price=open_price,
        close_price=close_price,
        high_price=high_price,
        low_price=low_price,
        min_body_ratio=impulse_min_body_ratio,
    )

    if _crossed_up(open_price, close_price, fast_value):
        score += 1.5
    elif _crossed_down(open_price, close_price, fast_value):
        score -= 1.5

    return score


def _impulse_card(
    *,
    open_price: float,
    close_price: float,
    high_price: float,
    low_price: float,
    min_body_ratio: float,
) -> float:
    candle_range = max(high_price - low_price, 0.0)
    if candle_range <= 0.0:
        return 0.0
    body = abs(close_price - open_price)
    if (body / candle_range) < min_body_ratio:
        return 0.0
    if close_price > open_price:
        return 1.0
    if close_price < open_price:
        return -1.0
    return 0.0


def _build_weight_map(weights: Sequence[Tuple[str, float]]) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for tf, weight in weights:
        key = _norm_tf(tf)
        if not key:
            continue
        try:
            result[key] = float(weight)
        except (TypeError, ValueError):
            continue
    return result


def _norm_tf(value: str) -> str:
    return str(value or "").strip().upper()


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


def _trend_direction(fast_value: float, slow_value: float) -> Optional[str]:
    if fast_value > slow_value:
        return "call"
    if fast_value < slow_value:
        return "put"
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
    # This strategy intentionally returns one instance to preserve one-position behavior.
    return MtfOddsOnePosStrategy(
        signal_timeframe=SIGNAL_TIMEFRAME or SINGLE_TIMEFRAME or "2M",
        monitored_timeframes=TIMEFRAMES if isinstance(TIMEFRAMES, list) else [SINGLE_TIMEFRAME or "2M"],
        fast=FAST_EMA,
        slow=SLOW_EMA,
        weights=TIMEFRAME_WEIGHTS,
        odds_decay=ODDS_DECAY,
        entry_threshold=ENTRY_THRESHOLD,
        exit_neutral_threshold=EXIT_NEUTRAL_THRESHOLD,
        exit_reverse_threshold=EXIT_REVERSE_THRESHOLD,
        max_bars_in_trade=MAX_BARS_IN_TRADE,
        impulse_min_body_ratio=IMPULSE_MIN_BODY_RATIO,
        name=STRATEGY_BASE_NAME,
    )
