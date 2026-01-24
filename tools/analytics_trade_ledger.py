from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paths import OPTIONS_TRADE_LEDGER_PATH


@dataclass
class PositionSummary:
    position_id: str
    strategy_tag: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    realized_pnl: Optional[float] = None
    status: Optional[str] = None
    entry_cost: float = 0.0

    @property
    def hold_time(self) -> Optional[timedelta]:
        if self.opened_at and self.closed_at:
            return self.closed_at - self.opened_at
        return None


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_positions(path: Path) -> list[PositionSummary]:
    positions: dict[str, PositionSummary] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            position_id = payload.get("position_id")
            if not position_id:
                continue

            summary = positions.get(position_id)
            if summary is None:
                summary = PositionSummary(position_id=position_id)
                positions[position_id] = summary

            if summary.strategy_tag is None:
                tag = payload.get("strategy_tag")
                if tag:
                    summary.strategy_tag = tag

            status = payload.get("position_status")
            if status:
                summary.status = status

            event = payload.get("event")
            ts = _parse_ts(payload.get("ts"))
            if event == "open" and ts:
                if summary.opened_at is None or ts < summary.opened_at:
                    summary.opened_at = ts
            elif event == "close" and ts:
                if summary.closed_at is None or ts > summary.closed_at:
                    summary.closed_at = ts
            if event in ("open", "add"):
                total_value = _safe_float(payload.get("total_value"))
                if total_value is None:
                    quantity = _safe_float(payload.get("quantity"))
                    fill_price = _safe_float(payload.get("fill_price"))
                    if quantity is not None and fill_price is not None:
                        total_value = quantity * fill_price * 100
                if total_value is not None:
                    summary.entry_cost += total_value

            realized = payload.get("realized_pnl")
            if realized is not None:
                try:
                    summary.realized_pnl = float(realized)
                except (TypeError, ValueError):
                    pass

    return list(positions.values())


def load_positions(path: Path) -> list[PositionSummary]:
    return _load_positions(path)


def _is_closed(summary: PositionSummary) -> bool:
    if summary.closed_at is not None:
        return True
    if summary.status:
        return summary.status.lower() == "closed"
    return False


def _format_float(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_ratio(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_percent(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _format_timedelta(delta: Optional[timedelta]) -> str:
    if not delta:
        return "-"
    total_seconds = int(delta.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{sign}{hours}h{minutes:02d}m"
    if minutes:
        return f"{sign}{minutes}m{seconds:02d}s"
    return f"{sign}{seconds}s"


def _compute_metrics(positions: list[PositionSummary]) -> dict:
    closed = [p for p in positions if _is_closed(p) and p.realized_pnl is not None]
    wins = [p for p in closed if p.realized_pnl > 0]
    losses = [p for p in closed if p.realized_pnl < 0]
    hold_times = [p.hold_time for p in closed if p.hold_time is not None]

    pnl_total = sum(p.realized_pnl for p in closed) if closed else 0.0
    win_rate = (len(wins) / len(closed)) if closed else None
    avg_win = (sum(p.realized_pnl for p in wins) / len(wins)) if wins else None
    avg_loss = (sum(p.realized_pnl for p in losses) / len(losses)) if losses else None
    avg_hold = (sum(hold_times, timedelta()) / len(hold_times)) if hold_times else None
    expectancy = (pnl_total / len(closed)) if closed else None
    entry_cost = sum(p.entry_cost for p in closed) if closed else 0.0
    pnl_per_dollar = (pnl_total / entry_cost) if entry_cost > 0 else None

    return {
        "positions": len(positions),
        "closed": len(closed),
        "open": len(positions) - len(closed),
        "pnl_total": pnl_total,
        "entry_cost": entry_cost,
        "pnl_per_dollar": pnl_per_dollar,
        "expectancy": expectancy,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_hold": avg_hold,
    }


def compute_metrics(positions: list[PositionSummary]) -> dict:
    return _compute_metrics(positions)


def _format_line(label: str, value: str, width: int = 18) -> str:
    return f"    {label:<{width}}= {value}"


def _print_summary(label: str, metrics: dict) -> None:
    pnl_per_dollar = metrics.get("pnl_per_dollar")
    if pnl_per_dollar is None:
        pnl_per_dollar_label = "-"
    else:
        pnl_per_dollar_label = f"{_format_ratio(pnl_per_dollar)} ({_format_percent(pnl_per_dollar)})"

    lines = [
        _format_line("positions_total", str(metrics["positions"])),
        _format_line("positions_closed", str(metrics["closed"])),
        _format_line("positions_open", str(metrics["open"])),
        _format_line("realized_pnl", _format_float(metrics["pnl_total"])),
        _format_line("entry_cost", _format_float(metrics["entry_cost"])),
        _format_line("pnl_per_dollar", pnl_per_dollar_label),
        _format_line("expectancy", _format_float(metrics["expectancy"])),
        _format_line("win_rate", _format_percent(metrics["win_rate"])),
        _format_line("avg_win", _format_float(metrics["avg_win"])),
        _format_line("avg_loss", _format_float(metrics["avg_loss"])),
        _format_line("avg_hold", _format_timedelta(metrics["avg_hold"])),
    ]
    print(f"\n{label}")
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize options trade ledger (JSONL).")
    parser.add_argument(
        "--path",
        default=str(OPTIONS_TRADE_LEDGER_PATH),
        help="Path to trade_events.jsonl",
    )
    parser.add_argument(
        "--by-strategy",
        action="store_true",
        help="Print per-strategy summary.",
    )
    parser.add_argument(
        "--by-position",
        action="store_true",
        help="Print per-position details.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Print per-strategy and per-position sections.",
    )
    args = parser.parse_args()

    ledger_path = Path(args.path)
    if not ledger_path.exists():
        print(f"[ANALYTICS] Ledger not found: {ledger_path}")
        return 1

    positions = _load_positions(ledger_path)
    if not positions:
        print(f"[ANALYTICS] No trade events found in {ledger_path}")
        return 0

    print(f"[ANALYTICS] Ledger: {ledger_path}")
    overall = _compute_metrics(positions)
    _print_summary("[SUMMARY]", overall)

    show_strategy = args.by_strategy or args.details
    show_position = args.by_position or args.details

    if show_strategy:
        print("\n[BY_STRATEGY]")
        by_strategy: dict[str, list[PositionSummary]] = {}
        for summary in positions:
            tag = summary.strategy_tag or "unknown"
            by_strategy.setdefault(tag, []).append(summary)
        for tag in sorted(by_strategy.keys()):
            metrics = _compute_metrics(by_strategy[tag])
            pnl_per_dollar = metrics.get("pnl_per_dollar")
            pnl_per_dollar_label = (
                f"{_format_ratio(pnl_per_dollar)} ({_format_percent(pnl_per_dollar)})"
                if pnl_per_dollar is not None
                else "-"
            )
            print(
                f"tag={tag} positions={metrics['positions']} closed={metrics['closed']} "
                f"pnl={_format_float(metrics['pnl_total'])} "
                f"entry_cost={_format_float(metrics['entry_cost'])} "
                f"pnl_per_dollar={pnl_per_dollar_label} "
                f"expectancy={_format_float(metrics['expectancy'])} "
                f"win_rate={_format_percent(metrics['win_rate'])} "
                f"avg_win={_format_float(metrics['avg_win'])} "
                f"avg_loss={_format_float(metrics['avg_loss'])} "
                f"avg_hold={_format_timedelta(metrics['avg_hold'])}"
            )

    if show_position:
        print("\n[BY_POSITION]")
        def sort_key(item: PositionSummary) -> tuple:
            return (item.opened_at is None, item.opened_at or datetime.min, item.position_id)

        for summary in sorted(positions, key=sort_key):
            status = summary.status or ("closed" if _is_closed(summary) else "open")
            print(
                f"{summary.position_id} "
                f"tag={summary.strategy_tag or 'unknown'} "
                f"status={status} "
                f"pnl={_format_float(summary.realized_pnl)} "
                f"hold={_format_timedelta(summary.hold_time)}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
