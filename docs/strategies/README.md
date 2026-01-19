# Strategies — Registry & Contracts

StratForge can run multiple strategies concurrently over one symbol. A strategy reads shared state (latest price, candles, objects) and emits **orders** and/or **annotations** (markers/flags) that the UI and storage can render.

## Built‑in examples

* **Flag Zone Strategy** — Detects supply/demand zones and adaptive flags.
* **Momentum** — Breakout/breakdown with EMA/band filters.
* **Trend** — Pullback entries aligned with higher‑TF bias.
* **Mean Reversion** — Reversion bands; small size near extremes.

### Strategy contract (suggested)

```python
class Strategy:
    def on_init(self, cfg, shared_state):
        ...
    def on_candle(self, candle_df_slice, objects_df_slice):
        ...  # may emit orders, markers, flags
    def on_close(self):
        ...
```

* **Pure inputs**: strategies never write to storage directly; they emit events via a mediator (keeps storage append‑only and testable).
* **Determinism**: prefer using only data up to the closed candle.
* **Telemetry**: log decisions for replay tests.

### See also

* Storage system: `docs/data/storage-system.md`
* Viewport API: `docs/api/storage-viewport.md`

## Options exit rules (profit targets)

Reusable profit-target logic lives in `strategies/options/exit_rules.py`. Use it inside any options strategy
to keep trims/closes consistent and easy to test.

Example:

```python
from strategies.options.exit_rules import ProfitTargetPlan, ProfitTargetStep

class MyOptionsStrategy:
    name = "my-strategy"

    def __init__(self, *, timeframe="15M"):
        self.timeframe = timeframe
        self.exit_plan = ProfitTargetPlan([
            ProfitTargetStep(target_pct=100.0, action="trim", fraction=0.5),
            ProfitTargetStep(target_pct=200.0, action="close"),
        ])

    def on_position_update(self, updates):
        return self.exit_plan.evaluate(updates, timeframe=self.timeframe)
```

Notes:

* `fraction` trims a percent of the open contracts (rounded to at least 1).
* `quantity` trims a fixed number of contracts.
* `close` ignores quantity and exits the full position.
