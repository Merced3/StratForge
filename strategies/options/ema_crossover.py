from __future__ import annotations

from typing import Optional

from .exit_rules import ProfitTargetPlan, ProfitTargetStep
from .types import StrategyContext, StrategySignal

class EmaCrossoverStrategy:
    name = "ema-crossover"

    def __init__(self, *, timeframe: str = "15M", fast: str = "13", slow: str = "48") -> None:
        self.timeframe = timeframe
        self.fast = fast
        self.slow = slow
        self._last_direction: Optional[str] = None
        # Take-profit plan uses watcher updates for trims/closes.
        self.exit_plan = ProfitTargetPlan([
            ProfitTargetStep(target_pct=100.0, action="trim", fraction=0.5),
            ProfitTargetStep(target_pct=200.0, action="close"),
        ])

    def on_position_update(self, updates):
        return self.exit_plan.evaluate(updates, timeframe=self.timeframe)

    def on_candle_close(self, context: StrategyContext) -> Optional[StrategySignal]:
        if context.timeframe != self.timeframe:
            return None

        if not context.ema:
            return None

        fast_val = context.ema.get(self.fast)
        slow_val = context.ema.get(self.slow)
        if fast_val is None or slow_val is None:
            return None

        if fast_val > slow_val:
            direction = "call"
        elif fast_val < slow_val:
            direction = "put"
        else:
            return None

        if direction == self._last_direction:
            return None

        self._last_direction = direction
        reason = f"EMA crossover {self.fast}>{self.slow}" if direction == "call" else f"EMA crossover {self.fast}<{self.slow}"
        return StrategySignal(direction=direction, reason=reason)


def build_strategy() -> EmaCrossoverStrategy:
    return EmaCrossoverStrategy()
