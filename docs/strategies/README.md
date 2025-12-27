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
