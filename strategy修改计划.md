# Strategy LLM Rich Context Implementation Plan

> **For agentic workers:** REQUIRED: Implement this plan step by step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `strategy_deliberation` LLM 在输出 `attempt_self / seek_help_then_attempt / avoid` 策略分数时，也能看到更丰富的个人画像、任务相关记忆、近期经历和检索到的 episodic memory 摘要，从而让 `pi_ref` 更像具体 agent 的语义判断。它只增强 `llm_weights -> semantic_v2 pi_ref` 这一路，不改变 downstream Bayesian / controllability / helplessness 机制。

**Architecture:** 保留当前两阶段结构：`task_appraisal` 继续只负责评估任务，不直接选 action；`strategy_deliberation` 继续只负责三策略分数。最小改动是在 `agent.py` 调用 `resolve_strategy_deliberation(...)` 时透传已有上下文，在 `llm_psychology.py` 的 strategy prompt 中加入这些上下文块，不新增 sampler、不改 Phase4/Phase5C 数学逻辑、不改 DB schema。

**Tech Stack:** Python, pytest, existing `examples/digital_friction_mvp/proto` modules, existing JSON-only LLM prompt/sanitize pattern.

---

## Current State

当前 `task_appraisal` LLM 已经能看到较丰富的信息：

```text
Agent Profile
Current Task
World / Stage Context
Current Status
Task-Specific Memory
Recent Experience
Retrieved Episodic Memory
Digital Emotion State
```

但 `strategy_deliberation` LLM 当前直接看到的输入较窄：

```text
task
task_appraisal
effective_helplessness
task_self_efficacy
help_success_rate_smoothed
recent_negative_feedback_ratio
recent_same_task_failure_count
digital_emotion_state
daily_reflection
rule_weights
```

因此 `pi_ref` 的个人化主要是间接来的：个人画像和记忆先影响 `task_appraisal`，再由 `task_appraisal` 影响 `strategy_deliberation`。本计划要做的是让 `strategy_deliberation` 也直接看到已有的压缩上下文，但仍保持它只输出三种合法 action 的分数。

## Core Interpretation

这个改动不是新增一套心理更新规则，也不是让 LLM 重新判断 helplessness。

更准确的定位是：

```text
task_appraisal = 当前任务的主观评价摘要
strategy_deliberation = 在该评价摘要下，对三种行动策略的语义偏好评分
```

因此，rich context 的作用是帮助 `strategy_deliberation` 回答：

```text
对于这个具体 agent，在当前 task_appraisal 已经给定的情况下，
attempt_self / seek_help_then_attempt / avoid 哪个更像合理的下一步？
```

而不是让它重新回答：

```text
这个任务到底难不难？
这个任务到底可不可控？
这个 agent 的 helplessness 应该涨多少？
```

必须避免的双重计入风险：

```text
profile/memory -> task_appraisal already affects felt_control / risk / difficulty
profile/memory -> strategy_deliberation should only affect action preference among allowed strategies
```

例如，过去失败很多可以让 strategy LLM 更理解为什么 `avoid` 或 `seek_help` 有吸引力，但它不应该再把 `felt_control` 重新打低一遍，也不应该输出任何新的 psychological delta。

## AgentSociety Native Prompt Patterns To Reuse

本计划应参考 AgentSociety 原生 prompt 的写法，但不直接复制原生城市生活 prompt 的业务语义。

已核查的本地文件：

```text
packages/agentsociety-community/agentsociety_community/agents/citizens/cityagent/plan_block.py
packages/agentsociety-community/agentsociety_community/agents/citizens/cityagent/needs_block.py
packages/agentsociety-community/agentsociety_community/agents/citizens/cityagent/societyagent.py
packages/agentsociety/agentsociety/cityagent/blocks/social_block.py
packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py
packages/agentsociety/agentsociety/agent/prompt.py
examples/digital_friction_mvp/analysis/agentsociety_native_prompts_zh.md
```

可复用模式：

1. **分块给上下文。**
   原生 prompt 通常把输入分为 profile、current need/intention、environment、emotion、thought、history/options。我们的 strategy prompt 也应把信息分成清楚的 JSON blocks，而不是拼成一段长文本。

2. **画像 + 情绪 + 当前想法一起出现。**
   原生 `PlanBlock` / `SocialBlock` / `CognitionBlock` 都会把 age、occupation、education/personality、emotion、thought 放在决策上下文里。我们的 strategy LLM 应至少看到 `agent_profile`、`digital_emotion_state`、`daily_reflection`。

3. **先给候选集合，再让 LLM 在候选集合内选择/评分。**
   原生 plan prompt 会给 guidance options，dispatcher 会给 block schema，social prompt 会给社交网络候选。我们的候选集合固定为：

   ```text
   attempt_self
   seek_help_then_attempt
   avoid
   ```

   LLM 不得新增 action。

4. **明确评价维度。**
   原生 `GUIDANCE_SELECTION_PROMPT` 使用 attitude / subjective norm / perceived control 三个维度。我们的 strategy prompt 不需要照搬这三个维度，但可以明确要求模型分别考虑：

   ```text
   task appraisal
   agent profile
   task-specific memory
   recent experience
   help effectiveness
   emotional state
   daily reflection / mastery signal
   rule weights as baseline
   ```

5. **JSON-only 输出 + schema repair / parse guard。**
   原生 block 常用 `response_format={"type": "json_object"}` 和 `json_repair`。我们当前 `_query_json_payload(...)` 已经有 strict JSON、repair、sanitize、fallback，因此应继续复用现有机制，不新增独立解析器。

6. **不要把 memory 全量塞入 prompt。**
   原生 cognition/social prompt 会检索或截取相关 memory，而不是无边界塞所有状态。我们的实现也只传现有压缩摘要和截断后的 retrieved text。

不要照搬的部分：

- 不把当前 `_query_json_payload(...)` 改成 `FormatPrompt`；当前模块已经有统一 JSON repair/sanitize/fallback，迁移会扩大改动面。
- 不直接读取 `self.memory.status` 于 `llm_psychology.py`；保持当前函数式传参风格，由 `agent.py` 负责取 memory。
- 不引入原生 cityagent 的 `attitude/subjective_norm/perceived_control` 作为新输出字段；只把它作为 prompt 组织风格参考。

落地含义：

```text
strategy_deliberation 不改成自由文本推理器；
它仍然是 bounded JSON module；
只是 user_payload 更像原生 AgentSociety prompt：有画像、有当前状态、有相关记忆、有候选动作、有严格输出。
```

## Hard Boundaries

- 不合并 `task_appraisal` 和 `strategy_deliberation`。
- 不让 `task_appraisal` 输出策略分数。
- 不新增 action。
- 不新增 sampler。
- 不改 outcome model。
- 不改 helplessness / attribution / scope_spillover 更新。
- 不改 DB schema。
- 不新增 env key。
- 不新增低层抽象或独立 context builder，除非测试证明现有函数无法承载。
- 不把完整原始 memory 全量塞进 prompt；只传已有的压缩摘要和检索文本摘要。
- 不改 `pi_ref` 公式；仍由 `build_semantic_reference_policy(...)` 用 `llm_weights` 和 `pi_prior` 混合得到。
- 不让 strategy prompt 重估 `task_appraisal` 中已经给出的 difficulty / risk / felt_control / expected_help_effectiveness / task_value。
- 不让 strategy prompt 输出 helplessness、self-efficacy、controllability、posterior 或任何 state delta。

## Intended Flow

修改后主链保持：

```text
profile_summary / task_relevant_memory / recent_episode_summary / retrieved episodic memory
-> task_appraisal LLM
-> strategy_deliberation LLM
-> llm_weights
-> semantic_v2 pi_ref
-> Bayesian action-outcome posterior / Phase4 pi_final
-> Phase5C control-centered modulation
-> sampler
```

关键变化只有一处：

```text
strategy_deliberation LLM 也能看到 profile/memory/retrieval context
```

而不是：

```text
task_appraisal 直接决定 action
```

---

## File Map

### Modify: `examples/digital_friction_mvp/proto/llm_psychology.py`

Responsibilities:

- 扩展 `resolve_strategy_deliberation(...)` 的可选参数。
- 把新增上下文加入 LLM user payload。
- 扩展 strategy deliberation cache key，避免不同 profile/memory context 命中同一个缓存。
- 对传入 strategy prompt 的 rich context 做轻量 sanitization / truncation，尤其是长文本字段。
- 保留现有 JSON schema、sanitize、repair、fallback 逻辑。

### Modify: `examples/digital_friction_mvp/proto/agent.py`

Responsibilities:

- 在调用 `resolve_strategy_deliberation(...)` 时传入已有上下文：

```python
profile_summary=profile_summary
task_relevant_memory=task_relevant_memory_packet
recent_episode_summary=recent_episode_summary
retrieved_episodic_memory=task_appraisal_retrieval_packet
```

这些变量在当前调用点之前已经存在，不需要新建数据流。

### Modify: `examples/digital_friction_mvp/tests/test_llm_psychology.py`

Responsibilities:

- 覆盖 strategy prompt 中新增上下文块。
- 覆盖新增上下文会影响 cache key。
- 覆盖低 confidence / invalid schema fallback 不变。

### Optional Docs: `frictionchangeLog.md`

Responsibilities:

- 只有在实现并测试通过后记录真实改动和真实命令。
- 不提前写实验结论。

---

## Task 1: Add Rich Context Parameters To Strategy Deliberation

**Files:**

- Modify: `examples/digital_friction_mvp/proto/llm_psychology.py`
- Test: `examples/digital_friction_mvp/tests/test_llm_psychology.py`

- [ ] **Step 1: Write failing test for rich context in LLM payload**

Add a test using the existing fake LLM pattern in `test_llm_psychology.py`.

The test should call `resolve_strategy_deliberation(...)` with:

```python
profile_summary = {
    "age": 72,
    "persona": "cautious older adult",
    "digital_experience": 0.25,
    "past_fraud_experience": 0.8,
}
task_relevant_memory = {
    "same_task_failure_count": 3,
    "same_task_failure_streak": 2,
    "same_task_controllable_success_memory": 0.1,
    "help_success_rate_same_task": 0.75,
    "recent_same_task_outcomes_tail": ["failure", "help_success"],
}
recent_episode_summary = {
    "recent_negative_feedback_ratio": 0.6,
    "recent_avoid_ratio": 0.25,
    "recent_help_seek_ratio": 0.4,
    "recent_same_task_failure_count": 3,
    "recent_failure_pressure": 12.0,
}
retrieved_episodic_memory = {
    "condition": "retrieved",
    "status": "ok",
    "count": 2,
    "hash": "abc123",
    "text": "Past login attempts failed until a family member helped.",
}
```

Expected assertion:

```python
assert captured_user_payload["agent_profile"] == profile_summary
assert captured_user_payload["task_relevant_memory"]["same_task_failure_count"] == 3
assert captured_user_payload["recent_episode_summary"]["recent_negative_feedback_ratio"] == 0.6
assert "family member helped" in captured_user_payload["retrieved_episodic_memory"]["text"]
assert captured_user_payload["allowed_strategies"] == [
    "attempt_self",
    "seek_help_then_attempt",
    "avoid",
]
assert "rule weights as baseline" in " ".join(
    captured_user_payload["decision_dimensions"]
)
```

Use the exact payload key names from implementation. Prefer lowercase snake_case keys to keep strategy payload compact:

```text
agent_profile
task_relevant_memory
recent_episode_summary
retrieved_episodic_memory
```

- [ ] **Step 2: Run focused failing test**

Run:

```bash
python -m pytest examples/digital_friction_mvp/tests/test_llm_psychology.py::test_strategy_deliberation_includes_profile_and_memory_context -q
```

Expected: FAIL because `resolve_strategy_deliberation(...)` does not yet accept/pass the new context.

- [ ] **Step 3: Extend function signature minimally**

In `resolve_strategy_deliberation(...)`, add optional keyword-only parameters after `daily_reflection`:

```python
profile_summary: Any = None,
task_relevant_memory: Any = None,
recent_episode_summary: Any = None,
retrieved_episodic_memory: Any = None,
```

Do not make them required; existing tests and callers should keep working.

- [ ] **Step 4: Add context to strategy user payload**

Inside the `_query_json_payload(...)` call for strategy deliberation, add:

```python
"agent_profile": (
    copy.deepcopy(profile_summary)
    if isinstance(profile_summary, dict)
    else {}
),
"task_relevant_memory": (
    copy.deepcopy(task_relevant_memory)
    if isinstance(task_relevant_memory, dict)
    else {}
),
"recent_episode_summary": (
    copy.deepcopy(recent_episode_summary)
    if isinstance(recent_episode_summary, dict)
    else {}
),
"retrieved_episodic_memory": {
    "condition": str((retrieved_episodic_memory or {}).get("condition", "structured-only"))
    if isinstance(retrieved_episodic_memory, dict)
    else "structured-only",
    "status": str((retrieved_episodic_memory or {}).get("status", "disabled"))
    if isinstance(retrieved_episodic_memory, dict)
    else "disabled",
    "count": int((retrieved_episodic_memory or {}).get("count", 0) or 0)
    if isinstance(retrieved_episodic_memory, dict)
    else 0,
    "hash": str((retrieved_episodic_memory or {}).get("hash", ""))
    if isinstance(retrieved_episodic_memory, dict)
    else "",
    "text": str((retrieved_episodic_memory or {}).get("text", "Nothing"))[:900]
    if isinstance(retrieved_episodic_memory, dict)
    else "Nothing",
},
```

If this inline block feels too noisy during implementation, use a tiny private helper only for retrieved memory sanitization. Do not introduce a large new context abstraction.

Recommended minimal sanitization rules:

```text
profile_summary: keep dict fields, truncate long string values to <= 240 chars
task_relevant_memory: keep existing numeric/categorical fields, truncate attribution summaries to <= 300 chars
recent_episode_summary: keep numeric ratio/count/pressure fields only
retrieved_episodic_memory.text: truncate to <= 900 chars
```

Do not pass full raw memory lists, full chat histories, full event logs, posterior tables, or future outcome labels into the strategy prompt.

- [ ] **Step 5: Keep role boundary explicit in prompt**

Update the strategy deliberation system prompt from:

```text
You are a strict JSON-only bounded strategy deliberation module...
```

to include these extra constraints:

```text
Use profile and memory context only to score the three allowed strategies.
Treat task_appraisal as the authoritative current appraisal summary.
Do not re-score task difficulty, risk, felt control, help effectiveness, or task value.
Do not revise task_appraisal scores.
Do not invent new actions.
Do not output recommendations outside the JSON schema.
Do not output helplessness, self-efficacy, controllability, posterior updates, or state deltas.
```

In the user payload, keep the native AgentSociety style of labeled decision context. The JSON object should make these blocks easy to inspect in captured tests:

```text
task
task_appraisal
agent_profile
task_relevant_memory
recent_episode_summary
retrieved_episodic_memory
digital_emotion_state
daily_reflection
rule_weights
allowed_strategies
decision_dimensions
output_schema_example
```

Add two explicit guidance fields to the payload:

```python
"allowed_strategies": [
    "attempt_self",
    "seek_help_then_attempt",
    "avoid",
],
"decision_dimensions": [
    "task appraisal as authoritative summary: difficulty, risk, felt control, help effectiveness, task value",
    "agent profile: age, digital experience, fraud/risk background, persona",
    "task-specific memory: same-family failure/success/help history",
    "recent experience: negative feedback, avoidance, help-seeking, failure pressure",
    "emotional state and daily reflection",
    "rule weights as baseline, not as a command",
],
```

Do not change output schema.

- [ ] **Step 6: Run focused test**

Run:

```bash
python -m pytest examples/digital_friction_mvp/tests/test_llm_psychology.py::test_strategy_deliberation_includes_profile_and_memory_context -q
```

Expected: PASS.

---

## Task 2: Wire Existing Agent Context Into Strategy Deliberation

**Files:**

- Modify: `examples/digital_friction_mvp/proto/agent.py`
- Test: `examples/digital_friction_mvp/tests/test_llm_psychology.py` or existing integration-style agent tests if available.

- [ ] **Step 1: Modify the existing call site**

In `agent.py`, find the existing call:

```python
strategy_deliberation = await resolve_strategy_deliberation(
    llm=getattr(self, "llm", None),
    task=task,
    task_appraisal=task_appraisal.to_dict(),
    effective_helplessness=memory_features.effective_helplessness,
    task_self_efficacy=memory_features.task_self_efficacy,
    help_success_rate_smoothed=memory_features.help_success_rate_smoothed,
    recent_negative_feedback_ratio=memory_features.recent_negative_feedback_ratio,
    recent_same_task_failure_count=memory_features.recent_same_task_failure_count,
    digital_emotion_state=digital_emotion_state.to_dict(),
    daily_reflection=current_daily_reflection,
    rule_weights=rule_strategy_weights,
)
```

Add:

```python
profile_summary=profile_summary,
task_relevant_memory=task_relevant_memory_packet,
recent_episode_summary=recent_episode_summary,
retrieved_episodic_memory=task_appraisal_retrieval_packet,
```

Use the variables already computed earlier in the method. Do not recompute memory.

- [ ] **Step 2: Run py_compile**

Run:

```bash
python -m py_compile \
  examples/digital_friction_mvp/proto/agent.py \
  examples/digital_friction_mvp/proto/llm_psychology.py
```

Expected: PASS.

---

## Task 3: Update Strategy Cache Key To Respect New Context

**Files:**

- Modify: `examples/digital_friction_mvp/proto/llm_psychology.py`
- Test: `examples/digital_friction_mvp/tests/test_llm_psychology.py`

Current strategy cache key already includes:

```text
task family
difficulty bucket
effective helplessness bucket
self-efficacy bucket
help success bucket
failure bucket
negative feedback bucket
felt_control bucket
expected_help_effectiveness bucket
task_value bucket
emotion buckets
mastery_signal
```

After adding richer context, avoid cache collisions where two agents share those coarse values but have different profile or memory context.

Also add a strategy prompt/cache version string. Current task appraisal cache already has `_TASK_APPRAISAL_PROMPT_VERSION`; strategy deliberation should mirror this pattern so that prompt changes do not reuse stale cached LLM outputs.

- [ ] **Step 1: Write failing cache-key test**

Add a test that calls the private cache-key builder, or calls `resolve_strategy_deliberation(...)` twice with cache enabled and different profile/memory context.

Expected behavior:

```text
different profile/memory context should produce different cache keys
```

Minimum cache-key additions:

```text
_STRATEGY_DELIBERATION_PROMPT_VERSION
age_bucket(profile.age)
education_bucket(profile.education)
persona_bucket(profile.persona, profile.background_summary)
profile_bucket(profile.digital_experience)
profile_bucket(profile.past_fraud_experience)
same_task_history_bucket(task_relevant_memory)
profile_bucket(task_relevant_memory.same_task_controllable_success_memory)
recent_outcome_pattern_bucket(task_relevant_memory.recent_same_task_outcomes_tail)
recent_episode_summary.recent_avoid_ratio bucket
recent_episode_summary.recent_help_seek_ratio bucket
recent_episode_summary.recent_failure_pressure bucket
retrieved condition/status/count/hash
```

These helper bucket functions already exist for task appraisal cache. Reuse them; do not create parallel bucket logic.

- [ ] **Step 2: Extend `_build_strategy_deliberation_cache_key(...)` signature**

Add optional parameters:

```python
profile_summary: Any = None,
task_relevant_memory: Any = None,
recent_episode_summary: Any = None,
retrieved_episodic_memory: Any = None,
```

Add a module-level version constant if absent:

```python
_STRATEGY_DELIBERATION_PROMPT_VERSION = "v2_profile_memory_strategy_context_20260518"
```

Use existing bucket helpers:

```python
age_bucket(...)
_education_bucket(...)
persona_bucket(...)
_profile_bucket(...)
_same_task_history_bucket(...)
_recent_outcome_pattern_bucket(...)
_help_rate_bucket(...) for recent ratios
_failure_bucket(...) for recent failure pressure bucket
```

Do not include full raw text in cache key. Use retrieved metadata:

```text
condition
status
count
hash
```

- [ ] **Step 3: Pass new context into cache-key builder**

In `resolve_strategy_deliberation(...)`, pass the new optional context values into `_build_strategy_deliberation_cache_key(...)`.

- [ ] **Step 4: Run cache-key test**

Run:

```bash
python -m pytest examples/digital_friction_mvp/tests/test_llm_psychology.py::test_strategy_deliberation_cache_key_includes_profile_and_memory_context -q
```

Expected: PASS.

---

## Task 4: Preserve Existing Fallback And Schema Behavior

**Files:**

- Test: `examples/digital_friction_mvp/tests/test_llm_psychology.py`

- [ ] **Step 1: Run existing strategy deliberation tests**

Run:

```bash
python -m pytest examples/digital_friction_mvp/tests/test_llm_psychology.py -q
```

Expected: PASS.

Pay attention to existing tests around:

```text
parses_json_and_blends_weights
low_confidence_keeps_rule_weights
invalid schema fallback
disabled mode fallback
```

- [ ] **Step 2: Add regression assertion for output schema unchanged**

In the rich-context test, assert that the returned result still only affects existing `StrategyDeliberationResult` fields:

```python
assert result.llm_weights is not None
assert set(result.llm_weights) == {
    "attempt_self",
    "seek_help_then_attempt",
    "avoid",
}
assert abs(sum(result.llm_weights.values()) - 1.0) < 1e-9
```

Do not add new action keys.

---

## Task 5: Verify Bayesian `pi_ref` Path Still Works

**Files:**

- Test: `examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py`
- Optional Test: `examples/digital_friction_mvp/tests/test_llm_psychology.py`

- [ ] **Step 1: Run semantic reference tests**

Run:

```bash
python -m pytest examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py -q
```

Expected: PASS.

This verifies:

```text
semantic_v2 still blends pi_prior and llm_weights
invalid llm_weights still fall back
low LLM confidence still falls back
inputs are not mutated
```

- [ ] **Step 2: Confirm no Phase4/Phase5C contract change**

Run:

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_bayesian_controllability_lite.py \
  examples/digital_friction_mvp/tests/test_runtime.py \
  examples/digital_friction_mvp/tests/test_huys_dayan_lite_controllability_analysis.py \
  -q
```

Expected: PASS.

If these test files are absent in a clean main checkout, run the subset that exists and document the absence in `frictionchangeLog.md`.

---

## Task 6: Optional Changelog Entry After Implementation

**Files:**

- Modify: `frictionchangeLog.md`

- [ ] **Step 1: Add a short dated entry only after tests pass**

Suggested wording:

```markdown
## 2026-05-18 Strategy LLM context enrichment

- Extended `resolve_strategy_deliberation(...)` so the strategy LLM receives existing compressed context: `profile_summary`, `task_relevant_memory_packet`, `recent_episode_summary`, and retrieved episodic memory metadata/text.
- Preserved the existing three-action JSON schema and fallback behavior.
- Did not merge task appraisal with strategy deliberation; task appraisal remains evaluation-only.
- Did not change sampler, outcome model, Phase4 Bayesian policy math, Phase5C controllability math, DB schema, or runtime env keys.
- Verification:
  - `<paste exact pytest/py_compile commands and results>`
```

Do not record expected experimental effects until a new experiment is actually run.

---

## Verification Commands

Run focused tests:

```bash
python -m pytest examples/digital_friction_mvp/tests/test_llm_psychology.py -q
```

Run policy/controllability regression:

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py \
  examples/digital_friction_mvp/tests/test_bayesian_controllability_lite.py \
  examples/digital_friction_mvp/tests/test_runtime.py \
  examples/digital_friction_mvp/tests/test_huys_dayan_lite_controllability_analysis.py \
  -q
```

Run compile check:

```bash
python -m py_compile \
  examples/digital_friction_mvp/proto/agent.py \
  examples/digital_friction_mvp/proto/llm_psychology.py \
  examples/digital_friction_mvp/proto/bayesian_policy_lite.py \
  examples/digital_friction_mvp/proto/bayesian_controllability_lite.py
```

Run diff hygiene:

```bash
git diff --check
```

---

## Acceptance Criteria

- `strategy_deliberation` LLM payload includes richer context:

```text
agent_profile
task_relevant_memory
recent_episode_summary
retrieved_episodic_memory
```

- Output schema remains unchanged:

```text
attempt_self_score
seek_help_score
avoid_score
dominant_strategy
judge_confidence
reason
```

- LLM is still restricted to:

```text
attempt_self
seek_help_then_attempt
avoid
```

- `task_appraisal` remains evaluation-only and does not choose strategy.
- `strategy_deliberation` treats `task_appraisal` as an authoritative appraisal summary and does not re-score appraisal constructs.
- `build_semantic_reference_policy(...)` remains unchanged.
- `pi_ref` formula remains unchanged.
- Strategy cache key includes rich context buckets and a strategy prompt version.
- Phase4 `pi_final` and Phase5C `pi_final_controllability` contracts remain unchanged.
- No new env key.
- No DB schema change.
- Existing fallback behavior remains:

```text
disabled -> rule weights
request/parse/schema error -> rule weights
low judge_confidence -> rule weights
invalid llm weights -> semantic fallback later if needed
```

---

## Experiment Expectation

This change should make `pi_ref` more sensitive to specific agent context because `llm_weights` will be based on richer memory/persona evidence. This mainly matters when `PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE=semantic_v2`; if using `hybrid_ref`, rule-blended `final_weights` still remain much more central.

Expected possible downstream effect:

```text
pi_ref and Phase4 pi_final may diverge more often
Phase5C low-C shrink toward pi_ref may produce larger effective TVD
intervention_applied_count may rise when LOW_C_THRESHOLD is also raised
```

But this is only a hypothesis. After implementation, validate with a seed-101 smoke run before making any claim.

Recommended first smoke after implementation:

```bash
PROTO_BAYESIAN_POLICY_LITE_MODE=gated_lite
PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE=semantic_v2
PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE=theory_v2
PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM=0.50
PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA=0.10
PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE=control_centered_modulate
PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD=0.05
PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES=1
PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA=0.25
PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD=0.55
```

Use a new group id that records the strategy context change, for example:

```text
exp_20260518_phase5c_strategyctx_control_centered_lambda050_policymax010_huysmax025_gate005_min1_low055_4world_10d_60min_seed101_smoke
```

Primary checks:

```text
huys_payload_coverage
uses_post_outcome_information_true_count
intervention_applied_count/rate
mean/max TVD from Phase4 pi_final
mean_reference_mix_gamma
TVD(pi_final, pi_ref) distribution
world separation
helplessness_delta by world
```

---

## Do Not Do In This Patch

- Do not move strategy scores into `task_appraisal`.
- Do not let LLM output arbitrary actions.
- Do not change `POLICY_LITE_ACTIONS`.
- Do not change `compute_bayesian_policy_shadow(...)`.
- Do not change `apply_controllability_gated_modulation(...)`.
- Do not change `choose_attempt_strategy(...)`.
- Do not add low-C target config.
- Do not add a new memory schema.
- Do not let strategy LLM re-score task appraisal constructs or write psychological state deltas.
- Do not claim improved experimental results before rerunning the experiment.
