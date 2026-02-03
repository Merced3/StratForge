from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from paths import (
    OPTIONS_RESEARCH_METRICS_PATH,
    OPTIONS_RESEARCH_PATHS_PATH,
    OPTIONS_RESEARCH_SIGNALS_PATH,
    OPTIONS_RESEARCH_SIM_PATH,
    OPTIONS_STORAGE_DIR,
    OPTIONS_TRADE_LEDGER_PATH,
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _backup_path(path: Path, stamp: str) -> Path:
    return path.with_suffix(path.suffix + f".bak.{stamp}")


def _backup_file(path: Path, stamp: str) -> Path:
    backup = _backup_path(path, stamp)
    backup.write_bytes(path.read_bytes())
    return backup


def _clear_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _delete_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def _handle_path(path: Path, *, action: str, backup: bool, stamp: str, apply: bool) -> None:
    exists = path.exists()
    if not exists:
        print(f"[RESET] skip (missing): {path}")
        return
    if backup:
        print(f"[RESET] backup -> {_backup_path(path, stamp)}")
    if not apply:
        print(f"[RESET] dry-run {action}: {path}")
        return
    if backup:
        _backup_file(path, stamp)
    if action == "clear":
        _clear_file(path)
    elif action == "delete":
        _delete_file(path)
    print(f"[RESET] {action}: {path}")


def _resolve_v1_paths() -> List[Path]:
    return [
        OPTIONS_TRADE_LEDGER_PATH,
        OPTIONS_STORAGE_DIR / "strategy_report_message_ids.json",
    ]


def _resolve_v2_paths(*, keep_rules: bool) -> List[tuple[Path, str]]:
    items: List[tuple[Path, str]] = [
        (OPTIONS_RESEARCH_SIGNALS_PATH, "delete"),
        (OPTIONS_RESEARCH_PATHS_PATH, "delete"),
        (OPTIONS_RESEARCH_METRICS_PATH, "delete"),
        (OPTIONS_RESEARCH_SIM_PATH, "delete"),
    ]
    if not keep_rules:
        items.append((OPTIONS_STORAGE_DIR / "analytics" / "rules.json", "delete"))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset analytics data for V1/V2 (with optional backups).",
    )
    parser.add_argument("--v1", action="store_true", help="Reset V1 analytics files.")
    parser.add_argument("--v2", action="store_true", help="Reset V2 analytics files.")
    parser.add_argument("--all", action="store_true", help="Reset both V1 and V2.")
    parser.add_argument("--keep-rules", action="store_true", help="Keep V2 rules.json.")
    parser.add_argument("--backup", action="store_true", help="Write .bak.<timestamp> copies before reset.")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run).")
    args = parser.parse_args()

    if not (args.v1 or args.v2 or args.all):
        print("[RESET] No targets specified. Use --v1, --v2, or --all.")
        return 1

    do_v1 = args.v1 or args.all
    do_v2 = args.v2 or args.all

    stamp = _timestamp()
    print(f"[RESET] Mode: {'apply' if args.apply else 'dry-run'}")
    if args.backup:
        print(f"[RESET] Backups enabled: .bak.{stamp}")

    if do_v1:
        print("[RESET] V1 targets:")
        for path in _resolve_v1_paths():
            action = "clear" if path == OPTIONS_TRADE_LEDGER_PATH else "delete"
            _handle_path(path, action=action, backup=args.backup, stamp=stamp, apply=args.apply)

    if do_v2:
        print("[RESET] V2 targets:")
        for path, action in _resolve_v2_paths(keep_rules=args.keep_rules):
            _handle_path(path, action=action, backup=args.backup, stamp=stamp, apply=args.apply)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
