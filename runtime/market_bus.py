from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class CandleCloseEvent:
    symbol: str
    timeframe: str
    candle: dict
    closed_at: datetime
    source: str


class MarketEventBus:
    def __init__(self, logger: Optional[Callable[[str], None]] = None) -> None:
        self._logger = logger
        self._listener_id = 0
        self._listeners: Dict[int, Callable[[CandleCloseEvent], object]] = {}

    def register_listener(self, callback: Callable[[CandleCloseEvent], object]) -> int:
        self._listener_id += 1
        self._listeners[self._listener_id] = callback
        return self._listener_id

    def register_queue(self, maxsize: int = 0) -> tuple[int, asyncio.Queue]:
        queue: asyncio.Queue[CandleCloseEvent] = asyncio.Queue(maxsize=maxsize)

        def _enqueue(event: CandleCloseEvent) -> None:
            if maxsize > 0 and queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        listener_id = self.register_listener(_enqueue)
        return listener_id, queue

    def remove_listener(self, listener_id: int) -> None:
        self._listeners.pop(listener_id, None)

    async def publish_candle_close(self, event: CandleCloseEvent) -> None:
        for callback in list(self._listeners.values()):
            self._dispatch(callback, event)

    def _dispatch(self, callback: Callable[[CandleCloseEvent], object], event: CandleCloseEvent) -> None:
        try:
            result = callback(event)
            if inspect.isawaitable(result):
                asyncio.create_task(result)
        except Exception as exc:
            self._log(f"[MARKET BUS] Listener error: {exc}")

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)
