from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from options.order_manager import OptionsOrderManager
from options.selection import DEFAULT_PRICE_RANGES, SelectionRequest
from paths import get_ema_path
from runtime.market_bus import CandleCloseEvent, MarketEventBus
from shared_state import safe_read_json
from strategies.options.types import StrategyContext, StrategySignal


@dataclass
class StrategyPosition:
    position_id: str
    direction: str


class EmaSnapshotCache:
    def __init__(self, logger: Optional[Callable[[str], None]] = None) -> None:
        self._logger = logger
        self._cache: Dict[Path, tuple[float, Optional[dict]]] = {}

    def get_latest(self, timeframe: str) -> Optional[dict]:
        path = Path(get_ema_path(timeframe))
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        cached = self._cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        data = safe_read_json(path, default=[])
        latest = data[-1] if isinstance(data, list) and data else None
        self._cache[path] = (mtime, latest)
        return latest


class OptionsStrategyRunner:
    def __init__(
        self,
        bus: MarketEventBus,
        order_manager: OptionsOrderManager,
        strategies: Iterable[object],
        *,
        expiration: str,
        selector_name: str = "price-range-otm",
        max_otm: Optional[float] = None,
        price_ranges=DEFAULT_PRICE_RANGES,
        order_quantity: int = 1,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._bus = bus
        self._order_manager = order_manager
        self._strategies = list(strategies)
        self._expiration = expiration
        self._selector_name = selector_name
        self._max_otm = max_otm
        self._price_ranges = price_ranges
        self._order_quantity = order_quantity
        self._logger = logger
        self._listener_id: Optional[int] = None
        self._positions: Dict[str, StrategyPosition] = {}
        self._ema_cache = EmaSnapshotCache(logger=logger)
        self._lock = asyncio.Lock()

    def start(self) -> None:
        if self._listener_id is not None:
            return
        self._listener_id = self._bus.register_listener(self._handle_event)

    def stop(self) -> None:
        if self._listener_id is None:
            return
        self._bus.remove_listener(self._listener_id)
        self._listener_id = None

    async def _handle_event(self, event: CandleCloseEvent) -> None:
        async with self._lock:
            ema_snapshot = self._ema_cache.get_latest(event.timeframe)
            context = StrategyContext(
                symbol=event.symbol,
                timeframe=event.timeframe,
                candle=event.candle,
                ema=ema_snapshot,
                timestamp=event.closed_at,
            )
            for strategy in self._strategies:
                signal = _call_strategy(strategy, context)
                if signal is None:
                    continue
                await self._handle_signal(strategy, signal, context)

    async def _handle_signal(
        self,
        strategy: object,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> None:
        direction = signal.direction
        if direction not in ("call", "put"):
            return

        name = getattr(strategy, "name", strategy.__class__.__name__)
        active = self._positions.get(name)
        if active and active.direction == direction:
            return

        if active:
            await self._order_manager.close_position(active.position_id)
            self._positions.pop(name, None)

        underlying = context.candle.get("close")
        if underlying is None:
            return

        request = SelectionRequest(
            symbol=context.symbol,
            option_type=direction,
            expiration=self._expiration,
            underlying_price=float(underlying),
            max_otm=self._max_otm,
            price_ranges=self._price_ranges,
        )
        try:
            result = await self._order_manager.open_position(
                request,
                selector_name=self._selector_name,
                quantity=self._order_quantity,
                strategy_tag=name,
            )
        except Exception as exc:
            self._log(f"[STRATEGY] {name} failed to open position: {exc}")
            return
        self._positions[name] = StrategyPosition(
            position_id=result.position_id,
            direction=direction,
        )
        self._log(f"[STRATEGY] {name} opened {direction} position {result.position_id} ({signal.reason})")

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)


def _call_strategy(strategy: object, context: StrategyContext) -> Optional[StrategySignal]:
    handler = getattr(strategy, "on_candle_close", None)
    if handler is None:
        return None
    return handler(context)


def discover_strategies(root: Optional[Path] = None) -> List[object]:
    # Strategy modules should expose build_strategy() returning an object with
    # a .name and on_candle_close(context) -> StrategySignal|None.
    base = root or Path(__file__).resolve().parents[1] / "strategies" / "options"
    if not base.exists():
        return []
    strategies: List[object] = []
    for path in sorted(base.glob("*.py")):
        if path.name.startswith("_") or path.name == "types.py":
            continue
        module_name = f"strategies.options.{path.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        build = getattr(module, "build_strategy", None)
        if not callable(build):
            continue
        try:
            strategies.append(build())
        except Exception:
            continue
    return strategies
