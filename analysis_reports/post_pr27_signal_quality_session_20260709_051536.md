# Post-PR27 Signal Quality Audit

## Source

- Session dir: `logs\sessions\20260709_051536`
- Mode: read-only artifact parser

## Metrics

- `total_snapshots`: 3287
- `pipeline_decisions`: 3287
- `real_generated_signals`: 34
- `shadow_unlocks`: 943
- `dispatch_events`: 0
- `telegram_events`: 0

## Artifact Presence

- `signal_engine_full_path_snapshots.jsonl`: True
- `pipeline_decisions.jsonl`: True
- `dispatch_events.jsonl`: True
- `telegram_events.jsonl`: True
- `missing_artifacts`: []

## Build Signal Reasons

| reason | count |
| --- | ---: |
| valid_entry_failed | 3078 |
| no_swing_no_scalper | 90 |
| delta_filters_failed | 71 |
| scalper_generated | 30 |
| timing_invalid | 14 |
| swing_generated | 4 |

## Valid Entry Reasons

| reason | count |
| --- | ---: |
| missing_displacement | 1838 |
| mitigation_light_true | 943 |
| missing_momentum | 280 |
| entry_filters_passed | 209 |
| fake_displacement_true | 17 |

## Terminal Reasons

| reason | count |
| --- | ---: |
| missing_displacement | 1838 |
| mitigation_light_true | 943 |
| missing_momentum | 280 |
| entry_filters_passed | 175 |
| scalper_generated | 30 |
| fake_displacement_true | 17 |
| swing_generated | 4 |

## Pipeline Decision Reasons

| reason | count |
| --- | ---: |
| no_final_signal | 3275 |
| ok | 12 |

## Missing Fields

| reason | count |
| --- | ---: |
| snapshot.micro.ob | 2564 |

## Real Output Samples

- `20260709_051536|1780460940.0` reason=`scalper_generated` price=`30720.25` missing=[]
- `20260709_051536|1780463700.0` reason=`scalper_generated` price=`30713.75` missing=[]
- `20260709_051536|1780469820.0` reason=`scalper_generated` price=`30696.25` missing=[]
- `20260709_051536|1780471440.0` reason=`scalper_generated` price=`30711.5` missing=[]
- `20260709_051536|1780473840.0` reason=`scalper_generated` price=`30715.0` missing=[]
- `20260709_051536|1780475760.0` reason=`scalper_generated` price=`30730.25` missing=[]
- `20260709_051536|1780478220.0` reason=`scalper_generated` price=`30750.0` missing=[]
- `20260709_051536|1780479600.0` reason=`scalper_generated` price=`30761.5` missing=[]
- `20260709_051536|1780484280.0` reason=`scalper_generated` price=`30758.25` missing=[]
- `20260709_051536|1780508340.0` reason=`scalper_generated` price=`30585.75` missing=[]
- `20260709_051536|1780530960.0` reason=`scalper_generated` price=`30408.75` missing=[]
- `20260709_051536|1780537440.0` reason=`scalper_generated` price=`30481.5` missing=[]
- `20260709_051536|1780537860.0` reason=`scalper_generated` price=`30475.0` missing=[]
- `20260709_051536|1780540680.0` reason=`scalper_generated` price=`30388.75` missing=[]
- `20260709_051536|1780541580.0` reason=`scalper_generated` price=`30426.5` missing=[]
- `20260709_051536|1780546620.0` reason=`scalper_generated` price=`30493.75` missing=[]
- `20260709_051536|1780547820.0` reason=`scalper_generated` price=`30497.5` missing=[]
- `20260709_051536|1780549140.0` reason=`scalper_generated` price=`30493.0` missing=[]
- `20260709_051536|1780552140.0` reason=`scalper_generated` price=`30476.5` missing=[]
- `20260709_051536|1780553820.0` reason=`scalper_generated` price=`30480.75` missing=[]
- `20260709_051536|1780554660.0` reason=`scalper_generated` price=`30479.0` missing=[]
- `20260709_051536|1780555560.0` reason=`scalper_generated` price=`30509.25` missing=[]
- `20260709_051536|1780558680.0` reason=`scalper_generated` price=`30518.25` missing=[]
- `20260709_051536|1780562820.0` reason=`scalper_generated` price=`30366.25` missing=[]
- `20260709_051536|1780567080.0` reason=`scalper_generated` price=`30337.0` missing=[]

## Shadow Unlock Samples

- `20260709_051536|1780459980.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780460280.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780460460.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']
- `20260709_051536|1780460580.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780460700.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780460760.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780461300.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']
- `20260709_051536|1780461540.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780461660.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']
- `20260709_051536|1780462200.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780462440.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780462860.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780463280.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780463460.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']
- `20260709_051536|1780464180.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780464240.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780464300.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']
- `20260709_051536|1780464540.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']
- `20260709_051536|1780464660.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780464960.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780465140.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780465200.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780465260.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']
- `20260709_051536|1780465800.0` terminal_reason=`mitigation_light_true` missing=[]
- `20260709_051536|1780465920.0` terminal_reason=`mitigation_light_true` missing=['snapshot.micro.ob']

## Classification

- `safety`: PASS
- `signal_quality_review`: REQUIRED
- `shadow_unlock_review`: REQUIRED
- `operational_authorization`: NO_GO

## Interpretation Guards

- real_generated_signals are internal SignalEngine outputs, not orders
- shadow_unlocks are research counters, not V2 activation approval
- dispatch_events and telegram_events must remain zero for this audit
- missing dispatch/telegram artifacts mean absence is unconfirmed
- this tool is read-only and does not run the pipeline
