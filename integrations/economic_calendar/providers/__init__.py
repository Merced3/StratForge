from datetime import date
from typing import Protocol

from ..models import EconomicCalendarWeek
from .trading_economics import TradingEconomicsCalendarProvider


class EconomicCalendarProvider(Protocol):
    name: str
    timezone: str

    async def fetch_week(self, week_start: date, week_end: date) -> EconomicCalendarWeek:
        ...


__all__ = [
    "EconomicCalendarProvider",
    "TradingEconomicsCalendarProvider",
]
