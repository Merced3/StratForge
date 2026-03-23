import json
from datetime import date, datetime

import pytest
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By

from integrations.economic_calendar import (
    EconomicCalendarService,
    EconomicCalendarStore,
    EconomicCalendarWeek,
)
from integrations.economic_calendar.providers.trading_economics import TradingEconomicsCalendarProvider

pytestmark = pytest.mark.anyio("asyncio")


class _FakeBody:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeDriver:
    def __init__(self, *, page_source: str = "", body_text: str = "", calendar_elements=None) -> None:
        self.page_source = page_source
        self.body_text = body_text
        self.calendar_elements = list(calendar_elements or [])

    def find_elements(self, by, value):
        if (by, value) == (By.ID, "calendar"):
            return list(self.calendar_elements)
        return []

    def find_element(self, by, value):
        if (by, value) == (By.TAG_NAME, "body"):
            return _FakeBody(self.body_text)
        if (by, value) == (By.ID, "calendar") and self.calendar_elements:
            return self.calendar_elements[0]
        raise NoSuchElementException()


class _FakeWait:
    def __init__(self, driver) -> None:
        self.driver = driver

    def until(self, condition):
        result = condition(self.driver)
        if not result:
            raise TimeoutException("timed out")
        return result


class _EmptyWeekProvider:
    name = "stub-empty"
    timezone = "America/Chicago"

    async def fetch_week(self, week_start: date, week_end: date) -> EconomicCalendarWeek:
        return EconomicCalendarWeek(
            week_start=week_start,
            week_end=week_end,
            timezone=self.timezone,
            source=self.name,
            events=tuple(),
        )


@pytest.mark.parametrize(
    "empty_text",
    [
        "No Events Scheduled",
        "No economic data available",
    ],
)
def test_trading_economics_extract_events_returns_empty_for_empty_state(empty_text):
    provider = TradingEconomicsCalendarProvider(logger=lambda _message: None)
    driver = _FakeDriver(
        page_source=f"<html><body><div>{empty_text}</div></body></html>",
        body_text=empty_text,
    )

    events = provider._extract_events(driver, _FakeWait(driver))

    assert events == []


async def test_ensure_week_persists_empty_events_and_formats_empty_message(tmp_path):
    store_path = tmp_path / "week_ecom_calendar.json"
    store = EconomicCalendarStore(path=store_path, logger=lambda _message: None)
    service = EconomicCalendarService(
        provider=_EmptyWeekProvider(),
        store=store,
        logger=lambda _message: None,
    )

    week = await service.ensure_week(today=date(2026, 3, 23))

    assert week is not None
    assert week.events == ()

    payload = json.loads(store_path.read_text())
    assert payload["events"] == []

    message = service.build_daily_message(now=datetime(2026, 3, 23, 12, 0))
    assert message == "**NO MAJOR NEWS EVENTS TODAY**"
