\# Pre-Sim101 Configuration And Risk Checklist



\## Objective



Define the configuration, risk-control, kill-switch, and rollback checks required before any BIUMOLO Sim101 validation can be considered.



\## Current Decision



Status: NO-GO for Sim101 activation.



Reason: PR31 defined the readiness gate, but configuration and risk controls have not yet been validated as evidence.



\## Scope



This checklist is documentation and audit-only.



It does not:



\- change `.env`

\- change runtime mode

\- enable trading

\- change account routing

\- change risk limits

\- start Sim101

\- start Live

\- call dispatch

\- call Telegram

\- open WebSockets

\- modify CORE, SignalEngine, RiskEngine, PipelineLivePRO, or execution logic



\## Required Configuration Evidence



Before any Sim101 test, record and review:



| Item | Required State | Evidence Required | Status |

| --- | --- | --- | --- |

| `RUN\_MODE` | Not `LIVE` | `.env` review or sanitized config snapshot | PENDING |

| `EnableTrading` | Explicitly reviewed | `.env` review or runtime config log | PENDING |

| `TRADING\_ACCOUNT` | Sim101 only | `.env` review and platform confirmation | PENDING |

| Runtime guard | Blocks unsafe modes | focused guard test or runtime log | PENDING |

| Telegram | Known enabled/disabled state | config review and event artifact | PENDING |

| WebSocket/server side effects | Known state | startup/runtime log review | PENDING |

| Dispatch path | Bounded and auditable | code/config review and artifact expectation | PENDING |



\## Required Risk-Control Evidence



Before any Sim101 test, define and validate:



| Risk Control | Required Evidence | Status |

| --- | --- | --- |

| Maximum position size | documented cap | PENDING |

| Maximum daily loss | documented cap | PENDING |

| Maximum trades per session | documented cap | PENDING |

| Allowed instruments | explicit list | PENDING |

| Allowed session/time window | explicit range | PENDING |

| Stop-loss behavior | expected behavior documented | PENDING |

| Take-profit behavior | expected behavior documented | PENDING |

| Rejection behavior | risk rejection artifact or test | PENDING |

| Abnormal data handling | expected safe behavior documented | PENDING |

| Duplicate signal handling | expected safe behavior documented | PENDING |



\## Kill-Switch Requirements



A Sim101 test is not allowed until the operator can stop the system quickly and prove that stopping worked.



Required evidence:



\- exact manual stop command or procedure

\- expected console/runtime confirmation

\- expected artifact after stop

\- confirmation that no further dispatch occurs after stop

\- human operator assigned during the test



Status: PENDING



\## Rollback Requirements



Before any Sim101 validation:



\- branch and commit must be recorded

\- `.env` state must be recorded

\- session start time must be recorded

\- rollback path must be defined

\- archive location for artifacts must be defined

\- criteria for abandoning the test must be defined



Status: PENDING



\## Pre-Sim101 NO-GO Conditions



Do not proceed if any are true:



\- workspace is dirty

\- branch is not `main`

\- latest `main` is not pulled

\- `.env` is unclear

\- account is not confirmed as Sim101

\- runtime guard is not verified

\- risk caps are undocumented

\- kill-switch is untested

\- rollback is undefined

\- artifact expectations are missing

\- human approval is missing



\## Required Human Approval



Before any Sim101 action, human approval must explicitly confirm:



\- account

\- runtime mode

\- trading enablement

\- maximum exposure

\- max loss

\- test duration

\- stop conditions

\- rollback path

\- artifact review plan



\## Current Recommendation



Remain in PLAYBACK audit-only.



Next safe work is to fill this checklist with observed evidence before any Sim101 activation is considered.

