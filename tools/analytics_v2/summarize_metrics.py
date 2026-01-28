from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from paths import OPTIONS_RESEARCH_METRICS_PATH


def load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
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


def summarize(metrics: Iterable[dict]) -> str:
    metrics_list = list(metrics)
    grouped: dict[str, list[dict]] = {}
    for row in metrics_list:
        tag = row.get("strategy_tag") or "unknown"
        grouped.setdefault(tag, []).append(row)

    lines: List[str] = []
    total = len(metrics_list)
    lines.append(f"[SUMMARY] signals={total}")
    for tag in sorted(grouped.keys()):
        rows = grouped[tag]
        lines.append("")
        lines.append(f"[STRATEGY] {tag} ({len(rows)} signals)")
        lines.append(f"  avg_mfe     = {_fmt_money(_avg(_values(rows, 'mfe')))}")
        lines.append(f"  avg_mae     = {_fmt_money(_avg(_values(rows, 'mae')))}")
        lines.append(f"  avg_mfe_pct = {_fmt_percent(_avg(_values(rows, 'mfe_pct')))}")
        lines.append(f"  avg_mae_pct = {_fmt_percent(_avg(_values(rows, 'mae_pct')))}")
        lines.append(f"  avg_t_mfe   = {_fmt_duration(_avg(_values(rows, 'seconds_to_mfe')))}")
        lines.append(f"  avg_t_mae   = {_fmt_duration(_avg(_values(rows, 'seconds_to_mae')))}")
    return "\n".join(lines).strip()


def _values(rows: List[dict], key: str) -> List[float]:
    values: List[float] = []
    for row in rows:
        val = row.get(key)
        if val is None:
            continue
        try:
            values.append(float(val))
        except (TypeError, ValueError):
            continue
    return values


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return mean(values)


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"${value:.2f}"


def _fmt_percent(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt_duration(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    seconds = int(value)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize research path metrics by strategy.")
    parser.add_argument("--metrics", type=Path, default=OPTIONS_RESEARCH_METRICS_PATH)
    args = parser.parse_args()

    metrics = load_jsonl(args.metrics)
    if not metrics:
        print("[ANALYTICS V2] No metrics found.")
        return
    print(summarize(metrics))


if __name__ == "__main__":
    main()
