from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from paths import OPTIONS_RESEARCH_SIM_PATH


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


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return mean(values)


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return median(values)


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordered[int(k)]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def _tail_mean(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    count = max(1, int(len(ordered) * (pct / 100.0)))
    return mean(ordered[:count])


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


def _parse_ts(value: object) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _group_key_rule(row: dict) -> str:
    return str(row.get("rule_name") or "unknown")


def _group_key_strategy(row: dict) -> str:
    return str(row.get("strategy_tag") or "unknown")


def _group_key_rule_strategy(row: dict) -> Tuple[str, str]:
    return _group_key_rule(row), _group_key_strategy(row)


def _compute_stats(rows: Iterable[dict]) -> dict:
    rows_list = list(rows)
    pnl_pct_values = [_safe_float(row.get("pnl_pct")) for row in rows_list]
    pnl_pct_values = [val for val in pnl_pct_values if val is not None]
    pnl_values = [_safe_float(row.get("pnl")) for row in rows_list]
    pnl_values = [val for val in pnl_values if val is not None]
    seconds_values = [_safe_float(row.get("seconds_in_trade")) for row in rows_list]
    seconds_values = [val for val in seconds_values if val is not None]

    wins = sum(1 for val in pnl_pct_values if val > 0)
    win_rate = (wins / len(pnl_pct_values)) if pnl_pct_values else None

    return {
        "count": len(rows_list),
        "count_pnl_pct": len(pnl_pct_values),
        "wins": wins,
        "win_rate": win_rate,
        "avg_pnl_pct": _avg(pnl_pct_values),
        "median_pnl_pct": _median(pnl_pct_values),
        "p5": _percentile(pnl_pct_values, 5),
        "p25": _percentile(pnl_pct_values, 25),
        "p75": _percentile(pnl_pct_values, 75),
        "p95": _percentile(pnl_pct_values, 95),
        "loss_tail_avg": _tail_mean(pnl_pct_values, 5),
        "avg_pnl": _avg(pnl_values),
        "median_pnl": _median(pnl_values),
        "avg_seconds": _avg(seconds_values),
    }


def _render_stats(label: str, rows: Iterable[dict]) -> str:
    stats = _compute_stats(rows)
    lines = [f"{label} ({stats['count']} sims)"]
    if stats["count_pnl_pct"] == 0:
        lines.append("  pnl_pct = n/a")
        return "\n".join(lines)

    lines.append(
        f"  win_rate     = {_fmt_percent(stats['win_rate'])} "
        f"({stats['wins']}/{stats['count_pnl_pct']})"
    )
    lines.append(f"  avg_pnl_pct  = {_fmt_percent(stats['avg_pnl_pct'])}")
    lines.append(f"  median_pnl%  = {_fmt_percent(stats['median_pnl_pct'])}")
    lines.append(
        f"  p25/p75 pnl% = {_fmt_percent(stats['p25'])} / {_fmt_percent(stats['p75'])}"
    )
    lines.append(
        f"  p5/p95 pnl%  = {_fmt_percent(stats['p5'])} / {_fmt_percent(stats['p95'])}"
    )
    lines.append(f"  loss_tail5%  = {_fmt_percent(stats['loss_tail_avg'])}")
    lines.append(f"  avg_pnl      = {_fmt_money(stats['avg_pnl'])}")
    lines.append(f"  avg_hold     = {_fmt_duration(stats['avg_seconds'])}")
    return "\n".join(lines)


def _render_grouped(
    rows: List[dict],
    *,
    title: str,
    key_fn,
    min_count: int,
) -> str:
    groups: dict = {}
    for row in rows:
        key = key_fn(row)
        groups.setdefault(key, []).append(row)

    grouped = sorted(groups.items(), key=lambda kv: (-len(kv[1]), str(kv[0])))
    lines: List[str] = [title]
    for key, group_rows in grouped:
        if len(group_rows) < min_count:
            continue
        if isinstance(key, tuple):
            label = f"[RULE+STRATEGY] {key[0]} | {key[1]}"
        else:
            label = f"[GROUP] {key}"
        lines.append("")
        lines.append(_render_stats(label, group_rows))
    return "\n".join(lines).strip()


def _summarize(rows: List[dict], *, min_count: int) -> str:
    lines: List[str] = []
    lines.append(_render_stats("[OVERALL]", rows))
    lines.append("")
    lines.append(_render_grouped(rows, title="[BY RULE]", key_fn=_group_key_rule, min_count=min_count))
    lines.append("")
    lines.append(
        _render_grouped(
            rows,
            title="[BY RULE + STRATEGY]",
            key_fn=_group_key_rule_strategy,
            min_count=min_count,
        )
    )
    lines.append("")
    lines.append(_render_grouped(rows, title="[BY STRATEGY]", key_fn=_group_key_strategy, min_count=min_count))
    return "\n".join(lines).strip()


def _split_by_time(
    rows: List[dict],
    split_ratio: float,
    *,
    train_side: str,
) -> tuple[List[dict], List[dict], int]:
    rows_with_ts: List[tuple[dict, datetime]] = []
    missing_ts = 0
    for row in rows:
        ts = _parse_ts(row.get("entry_ts"))
        if ts is None:
            missing_ts += 1
            continue
        rows_with_ts.append((row, ts))

    rows_with_ts.sort(key=lambda item: item[1])
    total = len(rows_with_ts)
    if total == 0:
        return [], [], missing_ts

    split_ratio = min(max(split_ratio, 0.0), 1.0)
    train_size = int(total * split_ratio)
    train_size = max(1, min(train_size, total - 1))

    if train_side == "last":
        train_rows = [row for row, _ in rows_with_ts[-train_size:]]
        test_rows = [row for row, _ in rows_with_ts[:-train_size]]
    else:
        train_rows = [row for row, _ in rows_with_ts[:train_size]]
        test_rows = [row for row, _ in rows_with_ts[train_size:]]

    return train_rows, test_rows, missing_ts


def _date_span(rows: List[dict]) -> tuple[Optional[str], Optional[str], int]:
    dates = []
    for row in rows:
        ts = _parse_ts(row.get("entry_ts"))
        if ts is None:
            continue
        dates.append(ts.date())
    if not dates:
        return None, None, 0
    dates = sorted(set(dates))
    return dates[0].isoformat(), dates[-1].isoformat(), len(dates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize research rule simulations.")
    parser.add_argument("--sim", type=Path, default=OPTIONS_RESEARCH_SIM_PATH)
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--split", type=float, default=None)
    parser.add_argument("--train-side", choices=("first", "last"), default="first")
    args = parser.parse_args()

    rows = load_jsonl(args.sim)
    if not rows:
        print("[SIM SUMMARY] No simulations found.")
        return

    print(f"[SUMMARY] sims={len(rows)}")
    print("")
    print(_summarize(rows, min_count=args.min_count))

    if args.split is None:
        return

    train_rows, test_rows, missing_ts = _split_by_time(
        rows,
        args.split,
        train_side=args.train_side,
    )
    train_start, train_end, train_days = _date_span(train_rows)
    test_start, test_end, test_days = _date_span(test_rows)

    print("")
    print(
        f"[SPLIT] train={args.split:.0%} ({args.train_side}) "
        f"| test={1 - args.split:.0%} | missing_ts={missing_ts}"
    )
    print("")
    print(
        f"[TRAIN] sims={len(train_rows)} days={train_days} "
        f"range={train_start or 'n/a'}..{train_end or 'n/a'}"
    )
    print(_summarize(train_rows, min_count=args.min_count))
    print("")
    print(
        f"[TEST] sims={len(test_rows)} days={test_days} "
        f"range={test_start or 'n/a'}..{test_end or 'n/a'}"
    )
    print(_summarize(test_rows, min_count=args.min_count))


if __name__ == "__main__":
    main()
