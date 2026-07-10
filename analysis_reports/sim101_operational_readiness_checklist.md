\# Sim101 Operational Readiness Checklist



\## Purpose



Confirm that BIUMOLO is ready for a controlled PAPER/Sim101 session without enabling Live trading.



\## Mandatory Conditions



\- \[ ] `RUN\_MODE=PAPER`

\- \[ ] `TRADING\_ACCOUNT=Sim101`

\- \[ ] `ENABLE\_TRADING=true`

\- \[ ] `LIVE\_TRADING\_APPROVED=false`

\- \[ ] `TELEGRAM\_ENABLED=false`

\- \[ ] Operational preflight passes

\- \[ ] Non-dispatching dry run passes

\- \[ ] Controlled dry run evidence exists

\- \[ ] Controlled evidence reports `dispatch\_attempted=false`

\- \[ ] Controlled evidence reports `orders\_sent=0`

\- \[ ] Controlled evidence reports `websocket\_connected=false`

\- \[ ] Controlled evidence reports `telegram\_connected=false`



\## Command



```powershell

python tools/sim101\_readiness.py

```



\## PASS Condition



```text

SIM101 READINESS: PASS

```



\## FAIL Condition



Any failed check means:



```text

NO-GO FOR CONTROLLED PAPER SESSION

```



\## Safety Boundary



This readiness check:



\- does not start the server

\- does not open WebSocket

\- does not connect NinjaTrader

\- does not send signals

\- does not send orders

\- does not modify `.env`

\- does not authorize Live trading

