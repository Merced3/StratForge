# Why `docs/` Exist

If it explains how/why the system works (not just what it does), it belongs in `docs/`. If it’s user-facing marketing or setup basics, that’s `README.md`.

---

## Table of Contents

1. **Overview**
  1.1 Purpose of the Bot  
  1.2 Key Features  
  1.3 Supported Markets & Instruments  

2. **Installation & Setup**
  2.1 Prerequisites  
  2.2 Cloning the Repository  
  2.3 Installing Dependencies  
  2.4 Environment Variables & Config Files  

3. **Running the Bot**
  3.1 Starting Data Acquisition  
  3.2 Running the Strategy Module  
  3.3 Launching the Web Dashboard  
  3.4 Development Mode vs Live Trading Mode  
  3.5 Research analytics EOD runbook (`docs/runbooks/research-analytics-eod.md`)  

4. **Architecture Overview**
  4.1 High-Level System Diagram  
  4.2 Module Breakdown  
  4.3 Data Flow & Storage Locations  
  4.4 See `docs/adr/` for key technical decisions and tradeoffs  
  4.5 Options subsystem study sheet (`docs/architecture/options-subsystem.md`)
  4.6 Research analytics v2 (`docs/architecture/research-analytics-v2.md`)
  4.7 Research analytics v2 data schema (`docs/data/research_analytics_v2.md`)

5. **Data Acquisition**
  5.1 Live Market Data Sources  
  5.2 Logging Candles (2M, 5M, 15M)  
  5.3 Handling Market Open/Close Logic  

6. **Strategies**
  6.1 Strategy Overview  
  6.2 EMA Calculations & Crossovers  
  6.3 Flag & Zone Detection  
  6.4 Risk Management Logic  

7. **Charts & Visualization**
  7.1 Live Chart (2M, 5M, 15M)  
  7.2 Zone Chart (15M Historical)  
  7.3 Real-Time Updates via WebSocket  
  7.4 PNG Exports for Discord  

8. **Separation of Concerns**
  8.1 Why Data Collection is Independent from Strategy  
  8.2 Benefits for Testing & Reliability  
  8.3 Applying Separation to New Modules  

9. **Configuration**
  9.1 Modifying `config.json`  
  9.2 Adding/Removing Timeframes  
  9.3 Changing EMA Settings  
  9.4 Options, research, and reporting config (`docs/configuration/options-and-research.md`)

10. **Deployment**
  10.1 Local Deployment  
  10.2 VPS / Cloud Deployment  
  10.3 Monitoring & Logging in Production  

11. **Troubleshooting**
  11.1 Common Errors & Fixes  
  11.2 Debugging Live Chart Updates  
  11.3 Handling Missing Data  

12. **Changelog**
  12.1 Week-by-Week Progress  
  12.2 Major Milestones  

---

## What to put in `docs/`

- **architecture_notes.md** — Big-picture principles, diagrams, module boundaries
- **adr/** (Architecture Decision Records) — Short “we decided X over Y because Z.”
  - `docs/adr/0001-websocket-over-polling.md`
- **runbooks/** — Step-by-step ops tasks.
  - `docs/runbooks/start-all-services.md`
  - `docs/runbooks/recover-stuck-websocket.md`
- **api/** — Endpoints for internal FastAPI services.
  - `docs/api/ws_server.md` (routes, payloads, examples)
- **data/** — Schemas and contracts for files/DB tables.
  - `docs/data/candles_schema.md`
  - `docs/data/signals_schema.md`
- **playbooks/** — “When X happens, do Y.”
  - `docs/playbooks/market-halt.md`
  - `docs/playbooks/broker-timeout.md`
- **troubleshooting.md** — Common errors + fixes.
- **testing.md** — How to run unit/integration/replay tests; test data locations.
- **conventions.md** — Code style, naming, folder conventions, logging levels.
- **roadmap.md** — Short-term priorities, longer-term ideas.
- **release-notes.md** — Human-readable summary per week/day.
- **security.md** — Token management, .env usage, what never goes in Git.
- **perf-notes.md** — Known bottlenecks, profiling tips, scale ideas.
- **incident_postmortems/** — Optional but great when things break.

---

## When to add something (quick vetting checklist)

- Will Future-You thank Present-You for writing this down?
- Is it a **contract** (API, schema, interface) others depend on?
- Is it a **repeatable** procedure (runbook/playbook)?
- Is it a **decision** you might revisit later (ADR)?
- Is it **too detailed** for README but too important to live only in your head/slack?

---

## Tiny templates to copy-paste

### ADR template

```bash
# ADR 000X: <Decision Title>
Date: 2025-08-07
Status: Accepted | Proposed | Superseded by 000Y

## Context
<Problem & constraints>

## Decision
<What we chose>

## Alternatives
<Option A / B with tradeoffs>

## Consequences
<Pros, cons, follow-ups>
```

### Runbook template

```bash
# Runbook: <Task>
Last updated: 2025-08-07
Owner: <you>

## Goal
What success looks like.

## Preconditions
What must be true (tokens, services up, market state).

## Steps
1) ...
2) ...
3) ...

## Verification
Logs/metrics to check.

## Rollback
How to undo safely.
```

### API doc template

```bash
# Service: ws_server

## Endpoints
### POST /trigger-chart-update
Body: `{ "timeframe": "2M" }`  
Response: `{ "status": "broadcasted", "timeframe": "2M", "clients": 1 }`

### WS /ws/chart-updates
Sends: `chart:<TF>` messages on update.
```

### Data schema template

```bash
# candles schema (SPY_2M.log lines)
- timestamp: ISO 8601 (NY timezone)
- open/high/low/close: float
- volume: int (optional)

Contract: append-only; no edits; consumers must tolerate gaps.
```
