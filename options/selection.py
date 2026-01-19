from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from .quote_service import OptionQuote

PriceRange = Tuple[float, float]

DEFAULT_PRICE_RANGES: Tuple[PriceRange, ...] = (
    (0.30, 0.50),
    (0.20, 0.80),
    (0.10, 1.25),
)


@dataclass(frozen=True)
class SelectionRequest:
    symbol: str
    option_type: str
    expiration: str
    underlying_price: float
    max_otm: Optional[float] = None
    price_ranges: Sequence[PriceRange] = DEFAULT_PRICE_RANGES


@dataclass(frozen=True)
class SelectionResult:
    quote: OptionQuote
    reason: str


class ContractSelector(Protocol):
    name: str

    def select(
        self,
        quotes: Iterable[OptionQuote],
        request: SelectionRequest,
    ) -> Optional[SelectionResult]:
        ...


class SelectorRegistry:
    def __init__(self) -> None:
        self._selectors: Dict[str, ContractSelector] = {}

    def register(self, selector: ContractSelector) -> None:
        self._selectors[selector.name] = selector

    def get(self, name: str) -> ContractSelector:
        if name not in self._selectors:
            raise KeyError(f"Unknown selector: {name}")
        return self._selectors[name]

    def list_names(self) -> List[str]:
        return sorted(self._selectors.keys())


class PriceRangeOtmSelector:
    name = "price-range-otm"

    def select(
        self,
        quotes: Iterable[OptionQuote],
        request: SelectionRequest,
    ) -> Optional[SelectionResult]:
        filtered = _filter_quotes(quotes, request)
        if not filtered:
            return None

        ordered = _order_by_strike(filtered, request.option_type)
        for lower, upper in request.price_ranges:
            for quote in ordered:
                ask = quote.ask
                if ask is None:
                    continue
                if lower <= ask <= upper:
                    return SelectionResult(quote=quote, reason="price-range")

        fallback = _fallback_cheapest(ordered, request.option_type, request.underlying_price)
        if fallback is not None:
            return SelectionResult(quote=fallback, reason="fallback-cheapest")
        return None


DEFAULT_SELECTOR_REGISTRY = SelectorRegistry()
DEFAULT_SELECTOR_REGISTRY.register(PriceRangeOtmSelector())


def select_contract(
    quotes: Iterable[OptionQuote],
    request: SelectionRequest,
    selector_name: str = PriceRangeOtmSelector.name,
    registry: Optional[SelectorRegistry] = None,
) -> Optional[SelectionResult]:
    registry = registry or DEFAULT_SELECTOR_REGISTRY
    selector = registry.get(selector_name)
    return selector.select(quotes, request)


def _filter_quotes(quotes: Iterable[OptionQuote], request: SelectionRequest) -> List[OptionQuote]:
    filtered: List[OptionQuote] = []
    for quote in quotes:
        contract = quote.contract
        if contract.symbol != request.symbol:
            continue
        if contract.option_type != request.option_type:
            continue
        if contract.expiration != request.expiration:
            continue
        if quote.ask is None:
            continue
        if request.max_otm is not None:
            if request.option_type == "call":
                if contract.strike < request.underlying_price:
                    continue
                if contract.strike > request.underlying_price + request.max_otm:
                    continue
            else:
                if contract.strike > request.underlying_price:
                    continue
                if contract.strike < request.underlying_price - request.max_otm:
                    continue
        filtered.append(quote)
    return filtered


def _order_by_strike(quotes: Iterable[OptionQuote], option_type: str) -> List[OptionQuote]:
    reverse = option_type == "put"
    return sorted(quotes, key=lambda q: q.contract.strike, reverse=reverse)


def _fallback_cheapest(
    quotes: Iterable[OptionQuote],
    option_type: str,
    underlying_price: float,
) -> Optional[OptionQuote]:
    candidates: List[OptionQuote] = []
    for quote in quotes:
        strike = quote.contract.strike
        if option_type == "call" and strike <= underlying_price:
            continue
        if option_type == "put" and strike >= underlying_price:
            continue
        if quote.ask is None:
            continue
        candidates.append(quote)
    if not candidates:
        return None
    return min(candidates, key=lambda q: q.ask or float("inf"))
