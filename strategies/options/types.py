from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class StrategyContext:
    symbol: str
    timeframe: str
    candle: dict
    ema: Optional[dict]
    timestamp: datetime


@dataclass(frozen=True)
class StrategySignal:
    direction: str
    reason: str


@dataclass(frozen=True)
class PositionAction:
    action: str  # "close" | "trim" | "add"
    position_id: str
    quantity: Optional[int] = None
    reason: str = ""
    timeframe: Optional[str] = None
