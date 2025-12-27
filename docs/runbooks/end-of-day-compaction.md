# Runbook – End-of-Day Compaction

**Goal** Merge part files into daily/monthly Parquet and (optionally) delete the parts.

## When

- After market close (automated in main loop) or manual maintenance.

## Commands

```bash
# Daily (candles)
python tools/compact_parquet.py --timeframe 2m --day 2025-09-02
python tools/compact_parquet.py --timeframe 5m --day 2025-09-02
python tools/compact_parquet.py --timeframe 15m --day 2025-09-02


# Monthly (objects)
python tools/compact_parquet.py --timeframe 15m --month 2025-09


# Keep parts (debug)
python tools/compact_parquet.py --timeframe 2m --day 2025-09-02 --keep-parts
```

## Verification

- Script re-reads the output and validates row counts and min/max `ts`.

## Rollback

- If compaction output looks wrong, parts are still there unless `--keep-parts` was omitted. Re-run with `--keep-parts` next time.
