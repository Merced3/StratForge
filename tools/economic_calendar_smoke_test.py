"""
Manual smoke test for the economic calendar integration.

This script is meant to mirror the same top-level calls that `main.py` uses:

    await ensure_economic_calendar_data()
    setup_economic_news_message()

Examples:
    python tools/economic_calendar_smoke_test.py
    python tools/economic_calendar_smoke_test.py --refresh
    python tools/economic_calendar_smoke_test.py --refresh --message --show-events 10
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.economic_calendar import (
    EconomicCalendarStore,
    ensure_economic_calendar_data,
    setup_economic_news_message,
)
from paths import WEEK_ECOM_CALENDER_PATH, pretty_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the economic calendar integration.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Call ensure_economic_calendar_data() before reading the cache.",
    )
    parser.add_argument(
        "--message",
        action="store_true",
        help="Print setup_economic_news_message() after loading the cache.",
    )
    parser.add_argument(
        "--show-events",
        type=int,
        default=5,
        help="How many cached events to preview.",
    )
    return parser.parse_args()


def _print_week_summary(store: EconomicCalendarStore, show_events: int) -> int:
    week = store.load_week()
    if not week:
        print(f"[econ-smoke] No cached week found at {pretty_path(WEEK_ECOM_CALENDER_PATH, short=False)}.")
        return 1

    event_count = len(week.events)
    print(f"[econ-smoke] Cache: {pretty_path(WEEK_ECOM_CALENDER_PATH, short=False)}")
    print(f"[econ-smoke] Week: {week.week_start.isoformat()} -> {week.week_end.isoformat()}")
    print(f"[econ-smoke] Source: {week.source}")
    print(f"[econ-smoke] Timezone: {week.timezone}")
    print(f"[econ-smoke] Event count: {event_count}")

    if not week.events:
        print("[econ-smoke] Cached week is valid and empty (`events: []`).")
        return 0

    for index, event in enumerate(week.events[: max(show_events, 0)], start=1):
        print(
            f"[econ-smoke] Event {index}: "
            f"{event.date.isoformat()} {event.time_label} | {event.title}"
        )
    return 0


async def _run() -> int:
    args = _parse_args()
    store = EconomicCalendarStore()

    if args.refresh:
        print("[econ-smoke] Calling ensure_economic_calendar_data()...")
        week = await ensure_economic_calendar_data()
        if week is None:
            print("[econ-smoke] ensure_economic_calendar_data() returned None.")
            return 1
        print(
            "[econ-smoke] Refresh completed: "
            f"{week.week_start.isoformat()} -> {week.week_end.isoformat()} "
            f"({len(week.events)} events)"
        )

    exit_code = _print_week_summary(store, args.show_events)

    if args.message:
        try:
            print("[econ-smoke] setup_economic_news_message():")
            print(setup_economic_news_message())
        except Exception as exc:
            print(f"[econ-smoke] setup_economic_news_message() failed: {exc}")
            return 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
