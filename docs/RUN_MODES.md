# Run modes

## Current implementation

The server currently starts with `api.is_live = True`.

Live mode rejects bars whose timestamps differ from wall-clock UTC by more than
`MAX_LIVE_BAR_DRIFT_SECONDS`. It is suitable only for current data.

## Required before Level 3

Introduce one explicit configuration value with these modes:

- `BACKTEST`: deterministic offline processing; no external sends.
- `PLAYBACK`: historical timestamps allowed; clearly labelled simulated output.
- `PAPER_LIVE`: current market data with NinjaTrader Sim101.
- `LIVE`: reserved and disabled until formally approved.

No implicit boolean combination should decide trading mode.

