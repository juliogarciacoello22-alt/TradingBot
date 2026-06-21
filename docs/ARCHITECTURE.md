# Architecture

```text
NinjaTrader closed 1m bar
        |
        v
FastAPI /stream WebSocket
        |
        v
live timestamp validator -> Feed -> TimeframeLoader
        |
        v
microstructure / context / timing / forecast / risk
        |
        v
SignalEngine -> ExecutionEngine -> deduplication
        |
        +----> NinjaTrader signal / chart arrow
        +----> Telegram
```

`server.py` owns transport. `core/pipeline_live_pro.py` is the current live
orchestrator. Engines under `core/` should remain deterministic and must not
perform transport side effects directly.

Legacy engines and audit scripts remain in place for baseline preservation.
They must not be removed or reorganized until regression tests identify the
production dependency graph.

