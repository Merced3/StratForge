# Orders & Tracking (Current)

This doc captures how orders, positions, and trade history are tracked today.
It is a reference for debugging, analytics, and future refactors.

---

## 1) Core responsibilities

- Submit orders via a shared executor (paper or broker).
- Track each order with status + fill info.
- Aggregate orders into positions (open/add/trim/close).
- Persist trade events locally (ledger) before any Discord calls.

---

## 2) Main components

### `options/order_manager.py`

- `OptionsOrderManager` owns order submission and position lifecycle.
- `OrderContext` stores order id, side, qty, fill price, and position link.
- `Position` stores average entry, open quantity, realized P&L, and status.

### `options/execution_paper.py`

- Fills using cached quotes.
- Buy uses ask (fallback: mid -> last -> bid).
- Sell uses bid (fallback: mid -> last -> ask).

### `options/trade_ledger.py`

- Append-only JSONL: `storage/options/trade_events.jsonl`.
- Written **before** Discord updates to keep analytics reliable if network fails.

### `runtime/options_trade_notifier.py`

- Adapter for Discord + chart markers.
- One Discord message per position; edits on add/trim/close.
- Restores message content from `storage/message_ids.json` if needed.

### `options/position_watcher.py`

- Streams mark price updates for open positions.
- When wired into the runner, strategies can implement `on_position_update`.

### `strategies/options/exit_rules.py`

- Shared profit-target helpers for trim/close actions.
- Used by strategies to keep exits consistent and testable.

---

## 3) Lifecycle flow

1) Strategy generates a signal.
2) Runner calls `OptionsOrderManager.open_position()`.
3) Manager submits order via executor.
4) Fill is applied to the position.
5) Notifier writes a `TradeEvent` to the ledger.
6) Notifier sends/edits Discord message and marker.

---

## 4) Persistent artifacts

- `storage/options/trade_events.jsonl`
  - Source of truth for analytics.
- `storage/message_ids.json`
  - Mapping of `position_id -> discord_message_id`.
  - Reset at EOD.

---

## 5) Current limitations

- Ledger is not yet summarized into daily analytics.
- Positions are in-memory (no mid-day restart resume).
- Paper execution does not model slippage/partial fills.

---

## 6) Future ideas

- Daily analytics pipeline from JSONL ledger.
- Persist open positions for resume after restart.
- Add reconciliation against broker fill history.
