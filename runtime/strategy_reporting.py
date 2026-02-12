from __future__ import annotations

import importlib
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


_CONFIG_IGNORE_KEYS = {
    "STRATEGY_BASE_NAME",
    "STRATEGY_DESCRIPTION",
    "STRATEGY_CONFIG_SUMMARY",
    "STRATEGY_ASSESSMENT",
    "IS_ENABLED",
    "MODE",
    "SINGLE_TIMEFRAME",
    "TIMEFRAMES",
}


def _format_config_value(value: object) -> Optional[str]:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        if all(isinstance(item, (str, int, float, bool)) for item in value):
            return ",".join(str(item) for item in value)
    return None


def _build_config_summary(module: object) -> Optional[str]:
    explicit = getattr(module, "STRATEGY_CONFIG_SUMMARY", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    pieces: list[str] = []
    mode = getattr(module, "MODE", None)
    if mode:
        pieces.append(f"mode={mode}")

    single_tf = getattr(module, "SINGLE_TIMEFRAME", None)
    timeframes = getattr(module, "TIMEFRAMES", None)
    tf_label = None
    if str(mode or "").lower() == "multi":
        if isinstance(timeframes, (list, tuple)):
            tfs = [str(tf) for tf in timeframes if tf]
        else:
            tfs = []
        if not tfs and single_tf:
            tfs = [str(single_tf)]
        if tfs:
            tf_label = ",".join(tfs)
    else:
        if single_tf:
            tf_label = str(single_tf)
        elif isinstance(timeframes, (list, tuple)) and timeframes:
            tf_label = str(timeframes[0])

    if tf_label:
        pieces.append(f"tf={tf_label}")

    extras: list[str] = []
    for name, value in vars(module).items():
        if not name.isupper() or name in _CONFIG_IGNORE_KEYS:
            continue
        formatted = _format_config_value(value)
        if formatted is None or formatted == "":
            continue
        extras.append(f"{name.lower()}={formatted}")

    pieces.extend(extras)
    return " | ".join(pieces) if pieces else None


def _load_strategy_metadata(root: Optional[Path] = None) -> Dict[str, dict]:
    base = root or Path(__file__).resolve().parents[1] / "strategies" / "options"
    if not base.exists():
        return {}
    metadata: Dict[str, dict] = {}
    for path in sorted(base.glob("*.py")):
        if path.name.startswith("_") or path.name in ("types.py", "exit_rules.py"):
            continue
        module_name = f"strategies.options.{path.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        base_name = getattr(module, "STRATEGY_BASE_NAME", None)
        if not base_name:
            continue
        description = getattr(module, "STRATEGY_DESCRIPTION", None)
        description_value = str(description).strip() if description else None
        assessment = getattr(module, "STRATEGY_ASSESSMENT", None)
        assessment_value = str(assessment).strip() if assessment else None
        enabled = getattr(module, "IS_ENABLED", None)
        config_summary = _build_config_summary(module)
        metadata[str(base_name)] = {
            "description": description_value or None,
            "assessment": assessment_value or None,
            "enabled": bool(enabled) if enabled is not None else None,
            "config_summary": config_summary,
        }
    return metadata


def _resolve_metadata(tag: str, metadata: Dict[str, dict]) -> dict:
    if not tag or not metadata:
        return {}
    if tag in metadata:
        return metadata[tag]
    for base_name in sorted(metadata.keys(), key=len, reverse=True):
        if tag.startswith(f"{base_name}-"):
            return metadata[base_name]
    return {}


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
    metadata = _load_strategy_metadata()

    for tag in sorted(by_tag.keys()):
        metrics = compute_metrics(by_tag[tag])
        last_updated = trading_day
        meta = _resolve_metadata(tag, metadata)
        description = meta.get("description")
        assessment = meta.get("assessment")
        enabled = meta.get("enabled")
        config_summary = meta.get("config_summary")
        message = format_strategy_report(
            tag,
            metrics,
            description=description,
            last_updated=last_updated,
            assessment=assessment,
            enabled=enabled,
            config_summary=config_summary,
        )

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
