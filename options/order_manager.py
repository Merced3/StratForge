from __future__ import annotations

from dataclasses import dataclass
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
    status: Optional[str] = None
    fill_price: Optional[float] = None


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
        return status

    def get_context(self, order_id: str) -> Optional[OrderContext]:
        return self._orders.get(order_id)

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)


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
