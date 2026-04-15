# 本次实验分析（1a60ca93）

## 1) 总体结论
- attempts：`134`
- emitted：`37`（`27.6%`）
- outcome：`positive=20`，`negative=17`，`no_event=97`
- 总体场景对齐（scenario_aligned）：`102/134` = `76.1%`

## 2) 按匹配来源（source）
- `llm_primary`：attempts `91`（`67.9%`），emitted `28`（`30.8%`），对齐 `62/91`（`68.1%`），conf(mean/median)=`0.887/0.900`
- `rule_fallback`：attempts `33`（`24.6%`），emitted `8`（`24.2%`），对齐 `33/33`（`100.0%`），conf(mean/median)=`0.339/0.500`
- `random_fallback`：attempts `10`（`7.5%`），emitted `1`（`10.0%`），对齐 `7/10`（`70.0%`），conf(mean/median)=`0.080/0.000`

## 3) LLM/Gate 状态
- llm_match_status：`ok=93`，`low_confidence=23`，`non_digital=14`，`parse_failed=4`
- 说明：`low_confidence/non_digital/parse_failed` 这三类会推高 fallback 占比，并降低 llm_primary 的纯净度。

## 4) 场景分布（Top 10）
- `digital_general`：`70`（`52.2%`），emitted `20`（`28.6%`），对齐 `42/70`（`60.0%`），source=(llm_primary:67, random_fallback:1, rule_fallback:2)
- `social_contact_coordination`：`20`（`14.9%`），emitted `4`（`20.0%`），对齐 `19/20`（`95.0%`），source=(rule_fallback:15, llm_primary:4, random_fallback:1)
- `payment_transfer`：`12`（`9.0%`），emitted `2`（`16.7%`），对齐 `11/12`（`91.7%`），source=(random_fallback:1, rule_fallback:9, llm_primary:2)
- `ecommerce_order_flow`：`10`（`7.5%`），emitted `4`（`40.0%`），对齐 `9/10`（`90.0%`），source=(llm_primary:10)
- `login_captcha`：`7`（`5.2%`），emitted `2`（`28.6%`），对齐 `7/7`（`100.0%`），source=(llm_primary:7)
- `app_update_permission`：`6`（`4.5%`），emitted `1`（`16.7%`），对齐 `6/6`（`100.0%`），source=(random_fallback:6)
- `account_auth_security`：`4`（`3.0%`），emitted `2`（`50.0%`），对齐 `4/4`（`100.0%`），source=(rule_fallback:4)
- `ride_hailing`：`3`（`2.2%`），emitted `2`（`66.7%`），对齐 `3/3`（`100.0%`），source=(rule_fallback:3)
- `info_ad_click`：`1`（`0.7%`），emitted `0`（`0.0%`），对齐 `0/1`（`0.0%`），source=(random_fallback:1)
- `gov_service`：`1`（`0.7%`），emitted `0`（`0.0%`），对齐 `1/1`（`100.0%`），source=(llm_primary:1)

## 5) 分阶段表现
- `steady`：attempts `66`，emitted `17`（`25.8%`），`negative=10`，`positive=7`，`total_event_prob均值=0.2140`，`hazard均值=0.2365`
- `shock`：attempts `32`，emitted `10`（`31.2%`），`negative=6`，`positive=4`，`total_event_prob均值=0.3820`，`hazard均值=0.4060`
- `recovery`：attempts `36`，emitted `10`（`27.8%`），`negative=1`，`positive=9`，`total_event_prob均值=0.2576`，`hazard均值=0.2732`

## 6) 按天（day）
- day `0`：attempts `35`，emitted `11`（`31.4%`），stage=(steady:35)
- day `1`：attempts `28`，emitted `5`（`17.9%`），stage=(steady:28)
- day `2`：attempts `22`，emitted `6`（`27.3%`），stage=(steady:3, shock:19)
- day `3`：attempts `9`，emitted `4`（`44.4%`），stage=(shock:9)
- day `4`：attempts `18`，emitted `6`（`33.3%`），stage=(shock:4, recovery:14)
- day `5`：attempts `18`，emitted `4`（`22.2%`），stage=(recovery:18)
- day `6`：attempts `4`，emitted `1`（`25.0%`），stage=(recovery:4)

## 7) 数字信号覆盖
- `digital_exposure`：全体 `134/134`（`100.0%`），在 emitted 中 `37/37`（`100.0%`）
- `digital_from_action`：全体 `110/134`（`82.1%`），在 emitted 中 `29/37`（`78.4%`）
- `digital_from_status`：全体 `90/134`（`67.2%`），在 emitted 中 `24/37`（`64.9%`）
- `digital_from_intention`：全体 `132/134`（`98.5%`），在 emitted 中 `36/37`（`97.3%`）
- `digital_from_signal`：全体 `0/134`（`0.0%`），在 emitted 中 `0/37`（`0.0%`）

## 8) 关键数值对比（emitted vs no_event）
- `total_event_prob`：all `0.2658`，emitted `0.3188`，no_event `0.2456`
- `hazard_p_total`：all `0.2868`，emitted `0.3109`，no_event `0.2776`
- `p_negative_interval`：all `0.1116`，emitted `0.1059`，no_event `0.1138`
- `p_positive_interval`：all `0.1752`，emitted `0.2050`，no_event `0.1639`
- `step_failure_pressure`：all `0.2668`，emitted `0.2027`，no_event `0.2912`
- `step_success_support`：all `0.8806`，emitted `0.9730`，no_event `0.8454`

## 9) Stage Explanation（原因聚合）
- `steady`：records `6`，events `17`，top_primary=(recent_step_success_supports_positive:7, low_trust_amplified_negative:7, step_failure_under_friction:3)，top_negative=(digital_intention_signal:9, recent_success:7, digital_action_signal:6)，top_positive=(recent_success:7, digital_intention_signal:7, match_llm_primary:7)
- `shock`：records `6`，events `10`，top_primary=(recent_step_success_supports_positive:4, low_trust_amplified_negative:3, high_friction_with_low_buffer:2)，top_negative=(high_friction:6, digital_intention_signal:6, recent_success:5)，top_positive=(high_friction:4, recent_success:4, digital_action_signal:4)
- `recovery`：records `6`，events `10`，top_primary=(recent_step_success_supports_positive:9, no_emitted_events:2, low_trust_amplified_negative:1)，top_negative=(high_support:1, recent_success:1, digital_action_signal:1)，top_positive=(high_support:9, recent_success:9, digital_intention_signal:9)

## 10) llm_primary 错配样例（前10）
- `1a60ca93-0023401-002-0001` | `digital_general` | conf `0.9` | need: safe | step: Review shopping list
- `1a60ca93-0023401-003-0001` | `digital_general` | conf `0.8` | need: safe | step: Review and organize my shopping list
- `1a60ca93-0025201-006-0001` | `digital_general` | conf `0.9` | need: safe | step: Prepare a shopping list based on needs
- `1a60ca93-0041401-005-0005` | `digital_general` | conf `0.9` | need: hungry | step: Retrieve grocery list and review what's available at ho…
- `1a60ca93-0079201-006-0006` | `digital_general` | conf `0.8` | need: safe | step: Check the shopping list to prepare items needed
- `1a60ca93-0118001-001-0007` | `digital_general` | conf `0.9` | need: safe | step: Check my shopping list and ensure it is ready to go
- `1a60ca93-0119801-001-0008` | `digital_general` | conf `0.9` | need: safe | step: Check my shopping list and ensure it is ready to go
- `1a60ca93-0121601-001-0009` | `digital_general` | conf `0.9` | need: safe | step: Check my shopping list and ensure it is ready to go
- `1a60ca93-0123401-001-0010` | `digital_general` | conf `0.9` | need: safe | step: Check my shopping list and ensure it is ready to go
- `1a60ca93-0132401-005-0011` | `digital_general` | conf `0.9` | need: Assist the agent with the authentication process and ad… | step: Prepare a cup of coffee

## 11) 诊断结论（针对本次）
- `llm_primary` 覆盖最高（91/134），但主要错配集中在 `digital_general`，且不少文本只出现“shopping list/生活动作”，缺少强数字锚点。
- `rule_fallback` 对齐率高（100%），说明规则端精度稳定；但它主要承接 `low_confidence/non_digital/parse_failed`，覆盖面受限。
- `shock` 阶段风险值最高（hazard/total_event_prob 均值最高），但 emitted 比 `recovery` 仅略高，说明当前阈值与校准偏保守。
- 全体 `digital_exposure=100%` 且 `digital_from_intention=98.5%`，数字信号主要来自意图字段，`status/action` 的补充贡献相对弱。
