from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from .order_manager import Position
from .quote_service import OptionQuote


CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class PositionUpdate:
    position_id: str
    contract_key: str
    quote: OptionQuote
    mark_price: Optional[float]
    mark_source: str
    unrealized_pnl: Optional[float]
    unrealized_pct: Optional[float]
    realized_pnl: float
    quantity_open: int
    avg_entry: Optional[float]
    status: str
    strategy_tag: Optional[str]
    updated_at: datetime


@dataclass
class _Listener:
    callback: Callable[[List[PositionUpdate]], object]
    position_ids: Optional[Set[str]]


class PositionWatcher:
    def __init__(
        self,
        quote_service,
        positions_provider: Callable[[], Iterable[Position]],
        refresh_interval: float = 1.0,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._quote_service = quote_service
        self._positions_provider = positions_provider
        self._refresh_interval = refresh_interval
        self._logger = logger
        self._listener_id = 0
        self._listeners: Dict[int, _Listener] = {}
        self._quote_listener_id: Optional[int] = None
        self._quote_queue: Optional[asyncio.Queue] = None
        self._positions: Dict[str, Position] = {}
        self._contract_map: Dict[str, List[str]] = {}
        self._active_contracts: Set[str] = set()
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    def register_listener(
        self,
        callback: Callable[[List[PositionUpdate]], object],
        position_ids: Optional[Iterable[str]] = None,
    ) -> int:
        self._listener_id += 1
        self._listeners[self._listener_id] = _Listener(
            callback=callback,
            position_ids=set(position_ids) if position_ids else None,
        )
        return self._listener_id

    def register_queue(
        self,
        position_ids: Optional[Iterable[str]] = None,
        maxsize: int = 0,
    ) -> Tuple[int, asyncio.Queue]:
        queue: asyncio.Queue[List[PositionUpdate]] = asyncio.Queue(maxsize=maxsize)

        def _enqueue(updates: List[PositionUpdate]) -> None:
            if maxsize > 0 and queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(list(updates))
            except asyncio.QueueFull:
                pass

        listener_id = self.register_listener(_enqueue, position_ids=position_ids)
        return listener_id, queue

    def update_listener_positions(self, listener_id: int, position_ids: Iterable[str]) -> None:
        listener = self._listeners.get(listener_id)
        if listener:
            listener.position_ids = set(position_ids)

    def remove_listener(self, listener_id: int) -> None:
        self._listeners.pop(listener_id, None)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        else:
            self._stop_event.clear()

        self._quote_listener_id, self._quote_queue = self._quote_service.register_queue(
            contract_ids=set(),
            maxsize=1,
        )
        self._task = asyncio.create_task(self._run(), name="PositionWatcher")

    async def stop(self) -> None:
        if not self._task:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        if self._quote_listener_id is not None:
            self._quote_service.remove_listener(self._quote_listener_id)
            self._quote_listener_id = None

    async def _run(self) -> None:
        last_refresh = 0.0
        timeout = max(self._refresh_interval, 0.1)
        while self._stop_event is not None and not self._stop_event.is_set():
            now = time.monotonic()
            if now - last_refresh >= self._refresh_interval:
                self._refresh_positions()
                last_refresh = now

            if not self._quote_queue:
                await asyncio.sleep(timeout)
                continue

            try:
                updates = await asyncio.wait_for(self._quote_queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                continue

            events = self._build_updates(updates)
            if events:
                self._notify_listeners(events)

    def _refresh_positions(self) -> None:
        positions = [p for p in self._positions_provider() if p.status != "closed" and p.quantity_open > 0]
        self._positions = {p.position_id: p for p in positions}
        contract_map: Dict[str, List[str]] = {}
        for pos in positions:
            contract_map.setdefault(pos.contract.key, []).append(pos.position_id)
        self._contract_map = contract_map
        active_contracts = set(contract_map.keys())
        if active_contracts != self._active_contracts and self._quote_listener_id is not None:
            self._quote_service.update_listener_contracts(self._quote_listener_id, active_contracts)
            self._active_contracts = active_contracts

    def _build_updates(self, quotes: Iterable[OptionQuote]) -> List[PositionUpdate]:
        events: List[PositionUpdate] = []
        now = datetime.now(timezone.utc)
        for quote in quotes:
            position_ids = self._contract_map.get(quote.contract.key, [])
            for position_id in position_ids:
                position = self._positions.get(position_id)
                if not position:
                    continue
                mark_price, mark_source = _select_mark_price(quote)
                unrealized_pnl = None
                unrealized_pct = None
                if mark_price is not None and position.avg_entry is not None:
                    unrealized_pnl = (mark_price - position.avg_entry) * position.quantity_open * CONTRACT_MULTIPLIER
                    if position.avg_entry:
                        unrealized_pct = ((mark_price - position.avg_entry) / position.avg_entry) * 100.0
                events.append(
                    PositionUpdate(
                        position_id=position.position_id,
                        contract_key=quote.contract.key,
                        quote=quote,
                        mark_price=mark_price,
                        mark_source=mark_source,
                        unrealized_pnl=unrealized_pnl,
                        unrealized_pct=unrealized_pct,
                        realized_pnl=position.realized_pnl,
                        quantity_open=position.quantity_open,
                        avg_entry=position.avg_entry,
                        status=position.status,
                        strategy_tag=position.strategy_tag,
                        updated_at=now,
                    )
                )
        return events

    def _notify_listeners(self, updates: List[PositionUpdate]) -> None:
        for listener in list(self._listeners.values()):
            if listener.position_ids is None:
                self._dispatch(listener.callback, updates)
                continue
            filtered = [u for u in updates if u.position_id in listener.position_ids]
            if filtered:
                self._dispatch(listener.callback, filtered)

    def _dispatch(self, callback: Callable[[List[PositionUpdate]], object], updates: List[PositionUpdate]) -> None:
        try:
            result = callback(updates)
            if inspect.isawaitable(result):
                asyncio.create_task(result)
        except Exception as exc:
            self._log(f"[WATCHER] Listener error: {exc}")

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)


def _select_mark_price(quote: OptionQuote) -> Tuple[Optional[float], str]:
    if quote.bid is not None:
        return quote.bid, "bid"
    if quote.mid is not None:
        return quote.mid, "mid"
    if quote.last is not None:
        return quote.last, "last"
    if quote.ask is not None:
        return quote.ask, "ask"
    return None, "none"
