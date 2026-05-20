# OutcomeModel v2 + LLM Trajectory Plan

## 文档定位

本文件定义 `digital_friction_mvp` 后续 `outcome_model` 的升级方案。

目标不是让 LLM 直接判断成功、失败或心理变化，而是把当前偏硬的 rule-only `outcome_model` 升级为：

> appraisal-conditioned stochastic resolver + bounded LLM trajectory input

中文可以理解为：

> 先用已有任务评估和记忆形成 outcome 前的结构化评估，再由可审计概率模型采样结果；LLM 只能作为有上限的行动轨迹建议者。

---

## 一句话裁决

**主实验保留 `appraisal_rule_v2` 作为规则基线，同时允许 `trajectory_bounded_online_mc` 作为 LLM trajectory 条件下的主结论实验。**

推荐定位：

```text
Primary result A:
  appraisal_rule_v2

Primary result B:
  trajectory_bounded_online_mc

Qualitative audit:
  trajectory_shadow / case studies

Optional robustness:
  trajectory_bounded_replay, if later cache/replay is implemented
```

也就是：

```text
appraisal_rule_v2 = 主规则模型 / 主裁判
LLM trajectory = 有上限的在线行动轨迹建议者
OutcomeModel = 最终采样器
```

这里的 `trajectory_bounded_online_mc` 不是 deterministic replay。它把 LLM trajectory 当成模拟器中的一个随机组件，通过多轮 Monte Carlo runs 估计平均效果、方差和置信区间。

---

## 当前问题

当前 `outcome_model.py` 主要使用：

```text
DigitalTask
+ AttemptStrategy
+ helplessness
+ env friction/support scalar
+ consecutive_failures
-> success_probability / abandon_probability
-> AttemptOutcome
```

这个模型的优点是：

- 可控
- 可复现
- 好做 paired-world comparison
- 不会让 LLM 接管主机制

但它的问题是：

- 太像固定公式加减分
- 没有充分利用已有 `TaskAppraisalResult`
- 没有充分利用已有 `MemoryFeatures`
- 很难解释任务执行过程中具体在哪里发生 friction
- 不够像 AgentSociety-style 的 LLM agent simulation

---

## 总体机制

完整目标流程：

```text
Mobile Intention Entry
        |
        |-- no-op / context-only
        |       -> audit only
        |       -> no outcome_model
        |       -> no psychology update
        |
        |-- mapped DigitalTask
                |
                v
          Task Appraisal
                |
                v
          Strategy Deliberation
                |
                v
          semantic_v2 pi_ref
                |
                v
          Bayesian Policy Lite / Phase4
                |
                v
          Controllability Modulation / Phase5C
                |
                v
          Selected Strategy
                |
                v
          appraisal_rule_v2 produces p_rule
                |
                |-- optional trajectory_shadow
                |       -> audit / case study only
                |
                |-- trajectory_bounded_online_mc
                |       -> online LLM produces trajectory tendency
                |       -> bounded residual fusion
                |
                v
          OutcomeModel samples AttemptOutcome
                |
                v
          Event Appraisal
                |
                v
          Helplessness / self-efficacy update
                |
                v
          Memory / posterior / controllability / audit
```

---

## Modes

### Mode 0: `rule_v1`

旧版 outcome model。

用途：

- baseline
- regression test
- fallback reference

要求：

- 默认必须仍可运行
- 旧输入、旧 seed、同一 RNG state 下行为必须与当前 `resolve_attempt_outcome` 完全一致
- 不读取 `TaskAppraisalResult / MemoryFeatures / LLM trajectory`

---

### Mode 1: `appraisal_rule_v2`

主实验推荐模式。

核心思想：

```text
TaskAppraisalResult
+ MemoryFeatures
+ DigitalTask
+ AttemptStrategy
+ env friction/support
-> OutcomeAppraisalResult
-> p_abandon
-> p_success_given_not_abandon
-> AttemptOutcome
```

它不是 LLM outcome judge，而是更细的规则概率模型。

---

### Mode 2: `trajectory_shadow`

LLM 只生成行动轨迹和 friction points。

用途：

- audit
- qualitative case study
- rule vs LLM disagreement analysis

要求：

- 不改变真实 outcome
- 不改变心理更新
- 不改变 posterior / C_family / Phase4 / Phase5C

---

### Mode 3: `trajectory_bounded_online_mc`

LLM trajectory 进入 outcome 主线，并作为主结论实验之一，但必须：

- strict schema
- fixed friction taxonomy
- bounded influence
- no hidden fallback
- multiple Monte Carlo runs
- confidence intervals / uncertainty reporting
- full prompt and output audit

用途：

- primary result B
- LLM-trajectory-conditioned simulation
- realism / process-trace enhancement

它不是严格 deterministic paired-world replay。它的结论应表述为：

```text
在 trajectory-conditioned stochastic simulation 下，多轮重复实验的平均效果。
```

而不是：

```text
单次 paired-world replay 中完全确定的因果差异。
```

### Optional Mode 4: `trajectory_bounded_replay`

如果后续要做更严格的 replay/cached ablation，可以再实现该模式。

用途：

- robustness check
- appendix ablation
- deterministic replay comparison

---

## appraisal_rule_v2 设计

### 复用现有字段

不要重造心理系统。`appraisal_rule_v2` 应主要复用已有字段。

来自 `TaskAppraisalResult`：

```text
perceived_task_difficulty
perceived_task_risk
felt_control
expected_help_effectiveness
task_value
```

来自 `MemoryFeatures`：

```text
effective_helplessness
task_self_efficacy
controllable_success_memory
recent_negative_feedback_ratio
recent_same_task_failure_count
recent_failure_pressure
```

来自 `DigitalTask / env`：

```text
task_family
friction_type
task.difficulty
support_sensitivity
friction_tier
support_quality_from_env(env)
```

来自 `AttemptStrategy`：

```text
attempt_self
seek_help_then_attempt
avoid
support_requested
```

---

### OutcomeAppraisalResult

建议新增极轻 dataclass 或 dict。

字段建议：

```text
mode
status
source
confidence
reason
cache_hit

perceived_task_difficulty
perceived_task_risk
felt_control
expected_help_effectiveness
task_value

effective_helplessness
task_self_efficacy
controllable_success_memory
recent_negative_feedback_ratio
recent_same_task_failure_count
recent_failure_pressure

friction_tier
difficulty_pressure
risk_pressure
control_deficit
efficacy_deficit
support_effective_quality
abandonment_pressure
```

禁止字段：

```text
outcome_type
success
failure
abandon
helplessness_delta
self_efficacy_delta
C_family
C_global
Bayesian posterior
Phase4 weights
Phase5C weights
```

---

### 两阶段概率

`appraisal_rule_v2` 建议使用：

```text
p_abandon = sigmoid(abandon_logit)
p_success_given_not_abandon = sigmoid(success_logit)
```

然后：

```text
P(abandon_midway) = p_abandon
P(success) = (1 - p_abandon) * p_success_given_not_abandon
P(failure) = (1 - p_abandon) * (1 - p_success_given_not_abandon)
```

这样比旧模型更清楚：

```text
先判断是否中途放弃
如果没有放弃，再判断是否成功
```

---

### abandon_logit 方向

提高放弃概率：

```text
perceived_task_difficulty higher
task.difficulty higher
friction_tier higher
effective_helplessness higher
control_deficit higher
efficacy_deficit higher
recent_negative_feedback_ratio higher
recent_same_task_failure_count higher
recent_failure_pressure higher
perceived_task_risk higher
```

降低放弃概率：

```text
task_value higher
felt_control higher
expected_help_effectiveness higher, especially when seek_help_then_attempt
support_effective_quality higher
controllable_success_memory higher
```

---

### success_logit 方向

提高成功概率：

```text
task_self_efficacy higher
felt_control higher
controllable_success_memory higher
task_value higher
expected_help_effectiveness higher when help strategy
support_effective_quality higher
task.support_sensitivity * support_quality higher
```

降低成功概率：

```text
perceived_task_difficulty higher
task.difficulty higher
friction_tier higher
effective_helplessness higher
perceived_task_risk higher
recent_same_task_failure_count higher
recent_negative_feedback_ratio higher
```

---

## LLM Trajectory 设计

### 何时调用

推荐位置：

```text
Phase4 / Phase5C 已经选出 strategy 后
OutcomeModel 采样前
```

原因：

- 不影响 Task Appraisal
- 不影响 Strategy Deliberation
- 不影响 Phase4 / Phase5C policy
- 只解释和调节已选 strategy 的执行过程

### 何时不调用

不调用：

```text
no_mobile_action
browse_entertainment
communicate_or_seek_help
unknown_or_unmapped
low_confidence_mapping_noop
avoid strategy, first version
```

`communicate_or_seek_help` 是 entry 层 context-only，不是真正的 help strategy。

---

### LLM 输入白名单

允许输入：

```text
task_family
friction_type
task difficulty bucket
selected strategy_type

TaskAppraisalResult:
  perceived_task_difficulty
  perceived_task_risk
  felt_control
  expected_help_effectiveness
  task_value

MemoryFeatures buckets:
  effective_helplessness
  task_self_efficacy
  controllable_success_memory
  recent_same_task_failure_count
  recent_negative_feedback_ratio

env buckets:
  friction_tier
  risk_level bucket
  complexity_level bucket
  accessibility_level bucket

stable capability profile:
  baseline digital familiarity bucket
  vision/accessibility constraint bucket, if initialized
```

禁止输入：

```text
sampled outcome
success/failure after sampling
helplessness_delta
post-event attribution
posterior after update
C_family / C_global after update
Phase4 / Phase5C after-event audit
future memory state
TalkingData validation labels
```

---

### LLM 输出 schema

所有概率使用 0-1。

```json
{
  "planned_steps": [
    {
      "step_id": 1,
      "action": "open payment confirmation page"
    },
    {
      "step_id": 2,
      "action": "read the risk warning"
    }
  ],
  "selected_friction_points": [
    {
      "point": "risk_popup_anxiety",
      "severity": 0.68,
      "step_id": 2
    }
  ],
  "friction_encounter_likelihood": 0.68,
  "cognitive_load": 0.70,
  "help_need": 0.45,
  "trajectory_outcome_tendency": {
    "success_self": 0.35,
    "failure_after_attempt": 0.40,
    "abandon_midway": 0.25
  },
  "trajectory_confidence": 0.74,
  "reason": "Risk warning and ambiguous confirmation create bounded risk appraisal.",
  "does_not_sample_final_outcome": true,
  "does_not_update_psychology": true
}
```

Hard rules:

```text
planned_steps: 2-6 steps
selected_friction_points: 0-3 points
all friction points must be in fixed taxonomy
trajectory_outcome_tendency probabilities sum to 1 within tolerance
no extra keys
does_not_sample_final_outcome must be true
does_not_update_psychology must be true
```

命名上避免使用 `predicted_outcome_distribution`。这里的 LLM 输出不是最终 outcome prediction，而是：

```text
trajectory_outcome_tendency = 在该行动轨迹下，LLM 给出的 bounded tendency / advisory distribution
```

最终 outcome 仍由：

```text
p_rule + bounded residual fusion -> p_final -> OutcomeModel sampling
```

决定。

---

### Allowed outcome keys by strategy

`attempt_self` allows:

```text
success_self
failure_after_attempt
abandon_midway
```

`seek_help_then_attempt` allows:

```text
success_with_help
failure_even_with_help
failure_after_attempt
abandon_midway
```

`avoid`:

```text
do not call LLM trajectory in first version
outcome_type = avoid_without_attempt
```

---

## Friction Point Taxonomy

LLM 不能自由发明 friction point。

### Cross-cutting

```text
visual_accessibility_load
small_touch_target
terminology_jargon
navigation_depth
unclear_feedback
error_recovery_uncertainty
session_timeout_pressure
permission_or_privacy_concern
security_or_scam_concern
multi_step_memory_load
authentication_handoff
support_unavailable_or_delayed
```

### navigation_service_location

```text
location_permission_confusion
address_disambiguation
route_choice_overload
map_visual_density
service_filter_confusion
location_accuracy_uncertainty
```

### account_login_verification

```text
password_memory_failure
otp_delay_or_expiry
captcha_visual_difficulty
account_lockout_anxiety
multi_factor_switching
device_trust_prompt_confusion
```

### information_search_judgment

```text
query_formulation_difficulty
information_overload
source_credibility_uncertainty
ad_or_sponsored_result_confusion
medical_or_service_jargon
contradictory_information
```

### profile_form_upload

```text
form_field_ambiguity
document_photo_quality_issue
file_format_or_size_error
upload_progress_uncertainty
privacy_concern_about_documents
required_field_discovery
```

### service_application_submission

```text
eligibility_rule_confusion
multi_step_form_burden
required_document_uncertainty
submission_confirmation_uncertainty
opaque_error_message
deadline_or_timeout_pressure
```

### payment_risk_confirmation

```text
risk_popup_anxiety
scam_security_concern
amount_or_fee_confusion
confirm_cancel_button_ambiguity
payment_failure_recovery_uncertainty
authentication_or_bank_handoff
```

---

## Bounded Fusion

### Rule distribution

`appraisal_rule_v2` produces:

```text
p_rule
```

Example:

```json
{
  "success_self": 0.60,
  "failure_after_attempt": 0.25,
  "abandon_midway": 0.15
}
```

### LLM trajectory tendency

LLM trajectory produces:

```text
p_traj
```

Example:

```json
{
  "success_self": 0.45,
  "failure_after_attempt": 0.35,
  "abandon_midway": 0.20
}
```

### Recommended fusion

Use bounded residual blend:

```text
delta_raw_i = p_traj_i - p_rule_i
delta_i = clip(alpha * delta_raw_i, -cap_i, +cap_i)
p_tmp_i = p_rule_i + delta_i
p_final = project_to_simplex(p_tmp)
```

Recommended default:

```text
alpha = 0.10
per_outcome_cap = 0.08
total_variation_cap = 0.10
trajectory_confidence_min = 0.65
```

LLM influence must remain bounded:

```text
LLM can adjust probabilities
LLM cannot replace p_rule
LLM cannot create impossible outcomes
LLM cannot decide final sampled outcome
```

---

## Objective Dominance

Objective task/env friction must remain the main driver.

Guardrails:

```text
if friction_tier is high:
  LLM cannot reduce failure/abandon probability beyond cap

if friction_tier is low and task difficulty is low:
  LLM cannot increase failure/abandon probability beyond cap

if p_rule is high confidence:
  alpha_effective decreases
```

Suggested:

```text
alpha_effective = alpha_base
                  * trajectory_confidence
                  * rule_uncertainty_factor
```

where:

```text
rule_uncertainty_factor = 1 - max(p_rule.values())
```

---

## Anti-Stereotype / Anti-Self-Reinforcement

### Risk

Without guardrails, the model may create a harmful loop:

```text
low confidence profile
-> LLM predicts high friction / failure
-> outcome worsens
-> memory worsens
-> LLM predicts even more failure
```

### Required protections

#### Profile swap test

Fix:

```text
DigitalTask
TaskAppraisalResult
MemoryFeatures
AttemptStrategy
env
```

Swap:

```text
age_bucket
gender
```

Expected:

```text
trajectory distribution TVD <= threshold
friction likelihood shift <= threshold
```

#### Capability-only prompt

Prompt should use:

```text
baseline_device_familiarity
vision_accessibility_constraint
digital_experience_bucket
task_self_efficacy_bucket
```

Avoid causal phrasing like:

```text
because the user is old
because the user is female
```

#### History cap test

Changing recent failure count should not let LLM dominate outcome.

Example:

```text
recent_same_task_failure_count: 0 -> 3+
```

Expected:

```text
LLM distribution shift <= cap
final distribution shift <= smaller cap
```

#### Low-confidence handling

```text
trajectory_confidence < threshold
-> no bounded-main use
-> rule distribution only
-> audit low_confidence
```

---

## Online Monte Carlo Discipline

`trajectory_bounded_online_mc` 允许 LLM 在实验运行时读取当前 pre-outcome 状态和 memory snapshot，并在线生成 trajectory appraisal。

这意味着它不追求：

```text
same input -> same LLM output forever
```

而是追求：

```text
same experimental condition -> many stochastic runs -> stable mean effect and uncertainty interval
```

因此，LLM trajectory 可以进入主结论，但主结论必须写成 Monte Carlo 估计，而不是 deterministic replay 结论。

### Online MC requirements

必须记录每次 LLM 调用的审计信息：

```text
run_id
world_id / condition_id
agent_id
day
tick
prompt_version
taxonomy_version
model_id
temperature / decoding config
pre-outcome input snapshot hash
raw response hash
sanitized trajectory JSON
schema status
trajectory_outcome_tendency
trajectory_confidence
p_rule
p_final
sampled outcome
```

必须报告：

```text
number of Monte Carlo runs
mean outcome metrics
standard error / confidence interval
between-run variance
invalid LLM output rate
low-confidence rate
banned-key leakage rate
taxonomy invalid rate
average TVD from p_rule
alpha / cap sensitivity
```

推荐最低要求：

```text
N >= 20 runs per experimental condition for pilot
N >= 50 runs per experimental condition for main reported results
same seeds / same condition grid where possible
same LLM model and decoding config across compared conditions
```

如果成本太高，可以先用较小 N 做 pilot，但主文里必须诚实报告 uncertainty。

### What online MC does not guarantee

它不保证：

```text
同一个 episode 在不同时间调用 LLM 得到完全相同 trajectory
四个 worlds 中每一个 agent/tick 都有完全相同 LLM output
单次 run 的 paired-world 差异完全来自 Phase4 / Phase5C
```

它保证的是：

```text
在相同实验配置和足够重复次数下，估计 trajectory-conditioned outcome mechanism 的平均效果。
```

---

## Optional Replay / Cache

`trajectory_bounded_replay` 是可选的 robustness / appendix 模式，不是当前主线必需项。

如果未来启用 replay/cached ablation，cache key should include:

```text
trajectory_prompt_version
trajectory_taxonomy_version
model_id
seed
agent_id
day
tick
task_family
friction_type
difficulty_bucket
strategy_type
allowed_outcome_keys
TaskAppraisalResult buckets
MemoryFeatures buckets
env buckets
support_features buckets, if any
```

### Cache key must not include

```text
sampled outcome
success/failure after sampling
abandon flag after sampling
helplessness_delta
event attribution after outcome
posterior after update
C_family / C_global after update
future memory
```

### Missing / invalid cache

For `trajectory_bounded_replay`:

```text
missing cache -> fail-fast
invalid JSON -> fail-fast
banned key -> fail-fast
taxonomy outside -> fail-fast
probabilities not normalized -> fail-fast
```

For `trajectory_shadow`:

```text
invalid output -> shadow_invalid
real outcome unaffected
```

For `trajectory_bounded_online_mc`:

```text
invalid JSON -> mark trajectory_invalid and use predeclared policy
banned key -> reject trajectory and record violation
taxonomy outside -> reject trajectory and record violation
probabilities not normalized -> reject trajectory and record violation
low confidence -> use p_rule only or reject run, according to predeclared config
```

主实验必须预先选择一种 invalid handling policy，不能跑完后临时挑选：

```text
recommended:
  invalid / banned / taxonomy outside -> exclude run from trajectory-conditioned analysis and report rate
  low confidence -> p_rule only with audit

stricter:
  invalid / banned / taxonomy outside -> fail run
```

---

## FamilyHelperAgent / support_response

Support should be integrated only after `seek_help_then_attempt`.

Recommended sequence:

```text
strategy == seek_help_then_attempt
        |
        v
FamilyHelperAgent support_response
        |
        v
derive_support_features
        |
        v
LLM trajectory sees support_features, not raw helper text
        |
        v
bounded trajectory distribution
        |
        v
OutcomeModel fusion
```

Why:

- raw helper text may over-narrate
- helper cannot decide outcome
- LLM cannot decide outcome
- support features are easier to audit and cap

Allowed support features:

```text
helper_available
responded
instruction_quality
autonomy_preservation
proxy_completion_level
support_alignment
response_delay_bucket
```

Forbidden:

```text
helper says success
helper says failure
helper raw outcome prediction
helplessness_delta
posterior update
```

---

## Config Plan

Suggested env:

```text
PROTO_OUTCOME_MODEL_MODE=rule_v1|appraisal_rule_v2|trajectory_bounded_online_mc|trajectory_bounded_replay
PROTO_OUTCOME_TRAJECTORY_LLM_MODE=off|shadow|online|replay
PROTO_OUTCOME_TRAJECTORY_PROMPT_VERSION=trajectory_v1
PROTO_OUTCOME_TRAJECTORY_TAXONOMY_VERSION=friction_taxonomy_v1
PROTO_OUTCOME_TRAJECTORY_ALPHA=0.10
PROTO_OUTCOME_TRAJECTORY_MAX_OUTCOME_SHIFT=0.08
PROTO_OUTCOME_TRAJECTORY_MAX_TVD=0.10
PROTO_OUTCOME_TRAJECTORY_MIN_CONFIDENCE=0.65
PROTO_OUTCOME_TRAJECTORY_STRICT_SCHEMA=1
PROTO_OUTCOME_TRAJECTORY_MC_RUNS=50
PROTO_OUTCOME_TRAJECTORY_INVALID_POLICY=rule_only|exclude_run|fail_run
```

Defaults:

```text
PROTO_OUTCOME_MODEL_MODE=rule_v1
PROTO_OUTCOME_TRAJECTORY_LLM_MODE=off
```

---

## File-Level Plan

### Must change

#### `examples/digital_friction_mvp/proto/outcome_model.py`

Add:

```text
_resolve_attempt_outcome_rule_v1
build_outcome_appraisal_rule_v2
build_rule_outcome_distribution_v2
validate_outcome_distribution
fuse_rule_and_trajectory_distribution
sample_from_outcome_distribution
_resolve_attempt_outcome_appraisal_rule_v2
_resolve_attempt_outcome_trajectory_bounded_online_mc
_resolve_attempt_outcome_trajectory_bounded_replay
```

Keep:

```text
support_quality_from_env
friction_tier_from_env
infer_event_level_uncontrollability
infer_avoid_reason
infer_support_mode
```

Do not call LLM inside `outcome_model.py`.

#### `examples/digital_friction_mvp/proto/models.py`

Add one of:

```text
OutcomeAppraisalResult
TrajectoryAppraisalResult
```

or keep trajectory details as JSON audit fields.

Add minimal audit fields to `AttemptOutcome`:

```text
outcome_model_mode
trajectory_mode
trajectory_status
trajectory_confidence
trajectory_cache_hit
trajectory_run_id
trajectory_model_id
trajectory_prompt_version
trajectory_friction_points_json
trajectory_tendency_json
rule_distribution_json
final_distribution_json
trajectory_alpha_effective
trajectory_tvd_from_rule
trajectory_invalid_reason
probability_audit_json
```

Do not change:

```text
OutcomeType
AttemptStrategy
RecentEpisode
HelplessnessUpdateInput
```

#### `examples/digital_friction_mvp/proto/agent.py`

At the point after strategy selection:

```text
if trajectory mode enabled and strategy != avoid:
    get trajectory from llm_psychology online call or replay cache, depending on mode

resolve_attempt_outcome(
    task=task,
    strategy=strategy,
    helplessness=helplessness,
    env=env,
    consecutive_failures=consecutive_failures,
    task_appraisal=task_appraisal,
    memory_features=memory_features,
    trajectory_result=trajectory_result,
    outcome_model_mode=runtime_config.proto_outcome_model_mode,
)
```

Ensure:

```text
no-op mobile entry never calls trajectory
avoid does not call trajectory first version
```

#### `examples/digital_friction_mvp/proto/llm_psychology.py`

Add:

```text
resolve_trajectory_appraisal_shadow
resolve_trajectory_appraisal_online
load_trajectory_replay
sanitize_trajectory_appraisal
build_trajectory_cache_key
```

Reuse existing JSON query / sanitizer style.

#### `examples/digital_friction_mvp/config_runtime.py`

Add config and fail-fast validation.

#### `examples/digital_friction_mvp/world_runner.py`

Add new outcome / trajectory env keys to fingerprint.

#### `examples/digital_friction_mvp/main.py`

Record metadata:

```text
outcome_model_mode
trajectory_mode
prompt_version
taxonomy_version
alpha / caps
MC run count
LLM model / decoding config
invalid handling policy
cache path / cache hash, if replay mode
```

### Do not change

```text
state_update.py
bayesian_policy_lite.py
bayesian_controllability_lite.py
DB schema
task_assignment.py entry semantics
runtime.py task surface semantics
RecentEpisode semantics
scope_spillover formula
```

---

## Test Plan

### Baseline regression

```text
rule_v1 same inputs + same rng -> same outcome as old model
```

### Schema tests

```text
missing required key -> reject
extra key -> reject
banned key -> reject
probabilities not sum to 1 -> reject
taxonomy outside point -> reject
more than 3 friction points -> reject
```

### Strategy outcome key tests

```text
attempt_self only allows:
  success_self / failure_after_attempt / abandon_midway

seek_help_then_attempt only allows:
  success_with_help / failure_even_with_help / failure_after_attempt / abandon_midway

avoid:
  no trajectory call
```

### Fusion tests

```text
final distribution normalized
impossible outcomes remain zero
per-outcome shift <= cap
TVD from rule <= cap
alpha=0 -> exactly rule distribution
low confidence -> rule-only or fail-fast according to mode
```

### Objective dominance tests

```text
higher friction_tier cannot increase final success probability
higher difficulty cannot increase final success probability
higher support_features cannot lower success_with_help under help strategy
```

### Fairness / self-reinforcement tests

```text
profile swap age/gender TVD <= threshold
history cap failure-history effect <= threshold
banned demographic causal phrases absent from reason
memory contribution cap enforced
```

### No-leakage tests

```text
online trajectory prompt excludes outcome / helplessness_delta / posterior after update
replay cache key excludes outcome / helplessness_delta / posterior after update, if replay mode is used
trajectory prompt excludes final outcome
trajectory result does not update psychological variables
no-op mobile entries never call trajectory
communicate_or_seek_help never triggers trajectory or support
validation artifact never enters trajectory prompt
```

### Online MC tests

```text
same experimental condition can run multiple stochastic repetitions
all LLM calls are audited with run_id / condition_id / prompt_version / model_id
invalid handling follows predeclared policy
summary reports mean / standard error / confidence interval
alpha sensitivity does not reverse the main conclusion without being reported
```

### Optional replay tests

```text
missing cache in bounded-main mode -> fail-fast
same cache key -> same trajectory result
paired worlds use same replay result when pre-outcome inputs match
```

---

## Experiment Plan

### E0-E3: Primary Outcome Bundle

E0-E3 should be treated as one combined implementation target for future engineering instructions.

Engineering can still proceed in small verified steps, but a later instruction such as:

```text
Implement OutcomeModel E0-E3
```

means completing the whole bundle:

```text
E0: rule_v1 wrapper / exact regression
E1: appraisal_rule_v2 rule-based outcome upgrade
E2: appraisal_rule_v2 + trajectory_shadow audit
E3: trajectory_bounded_online_mc primary trajectory-conditioned Monte Carlo
```

The bundle has two primary reporting tracks:

```text
Primary A:
  appraisal_rule_v2

Primary B:
  trajectory_bounded_online_mc
```

`trajectory_shadow` is included in the same bundle as an audit layer. It records LLM action trajectory, friction points, schema status, and safety diagnostics without changing outcome.

`trajectory_bounded_online_mc` is not deterministic replay. It treats LLM trajectory generation as a bounded stochastic component of the simulator:

```text
p_rule from appraisal_rule_v2
p_traj from online LLM trajectory
p_final by bounded residual fusion
repeat N runs
report mean / confidence interval / variance
```

The combined bundle must still preserve the engineering order internally:

```text
1. make rule_v1 behaviorally identical to current outcome_model
2. add appraisal_rule_v2 and verify it without LLM
3. add trajectory_shadow and verify it cannot change outcome
4. add trajectory_bounded_online_mc and verify bounded fusion / MC reporting
```

### E4: `trajectory_bounded_replay`

Optional robustness / appendix mode, only if replay/cache is later implemented.

```text
p_rule from appraisal_rule_v2
p_traj from cached LLM trajectory
p_final by bounded residual fusion
```

### Sensitivity

```text
alpha = 0.05 / 0.10 / 0.20
cap = 0.05 / 0.08 / 0.10
confidence threshold = 0.60 / 0.65 / 0.70
```

---

## Paper Language

### Can say

```text
We upgrade the outcome resolver from a rule-only probability calculator to an appraisal-conditioned stochastic resolver.
```

```text
A constrained LLM trajectory module produces task walkthroughs, friction-point annotations, and bounded outcome tendencies.
```

```text
LLM trajectory outputs are bounded by per-outcome and total-variation caps before they can affect final probabilities.
```

```text
Trajectory-conditioned results are estimated through repeated Monte Carlo simulations and reported with uncertainty intervals.
```

```text
Objective task and environment friction remain the dominant inputs.
```

```text
The LLM does not sample final outcomes or update psychological states.
```

### Cannot say

```text
LLM predicts real older adults' task outcomes.
```

```text
TalkingData validates digital friction points.
```

```text
Profile determines failure.
```

```text
LLM simulates true helplessness dynamics.
```

```text
Trajectory replaces Phase4 / Phase5C.
```

```text
LLM decides whether the agent succeeds.
```

---

## Done Definition

This plan is complete only when:

```text
rule_v1 baseline passes regression
appraisal_rule_v2 runs without LLM
trajectory_shadow records audit without changing outcome
trajectory_bounded_online_mc runs as bounded online Monte Carlo
MC results report mean / variance / confidence interval
every online LLM call is audited
trajectory_bounded_replay, if implemented, is cache/replay only
bounded fusion obeys caps
banned-key leakage = 0
taxonomy-outside outputs are rejected
no-op entries never reach outcome_model
avoid strategy does not call trajectory first version
profile swap / history cap / objective dominance tests pass
world_runner fingerprint includes all new outcome config
paper claims match implementation boundaries
```

---

## Final Recommendation

Future implementation instructions may request E0-E3 as one combined task:

```text
Implement OutcomeModel E0-E3
```

When that happens, implement the whole primary bundle in one engineering pass, while still verifying each internal step:

```text
1. rule_v1 wrapper / regression
2. appraisal_rule_v2
3. trajectory_shadow
4. trajectory_bounded_online_mc as primary trajectory-conditioned experiment
```

Keep separate for later:

```text
E4: optional trajectory_bounded_replay as robustness / appendix
Future: optional FamilyHelperAgent support_features integration
```

Do not start with:

```text
LLM directly deciding outcome
LLM directly updating helplessness
LLM free-form friction point generation
uncapped online LLM deciding outcome in primary result
```

Final one-line summary:

> Let LLM trajectory enter the main conclusion as a bounded online Monte Carlo component of `appraisal_rule_v2`, not as the judge of task outcomes.
