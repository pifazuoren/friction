# Phase 5 Huys & Dayan-Inspired Controllability Plan

## Phase5B Amendment

本文件原先定义 Phase5A 的 `shadow-only controllability audit`。Phase5B 在此基础上增加一个 **controllability-aware gated modulation**，但仍然不新增 sampler，不改 outcome、helplessness、attribution、scope spillover 或 DB schema。

Phase5B 只允许改变：

```text
传入 choose_attempt_strategy(..., precomputed_final_weights=...) 的最终行动概率
```

Phase5B 的当前实施规则：

```text
Low C:
  flatten-only，把 Phase4 pi_final 小幅拉向 uniform policy
  不直接推 seek_help
  不直接推 avoid

High C:
  减少 avoid
  把概率给 Phase4 pi_final / Q_bayes 中更强的 non-avoid action
  不默认转向 attempt_self
```

Phase5B 显式开启：

```bash
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE=gated_modulate
PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD=0.50
PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA=0.25
PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD=0.45
PROTO_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD=0.60
```

Phase5B 只使用：

```text
C_before_event
```

影响当前 action。`C_after_event` 只用于 learning trace 和下一轮/下一天预测，不能影响当前 action。

Low-C flatten-only 规则：

```text
if C_family_before_event < low_c_threshold:
  gamma = max_delta * family_confidence * ((low_c_threshold - C) / low_c_threshold)
  gamma = min(gamma, max_delta)
  pi_after = (1 - gamma) * pi_base + gamma * uniform_policy
```

第一版禁用：

```text
low_c_directional_help_shift_enabled = false
extreme_low_c_avoid_shift_enabled = false
```

High-C reduce-avoid 规则：

```text
if C_family_before_event > high_c_threshold:
  delta = max_delta * family_confidence * ((C - high_c_threshold) / (1 - high_c_threshold))
  delta = min(delta, max_delta, pi_base["avoid"])
  best_nonavoid = argmax(["attempt_self", "seek_help_then_attempt"])
  avoid -= delta
  best_nonavoid += delta
```

`best_nonavoid` 选择优先级：

```text
1. Phase4 pi_final 中更强的 non-avoid action
2. 如果 pi_final 缺失，用 q_bayes 中更强的 non-avoid action
3. 如果二者都缺失，不介入
```

Phase5B 论文口径：

```text
Low controllability attenuates action-preference contrast by flattening the Phase4 policy toward a neutral distribution, while high controllability reduces avoidance in favor of the strongest non-avoid action already supported by the Phase4 policy.
```

## Phase5C Amendment

Phase5C 新增一个 **controllability-centered but action-outcome-grounded** mode：

```bash
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE=control_centered_modulate
```

Phase5C 不删除 Phase4 的 action-outcome posterior。新的主链是：

```text
semantic_v2 pi_ref
-> Bayesian action-outcome posterior / q_bayes / Phase4 pi_final
-> C_before_event controllability diagnostic
-> control-centered modulation
-> choose_attempt_strategy(..., precomputed_final_weights=...)
```

Phase5C 与 Phase5B 共用硬边界：

```text
不新增 sampler
不改 outcome model
不改 helplessness / attribution / scope_spillover update
不改 DB schema
不让 C_family 单独直接选 action
不使用 C_after_event、当前 outcome 或 post-outcome 字段影响当前 action
```

Phase5C 的 low-C 规则从 `uniform` 改为 `pi_ref`：

```text
if mode == control_centered_modulate
and C_family_before_event < low_c_threshold
and family_confidence >= gate_threshold
and pi_ref is valid:
  gamma = max_delta * family_confidence * ((low_c_threshold - C) / low_c_threshold)
  gamma = min(gamma, max_delta)
  pi_after = (1 - gamma) * pi_base + gamma * pi_ref
```

`pi_ref` 必须先显式验证为合法 action distribution，再 normalize；缺失、缺 action、非 finite、负值或总和非正时不进入 low-C shrink，也不回退到 uniform。此时：

```text
modulation_status = reference_policy_unavailable
intervention_applied = false
```

Phase5C 的 high-C 规则继续复用 Phase5B：

```text
reduce avoid -> best non-avoid action
best_nonavoid 仍由 _best_nonavoid_from(...) 决定
不手写第二份 argmax
不默认推 attempt_self
```

新增 audit/analysis 字段：

```text
reference_mix_gamma
control_centered_low_c_target
pi_reference_for_control_centered
```

Phase5C 论文口径：

```text
Action-outcome posterior supplies task-family/action-specific evidence. A Huys-Dayan-inspired controllability trace is the central mediator. The policy is modulated by controllability, while concrete non-avoid preference remains grounded in posterior/semantic evidence.
```

## Summary

本计划包含两个层级：

```text
Phase5A:
  shadow-only controllability audit

Phase5B:
  controllability-aware gated modulation

Phase5C:
  controllability-centered policy modulation
```

Phase5B/Phase5C 都不是替代 Phase4 的 action-choice 主链，而是在已经跑通的 `semantic_v2 + Bayesian gated-lite2` 之上，把 Huys & Dayan-inspired controllability 接成一个 **小幅、证据门控、可审计的 action-probability modulation**。

Phase4 已经负责：

```text
weak neutral prior
-> bounded LLM semantic adjustment
-> Bayesian gated-lite action choice
-> pi_final
-> sampled action
```

Phase5A 只回答一个诊断问题：

```text
在某个 task_family 中，agent 过去的行动是否能可靠地产生有价值、可控的结果？
```

Phase5A 不回答：

```text
agent 当前应该选择哪个 action？
```

所以 Phase5A 保持：

```text
shadow-only controllability audit
```

Phase5B 在这个 shadow substrate 上额外允许改变：

```text
传入 choose_attempt_strategy(..., precomputed_final_weights=...) 的最终行动概率
```

Phase5B 仍不改变：

```text
outcome
helplessness
self_efficacy
attribution
scope_spillover
experience memory
stream memory
interview
DB schema
```

## Claim Boundary

本阶段可以说：

```text
Huys & Dayan-inspired controllability audit
posterior-derived diagnostic controllability score
lightweight controllability trace for LLM social simulation
```

不要说：

```text
full Huys & Dayan Bayesian RL
full Bayesian behavioral control model
generative posterior over environments
multi-step Bayesian RL planning
```

核心边界：

```text
C_family:
  posterior-derived diagnostic controllability score
  来自 task_family + action -> outcome_subtype posterior
  不是完整 environment-level Bayesian posterior

C_global:
  smoothed global controllability trace
  是 family-level diagnostic score 的平滑汇总
  不是 full Bayesian posterior over environments
```

## Relation To Phase4

Phase4 是当前 action-choice 主链：

```text
task appraisal
-> strategy deliberation
-> semantic_v2 reference policy
-> Bayesian gated-lite bounded shift
-> choose_attempt_strategy(..., precomputed_final_weights=pi_final)
-> outcome
```

Phase5 只读已有记忆和审计信息：

```text
proto_bayesian_policy_memory
Phase4 policy audit fields
runtime config
task_family
day
```

Phase5 只写：

```text
payload_json.auxiliary_audit.huys_dayan_lite_controllability
proto_bayesian_controllability_lite_memory
analysis CSV
```

Phase5 不允许把 `C_family` 或 `C_global` 传入：

```text
choose_attempt_strategy
compute_bayesian_policy_shadow
outcome model
helplessness update
attribution update
scope spillover update
```

## Pre/Post Timing Design

为避免信息泄漏，第一版必须同时记录两个时间点。

### C Before Event

`C_before_event` 在当前 action/outcome 发生前计算：

```text
old proto_bayesian_policy_memory
-> C_family_before_event
-> C_global_before_event
```

用途：

```text
no-leakage audit
表示 agent 在当前 event 前可获得的 controllability diagnostic
可用于解释当前 action 前的 shadow belief
```

禁止使用：

```text
current outcome
support_mode
avoid_reason
attribution labels
post_outcome_uncontrollability
helplessness_after
self_efficacy_after
```

### C After Event

`C_after_event` 在当前 outcome 结束、`proto_bayesian_policy_memory` 更新后计算：

```text
updated proto_bayesian_policy_memory
-> C_family_after_event
-> C_global_after_event
-> update proto_bayesian_controllability_lite_memory
```

用途：

```text
learning trace
day/event t -> t+1 lagged prediction
world-level controllability trend
task-family-level controllability trend
```

`C_after_event` 可以包含当前 outcome 的学习结果，但不能用于解释当前 action 前的选择。

## New Runtime Mode

新增 runtime 配置：

```text
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE=off
```

支持值：

```text
off
shadow
```

默认必须是：

```text
off
```

实验时显式开启：

```bash
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE=shadow
```

## New Config Items

在 `examples/digital_friction_mvp/config_runtime.py` 新增：

```text
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE=off
PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K=6
PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES=1
PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT=0.05
PROTO_HUYS_DAYAN_LITE_RHO=1.0
PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE=false
PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY=0.25
PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST=0.25
PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI=0.50
```

Clamp 要求：

```text
confidence_k >= 1
min_action_updates >= 0
global_update_weight in [0.0, 1.0]
rho in [0.0, 1.0]
weights >= 0.0
```

如果三个权重之和不为 1，helper 内部归一化。

## New Fingerprint Keys

在 `examples/digital_friction_mvp/world_runner.py` 的 fingerprint keys 中加入：

```text
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE
PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K
PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES
PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT
PROTO_HUYS_DAYAN_LITE_RHO
PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE
PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY
PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST
PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI
```

## New Derived Memory

在 `examples/digital_friction_mvp/proto/state_schema.py` 新增 status memory：

```text
proto_bayesian_controllability_lite_memory: dict
```

不要复用：

```text
proto_bayesian_policy_memory
proto_bayesian_control_memory
```

原因是三者职责不同：

```text
proto_bayesian_policy_memory:
  task_family + action -> outcome_subtype posterior

proto_bayesian_control_memory:
  旧版总体 C_hat audit

proto_bayesian_controllability_lite_memory:
  从 action-outcome posterior 派生 C_family / C_global
  只作为 derived/audit memory
```

必须明确：

```text
This memory is derived/audit memory and must not be used by Phase5 to drive real behavior.
```

初始 memory：

```json
{
  "version": "huys_dayan_lite_controllability_v1",
  "mode": "shadow",
  "global": {
    "global_controllability_trace": 0.5,
    "confidence": 0.0,
    "evidence_count": 0,
    "last_updated_day": -1
  },
  "families": {}
}
```

每个 family 默认：

```json
{
  "raw_c_family": 0.5,
  "shrunk_c_family": 0.5,
  "family_confidence": 0.0,
  "entropy_control": 0.5,
  "action_contrast_control": 0.5,
  "reward_control_chi_lite": 0.5,
  "reward_achievability": 0.5,
  "reward_action_gain": 0.0,
  "effective_action_count": 0,
  "min_control_action_updates": 0,
  "harmonic_control_action_updates": 0.0,
  "last_updated_day": -1
}
```

如果保留旧式 `alpha_control_high / alpha_control_low` 字段，也只能解释为 trace smoothing internals，不要解释为 full environment posterior。

## New Helper File

新增：

```text
examples/digital_friction_mvp/proto/bayesian_controllability_lite.py
```

只做纯函数计算：

```text
不读 LLM
不访问 DB
不抽样
不改变主策略
不改变 outcome
不改变 psychological state
不改变随机数流
```

建议函数：

```text
build_initial_controllability_lite_memory()
normalize_controllability_lite_memory()
compute_entropy_control()
compute_action_contrast_control()
compute_reward_control_chi_lite()
compute_family_controllability_diagnostic()
compute_huys_dayan_lite_before_event_audit()
compute_huys_dayan_lite_after_event_audit()
update_controllability_lite_shadow_memory()
combine_huys_dayan_lite_audits()
```

可复用 `bayesian_policy_lite.py` 中已有内容：

```text
POLICY_LITE_ACTIONS
POLICY_OUTCOME_SUBTYPES
compute_posterior_predictive_by_action
normalize_bayesian_policy_memory
normalize_utility_profile
outcome_utility_profile
```

如需使用 `_PLAUSIBLE_OUTCOMES_BY_ACTION`，建议改为公开常量：

```text
PLAUSIBLE_OUTCOMES_BY_ACTION
```

或在新 helper 内定义同构常量，避免直接依赖 private name。

## Control-Relevant Actions

主 `C_family` 默认只使用：

```text
attempt_self
seek_help_then_attempt
```

默认排除：

```text
avoid
```

原因：

```text
avoid -> no_attempt
```

这会天然低熵，但这不是 task controllability evidence，而是退出任务。

推荐写入 audit：

```text
avoid can be reported as behavioral separability diagnostic,
but it must not inflate main task controllability.
```

保留 optional diagnostic：

```text
behavioral_action_separability
```

这个可以包含 `avoid`，但不能进入主 `C_family`。

## Coarse Outcome Bins

新增 outcome bin 映射：

```text
success:
  success_self
  success_with_help

controllable_failure:
  failure_after_attempt_low_uncontrollability

uncontrollable_failure:
  failure_after_attempt_mid_uncontrollability
  failure_after_attempt_high_uncontrollability
  failure_even_with_help

dropout:
  abandon_midway

no_task_evidence:
  no_attempt

unknown:
  neutral_unknown
```

说明：

```text
failure_after_attempt_low_uncontrollability 不是 good outcome。
它代表失败但仍保留可学习、可调整的 controllable failure signal。
```

`action_contrast_control` 必须基于 coarse bins 计算，不能直接用原始 subtype。

## Metric 1: Entropy Control

`entropy_control` 只表示 outcome reliability / predictability，不表示 outcome 是否好。

例如：

```text
attempt_self -> 总是 high uncontrollable failure
```

这也是低熵、高 predictability，但不是高价值可控。

所以 `entropy_control` 必须和 `reward_control_chi_lite` 分开解释。

对每个 control-relevant action 计算：

```text
H(a) = -sum_o p(o | f,a) * log p(o | f,a)
H_norm(a) = H(a) / log(|Omega_a|)
entropy_control(a) = 1 - H_norm(a)
```

`Omega_a` 使用该 action 的 plausible outcomes。

family-level：

```text
w_a = update_count(a) / (update_count(a) + confidence_k)

entropy_control(f)
  = weighted_mean_a entropy_control(a)
```

如果有效证据不足：

```text
entropy_control(f) = 0.5
status = insufficient_evidence
```

## Metric 2: Action Contrast Control

先把每个 action 的 posterior 映射为：

```text
p_bin(bin | task_family, action)
```

再计算 pairwise TVD：

```text
TVD(a_i, a_j)
  = 0.5 * sum_b |p_bin(b | a_i) - p_bin(b | a_j)|
```

默认只比较：

```text
attempt_self
seek_help_then_attempt
```

如果某个 action 证据不足：

```text
action_contrast_control = 0.5
status = insufficient_balanced_evidence
```

解释边界：

```text
action_contrast_control 高，说明不同可控行动产生了不同 outcome distribution。
它不单独说明结果好坏。
```

## Metric 3: Reward Control / Chi-Lite

使用当前 utility profile：

```text
shadow_v1
theory_v2
```

先归一化 utility：

```text
U_norm(o) = (U(o) - U_min) / (U_max - U_min)
U_plus(o) = max(U_norm(o), 0)
```

计算：

```text
reward_achievability(f)
  = max_a E[U_plus(o) | f,a]

reward_action_gain(f)
  = max_a E[U_norm(o) | f,a] - min_a E[U_norm(o) | f,a]

reward_control_chi_lite(f)
  = 0.70 * reward_achievability
    + 0.30 * reward_action_gain
```

如果 utility profile 不合法：

```text
fallback to default utility profile
record status in audit
```

## C Family

默认：

```text
C_raw(f)
  = 0.25 * entropy_control(f)
    + 0.25 * action_contrast_control(f)
    + 0.50 * reward_control_chi_lite(f)
```

然后做 shrinkage：

```text
C_family(f)
  = family_confidence * C_raw(f)
    + (1 - family_confidence) * 0.5
```

audit 同时记录：

```text
raw_c_family
shrunk_c_family
family_confidence
```

主分析默认使用：

```text
shrunk_c_family
```

解释边界：

```text
shrunk_c_family 是 posterior-derived diagnostic controllability score。
它不是完整 Bayesian RL controllability posterior。
```

## Confidence

不要用 family 总次数。使用 control-relevant actions 的平衡证据。

```text
n_attempt = update_count(attempt_self)
n_help = update_count(seek_help_then_attempt)

n_eff = 2 * n_attempt * n_help / (n_attempt + n_help + epsilon)

coverage =
  count(action with update_count >= min_action_updates)
  / len(control_relevant_actions)

family_confidence =
  coverage * n_eff / (n_eff + confidence_k)
```

默认：

```text
confidence_k = 6
min_action_updates = 2
```

## C Global

`C_global` 建议解释为：

```text
global_controllability_trace
```

它来自 family-level shadow update。

默认只有当：

```text
family_confidence >= 0.50
```

才更新 global trace。

更新：

```text
w = global_update_weight * family_confidence

global_controllability_trace =
  (1 - w) * previous_global_controllability_trace
  + w * C_family
```

第一版建议：

```text
global_update_weight = 0.05
rho = 1.0
```

如果继续使用 rho：

```text
rho controls trace persistence / decay
```

如果证据不足：

```text
would_update_global = false
reason = family_confidence_below_threshold
```

解释边界：

```text
C_global is a smoothed summary trace over family-level diagnostic scores,
not a generative environment-level Bayesian posterior.
```

## Agent Integration

修改：

```text
examples/digital_friction_mvp/proto/agent.py
```

Phase5A shadow 接入位置：

```text
strategy_deliberation
-> build_semantic_reference_policy
-> compute_bayesian_policy_shadow
-> compute_huys_dayan_lite_before_event_audit
-> choose_attempt_strategy
-> outcome
-> update_bayesian_policy_memory
-> compute_huys_dayan_lite_after_event_audit
-> combine before/after audit
```

Phase5A 要求：

```text
controllability audit 不传入 choose_attempt_strategy
controllability audit 不修改 bayesian_policy_pre_audit
controllability audit 不修改 gated_lite_final_weights
controllability audit 不修改 outcome
controllability audit 不修改 helplessness / attribution / scope spillover
```

Phase5B gated_modulate 接入位置：

```text
strategy_deliberation
-> build_semantic_reference_policy
-> compute_bayesian_policy_shadow
-> compute_huys_dayan_lite_before_event_audit
-> apply_controllability_gated_modulation on Phase4 pi_final
-> choose_attempt_strategy(..., precomputed_final_weights=pi_final_controllability)
-> outcome
-> update_bayesian_policy_memory
-> compute_huys_dayan_lite_after_event_audit
-> combine before/modulation/after audit
```

Phase5B 要求：

```text
只允许 C_before_event 影响当前 action probability
C_after_event 只用于 learning trace / lagged prediction
不覆盖 bayesian_policy_lite.pi_final
真实 sampler 收到 huys_dayan_lite_controllability.pi_final_controllability
不修改 outcome / helplessness / attribution / scope spillover
```

Phase5C control_centered_modulate 接入位置与 Phase5B 相同，但 `apply_controllability_gated_modulation(...)` 额外读取 Phase4 audit 中的 `pi_ref`：

```text
strategy_deliberation
-> build_semantic_reference_policy
-> compute_bayesian_policy_shadow
-> compute_huys_dayan_lite_before_event_audit
-> apply_controllability_gated_modulation(
     pi_base=Phase4 pi_final,
     pi_ref=bayesian_policy_lite.pi_ref
   )
-> choose_attempt_strategy(..., precomputed_final_weights=pi_final_controllability)
```

Phase5C 要求：

```text
gated_modulate 旧行为不变
control_centered_modulate low C shrink toward pi_ref
pi_ref 缺失或非法时 no-op，不隐式 uniform fallback
high C 继续复用 best_nonavoid helper
bayesian_policy_lite.pi_final 保留 Phase4 原样
huys_dayan_lite_controllability.pi_final_controllability 记录真实 sampler weights
```

在 payload 中写入：

```text
payload_json.auxiliary_audit.huys_dayan_lite_controllability
```

## Audit Payload

audit 字段必须包含：

```json
{
  "version": "huys_dayan_lite_controllability_v1",
  "mode": "shadow",
  "enabled": true,
  "task_family": "...",
  "uses_post_outcome_information_for_controllability": false,
  "policy_unchanged": true,
  "state_unchanged": true,
  "outcome_unchanged": true,
  "modulation_family": "none",
  "modulation_status": "disabled",
  "reference_mix_gamma": 0.0,
  "control_centered_low_c_target": "",
  "pi_reference_for_control_centered": {},
  "control_relevant_actions": ["attempt_self", "seek_help_then_attempt"],
  "excluded_actions": {
    "avoid": "no_attempt is behavioral avoidance, not task controllability evidence"
  },
  "before_event": {
    "pre_update": true,
    "update_counts_by_action": {},
    "confidence_by_action": {},
    "entropy_control_by_action": {},
    "entropy_control": 0.5,
    "coarse_posterior_by_action": {},
    "action_contrast_control": 0.5,
    "reward_value_by_action": {},
    "reward_achievability": 0.5,
    "reward_action_gain": 0.0,
    "reward_control_chi_lite": 0.5,
    "raw_c_family": 0.5,
    "family_confidence": 0.0,
    "shrunk_c_family": 0.5,
    "global_controllability_trace": 0.5
  },
  "after_event": {
    "post_update": true,
    "post_update_memory_status": "updated",
    "raw_c_family": 0.5,
    "family_confidence": 0.0,
    "shrunk_c_family": 0.5,
    "global_controllability_trace_before": 0.5,
    "global_controllability_trace_after": 0.5,
    "would_update_global": false,
    "global_update_reason": "family_confidence_below_threshold"
  }
}
```

关键解释：

```text
before_event 用于 no-leakage 和当前 event 前可获得的 diagnostic。
after_event 用于学习轨迹和下一步预测，不用于解释当前 action 前选择。
```

## Post-Outcome Memory Update

当前 outcome 结束后，现有流程继续更新：

```text
proto_bayesian_policy_memory
```

Huys-Dayan-lite memory 可以在 policy memory update 之后做 shadow update：

```text
updated policy memory
-> recompute C_family_after_event
-> update proto_bayesian_controllability_lite_memory
```

但仍然不能影响：

```text
当前 event action
当前 event outcome
当前 event helplessness update
当前 event attribution
当前 event scope spillover
```

## Analysis Script

新增：

```text
examples/digital_friction_mvp/analysis_huys_dayan_lite_controllability.py
```

输入：

```text
--manifest-json
--db-path
--out-dir
```

输出：

```text
huys_dayan_lite_summary_<exp_id>.csv
huys_dayan_lite_by_world_<exp_id>.csv
huys_dayan_lite_by_world_day_<exp_id>.csv
huys_dayan_lite_by_task_family_<exp_id>.csv
huys_dayan_lite_lagged_prediction_<exp_id>.csv
huys_dayan_lite_qc_<exp_id>.csv
```

必须统计：

```text
payload_coverage
uses_post_outcome_information_true_count
mean_c_family_before_event
mean_c_family_after_event
mean_raw_c_family_before_event
mean_raw_c_family_after_event
mean_global_controllability_trace_before_event
mean_global_controllability_trace_after_event
mean_family_confidence
mean_entropy_control
mean_action_contrast_control
mean_reward_control_chi_lite
world-level C differences
day-level C trend
task-family-level C ranking
```

为了和 Phase4 主链对齐，分析脚本还应输出或聚合：

```text
reference_mode
lambda_llm
max_delta
utility_profile
intervention_applied_rate
mean_total_variation_distance
semantic_fallback_rate
rule_fallback_rate
safety_guard_fallback_rate
```

这样可以分析：

```text
C_family 低的时候，Bayesian gated-lite 是否更常介入？
C_family 和 TVD / gate_open / intervention_applied 是否相关？
```

Lagged prediction 第一版至少输出描述性表：

```text
C_family_after_event_day_t_minus_1 vs avoid_rate_day_t
C_family_after_event_day_t_minus_1 vs attempt_rate_day_t
C_family_after_event_day_t_minus_1 vs help_seek_rate_day_t
C_family_after_event_day_t_minus_1 vs helplessness_delta_day_t
C_family_after_event_day_t_minus_1 vs self_efficacy_day_t
C_family_after_event_day_t_minus_1 vs scope_spillover_day_t
```

第一版只需要描述性结果，不必声称因果。

## Expected World Pattern

第一版 sanity expectation：

```text
low_friction_high_assist:
  C_family / global_controllability_trace highest or among highest

high_friction_low_assist:
  C_family / global_controllability_trace lowest

high_friction_high_assist:
  should improve over high_friction_low_assist,
  but does not have to exceed baseline

baseline_low_friction:
  middle / stable reference
```

如果 world pattern 不符合，也不要立刻调参。先检查：

```text
payload coverage
pre/post timing
outcome bin mapping
task-family evidence balance
avoid 是否错误进入 main C_family
utility profile 是否与 theory_v2 一致
```

## Tests

新增：

```text
examples/digital_friction_mvp/tests/test_bayesian_controllability_lite.py
```

必须覆盖：

```text
empty / malformed memory safe initialization
low entropy success -> entropy_control high
high entropy mixed outcomes -> entropy_control low
all actions same failure -> action_contrast low and chi_lite low
all actions same success -> action_contrast low but chi_lite high
avoid -> no_attempt does not inflate main C_family
success_self and success_with_help map to success bin
failure_after_attempt_low_uncontrollability maps to controllable_failure, not success
early single failure shrinks C_family toward 0.5
unbalanced evidence keeps family_confidence low
global trace update skipped when family_confidence below threshold
rho clamp works
weight normalization works
helper does not mutate input memory in place
disabled/off returns status disabled and no update
shadow mode does not change pi_ref / pi_bayes / pi_final / sampled action
before_event audit does not contain current outcome / support_mode / attribution
after_event audit is clearly marked post_update and not used for current action
gated_modulate uses only C_before_event
low C flattens Phase4 pi_final toward uniform
low C does not directly encode seek_help or avoid
high C reduces avoid and assigns mass to best non-avoid action
high C can choose seek_help or attempt_self depending on Phase4 pi_final / q_bayes
missing Phase4 pi_final and q_bayes leaves policy unmodified
modulation max_delta clamps to [0, 1]
```

Runtime / fingerprint tests:

```text
default mode is off
env can enable shadow
config clamps are correct
world_runner fingerprint includes all Huys-Dayan-lite keys
```

Regression behavior test:

```text
same seed
same 0513-style config
Huys-Dayan-lite off vs shadow
actual action sequence unchanged
outcome unchanged
helplessness_after unchanged
attribution unchanged
scope_spillover unchanged
payload contains huys_dayan_lite_controllability only in shadow mode
```

这个测试要求 helper 不调用 LLM、不抽样、不改变随机数流。

Analysis tests:

```text
temporary SQLite + manifest
payload coverage computed correctly
before_event / after_event fields exported separately
uses_post_outcome_information true count computed correctly
Phase4 alignment fields exported when present
lagged prediction table uses day t-1 C_after_event to describe day t outcomes
```

## Validation Commands

建议验证命令：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_bayesian_controllability_lite.py \
  examples/digital_friction_mvp/tests/test_huys_dayan_lite_controllability_analysis.py \
  examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py \
  examples/digital_friction_mvp/tests/test_runtime.py \
  -q
```

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_bayesian_control_audit.py \
  examples/digital_friction_mvp/tests/test_experience_memory.py \
  examples/digital_friction_mvp/tests/test_llm_psychology.py \
  examples/digital_friction_mvp/tests/test_stream_episode_recording.py \
  -q
```

```bash
python -m py_compile \
  examples/digital_friction_mvp/config_runtime.py \
  examples/digital_friction_mvp/proto/agent.py \
  examples/digital_friction_mvp/proto/state_schema.py \
  examples/digital_friction_mvp/proto/bayesian_policy_lite.py \
  examples/digital_friction_mvp/proto/bayesian_controllability_lite.py \
  examples/digital_friction_mvp/world_runner.py \
  examples/digital_friction_mvp/analysis_huys_dayan_lite_controllability.py
```

```bash
git diff --check -- \
  Huys–Dayan-litePlan.md \
  frictionchangeLog.md \
  examples/digital_friction_mvp/config_runtime.py \
  examples/digital_friction_mvp/proto/agent.py \
  examples/digital_friction_mvp/proto/state_schema.py \
  examples/digital_friction_mvp/proto/bayesian_policy_lite.py \
  examples/digital_friction_mvp/proto/bayesian_controllability_lite.py \
  examples/digital_friction_mvp/world_runner.py \
  examples/digital_friction_mvp/analysis_huys_dayan_lite_controllability.py \
  examples/digital_friction_mvp/tests
```

## Experiment Command Add-On

在现有 0513-style gated-lite 命令基础上追加：

```bash
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE=shadow \
PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K=6 \
PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES=1 \
PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT=0.05 \
PROTO_HUYS_DAYAN_LITE_RHO=1.0 \
PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE=false \
PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY=0.25 \
PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST=0.25 \
PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI=0.50 \
PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD=0.50 \
PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA=0.25 \
PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD=0.45 \
PROTO_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD=0.60 \
```

第一轮建议沿用 0513 风格配置：

```text
semantic_v2
lambda_llm=0.50
max_delta=0.10
4 worlds
3 paired seeds
10 agents
10 days
single steady stage
Huys-Dayan-lite shadow
```

本轮不建议改：

```text
world batch
agent count
stage mode
LLM switch
Bayesian gated-lite policy params
```

这样 Phase5 shadow 结果可以和 2026-05-13 gated-lite pilot 对齐比较。

第一轮只作为：

```text
Phase5 smoke / sanity test
```

不是最终主实验。

## Non-Goals

本计划不做：

```text
full Bayesian RL
transition model
multi-step planning
exploration bonus controlling real actions
C_family replacing Phase4 policy
C_family directly increasing seek_help
C_family directly increasing avoid
C_global directly changing helplessness
C_global directly changing self_efficacy
C_global directly changing outcome probability
C_family overriding pi_ref
C_family replacing pi_bayes
policy_mode=on
DB schema change
HelperAgent
PeerOlderAdultAgent
CustomerServiceAgent
```

## Changelog Entry

实施后追加到：

```text
frictionchangeLog.md
```

建议标题：

```text
### Phase 5 Huys-Dayan-inspired controllability shadow audit
```

必须写清：

```text
新增 proto_bayesian_controllability_lite_memory
新增 bayesian_controllability_lite.py
新增 entropy_control / action_contrast_control / reward_control_chi_lite
新增 C_family diagnostic score / global_controllability_trace
区分 C_before_event 和 C_after_event
主 C_family 默认排除 avoid
coarse outcome bins 使用 success / controllable_failure / uncontrollable_failure
shadow-only 不影响 action / outcome / helplessness / attribution / scope_spillover
新增 analysis_huys_dayan_lite_controllability.py
记录实际测试命令和结果
```

Phase5B 实施后建议标题：

```text
### Phase 5B Huys-Dayan controllability-aware gated modulation
```

必须写清：

```text
新增 gated_modulate mode
Low-C 使用 flatten-only，不声称 low controllability causes help-seeking
High-C 减少 avoid，并把概率给 Phase4 pi_final / Q_bayes 支持的 best non-avoid action
C_before_event 才能影响当前 action
C_after_event 只用于 learning trace
真实行动仍复用 choose_attempt_strategy(..., precomputed_final_weights=...)
不改 outcome / helplessness / attribution / scope_spillover / DB schema
```
