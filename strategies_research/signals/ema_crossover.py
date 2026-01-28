from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from strategies_research.types import ResearchContext, ResearchSignal
from utils.json_utils import read_config

CrossPair = Tuple[int, int]
DEFAULT_PAIRS: Tuple[CrossPair, ...] = ((13, 48), (48, 200), (13, 200))


@dataclass
class EmaCrossoverSignal:
    name: str = "ema-crossover"
    cross_pairs: Optional[Sequence[CrossPair]] = None
    timeframes: Optional[Iterable[str]] = None

    def __post_init__(self) -> None:
        if not self.cross_pairs:
            self.cross_pairs = _pairs_from_config()

    def on_candle_close(self, context: ResearchContext) -> List[ResearchSignal]:
        if self.timeframes and context.timeframe not in set(self.timeframes):
            return []
        history = list(context.ema_history or [])
        if len(history) < 2:
            return []
        previous = history[-2]
        current = history[-1]
        signals: List[ResearchSignal] = []
        for fast, slow in self.cross_pairs:
            prev_fast = _ema_value(previous, fast)
            prev_slow = _ema_value(previous, slow)
            curr_fast = _ema_value(current, fast)
            curr_slow = _ema_value(current, slow)
            if None in (prev_fast, prev_slow, curr_fast, curr_slow):
                continue
            crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
            crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow
            if crossed_up:
                signals.append(
                    ResearchSignal(
                        direction="call",
                        reason=f"{fast} crossed above {slow}",
                        variant=f"{fast}x{slow}-bull",
                    )
                )
            elif crossed_down:
                signals.append(
                    ResearchSignal(
                        direction="put",
                        reason=f"{fast} crossed below {slow}",
                        variant=f"{fast}x{slow}-bear",
                    )
                )
        return signals


def build_signal() -> EmaCrossoverSignal:
    return EmaCrossoverSignal()


def _pairs_from_config() -> Sequence[CrossPair]:
    raw = read_config("EMAS") or []
    periods: List[int] = []
    for item in raw:
        value = None
        if isinstance(item, (list, tuple)) and item:
            value = item[0]
        else:
            value = item
        try:
            period = int(value)
        except (TypeError, ValueError):
            continue
        if period not in periods:
            periods.append(period)
    periods = sorted(periods)
    pairs: List[CrossPair] = []
    for idx, fast in enumerate(periods):
        for slow in periods[idx + 1 :]:
            if fast == slow:
                continue
            pairs.append((fast, slow))
    return tuple(pairs) if pairs else DEFAULT_PAIRS


def _ema_value(snapshot: dict, period: int) -> Optional[float]:
    if not isinstance(snapshot, dict):
        return None
    key = str(period)
    value = snapshot.get(key)
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
