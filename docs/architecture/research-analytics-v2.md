# Research Analytics v2 (Entry -> Paths -> Metrics -> Simulations)

This is the **research-only** analytics pipeline used to study exit/add rules
without touching live trades. It is intentionally decoupled from execution.

---

## Goals

- Record **hypothetical entries** from research strategies.
- Capture **post-entry events** (candle closes + touches).
- Compute **path metrics** (MFE/MAE, time-to-MFE/MAE).
- Simulate exit rules offline (TP/SL, touch-based, time-stop).

---

## Data Flow

1) **Research signals**
   - Source: `runtime/research_signal_runner.py`
   - Writes: `storage/options/analytics/strategy_signals.jsonl`
   - Trigger: EMA crossover (research-only)

2) **Path events**
   - Source: `runtime/research_signal_runner.py`
   - Writes: `storage/options/analytics/strategy_paths.jsonl`
   - Events:
     - Candle close (per signal, per timeframe)
     - EMA touches (intrabar)
     - Level touches (intrabar)
     - Zone touches (intrabar)
   - Deduped per signal + event_key + candle bucket

3) **Path metrics (offline)**
   - Tool: `tools/analytics_v2/compute_path_metrics.py`
   - Output: `storage/options/analytics/path_metrics.jsonl`
   - Computes: MFE/MAE + time-to-extremes

4) **Rule simulations (offline)**
   - Tool: `tools/analytics_v2/simulate_rules.py`
   - Output: `storage/options/analytics/rule_simulations.jsonl`
   - Rules:
     - TP/SL by percentage
     - Exit on touch (EMA / level / zone)
     - Optional time-stop

---

## Runtime wiring

Enabled by config:

- `RESEARCH_SIGNALS_ENABLED`: true/false
- `RESEARCH_SIGNALS_TIMEFRAMES`: list (defaults to main timeframes)
- `RESEARCH_TOUCH_POLL_SECS`: poll interval (seconds)
- `RESEARCH_TOUCH_TOLERANCE`: absolute price tolerance

Runner is started in `main.py` when enabled and runs in parallel with live strategies.

---

## Why this is decoupled

- Avoids contaminating live trade ledger.
- Allows safe experimentation on exits/adds.
- Append-only JSONL keeps it simple and auditable.

---

## Manual EOD flow (current)

1) Let the bot run and collect signals + paths.
2) Compute metrics:
   - `python tools/analytics_v2/compute_path_metrics.py`
3) Run simulations:
   - `python tools/analytics_v2/simulate_rules.py --rules storage/options/analytics/rules.json`

Runbook: `docs/runbooks/research-analytics-eod.md`

Automation can be added later (EOD report to Discord).
