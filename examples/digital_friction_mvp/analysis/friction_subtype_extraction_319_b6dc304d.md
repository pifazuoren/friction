# Friction Subtype Extraction (319 Candidates, b6dc304d)

## 1) Purpose

Based on the validated summary statistics:

- universe: `1547` actions (6 behavior classes)
- digital-hit pool: `319` (`action OR status`)

This extraction builds a **stratified 319-candidate pool** and classifies each row into finer friction subtypes to support scenario expansion.

## 2) Input files

- `examples/digital_friction_mvp/analysis/step_actions_b6dc304d_reclass_coarse_long.csv`
- `examples/digital_friction_mvp/analysis/explicit_tech_action_status_by_behavior_class_b6dc304d.csv`
- `examples/digital_friction_mvp/analysis/explicit_tech_status_only_examples_b6dc304d.csv`

## 3) Sampling method (important)

Because the strict hit summary is aggregated by class (not row-level), this run uses:

1. fixed class quotas from `tech_action_or_status`:
   - 放松与情绪调节 `64`
   - 购物采购 `75`
   - 出行移动 `47`
   - 数字设备与账号操作 `104`
   - 社交沟通 `24`
   - 工作任务 `5`
2. token-score ranking within each class
3. top-N selection per class to form exactly `319` rows

So this is a **quota-aligned extraction sample** for subtype discovery.

## 4) Output files

- detailed sampled rows:
  - `examples/digital_friction_mvp/analysis/sampled_digital_candidates_319_b6dc304d.csv`
- subtype summary:
  - `examples/digital_friction_mvp/analysis/sampled_digital_candidates_319_subtype_summary_b6dc304d.csv`
- subtype × behavior class:
  - `examples/digital_friction_mvp/analysis/sampled_digital_candidates_319_subtype_by_class_b6dc304d.csv`

## 5) Extracted subtype distribution (N=319)

- `app_update_permission`: `142` (`44.51%`)
- `ecommerce_order_flow`: `80` (`25.08%`)
- `social_contact_coordination`: `73` (`22.88%`)
- `account_auth_security`: `14` (`4.39%`)
- `notification_risk_interrupt`: `10` (`3.13%`)

## 6) Recommended scenario expansion

### High priority

- `app_update_permission`
- `ecommerce_order_flow`
- `social_contact_coordination`

### Medium priority

- `account_auth_security` (can reuse/merge with existing `login_captcha` or split into maintenance vs login)
- `notification_risk_interrupt` (can merge into `digital_general` if you want fewer classes)

## 7) Suggested minimal migration from current taxonomy

- keep existing:
  - `payment_transfer`, `ride_hailing`, `medical_appointment`, `gov_service`
- keep and strengthen:
  - `social_contact`, `ecommerce_order`, `digital_general`
- optional split from `digital_general`:
  - `app_update_permission`
  - `notification_risk_interrupt`
- optional split from `login_captcha`:
  - `account_auth_security`

This gives a controlled path from the current expanded set to a more evidence-driven set.

