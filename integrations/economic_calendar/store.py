import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytz

from paths import WEEK_ECOM_CALENDER_PATH, pretty_path
from shared_state import print_log

from .models import EconomicCalendarWeek, EconomicEvent

DEFAULT_TIMEZONE = "America/Chicago"
LEGACY_DATE_FORMAT = "%m-%d-%y"


class EconomicCalendarStore:
    def __init__(
        self,
        path: Path = WEEK_ECOM_CALENDER_PATH,
        default_timezone: str = DEFAULT_TIMEZONE,
        logger=print_log,
    ) -> None:
        self.path = path
        self.default_timezone = default_timezone
        self.logger = logger

    def load_week(self) -> Optional[EconomicCalendarWeek]:
        if not self.path.exists():
            return None
        try:
            with open(self.path, "r") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self.logger(f"[ECON] Failed to read {pretty_path(self.path)}: {exc}")
            return None

        if isinstance(data, dict) and "week_timespan" in data and "dates" in data:
            return self._from_legacy_payload(data)

        if isinstance(data, dict) and "week_start" in data and "events" in data:
            return self._from_payload(data)

        self.logger(f"[ECON] Unknown calendar format in {pretty_path(self.path)}")
        return None

    def require_week(self) -> EconomicCalendarWeek:
        week = self.load_week()
        if not week:
            raise FileNotFoundError(f"`{pretty_path(self.path)}` does not exist")
        return week

    def save_week(self, week: EconomicCalendarWeek) -> None:
        payload = self._to_payload(week)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as handle:
            json.dump(payload, handle, indent=4)

    def _from_payload(self, payload: dict) -> Optional[EconomicCalendarWeek]:
        timezone_name = payload.get("timezone") or self.default_timezone
        tz = pytz.timezone(timezone_name)
        try:
            week_start = date.fromisoformat(payload["week_start"])
            week_end = date.fromisoformat(payload["week_end"])
        except (KeyError, ValueError) as exc:
            self.logger(f"[ECON] Invalid week bounds in {pretty_path(self.path)}: {exc}")
            return None

        events = []
        for raw in payload.get("events", []):
            if not isinstance(raw, dict):
                continue
            title = (raw.get("title") or "").strip()
            if not title:
                continue

            raw_date = raw.get("date")
            event_date = None
            if raw_date:
                try:
                    event_date = date.fromisoformat(raw_date)
                except ValueError:
                    event_date = None

            starts_at = None
            raw_starts = raw.get("starts_at")
            if raw_starts:
                try:
                    starts_at = _parse_datetime(raw_starts, tz)
                except ValueError:
                    starts_at = None

            if event_date is None and starts_at is not None:
                event_date = starts_at.date()

            if event_date is None:
                continue

            time_label = (raw.get("time_label") or "").strip()
            if not time_label and starts_at is not None:
                time_label = starts_at.strftime("%I:%M %p").lstrip("0")

            if not time_label:
                time_label = "TBD"

            events.append(
                EconomicEvent(
                    date=event_date,
                    time_label=time_label,
                    title=title,
                    starts_at=starts_at,
                    impact=_clean_optional(raw.get("impact")),
                    country=_clean_optional(raw.get("country")),
                    source=_clean_optional(raw.get("source")),
                )
            )

        return EconomicCalendarWeek(
            week_start=week_start,
            week_end=week_end,
            timezone=timezone_name,
            source=str(payload.get("source") or "unknown"),
            events=tuple(events),
        )

    def _from_legacy_payload(self, payload: dict) -> Optional[EconomicCalendarWeek]:
        week_timespan = payload.get("week_timespan") or ""
        if not week_timespan:
            return None
        try:
            start_str, end_str = [part.strip() for part in week_timespan.split("to")]
            week_start = datetime.strptime(start_str, LEGACY_DATE_FORMAT).date()
            week_end = datetime.strptime(end_str, LEGACY_DATE_FORMAT).date()
        except ValueError:
            return None

        tz = pytz.timezone(self.default_timezone)
        events = []
        dates = payload.get("dates", {})
        if not isinstance(dates, dict):
            dates = {}

        for date_str, times in dates.items():
            try:
                event_date = datetime.strptime(date_str, LEGACY_DATE_FORMAT).date()
            except ValueError:
                continue
            if not isinstance(times, dict):
                continue
            for time_label, titles in times.items():
                if not isinstance(titles, list):
                    continue
                for title in titles:
                    title = str(title).strip()
                    if not title:
                        continue
                    starts_at = _parse_time_label(event_date, str(time_label), tz)
                    events.append(
                        EconomicEvent(
                            date=event_date,
                            time_label=str(time_label),
                            title=title,
                            starts_at=starts_at,
                            source="legacy",
                        )
                    )

        return EconomicCalendarWeek(
            week_start=week_start,
            week_end=week_end,
            timezone=self.default_timezone,
            source="legacy",
            events=tuple(events),
        )

    def _to_payload(self, week: EconomicCalendarWeek) -> dict:
        events = []
        for event in week.events:
            item = {
                "date": event.date.isoformat(),
                "time_label": event.time_label,
                "title": event.title,
            }
            if event.starts_at is not None:
                item["starts_at"] = event.starts_at.isoformat()
            if event.impact:
                item["impact"] = event.impact
            if event.country:
                item["country"] = event.country
            if event.source:
                item["source"] = event.source
            events.append(item)

        return {
            "version": 1,
            "week_start": week.week_start.isoformat(),
            "week_end": week.week_end.isoformat(),
            "timezone": week.timezone,
            "source": week.source,
            "events": events,
        }


def _parse_datetime(value: str, tz) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return tz.localize(dt)
    return dt.astimezone(tz)


def _parse_time_label(event_date: date, time_label: str, tz) -> Optional[datetime]:
    label = time_label.strip()
    if not label:
        return None
    try:
        time_obj = datetime.strptime(label, "%I:%M %p").time()
    except ValueError:
        return None
    return tz.localize(datetime.combine(event_date, time_obj))


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
