from __future__ import annotations

import asyncio
import importlib
import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

import shared_state
from options.research_path_ledger import ResearchPathEvent, record_research_path_event
from options.research_signal_ledger import ResearchSignalEvent, record_research_signal
from options.selection import DEFAULT_PRICE_RANGES, SelectionRequest, select_contract
from options.quote_service import OptionQuote, OptionQuoteService
from paths import CURRENT_OBJECTS_PATH, get_ema_path
from runtime.market_bus import CandleCloseEvent, MarketEventBus
from shared_state import price_lock, safe_read_json
from strategies_research.types import ResearchContext, ResearchSignal
from utils.json_utils import read_config
from utils.timezone import NY_TZ


class EmaHistoryCache:
    def __init__(self) -> None:
        self._cache: Dict[Path, tuple[float, List[dict]]] = {}

    def get_last_two(self, timeframe: str) -> List[dict]:
        path = Path(get_ema_path(timeframe))
        if not path.exists():
            return []
        mtime = path.stat().st_mtime
        cached = self._cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        data = safe_read_json(path, default=[])
        if not isinstance(data, list) or not data:
            history: List[dict] = []
        else:
            history = data[-2:] if len(data) >= 2 else [data[-1]]
        self._cache[path] = (mtime, history)
        return history


class ObjectsCache:
    def __init__(self) -> None:
        self._cache: tuple[float, list, list] = (0.0, [], [])

    def get_current(self) -> tuple[list, list]:
        path = Path(CURRENT_OBJECTS_PATH)
        if not path.exists():
            return ([], [])
        mtime = path.stat().st_mtime
        cached_mtime, zones, levels = self._cache
        if cached_mtime == mtime:
            return (zones, levels)
        try:
            from objects import get_objects
        except Exception:
            return (zones, levels)
        zones, levels = get_objects()
        self._cache = (mtime, zones, levels)
        return (zones, levels)


@dataclass(frozen=True)
class ActiveSignal:
    signal_id: str
    strategy_tag: str
    timeframe: str
    symbol: str
    contract_key: str
    option_type: str
    strike: float
    expiration: str
    variant: Optional[str]


@dataclass
class ResearchSignalRunner:
    bus: MarketEventBus
    quote_service: OptionQuoteService
    strategies: Iterable[object]
    expiration: str
    selector_name: str = "price-range-otm"
    max_otm: Optional[float] = None
    price_ranges=DEFAULT_PRICE_RANGES
    timeframes: Optional[Sequence[str]] = None
    touch_poll_secs: float = 1.0
    touch_tolerance: float = 0.02
    logger: Optional[Callable[[str], None]] = None

    def __post_init__(self) -> None:
        self._strategies = list(self.strategies)
        self._listener_id: Optional[int] = None
        self._ema_cache = EmaHistoryCache()
        self._objects_cache = ObjectsCache()
        self._lock = asyncio.Lock()
        self._allowed_timeframes = set(self.timeframes or [])
        self._active_signals: Dict[str, ActiveSignal] = {}
        self._touch_task: Optional[asyncio.Task] = None
        self._touch_stop = asyncio.Event()
        self._touch_seen: Dict[str, Dict[str, str]] = {}
        self._tag_include_timeframe = _read_tag_include_timeframe()

    def start(self) -> None:
        if self._listener_id is not None:
            return
        self._listener_id = self.bus.register_listener(self._handle_event)
        if self.touch_poll_secs and self.touch_poll_secs > 0:
            if not self._touch_task or self._touch_task.done():
                self._touch_stop.clear()
                self._touch_task = asyncio.create_task(
                    self._poll_touches(),
                    name="ResearchSignalTouches",
                )

    def stop(self) -> None:
        if self._listener_id is None:
            return
        self.bus.remove_listener(self._listener_id)
        self._listener_id = None
        if self._touch_task and not self._touch_task.done():
            self._touch_stop.set()
            self._touch_task.cancel()
        self._touch_task = None

    async def _handle_event(self, event: CandleCloseEvent) -> None:
        if self._allowed_timeframes and event.timeframe not in self._allowed_timeframes:
            return
        async with self._lock:
            ema_history = self._ema_cache.get_last_two(event.timeframe)
            context = ResearchContext(
                symbol=event.symbol,
                timeframe=event.timeframe,
                candle=event.candle,
                ema_history=ema_history,
                timestamp=event.closed_at,
            )
            snapshot = self.quote_service.get_snapshot()
            if not snapshot:
                return
            for strategy in self._strategies:
                signals = await _call_strategy(strategy, context, logger=self._log)
                if not signals:
                    continue
                for signal in signals:
                    await self._record_signal(strategy, signal, context, snapshot)
            await self._record_candle_close_paths(event)
            if event.source == "eod":
                self._clear_timeframe_signals(event.timeframe)

    async def _record_signal(
        self,
        strategy: object,
        signal: ResearchSignal,
        context: ResearchContext,
        snapshot: Dict[str, OptionQuote],
    ) -> None:
        direction = signal.direction
        if direction not in ("call", "put"):
            return
        underlying = context.candle.get("close")
        if underlying is None:
            return
        name = getattr(strategy, "name", strategy.__class__.__name__)
        strategy_tag = _format_strategy_tag(name, context.timeframe, self._tag_include_timeframe)
        request = SelectionRequest(
            symbol=context.symbol,
            option_type=direction,
            expiration=self.expiration,
            underlying_price=float(underlying),
            max_otm=self.max_otm,
            price_ranges=self.price_ranges,
        )
        selection = select_contract(snapshot.values(), request, selector_name=self.selector_name)
        if not selection:
            self._log(f"[RESEARCH] {name} no contract for {direction} on {context.timeframe}")
            return
        quote = selection.quote
        entry_mark = _entry_mark(quote)
        if entry_mark is None:
            self._log(f"[RESEARCH] {name} no entry mark for {quote.contract.key}")
            return
        ts = _timestamp_iso(context.timestamp)
        signal_id = _build_signal_id(name, context.timeframe, ts, quote.contract.key, signal.variant)
        event = ResearchSignalEvent(
            ts=ts,
            event="signal",
            signal_id=signal_id,
            strategy_tag=strategy_tag,
            timeframe=context.timeframe,
            symbol=quote.contract.symbol,
            option_type=quote.contract.option_type,
            strike=quote.contract.strike,
            expiration=quote.contract.expiration,
            contract_key=quote.contract.key,
            underlying_price=float(underlying),
            entry_mark=float(entry_mark),
            bid=_to_float(quote.bid),
            ask=_to_float(quote.ask),
            last=_to_float(quote.last),
            reason=signal.reason,
            variant=signal.variant,
        )
        record_research_signal(event, logger=self._log)
        self._active_signals[signal_id] = ActiveSignal(
            signal_id=signal_id,
            strategy_tag=strategy_tag,
            timeframe=context.timeframe,
            symbol=quote.contract.symbol,
            contract_key=quote.contract.key,
            option_type=quote.contract.option_type,
            strike=quote.contract.strike,
            expiration=quote.contract.expiration,
            variant=signal.variant,
        )
        self._log(
            f"[RESEARCH] {strategy_tag} {direction} {quote.contract.key} @ {entry_mark:.2f} "
            f"({context.timeframe}: {signal.reason})"
        )

    async def _record_candle_close_paths(self, event: CandleCloseEvent) -> None:
        if not self._active_signals:
            return
        candle_close = event.candle.get("close")
        if candle_close is None:
            return
        bucket = _bucket_from_candle(event)
        ts = _timestamp_iso(event.closed_at)
        for signal in list(self._active_signals.values()):
            if signal.timeframe != event.timeframe:
                continue
            if not _should_record(self._touch_seen, signal.signal_id, "candle_close", bucket):
                continue
            quote = self.quote_service.get_quote(signal.contract_key)
            if quote is None:
                continue
            mark = _entry_mark(quote)
            if mark is None:
                continue
            path_event = ResearchPathEvent(
                ts=ts,
                event="candle_close",
                event_key="candle_close",
                signal_id=signal.signal_id,
                strategy_tag=signal.strategy_tag,
                timeframe=signal.timeframe,
                symbol=signal.symbol,
                option_type=signal.option_type,
                strike=signal.strike,
                expiration=signal.expiration,
                contract_key=signal.contract_key,
                underlying_price=float(candle_close),
                mark=float(mark),
                bid=_to_float(quote.bid),
                ask=_to_float(quote.ask),
                last=_to_float(quote.last),
                reason=f"close:{event.source}",
                variant=signal.variant,
            )
            record_research_path_event(path_event, logger=self._log)

    async def _poll_touches(self) -> None:
        while not self._touch_stop.is_set():
            await asyncio.sleep(max(self.touch_poll_secs, 0.2))
            if not self._active_signals:
                continue
            async with price_lock:
                latest_price = shared_state.latest_price
            if latest_price is None:
                continue
            if self.touch_tolerance is None or self.touch_tolerance <= 0:
                continue
            now = datetime.now(NY_TZ)
            zones, levels = self._objects_cache.get_current()
            async with self._lock:
                self._process_touches(latest_price, now, zones, levels)

    def _process_touches(
        self,
        latest_price: float,
        now: datetime,
        zones: list,
        levels: list,
    ) -> None:
        for signal in list(self._active_signals.values()):
            ema_history = self._ema_cache.get_last_two(signal.timeframe)
            if not ema_history:
                continue
            latest = ema_history[-1]
            ema_levels = _extract_ema_levels(latest)
            if not ema_levels:
                continue
            bucket = _bucket_id(now, signal.timeframe)
            quote = self.quote_service.get_quote(signal.contract_key)
            if quote is None:
                continue
            mark = _entry_mark(quote)
            if mark is None:
                continue
            for period, value in ema_levels.items():
                if abs(latest_price - value) > self.touch_tolerance:
                    continue
                event_key = f"ema:{period}"
                if not _should_record(self._touch_seen, signal.signal_id, event_key, bucket):
                    continue
                path_event = ResearchPathEvent(
                    ts=_timestamp_iso(now),
                    event="touch",
                    event_key=event_key,
                    signal_id=signal.signal_id,
                    strategy_tag=signal.strategy_tag,
                    timeframe=signal.timeframe,
                    symbol=signal.symbol,
                    option_type=signal.option_type,
                    strike=signal.strike,
                    expiration=signal.expiration,
                    contract_key=signal.contract_key,
                    underlying_price=float(latest_price),
                    mark=float(mark),
                    bid=_to_float(quote.bid),
                    ask=_to_float(quote.ask),
                    last=_to_float(quote.last),
                    reason="ema_touch",
                    variant=signal.variant,
                )
                record_research_path_event(path_event, logger=self._log)
            for level in levels or []:
                y = _to_float(level.get("y"))
                if y is None:
                    continue
                if abs(latest_price - y) > self.touch_tolerance:
                    continue
                event_key = f"level:{_format_price_key(y)}"
                if not _should_record(self._touch_seen, signal.signal_id, event_key, bucket):
                    continue
                reason = f"level_touch:{level.get('type')}:{level.get('id')}"
                path_event = ResearchPathEvent(
                    ts=_timestamp_iso(now),
                    event="touch",
                    event_key=event_key,
                    signal_id=signal.signal_id,
                    strategy_tag=signal.strategy_tag,
                    timeframe=signal.timeframe,
                    symbol=signal.symbol,
                    option_type=signal.option_type,
                    strike=signal.strike,
                    expiration=signal.expiration,
                    contract_key=signal.contract_key,
                    underlying_price=float(latest_price),
                    mark=float(mark),
                    bid=_to_float(quote.bid),
                    ask=_to_float(quote.ask),
                    last=_to_float(quote.last),
                    reason=reason,
                    variant=signal.variant,
                )
                record_research_path_event(path_event, logger=self._log)
            for zone in zones or []:
                top = _to_float(zone.get("top"))
                bottom = _to_float(zone.get("bottom"))
                if top is None or bottom is None:
                    continue
                low, high = (bottom, top) if bottom <= top else (top, bottom)
                if latest_price < low - self.touch_tolerance:
                    continue
                if latest_price > high + self.touch_tolerance:
                    continue
                event_key = f"zone:{_format_price_key(low)}-{_format_price_key(high)}"
                if not _should_record(self._touch_seen, signal.signal_id, event_key, bucket):
                    continue
                reason = f"zone_touch:{zone.get('type')}:{zone.get('id')}"
                path_event = ResearchPathEvent(
                    ts=_timestamp_iso(now),
                    event="touch",
                    event_key=event_key,
                    signal_id=signal.signal_id,
                    strategy_tag=signal.strategy_tag,
                    timeframe=signal.timeframe,
                    symbol=signal.symbol,
                    option_type=signal.option_type,
                    strike=signal.strike,
                    expiration=signal.expiration,
                    contract_key=signal.contract_key,
                    underlying_price=float(latest_price),
                    mark=float(mark),
                    bid=_to_float(quote.bid),
                    ask=_to_float(quote.ask),
                    last=_to_float(quote.last),
                    reason=reason,
                    variant=signal.variant,
                )
                record_research_path_event(path_event, logger=self._log)

    def _clear_timeframe_signals(self, timeframe: str) -> None:
        to_remove = [key for key, sig in self._active_signals.items() if sig.timeframe == timeframe]
        for key in to_remove:
            self._active_signals.pop(key, None)
            self._touch_seen.pop(key, None)

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)


async def _call_strategy(
    strategy: object,
    context: ResearchContext,
    *,
    logger: Optional[Callable[[str], None]] = None,
) -> List[ResearchSignal]:
    handler = getattr(strategy, "on_candle_close", None)
    if handler is None:
        return []
    try:
        result = handler(context)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        if logger:
            name = getattr(strategy, "name", strategy.__class__.__name__)
            logger(f"[RESEARCH] {name} signal error: {exc}")
        return []
    return _normalize_signals(result)


def _normalize_signals(result: object) -> List[ResearchSignal]:
    if result is None:
        return []
    if isinstance(result, ResearchSignal):
        return [result]
    if isinstance(result, (list, tuple)):
        return [item for item in result if isinstance(item, ResearchSignal)]
    return []


def _read_tag_include_timeframe() -> bool:
    raw = read_config("STRATEGY_TAG_INCLUDE_TIMEFRAME")
    return True if raw is None else bool(raw)


def _format_strategy_tag(name: str, timeframe: Optional[str], include_timeframe: bool) -> str:
    if not include_timeframe or not timeframe:
        return name
    tf = str(timeframe).strip().lower()
    lowered = str(name).lower()
    if lowered.endswith(f"-{tf}"):
        return name
    return f"{name}-{tf}"


def _entry_mark(quote: OptionQuote) -> Optional[float]:
    for value in (quote.ask, quote.mid, quote.last, quote.bid):
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _extract_ema_levels(snapshot: dict) -> Dict[int, float]:
    levels: Dict[int, float] = {}
    if not isinstance(snapshot, dict):
        return levels
    for key, value in snapshot.items():
        if key == "x":
            continue
        try:
            period = int(str(key))
            levels[period] = float(value)
        except (TypeError, ValueError):
            continue
    return levels


def _build_signal_id(
    name: str,
    timeframe: str,
    ts: str,
    contract_key: str,
    variant: Optional[str],
) -> str:
    variant_part = f"-{variant}" if variant else ""
    return f"sig-{name}-{timeframe}-{ts}-{contract_key}{variant_part}"


def _to_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_price_key(value: float, places: int = 2) -> str:
    return f"{value:.{places}f}"


def _timestamp_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _bucket_id(value: datetime, timeframe: str) -> str:
    minutes = _parse_timeframe_minutes(timeframe)
    if minutes <= 0:
        return value.replace(second=0, microsecond=0).isoformat()
    bucket_minute = (value.minute // minutes) * minutes
    return value.replace(minute=bucket_minute, second=0, microsecond=0).isoformat()


def _bucket_from_candle(event: CandleCloseEvent) -> str:
    ts = event.candle.get("timestamp")
    if ts:
        return str(ts)
    return _timestamp_iso(event.closed_at)


def _parse_timeframe_minutes(timeframe: str) -> int:
    raw = str(timeframe).strip().upper().replace("M", "")
    try:
        return int(raw)
    except ValueError:
        return 0


def _should_record(
    seen: Dict[str, Dict[str, str]],
    signal_id: str,
    event_key: str,
    bucket: str,
) -> bool:
    per_signal = seen.setdefault(signal_id, {})
    last_bucket = per_signal.get(event_key)
    if last_bucket == bucket:
        return False
    per_signal[event_key] = bucket
    return True


def discover_research_signals(root: Optional[Path] = None) -> List[object]:
    base = root or Path(__file__).resolve().parents[1] / "strategies_research" / "signals"
    if not base.exists():
        return []
    signals: List[object] = []
    for path in sorted(base.glob("*.py")):
        if path.name.startswith("_") or path.name in ("types.py",):
            continue
        module_name = f"strategies_research.signals.{path.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        build = getattr(module, "build_signal", None) or getattr(module, "build_strategy", None)
        if not callable(build):
            continue
        try:
            signals.append(build())
        except Exception:
            continue
    return signals
