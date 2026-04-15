# Trigger Gate Observable Summary (dc6d9388-2bd3-4f61-88ed-a7eea7491f3c)

## Step-level
- total steps: `288`
- steps with attempts: `244`
- total decision attempts: `542`
- total events emitted: `6`
- overall emit/attempt: `0.0111`
- median(step emit/attempt | attempts>0): `0.0000`
- mean(step emit/attempt | attempts>0): `0.0123`
- histogram(all steps): `{'0': 284, '(0.5,1.0]': 2, '(0.25,0.5]': 2}`
- histogram(steps with attempts): `{'0': 240, '(0.5,1.0]': 2, '(0.25,0.5]': 2}`

## Forced vs Non-forced
- forced attempts/events: `9/6` (rate `0.6667`)
- non-forced attempts/events: `533/0` (rate `0.0000`)

## Important limitation
- Current DB schema does **not** persist per-attempt `p_negative_interval/p_positive_interval` for non-emitted attempts.
- So full probability distribution for all 542 attempts cannot be reconstructed post hoc from DB.
- `trigger_gate_event_prob_samples_*.csv` contains probabilities only for emitted events from `artifacts.json`.