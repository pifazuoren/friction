# Experiment Analysis (b6dc304d)

## Basic
- exp_id: `b6dc304d6ec745cda863687dc915d209`
- name: `digital_friction_r6_20260301_033832`
- status: `2` (2=completed)
- end cursor: day `9`, t `20701.0`
- step count: `864`
- slots (agent-step): `5184`
- active agents per step: `6.0`
- unique parent_id observed: `112`
- id-swapped steps: `744/864` (86.11%)

## Core Funnel
- decision attempts: `1633` (31.50% of slots)
- events emitted: `13` (0.80% of attempts; 0.25% of slots)
- no_event: `1620` (99.20% of attempts)
- pre_match_miss: `3642` (70.25% of slots)
- scenario_skip: `3551` (68.50% of slots)
- skip_fallback_not_triggered: `3551`
- skip_fallback_failed: `0`
- forced_min_attempt: `53`
- exploratory: `38`

## Digital Exposure & Supply
- digital_exposure: `924` (17.82% of slots)
- source split: action `201`, status `197`, intention `483`, signal `693`
- supply seeded/surfaced/completed: `60 / 119 / 59`
- completed/surfaced: `49.58%`
- queue_active(sum): `468`, carryover(sum): `0`, pending_timeout_reset(sum): `0`

## Mobility & LLM
- mobility nudge sent/executed/effective/expired: `177 / 99 / 0 / 13`
- decider llm calls(sum): `952` (1.10/step)
- decider llm errors(parse/budget): `0 / 0 / 0`

## Events
- stage counts: `{'shock': 5, 'recovery': 5, 'steady': 3}`
- scenario counts: `{'ride_hailing': 6, 'info_ad_click': 4, 'payment_transfer': 2, 'medical_appointment': 1}`
- outcome counts: `{'negative': 7, 'positive': 6}`

## Action Categories
- overall: `meal 1651 (31.85%)`, `sleep 1326 (25.58%)`, `mobility 289 (5.57%)`, `digital 58 (1.12%)`, `other 1860 (35.88%)`
- top actions:
  - `Return home from current location`: `79`
  - `Enjoy the meal`: `79`
  - `Clean up after eating`: `53`
  - `Lie down in bed`: `47`
  - `Serve the meal`: `42`
  - `Prepare a comfortable sleeping environment`: `38`
  - `Ensure a comfortable sleeping environment`: `37`
  - `Return to home`: `33`
  - `Return to home from current location`: `30`
  - `Start cooking the meal`: `28`
  - `Clean up after the meal`: `28`
  - `Eat the meal`: `28`