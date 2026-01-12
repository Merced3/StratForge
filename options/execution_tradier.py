from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import aiohttp


class TradierOrderError(RuntimeError):
    pass


@dataclass(frozen=True)
class OptionOrderRequest:
    symbol: str
    option_type: str  # "call" or "put"
    strike: float
    expiration: str  # YYYYMMDD
    quantity: int
    side: str  # "buy_to_open" or "sell_to_close"
    order_type: str = "market"
    limit_price: Optional[float] = None
    duration: str = "gtc"


@dataclass
class OrderSubmitResult:
    order_id: str
    status: Optional[str]
    raw: dict


@dataclass
class OrderStatus:
    order_id: str
    status: str
    avg_fill_price: Optional[float]
    filled_quantity: Optional[int]
    raw: dict


class TradierOrderExecutor:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        account_id: str,
        access_token: str,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._account_id = account_id
        self._access_token = access_token
        self._logger = logger

    async def submit_option_order(self, request: OptionOrderRequest) -> OrderSubmitResult:
        url = f"{self._base_url}/accounts/{self._account_id}/orders"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        option_symbol = _build_option_symbol(
            request.symbol,
            request.option_type,
            request.strike,
            request.expiration,
        )
        payload = {
            "class": "option",
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "type": request.order_type,
            "duration": request.duration,
            "option_symbol": option_symbol,
        }
        if request.order_type == "limit":
            if request.limit_price is None:
                raise ValueError("limit_price required for limit orders")
            payload["price"] = request.limit_price

        self._log(f"[TRADIER] Submit {payload}")
        async with self._session.post(url, headers=headers, data=payload) as response:
            raw_text = await response.text()
            if response.status != 200:
                raise TradierOrderError(
                    f"submit failed {response.status}: {raw_text}"
                )
            data = await response.json()

        order = data.get("order")
        if not order:
            errors = data.get("errors") or data
            raise TradierOrderError(f"submit failed: {errors}")
        return OrderSubmitResult(
            order_id=str(order.get("id")),
            status=order.get("status"),
            raw=data,
        )

    async def get_order_status(self, order_id: str) -> OrderStatus:
        url = f"{self._base_url}/accounts/{self._account_id}/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        async with self._session.get(url, headers=headers) as response:
            raw_text = await response.text()
            if response.status != 200:
                raise TradierOrderError(
                    f"status failed {response.status}: {raw_text}"
                )
            data = await response.json()

        order = data.get("order")
        if not order:
            raise TradierOrderError(f"status missing order: {data}")
        return OrderStatus(
            order_id=str(order.get("id", order_id)),
            status=str(order.get("status")),
            avg_fill_price=_to_float(order.get("avg_fill_price")),
            filled_quantity=_to_int(order.get("quantity")),
            raw=data,
        )

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)


def _build_option_symbol(
    symbol: str,
    option_type: str,
    strike: float,
    expiration: str,
) -> str:
    expiration_short = datetime.strptime(expiration, "%Y%m%d").strftime("%y%m%d")
    option_flag = option_type[0].upper()
    strike_1000 = int(float(strike) * 1000)
    return f"{symbol}{expiration_short}{option_flag}{strike_1000:08d}"


def _to_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None



"""
Example usage:

async with aiohttp.ClientSession() as session:
    executor = TradierOrderExecutor(
        session,
        base_url=TRADIER_BASE_URL,
        account_id=TRADIER_ACCOUNT_ID,
        access_token=TRADIER_ACCESS_TOKEN,
        logger=print_log,
    )

    request = OptionOrderRequest(
        symbol="SPY",
        option_type="call",
        strike=520.0,
        expiration="20260106",
        quantity=1,
        side="buy_to_open",
    )

    result = await executor.submit_option_order(request)
    status = await executor.get_order_status(result.order_id)
"""