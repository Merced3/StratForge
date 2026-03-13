import asyncio

from integrations.discord import client as discord_client


class DummyResponse:
    def __init__(self, status=429, headers=None):
        self.status = status
        self.headers = headers or {}


class DummyException(Exception):
    def __init__(self, *, retry_after=None, status=None, text=None, response=None):
        super().__init__("dummy")
        self.retry_after = retry_after
        self.status = status
        self.text = text
        self.response = response


def test_extract_retry_after_prefers_direct_attr():
    exc = DummyException(retry_after="1.5")
    assert discord_client._extract_retry_after_seconds(exc) == 1.5


def test_extract_retry_after_from_text_dict():
    exc = DummyException(status=429, text={"retry_after": 2})
    assert discord_client._extract_retry_after_seconds(exc) == 2.0


def test_extract_retry_after_from_headers():
    response = DummyResponse(status=429, headers={"Retry-After": "3"})
    exc = DummyException(status=429, response=response)
    assert discord_client._extract_retry_after_seconds(exc) == 3.0


def test_extract_retry_after_ignores_non_429_without_attr():
    exc = DummyException(status=500, text={"retry_after": 2})
    assert discord_client._extract_retry_after_seconds(exc) is None


def test_maybe_wait_for_rate_limit_uses_backoff(monkeypatch):
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(discord_client, "print_log", lambda _message: None)
    monkeypatch.setattr(discord_client.asyncio, "sleep", fake_sleep)
    exc = DummyException(retry_after=0.5)
    result = asyncio.run(discord_client._maybe_wait_for_rate_limit(exc, attempt=2, backoff_factor=1))
    assert result is True
    assert waits == [4]
