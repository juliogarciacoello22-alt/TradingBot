# Sim101 Operational Readiness Checklist

## Purpose

Confirm that BIUMOLO is ready for a controlled PAPER/Sim101 session without enabling Live trading.

## Mandatory Conditions

- [ ] `RUN_MODE=PAPER`
- [ ] `TRADING_ACCOUNT=Sim101`
- [ ] `ENABLE_TRADING=true`
- [ ] `LIVE_TRADING_APPROVED=false`
- [ ] `TELEGRAM_ENABLED=false`
- [ ] Operational preflight passes
- [ ] Non-dispatching dry run passes
- [ ] Controlled dry run evidence exists
- [ ] Controlled evidence reports `dispatch_attempted=false`
- [ ] Controlled evidence reports `orders_sent=0`
- [ ] Controlled evidence reports `websocket_connected=false`
- [ ] Controlled evidence reports `telegram_connected=false`

## Command

```powershell
python tools/sim101_readiness.py
```

## PASS Condition

```text
SIM101 READINESS: PASS
```

## FAIL Condition

Any failed check means:

```text
NO-GO FOR CONTROLLED PAPER SESSION
```

## Safety Boundary

This readiness check:

- does not start the server
- does not open WebSocket
- does not connect NinjaTrader
- does not send signals
- does not send orders
- does not modify `.env`
- does not authorize Live trading