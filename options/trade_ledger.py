from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from paths import OPTIONS_TRADE_LEDGER_PATH
from utils.timezone import NY_TZ

from .execution_tradier import OrderSubmitResult
from .order_manager import Position


@dataclass
class TradeEvent:
    ts: str
    event: str
    position_id: str
    order_id: Optional[str]
    order_status: Optional[str]
    symbol: str
    option_type: str
    strike: float
    expiration: str
    contract_key: str
    strategy_tag: Optional[str]
    quantity: Optional[int]
    fill_price: Optional[float]
    total_value: Optional[float]
    avg_entry: Optional[float]
    quantity_open: int
    position_status: str
    realized_pnl: Optional[float]
    reason: Optional[str]


def build_trade_event(
    event: str,
    position: Position,
    order_result: Optional[OrderSubmitResult],
    quantity: Optional[int],
    fill_price: Optional[float],
    reason: Optional[str],
) -> TradeEvent:
    now = datetime.now(timezone.utc).isoformat()
    contract = position.contract
    order_id = order_result.order_id if order_result else None
    status = order_result.status if order_result else None
    total_value = None
    if quantity is not None and fill_price is not None:
        total_value = quantity * fill_price * 100
    return TradeEvent(
        ts=now,
        event=event,
        position_id=position.position_id,
        order_id=order_id,
        order_status=status,
        symbol=contract.symbol,
        option_type=contract.option_type,
        strike=contract.strike,
        expiration=contract.expiration,
        contract_key=contract.key,
        strategy_tag=position.strategy_tag,
        quantity=quantity,
        fill_price=fill_price,
        total_value=total_value,
        avg_entry=position.avg_entry,
        quantity_open=position.quantity_open,
        position_status=position.status,
        realized_pnl=position.realized_pnl,
        reason=reason,
    )


def record_trade_event(
    event: TradeEvent,
    path: Optional[Path] = None,
    logger=None,
) -> None:
    target = path or OPTIONS_TRADE_LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(event), ensure_ascii=True)
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    except Exception as exc:
        if logger:
            logger(f"[LEDGER] Failed to write trade event: {exc}")


def sum_realized_pnl_for_day(
    trading_day: Optional[str],
    path: Optional[Path] = None,
) -> float:
    if not trading_day:
        trading_day = datetime.now(NY_TZ).strftime("%Y-%m-%d")
    target = path or OPTIONS_TRADE_LEDGER_PATH
    if not target.exists():
        return 0.0
    total = 0.0
    try:
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("event") != "close":
                    continue
                ts = payload.get("ts")
                if not ts:
                    continue
                try:
                    timestamp = datetime.fromisoformat(ts)
                except ValueError:
                    continue
                day = timestamp.astimezone(NY_TZ).strftime("%Y-%m-%d")
                if day != trading_day:
                    continue
                realized = payload.get("realized_pnl")
                if realized is None:
                    continue
                try:
                    total += float(realized)
                except (TypeError, ValueError):
                    continue
    except OSError:
        return 0.0
    return total
