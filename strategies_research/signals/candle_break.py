from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from strategies_research.types import ResearchContext, ResearchSignal


@dataclass
class CandleEmaBreakSignal:
    name: str = "candle-ema-break"
    timeframes: Optional[Iterable[str]] = None

    def on_candle_close(self, context: ResearchContext) -> List[ResearchSignal]:
        if self.timeframes and context.timeframe not in set(self.timeframes):
            return []
        candle = context.candle or {}
        open_price = candle.get("open")
        close_price = candle.get("close")
        if open_price is None or close_price is None:
            return []
        ema_snapshot = _latest_ema_snapshot(context.ema_history)
        if not ema_snapshot:
            return []
        signals: List[ResearchSignal] = []
        for ema_key in _sorted_ema_keys(ema_snapshot):
            ema_value = _ema_value(ema_snapshot, ema_key)
            if ema_value is None:
                continue
            if _crossed_up(open_price, close_price, ema_value):
                signals.append(
                    ResearchSignal(
                        direction="call",
                        reason=f"Candle broke EMA {ema_key} up",
                        variant=f"{ema_key}-up",
                    )
                )
            elif _crossed_down(open_price, close_price, ema_value):
                signals.append(
                    ResearchSignal(
                        direction="put",
                        reason=f"Candle broke EMA {ema_key} down",
                        variant=f"{ema_key}-down",
                    )
                )
        return signals


def build_signal() -> CandleEmaBreakSignal:
    return CandleEmaBreakSignal()


def _latest_ema_snapshot(history: Optional[Sequence[dict]]) -> Optional[dict]:
    if not history:
        return None
    return history[-1]


def _sorted_ema_keys(ema_snapshot: dict) -> List[str]:
    keys = [key for key in ema_snapshot.keys() if key != "x"]
    return sorted(keys, key=_ema_sort_key)


def _ema_sort_key(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def _ema_value(ema_snapshot: dict, key: str) -> Optional[float]:
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
