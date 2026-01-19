from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Optional
from uuid import uuid4

from .execution_tradier import OptionOrderRequest, OrderStatus, OrderSubmitResult
from .quote_service import OptionContract, OptionQuote


class PaperOrderError(RuntimeError):
    pass


@dataclass
class PaperOrder:
    order_id: str
    request: OptionOrderRequest
    status: str
    submitted_at: datetime
    filled_at: Optional[datetime]
    fill_price: Optional[float]
    rejection_reason: Optional[str] = None


class PaperOrderExecutor:
    def __init__(
        self,
        quote_getter: Callable[[str], Optional[OptionQuote]],
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._quote_getter = quote_getter
        self._logger = logger
        self._orders: Dict[str, PaperOrder] = {}

    async def submit_option_order(self, request: OptionOrderRequest) -> OrderSubmitResult:
        now = datetime.now(timezone.utc)
        order_id = f"paper-{uuid4().hex}"
        order = PaperOrder(
            order_id=order_id,
            request=request,
            status="submitted",
            submitted_at=now,
            filled_at=None,
            fill_price=None,
        )

        price = self._resolve_fill_price(request)
        if price is None:
            order.status = "rejected"
            order.rejection_reason = "missing_quote"
            self._orders[order_id] = order
            return OrderSubmitResult(order_id=order_id, status=order.status, raw={"error": order.rejection_reason})

        if request.order_type == "limit":
            if request.limit_price is None:
                raise ValueError("limit_price required for limit orders")
            if request.side == "buy_to_open" and price > request.limit_price:
                order.status = "rejected"
                order.rejection_reason = "limit_not_reached"
            elif request.side == "sell_to_close" and price < request.limit_price:
                order.status = "rejected"
                order.rejection_reason = "limit_not_reached"
            else:
                order.status = "filled"
        else:
            order.status = "filled"

        if order.status == "filled":
            order.filled_at = now
            order.fill_price = price

        self._orders[order_id] = order
        raw = {
            "status": order.status,
            "fill_price": order.fill_price,
            "rejection_reason": order.rejection_reason,
        }
        return OrderSubmitResult(order_id=order_id, status=order.status, raw=raw)

    async def get_order_status(self, order_id: str) -> OrderStatus:
        order = self._orders.get(order_id)
        if not order:
            raise PaperOrderError(f"unknown order_id: {order_id}")
        return OrderStatus(
            order_id=order.order_id,
            status=order.status,
            avg_fill_price=order.fill_price,
            filled_quantity=order.request.quantity if order.fill_price is not None else None,
            raw={
                "status": order.status,
                "fill_price": order.fill_price,
                "submitted_at": order.submitted_at.isoformat(),
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "rejection_reason": order.rejection_reason,
            },
        )

    def _resolve_fill_price(self, request: OptionOrderRequest) -> Optional[float]:
        contract = OptionContract(
            symbol=request.symbol,
            option_type=request.option_type,
            strike=request.strike,
            expiration=request.expiration,
        )
        quote = self._quote_getter(contract.key)
        if quote is None:
            self._log(f"[PAPER] Missing quote for {contract.key}")
            return None
        if request.side == "buy_to_open":
            return _pick_first(quote.ask, quote.mid, quote.last, quote.bid)
        return _pick_first(quote.bid, quote.mid, quote.last, quote.ask)

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)


def _pick_first(*values: Optional[float]) -> Optional[float]:
    for value in values:
        if value is not None:
            return float(value)
    return None

"""
Example of usage:

service = OptionQuoteService(...)
await service.start()

paper = PaperOrderExecutor(service.get_quote, logger=print_log)
req = OptionOrderRequest(
    symbol="SPY",
    option_type="call",
    strike=520.0,
    expiration="20260106",
    quantity=1,
    side="buy_to_open",
)
result = await paper.submit_option_order(req)
status = await paper.get_order_status(result.order_id)
"""
