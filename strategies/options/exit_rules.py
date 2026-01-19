from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple

from options.position_watcher import PositionUpdate

from .types import PositionAction


@dataclass(frozen=True)
class ProfitTargetStep:
    target_pct: float
    action: str  # "trim" | "close"
    quantity: Optional[int] = None
    fraction: Optional[float] = None
    reason: Optional[str] = None


class ProfitTargetPlan:
    def __init__(self, steps: Iterable[ProfitTargetStep]) -> None:
        self._steps: List[ProfitTargetStep] = sorted(steps, key=lambda s: s.target_pct)
        self._fired: Set[Tuple[str, float]] = set()

    def evaluate(
        self,
        updates: Iterable[PositionUpdate],
        *,
        timeframe: Optional[str] = None,
    ) -> List[PositionAction]:
        actions: List[PositionAction] = []
        for update in updates:
            actions.extend(self.evaluate_update(update, timeframe=timeframe))
        return actions

    def evaluate_update(
        self,
        update: PositionUpdate,
        *,
        timeframe: Optional[str] = None,
    ) -> List[PositionAction]:
        if update.status == "closed" or update.quantity_open <= 0:
            self._clear_position(update.position_id)
            return []
        if update.unrealized_pct is None:
            return []
        actions: List[PositionAction] = []
        for step in self._steps:
            key = (update.position_id, step.target_pct)
            if key in self._fired:
                continue
            if update.unrealized_pct < step.target_pct:
                continue
            action = self._build_action(step, update, timeframe)
            if action:
                actions.append(action)
                self._fired.add(key)
        return actions

    def _build_action(
        self,
        step: ProfitTargetStep,
        update: PositionUpdate,
        timeframe: Optional[str],
    ) -> Optional[PositionAction]:
        reason = step.reason or f"TP {step.target_pct:.0f}%"
        action = step.action.lower()
        if action == "close":
            return PositionAction(
                action="close",
                position_id=update.position_id,
                reason=reason,
                timeframe=timeframe,
            )
        if action != "trim":
            raise ValueError(f"unsupported action: {step.action}")
        quantity = self._resolve_quantity(step, update)
        if quantity <= 0:
            return None
        if quantity >= update.quantity_open:
            return PositionAction(
                action="close",
                position_id=update.position_id,
                reason=reason,
                timeframe=timeframe,
            )
        return PositionAction(
            action="trim",
            position_id=update.position_id,
            quantity=quantity,
            reason=reason,
            timeframe=timeframe,
        )

    def _resolve_quantity(self, step: ProfitTargetStep, update: PositionUpdate) -> int:
        if step.quantity is not None:
            return min(step.quantity, update.quantity_open)
        if step.fraction is not None:
            if step.fraction <= 0:
                return 0
            qty = int(update.quantity_open * step.fraction)
            return max(1, qty)
        raise ValueError("trim step requires quantity or fraction")

    def _clear_position(self, position_id: str) -> None:
        to_remove = [key for key in self._fired if key[0] == position_id]
        for key in to_remove:
            self._fired.discard(key)
