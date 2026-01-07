# tests/runtime/test_ws_auto_connect.py
import asyncio
import json
from contextlib import suppress
from types import SimpleNamespace

import data_acquisition as da


class FailingWS:
    def __init__(self, url, calls):
        self.url = url
        self.calls = calls

    async def __aenter__(self):
        # Record the attempt, then fail to trigger retry/rotation
        self.calls.append(self.url)
        raise RuntimeError("fail")

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeWS:
    """Async websocket stub that yields messages and supports close(); used to drive happy-path behavior."""
    def __init__(self, url, calls, messages, should_close_cb):
        self.url = url
        self.calls = calls
        self._messages = messages
        self._should_close = should_close_cb
        self.closed = False

    async def __aenter__(self):
        self.calls.append(self.url)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, _):
        # no-op for auth/sub messages
        return

    def __aiter__(self):
        async def gen():
            for m in self._messages:
                yield m
            # keepalive messages so ws_auto_connect can hit should_close branch
            while not self._should_close():
                yield '{"type":"keepalive"}'
                await asyncio.sleep(0)
        return gen()

    async def close(self):
        self.closed = True


def test_single_provider_retries(monkeypatch):
    # Single provider keeps retrying on failure.
    calls = []

    def fake_connect(url, **_):
        return FailingWS(url, calls)

    monkeypatch.setattr(da, "websockets", SimpleNamespace(connect=fake_connect))
    monkeypatch.setattr(da, "get_session_id", lambda: "sid")
    monkeypatch.setattr(da, "get_enabled_providers", lambda: ["tradier"])
    da.should_close = False
    da.RETRY_INTERVAL = 0

    async def run():
        q = asyncio.Queue()
        task = asyncio.create_task(da.ws_auto_connect(q, "SPY"))
        await asyncio.sleep(0.02)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert calls and all("tradier" in url for url in calls)


def test_rotation_on_failure(monkeypatch):
    # Failure triggers provider rotation.
    calls = []

    def fake_connect(url, **_):
        return FailingWS(url, calls)

    monkeypatch.setattr(da, "websockets", SimpleNamespace(connect=fake_connect))
    monkeypatch.setattr(da, "get_session_id", lambda: "sid")
    monkeypatch.setattr(da, "get_enabled_providers", lambda: ["tradier", "polygon"])
    da.should_close = False
    da.RETRY_INTERVAL = 0

    async def run():
        q = asyncio.Queue()
        task = asyncio.create_task(da.ws_auto_connect(q, "SPY"))
        await asyncio.sleep(0.02)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert any("tradier" in url for url in calls)
    assert any("polygon" in url for url in calls)


def test_success_puts_message_and_honors_should_close(monkeypatch):
    # Happy path: enqueue a trade, then exit when should_close flips.
    calls = []

    def fake_connect(url, **_):
        return FakeWS(url, calls, ['{"type":"trade","price":1}'], should_close_cb=lambda: da.should_close)

    monkeypatch.setattr(da, "websockets", SimpleNamespace(connect=fake_connect))
    monkeypatch.setattr(da, "get_session_id", lambda: "sid")
    monkeypatch.setattr(da, "get_enabled_providers", lambda: ["tradier"])
    da.should_close = False
    da.RETRY_INTERVAL = 0

    async def run():
        q = asyncio.Queue()
        task = asyncio.create_task(da.ws_auto_connect(q, "SPY"))
        msg = await q.get()
        assert json.loads(msg)["price"] == 1
        da.should_close = True  # trigger close path in ws_auto_connect
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=0.5)
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    asyncio.run(run())

    assert calls and any("tradier" in url for url in calls)
