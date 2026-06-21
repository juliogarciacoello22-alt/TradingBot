# Security policy

This repository must remain private.

- Never commit `.env`, Telegram credentials, account identifiers, logs, or raw
  market data.
- Bind Uvicorn to `127.0.0.1` unless remote access has been explicitly secured.
- Do not expose `/stream`, `/ws`, or `/send_signal` to an untrusted network.
- Rotate Telegram credentials immediately if they appear in a commit, log, or
  screenshot.
- Use the NinjaTrader `Sim101` account until offline and forward validation are
  complete.
- Report suspected credential or trading-safety issues privately to the owner.

