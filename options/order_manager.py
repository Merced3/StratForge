from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from .execution_tradier import OptionOrderRequest, OrderStatus, OrderSubmitResult
from .quote_service import OptionContract, OptionQuoteService
from .selection import (
    DEFAULT_SELECTOR_REGISTRY,
    SelectionRequest,
    SelectionResult,
    SelectorRegistry,
    select_contract,
)


@dataclass
class OrderContext:
    order_id: str
    contract: OptionContract
    side: str
    quantity: int
    order_type: str
    requested_at: datetime
    selector_name: Optional[str] = None
    position_id: Optional[str] = None
    status: Optional[str] = None
    fill_price: Optional[float] = None
    applied_to_position: bool = False


@dataclass
class Position:
    position_id: str
    contract: OptionContract
    quantity_open: int
    avg_entry: Optional[float]
    realized_pnl: float
    status: str
    created_at: datetime
    updated_at: datetime
    strategy_tag: Optional[str] = None
    orders: list = field(default_factory=list)


@dataclass
class PositionActionResult:
    position_id: str
    order_result: OrderSubmitResult


class OptionsOrderManager:
    def __init__(
        self,
        quote_service: OptionQuoteService,
        executor,
        selector_registry: Optional[SelectorRegistry] = None,
        logger=None,
    ) -> None:
        self._quote_service = quote_service
        self._executor = executor
        self._selectors = selector_registry or DEFAULT_SELECTOR_REGISTRY
        self._logger = logger
        self._orders: Dict[str, OrderContext] = {}
        self._positions: Dict[str, Position] = {}

    def select_contract(
        self,
        request: SelectionRequest,
        selector_name: str = "price-range-otm",
    ) -> SelectionResult:
        snapshot = self._quote_service.get_snapshot()
        result = select_contract(
            quotes=snapshot.values(),
            request=request,
            selector_name=selector_name,
            registry=self._selectors,
        )
        if result is None:
            raise RuntimeError(f"No contract found for selector '{selector_name}'")
        return result

    async def buy(
        self,
        request: SelectionRequest,
        selector_name: str = "price-range-otm",
        quantity: int = 1,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> OrderSubmitResult:
        selection = self.select_contract(request, selector_name)
        contract = selection.quote.contract
        order_request = OptionOrderRequest(
            symbol=contract.symbol,
            option_type=contract.option_type,
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=quantity,
            side="buy_to_open",
            order_type=order_type,
            limit_price=limit_price,
        )
        result = await self._executor.submit_option_order(order_request)
        context = OrderContext(
            order_id=result.order_id,
            contract=contract,
            side="buy_to_open",
            quantity=quantity,
            order_type=order_type,
            requested_at=datetime.now(timezone.utc),
            selector_name=selector_name,
            status=result.status,
            fill_price=_extract_fill_price(result),
        )
        self._orders[result.order_id] = context
        return result

    async def sell(
        self,
        contract: OptionContract,
        quantity: int,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> OrderSubmitResult:
        order_request = OptionOrderRequest(
            symbol=contract.symbol,
            option_type=contract.option_type,
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=quantity,
            side="sell_to_close",
            order_type=order_type,
            limit_price=limit_price,
        )
        result = await self._executor.submit_option_order(order_request)
        context = OrderContext(
            order_id=result.order_id,
            contract=contract,
            side="sell_to_close",
            quantity=quantity,
            order_type=order_type,
            requested_at=datetime.now(timezone.utc),
            status=result.status,
            fill_price=_extract_fill_price(result),
        )
        self._orders[result.order_id] = context
        return result

    async def get_status(self, order_id: str) -> OrderStatus:
        status = await self._executor.get_order_status(order_id)
        context = self._orders.get(order_id)
        if context:
            context.status = status.status
            if status.avg_fill_price is not None:
                context.fill_price = status.avg_fill_price
            if not context.applied_to_position:
                self._maybe_apply_fill(context)
        return status

    def get_position(self, position_id: str) -> Optional[Position]:
        return self._positions.get(position_id)

    def list_positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    async def open_position(
        self,
        request: SelectionRequest,
        selector_name: str = "price-range-otm",
        quantity: int = 1,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        strategy_tag: Optional[str] = None,
    ) -> PositionActionResult:
        selection = self.select_contract(request, selector_name)
        contract = selection.quote.contract
        position_id = _build_position_id(contract, strategy_tag)
        now = datetime.now(timezone.utc)
        position = Position(
            position_id=position_id,
            contract=contract,
            quantity_open=0,
            avg_entry=None,
            realized_pnl=0.0,
            status="pending",
            created_at=now,
            updated_at=now,
            strategy_tag=strategy_tag,
        )
        self._positions[position_id] = position

        result = await self._submit_order(
            contract=contract,
            side="buy_to_open",
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            selector_name=selector_name,
            position_id=position_id,
        )
        return PositionActionResult(position_id=position_id, order_result=result)

    async def add_to_position(
        self,
        position_id: str,
        quantity: int,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> PositionActionResult:
        position = self._require_position(position_id)
        result = await self._submit_order(
            contract=position.contract,
            side="buy_to_open",
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            position_id=position_id,
        )
        return PositionActionResult(position_id=position_id, order_result=result)

    async def trim_position(
        self,
        position_id: str,
        quantity: int,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> PositionActionResult:
        position = self._require_position(position_id)
        if quantity > position.quantity_open:
            raise ValueError("trim quantity exceeds open position")
        result = await self._submit_order(
            contract=position.contract,
            side="sell_to_close",
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            position_id=position_id,
        )
        return PositionActionResult(position_id=position_id, order_result=result)

    async def close_position(
        self,
        position_id: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Optional[PositionActionResult]:
        position = self._require_position(position_id)
        if position.quantity_open <= 0:
            return None
        return await self.trim_position(
            position_id=position_id,
            quantity=position.quantity_open,
            order_type=order_type,
            limit_price=limit_price,
        )

    def get_context(self, order_id: str) -> Optional[OrderContext]:
        return self._orders.get(order_id)

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)

    async def _submit_order(
        self,
        contract: OptionContract,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[float],
        selector_name: Optional[str] = None,
        position_id: Optional[str] = None,
    ) -> OrderSubmitResult:
        order_request = OptionOrderRequest(
            symbol=contract.symbol,
            option_type=contract.option_type,
            strike=contract.strike,
            expiration=contract.expiration,
            quantity=quantity,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
        )
        result = await self._executor.submit_option_order(order_request)
        context = OrderContext(
            order_id=result.order_id,
            contract=contract,
            side=side,
            quantity=quantity,
            order_type=order_type,
            requested_at=datetime.now(timezone.utc),
            selector_name=selector_name,
            position_id=position_id,
            status=result.status,
            fill_price=_extract_fill_price(result),
        )
        self._orders[result.order_id] = context
        if position_id:
            position = self._positions.get(position_id)
            if position:
                position.orders.append(result.order_id)
        self._maybe_apply_fill(context)
        return result

    def _maybe_apply_fill(self, context: OrderContext) -> None:
        if context.applied_to_position:
            return
        if context.position_id is None:
            return
        if context.status != "filled":
            return
        if context.fill_price is None:
            return
        position = self._positions.get(context.position_id)
        if not position:
            return

        if context.side == "buy_to_open":
            self._apply_buy_fill(position, context.quantity, context.fill_price)
        elif context.side == "sell_to_close":
            self._apply_sell_fill(position, context.quantity, context.fill_price)
        context.applied_to_position = True

    def _apply_buy_fill(self, position: Position, quantity: int, fill_price: float) -> None:
        if quantity <= 0:
            return
        total_qty = position.quantity_open + quantity
        if position.avg_entry is None or position.quantity_open <= 0:
            position.avg_entry = fill_price
        else:
            position.avg_entry = (
                (position.avg_entry * position.quantity_open) + (fill_price * quantity)
            ) / total_qty
        position.quantity_open = total_qty
        position.status = "open"
        position.updated_at = datetime.now(timezone.utc)

    def _apply_sell_fill(self, position: Position, quantity: int, fill_price: float) -> None:
        if quantity <= 0:
            return
        if position.avg_entry is not None:
            position.realized_pnl += (fill_price - position.avg_entry) * quantity * CONTRACT_MULTIPLIER
        position.quantity_open = max(0, position.quantity_open - quantity)
        if position.quantity_open == 0:
            position.status = "closed"
        position.updated_at = datetime.now(timezone.utc)

    def _require_position(self, position_id: str) -> Position:
        position = self._positions.get(position_id)
        if not position:
            raise KeyError(f"unknown position_id: {position_id}")
        return position


def _extract_fill_price(result: OrderSubmitResult) -> Optional[float]:
    raw = result.raw if isinstance(result.raw, dict) else None
    if not raw:
        return None
    if "fill_price" in raw:
        return _safe_float(raw.get("fill_price"))
    return None


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_position_id(contract: OptionContract, strategy_tag: Optional[str] = None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    strike_label = _format_strike(contract.strike)
    tag_label = _sanitize_tag(strategy_tag)
    parts = [
        "pos",
        contract.symbol,
        contract.option_type,
        strike_label,
        contract.expiration,
    ]
    if tag_label:
        parts.append(f"tag-{tag_label}")
    parts.append(stamp)
    return "-".join(parts)


def _format_strike(strike: float) -> str:
    as_text = f"{strike:.4f}".rstrip("0").rstrip(".")
    return as_text.replace(".", "p")


def _sanitize_tag(tag: Optional[str]) -> str:
    if not tag:
        return ""
    cleaned = []
    for ch in tag.strip():
        if ch.isalnum() or ch in ("-", "_"):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    return "".join(cleaned)


CONTRACT_MULTIPLIER = 100
