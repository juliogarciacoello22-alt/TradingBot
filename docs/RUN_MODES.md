# Run modes

## Current implementation

Runtime mode is controlled by `RUN_MODE` and synchronized into the API object
with `sync_api_runtime_mode(api)`. Do not assume `api.is_live` is always `True`
at startup.

Current defaults in `.env.example` are:

```text
RUN_MODE=PLAYBACK
EnableTrading=false
TRADING_ACCOUNT=playback
```

Current modes accepted by `core/runtime_guard.py`:

- `PLAYBACK`: historical/playback processing. Dispatch is blocked unless
  `EnableTrading=true` and the account name contains `playback` or `replay`.
- `PAPER_LIVE`: current market data / paper-live processing. Dispatch is
  blocked unless `EnableTrading=true` and the account name contains `sim`
  such as `Sim101`.

Current modes not enabled by `core/runtime_guard.py`:

- `BACKTEST`: invalid run mode in the current runtime guard.
- `LIVE`: invalid run mode in the current runtime guard and not authorized.

`api.is_live` is derived from `RUN_MODE`; it is `True` only for `PAPER_LIVE`.
When `api.is_live` is true, live timestamp validation rejects bars whose
timestamps differ from wall-clock UTC by more than
`MAX_LIVE_BAR_DRIFT_SECONDS`.

`EnableTrading=false` blocks dispatch before sending. This remains the safe
default. Changing `.env`, `RUN_MODE`, `EnableTrading`, account settings, or any
execution path requires explicit human approval.

## Required before Level 3

The intended future mode model remains:

- `BACKTEST`: deterministic offline processing; no external sends.
- `PLAYBACK`: historical timestamps allowed; clearly labelled simulated output.
- `PAPER_LIVE`: current market data with NinjaTrader Sim101.
- `LIVE`: reserved and disabled until formally approved.

No implicit boolean combination should decide trading mode.

BIUMOLO is not authorized for production, real capital, or `LIVE` execution.
Documentation changes do not authorize execution.
