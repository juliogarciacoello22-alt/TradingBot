\# Alternate Dispatch Path Audit PR41



\## Confirmed



\- `server.py` routes manual HTTP and WebSocket signals through `API.send\_signal()`.

\- `PipelineLivePRO.\_dispatch\_signal()` routes delivery through `API.send\_signal()`.

\- No direct call to `\_send\_to\_ninjatrader()` or `\_send\_to\_telegram()` was found outside `API.send\_signal()`.

\- PR40 proves blocked permission prevents both external delivery methods.



\## Finding A — Legacy Backend Async Call



`core/backend.py` calls the async method `api.send\_signal()` without awaiting or scheduling the returned coroutine.



Classification: INCONSISTENT / REQUIRES TEST.



This does not currently demonstrate a runtime-guard bypass. It may instead mean that the legacy backend path does not execute delivery reliably.



\## Finding B — Internal Trade State Before Authorization Result



`core/pipeline\_live\_pro.py` schedules `\_dispatch\_signal(final\_signal)` and immediately calls `exit\_engine.open\_from\_signal(final\_signal)`.



`core/backend.py` follows a similar sequence.



Classification: PRE-SIM101 BLOCKER.



The external dispatch may be blocked while the internal exit engine still records an open trade.



\## Current Decision



\- External runtime guard: PROVEN FOR API DELIVERY.

\- Alternate external bypass: NOT FOUND IN CURRENT SEARCH.

\- Internal state synchronization: NOT PROVEN.

\- Sim101: NO-GO.



\## Required Next Test



Add a focused test proving that a blocked runtime authorization cannot open an internal trade in `ExitEngine`.

