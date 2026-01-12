from __future__ import annotations

import argparse
import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp

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
    symbol: str,
    expiration: str,
    poll_interval: float,
    log_every: float,
    sample_size: int,
    base_url: Optional[str],
    token: Optional[str],
    run_seconds: Optional[float],
) -> None:
    base_url, token = _load_tradier_config(base_url, token)
    async with aiohttp.ClientSession() as session:
        provider = TradierOptionsProvider(session, base_url=base_url, access_token=token, logger=_log)
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
    parser.add_argument("--base-url", default=os.getenv("TRADIER_BASE_URL"))
    parser.add_argument("--token", default=os.getenv("TRADIER_ACCESS_TOKEN"))
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    expiration = resolve_expiration(args.expiration)
    if args.log_every < args.poll_interval:
        _log("[HUB] NOTE: log-every < poll-interval means some polls won't be visible.")
    asyncio.run(
        run_quote_hub(
            symbol=args.symbol,
            expiration=expiration,
            poll_interval=args.poll_interval,
            log_every=args.log_every,
            sample_size=args.sample_size,
            base_url=args.base_url,
            token=args.token,
            run_seconds=args.run_seconds,
        )
    )


if __name__ == "__main__":
    main()
