from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp

from options.mock_provider import (
    RecordingOptionsProvider,
    ReplayOptionsProvider,
    SyntheticOptionsProvider,
    SyntheticQuoteConfig,
)
from options.quote_service import OptionQuoteService, TradierOptionsProvider

NY_TZ = ZoneInfo("America/New_York")

r"""
OPTIONS QUOTE HUB
-----------------
This script runs a central options quote cache for a single symbol/expiration.
It polls Tradier's option chain, caches quotes, and prints periodic summaries.

Quick start (module run from repo root):
  python -m options.quote_hub --symbol SPY --expiration 0dte

Common flags:
  --poll-interval   How often to hit Tradier (seconds).
  --log-every       How often to print summary lines (seconds).
  --sample-size     How many sample contracts to show per log line.
  --run-seconds     Optional auto-stop timer for quick tests.
  --expiration      0dte | YYYY-MM-DD | YYYYMMDD

Examples:
  # 1s polling, log every 5s
  python -m options.quote_hub --symbol SPY --expiration 0dte --poll-interval 1 --log-every 5

  # Faster polling + faster logs (watch for rate limiting)
  python -m options.quote_hub --symbol SPY --expiration 0dte --poll-interval 0.5 --log-every 1

  # Offline synthetic quotes (no network)
  python -m options.quote_hub --symbol SPY --expiration 0dte --mock --run-seconds 30

  # Replay a recorded fixture (JSONL or JSON)
  python -m options.quote_hub --symbol SPY --expiration 0dte --fixture fixtures/spy_0dte.jsonl

  # Record live snapshots to a JSONL file (then replay offline)
  python -m options.quote_hub --symbol SPY --expiration 0dte --record fixtures/spy_0dte.jsonl

  # Fixed-date expiration (useful for backtests or other projects)
  python -m options.quote_hub --symbol SPY --expiration 2026-01-12

  # Auto-stop after 30 seconds
  python -m options.quote_hub --symbol SPY --expiration 0dte --run-seconds 30

Auth:
  Defaults to cred.TRADIER_BROKERAGE_BASE_URL and cred.TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN.
  Or provide env vars:
    $env:TRADIER_BASE_URL="https://api.tradier.com/v1"
    $env:TRADIER_ACCESS_TOKEN="YOUR_TOKEN"
"""


def resolve_expiration(expiration: str) -> str:
    raw = expiration.strip()
    if not raw:
        raise ValueError("Expiration is empty")

    lower = raw.lower()
    if lower.endswith("dte") and lower[:-3].isdigit():
        days = int(lower[:-3])
        date_val = datetime.now(NY_TZ).date() + timedelta(days=days)
        while date_val.weekday() >= 5:
            date_val += timedelta(days=1)
        return date_val.strftime("%Y%m%d")

    if "-" in raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError as exc:
            raise ValueError(f"Unrecognized expiration format: {expiration}") from exc

    if raw.isdigit() and len(raw) == 8:
        return raw

    raise ValueError(f"Unrecognized expiration format: {expiration}")


def _log(message: str) -> None:
    print(message, flush=True)


def _load_tradier_config(base_url: Optional[str], token: Optional[str]) -> tuple[str, str]:
    resolved_base = base_url
    resolved_token = token
    if resolved_base and resolved_token:
        return resolved_base, resolved_token

    try:
        import cred
    except Exception as exc:
        raise RuntimeError("Missing Tradier config; pass --base-url and --token") from exc

    if not resolved_base:
        resolved_base = getattr(cred, "TRADIER_BROKERAGE_BASE_URL", None)
    if not resolved_token:
        resolved_token = getattr(cred, "TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN", None)

    if not resolved_base or not resolved_token:
        raise RuntimeError("Tradier config incomplete; pass --base-url and --token")

    return resolved_base, resolved_token


def _format_sample(updates, limit: int) -> str:
    if not updates or limit <= 0:
        return ""
    rows = []
    for quote in updates[:limit]:
        rows.append(
            f"{quote.contract.key} bid={quote.bid} ask={quote.ask} last={quote.last}"
        )
    return " | ".join(rows)


async def run_quote_hub(
    provider,
    symbol: str,
    expiration: str,
    poll_interval: float,
    log_every: float,
    sample_size: int,
    run_seconds: Optional[float],
) -> None:
    service = OptionQuoteService(
        provider,
        symbol=symbol,
        expiration=expiration,
        poll_interval=poll_interval,
        logger=_log,
    )
    _, queue = service.register_queue(contract_ids=None, maxsize=1)
    await service.start()
    _log(f"[HUB] Started for {symbol} expiration={expiration} poll={poll_interval}s")

    last_log = time.monotonic()
    updates_since = 0
    last_updates = []

    start_time = time.monotonic()
    try:
        while True:
            try:
                updates = await asyncio.wait_for(queue.get(), timeout=log_every)
                updates_since += len(updates)
                last_updates = updates
            except asyncio.TimeoutError:
                pass

            if run_seconds is not None and (time.monotonic() - start_time) >= run_seconds:
                _log("[HUB] Run time limit reached; stopping.")
                break

            now = time.monotonic()
            if now - last_log >= log_every:
                snapshot = service.get_snapshot()
                sample = _format_sample(last_updates, sample_size)
                _log(
                    f"[HUB] cached={len(snapshot)} updates={updates_since}"
                    + (f" sample={sample}" if sample else "")
                )
                updates_since = 0
                last_log = now
    finally:
        await service.stop()
        _log("[HUB] Stopped")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the options quote hub (Tradier chain cache). "
            "Polls the full option chain into a cache and logs periodic summaries."
        )
    )
    parser.add_argument("--symbol", default="SPY", help="Underlying symbol (default: SPY)")
    parser.add_argument("--expiration", default="0dte", help="Expiration (0dte, YYYY-MM-DD, or YYYYMMDD)")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--log-every", type=float, default=5.0, help="Log summary interval in seconds")
    parser.add_argument("--sample-size", type=int, default=3, help="Sample quotes to print per log")
    parser.add_argument("--run-seconds", type=float, default=None, help="Stop after this many seconds")
    parser.add_argument("--mock", action="store_true", help="Use offline synthetic quotes")
    parser.add_argument("--fixture", type=str, default=None, help="Replay snapshots from a JSON/JSONL file")
    parser.add_argument("--record", type=str, default=None, help="Record live snapshots to a JSONL file")
    parser.add_argument("--mock-underlying", type=float, default=500.0, help="Synthetic underlying price")
    parser.add_argument("--mock-step", type=float, default=1.0, help="Synthetic strike step")
    parser.add_argument("--mock-count", type=int, default=50, help="Strikes each side of underlying")
    parser.add_argument("--mock-jitter", type=float, default=0.25, help="Synthetic underlying jitter")
    parser.add_argument("--mock-seed", type=int, default=None, help="Synthetic random seed")
    parser.add_argument("--mock-spread", type=float, default=0.02, help="Synthetic spread percentage")
    parser.add_argument("--mock-min-spread", type=float, default=0.01, help="Synthetic minimum spread")
    parser.add_argument("--mock-time-value", type=float, default=0.5, help="Synthetic at-the-money time value")
    parser.add_argument("--mock-decay", type=float, default=0.02, help="Synthetic time value decay per strike")
    parser.add_argument("--mock-min-time-value", type=float, default=0.05, help="Synthetic minimum time value")
    parser.add_argument("--base-url", default=os.getenv("TRADIER_BASE_URL"))
    parser.add_argument("--token", default=os.getenv("TRADIER_ACCESS_TOKEN"))
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    expiration = resolve_expiration(args.expiration)
    if args.log_every < args.poll_interval:
        _log("[HUB] NOTE: log-every < poll-interval means some polls won't be visible.")

    async def _run_with_session() -> None:
        if args.fixture:
            provider = ReplayOptionsProvider(
                Path(args.fixture),
                symbol=args.symbol,
                expiration=expiration,
                logger=_log,
            )
            if args.record:
                provider = RecordingOptionsProvider(provider, Path(args.record), logger=_log)
            await run_quote_hub(
                provider=provider,
                symbol=args.symbol,
                expiration=expiration,
                poll_interval=args.poll_interval,
                log_every=args.log_every,
                sample_size=args.sample_size,
                run_seconds=args.run_seconds,
            )
            return

        if args.mock:
            config = SyntheticQuoteConfig(
                underlying_price=args.mock_underlying,
                strike_step=args.mock_step,
                strikes_each_side=args.mock_count,
                price_jitter=args.mock_jitter,
                spread_pct=args.mock_spread,
                min_spread=args.mock_min_spread,
                time_value_atm=args.mock_time_value,
                time_value_decay=args.mock_decay,
                min_time_value=args.mock_min_time_value,
                seed=args.mock_seed,
            )
            provider = SyntheticOptionsProvider(
                symbol=args.symbol,
                expiration=expiration,
                config=config,
                logger=_log,
            )
            if args.record:
                provider = RecordingOptionsProvider(provider, Path(args.record), logger=_log)
            await run_quote_hub(
                provider=provider,
                symbol=args.symbol,
                expiration=expiration,
                poll_interval=args.poll_interval,
                log_every=args.log_every,
                sample_size=args.sample_size,
                run_seconds=args.run_seconds,
            )
            return

        base_url, token = _load_tradier_config(args.base_url, args.token)
        async with aiohttp.ClientSession() as session:
            provider = TradierOptionsProvider(
                session=session,
                base_url=base_url,
                access_token=token,
                logger=_log,
            )
            if args.record:
                provider = RecordingOptionsProvider(provider, Path(args.record), logger=_log)
            await run_quote_hub(
                provider=provider,
                symbol=args.symbol,
                expiration=expiration,
                poll_interval=args.poll_interval,
                log_every=args.log_every,
                sample_size=args.sample_size,
                run_seconds=args.run_seconds,
            )

    asyncio.run(_run_with_session())


if __name__ == "__main__":
    main()
