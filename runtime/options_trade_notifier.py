from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from data_acquisition import add_markers
from integrations.discord import (
    append_trade_update,
    edit_discord_message,
    extract_trade_totals,
    format_trade_add,
    format_trade_close,
    format_trade_open,
    format_trade_trim,
    get_message_content,
    print_discord,
)
from options.execution_tradier import OrderSubmitResult
from options.order_manager import OptionsOrderManager, Position
from options.trade_ledger import build_trade_event, record_trade_event
from utils.json_utils import load_message_ids, save_message_ids


@dataclass
class TradeMessageState:
    message_id: int
    content: str
    total_entry_cost: float = 0.0
    total_exit_value: float = 0.0
    total_exit_qty: int = 0

    def record_entry(self, quantity: Optional[int], fill_price: Optional[float]) -> None:
        if quantity is None or fill_price is None:
            return
        self.total_entry_cost += quantity * fill_price * 100

    def record_exit(self, quantity: Optional[int], fill_price: Optional[float]) -> None:
        if quantity is None or fill_price is None:
            return
        self.total_exit_value += quantity * fill_price * 100
        self.total_exit_qty += quantity

    def avg_exit(self) -> Optional[float]:
        if self.total_exit_qty <= 0:
            return None
        return self.total_exit_value / (self.total_exit_qty * 100)


class OptionsTradeNotifier:
    def __init__(
        self,
        order_manager: OptionsOrderManager,
        *,
        logger=None,
    ) -> None:
        self._order_manager = order_manager
        self._logger = logger
        self._trade_messages: Dict[str, TradeMessageState] = {}

    async def on_position_opened(
        self,
        position: Position,
        order_result: Optional[OrderSubmitResult],
        reason: str,
        timeframe: Optional[str] = None,
    ) -> None:
        try:
            quantity, fill_price = self._order_details(order_result)
            record_trade_event(
                build_trade_event("open", position, order_result, quantity, fill_price, reason),
                logger=self._logger,
            )
            if quantity is None or fill_price is None:
                self._log("[OPTIONS] Missing fill details for open; skipping Discord message.")
                return
            contract = position.contract
            total_investment = quantity * fill_price * 100
            message = format_trade_open(
                strategy_name=position.strategy_tag or "strategy",
                ticker_symbol=contract.symbol,
                strike=contract.strike,
                option_type=contract.option_type,
                quantity=quantity,
                order_price=fill_price,
                total_investment=total_investment,
                reason=reason,
            )
            sent = await print_discord(message)
            if sent:
                trade_state = TradeMessageState(
                    message_id=sent.id,
                    content=message,
                    total_entry_cost=total_investment,
                )
                self._trade_messages[position.position_id] = trade_state
                save_message_ids(position.position_id, sent.id)
            marker_tf = timeframe or "2M"
            await add_markers("buy", live_tf=marker_tf, x_offset=1)  # Trade executes after close; mark next candle.
        except Exception as exc:
            self._log(f"[OPTIONS] Open notify failed: {exc}")

    async def on_position_added(
        self,
        position: Position,
        order_result: Optional[OrderSubmitResult],
        reason: str,
        timeframe: Optional[str] = None,
    ) -> None:
        try:
            quantity, fill_price = self._order_details(order_result)
            record_trade_event(
                build_trade_event("add", position, order_result, quantity, fill_price, reason),
                logger=self._logger,
            )
            state = await self._get_trade_state(position.position_id)
            if not state:
                self._log(f"[OPTIONS] No Discord message tracked for {position.position_id}")
                return
            if quantity is None or fill_price is None:
                self._log("[OPTIONS] Missing fill details for add; skipping Discord update.")
                return
            total_value = quantity * fill_price * 100
            state.record_entry(quantity, fill_price)
            update_line = format_trade_add(quantity, total_value, fill_price, reason)
            await self._edit_trade_message(position.position_id, update_line)
            marker_tf = timeframe or "2M"
            await add_markers("buy", live_tf=marker_tf, x_offset=1)  # Trade executes after close; mark next candle.
        except Exception as exc:
            self._log(f"[OPTIONS] Add notify failed: {exc}")

    async def on_position_trimmed(
        self,
        position: Position,
        order_result: Optional[OrderSubmitResult],
        reason: str,
        timeframe: Optional[str] = None,
    ) -> None:
        try:
            quantity, fill_price = self._order_details(order_result)
            record_trade_event(
                build_trade_event("trim", position, order_result, quantity, fill_price, reason),
                logger=self._logger,
            )
            state = await self._get_trade_state(position.position_id)
            if not state:
                self._log(f"[OPTIONS] No Discord message tracked for {position.position_id}")
                return
            if quantity is None or fill_price is None:
                self._log("[OPTIONS] Missing fill details for trim; skipping Discord update.")
                return
            total_value = quantity * fill_price * 100
            state.record_exit(quantity, fill_price)
            update_line = format_trade_trim(quantity, total_value, fill_price, reason)
            await self._edit_trade_message(position.position_id, update_line)
            marker_tf = timeframe or "2M"
            await add_markers("trim", live_tf=marker_tf, x_offset=1)  # Trade executes after close; mark next candle.
        except Exception as exc:
            self._log(f"[OPTIONS] Trim notify failed: {exc}")

    async def on_position_closed(
        self,
        position: Position,
        order_result: Optional[OrderSubmitResult],
        reason: str,
        timeframe: Optional[str] = None,
    ) -> None:
        try:
            quantity, fill_price = self._order_details(order_result)
            record_trade_event(
                build_trade_event("close", position, order_result, quantity, fill_price, reason),
                logger=self._logger,
            )
            state = await self._get_trade_state(position.position_id)
            if state and quantity is not None and fill_price is not None:
                total_value = quantity * fill_price * 100
                state.record_exit(quantity, fill_price)
                update_line = format_trade_trim(quantity, total_value, fill_price, reason)
                await self._edit_trade_message(position.position_id, update_line)
            else:
                if not state:
                    self._log(f"[OPTIONS] No Discord message tracked for {position.position_id}")
                if quantity is None or fill_price is None:
                    self._log("[OPTIONS] Missing fill details for close; skipping sell line.")

            avg_exit = state.avg_exit() if state else None
            total_pnl = position.realized_pnl
            percent = (
                (total_pnl / state.total_entry_cost) * 100
                if state and state.total_entry_cost > 0
                else None
            )
            summary = format_trade_close(avg_exit, total_pnl, percent, None)
            if state:
                await self._edit_trade_message(position.position_id, summary)
            else:
                await print_discord(summary)
            marker_tf = timeframe or "2M"
            await add_markers("sell", live_tf=marker_tf, x_offset=1)  # Trade executes after close; mark next candle.
        except Exception as exc:
            self._log(f"[OPTIONS] Close notify failed: {exc}")

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)

    def _order_details(
        self,
        order_result: Optional[OrderSubmitResult],
    ) -> tuple[Optional[int], Optional[float]]:
        if not order_result:
            return None, None
        context = self._order_manager.get_context(order_result.order_id)
        quantity = context.quantity if context else None
        fill_price = context.fill_price if context else None
        if fill_price is None and isinstance(order_result.raw, dict):
            fill_price = order_result.raw.get("fill_price")
        return quantity, fill_price

    async def _get_trade_state(self, position_id: str) -> Optional[TradeMessageState]:
        state = self._trade_messages.get(position_id)
        if state:
            return state
        message_ids = load_message_ids()
        message_id = message_ids.get(position_id)
        if not message_id:
            return None
        content = await get_message_content(message_id)
        if not content:
            return None
        totals = extract_trade_totals(content)
        state = TradeMessageState(
            message_id=message_id,
            content=content,
            total_entry_cost=totals.get("total_entry_cost", 0.0),
            total_exit_value=totals.get("total_exit_value", 0.0),
            total_exit_qty=totals.get("total_exit_qty", 0),
        )
        self._trade_messages[position_id] = state
        return state

    async def _edit_trade_message(self, position_id: str, update_line: str) -> None:
        state = await self._get_trade_state(position_id)
        if not state:
            self._log(f"[OPTIONS] No Discord message tracked for {position_id}")
            return
        state.content = append_trade_update(state.content, update_line)
        await edit_discord_message(state.message_id, state.content)
