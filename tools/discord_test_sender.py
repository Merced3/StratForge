"""
Purpose:
- Send one-off test messages to a Discord channel without touching prod flows.
- Preview messages from integrations/discord/templates.py.

Channel selection:
- --channel-id overrides everything.
- Otherwise uses DISCORD_TEST_CHANNEL_ID in cred.py if set.
- Falls back to DISCORD_CHANNEL_ID.

How to get a channel ID:
- Discord URLs look like https://discord.com/channels/<guild>/<channel>
- The last number is the channel ID.

Usage (choose exactly one message source):
1) Simple message:
   python tools/discord_test_sender.py --message "Hello test channel"

2) Message from a file:
   python tools/discord_test_sender.py --message-file path\\to\\message.txt

3) Economic calendar message (cached):
   python tools/discord_test_sender.py --econ

4) Economic calendar message (refresh first, opens Chrome):
   python tools/discord_test_sender.py --econ --econ-refresh

5) Economic calendar message for a specific date (uses cached data):
   python tools/discord_test_sender.py --econ --econ-date 2026-01-22

6) Economic calendar message for a date with no events:
   python tools/discord_test_sender.py --econ --econ-date 2026-01-24

7) Template message with defaults:
   python tools/discord_test_sender.py --template trade-open

8) Template message with JSON overrides:
   python tools/discord_test_sender.py --template trade-open --template-json path\\to\\trade_open.json

Template names:
- trade-open
- trade-add
- trade-trim
- trade-close
- day-performance

Extras:
- --dry-run prints without sending.
- --file attaches a file.
- --timeout fails fast if the gateway login/send hangs.
- --debug prints progress steps.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import discord

import cred
from integrations.economic_calendar import EconomicCalendarService, ensure_economic_calendar_data
from integrations.discord.templates import (
    format_day_performance,
    format_trade_add,
    format_trade_close,
    format_trade_open,
    format_trade_trim,
)

TEMPLATE_DEFAULTS = {
    "trade-open": {
        "strategy_name": "EMA Crossover",
        "ticker_symbol": "SPY",
        "strike": 450.0,
        "option_type": "CALL",
        "quantity": 2,
        "order_price": 1.23,
        "total_investment": 246.0,
        "reason": "Breakout above VWAP",
    },
    "trade-add": {
        "quantity": 1,
        "total_value": 120.0,
        "fill_price": 1.2,
        "reason": "Added on retest",
    },
    "trade-trim": {
        "quantity": 1,
        "total_value": 180.0,
        "fill_price": 1.8,
        "reason": "Trim into strength",
    },
    "trade-close": {
        "avg_exit": 2.15,
        "total_pnl": 145.5,
        "percent": 58.4,
        "profit_indicator": None,
    },
    "day-performance": {
        "trades_str_list": ["$120.00, 25.00%+", "$-50.00, -10.00%-"],
        "total_bp_used_today": 1000.0,
        "start_balance": 20000.0,
        "end_balance": 20100.0,
    },
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a test message to a Discord channel.")
    parser.add_argument("--channel-id", type=int, default=None, help="Override channel ID to send to.")
    parser.add_argument("--message", type=str, default=None, help="Message to send.")
    parser.add_argument("--message-file", type=str, default=None, help="Path to a text file with the message.")
    parser.add_argument(
        "--template",
        choices=sorted(TEMPLATE_DEFAULTS.keys()),
        default=None,
        help="Send a message built from integrations/discord/templates.py.",
    )
    parser.add_argument(
        "--template-json",
        type=str,
        default=None,
        help="Path to a JSON file with overrides for the selected template.",
    )
    parser.add_argument("--econ", action="store_true", help="Send today's economic calendar message.")
    parser.add_argument(
        "--econ-refresh",
        action="store_true",
        help="Refresh economic calendar data before sending the message.",
    )
    parser.add_argument(
        "--econ-date",
        type=str,
        default=None,
        help="Override econ message date (YYYY-MM-DD).",
    )
    parser.add_argument("--file", type=str, default=None, help="Optional file to attach.")
    parser.add_argument("--dry-run", action="store_true", help="Print the message without sending.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait before aborting.")
    parser.add_argument("--debug", action="store_true", help="Print progress steps.")
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    sources = [
        bool(args.message),
        bool(args.message_file),
        bool(args.template),
        bool(args.econ),
    ]
    if sum(sources) != 1:
        raise ValueError("Choose exactly one: --message, --message-file, --template, or --econ.")
    if args.econ_refresh and not args.econ:
        raise ValueError("--econ-refresh only applies when using --econ.")
    if args.econ_date and not args.econ:
        raise ValueError("--econ-date only applies when using --econ.")
    if args.template_json and not args.template:
        raise ValueError("--template-json requires --template.")


def _load_message(args: argparse.Namespace) -> str:
    if args.econ:
        service = EconomicCalendarService()
        return service.build_daily_message(now=_parse_econ_datetime(args.econ_date))

    if args.template:
        return _load_template_message(args)

    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8")

    if args.message:
        return args.message

    raise ValueError("Provide --message, --message-file, --template, or --econ.")


def _load_template_message(args: argparse.Namespace) -> str:
    template_name = args.template
    data = dict(TEMPLATE_DEFAULTS[template_name])
    overrides = _load_template_overrides(args.template_json)
    data.update(overrides)

    if template_name == "trade-open":
        return format_trade_open(
            strategy_name=str(data["strategy_name"]),
            ticker_symbol=str(data["ticker_symbol"]),
            strike=float(data["strike"]),
            option_type=str(data["option_type"]),
            quantity=int(data["quantity"]),
            order_price=_float_or_none(data.get("order_price")),
            total_investment=_float_or_none(data.get("total_investment")),
            reason=_str_or_none(data.get("reason")),
        )

    if template_name == "trade-add":
        return format_trade_add(
            quantity=int(data["quantity"]),
            total_value=_float_or_none(data.get("total_value")),
            fill_price=_float_or_none(data.get("fill_price")),
            reason=_str_or_none(data.get("reason")),
        )

    if template_name == "trade-trim":
        return format_trade_trim(
            quantity=int(data["quantity"]),
            total_value=_float_or_none(data.get("total_value")),
            fill_price=_float_or_none(data.get("fill_price")),
            reason=_str_or_none(data.get("reason")),
        )

    if template_name == "trade-close":
        return format_trade_close(
            avg_exit=_float_or_none(data.get("avg_exit")),
            total_pnl=_float_or_none(data.get("total_pnl")),
            percent=_float_or_none(data.get("percent")),
            profit_indicator=_str_or_none(data.get("profit_indicator")),
        )

    if template_name == "day-performance":
        trades_str_list = _coerce_trades_list(data.get("trades_str_list"))
        total_bp_used_today = float(data.get("total_bp_used_today", 0.0))
        start_balance = float(data.get("start_balance", 0.0))
        end_balance = float(data.get("end_balance", start_balance))
        profit_loss = data.get("profit_loss")
        if profit_loss is None:
            profit_loss = end_balance - start_balance
        percent_gl = data.get("percent_gl")
        if percent_gl is None:
            percent_gl = (profit_loss / start_balance * 100) if start_balance else 0.0

        return format_day_performance(
            trades_str_list=trades_str_list,
            total_bp_used_today=total_bp_used_today,
            start_balance=start_balance,
            end_balance=end_balance,
            profit_loss=profit_loss,
            percent_gl=percent_gl,
        )

    raise ValueError(f"Unknown template: {template_name}")


def _load_template_overrides(path: Optional[str]) -> dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Template JSON overrides must be a JSON object.")
    return data


def _coerce_trades_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_econ_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Expected --econ-date in YYYY-MM-DD format.") from exc
    return datetime.combine(day, time(hour=12))


async def _send_message(
    channel_id: int,
    message: str,
    file_path: Optional[str],
    timeout: float,
    debug: bool,
) -> None:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    async def _deliver() -> None:
        try:
            if debug:
                print(f"[discord-test] Fetching channel {channel_id}...")
            channel = client.get_channel(channel_id)
            if channel is None:
                channel = await client.fetch_channel(channel_id)

            if debug:
                print("[discord-test] Sending message...")
            if file_path:
                upload = discord.File(file_path)
                if message:
                    await channel.send(content=message, file=upload)
                else:
                    await channel.send(file=upload)
            else:
                await channel.send(message)
            if debug:
                print("[discord-test] Message sent.")
        except discord.NotFound:
            print(f"Channel not found for ID {channel_id}.")
        except discord.Forbidden as exc:
            print(f"Forbidden: {exc}")
        except discord.HTTPException as exc:
            print(f"Discord API error: {exc}")
        finally:
            await client.close()

    @client.event
    async def on_ready() -> None:
        if debug:
            print(f"[discord-test] Logged in as {client.user}.")
        await _deliver()

    if debug:
        print("[discord-test] Connecting to Discord...")
    try:
        await asyncio.wait_for(client.start(cred.DISCORD_TOKEN), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[discord-test] Timeout after {timeout:.0f}s waiting for send.")
        await client.close()
    except discord.LoginFailure as exc:
        print(f"[discord-test] Login failed: {exc}")
        await client.close()
    except Exception as exc:
        print(f"[discord-test] Discord client error: {exc}")
        await client.close()
    finally:
        await asyncio.sleep(0.2)


async def main() -> None:
    args = _parse_args()
    _validate_args(args)

    channel_id = (
        args.channel_id
        or getattr(cred, "DISCORD_TEST_CHANNEL_ID", None)
        or getattr(cred, "DISCORD_CHANNEL_ID", None)
    )
    if not channel_id:
        raise ValueError("Channel ID is required (use --channel-id or set DISCORD_CHANNEL_ID).")

    if args.econ_refresh:
        await ensure_economic_calendar_data()

    message = _load_message(args)
    if args.dry_run:
        print(message)
        return

    await _send_message(
        channel_id,
        message,
        args.file,
        timeout=args.timeout,
        debug=args.debug,
    )


if __name__ == "__main__":
    asyncio.run(main())
