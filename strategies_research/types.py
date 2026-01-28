from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence


@dataclass(frozen=True)
class ResearchContext:
    symbol: str
    timeframe: str
    candle: dict
    ema_history: Optional[Sequence[dict]]
    timestamp: datetime


@dataclass(frozen=True)
class ResearchSignal:
    direction: str
    reason: str
    variant: Optional[str] = None

