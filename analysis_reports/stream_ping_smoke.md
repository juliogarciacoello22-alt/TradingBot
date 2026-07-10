# Controlled Stream Ping Smoke Test

## Purpose

Validate the local `/stream` WebSocket handshake and ping-only path.

## Scope

The smoke test:

- starts the server on `127.0.0.1`
- connects a local smoke client only to `/stream`
- sends exactly `{"ping": true}`
- expects no application response
- closes the WebSocket
- stops the server

It does not send:

- candles
- manual signals
- trading signals
- orders

## Safety Boundary

The report must preserve:

- `stream_client=local_smoke_client`
- `real_ninjatrader_connected=false`
- `dispatch_attempted=false`
- `pipeline_invoked=false`
- `signals_sent=0`
- `orders_sent=0`
- `telegram_connected=false`
