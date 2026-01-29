from __future__ import annotations

import asyncio
import importlib
import inspect
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from options.order_manager import OptionsOrderManager, Position, PositionActionResult
from options.position_watcher import PositionUpdate, PositionWatcher
from options.execution_tradier import OrderSubmitResult
from options.selection import DEFAULT_PRICE_RANGES, SelectionRequest
from paths import get_ema_path
from runtime.market_bus import CandleCloseEvent, MarketEventBus
from shared_state import safe_read_json
from strategies.options.types import PositionAction, StrategyContext, StrategySignal


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
        position_watcher: Optional[PositionWatcher] = None,
        on_position_opened: Optional[Callable[[Position, Optional[OrderSubmitResult], str, Optional[str]], object]] = None,
        on_position_closed: Optional[Callable[[Position, Optional[OrderSubmitResult], str, Optional[str]], object]] = None,
        on_position_added: Optional[Callable[[Position, Optional[OrderSubmitResult], str, Optional[str]], object]] = None,
        on_position_trimmed: Optional[Callable[[Position, Optional[OrderSubmitResult], str, Optional[str]], object]] = None,
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
        self._position_watcher = position_watcher
        self._on_position_opened = on_position_opened
        self._on_position_closed = on_position_closed
        self._on_position_added = on_position_added
        self._on_position_trimmed = on_position_trimmed
        self._logger = logger
        self._listener_id: Optional[int] = None
        self._position_listener_id: Optional[int] = None
        self._positions: Dict[str, StrategyPosition] = {}
        self._ema_cache = EmaSnapshotCache(logger=logger)
        self._lock = asyncio.Lock()

    def start(self) -> None:
        if self._listener_id is not None:
            return
        self._listener_id = self._bus.register_listener(self._handle_event)
        if self._position_watcher and self._position_listener_id is None:
            self._position_listener_id = self._position_watcher.register_listener(
                self._handle_position_updates
            )

    def stop(self) -> None:
        if self._listener_id is None:
            return
        self._bus.remove_listener(self._listener_id)
        self._listener_id = None
        if self._position_watcher and self._position_listener_id is not None:
            self._position_watcher.remove_listener(self._position_listener_id)
            self._position_listener_id = None

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

    async def _handle_position_updates(self, updates: List[PositionUpdate]) -> None:
        if not updates:
            return
        updates_by_tag: Dict[Optional[str], List[PositionUpdate]] = {}
        for update in updates:
            updates_by_tag.setdefault(update.strategy_tag, []).append(update)
        actions: List[PositionAction] = []
        async with self._lock:
            for strategy in self._strategies:
                handler = getattr(strategy, "on_position_update", None)
                if handler is None:
                    continue
                name = getattr(strategy, "name", strategy.__class__.__name__)
                scoped = updates_by_tag.get(name, [])
                if not scoped:
                    continue
                actions.extend(await self._resolve_position_actions(handler, scoped, name))
        if actions:
            await self._apply_position_actions(actions)

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
            close_result = await self._order_manager.close_position(active.position_id)
            closed_position = self._order_manager.get_position(active.position_id)
            if closed_position:
                self._dispatch_hook(
                    self._on_position_closed,
                    closed_position,
                    close_result.order_result if close_result else None,
                    f"flip to {direction}: {signal.reason}",
                    context.timeframe,
                )
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
        opened_position = self._order_manager.get_position(result.position_id)
        if opened_position:
            self._dispatch_hook(
                self._on_position_opened,
                opened_position,
                result.order_result,
                signal.reason,
                context.timeframe,
            )
        self._log(f"[STRATEGY] {name} opened {direction} position {result.position_id} ({signal.reason})")

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)

    def _forget_position(self, position_id: str) -> None:
        for name, position in list(self._positions.items()):
            if position.position_id == position_id:
                self._positions.pop(name, None)
                return

    def _dispatch_hook(
        self,
        hook: Optional[Callable[[Position, Optional[OrderSubmitResult], str, Optional[str]], object]],
        position: Position,
        order_result: Optional[OrderSubmitResult],
        reason: str,
        timeframe: Optional[str] = None,
    ) -> None:
        if hook is None:
            return
        try:
            if _hook_accepts_timeframe(hook):
                result = hook(position, order_result, reason, timeframe)
            else:
                result = hook(position, order_result, reason)
            if inspect.isawaitable(result):
                asyncio.create_task(self._run_hook(result))
        except Exception as exc:
            self._log(f"[STRATEGY] Hook error: {exc}")

    async def _resolve_position_actions(
        self,
        handler: Callable[[List[PositionUpdate]], object],
        updates: List[PositionUpdate],
        name: str,
    ) -> List[PositionAction]:
        try:
            result = handler(updates)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            self._log(f"[STRATEGY] {name} position update error: {exc}")
            return []
        return _normalize_position_actions(result)

    async def _run_hook(self, coro) -> None:
        try:
            await coro
        except Exception as exc:
            self._log(f"[STRATEGY] Hook async error: {exc}")

    async def _apply_position_actions(self, actions: List[PositionAction]) -> None:
        for action in actions:
            if action.action == "close":
                result = await self._order_manager.close_position(action.position_id)
                position = self._order_manager.get_position(action.position_id)
                if position:
                    self._dispatch_hook(
                        self._on_position_closed,
                        position,
                        result.order_result if result else None,
                        action.reason or "close",
                        action.timeframe,
                    )
                    if position.status == "closed" or position.quantity_open <= 0:
                        self._forget_position(action.position_id)
                else:
                    self._forget_position(action.position_id)
                continue
            if action.action == "trim":
                if action.quantity is None or action.quantity <= 0:
                    self._log("[STRATEGY] trim action missing quantity")
                    continue
                result = await self._order_manager.trim_position(
                    action.position_id,
                    quantity=action.quantity,
                )
                position = self._order_manager.get_position(action.position_id)
                if position:
                    self._dispatch_hook(
                        self._on_position_trimmed,
                        position,
                        result.order_result if result else None,
                        action.reason or "trim",
                        action.timeframe,
                    )
                continue
            if action.action == "add":
                if action.quantity is None or action.quantity <= 0:
                    self._log("[STRATEGY] add action missing quantity")
                    continue
                result = await self._order_manager.add_to_position(
                    action.position_id,
                    quantity=action.quantity,
                )
                position = self._order_manager.get_position(action.position_id)
                if position:
                    self._dispatch_hook(
                        self._on_position_added,
                        position,
                        result.order_result if result else None,
                        action.reason or "add",
                        action.timeframe,
                    )
                continue
            self._log(f"[STRATEGY] Unknown position action: {action.action}")

    async def add_to_position(
        self,
        position_id: str,
        quantity: int,
        *,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        reason: str = "add",
        timeframe: Optional[str] = None,
    ) -> Optional[PositionActionResult]:
        result = await self._order_manager.add_to_position(
            position_id,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        position = self._order_manager.get_position(position_id)
        if position:
            self._dispatch_hook(
                self._on_position_added,
                position,
                result.order_result,
                reason,
                timeframe,
            )
        return result

    async def trim_position(
        self,
        position_id: str,
        quantity: int,
        *,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        reason: str = "trim",
        timeframe: Optional[str] = None,
    ) -> Optional[PositionActionResult]:
        result = await self._order_manager.trim_position(
            position_id,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        position = self._order_manager.get_position(position_id)
        if position:
            self._dispatch_hook(
                self._on_position_trimmed,
                position,
                result.order_result,
                reason,
                timeframe,
            )
        return result


def _call_strategy(strategy: object, context: StrategyContext) -> Optional[StrategySignal]:
    handler = getattr(strategy, "on_candle_close", None)
    if handler is None:
        return None
    return handler(context)


def _hook_accepts_timeframe(hook: Callable) -> bool:
    try:
        signature = inspect.signature(hook)
    except (TypeError, ValueError):
        return True
    params = list(signature.parameters.values())
    if any(param.kind == inspect.Parameter.VAR_POSITIONAL for param in params):
        return True
    positional = [
        param
        for param in params
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 4


def _normalize_position_actions(result: object) -> List[PositionAction]:
    if result is None:
        return []
    if isinstance(result, PositionAction):
        return [result]
    if isinstance(result, (list, tuple)):
        return [item for item in result if isinstance(item, PositionAction)]
    return []


def discover_strategies(root: Optional[Path] = None) -> List[object]:
    # Strategy modules should expose build_strategy() returning an object with
    # a .name and on_candle_close(context) -> StrategySignal|None.
    base = root or Path(__file__).resolve().parents[1] / "strategies" / "options"
    if not base.exists():
        return []
    strategies: List[object] = []
    for path in sorted(base.glob("*.py")):
        if path.name.startswith("_") or path.name in ("types.py", "exit_rules.py"):
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
            built = build()
        except Exception:
            continue
        if isinstance(built, (list, tuple)):
            strategies.extend([item for item in built if item is not None])
        elif built is not None:
            strategies.append(built)
    return strategies
