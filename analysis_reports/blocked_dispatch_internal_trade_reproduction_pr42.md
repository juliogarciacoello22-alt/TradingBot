\# Blocked Dispatch Internal Trade Reproduction PR42



\## Objective



Reproduce and document whether a blocked dispatch can still open an internal trade state.



\## Scope



Test and evidence only.



This PR does not:



\- change runtime behavior

\- change dispatch behavior

\- change configuration

\- enable Sim101

\- enable live trading

\- modify risk thresholds

\- modify account routing



\## Confirmed Behavior



The focused process-level test reproduced the following sequence:



1\. A valid final signal is generated.

2\. `\_dispatch\_signal(final\_signal)` returns a blocked authorization result.

3\. The result contains:

&#x20;  - `allowed=false`

&#x20;  - `reason=enable\_trading\_disabled`

4\. `exit\_engine.open\_from\_signal(final\_signal)` is still called.



\## Observed Output



The pipeline also prints:



`INSTITUTIONAL SIGNAL SENT TO TELEGRAM / NINJATRADER`



even though the simulated dispatch result is blocked.



\## Classification



External delivery bypass: NOT PROVEN.



Internal trade-state desynchronization: CONFIRMED.



\## Risk



BIUMOLO may internally represent a trade as open even when runtime authorization blocks external delivery.



This can create inconsistency between:



\- runtime authorization

\- external delivery

\- internal exit management

\- logs and operator expectations



\## Test Status



\- `\_dispatch\_signal()` isolation test: PASS

\- full `process()` blocked-dispatch test: EXPECTED FAILURE



The expected failure is intentionally retained as regression evidence until the runtime logic is corrected.



\## Decision



Sim101 remains NO-GO.



\## Required Next Change



Update `PipelineLivePRO` so that `exit\_engine.open\_from\_signal()` runs only after dispatch authorization returns `allowed=true`.



A follow-up PR must remove the expected-failure marker and make the regression test pass.
