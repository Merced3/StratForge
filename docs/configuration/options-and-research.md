# Configuration - Options, Research, and Reporting

This doc covers configuration keys that are not part of the symbol/timeframe setup.
All keys live in `config.json`.

---

## 1) Options trading controls

- `OPTION_EXPIRATION_DTE`
  - Controls the target expiration (ex: "0dte", "1dte", or an explicit date).
- `NUM_OUT_OF_MONEY`
  - Max OTM distance for contract selection (used by the selector).
- `RECORD_OPTIONS_QUOTES`
  - When true, writes the full option chain snapshots to JSONL.
- `OPTIONS_QUOTES_DIR`
  - Directory for recorded option chains (JSONL).

---

## 2) Research analytics (v2)

- `RESEARCH_SIGNALS_ENABLED`
  - Turns the research signal runner on/off.
- `RESEARCH_SIGNALS_TIMEFRAMES`
  - Which timeframes the research runner listens to.
- `RESEARCH_TOUCH_POLL_SECS`
  - Poll interval (seconds) for intrabar touches.
- `RESEARCH_TOUCH_TOLERANCE`
  - Absolute price tolerance for EMA/level/zone touches.

---

## 3) Strategy reporting (Discord EOD)

`STRATEGY_REPORTING` is a JSON object:

```json
{
  "enabled": true,
  "use_test_channel": false,
  "update_existing": true
}
```

- `enabled`: run EOD reporting or not
- `use_test_channel`: use the test channel ID in `cred.py`
- `update_existing`: edit existing message IDs if present

---

## 4) Account state / daily bookkeeping

- `REAL_MONEY_ACTIVATED`
  - When true, live account balance is pulled at EOD.
- `START_OF_DAY_BALANCE`
  - Stored balance used for daily P/L.
- `START_OF_DAY_DATE`
  - Date that the stored balance applies to.

---

## 5) Data and signals

- `CANDLE_BUFFER`
  - Seconds buffer added to candle close schedule.
- `EMAS`
  - EMA periods and colors, used by both live strategies and research signals.
- `FLAGPOLE_CRITERIA`
  - Flag detection thresholds (used in legacy flag logic).
- `GET_PDHL`
  - Toggle for pulling previous day high/low.
- `MINS_BEFORE_MAJOR_NEWS_ORDER_CANCELATION`
  - Minutes before major news where orders are canceled.
