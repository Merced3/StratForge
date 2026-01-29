from __future__ import annotations

"""
Retag strategy_tag fields in JSONL ledgers (manual, explicit migration).

Purpose:
- This tool is a safe, manual way to rename strategy tags after you decide
  to change naming conventions (ex: "ema-crossover" -> "ema-crossover-15m").
- It updates only the "strategy_tag" field, leaving all numeric data intact.
- It does NOT touch "position_id" or "signal_id" because those are primary
  identifiers used to link events together. Keeping them stable avoids breaking
  historical joins.

What it targets by default:
- V1 ledger: storage/options/trade_events.jsonl
- V2 ledgers:
  - storage/options/analytics/strategy_signals.jsonl
  - storage/options/analytics/strategy_paths.jsonl
  - storage/options/analytics/path_metrics.jsonl
  - storage/options/analytics/rule_simulations.jsonl

Common usage (safe, non-destructive):
  python tools/retag_strategy_tags.py --map "ema-crossover=ema-crossover-15m"
  - Writes new files alongside originals with the ".retagged" suffix.

In-place (overwrites with backup):
  python tools/retag_strategy_tags.py --map "ema-crossover=ema-crossover-15m" --in-place
  - Creates a .bak copy of each file before overwriting.

Multiple renames:
  python tools/retag_strategy_tags.py \
    --map "ema-crossover=ema-crossover-15m" \
    --map "candle-ema-break=candle-ema-break-2m"

Specific files only:
  python tools/retag_strategy_tags.py \
    --map "ema-crossover=ema-crossover-15m" \
    --paths storage/options/trade_events.jsonl

After retagging V2 data, recompute derived outputs:
  python tools/analytics_v2/compute_path_metrics.py
  python tools/analytics_v2/simulate_rules.py
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from paths import (
    OPTIONS_RESEARCH_METRICS_PATH,
    OPTIONS_RESEARCH_PATHS_PATH,
    OPTIONS_RESEARCH_SIGNALS_PATH,
    OPTIONS_RESEARCH_SIM_PATH,
    OPTIONS_TRADE_LEDGER_PATH,
)


DEFAULT_PATHS = [
    OPTIONS_TRADE_LEDGER_PATH,
    OPTIONS_RESEARCH_SIGNALS_PATH,
    OPTIONS_RESEARCH_PATHS_PATH,
    OPTIONS_RESEARCH_METRICS_PATH,
    OPTIONS_RESEARCH_SIM_PATH,
]


def _parse_map(values: Iterable[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            continue
        old, new = raw.split("=", 1)
        old = old.strip()
        new = new.strip()
        if not old or not new:
            continue
        mapping[old] = new
    return mapping


def _normalize_timeframe(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _retag_from_timeframe(rows: List[dict], base_tag: str) -> Tuple[List[dict], int]:
    changed = 0
    for row in rows:
        timeframe = _normalize_timeframe(row.get("timeframe"))
        if not timeframe:
            continue
        tag = row.get("strategy_tag")
        if tag is not None and not str(tag).startswith(base_tag):
            continue
        row["strategy_tag"] = f"{base_tag}-{timeframe}"
        changed += 1
    return rows, changed


def _read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _retag_rows(rows: List[dict], mapping: Dict[str, str]) -> Tuple[List[dict], int]:
    changed = 0
    for row in rows:
        tag = row.get("strategy_tag")
        if tag is None:
            continue
        if tag in mapping:
            row["strategy_tag"] = mapping[tag]
            changed += 1
    return rows, changed


def _resolve_paths(paths: Iterable[str]) -> List[Path]:
    resolved: List[Path] = []
    for item in paths:
        if not item:
            continue
        resolved.append(Path(item))
    return resolved


def _default_out_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".retagged")


def _backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".bak")


def _process_path(
    path: Path,
    mapping: Dict[str, str],
    *,
    inplace: bool,
    timeframe_base: str = "",
) -> Tuple[int, int, Path]:
    rows = _read_jsonl(path)
    if not rows:
        return 0, 0, path
    if timeframe_base:
        rows, changed = _retag_from_timeframe(rows, timeframe_base)
    else:
        rows, changed = _retag_rows(rows, mapping)
    if inplace:
        backup = _backup_path(path)
        if path.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        _write_jsonl(path, rows)
        return len(rows), changed, path
    out_path = _default_out_path(path)
    _write_jsonl(out_path, rows)
    return len(rows), changed, out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retag strategy_tag fields in JSONL ledgers (safe defaults).",
    )
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        help="Mapping in form old=new (repeatable).",
    )
    parser.add_argument(
        "--tag-from-timeframe",
        default="",
        help="Base tag to apply using each row's timeframe (ex: ema-crossover).",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Optional list of JSONL paths to retag.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite files (creates .bak backups). Default writes *.retagged.",
    )
    args = parser.parse_args()

    mapping = _parse_map(args.map)
    if not mapping and not args.tag_from_timeframe:
        print("[RETAG] No valid mappings provided. Use --map old=new or --tag-from-timeframe.")
        return 1

    paths = _resolve_paths(args.paths) if args.paths else list(DEFAULT_PATHS)
    if not paths:
        print("[RETAG] No paths to process.")
        return 1

    if args.tag_from_timeframe:
        print(f"[RETAG] Tag-from-timeframe base: {args.tag_from_timeframe}")
    else:
        print(f"[RETAG] Mapping: {mapping}")
    print(f"[RETAG] Mode: {'in-place' if args.in_place else 'write new files'}")

    total_rows = 0
    total_changed = 0
    for path in paths:
        rows, changed, out_path = _process_path(
            path,
            mapping,
            inplace=args.in_place,
            timeframe_base=args.tag_from_timeframe,
        )
        total_rows += rows
        total_changed += changed
        label = str(path)
        if rows == 0:
            print(f"[RETAG] {label}: skipped (empty/missing)")
            continue
        if out_path != path:
            print(f"[RETAG] {label}: {changed}/{rows} retagged -> {out_path}")
        else:
            print(f"[RETAG] {label}: {changed}/{rows} retagged (in-place)")

    print(f"[RETAG] Done. Total changed: {total_changed} of {total_rows} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
