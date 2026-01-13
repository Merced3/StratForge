from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from .quote_service import OptionContract, OptionQuote, OptionsProvider


class MockProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class SyntheticQuoteConfig:
    underlying_price: float = 500.0
    strike_step: float = 1.0
    strikes_each_side: int = 50
    price_jitter: float = 0.25
    spread_pct: float = 0.02
    min_spread: float = 0.01
    time_value_atm: float = 0.5
    time_value_decay: float = 0.02
    min_time_value: float = 0.05
    seed: Optional[int] = None


class SyntheticOptionsProvider(OptionsProvider):
    def __init__(
        self,
        symbol: str,
        expiration: str,
        config: SyntheticQuoteConfig,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._symbol = symbol
        self._expiration = expiration
        self._config = config
        self._price = config.underlying_price
        self._rng = random.Random(config.seed)
        self._logger = logger

    async def fetch_quotes(self, symbol: str, expiration: str) -> List[OptionQuote]:
        self._price += self._rng.uniform(-self._config.price_jitter, self._config.price_jitter)
        base = _round_to_step(self._price, self._config.strike_step)
        strikes = [
            base + (offset * self._config.strike_step)
            for offset in range(-self._config.strikes_each_side, self._config.strikes_each_side + 1)
        ]
        now = datetime.now(timezone.utc)
        quotes: List[OptionQuote] = []
        for strike in strikes:
            quotes.append(
                _build_quote(
                    symbol,
                    expiration,
                    "call",
                    strike,
                    self._price,
                    now,
                    self._config,
                    self._rng,
                )
            )
            quotes.append(
                _build_quote(
                    symbol,
                    expiration,
                    "put",
                    strike,
                    self._price,
                    now,
                    self._config,
                    self._rng,
                )
            )
        return quotes


class ReplayOptionsProvider(OptionsProvider):
    def __init__(
        self,
        fixture_path: Path,
        symbol: str,
        expiration: str,
        loop: bool = True,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._fixture_path = fixture_path
        self._symbol = symbol
        self._expiration = expiration
        self._loop = loop
        self._logger = logger
        self._snapshots = _load_fixture(fixture_path, symbol, expiration)
        self._index = 0
        if not self._snapshots:
            raise MockProviderError(f"fixture has no snapshots: {fixture_path}")

    async def fetch_quotes(self, symbol: str, expiration: str) -> List[OptionQuote]:
        snapshot = self._snapshots[self._index]
        self._index += 1
        if self._index >= len(self._snapshots):
            if self._loop:
                self._index = 0
            else:
                self._index = len(self._snapshots) - 1
        return snapshot


class RecordingOptionsProvider(OptionsProvider):
    def __init__(
        self,
        provider: OptionsProvider,
        output_path: Path,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._provider = provider
        self._output_path = output_path
        self._logger = logger
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

    async def fetch_quotes(self, symbol: str, expiration: str) -> List[OptionQuote]:
        quotes = await self._provider.fetch_quotes(symbol, expiration)
        _append_snapshot(self._output_path, quotes)
        return quotes


def _round_to_step(value: float, step: float) -> float:
    return round(value / step) * step


def _build_quote(
    symbol: str,
    expiration: str,
    option_type: str,
    strike: float,
    underlying_price: float,
    now: datetime,
    config: SyntheticQuoteConfig,
    rng: random.Random,
) -> OptionQuote:
    if option_type == "call":
        intrinsic = max(0.0, underlying_price - strike)
    else:
        intrinsic = max(0.0, strike - underlying_price)

    distance = abs(strike - underlying_price)
    time_value = max(
        config.min_time_value,
        config.time_value_atm - (distance * config.time_value_decay),
    )
    mid = intrinsic + time_value
    spread = max(config.min_spread, mid * config.spread_pct)
    bid = max(0.0, mid - (spread / 2.0))
    ask = bid + spread
    last = max(0.0, mid + rng.uniform(-spread / 4.0, spread / 4.0))

    contract = OptionContract(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
    )
    return OptionQuote(
        contract=contract,
        bid=_safe_float(bid),
        ask=_safe_float(ask),
        last=_safe_float(last),
        volume=None,
        open_interest=None,
        updated_at=now,
    )


def _append_snapshot(path: Path, quotes: Iterable[OptionQuote]) -> None:
    payload = [_quote_to_dict(q) for q in quotes]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _quote_to_dict(quote: OptionQuote) -> dict:
    return {
        "symbol": quote.contract.symbol,
        "option_type": quote.contract.option_type,
        "strike": quote.contract.strike,
        "expiration": quote.contract.expiration,
        "bid": quote.bid,
        "ask": quote.ask,
        "last": quote.last,
        "volume": quote.volume,
        "open_interest": quote.open_interest,
        "updated_at": quote.updated_at.isoformat(),
    }


def _load_fixture(path: Path, symbol: str, expiration: str) -> List[List[OptionQuote]]:
    if not path.exists():
        raise MockProviderError(f"fixture not found: {path}")

    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        raw_snapshots = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw_snapshots = raw

    if isinstance(raw_snapshots, dict):
        raw_snapshots = [raw_snapshots]
    if isinstance(raw_snapshots, list) and raw_snapshots:
        first = raw_snapshots[0]
        if isinstance(first, dict) and ("option_type" in first or "strike" in first):
            raw_snapshots = [raw_snapshots]
        elif not isinstance(first, (list, dict)):
            raise MockProviderError(f"unsupported fixture format: {path}")

    snapshots: List[List[OptionQuote]] = []
    if isinstance(raw_snapshots, list):
        for entry in raw_snapshots:
            snapshots.append(_parse_snapshot(entry, symbol, expiration))
    return snapshots


def _parse_snapshot(entry: object, symbol: str, expiration: str) -> List[OptionQuote]:
    if isinstance(entry, dict):
        if "options" in entry:
            rows = entry["options"]
        elif "quotes" in entry:
            rows = entry["quotes"]
        else:
            rows = [entry]
    elif isinstance(entry, list):
        rows = entry
    else:
        raise MockProviderError("snapshot entry must be dict or list")

    quotes: List[OptionQuote] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        option_type = row.get("option_type") or row.get("type")
        if option_type not in ("call", "put"):
            continue
        strike = _safe_float(row.get("strike"))
        if strike is None:
            continue
        contract = OptionContract(
            symbol=row.get("symbol") or symbol,
            option_type=option_type,
            strike=strike,
            expiration=row.get("expiration") or expiration,
        )
        updated_at = _parse_timestamp(row.get("updated_at"))
        quotes.append(
            OptionQuote(
                contract=contract,
                bid=_safe_float(row.get("bid")),
                ask=_safe_float(row.get("ask")),
                last=_safe_float(row.get("last")),
                volume=_safe_int(row.get("volume")),
                open_interest=_safe_int(row.get("open_interest")),
                updated_at=updated_at,
            )
        )
    return quotes


def _parse_timestamp(value: object) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
