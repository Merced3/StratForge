import asyncio
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.anyio

from options.quote_service import OptionContract, OptionQuote, OptionQuoteService


class QueueProvider:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = None

    @property
    def queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    async def fetch_quotes(self, symbol: str, expiration: str):
        return await self.queue.get()


def _make_quote(symbol, option_type, strike, expiration, bid, ask, last=None):
    contract = OptionContract(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
    )
    return OptionQuote(
        contract=contract,
        bid=bid,
        ask=ask,
        last=last,
        volume=None,
        open_interest=None,
        updated_at=datetime.now(timezone.utc),
    )


def test_option_quote_mid():
    quote = _make_quote("SPY", "call", 500.0, "20260106", bid=1.0, ask=1.4, last=1.2)
    assert quote.mid == 1.2

    quote_missing = _make_quote("SPY", "call", 500.0, "20260106", bid=None, ask=1.4, last=1.2)
    assert quote_missing.mid is None


async def test_quote_service_updates_and_filters():
    provider = QueueProvider()
    service = OptionQuoteService(
        provider,
        symbol="SPY",
        expiration="20260106",
        poll_interval=0.01,
    )

    _, queue = service.register_queue(contract_ids=None, maxsize=1)
    await service.start()
    try:
        q1 = _make_quote("SPY", "call", 500.0, "20260106", bid=1.0, ask=1.2, last=1.1)
        q2 = _make_quote("SPY", "put", 490.0, "20260106", bid=0.9, ask=1.1, last=1.0)
        await provider.queue.put([q1, q2])
        updates = await asyncio.wait_for(queue.get(), timeout=1)
        assert {u.contract.key for u in updates} == {q1.contract.key, q2.contract.key}

        await provider.queue.put([q1, q2])
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.2)

        q1b = _make_quote("SPY", "call", 500.0, "20260106", bid=1.05, ask=1.2, last=1.1)
        await provider.queue.put([q1b, q2])
        updates = await asyncio.wait_for(queue.get(), timeout=1)
        assert [u.contract.key for u in updates] == [q1.contract.key]
    finally:
        await service.stop()


async def test_quote_service_contract_filter():
    provider = QueueProvider()
    service = OptionQuoteService(
        provider,
        symbol="SPY",
        expiration="20260106",
        poll_interval=0.01,
    )
    q1 = _make_quote("SPY", "call", 500.0, "20260106", bid=1.0, ask=1.2)
    q2 = _make_quote("SPY", "put", 490.0, "20260106", bid=0.9, ask=1.1)

    _, queue = service.register_queue(contract_ids={q1.contract.key}, maxsize=1)
    await service.start()
    try:
        await provider.queue.put([q1, q2])
        updates = await asyncio.wait_for(queue.get(), timeout=1)
        assert [u.contract.key for u in updates] == [q1.contract.key]
    finally:
        await service.stop()


def test_set_expiration_clears_cache():
    provider = QueueProvider()
    service = OptionQuoteService(
        provider,
        symbol="SPY",
        expiration="20260106",
        poll_interval=0.01,
    )
    q1 = _make_quote("SPY", "call", 500.0, "20260106", bid=1.0, ask=1.2)
    service._quotes[q1.contract.key] = q1
    service.set_expiration("20260107")
    assert service.get_snapshot() == {}
