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
    OPTIONS_RESEARCH_PATHS_PATH,
    OPTIONS_RESEARCH_SIGNALS_PATH,
    OPTIONS_RESEARCH_SIM_PATH,
)


DEFAULT_RULES = [
    {"name": "tp50_sl30", "type": "tp_sl", "tp_pct": 0.50, "sl_pct": -0.30},
    {"name": "exit_ema_touch", "type": "touch", "event_prefixes": ["ema:"]},
    {"name": "exit_level_zone_touch", "type": "touch", "event_prefixes": ["level:", "zone:"]},
]


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


def load_rules(path: Optional[Path]) -> List[dict]:
    if not path:
        return list(DEFAULT_RULES)
    if not path.exists():
        return list(DEFAULT_RULES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return list(DEFAULT_RULES)
    if isinstance(data, dict):
        rules = data.get("rules")
    else:
        rules = data
    if not isinstance(rules, list):
        return list(DEFAULT_RULES)
    return [rule for rule in rules if isinstance(rule, dict)]


def simulate_rules(
    signals: Dict[str, dict],
    paths: Dict[str, List[dict]],
    rules: Iterable[dict],
) -> List[dict]:
    results: List[dict] = []
    for signal_id, signal in signals.items():
        entry_mark = _safe_float(signal.get("entry_mark"))
        if entry_mark is None:
            continue
        entry_ts = parse_ts(signal.get("ts"))
        events = sorted(paths.get(signal_id, []), key=lambda e: e.get("ts") or "")
        for rule in rules:
            result = _simulate_rule(rule, signal_id, signal, entry_mark, entry_ts, events)
            if result:
                results.append(result)
    return results


def _simulate_rule(
    rule: dict,
    signal_id: str,
    signal: dict,
    entry_mark: float,
    entry_ts: Optional[datetime],
    events: List[dict],
) -> Optional[dict]:
    rule_type = rule.get("type") or "tp_sl"
    name = rule.get("name") or rule_type
    exit_event = None
    exit_reason = None

    if rule_type == "tp_sl":
        tp_pct = _safe_float(rule.get("tp_pct"))
        sl_pct = _safe_float(rule.get("sl_pct"))
        tp_level = entry_mark * (1 + (tp_pct or 0.0))
        sl_level = entry_mark * (1 + (sl_pct or 0.0))
        for event in events:
            mark = _safe_float(event.get("mark"))
            if mark is None:
                continue
            if tp_pct is not None and mark >= tp_level:
                exit_event = event
                exit_reason = "tp"
                break
            if sl_pct is not None and mark <= sl_level:
                exit_event = event
                exit_reason = "sl"
                break

    elif rule_type == "touch":
        prefixes = rule.get("event_prefixes") or []
        keys = rule.get("event_keys") or []
        for event in events:
            event_key = event.get("event_key") or ""
            if event_key in keys:
                exit_event = event
                exit_reason = "touch"
                break
            if any(str(event_key).startswith(prefix) for prefix in prefixes):
                exit_event = event
                exit_reason = "touch"
                break

    elif rule_type == "time_stop":
        max_seconds = _safe_float(rule.get("max_seconds"))
        if max_seconds is not None and entry_ts is not None:
            for event in events:
                ts = parse_ts(event.get("ts"))
                if ts is None:
                    continue
                if (ts - entry_ts).total_seconds() >= max_seconds:
                    exit_event = event
                    exit_reason = "time_stop"
                    break

    if exit_event is None and events:
        exit_event = events[-1]
        exit_reason = exit_reason or "last_event"
    if exit_event is None:
        exit_reason = exit_reason or "no_path"

    return _build_result(
        signal_id,
        signal,
        entry_mark,
        entry_ts,
        events,
        name,
        rule_type,
        exit_event,
        exit_reason,
    )


def _build_result(
    signal_id: str,
    signal: dict,
    entry_mark: float,
    entry_ts: Optional[datetime],
    events: List[dict],
    rule_name: str,
    rule_type: str,
    exit_event: Optional[dict],
    exit_reason: str,
) -> dict:
    exit_mark = _safe_float(exit_event.get("mark")) if exit_event else None
    exit_ts = parse_ts(exit_event.get("ts")) if exit_event else None
    pnl = _round((exit_mark - entry_mark) if exit_mark is not None else None)
    pnl_pct = _round(_pct(pnl, entry_mark))
    seconds_held = _elapsed_seconds(entry_ts, exit_ts)
    return {
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
        "rule_name": rule_name,
        "rule_type": rule_type,
        "exit_reason": exit_reason,
        "exit_ts": exit_event.get("ts") if exit_event else None,
        "exit_event_key": exit_event.get("event_key") if exit_event else None,
        "exit_event_type": exit_event.get("event") if exit_event else None,
        "exit_underlying": exit_event.get("underlying_price") if exit_event else None,
        "exit_mark": exit_mark,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "seconds_in_trade": seconds_held,
    }


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
    parser = argparse.ArgumentParser(description="Simulate exit rules on research path events.")
    parser.add_argument("--signals", type=Path, default=OPTIONS_RESEARCH_SIGNALS_PATH)
    parser.add_argument("--paths", type=Path, default=OPTIONS_RESEARCH_PATHS_PATH)
    parser.add_argument("--rules", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=OPTIONS_RESEARCH_SIM_PATH)
    args = parser.parse_args()

    signals = load_signals(args.signals)
    paths = load_path_events(args.paths)
    rules = load_rules(args.rules)
    rows = simulate_rules(signals, paths, rules)
    write_jsonl(args.out, rows)
    print(
        f"[SIM] Signals: {len(signals)} | Paths: {sum(len(v) for v in paths.values())} "
        f"| Rules: {len(rules)} | Output: {args.out}"
    )


if __name__ == "__main__":
    main()
