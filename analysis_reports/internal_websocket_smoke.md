# Controlled Internal WebSocket Smoke Test

## Purpose

Validate the local FastAPI `/ws` endpoint using a harmless JSON message.

## Scope

The smoke test:

- starts the server on `127.0.0.1`
- connects only to `/ws`
- sends one inert JSON message
- expects exactly `OK`
- closes the WebSocket
- stops the server

It does not use:

- `/stream`
- `/send_signal`
- NinjaTrader
- Telegram
- the trading pipeline

## Safe Environment

- `RUN_MODE=PLAYBACK`
- `ENABLE_TRADING=false`
- `TRADING_ACCOUNT=playback`
- `TELEGRAM_ENABLED=false`
- `LIVE_TRADING_APPROVED=false`

## Safety Boundary

The report must preserve:

- `dispatch_attempted=false`
- `orders_sent=0`
- `stream_connected=false`
- `ninjatrader_connected=false`
- `telegram_connected=false`
