from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from paths import (
    OPTIONS_RESEARCH_METRICS_PATH,
    OPTIONS_RESEARCH_PATHS_PATH,
    OPTIONS_RESEARCH_SIGNALS_PATH,
)


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


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def load_signals(path: Path) -> Dict[str, dict]:
    signals: Dict[str, dict] = {}
    for row in load_jsonl(path):
        signal_id = row.get("signal_id")
        if not signal_id:
            continue
        signals[signal_id] = row
    return signals


def load_path_events(path: Path) -> Dict[str, List[dict]]:
    events: Dict[str, List[dict]] = {}
    for row in load_jsonl(path):
        signal_id = row.get("signal_id")
        if not signal_id:
            continue
        events.setdefault(signal_id, []).append(row)
    return events


def compute_metrics(
    signals: Dict[str, dict],
    paths: Dict[str, List[dict]],
) -> List[dict]:
    metrics: List[dict] = []
    for signal_id, signal in signals.items():
        entry_mark = _safe_float(signal.get("entry_mark"))
        if entry_mark is None:
            continue
        entry_ts = parse_ts(signal.get("ts"))
        events = sorted(paths.get(signal_id, []), key=lambda e: e.get("ts") or "")
        best = None
        worst = None
        best_event = None
        worst_event = None
        for event in events:
            mark = _safe_float(event.get("mark"))
            if mark is None:
                continue
            delta = mark - entry_mark
            if best is None or delta > best:
                best = delta
                best_event = event
            if worst is None or delta < worst:
                worst = delta
                worst_event = event

        last_ts = parse_ts(events[-1].get("ts")) if events else None
        metrics.append(
            {
                "signal_id": signal_id,
                "strategy_tag": signal.get("strategy_tag"),
                "timeframe": signal.get("timeframe"),
                "symbol": signal.get("symbol"),
                "option_type": signal.get("option_type"),
                "strike": signal.get("strike"),
                "expiration": signal.get("expiration"),
                "contract_key": signal.get("contract_key"),
                "entry_ts": signal.get("ts"),
                "entry_mark": entry_mark,
                "event_count": len(events),
                "last_ts": last_ts.isoformat() if last_ts else None,
                "mfe": _round(best) if best is not None else 0.0,
                "mae": _round(worst) if worst is not None else 0.0,
                "mfe_pct": _round(_pct(best, entry_mark)),
                "mae_pct": _round(_pct(worst, entry_mark)),
                "mfe_ts": best_event.get("ts") if best_event else None,
                "mae_ts": worst_event.get("ts") if worst_event else None,
                "mfe_event_key": best_event.get("event_key") if best_event else None,
                "mae_event_key": worst_event.get("event_key") if worst_event else None,
                "mfe_underlying": best_event.get("underlying_price") if best_event else None,
                "mae_underlying": worst_event.get("underlying_price") if worst_event else None,
                "seconds_to_mfe": _elapsed_seconds(entry_ts, parse_ts(best_event.get("ts")) if best_event else None),
                "seconds_to_mae": _elapsed_seconds(entry_ts, parse_ts(worst_event.get("ts")) if worst_event else None),
            }
        )
    return metrics


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Optional[float], base: float) -> Optional[float]:
    if value is None or base == 0:
        return None
    return value / base


def _elapsed_seconds(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
    if not start or not end:
        return None
    return int((end - start).total_seconds())


def _round(value: Optional[float], places: int = 6) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), places)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute MFE/MAE path metrics for research signals.")
    parser.add_argument("--signals", type=Path, default=OPTIONS_RESEARCH_SIGNALS_PATH)
    parser.add_argument("--paths", type=Path, default=OPTIONS_RESEARCH_PATHS_PATH)
    parser.add_argument("--out", type=Path, default=OPTIONS_RESEARCH_METRICS_PATH)
    args = parser.parse_args()

    signals = load_signals(args.signals)
    paths = load_path_events(args.paths)
    rows = compute_metrics(signals, paths)
    write_jsonl(args.out, rows)
    print(f"[ANALYTICS V2] Signals: {len(signals)} | Paths: {sum(len(v) for v in paths.values())} | Metrics: {len(rows)}")
    print(f"[ANALYTICS V2] Output: {args.out}")


if __name__ == "__main__":
    main()
