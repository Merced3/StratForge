import asyncio
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


def test_single_provider_retries(monkeypatch):
    calls = []

    def fake_connect(url, **_):
        return FailingWS(url, calls)

    monkeypatch.setattr(da, "websockets", SimpleNamespace(connect=fake_connect))
    monkeypatch.setattr(da, "get_session_id", lambda: "sid")
    monkeypatch.setitem(da.PROVIDERS["tradier"], "enabled", True)
    da.should_close = False
    da.RETRY_INTERVAL = 0

    async def run():
        q = asyncio.Queue()
        task = asyncio.create_task(da.ws_auto_connect(q, ["tradier"], "SPY"))
        await asyncio.sleep(0.05)
        da.should_close = True
        await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(run())

    assert calls and all("tradier" in url for url in calls)


def test_rotation_on_failure(monkeypatch):
    calls = []

    def fake_connect(url, **_):
        return FailingWS(url, calls)

    monkeypatch.setattr(da, "websockets", SimpleNamespace(connect=fake_connect))
    monkeypatch.setattr(da, "get_session_id", lambda: "sid")
    monkeypatch.setitem(da.PROVIDERS["tradier"], "enabled", True)
    monkeypatch.setitem(da.PROVIDERS["polygon"], "enabled", True)
    da.should_close = False
    da.RETRY_INTERVAL = 0

    async def run():
        q = asyncio.Queue()
        task = asyncio.create_task(da.ws_auto_connect(q, ["tradier", "polygon"], "SPY"))
        await asyncio.sleep(0.05)
        da.should_close = True
        await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(run())

    assert any("tradier" in url for url in calls)
    assert any("polygon" in url for url in calls)
