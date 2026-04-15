# Experiment Analysis (dc6d9388-2bd3-4f61-88ed-a7eea7491f3c)

- exp_name: `digital_friction_r7_statusgate_20260301_233847`
- status: `2`
- end_time: day `3` at tick `20701`

## Core Funnel
- steps: `288`
- agent count observed: `34`
- agent-step slots: `1728`
- decision attempts: `542` (31.37% of slots)
- events emitted: `6` (1.11% of attempts; 0.35% of slots)
- no_event after decision: `536`
- pre-match miss: `1238` (71.64% of slots)
- scenario skip: `1186` (68.63% of slots)

## Status Gate (Second Gate)
- status gate attempted: `2` (0.16% of pre-match misses)
- status gate hit: `0`
- status gate no-anchor: `2`
- status gate low-score: `0`
- status gate ambiguous: `0`

## Digital Exposure & Supply
- digital exposure: `222` (12.85% of slots)
- from action/status/intention/signal: `99` / `81` / `167` / `110`
- supply chain seeded->surfaced->completed: `24 -> 56 -> 23` (complete/surfaced 41.07%)

## Stage Summary
- steady: attempts `175`, events `2`, pre_match_miss `411`, status_gate `2/0`
- shock: attempts `213`, events `2`, pre_match_miss `389`, status_gate `0/0`
- recovery: attempts `154`, events `2`, pre_match_miss `438`, status_gate `0/0`

## Event Composition
- scenarios: {'info_ad_click': 2, 'ride_hailing': 3, 'payment_transfer': 1}
- outcomes: {'positive': 5, 'negative': 1}
- psych steady: trust `46.05`, helplessness `38.02`, avoidance `56.33`
- psych shock: trust `42.23`, helplessness `38.84`, avoidance `58.12`
- psych recovery: trust `43.11`, helplessness `37.11`, avoidance `62.76`

## Action Structure
- meal: `617` (35.71%)
- other: `562` (32.52%)
- sleep: `472` (27.31%)
- digital: `39` (2.26%)
- mobility: `38` (2.20%)
- explicit tech mention (action+status broad keywords): `463` / `1728` (26.79%)
- top actions:
  - Clean up after eating: 33
  - Enjoy the meal: 18
  - Ensure a comfortable sleeping environment: 16
  - Serve the meal: 15
  - Lie down in bed: 15
  - Cook the meal: 14
  - Enjoy the meal at home: 14
  - Prepare a comfortable sleeping environment: 12
  - Ensure a comfortable sleep environment: 11
  - Relax and prepare for sleep: 11