# Economic Calendar Integration

Provider-agnostic economic calendar access with a cached weekly payload.

Defaults

- Provider: Trading Economics (Selenium-backed).
- Cache file: `storage/week_ecom_calendar.json`
- Timezone: `America/Chicago` (override by passing a provider with a different `timezone`).

Entry points

- `ensure_economic_calendar_data()` loads or refreshes the current week.
- `setup_economic_news_message()` formats today's events for Discord.
- `check_order_time_to_event_time()` gates trades within a time window.

Cache format

```json
{
  "version": 1,
  "week_start": "2026-01-12",
  "week_end": "2026-01-18",
  "timezone": "America/Chicago",
  "source": "tradingeconomics",
  "events": [
    {
      "date": "2026-01-14",
      "time_label": "08:30 AM",
      "title": "CPI MoM",
      "starts_at": "2026-01-14T08:30:00-06:00",
      "impact": "high",
      "country": "US",
      "source": "tradingeconomics"
    }
  ]
}
```

Provider interface
Implement `EconomicCalendarProvider.fetch_week(week_start, week_end)` to return an
`EconomicCalendarWeek`. The service takes care of caching and message formatting.

Example

```python
from integrations.economic_calendar import EconomicCalendarService

service = EconomicCalendarService()
await service.ensure_week()
message = service.build_daily_message()
```
