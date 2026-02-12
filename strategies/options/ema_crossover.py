from __future__ import annotations

from typing import List, Optional

from .exit_rules import ProfitTargetPlan, ProfitTargetStep
from .types import StrategyContext, StrategySignal

STRATEGY_BASE_NAME = "ema-crossover"
MODE = "single"  # "single" or "multi"
SINGLE_TIMEFRAME = "15M"
TIMEFRAMES = ["2M", "5M", "15M"]
FAST_EMA = "13"
SLOW_EMA = "48"
IS_ENABLED = True
STRATEGY_DESCRIPTION = (
    "Tracks a fast/slow EMA crossover on the configured timeframe. "
    "Enters on crossover and flips direction when the cross reverses. "
    "Uses a profit target plan (trim at 100%, close at 200%)."
)
STRATEGY_ASSESSMENT = ""


class EmaCrossoverStrategy:
    name = STRATEGY_BASE_NAME

    def __init__(
        self,
        *,
        timeframe: str = "15M",
        fast: str = "13",
        slow: str = "48",
        name: Optional[str] = None,
    ) -> None:
        self.timeframe = timeframe
        self.fast = fast
        self.slow = slow
        if name:
            self.name = name
        self._last_direction: Optional[str] = None
        # Take-profit plan uses watcher updates for trims/closes.
        self.exit_plan = ProfitTargetPlan([
            ProfitTargetStep(
                target_pct=100.0,
                action="trim",
                fraction=0.5,
                allow_full_close=False,
            ),
            ProfitTargetStep(
                target_pct=200.0, 
                action="close",
            ),
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


def build_strategy() -> object:
    if not IS_ENABLED:
        return None
    base_name = STRATEGY_BASE_NAME
    mode = str(MODE or "single").lower()
    if mode == "multi":
        timeframes = TIMEFRAMES if isinstance(TIMEFRAMES, list) else []
        if not timeframes:
            timeframes = [SINGLE_TIMEFRAME] if SINGLE_TIMEFRAME else ["15M"]
        strategies: List[EmaCrossoverStrategy] = []
        for tf in timeframes:
            if not tf:
                continue
            name = f"{base_name}-{str(tf).lower()}"
            strategies.append(
                EmaCrossoverStrategy(
                    timeframe=str(tf),
                    fast=FAST_EMA,
                    slow=SLOW_EMA,
                    name=name,
                )
            )
        return strategies or EmaCrossoverStrategy(
            timeframe=SINGLE_TIMEFRAME or "15M",
            fast=FAST_EMA,
            slow=SLOW_EMA,
            name=base_name,
        )
    single_tf = SINGLE_TIMEFRAME or (TIMEFRAMES[0] if TIMEFRAMES else "15M")
    return EmaCrossoverStrategy(
        timeframe=single_tf,
        fast=FAST_EMA,
        slow=SLOW_EMA,
        name=base_name,
    )
