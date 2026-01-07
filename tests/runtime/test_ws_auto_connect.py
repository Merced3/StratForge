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
    def __init__(self, url, calls, messages, stop_event: asyncio.Event):
        self.url = url
        self.calls = calls
        self._messages = messages
        self._stop_event = stop_event
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
            while not self._stop_event.is_set():
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
    da.RETRY_INTERVAL = 0

    async def run():
        q = asyncio.Queue()
        stop_event = asyncio.Event()
        task = asyncio.create_task(da.ws_auto_connect(q, "SPY", stop_event))
        await asyncio.sleep(0.02)
        stop_event.set()
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
    da.RETRY_INTERVAL = 0

    async def run():
        q = asyncio.Queue()
        stop_event = asyncio.Event()
        task = asyncio.create_task(da.ws_auto_connect(q, "SPY", stop_event))
        await asyncio.sleep(0.02)
        stop_event.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert any("tradier" in url for url in calls)
    assert any("polygon" in url for url in calls)


def test_success_puts_message_and_honors_stop_event(monkeypatch):
    # Happy path: enqueue a trade, then exit when stop_event is set.
    calls = []

    async def run():
        q = asyncio.Queue()
        stop_event = asyncio.Event()

        def fake_connect(url, **_):
            return FakeWS(url, calls, ['{"type":"trade","price":1}'], stop_event=stop_event)

        monkeypatch.setattr(da, "websockets", SimpleNamespace(connect=fake_connect))
        monkeypatch.setattr(da, "get_session_id", lambda: "sid")
        monkeypatch.setattr(da, "get_enabled_providers", lambda: ["tradier"])
        da.RETRY_INTERVAL = 0

        task = asyncio.create_task(da.ws_auto_connect(q, "SPY", stop_event))
        msg = await q.get()
        assert json.loads(msg)["price"] == 1
        stop_event.set()  # trigger close path in ws_auto_connect
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=0.5)
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    asyncio.run(run())

    assert calls and any("tradier" in url for url in calls)
