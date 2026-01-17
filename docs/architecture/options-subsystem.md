# Options Subsystem (Study Sheet)

This document is a **study sheet** for the options subsystem under `options/`.
It explains the mental model, the entry points, and how the parts connect so you
can revisit it later and remember how to work on it safely.

---

## 1) What this subsystem is for

The options subsystem provides a **centralized options chain cache** and a
simple, decoupled way to:

1. Fetch and cache options quotes (bid/ask/last).
2. Select a contract (strike) based on a rule/selector.
3. Execute an order in either **paper mode** or **real broker mode**.

The key design goal: **simple, decoupled, easy to change**.
Each stage can be replaced without rewriting the others.

---

## 2) High-level data flow (the pipeline)

```bash
Tradier (or other provider)
        |
        v
OptionsProvider.fetch_quotes()
        |
        v
OptionQuoteService (cache + change stream)
        |
        +----> selection.select_contract(...)  -> picks a contract
        |
        +----> PaperOrderExecutor / TradierOrderExecutor
```

**In plain language:**

1) Provider pulls the full chain from Tradier.
2) Quote service caches it and emits **only changed quotes**.
3) Selector chooses which contract to trade.
4) Executor submits or simulates the order.

---

## 3) Files and their responsibilities

### `options/quote_service.py`

**Purpose:** Central cache + event stream of option quotes.

Key pieces:

- `OptionContract`: unique identifier for a contract.
- `OptionQuote`: bid/ask/last + metadata.
- `OptionsProvider` protocol: any provider that can fetch quotes.
- `TradierOptionsProvider`: concrete provider for Tradier.
- `OptionQuoteService`: poll loop, cache, and listener/queue updates.

**Entry points:**

- `OptionQuoteService.start()` -> starts polling
- `OptionQuoteService.stop()` -> stops polling
- `OptionQuoteService.get_snapshot()` -> returns full cache
- `OptionQuoteService.get_quote(contract_key)` -> returns one quote
- `OptionQuoteService.register_listener(callback)` -> push updates to a function
- `OptionQuoteService.register_queue(...)` -> push updates to a queue

**Why it exists:**
Instead of every order calling Tradier, this pulls once and shares the cache.
It reduces API calls and makes the system less fragile.

---

### `options/quote_hub.py`

**Purpose:** Standalone CLI runner for the quote cache.

It starts `OptionQuoteService`, logs summary stats, and exits on Ctrl+C
or after `--run-seconds`.

**Entry point:**

- `python -m options.quote_hub ...`

**Useful flags:**

- `--poll-interval` -> how often to hit Tradier
- `--log-every` -> how often to print a summary
- `--run-seconds` -> auto-stop timer
- `--expiration` -> `0dte`, `YYYY-MM-DD`, or `YYYYMMDD`

**What it proves:** The cache is live and updating.

---

### `options/selection.py`

**Purpose:** Choose a contract/strike from cached quotes.

Key pieces:

- `SelectionRequest`: defines the selection context.
- `SelectionResult`: result + reason.
- `ContractSelector` protocol: interface for selector strategies.
- `PriceRangeOtmSelector`: default selector (price-range + OTM logic).
- `SelectorRegistry`: registry of named selectors.

**Entry points:**

- `select_contract(quotes, request, selector_name)`
- `DEFAULT_SELECTOR_REGISTRY.register(...)` to add custom selectors.

**Why it exists:** strategy can swap selection logic without touching
quote fetching or order execution.

---

### `options/execution_paper.py`

**Purpose:** Simulated order execution using cached quotes (primary mode).

Key pieces:

- `PaperOrderExecutor`: fills orders using bid/ask from cache.

**How fills work:**

- Buy -> uses ask (fallback: mid, last, bid).
- Sell -> uses bid (fallback: mid, last, ask).
- Limit orders only fill if price crosses.
- Orders stored in memory; `get_order_status()` returns status.

**Entry points:**

- `PaperOrderExecutor.submit_option_order(...)`
- `PaperOrderExecutor.get_order_status(order_id)`

**Why it exists:** Run strategies without broker latency/limits.

---

### `options/execution_tradier.py`

**Purpose:** Real order execution via Tradier.

Key pieces:

- `TradierOrderExecutor`: submit + status via Tradier endpoints.
- `OptionOrderRequest`: shared order request model.

**Entry points:**

- `TradierOrderExecutor.submit_option_order(...)`
- `TradierOrderExecutor.get_order_status(order_id)`

**Why it exists:** swap paper fills for real broker mode without changing
the rest of the system.

---

### `options/order_manager.py`

**Purpose:** Orchestration layer that connects quotes, selection, and execution.

Key pieces:

- `OptionsOrderManager`: buy/sell and position lifecycle methods.
- `Position`: tracks open quantity, average entry, realized P&L, and status.
- `OrderContext`: tracks each submitted order and links it to a position.

**Entry points:**

- `open_position(...)` -> select + submit buy, returns `position_id`
- `add_to_position(position_id, qty)` -> buy more
- `trim_position(position_id, qty)` -> sell some
- `close_position(position_id)` -> sell remaining
- `get_status(order_id)` -> refresh status from executor

**Position IDs:**

IDs are human-readable for debugging:

```bash
pos-<SYMBOL>-<TYPE>-<STRIKE>-<EXP>-tag-<TAG>-<TIMESTAMP>
```

Example:

```bash
pos-SPY-call-500p5-20260106-tag-flag_zone-20260112123456789012
```

`tag-...` is included only if a strategy tag is provided.

---

### `options/position_watcher.py`

**Purpose:** Watch open positions and stream updates from the quote cache.

Key pieces:

- `PositionWatcher`: polls active positions, subscribes to the right contracts,
  and emits updates when quotes change.
- `PositionUpdate`: payload containing mark price, P&L, and position metadata.

**Entry points:**

- `PositionWatcher.start()` -> begin watching
- `PositionWatcher.stop()` -> stop watching
- `PositionWatcher.register_listener(callback)` -> push updates to a function
- `PositionWatcher.register_queue(...)` -> push updates to a queue

**How mark price is picked:**

`bid` -> `mid` -> `last` -> `ask` (first available).

**Why it exists:**
It decouples real-time quote tracking from strategy logic so strategies can
react without re-polling the provider.

---

### `options/trade_ledger.py`

**Purpose:** Append-only local trade ledger (source of truth).

Key pieces:

- `TradeEvent`: normalized record for open/add/trim/close events.
- `build_trade_event(...)`: builds a record from a position + order result.
- `record_trade_event(...)`: appends JSONL to `storage/options/trade_events.jsonl`.

**Why it exists:**
Discord is display-only. The ledger is written **before any Discord call** so
you still have reliable data if Wi-Fi drops or Discord is down.

---

### `runtime/market_bus.py`

**Purpose:** In-process event bus for candle-close events.

Key pieces:

- `MarketEventBus`: register listeners or queues for `CandleCloseEvent`.
- `CandleCloseEvent`: payload emitted after a candle is finalized.

**Why it exists:**
It lets the pipeline publish a single event that can be consumed by strategies, watchers, or chart refreshers without adding HTTP or file polling.

---

### `runtime/options_strategy_runner.py`

**Purpose:** Glue layer that listens to the market bus and runs strategies.

Key pieces:

- `OptionsStrategyRunner`: subscribes to `CandleCloseEvent` and calls each strategy.
- EMA cache: reads the latest EMA snapshot once per candle for all strategies.
- Auto-discovery: loads `build_strategy()` from `strategies/options/*.py`.

**Why it exists:**
Strategies stay pure (no IO). The runner does the IO and order handling once.

---

### `runtime/options_trade_notifier.py`

**Purpose:** Adapter for Discord + chart markers + trade ledger.

Key pieces:

- Writes to the trade ledger before any Discord calls.
- Sends one Discord message per position and edits it for add/trim/close.
- Emits chart markers using the strategy's timeframe (defaults to `2M`).
- Rehydrates message state from `storage/message_ids.json` if memory is missing.

**Why it exists:**
Keeps `main.py` small and keeps Discord concerns out of core logic.

---

## 4) Key interfaces (what plugs into what)

### Quote Provider Interface

```bash
class OptionsProvider(Protocol):
    async def fetch_quotes(symbol, expiration) -> List[OptionQuote]
```

Swap Tradier with another provider by implementing this one method.

### Selection Interface

```bash
class ContractSelector(Protocol):
    name: str
    def select(quotes, request) -> Optional[SelectionResult]
```

Add new contract selection methods without changing the cache or executor.

### Execution Interface

Both executors accept:

```bash
OptionOrderRequest(
    symbol, option_type, strike, expiration,
    quantity, side, order_type, limit_price
)
```

Paper and Tradier share the same request structure.

---

### Strategy Runner Hooks

```bash
on_position_opened(position, order_result, reason, timeframe)
on_position_added(position, order_result, reason, timeframe)
on_position_trimmed(position, order_result, reason, timeframe)
on_position_closed(position, order_result, reason, timeframe)
```

Hooks accept an optional timeframe so marker files can be written to the
correct chart (2M/5M/15M).

---

## 5) Common usage patterns

### Pattern A: Just run the quote hub

```bash
python -m options.quote_hub --symbol SPY --expiration 0dte --poll-interval 1 --log-every 5
```

Use this when you want to verify the cache and rate limits.

### Pattern B: Pick a contract from the cache

```bash
snapshot = quote_service.get_snapshot()
result = select_contract(
    quotes=snapshot.values(),
    request=SelectionRequest(
        symbol="SPY",
        option_type="call",
        expiration="20260112",
        underlying_price=690.0,
        max_otm=5.0,
    ),
    selector_name="price-range-otm",
)
```

### Pattern C: Paper buy + sell

```bash
paper = PaperOrderExecutor(quote_service.get_quote)
submit = await paper.submit_option_order(request)
status = await paper.get_order_status(submit.order_id)
```

### Pattern D: Position lifecycle (open/add/trim/close)

```bash
manager = OptionsOrderManager(quote_service, paper_executor)
open_result = await manager.open_position(request, quantity=2, strategy_tag="flag_zone")
await manager.add_to_position(open_result.position_id, quantity=1)
await manager.trim_position(open_result.position_id, quantity=1)
await manager.close_position(open_result.position_id)
```

### Pattern E: Watch position updates

```bash
watcher = PositionWatcher(quote_service, manager.list_positions)
listener_id, queue = watcher.register_queue()
await watcher.start()

updates = await queue.get()
for update in updates:
    print(update.position_id, update.mark_price, update.unrealized_pnl)
```

### Pattern F: Event-driven strategies

```bash
bus = MarketEventBus()
runner = OptionsStrategyRunner(bus, order_manager, strategies, expiration="20260106")
runner.start()

await bus.publish_candle_close(CandleCloseEvent(
    symbol="SPY",
    timeframe="15M",
    candle={"close": 500.0},
    closed_at=datetime.utcnow(),
    source="test",
))
```

### Pattern G: Trade ledger events

Every open/add/trim/close writes a line to:

```bash
storage/options/trade_events.jsonl
```

Each line is JSON (append-only) so analytics can be built later without
relying on Discord or in-memory state.

---

## 6) How to test quickly

### Unit tests

```bash
python -m pytest tests/options_unit_tests
```

### Integration test (synthetic provider + real hub loop)

```bash
python -m pytest tests/options_integration_tests/test_order_flow.py
```

### Integration test (strategy runner + market bus)

```bash
python -m pytest tests/options_integration_tests/test_strategy_runner_flow.py
```

### Live hub smoke test

```bash
python -m options.quote_hub --symbol SPY --expiration 0dte --poll-interval 1 --log-every 5 --run-seconds 30
```

### Offline hub (synthetic quotes)

```bash
python -m options.quote_hub --symbol SPY --expiration 0dte --mock --run-seconds 30
```

### Offline hub (replay recorded data)

1) Record snapshots from live data:

    ```bash
    python -m options.quote_hub --symbol SPY --expiration 0dte --record fixtures/spy_0dte.jsonl --run-seconds 60
    ```

1) Replay offline:

    ```bash
    python -m options.quote_hub --symbol SPY --expiration 0dte --fixture fixtures/spy_0dte.jsonl --run-seconds 30
    ```

**Fixture format (JSONL):**
Each line is a JSON list of quote dicts:

```bash
[{"symbol":"SPY","option_type":"call","strike":690.0,"expiration":"20260112","bid":1.2,"ask":1.3,"last":1.25}]
```

---

## 7) Design principles used here

- **Decoupled:** cache, selection, and execution are independent.
- **Pluggable:** providers and selectors can be swapped.
- **Simple defaults:** a single selector and a simple paper executor.
- **Low API usage:** one chain poll feeds all consumers.
- **Discord is display-only:** ledger is the source of truth.

---

## 8) FAQ / future reminders

**Q: Why not call Tradier from every order?**  
Because it wastes API calls and risks rate limits. The cache is safer and faster.

**Q: Can we use non-0DTE?**  
Yes. Pass any expiration date. `quote_hub.py` accepts `YYYY-MM-DD` or `YYYYMMDD`.

**Q: How do we add a new selector?**  
Create a class with `name` + `select()`, then register it in `SelectorRegistry`.

**Q: How do we add a new provider?**  
Implement `fetch_quotes()` and pass it into `OptionQuoteService`.

---

## 9) Current limitations

- Paper execution does not model latency, slippage, or partial fills.
- Quote cache is single-symbol, single-expiration per service instance.
- Trade ledger is not yet summarized into daily analytics (JSONL only).
- Position watcher is not wired into runtime yet.

---

## 10) Next steps (optional)

- Add daily analytics from `storage/options/trade_events.jsonl`.
- Wire `PositionWatcher` into runtime for live P&L streaming.
- Add selection strategies for tighter spreads or IV filters.
