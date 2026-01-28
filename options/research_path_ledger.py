from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from paths import OPTIONS_RESEARCH_PATHS_PATH


@dataclass
class ResearchPathEvent:
    ts: str
    event: str
    event_key: str
    signal_id: str
    strategy_tag: str
    timeframe: str
    symbol: str
    option_type: str
    strike: float
    expiration: str
    contract_key: str
    underlying_price: float
    mark: float
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    reason: Optional[str] = None
    variant: Optional[str] = None


def record_research_path_event(
    event: ResearchPathEvent,
    path: Optional[Path] = None,
    logger=None,
) -> None:
    target = path or OPTIONS_RESEARCH_PATHS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(event), ensure_ascii=True)
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    except Exception as exc:
        if logger:
            logger(f"[RESEARCH PATH] Failed to write path event: {exc}")

