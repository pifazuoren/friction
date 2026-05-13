# Phase 4 Semantic Gated-Lite2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans or an equivalent test-first workflow to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase 3 的 `gated_lite` 从“rule + LLM hybrid reference policy 上的小幅 Bayesian 修正”，推进为更接近 `Bayesian gated-lite2.md` 的 `weak prior -> bounded LLM semantic adjustment -> Bayesian gated shift -> safety guard / rule fallback` 主机制。

**Architecture:** Phase 4 不重写 outcome、helplessness、attribution、scope spillover、experience memory、stream memory 或 DB schema。它只修改 action choice 的 reference policy 构造方式：默认保留 Phase 3 `hybrid_ref` 兼容模式，新增 `semantic_v2` 模式，把 `pi_ref` 从 `strategy_deliberation.final_weights` 切换为 `pi_prior + strategy_deliberation.llm_weights` 的有界语义策略。Bayesian 仍只做 evidence-gated、max-delta-bounded shift，rule 只做 fallback / safety guard。

**Tech Stack:** Python, pytest, AgentSociety digital friction MVP, existing `attempt_strategy.py` `precomputed_final_weights` interface, existing `llm_psychology.py` `StrategyDeliberationResult`, existing `bayesian_policy_lite.py` posterior / gate / audit helpers.

---

## 0. 当前事实

Phase 1-3 已完成：

```text
Phase 1: shadow-only Bayesian posterior predictive audit
Phase 2: theory_v2 utility profile + fixed shadow analysis
Phase 3: gated_lite infrastructure + max_delta=0 dry-run + max_delta=0.05 smoke
```

当前代码里已经存在的可靠接口：

```text
examples/digital_friction_mvp/proto/attempt_strategy.py
  choose_attempt_strategy(..., precomputed_final_weights=pi_final)

examples/digital_friction_mvp/proto/llm_psychology.py
  StrategyDeliberationResult.rule_weights
  StrategyDeliberationResult.llm_weights
  StrategyDeliberationResult.final_weights
  StrategyDeliberationResult.confidence
  StrategyDeliberationResult.reason
  StrategyDeliberationResult.status
  StrategyDeliberationResult.source

examples/digital_friction_mvp/proto/bayesian_policy_lite.py
  compute_bayesian_policy_shadow(...)
  update_bayesian_policy_memory(...)
  combine_bayesian_policy_audits(...)
  gated_lite support: pi_ref -> pi_bayes -> pi_final
```

Phase 3 smoke 结果说明当前 `gated_lite` 基础设施是保守且可运行的：

```text
dry-run max_delta=0:
  payload coverage = 862 / 862
  posterior update = 862 / 862
  intervention_applied = 0

smoke max_delta=0.05:
  intervention = 148 / 862
  baseline intervention = 30 / 387
  high_friction_low_assist intervention = 118 / 475
  mean TVD baseline = 0.00137
  mean TVD high_friction_low_assist = 0.00409
  max TVD ≈ 0.038
```

Phase 3 的主要限制：

```text
pi_ref = strategy_deliberation.final_weights
```

这个 `final_weights` 是 rule + LLM hybrid distribution。它适合作为 Phase 3 过渡链路，但不适合作为最终 gated-lite2 主贡献，因为 rule 仍然是常规策略主干的一部分。

---

## 1. Phase 4 的核心变化

Phase 4 要把 action choice 从：

```text
rule weights
-> LLM strategy deliberation mixed with rule
-> final_weights as pi_ref
-> Bayesian gated shift
-> pi_final
-> sampled action
```

推进为：

```text
weak neutral prior
-> bounded LLM semantic adjustment
-> pi_semantic as pi_ref
-> Bayesian posterior predictive policy
-> confidence + entropy evidence gate
-> max_delta bounded shift
-> probability floor + safety guard
-> pi_final
-> sampled action
```

Phase 4 的关键边界：

```text
rule 不再作为 semantic_v2 的常规策略权重来源。
rule_weights 只能 audit-only，或在 LLM semantic policy 非法时作为 fallback 诊断信息。
Bayesian 仍不接管 agent，只能在证据足够时小幅修正 pi_semantic。
task appraisal / event appraisal / attribution / scope spillover / helplessness update 全部保留。
```

重要诚实边界：

```text
semantic_v2 removes direct rule mixing, but the current LLM deliberation may still see rule_weights as contextual reference.
```

这意味着 Phase 4 第一版只能声称：

```text
rule 不再直接混入 pi_ref；
LLM semantic policy 仍复用现有 deliberation 管线；
当前版本不是完全 rule-free LLM semantic policy。
```

后续 Phase 5 可单独做：

```text
LLM semantic without rule_weights in prompt
```

但 Phase 4 第一版不建议同时改 prompt，因为那会把 reference policy 改造和 LLM 输入语义改造混在一起，增加解释风险。

推荐论文表述：

```text
Huys & Dayan-inspired lightweight Bayesian behavioral control layer for LLM social simulation.
```

仍不要说：

```text
full Bayesian RL
externally validated older-adult model
Bayesian mechanism is proven without ablation / sensitivity
```

---

## 2. 文件职责

### 修改文件

```text
examples/digital_friction_mvp/config_runtime.py
```

职责：新增 Phase 4 runtime config，默认保持 Phase 3 兼容。

```text
examples/digital_friction_mvp/proto/bayesian_policy_lite.py
```

职责：新增 semantic reference policy builder；复用已有 posterior、Q、gate、max_delta、prob_floor、audit 逻辑。

```text
examples/digital_friction_mvp/proto/agent.py
```

职责：根据 `reference_mode` 选择 `pi_ref` 来源，并把 semantic audit 合并进 payload。

```text
examples/digital_friction_mvp/world_runner.py
```

职责：fingerprint 增加 Phase 4 新环境变量。

```text
examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py
```

职责：覆盖 semantic builder、fallback、no-mutation、reference-mode 行为、gated shift 兼容。

```text
examples/digital_friction_mvp/tests/test_runtime.py
```

职责：覆盖 runtime 默认值、env parsing、clamp、非法值、fingerprint。

```text
frictionchangeLog.md
```

职责：实施完成后追加 Phase 4 变更、测试结果、实验结果。

### 不修改文件，除非测试证明必须修改

```text
examples/digital_friction_mvp/proto/attempt_strategy.py
```

理由：已有 `precomputed_final_weights` 是正确入口。Phase 4 应复用它，不创造新 sampler 接口。

```text
examples/digital_friction_mvp/proto/llm_psychology.py
```

理由：已有 `StrategyDeliberationResult.llm_weights`。Phase 4 第一版不改 prompt，不新增 LLM-only deliberation 接口。

---

## 3. 新增配置

新增：

```bash
PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE=hybrid_ref
PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM=0.25
PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE=0.50
```

合法值：

```text
PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE:
  hybrid_ref
  semantic_v2
```

默认值：

```text
reference_mode = hybrid_ref
lambda_llm = 0.25
min_llm_confidence = 0.50
```

含义：

```text
hybrid_ref:
  Phase 3 compatibility mode.
  pi_ref = strategy_deliberation.final_weights.

semantic_v2:
  Phase 4 main mechanism.
  pi_prior -> pi_llm -> pi_semantic -> pi_ref.

lambda_llm:
  LLM semantic policy 对 weak prior 的最大影响比例。
  0.25 表示 LLM 可以温和调整 prior，但不会单独接管策略。

min_llm_confidence:
  低于阈值时，不使用 llm_weights 构造 pi_semantic，fallback 到 weak prior。
```

建议保守起步：

```text
lambda_llm=0.25
min_llm_confidence=0.50
max_delta=0.05
gate_threshold=0.50
entropy_threshold=0.85
prob_floor=0.05
utility_profile=theory_v2
```

`lambda_llm=0.25` 是 Phase 4A 安全起点，不是最终结论。Phase 4B 至少应加入：

```text
lambda_llm = 0.10 / 0.25 / 0.50
```

原因：

```text
如果 semantic_v2 效果很弱，需要区分是机制无效，还是 LLM semantic adjustment 太弱。
如果 lambda_llm=0.50 出现 over-avoid 或 instability，也能证明 0.25 的保守性有工程依据。
```

---

## 4. Phase 4 机制细节

### 4.1 Weak Neutral Prior

固定弱先验：

```python
{
    "attempt_self": 0.34,
    "seek_help_then_attempt": 0.33,
    "avoid": 0.33,
}
```

第一版不要让 prior 使用：

```text
task_difficulty
support_quality
helplessness
consecutive_failures
task_self_efficacy
recent_negative_feedback_ratio
```

原因：这些如果进入 prior，审稿人很容易认为 rule 只是换了一个名字继续主导策略。

### 4.2 Bounded LLM Semantic Adjustment

复用已有 `strategy_deliberation.llm_weights`：

```text
pi_llm = strategy_deliberation.llm_weights
llm_confidence = strategy_deliberation.confidence
llm_reason = strategy_deliberation.reason
```

如果 `pi_llm` 合法且 `llm_confidence >= min_llm_confidence`：

```python
pi_semantic[action] = (
    (1.0 - lambda_llm) * pi_prior[action]
    + lambda_llm * pi_llm[action]
)
```

如果不合法：

```python
pi_semantic = pi_prior
semantic_fallback_used = True
semantic_fallback_reason = "invalid_or_low_confidence_llm"
```

合法性检查至少包括：

```text
包含全部 3 个 action
每个 action 是 finite number
每个 action >= 0
总和 > 0
normalize 后概率和为 1
llm_confidence >= min_llm_confidence
```

### 4.3 Bayesian Gated Shift

复用 Phase 3 已有逻辑：

```text
pi_ref = pi_semantic
pi_bayes = softmax(Q_bayes, tau)
gate opens if confidence >= gate_threshold and entropy <= entropy_threshold
delta = clip((pi_bayes - pi_ref) * confidence, -max_delta, +max_delta)
pi_after_bayesian_shift = normalize(pi_ref + delta)
pi_final = apply_prob_floor_and_normalize(pi_after_bayesian_shift)
```

### 4.4 Safety Guard / Rule Fallback

rule 可以用于：

```text
invalid pi_final fallback
all-zero distribution fallback
NaN / negative probability fallback
missing action fallback
probability floor
future impossible-action mask
```

rule 不应用于：

```text
helplessness 高就直接提高 avoid
support_quality 低就直接降低 seek_help
consecutive_failures 高就覆盖 pi_final
task_difficulty 高就大幅改 pi_final
```

第一版 fallback 优先级：

```text
1. semantic_v2 LLM invalid -> pi_semantic = pi_prior
2. Bayesian shift invalid -> fallback to pi_ref
3. floor 后 invalid -> fallback to pi_ref
4. sampler 仍然复用 attempt_strategy.py 的 normalize/floor 保护
```

Phase 4 第一版默认不 fallback 到 rule weights：

```text
rule_fallback_used 理想值应接近 0。
semantic_v2 的常规 fallback 是 pi_prior 或 pi_ref，不是 rule_weights。
rule_weights 在 Phase 4A/4B 中主要是 audit-only。
只有未来加入 impossible-action mask、严重异常兜底或外部 safety policy 时，才考虑 rule_fallback_used=true。
```

---

## 5. Payload Audit

扩展 `payload_json.auxiliary_audit.bayesian_policy_lite`。

必须保留 Phase 3 字段：

```text
mode
utility_profile
pi_ref
q_bayes
pi_bayes
pi_bayes_shadow
confidence_by_action
posterior_entropy_by_action
gate_by_action
delta_before_clamp
delta_applied
pi_after_bayesian_shift
pi_final
final_delta_after_floor
max_abs_final_delta
total_variation_distance
intervention_applied
safety_guard_status
uses_post_outcome_information_for_policy=false
posterior_update_action
policy_outcome_subtype
```

Phase 4 新增字段：

```text
reference_mode
pi_prior
pi_llm
llm_confidence
llm_reason
llm_status
llm_source
lambda_llm
min_llm_confidence
pi_semantic
semantic_delta_from_prior
semantic_fallback_used
semantic_fallback_reason
rule_weights_audit_only
rule_fallback_used
rule_fallback_reason
bayesian_shift_before_floor
```

审稿复核目标：

```text
LLM 语义到底改了 prior 多少？
Bayesian posterior 到底改了 semantic policy 多少？
rule 是否只是 fallback / audit，而不是常规主策略？
最终 sampled action 的概率来自哪里？
```

Phase 4 分析不能只看最终 `pi_final`。必须单独输出和复核：

```text
pi_prior
pi_llm
pi_semantic
pi_ref
pi_bayes
pi_final
semantic_delta_from_prior
final_delta_after_floor
```

否则无法证明 Phase 4 真正减少了 rule-heavy reference policy，而不仅仅是换了 audit 字段名称。

---

## 6. Task 1: Runtime Config

**Files:**

```text
Modify: examples/digital_friction_mvp/config_runtime.py
Modify: examples/digital_friction_mvp/world_runner.py
Modify: examples/digital_friction_mvp/tests/test_runtime.py
```

- [ ] **Step 1: 写 failing tests**

测试点：

```text
默认 reference_mode == "hybrid_ref"
默认 lambda_llm == 0.25
默认 min_llm_confidence == 0.50
env 可设置 reference_mode=semantic_v2
非法 reference_mode 抛 ValueError
lambda_llm clamp 到 [0.0, 1.0]
min_llm_confidence clamp 到 [0.0, 1.0]
world_runner fingerprint 包含三个新 key
```

运行：

```bash
python -m pytest examples/digital_friction_mvp/tests/test_runtime.py -q
```

预期：新增测试先失败。

- [ ] **Step 2: 修改 config_runtime.py**

新增常量：

```python
VALID_BAYESIAN_POLICY_LITE_REFERENCE_MODES = {"hybrid_ref", "semantic_v2"}
DEFAULT_BAYESIAN_POLICY_LITE_REFERENCE_MODE = "hybrid_ref"
```

`RuntimeConfig` 新增字段：

```python
proto_bayesian_policy_lite_reference_mode: str
proto_bayesian_policy_lite_lambda_llm: float
proto_bayesian_policy_lite_min_llm_confidence: float
```

`load_runtime_config()` 新增 env parsing：

```python
proto_bayesian_policy_lite_reference_mode = (
    os.getenv(
        "PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE",
        DEFAULT_BAYESIAN_POLICY_LITE_REFERENCE_MODE,
    )
    .strip()
    .lower()
)
if proto_bayesian_policy_lite_reference_mode not in VALID_BAYESIAN_POLICY_LITE_REFERENCE_MODES:
    raise ValueError(
        "PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE must be one of: "
        + ", ".join(sorted(VALID_BAYESIAN_POLICY_LITE_REFERENCE_MODES))
    )

proto_bayesian_policy_lite_lambda_llm = max(
    0.0,
    min(1.0, float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM", "0.25"))),
)
proto_bayesian_policy_lite_min_llm_confidence = max(
    0.0,
    min(
        1.0,
        float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE", "0.50")),
    ),
)
```

- [ ] **Step 3: 修改 world_runner.py**

`FINGERPRINT_ENV_KEYS` 增加：

```text
PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE
PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM
PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest examples/digital_friction_mvp/tests/test_runtime.py -q
```

预期：通过。

---

## 7. Task 2: Semantic Reference Policy Builder

**Files:**

```text
Modify: examples/digital_friction_mvp/proto/bayesian_policy_lite.py
Modify: examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py
```

- [ ] **Step 1: 写 failing tests**

测试点：

```text
build_semantic_reference_policy 正常 blend prior 和 llm_weights
lambda_llm=0 时 pi_semantic == pi_prior
lambda_llm=1 时 pi_semantic == normalized pi_llm
非法 llm_weights fallback 到 pi_prior
低 llm_confidence fallback 到 pi_prior
semantic_delta_from_prior = pi_semantic - pi_prior
rule_weights_audit_only 只记录，不进入 pi_semantic
helper 不原地修改输入 dict
```

运行：

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py -q
```

预期：新增测试先失败。

- [ ] **Step 2: 新增 helper**

建议新增 public helper：

```python
def build_semantic_reference_policy(
    *,
    reference_mode: Any,
    hybrid_reference: Any,
    llm_weights: Any,
    llm_confidence: Any,
    llm_reason: Any = "",
    llm_status: Any = "",
    llm_source: Any = "",
    rule_weights: Any = None,
    lambda_llm: Any = 0.25,
    min_llm_confidence: Any = 0.50,
) -> dict[str, Any]:
    ...
```

返回字段：

```text
reference_mode
pi_prior
pi_llm
llm_confidence
llm_reason
llm_status
llm_source
lambda_llm
min_llm_confidence
pi_semantic
semantic_delta_from_prior
semantic_fallback_used
semantic_fallback_reason
rule_weights_audit_only
pi_ref
```

`reference_mode=hybrid_ref`：

```text
pi_ref = normalize(hybrid_reference)
pi_semantic = {}
semantic_fallback_used = false
```

`reference_mode=semantic_v2`：

```text
pi_ref = pi_semantic
pi_semantic = bounded blend of pi_prior and pi_llm, or pi_prior fallback
rule_weights_audit_only = normalize(rule_weights)
```

注意：

```text
不要读取 support_mode / avoid_reason / outcome_type / attribution 等 post-outcome 字段。
不要修改传入 dict。
不要新增 action set。
```

- [ ] **Step 3: 跑 helper tests**

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py -q
```

预期：通过。

---

## 8. Task 3: Bayesian Helper 接入 Reference Audit

**Files:**

```text
Modify: examples/digital_friction_mvp/proto/bayesian_policy_lite.py
Modify: examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py
```

- [ ] **Step 1: 写 failing tests**

测试点：

```text
compute_bayesian_policy_shadow 可接收 semantic reference audit
semantic_v2 gated_lite 的 pi_ref 等于 pi_semantic
hybrid_ref 行为与 Phase 3 兼容
shadow mode 仍不返回 pi_final 作为行为介入
gated_lite mode 仍返回 pi_final
posterior update 逻辑不变
leakage invariance 仍通过
```

- [ ] **Step 2: 最小实现**

可选实现方式：

```text
方案 A: agent.py 先 build_semantic_reference_policy，然后把 reference_audit["pi_ref"] 作为 strategy_reference 传入 compute_bayesian_policy_shadow，并在 agent.py 合并 audit。
方案 B: compute_bayesian_policy_shadow 增加 optional reference_audit 参数并在 helper 内合并。
```

推荐方案 A：

```text
更小改动；
不破坏现有 compute_bayesian_policy_shadow 调用；
更容易保证 Phase 3 兼容。
```

在 `compute_bayesian_policy_shadow` 内保持：

```text
strategy_reference -> pi_ref -> existing gated shift
```

不要在 helper 内重新读取 `strategy_deliberation`。

- [ ] **Step 3: 跑 tests**

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py -q
```

预期：通过。

---

## 9. Task 4: Agent Wiring

**Files:**

```text
Modify: examples/digital_friction_mvp/proto/agent.py
Modify: examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py
```

- [ ] **Step 1: 写 failing integration-ish tests**

如果现有 tests 没有直接 agent integration harness，至少在 helper 层验证：

```text
semantic_v2 不使用 strategy_deliberation.final_weights 作为 pi_ref
semantic_v2 使用 strategy_deliberation.llm_weights 构造 pi_semantic
semantic_v2 payload 中 rule_weights_audit_only 存在
gated_lite 模式下 pi_final 仍进入 precomputed_final_weights
off / shadow 不传 pi_final
```

- [ ] **Step 2: 修改 agent.py action choice 前链路**

当前 Phase 3 代码类似：

```python
compute_bayesian_policy_shadow(
    strategy_reference=strategy_deliberation.final_weights,
    ...
)
```

Phase 4 改为：

```python
reference_audit = build_semantic_reference_policy(
    reference_mode=runtime_config.proto_bayesian_policy_lite_reference_mode,
    hybrid_reference=strategy_deliberation.final_weights,
    llm_weights=strategy_deliberation.llm_weights,
    llm_confidence=strategy_deliberation.confidence,
    llm_reason=strategy_deliberation.reason,
    llm_status=strategy_deliberation.status,
    llm_source=strategy_deliberation.source,
    rule_weights=rule_strategy_weights,
    lambda_llm=runtime_config.proto_bayesian_policy_lite_lambda_llm,
    min_llm_confidence=runtime_config.proto_bayesian_policy_lite_min_llm_confidence,
)

compute_bayesian_policy_shadow(
    strategy_reference=reference_audit["pi_ref"],
    ...
)
```

然后把 `reference_audit` 合并进 `bayesian_policy_pre_audit`：

```python
bayesian_policy_pre_audit.update(reference_audit)
```

或使用明确前缀字段，避免覆盖已有 `pi_ref`。如果合并会覆盖，必须保证覆盖后的 `pi_ref` 与 helper 真实用于 gated shift 的 `pi_ref` 一致。

- [ ] **Step 3: 保持 gated_lite 行为入口不变**

继续使用：

```python
choose_attempt_strategy(..., precomputed_final_weights=gated_lite_final_weights)
```

不要新增 sampler 参数。

- [ ] **Step 4: 跑 tests**

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py examples/digital_friction_mvp/tests/test_runtime.py -q
```

预期：通过。

---

## 10. Task 5: Analysis Support

**Files:**

```text
Modify: examples/digital_friction_mvp/analysis_bayesian_policy_shadow.py
Optional Test: examples/digital_friction_mvp/tests/test_bayesian_policy_shadow_analysis.py
```

- [ ] **Step 1: 检查现有分析脚本字段**

确认是否已输出：

```text
mode
utility_profile
pi_attempt / pi_help / pi_avoid
confidence_by_action
posterior_entropy_by_action
actual action vs shadow/gated top action
payload coverage
uses_post_outcome_information_for_policy
```

- [ ] **Step 2: 为 Phase 4 增加输出列**

新增列：

```text
reference_mode
lambda_llm
min_llm_confidence
semantic_fallback_used
semantic_fallback_reason
rule_fallback_used
rule_fallback_reason
mean_semantic_delta_attempt
mean_semantic_delta_help
mean_semantic_delta_avoid
mean_bayesian_final_delta_attempt
mean_bayesian_final_delta_help
mean_bayesian_final_delta_avoid
rule_fallback_rate
semantic_fallback_rate
intervention_applied_rate
```

- [ ] **Step 3: 分析脚本测试**

如果已有 `test_bayesian_policy_shadow_analysis.py`，增加一个含 `semantic_v2` payload 的临时 SQLite case。

运行：

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_policy_shadow_analysis.py -q
```

如果当前仓库没有该测试或脚本，Phase 4A 可以先不阻塞实现，但 Phase 4B 前必须补齐。

---

## 11. Task 6: Full Regression

**Files:**

```text
No direct code change unless tests fail.
```

- [ ] **Step 1: Policy-lite + runtime tests**

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py examples/digital_friction_mvp/tests/test_runtime.py -q
```

预期：

```text
PASS
```

- [ ] **Step 2: Broader regression**

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_control_audit.py examples/digital_friction_mvp/tests/test_experience_memory.py examples/digital_friction_mvp/tests/test_llm_psychology.py examples/digital_friction_mvp/tests/test_stream_episode_recording.py -q
```

预期：

```text
PASS
```

- [ ] **Step 3: Compile**

```bash
python -m py_compile examples/digital_friction_mvp/config_runtime.py examples/digital_friction_mvp/proto/bayesian_policy_lite.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/proto/attempt_strategy.py examples/digital_friction_mvp/world_runner.py examples/digital_friction_mvp/analysis_bayesian_policy_shadow.py
```

预期：

```text
No output, exit 0
```

- [ ] **Step 4: Diff check**

```bash
git diff --check -- Phase4plan.md frictionchangeLog.md examples/digital_friction_mvp/config_runtime.py examples/digital_friction_mvp/proto/bayesian_policy_lite.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/world_runner.py examples/digital_friction_mvp/tests
```

预期：

```text
No whitespace errors
```

---

## 12. Phase 4A: Conservative Semantic Pilot

目的：

```text
验证 semantic_v2 不会导致 runaway、over-avoid、fallback 暴涨或 world direction 反转。
```

建议按三层推进：

```text
Phase 4A1:
  2-world smoke，用于验证 semantic_v2 接入、payload、fallback、基本方向。

Phase 4A2:
  加入 low_friction_high_assist sanity check，确认好环境不会被推向 over-avoid。

Phase 4A3:
  4-world conservative pilot，用于进入 Phase 4B 前的正式稳定性检查。
```

先跑 2 worlds，3 paired seeds：

```bash
cd /Users/pifazuoren/Downloads/AgentSociety-main

AGENT_COUNT=10 \
STAGE_MODE=single \
STAGE_SINGLE_NAME=steady \
STAGE_DAYS=10 \
EVENT_DECISION_INTERVAL_MINUTES=60 \
PROTO_LOGICAL_CLOCK_ENABLED=1 \
PROTO_LLM_PSYCHOLOGY_MODE=hybrid \
PROTO_LLM_TASK_APPRAISAL_ENABLED=1 \
PROTO_LLM_EVENT_APPRAISAL_ENABLED=1 \
PROTO_LLM_DAILY_REFLECTION_ENABLED=1 \
PROTO_LLM_STRATEGY_DELIBERATION_ENABLED=1 \
PROTO_LLM_STAGE_INTERVIEW_ENABLED=1 \
PROTO_LLM_FINAL_INTERVIEW_ENABLED=1 \
PROTO_LLM_UNCONTROLLABILITY_MODE=hybrid \
PROTO_STREAM_EPISODE_RECORDING_ENABLED=1 \
PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED=1 \
PROTO_STREAM_ATTRIBUTION_RETRIEVAL_ENABLED=1 \
PROTO_BAYESIAN_POLICY_LITE_MODE=gated_lite \
PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE=semantic_v2 \
PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE=theory_v2 \
PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM=0.25 \
PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE=0.50 \
PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD=0.50 \
PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD=0.85 \
PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA=0.05 \
PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR=0.05 \
python examples/digital_friction_mvp/world_runner.py \
  --group-id exp_20260513_policy_lite_semantic_v2_gated_lite_pilot_2world_10d_60min \
  --seed-list 101,201,301 \
  --world-batch baseline_low_friction,high_friction_low_assist \
  --summarize-paired \
  --paired-baseline-world baseline_low_friction \
  --paired-direction-overrides high_friction_low_assist=worse_than_baseline
```

通过标准：

```text
payload coverage = 1.0
uses_post_outcome_information_for_policy 始终 false
safety_guard fallback 不频繁
semantic_fallback_used 不频繁
rule_fallback_used 接近 0
intervention_applied 有但不过度
mean total_variation_distance 小于 Phase 4 预设安全阈值，建议先看 < 0.03
high_friction_low_assist 不出现异常低 helplessness 或异常高 success
baseline_low_friction 不被推向过度 avoid
world paired direction 仍符合 worse_than_baseline
```

如果 2-world pilot 稳定，先补一个 3-world sanity check：

```bash
cd /Users/pifazuoren/Downloads/AgentSociety-main

AGENT_COUNT=10 \
STAGE_MODE=single \
STAGE_SINGLE_NAME=steady \
STAGE_DAYS=10 \
EVENT_DECISION_INTERVAL_MINUTES=60 \
PROTO_LOGICAL_CLOCK_ENABLED=1 \
PROTO_LLM_PSYCHOLOGY_MODE=hybrid \
PROTO_LLM_TASK_APPRAISAL_ENABLED=1 \
PROTO_LLM_EVENT_APPRAISAL_ENABLED=1 \
PROTO_LLM_DAILY_REFLECTION_ENABLED=1 \
PROTO_LLM_STRATEGY_DELIBERATION_ENABLED=1 \
PROTO_LLM_STAGE_INTERVIEW_ENABLED=1 \
PROTO_LLM_FINAL_INTERVIEW_ENABLED=1 \
PROTO_LLM_UNCONTROLLABILITY_MODE=hybrid \
PROTO_STREAM_EPISODE_RECORDING_ENABLED=1 \
PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED=1 \
PROTO_STREAM_ATTRIBUTION_RETRIEVAL_ENABLED=1 \
PROTO_BAYESIAN_POLICY_LITE_MODE=gated_lite \
PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE=semantic_v2 \
PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE=theory_v2 \
PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM=0.25 \
PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE=0.50 \
PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD=0.50 \
PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD=0.85 \
PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA=0.05 \
PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR=0.05 \
python examples/digital_friction_mvp/world_runner.py \
  --group-id exp_20260513_policy_lite_semantic_v2_gated_lite_sanity_3world_10d_60min \
  --seed-list 101,201,301 \
  --world-batch baseline_low_friction,high_friction_low_assist,low_friction_high_assist \
  --summarize-paired \
  --paired-baseline-world baseline_low_friction \
  --paired-direction-overrides high_friction_low_assist=worse_than_baseline,low_friction_high_assist=better_than_baseline
```

3-world sanity 的特殊检查：

```text
low_friction_high_assist avoid_rate 不应高于 baseline 太多；
low_friction_high_assist help_seek_rate 或 success_rate 应保持相对优势；
low_friction_high_assist 不应出现 semantic_v2 over-avoid。
```

如果 3-world sanity 稳定，再跑 4 worlds，3 paired seeds：

```bash
cd /Users/pifazuoren/Downloads/AgentSociety-main

AGENT_COUNT=10 \
STAGE_MODE=single \
STAGE_SINGLE_NAME=steady \
STAGE_DAYS=10 \
EVENT_DECISION_INTERVAL_MINUTES=60 \
PROTO_LOGICAL_CLOCK_ENABLED=1 \
PROTO_LLM_PSYCHOLOGY_MODE=hybrid \
PROTO_LLM_TASK_APPRAISAL_ENABLED=1 \
PROTO_LLM_EVENT_APPRAISAL_ENABLED=1 \
PROTO_LLM_DAILY_REFLECTION_ENABLED=1 \
PROTO_LLM_STRATEGY_DELIBERATION_ENABLED=1 \
PROTO_LLM_STAGE_INTERVIEW_ENABLED=1 \
PROTO_LLM_FINAL_INTERVIEW_ENABLED=1 \
PROTO_LLM_UNCONTROLLABILITY_MODE=hybrid \
PROTO_STREAM_EPISODE_RECORDING_ENABLED=1 \
PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED=1 \
PROTO_STREAM_ATTRIBUTION_RETRIEVAL_ENABLED=1 \
PROTO_BAYESIAN_POLICY_LITE_MODE=gated_lite \
PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE=semantic_v2 \
PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE=theory_v2 \
PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM=0.25 \
PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE=0.50 \
PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD=0.50 \
PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD=0.85 \
PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA=0.05 \
PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR=0.05 \
python examples/digital_friction_mvp/world_runner.py \
  --group-id exp_20260513_policy_lite_semantic_v2_gated_lite_pilot_4world_10d_60min \
  --seed-list 101,201,301 \
  --world-batch baseline_low_friction,high_friction_low_assist,high_friction_high_assist,low_friction_high_assist \
  --summarize-paired \
  --paired-baseline-world baseline_low_friction \
  --paired-direction-overrides high_friction_low_assist=worse_than_baseline,low_friction_high_assist=better_than_baseline
```

---

## 13. Phase 4B: Main Experiment

前提：

```text
Phase 4A 2-world pilot 稳定
Phase 4A 4-world pilot 稳定
analysis script 能输出 reference_mode / semantic fallback / rule fallback / intervention metrics
```

建议主实验：

```text
10 paired seeds
4 worlds
10 agents
10 days
single steady stage
```

主实验组：

```text
baseline rule+LLM hybrid without Bayesian intervention
shadow-only theory_v2
gated_lite hybrid_ref theory_v2
gated_lite semantic_v2 theory_v2
semantic_v2 max_delta=0
```

最小必要 ablation：

```text
semantic_v2 + max_delta=0
semantic_v2 + gated_lite max_delta=0.05
hybrid_ref + gated_lite max_delta=0.05
shadow-only theory_v2
```

如果算力允许，再加：

```text
semantic_v2 lambda_llm=0.10
semantic_v2 lambda_llm=0.50
semantic_v2 gate_threshold=0.70
semantic_v2 entropy_threshold=0.75
semantic_v2 max_delta=0.10 stress test
```

注意：

```text
max_delta=0.10 只能作为 sensitivity / stress test，不建议作为默认主结果。
```

Phase 4B 最小必跑集：

```text
1. baseline rule+LLM hybrid without Bayesian intervention
2. shadow-only theory_v2
3. gated_lite hybrid_ref theory_v2
4. gated_lite semantic_v2 theory_v2
5. semantic_v2 max_delta=0
```

这 5 组分别回答：

```text
baseline rule+LLM:
  当前主链的基线表现。

shadow-only theory_v2:
  Bayesian posterior 有无解释信号，但不改变行为。

gated_lite hybrid_ref:
  Phase 3 机制在同规模下的行为效果。

gated_lite semantic_v2:
  Phase 4 rule-reduced reference policy 的主要结果。

semantic_v2 max_delta=0:
  只改变 reference policy，不做 Bayesian shift，用来分离 semantic policy 和 Bayesian intervention 的贡献。
```

Phase 4B sensitivity 至少包含：

```text
lambda_llm = 0.10 / 0.25 / 0.50
```

`0.10` 检查 LLM semantic signal 过弱时的下限；`0.50` 检查更强 LLM semantic adjustment 是否带来 over-avoid 或 instability。

Seed 数量说明：

```text
Phase 4B 的 10 paired seeds 是最低工程线，不是 paper-facing 强证据线。
如果算力和时间允许，论文核心结果应考虑扩展到 20 paired seeds，或至少对关键指标报告 bootstrap confidence interval / paired CI。
```

---

## 14. 主要分析指标

World-level behavioral outcomes：

```text
attempt_rate
help_seek_rate
avoid_rate
success_rate
negative_feedback_rate
abandon_rate
helplessness_delta
trust_delta
avoidance_delta
```

Mechanism audit：

```text
intervention_applied_rate
gate_open_rate
mean total_variation_distance
max total_variation_distance
mean semantic_delta_from_prior
mean final_delta_after_floor
posterior confidence trajectory
posterior entropy trajectory
semantic_fallback_rate
rule_fallback_rate
safety_guard fallback rate
```

Semantic reference analysis：

```text
mean pi_prior by world
mean pi_llm by world
mean pi_semantic by world
mean pi_ref by world
mean pi_bayes by world
mean pi_final by world
shadow/gated top-action distribution by world
semantic_delta_from_prior by action
final_delta_after_floor by action
mean_delta_applied_by_action
mean_bayesian_shift_before_floor_by_action
lambda_llm sensitivity
```

Bayesian shift 与 probability floor 必须分开看：

```text
delta_applied:
  evidence gate + confidence scaling + max_delta 后，Bayesian posterior 真正尝试施加的 action-level shift。

bayesian_shift_before_floor:
  pi_after_bayesian_shift - pi_ref，用来衡量 floor/renormalization 前的 Bayesian policy effect。

final_delta_after_floor:
  pi_final - pi_ref，包含 Bayesian shift、probability floor 和 final renormalization 的综合效果。
```

分析时不要只报告 `final_delta_after_floor`，否则无法回答：

```text
到底是 Bayesian posterior 在改概率，还是 probability floor 在改概率？
```

Claim support：

```text
semantic_v2 是否减少 rule-heavy dependence
Bayesian posterior 是否只在证据足够时介入
介入是否保守且可审计
world manipulation direction 是否保持合理
helplessness / avoidance 是否没有 runaway
```

---

## 15. Changelog

实施完成后追加到：

```text
frictionchangeLog.md
```

标题：

```text
### Bayesian policy-lite Phase 4 semantic gated-lite2 reference policy
```

内容必须写清楚：

```text
新增 PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE=hybrid_ref|semantic_v2
新增 PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM
新增 PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE
默认 hybrid_ref 保持 Phase 3 兼容
semantic_v2 使用 weak prior + bounded LLM semantic adjustment 构造 pi_ref
rule_weights 在 semantic_v2 中 audit-only，不进入常规策略混合
Bayesian gated shift / confidence gate / entropy gate / max_delta / prob_floor 复用 Phase 3
不改变 outcome、helplessness、attribution、scope spillover、experience memory、stream memory、DB schema
记录测试命令与结果
记录 Phase 4A pilot 实验 group id 与核心结果
```

---

## 16. Go / No-Go 标准

可以进入 Phase 4A 的条件：

```text
runtime tests pass
policy-lite tests pass
broader regression pass
py_compile pass
diff check pass
semantic_v2 payload 字段完整
hybrid_ref 兼容 Phase 3
```

可以进入 Phase 4B 的条件：

```text
Phase 4A 2-world pilot 无 safety runaway
Phase 4A 3-world sanity 中 low_friction_high_assist 未出现 over-avoid
Phase 4A 4-world pilot world direction 合理
semantic_fallback_rate 不高
rule_fallback_rate 接近 0
intervention_applied_rate 不是 0，也不是接近 1
mean TVD 保守
helplessness 没有 runaway
```

建议第一版工程安全阈值：

```text
semantic_fallback_rate < 20%
rule_fallback_rate < 5%
safety_guard_fallback_rate < 5%
mean total_variation_distance < 0.03
max total_variation_distance < 0.08
low_friction_high_assist avoid_rate 不显著高于 baseline_low_friction
high_friction_low_assist 仍 worse_than_baseline
```

这些阈值是 Phase 4A/4B 的工程 go/no-go guard，不是论文最终统计阈值。后续可根据 3-seed pilot 分布重新校准。

不可以进入论文主 claim 的情况：

```text
semantic_v2 大量 fallback 到 prior
rule_fallback_used 频繁
pi_final 经常被 safety guard 修正
high_friction_low_assist 反而显著优于 baseline
low_friction_high_assist 被推向高 avoid
max_delta=0 与 max_delta=0.05 没有任何可解释差异
ablation / sensitivity 尚未完成
```

---

## 17. Phase 4 完成后可声称什么

Phase 4A 完成后可以说：

```text
We implemented a direct-rule-reduced semantic gated-lite2 action construction and verified its safety in conservative pilot runs.
```

更完整的边界说明：

```text
semantic_v2 removes direct rule mixing from pi_ref, while the current LLM deliberation may still use rule weights as contextual reference.
```

Phase 4B + ablation/sensitivity 完成后可以说：

```text
The agent's action choice is generated by a weak-prior LLM semantic policy with a bounded Bayesian posterior predictive shift, and the shift is auditable, evidence-gated, and behaviorally consequential under controlled simulation conditions.
```

仍然不要说：

```text
We implement Huys & Dayan's full Bayesian RL model.
The mechanism is externally validated on real older adults.
Bayesian posterior alone controls the agent.
```
