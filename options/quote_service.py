from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Protocol, Set, Tuple

import aiohttp


class RateLimitError(Exception):
    def __init__(self, retry_after: float):
        super().__init__(f"Rate limit; retry after {retry_after}s")
        self.retry_after = retry_after


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    option_type: str
    strike: float
    expiration: str

    @property
    def key(self) -> str:
        return f"{self.symbol}-{self.option_type}-{self.strike}-{self.expiration}"


@dataclass
class OptionQuote:
    contract: OptionContract
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    updated_at: datetime

    @property
    def mid(self) -> Optional[float]:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2.0


class OptionsProvider(Protocol):
    async def fetch_quotes(self, symbol: str, expiration: str) -> List[OptionQuote]:
        ...


@dataclass
class _Listener:
    callback: Callable[[List[OptionQuote]], object]
    contract_ids: Optional[Set[str]]


class TradierOptionsProvider:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        access_token: str,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token
        self._logger = logger

    async def fetch_quotes(self, symbol: str, expiration: str) -> List[OptionQuote]:
        raw_options = await self.fetch_chain(symbol, expiration)
        now = datetime.now(timezone.utc)
        quotes: List[OptionQuote] = []
        for raw in raw_options:
            quote = self._parse_option(raw, symbol, expiration, now)
            if quote is not None:
                quotes.append(quote)
        return quotes

    async def fetch_chain(self, symbol: str, expiration: str) -> List[dict]:
        url = f"{self._base_url}/markets/options/chains?symbol={symbol}&expiration={expiration}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        async with self._session.get(url, headers=headers) as response:
            if response.status == 429:
                retry_after = float(response.headers.get("Retry-After", 1))
                raise RateLimitError(retry_after)
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(f"Tradier options chain error {response.status}: {body}")
            payload = await response.json()

        options = payload.get("options", {}).get("option", [])
        if isinstance(options, dict):
            return [options]
        return options

    def _parse_option(
        self,
        raw: dict,
        symbol: str,
        expiration: str,
        now: datetime,
    ) -> Optional[OptionQuote]:
        option_type = raw.get("option_type")
        if option_type not in ("call", "put"):
            return None
        strike = _to_float(raw.get("strike"))
        if strike is None:
            return None
        contract = OptionContract(
            symbol=symbol,
            option_type=option_type,
            strike=strike,
            expiration=expiration,
        )
        return OptionQuote(
            contract=contract,
            bid=_to_float(raw.get("bid")),
            ask=_to_float(raw.get("ask")),
            last=_to_float(raw.get("last")),
            volume=_to_int(raw.get("volume")),
            open_interest=_to_int(raw.get("open_interest")),
            updated_at=now,
        )


class OptionQuoteService:
    def __init__(
        self,
        provider: OptionsProvider,
        symbol: str,
        expiration: str,
        poll_interval: float = 1.0,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._provider = provider
        self._symbol = symbol
        self._expiration = expiration
        self._poll_interval = poll_interval
        self._logger = logger
        self._quotes: Dict[str, OptionQuote] = {}
        self._listeners: Dict[int, _Listener] = {}
        self._listener_id = 0
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    def set_expiration(self, expiration: str) -> None:
        if expiration != self._expiration:
            self._quotes.clear()
        self._expiration = expiration

    def set_poll_interval(self, seconds: float) -> None:
        self._poll_interval = seconds

    def register_listener(
        self,
        callback: Callable[[List[OptionQuote]], object],
        contract_ids: Optional[Iterable[str]] = None,
    ) -> int:
        self._listener_id += 1
        self._listeners[self._listener_id] = _Listener(
            callback=callback,
            contract_ids=set(contract_ids) if contract_ids else None,
        )
        return self._listener_id

    def register_queue(
        self,
        contract_ids: Optional[Iterable[str]] = None,
        maxsize: int = 0,
    ) -> Tuple[int, asyncio.Queue]:
        queue: asyncio.Queue[List[OptionQuote]] = asyncio.Queue(maxsize=maxsize)

        def _enqueue(updates: List[OptionQuote]) -> None:
            if maxsize > 0 and queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(list(updates))
            except asyncio.QueueFull:
                pass

        listener_id = self.register_listener(_enqueue, contract_ids=contract_ids)
        return listener_id, queue

    def update_listener_contracts(self, listener_id: int, contract_ids: Iterable[str]) -> None:
        listener = self._listeners.get(listener_id)
        if listener is not None:
            listener.contract_ids = set(contract_ids)

    def remove_listener(self, listener_id: int) -> None:
        self._listeners.pop(listener_id, None)

    def get_quote(self, contract_key: str) -> Optional[OptionQuote]:
        return self._quotes.get(contract_key)

    def get_snapshot(self) -> Dict[str, OptionQuote]:
        return dict(self._quotes)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        else:
            self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name=f"OptionQuotes-{self._symbol}")

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

    async def _run(self) -> None:
        while self._stop_event is not None and not self._stop_event.is_set():
            try:
                expiration = self._expiration
                quotes = await self._provider.fetch_quotes(self._symbol, expiration)
                updates = self._apply_updates(quotes)
                if updates:
                    self._notify_listeners(updates)
            except RateLimitError as exc:
                self._log(f"[OPTIONS] Rate limited; sleeping {exc.retry_after}s")
                await asyncio.sleep(exc.retry_after)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log(f"[OPTIONS] Quote poll error: {exc}")
            await asyncio.sleep(self._poll_interval)

    def _apply_updates(self, quotes: Iterable[OptionQuote]) -> List[OptionQuote]:
        updates: List[OptionQuote] = []
        for quote in quotes:
            key = quote.contract.key
            existing = self._quotes.get(key)
            if existing is None or _quote_changed(existing, quote):
                self._quotes[key] = quote
                updates.append(quote)
        return updates

    def _notify_listeners(self, updates: List[OptionQuote]) -> None:
        for listener in list(self._listeners.values()):
            if listener.contract_ids is None:
                self._dispatch(listener.callback, updates)
                continue
            filtered = [q for q in updates if q.contract.key in listener.contract_ids]
            if filtered:
                self._dispatch(listener.callback, filtered)

    def _dispatch(self, callback: Callable[[List[OptionQuote]], object], updates: List[OptionQuote]) -> None:
        try:
            result = callback(updates)
            if inspect.isawaitable(result):
                asyncio.create_task(result)
        except Exception as exc:
            self._log(f"[OPTIONS] Listener error: {exc}")

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)


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


def _quote_changed(existing: OptionQuote, incoming: OptionQuote) -> bool:
    return any(
        (
            existing.bid != incoming.bid,
            existing.ask != incoming.ask,
            existing.last != incoming.last,
            existing.volume != incoming.volume,
            existing.open_interest != incoming.open_interest,
        )
    )
