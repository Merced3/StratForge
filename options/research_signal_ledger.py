from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from paths import OPTIONS_RESEARCH_SIGNALS_PATH


@dataclass
class ResearchSignalEvent:
    ts: str
    event: str
    signal_id: str
    strategy_tag: str
    timeframe: str
    symbol: str
    option_type: str
    strike: float
    expiration: str
    contract_key: str
    underlying_price: float
    entry_mark: float
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    reason: Optional[str] = None
    variant: Optional[str] = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_research_signal(
    event: ResearchSignalEvent,
    path: Optional[Path] = None,
    logger=None,
) -> None:
    target = path or OPTIONS_RESEARCH_SIGNALS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(event), ensure_ascii=True)
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    except Exception as exc:
        if logger:
            logger(f"[RESEARCH LEDGER] Failed to write research signal: {exc}")

