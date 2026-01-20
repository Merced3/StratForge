from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class EconomicEvent:
    date: date
    time_label: str
    title: str
    starts_at: Optional[datetime] = None
    impact: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None


@dataclass(frozen=True)
class EconomicCalendarWeek:
    week_start: date
    week_end: date
    timezone: str
    source: str
    events: Tuple[EconomicEvent, ...]

    def contains(self, day: date) -> bool:
        return self.week_start <= day <= self.week_end
