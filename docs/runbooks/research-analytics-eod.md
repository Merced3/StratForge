# Runbook: Research Analytics v2 EOD

Last updated: 2026-01-27
Owner: Merced Gonzales III

## Goal

Generate path metrics and rule simulation outputs after a trading day so research data is ready for review.

## Preconditions

- Bot ran during market hours with:
  - `RESEARCH_SIGNALS_ENABLED = true`
  - `RESEARCH_SIGNALS_TIMEFRAMES` set as desired
- Input data exists:
  - `storage/options/analytics/strategy_signals.jsonl`
  - `storage/options/analytics/strategy_paths.jsonl`

## Steps

1) Compute path metrics:
   - `python tools/analytics_v2/compute_path_metrics.py`
2) Run rule simulations (default rules):
   - `python tools/analytics_v2/simulate_rules.py`
3) Run rule simulations with custom rules (optional):
   - `python tools/analytics_v2/simulate_rules.py --rules storage/options/analytics/rules.json`
4) Summarize metrics (optional):
   - `python tools/analytics_v2/summarize_metrics.py`

## Verification

- `storage/options/analytics/path_metrics.jsonl` is non-empty when signals exist.
- `storage/options/analytics/rule_simulations.jsonl` is non-empty when signals exist.
- Command output should show non-zero counts for Signals/Paths.

## Rollback

- No rollback required. Outputs are derived and can be regenerated at any time.
