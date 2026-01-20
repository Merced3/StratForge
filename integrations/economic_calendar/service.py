from datetime import date, datetime, timedelta
from typing import Callable, Optional

import pytz

from error_handler import error_log_and_discord_message
from integrations.discord.templates import format_economic_news_message
from shared_state import print_log

from .models import EconomicCalendarWeek
from .providers import EconomicCalendarProvider, TradingEconomicsCalendarProvider
from .store import EconomicCalendarStore, DEFAULT_TIMEZONE


class EconomicCalendarService:
    def __init__(
        self,
        provider: Optional[EconomicCalendarProvider] = None,
        store: Optional[EconomicCalendarStore] = None,
        logger: Callable[[str], None] = print_log,
    ) -> None:
        self.logger = logger
        self.provider = provider or TradingEconomicsCalendarProvider(timezone_name=DEFAULT_TIMEZONE, logger=logger)
        self.store = store or EconomicCalendarStore(default_timezone=self.provider.timezone, logger=logger)

    async def ensure_week(self, today: Optional[date] = None) -> Optional[EconomicCalendarWeek]:
        tz = pytz.timezone(self.provider.timezone)
        if today is None:
            today = datetime.now(tz).date()

        cached_week = self.store.load_week()
        if cached_week and cached_week.contains(today):
            return cached_week

        week_start, week_end = _week_bounds(today)
        try:
            week = await self.provider.fetch_week(week_start=week_start, week_end=week_end)
        except Exception as exc:
            await error_log_and_discord_message(exc, "economic_calendar", "ensure_economic_calendar_data")
            return None

        if week:
            self.store.save_week(week)
        return week

    def build_daily_message(self, now: Optional[datetime] = None) -> str:
        week = self.store.require_week()
        tz = pytz.timezone(week.timezone)
        current = _coerce_datetime(now, tz)
        today = current.date()

        events_today = [event for event in week.events if event.date == today]
        return format_economic_news_message(events_today)

    def is_safe_to_trade(
        self,
        time_threshold: int = 20,
        sim_active: bool = False,
        now: Optional[datetime] = None,
    ) -> bool:
        if sim_active:
            return True

        week = self.store.require_week()
        tz = pytz.timezone(week.timezone)
        current = _coerce_datetime(now, tz)

        for event in week.events:
            if event.date != current.date():
                continue
            if event.starts_at is None:
                continue
            time_diff = (event.starts_at - current).total_seconds() / 60
            if 0 <= time_diff <= time_threshold:
                return False
        return True


async def ensure_economic_calendar_data() -> Optional[EconomicCalendarWeek]:
    service = EconomicCalendarService()
    return await service.ensure_week()


def setup_economic_news_message() -> str:
    service = EconomicCalendarService()
    return service.build_daily_message()


def check_order_time_to_event_time(time_threshold: int = 20, sim_active: bool = False) -> bool:
    service = EconomicCalendarService()
    return service.is_safe_to_trade(time_threshold=time_threshold, sim_active=sim_active)


def _week_bounds(today: date) -> tuple[date, date]:
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _coerce_datetime(value: Optional[datetime], tz) -> datetime:
    if value is None:
        return datetime.now(tz)
    if value.tzinfo is None:
        return tz.localize(value)
    return value.astimezone(tz)

