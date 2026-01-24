from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import cred
from integrations.discord import bot, edit_discord_message, print_discord
from integrations.discord.templates import format_strategy_report
from paths import OPTIONS_STORAGE_DIR, OPTIONS_TRADE_LEDGER_PATH
from shared_state import print_log, safe_read_json, safe_write_json
from tools.analytics_trade_ledger import compute_metrics, load_positions
from utils.json_utils import read_config


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "use_test_channel": False,
    "update_existing": True,
}

STATE_PATH = OPTIONS_STORAGE_DIR / "strategy_report_message_ids.json"


@dataclass
class StrategyReportState:
    message_ids: Dict[str, int]


def _merge_defaults(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_config() -> Dict[str, Any]:
    raw = read_config("STRATEGY_REPORTING") or {}
    if not isinstance(raw, dict):
        raw = {}
    return _merge_defaults(DEFAULT_CONFIG, raw)


def _load_state(path: Path) -> StrategyReportState:
    if not path.exists() or path.stat().st_size == 0:
        return StrategyReportState(message_ids={})
    data = safe_read_json(path, default={})
    if not isinstance(data, dict):
        data = {}
    message_ids = data.get("message_ids")
    if not isinstance(message_ids, dict):
        message_ids = {}
    return StrategyReportState(message_ids=message_ids)


def _save_state(path: Path, state: StrategyReportState) -> None:
    payload = {"message_ids": state.message_ids}
    safe_write_json(path, payload)


def _resolve_channel_id(config: Dict[str, Any]) -> int:
    if bool(config.get("use_test_channel")):
        return int(getattr(cred, "DISCORD_TEST_CHANNEL_ID", 0) or 0)
    return int(getattr(cred, "DISCORD_STRATEGY_REPORTING_CHANNEL_ID", 0) or 0)


async def _send_with_temp_client(
    message: str,
    channel_id: int,
    logger,
    *,
    message_id: Optional[int] = None,
    update_existing: bool = False,
) -> Optional[int]:
    try:
        import discord
    except ImportError:
        logger("[STRATEGY REPORT] discord module not available.")
        return None

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    sent_id: Optional[int] = None

    @client.event
    async def on_ready():
        nonlocal sent_id
        try:
            channel = client.get_channel(channel_id)
            if channel is None:
                channel = await client.fetch_channel(channel_id)
            if message_id and update_existing:
                try:
                    existing = await channel.fetch_message(message_id)
                    await existing.edit(content=message)
                    sent_id = existing.id
                except Exception as exc:
                    logger(f"[STRATEGY REPORT] Temp client edit failed: {exc}")
            if sent_id is None:
                sent = await channel.send(message)
                sent_id = sent.id
        except Exception as exc:
            logger(f"[STRATEGY REPORT] Temp client send failed: {exc}")
        finally:
            await client.close()

    try:
        await client.start(cred.DISCORD_TOKEN)
    except Exception as exc:
        logger(f"[STRATEGY REPORT] Temp client login failed: {exc}")
        return None
    finally:
        if not client.is_closed():
            await client.close()
        http = getattr(client, "http", None)
        if http is not None:
            await http.close()
    return sent_id


async def send_strategy_reports(
    trading_day: Optional[str] = None,
    *,
    ledger_path: Optional[Path] = None,
    logger=None,
) -> None:
    log = logger or print_log
    config = _load_config()
    if not config.get("enabled"):
        return

    target_channel = _resolve_channel_id(config)
    if not target_channel:
        log("[STRATEGY REPORT] No channel configured; skipping.")
        return

    path = ledger_path or OPTIONS_TRADE_LEDGER_PATH
    if not path.exists():
        log(f"[STRATEGY REPORT] Ledger not found: {path}")
        return

    positions = load_positions(path)
    if not positions:
        log("[STRATEGY REPORT] No positions found; skipping.")
        return

    by_tag: Dict[str, list] = {}
    for position in positions:
        tag = position.strategy_tag or "unknown"
        by_tag.setdefault(tag, []).append(position)

    state = _load_state(STATE_PATH)
    updated = False
    use_temp_client = not bot.is_ready()

    for tag in sorted(by_tag.keys()):
        metrics = compute_metrics(by_tag[tag])
        note = f"EOD summary for {trading_day}" if trading_day else "EOD summary"
        last_updated = trading_day
        message = format_strategy_report(tag, metrics, note=note, last_updated=last_updated)

        message_id = state.message_ids.get(tag)
        if message_id is not None:
            try:
                message_id = int(message_id)
            except (TypeError, ValueError):
                message_id = None

        if message_id and config.get("update_existing", True) and not use_temp_client:
            await edit_discord_message(message_id, message, channel_id=target_channel)
        else:
            if use_temp_client:
                sent_id = await _send_with_temp_client(
                    message,
                    target_channel,
                    log,
                    message_id=message_id,
                    update_existing=bool(config.get("update_existing", True)),
                )
            else:
                sent = await print_discord(message, channel_id=target_channel)
                sent_id = sent.id if sent else None
            if sent_id:
                state.message_ids[tag] = sent_id
                updated = True

    if updated:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _save_state(STATE_PATH, state)
