# Helplessness Update v2 Todo

> **For agentic workers:** REQUIRED: implement in small, testable phases. Keep `rule_v1` as the default comparator until v2 passes unit tests, smoke runs, QC, and ablations.

**Goal:** 把当前直接的 `outcome -> helplessness delta` 公式，升级成一个有文献支撑、可审计、可回放、可消融的无助感状态更新机制。

**Architecture:** v2 不让 LLM 直接改 helplessness。事件先经过 outcome、task appraisal、event attribution、avoid reason、support response 等中间层，最后由受控规则计算 bounded update。LLM 只能提供结构化语义 appraisal，不输出最终 delta。

**Tech Stack:** Python dataclasses, pytest, AgentSociety memory/status, CSV/JSON audit, optional online LLM appraisal with rule fallback.

---

## 0. 一句话版本

现在的更新逻辑更像记账：

```text
成功 -> helplessness 降
失败 / 放弃 / 回避 -> helplessness 升
不可控越高 -> 升得越多
自我效能越低 -> 升得越多
```

这很透明，适合作为 baseline，但论文主模型还不够。真正要模拟的是：

```text
这次数字任务经历，让 agent 学到了什么？

是“我做什么都没用”？
还是“这个页面设计差，但我以后有人教就能做”？
还是“这个弹窗像诈骗，停止才是理性选择”？
还是“家人帮我代办成功了，但我自己还是没学会”？
```

所以 v2 的核心改法是：

```text
digital task event
-> outcome
-> event meaning / attribution / support process
-> perceived controllability + self-efficacy + mastery memory
-> bounded helplessness update
```

不是让公式更花哨，而是让每次更新更像“心理学习过程”。

---

## 1. 当前代码在哪里

### 1.1 现在真正改 helplessness 的地方

当前主入口：

```text
examples/digital_friction_mvp/proto/state_update.py
```

核心函数：

```python
apply_helplessness_update(payload: HelplessnessUpdateInput) -> HelplessnessUpdateResult
```

当前公式大致是：

```text
success_self              -> base - recovery
success_with_help         -> base - recovery
failure_after_attempt     -> base + uncontrollability + efficacy_loss
failure_even_with_help    -> base + uncontrollability + efficacy_loss
abandon_midway            -> base + uncontrollability + efficacy_loss
avoid_without_attempt     -> base + uncontrollability + efficacy_loss, 再乘 avoid_reason_multiplier
```

已有项：

```text
BASE_DELTAS
UNCONTROLLABILITY_DELTAS
efficacy_loss_term
avoid_reason_multiplier
controllable_success_protection
damping_factor
success_recovery_bonus
```

### 1.2 输入 dataclass 在哪里

```text
examples/digital_friction_mvp/proto/models.py
```

当前输入：

```python
@dataclass(slots=True)
class HelplessnessUpdateInput:
    helplessness_now: float
    outcome_type: OutcomeType
    consecutive_failures: int
    support_quality: int
    event_level_uncontrollability: int
    task_self_efficacy: float
    felt_control: float
    expected_help_effectiveness: float
    avoid_reason: str
    controllable_success_memory: float
    support_mode: str
```

当前输出：

```python
@dataclass(slots=True)
class HelplessnessUpdateResult:
    helplessness_before: float
    helplessness_after: float
    delta: float
    base_delta: float
    uncontrollability_delta: float
    efficacy_loss_term: float
    recovery_bonus: float
    mastery_recovery_term: float
    raw_delta_before_damping: float
    damping_factor: float
    avoid_reason_multiplier: float
    controllable_success_protection: float
    next_consecutive_failures: int
```

### 1.3 agent 调用点在哪里

```text
examples/digital_friction_mvp/proto/agent.py
```

关键顺序大概是：

```text
resolve_attempt_outcome
-> infer_avoid_reason
-> infer_support_mode
-> infer_event_attribution
-> resolve_event_appraisal
-> apply_helplessness_update
-> update_experience_memory
-> bayesian / Huys-Dayan-lite audit
-> write attempt row / payload_json
```

也就是说，v2 很幸运：很多中间信息已经存在。问题不是没有输入，而是 `state_update.py` 还没有充分利用这些输入。

---

## 2. 为什么要改

### 2.1 最近实验暴露的问题

在 7 天、1 seed 的 full LLM online entry run 里，`low_friction_high_assist` 的 helplessness 仍然很高，和 baseline 差距不明显。

一个重要原因是：当前模型里 support 主要还是环境参数或 outcome 后的粗标签。它没有充分区分：

```text
有人耐心教我，让我自己完成
有人直接拿手机替我做完
有人不耐烦地责备我
没人回应我的求助
```

这四种帮助对 “我以后能不能自己做” 的意义完全不同。

### 2.2 当前公式太容易把不同心理含义压成同一个 delta

现在很多事件都可能变成：

```text
outcome_type 是负向
event_level_uncontrollability 高
task_self_efficacy 低
=> helplessness 上升
```

但同样是没有完成任务，含义可能完全不一样：

```text
系统真的坏了                 -> 更像 external/system attribution
页面设计很糟但有人教会了       -> 不一定增加 helplessness
我觉得自己永远学不会           -> strongly helplessness-relevant
付款弹窗像诈骗所以停止         -> 可能是理性安全行为
任务不重要所以今天不做         -> 更像 low value / low usefulness
```

论文里如果继续只靠 outcome label，很容易被审稿人问：

```text
为什么所有失败都按同一种心理伤害处理？
为什么 high assist 没有被建模成真正的支持过程？
为什么 avoidance 一定代表 helplessness？
```

### 2.3 v2 要解决什么

v2 不是“把 helplessness 调低一点”。v2 要解决的是机制：

```text
failure count 不是 helplessness 的核心。
response-outcome noncontingency 才是核心。
self-efficacy 是“我能不能执行动作”。
controllability 是“我的动作有没有用”。
attribution 决定这次失败会不会泛化。
support style 决定帮助是在教学、代办、打击，还是缺席。
avoidance 要拆成 helplessness / risk / low value / rational security。
```

---

## 3. 文献支持矩阵

主要证据来自：

```text
模块文献支持矩阵_mineru证据句版.md
paper/mineruex/
paper/_extracted/
```

下面只列和 helplessness update v2 直接相关的证据。正式论文中可以用 evidence ID 回到矩阵查完整 MinerU 位置。

| v2 模块 | 证据 ID | 文献/理论 | 支持什么 | 不能支持什么 |
|---|---:|---|---|---|
| response-outcome noncontingency | E18, E19 | Seligman & Maier (1967) | learned helplessness 核心是结果与行动脱钩、控制程度下降 | 不给数字任务里的具体 delta |
| learned control | E21, E23 | Maier & Seligman (2016) | 关键信念是 “nothing one does matters” / 未来坏事是否可控 | 不支持失败自动等于 helplessness |
| attribution | E11, E12 | Abramson et al. (1978) | 内外归因、稳定性、广泛性影响 helplessness 的持续和泛化 | 不给 LLM prompt 的正确性证明 |
| self-efficacy | E24, E25, E26 | Bandura (1977) | outcome expectancy 和 efficacy expectation 要分开；成功提高 mastery，失败降低 efficacy | 不支持把 self-efficacy 和 controllability 混成一个变量 |
| controllability diagnostic | E13-E17 | Huys & Dayan (2009) | 可以从 action-outcome observations / contingency / entropy / utility 推断 control | 我们只能说 inspired by，不是完整复现 |
| hopelessness-control distinction | E35, E36 | Karvelis & Diaconescu (2022) | helplessness/hopelessness 与 controllability 可区分但耦合 | 场景不是老年数字服务，不能过度外推 |
| avoidance decomposition | E01, E27, E34 | TAM, technophobia, digital anxiety | non-use/avoidance 可能来自低 usefulness、焦虑、风险，而非 helplessness | 不支持所有 avoid subtype 的数值权重 |
| support as process | E04, E28-E33 | UTAUT, digital support/intervention, family support | support 应是 facilitating condition / 一对一 coaching / family guidance / enabling vs over-reliant support | 不支持 helper 直接决定真实 outcome 或心理状态 |
| auditability | E39, E40 | LifeSim / agent simulation validation | 长程 agent simulation 需要结构化、透明、可审计和人工 sanity validation | 不证明当前参数已经正确 |

最稳论文表述：

```text
The literature supports the organization and directional constraints of the
mechanism, but not exact event-level numerical parameters. Therefore we treat
the v2 update as theory-informed, bounded, and audit-driven, and evaluate it
through ablation, sensitivity, paired-seed comparison, and human/expert audit.
```

---

## 4. v2 的核心设计原则

### 4.1 LLM 不直接改 helplessness

禁止 LLM 输出：

```text
helplessness_delta
helplessness_after
Bayesian posterior update
C_family
scope_spillover_total
true outcome
```

允许 LLM 或 rule fallback 输出：

```text
perceived_contingency
attribution_locus
attribution_stability
attribution_scope
support_helpfulness
support_style
emotional_impact
recoverability
confidence
```

通俗讲：

```text
LLM 可以说“这次失败更像系统问题，且是临时的”。
LLM 不能说“helplessness 应该 +2.7”。
```

### 4.2 v1 必须保留

`rule_v1` 是论文里的必要 comparator。

要新增：

```text
PROTO_HELPLESSNESS_UPDATE_MODE=rule_v1|theory_update_v2
```

默认必须先保持：

```text
PROTO_HELPLESSNESS_UPDATE_MODE=rule_v1
```

只有显式设置 v2 时才启用新机制。

### 4.3 v2 必须可审计

每次更新都要能回答：

```text
为什么这次 helplessness 上升/下降？
哪一部分来自 uncontrollability？
哪一部分来自 self-efficacy？
哪一部分来自 attribution？
support 是保护还是伤害？
avoid 是 helpless avoid 还是 risk avoid？
有没有 fallback？
```

如果回答不了，就不能作为主实验机制。

---

## 5. v2 公式形状

### 5.1 失败/放弃/回避事件

建议结构：

```python
raw_harm = (
    base_failure_signal
    + noncontingency_harm
    + self_efficacy_harm
    + affective_distress_harm
)

raw_harm *= attribution_harm_multiplier
raw_harm *= avoid_reason_multiplier
raw_harm *= support_harm_multiplier
raw_harm *= controllable_success_protection
raw_harm *= damping

delta = max(0, raw_harm)
```

解释：

```text
base_failure_signal:
  outcome label 本身只给小信号，不应决定全部心理变化。

noncontingency_harm:
  这次事件是否让 agent 感到“做什么都没用”。

self_efficacy_harm:
  这次事件是否打击了“我能执行这个动作”的信念。

affective_distress_harm:
  这次事件是否带来羞耻、焦虑、挫败等情绪负荷。

attribution_harm_multiplier:
  自我 + 稳定 + 全局归因放大伤害；
  系统 + 临时 + 任务特定归因缓冲伤害。

avoid_reason_multiplier:
  helpless_avoid 高；
  risk_avoid / low_value_avoid 低；
  rational_security_avoid 接近 0 或保护。

support_harm_multiplier:
  enabling support 缓冲失败；
  substituting support 弱缓冲；
  dismissive/unavailable 不缓冲甚至放大。

controllable_success_protection:
  以前有过“我能搞定”的记忆，本次打击应更小。

damping:
  helplessness 已经很高时，边际上升不应无限增加。
```

### 5.2 成功事件

建议结构：

```python
recovery = (
    base_success_recovery
    + mastery_recovery
    + support_guided_mastery_bonus
    + ended_failure_streak_bonus
)

recovery *= attribution_recovery_multiplier
recovery *= support_recovery_multiplier

delta = -max(0, recovery)
```

解释：

```text
success_self:
  最强 mastery recovery，因为 agent 自己完成。

success_with_help + enabling:
  中强 recovery，因为帮助保留了自主性，agent 学到“我在指导下能做”。

success_with_help + substituting:
  outcome 是成功，但 mastery recovery 弱，因为“别人替我做了”。

success_with_help + dismissive:
  可能任务完成了，但情绪/效能恢复弱。
```

---

## 6. 新增/扩展数据结构

### 6.1 `HelplessnessUpdateInput` 扩展字段

文件：

```text
examples/digital_friction_mvp/proto/models.py
```

建议新增字段，先给默认值，避免破坏旧测试：

```python
helplessness_update_mode: str = "rule_v1"

perceived_contingency: str = "not_applicable"
emotional_impact: str = "not_applicable"
recoverability: str = "not_applicable"
appraisal_confidence: float = 0.0

event_attribution_locus: str = "not_applicable"
event_attribution_stability: str = "not_applicable"
event_attribution_scope: str = "not_applicable"
event_attribution_confidence: float = 0.0

support_style: str = "not_applicable"
support_helpfulness: str = "not_applicable"
support_instruction_quality: float = 0.0
support_autonomy_preservation: float = 0.0
support_availability: str = "not_applicable"
```

注意：第一版不一定全部用上，但 audit schema 要提前留好。

### 6.2 `HelplessnessUpdateResult` 扩展字段

建议新增：

```python
mode: str = "rule_v1"
status: str = "ok"

base_failure_signal: float = 0.0
noncontingency_harm: float = 0.0
self_efficacy_harm: float = 0.0
affective_distress_harm: float = 0.0

attribution_multiplier: float = 1.0
support_harm_multiplier: float = 1.0
support_recovery_multiplier: float = 1.0
attribution_recovery_multiplier: float = 1.0

rule_fallback_reason: str = ""
```

### 6.3 audit payload

`agent.py` 的 attempt row / `payload_json.paper_backed_core.update_breakdown` 要扩展成：

```json
{
  "helplessness_update": {
    "mode": "theory_update_v2",
    "status": "ok",
    "before": 48.0,
    "after": 49.1,
    "delta": 1.1,
    "terms": {
      "base_failure_signal": 0.25,
      "noncontingency_harm": 1.2,
      "self_efficacy_harm": 0.4,
      "affective_distress_harm": 0.2,
      "attribution_multiplier": 0.75,
      "avoid_reason_multiplier": 1.0,
      "support_harm_multiplier": 0.8,
      "controllable_success_protection": 0.2,
      "damping_factor": 0.76
    },
    "semantic_inputs": {
      "event_attribution_locus": "system",
      "event_attribution_stability": "temporary",
      "event_attribution_scope": "task_specific",
      "support_style": "enabling",
      "avoid_reason": "not_applicable"
    }
  }
}
```

---

## 7. Support process 怎么接入

参考：

```text
多agenttodo.md
```

不要一开始做完整 multi-agent 社会。第一版只做最小闭环：

```text
seek_help_then_attempt
-> support_request
-> FamilyHelperAgent 或 seeded helper stub
-> support_response
-> outcome_model / event_appraisal / helplessness_update
-> audit
```

### 7.1 第一版 support style

固定四类：

```text
enabling
substituting
dismissive
unavailable
```

含义：

| style | 通俗解释 | 对 helplessness v2 的方向 |
|---|---|---|
| enabling | 耐心教，让老人自己完成 | 成功时强 recovery，失败时也缓冲 |
| substituting | 直接代办 | outcome 可能成功，但 self-efficacy recovery 弱 |
| dismissive | 不耐烦、责备、催促 | 可能放大 shame/anxiety，降低未来求助 |
| unavailable | 没人回应/太晚回应 | 增加 abandon 和 help ineffectiveness |

### 7.2 support_response 字段

建议新建或扩展数据结构：

```python
@dataclass(slots=True)
class SupportResponse:
    source: str
    responded: bool
    support_style: str
    instruction_quality: float
    emotional_tone: str
    autonomy_preservation: float
    proxy_completion_level: str
    requested_help_alignment: float
    response_delay_bucket: str
    status: str = "ok"
```

禁止字段：

```text
outcome_type
success
helplessness_delta
helplessness_after
posterior_update
C_family
```

support 可以影响 outcome probability 和 event meaning，但不能直接写最终心理状态。

---

## 8. Avoidance decomposition

当前已有：

```text
helpless_avoid
risk_avoid
low_value_avoid
```

建议补：

```text
rational_security_avoid
```

四类含义：

| avoid_reason | 含义 | helplessness 影响 |
|---|---|---|
| helpless_avoid | “我不会，我做不了，所以不试” | 高 |
| risk_avoid | “看起来有风险/像诈骗，所以不继续” | 低，更多影响 trust/anxiety |
| low_value_avoid | “这事不值得现在做” | 很低，更多影响 usefulness/intention |
| rational_security_avoid | “停止是正确安全行为” | 0 或保护 |

这点很重要，因为论文里绝不能写成：

```text
所有 non-use / avoid 都是 helplessness。
```

更稳说法：

```text
Avoidance is decomposed into risk, low value, rational security, and
uncontrollability-driven withdrawal.
```

---

## 9. 实现计划

## Chunk 1: Freeze v1 and Add Mode Flag

### Task U1: 保留 `rule_v1`，新增 mode 但不改变行为

**Files:**

- Modify: `examples/digital_friction_mvp/config_runtime.py`
- Modify: `examples/digital_friction_mvp/world_runner.py`
- Modify: `examples/digital_friction_mvp/proto/models.py`
- Modify: `examples/digital_friction_mvp/proto/state_update.py`
- Test: `examples/digital_friction_mvp/tests/test_state_update.py`
- Test: `examples/digital_friction_mvp/tests/test_runtime.py`

- [ ] **Step 1: 写 runtime 测试**

测试：

```python
def test_helplessness_update_mode_defaults_to_rule_v1():
    cfg = load_runtime_config({})
    assert cfg.proto_helplessness_update_mode == "rule_v1"
```

- [ ] **Step 2: 加 env 配置**

新增：

```text
PROTO_HELPLESSNESS_UPDATE_MODE=rule_v1|theory_update_v2
```

默认：

```text
rule_v1
```

校验非法值时报错。

- [ ] **Step 3: `HelplessnessUpdateInput` 加 mode 字段**

```python
helplessness_update_mode: str = "rule_v1"
```

- [ ] **Step 4: `apply_helplessness_update` 做 dispatcher**

```python
def apply_helplessness_update(payload):
    if payload.helplessness_update_mode == "theory_update_v2":
        return apply_helplessness_update_v2(payload)
    return apply_helplessness_update_rule_v1(payload)
```

先把当前函数内容重命名为：

```python
apply_helplessness_update_rule_v1
```

- [ ] **Step 5: 回归测试 v1 不变**

运行：

```bash
PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_state_update.py -q
```

预期：

```text
全部通过，旧断言不需要大改。
```

---

## Chunk 2: v2 Skeleton and Audit

### Task U2: 加 v2 骨架，行为先和 v1 基本一致

**Files:**

- Modify: `examples/digital_friction_mvp/proto/models.py`
- Modify: `examples/digital_friction_mvp/proto/state_update.py`
- Modify: `examples/digital_friction_mvp/proto/agent.py`
- Test: `examples/digital_friction_mvp/tests/test_state_update.py`

- [ ] **Step 1: 扩展 result 字段**

给 `HelplessnessUpdateResult` 增加默认字段：

```python
mode: str = "rule_v1"
status: str = "ok"
base_failure_signal: float = 0.0
noncontingency_harm: float = 0.0
self_efficacy_harm: float = 0.0
affective_distress_harm: float = 0.0
attribution_multiplier: float = 1.0
support_harm_multiplier: float = 1.0
support_recovery_multiplier: float = 1.0
attribution_recovery_multiplier: float = 1.0
rule_fallback_reason: str = ""
```

- [ ] **Step 2: v2 函数先返回同样方向的结果**

```python
def apply_helplessness_update_v2(payload):
    result = apply_helplessness_update_rule_v1(payload)
    result.mode = "theory_update_v2"
    return result
```

如果 dataclass frozen/slots 不方便直接改，就新建 result。

- [ ] **Step 3: audit 写入 mode/status**

在 `agent.py` 的 `paper_backed_core.update_breakdown` 中加入：

```text
helplessness_update_mode
helplessness_update_status
```

- [ ] **Step 4: 测试**

新增测试：

```text
v2 result.mode == "theory_update_v2"
v2 result.status == "ok"
v2 有完整 audit terms
```

---

## Chunk 3: Attribution Multiplier

### Task U3: 把 event attribution 接入 v2

**Files:**

- Modify: `examples/digital_friction_mvp/proto/models.py`
- Modify: `examples/digital_friction_mvp/proto/state_update.py`
- Modify: `examples/digital_friction_mvp/proto/agent.py`
- Test: `examples/digital_friction_mvp/tests/test_state_update.py`

- [ ] **Step 1: input 增加 attribution 字段**

```python
event_attribution_locus: str = "not_applicable"
event_attribution_stability: str = "not_applicable"
event_attribution_scope: str = "not_applicable"
event_attribution_confidence: float = 0.0
```

- [ ] **Step 2: agent 传入已有 outcome attribution**

在 `agent.py` 调用 `HelplessnessUpdateInput(...)` 时传：

```python
event_attribution_locus=outcome.event_attribution_locus
event_attribution_stability=outcome.event_attribution_stability
event_attribution_scope=outcome.event_attribution_scope
event_attribution_confidence=outcome.event_attribution_confidence
```

- [ ] **Step 3: 实现 multiplier**

建议初始范围保守：

```python
def attribution_harm_multiplier(locus, stability, scope, confidence):
    if confidence < 0.55:
        return 1.0
    multiplier = 1.0
    if locus == "self":
        multiplier += 0.10
    elif locus in {"system", "external"}:
        multiplier -= 0.10
    if stability == "stable":
        multiplier += 0.10
    elif stability == "temporary":
        multiplier -= 0.08
    if scope == "global":
        multiplier += 0.12
    elif scope == "task_specific":
        multiplier -= 0.08
    return clamp_term(multiplier, 0.70, 1.30)
```

原则：

```text
self + stable + global -> 放大
system/external + temporary + task_specific -> 缓冲
low confidence -> 不用
```

- [ ] **Step 4: recovery multiplier**

成功事件也要用 attribution：

```text
成功归因于自己能力/努力 -> recovery 更强
成功完全归因于别人代办/偶然 -> recovery 较弱
```

第一版可以先做 failure-only，成功侧留 audit 字段。

- [ ] **Step 5: 测试**

必须有：

```text
self_stable_global failure delta > system_temporary_task_specific failure delta
low attribution confidence -> multiplier == 1.0
```

---

## Chunk 4: Avoidance Decomposition Fix

### Task U4: 增加 rational_security_avoid，并降低非 helpless avoidance 的伤害

**Files:**

- Modify: `examples/digital_friction_mvp/proto/outcome_model.py`
- Modify: `examples/digital_friction_mvp/proto/state_update.py`
- Test: `examples/digital_friction_mvp/tests/test_outcome_model.py`
- Test: `examples/digital_friction_mvp/tests/test_state_update.py`

- [ ] **Step 1: `infer_avoid_reason` 支持 `rational_security_avoid`**

触发条件示例：

```text
risk high
malicious_friction high
payment/security task
task_value not extremely high
felt_control not necessarily low
```

- [ ] **Step 2: 更新 multipliers**

建议：

```python
AVOID_REASON_MULTIPLIERS_V2 = {
    "helpless_avoid": 1.00,
    "risk_avoid": 0.25,
    "low_value_avoid": 0.10,
    "rational_security_avoid": 0.00,
}
```

是否 0.00 可以做 sensitivity：

```text
0.00 / 0.05 / 0.10
```

- [ ] **Step 3: audit 记录 avoid reason scores**

`payload_json.paper_backed_core.avoid_reason.scores` 现在已有类似结构，确认 summary 能统计。

- [ ] **Step 4: 测试**

```text
helpless_avoid delta > risk_avoid delta > low_value_avoid delta >= rational_security_avoid delta
rational_security_avoid 不增加 consecutive_failures
```

---

## Chunk 5: Support Response Stub

### Task U5: 先做 seeded support stub，不直接上 full helper agent

**Files:**

- Create: `examples/digital_friction_mvp/proto/support_process.py`
- Modify: `examples/digital_friction_mvp/proto/models.py`
- Modify: `examples/digital_friction_mvp/proto/agent.py`
- Modify: `examples/digital_friction_mvp/proto/outcome_model.py`
- Test: `examples/digital_friction_mvp/tests/test_support_process.py`

- [ ] **Step 1: 新增配置**

```text
PROTO_SUPPORT_PROCESS_MODE=off|seeded_stub|family_helper_llm
```

默认：

```text
off
```

第一版推荐实验：

```text
seeded_stub
```

- [ ] **Step 2: 定义 SupportRequest / SupportResponse**

```python
@dataclass(slots=True)
class SupportRequest:
    requester_agent_id: int
    task_family: str
    friction_type: str
    requested_help: str
    perceived_difficulty: float
    perceived_risk: float
    felt_control: float

@dataclass(slots=True)
class SupportResponse:
    responded: bool
    support_style: str
    instruction_quality: float
    emotional_tone: str
    autonomy_preservation: float
    proxy_completion_level: str
    requested_help_alignment: float
    response_delay_bucket: str
    source: str = "seeded_stub"
    status: str = "ok"
```

- [ ] **Step 3: seeded stub 逻辑**

根据 world support 配置和 agent/task 状态抽样：

```text
high assist -> enabling 概率高
low assist -> unavailable/dismissive 概率高
高风险任务 -> substituting 概率略升
低 felt_control -> substituting 概率略升
```

注意要用传入的 RNG，保证可复现。

- [ ] **Step 4: support_response 进入 outcome_model**

`resolve_attempt_outcome` 或 `build_rule_outcome_distribution_v2` 中，support 不再只看 `support_quality`，还看：

```text
instruction_quality
autonomy_preservation
support_style
response_delay_bucket
```

第一版不要大改概率，只做小幅 bounded modifier。

- [ ] **Step 5: 测试 no leakage**

确保 support_response 不含：

```text
outcome_type
success
helplessness_delta
helplessness_after
posterior
```

---

## Chunk 6: Support-Aware Helplessness v2

### Task U6: support style 影响 v2 update

**Files:**

- Modify: `examples/digital_friction_mvp/proto/state_update.py`
- Modify: `examples/digital_friction_mvp/proto/agent.py`
- Test: `examples/digital_friction_mvp/tests/test_state_update.py`

- [ ] **Step 1: input 加 support response features**

```python
support_style: str = "not_applicable"
support_instruction_quality: float = 0.0
support_autonomy_preservation: float = 0.0
support_helpfulness: str = "not_applicable"
```

- [ ] **Step 2: 实现 harm multiplier**

建议：

```python
def support_harm_multiplier(style, instruction_quality, autonomy):
    if style == "enabling":
        quality = 0.5 * instruction_quality + 0.5 * autonomy
        return clamp_term(1.0 - 0.30 * quality, 0.70, 1.0)
    if style == "substituting":
        return 0.92
    if style == "dismissive":
        return 1.12
    if style == "unavailable":
        return 1.08
    return 1.0
```

- [ ] **Step 3: 实现 recovery multiplier**

```python
def support_recovery_multiplier(style, instruction_quality, autonomy):
    if style == "enabling":
        return clamp_term(1.0 + 0.35 * instruction_quality * autonomy, 1.0, 1.35)
    if style == "substituting":
        return 0.75
    if style == "dismissive":
        return 0.85
    return 1.0
```

- [ ] **Step 4: 测试**

```text
success_with_help + enabling recovery > success_with_help + substituting recovery
failure_even_with_help + enabling harm < failure_even_with_help + unavailable harm
dismissive support 不应给 recovery bonus
```

---

## Chunk 7: Event Meaning Appraisal Fallback

### Task U7: 如果要加 LLM update appraisal，只能做中间标签

**Files:**

- Create: `examples/digital_friction_mvp/proto/helplessness_appraisal.py`
- Modify: `examples/digital_friction_mvp/proto/agent.py`
- Modify: `examples/digital_friction_mvp/config_runtime.py`
- Test: `examples/digital_friction_mvp/tests/test_helplessness_appraisal.py`

配置：

```text
PROTO_LLM_HELPLESSNESS_APPRAISAL_ENABLED=false
PROTO_LLM_HELPLESSNESS_APPRAISAL_TIMEOUT=45
PROTO_LLM_HELPLESSNESS_APPRAISAL_RETRIES=2
PROTO_LLM_HELPLESSNESS_APPRAISAL_MIN_CONFIDENCE=0.60
PROTO_LLM_HELPLESSNESS_APPRAISAL_INVALID_POLICY=rule_fallback_with_audit
```

LLM 输出 schema：

```json
{
  "perceived_contingency": "low|mid|high",
  "attribution_locus": "self|system|mixed|external",
  "attribution_stability": "temporary|uncertain|stable",
  "attribution_scope": "task_specific|domain|global",
  "support_helpfulness": "none|low|mid|high",
  "support_style": "enabling|substituting|dismissive|unavailable|not_applicable",
  "emotional_impact": "low|mid|high",
  "recoverability": "low|mid|high",
  "confidence": 0.75,
  "reason": "short bounded explanation"
}
```

fallback 规则：

```text
invalid schema -> rule_fallback_invalid_schema
timeout -> rule_fallback_timeout
low confidence -> rule_fallback_low_confidence
```

长跑实验默认不应因为一次 update appraisal invalid schema 崩掉。

---

## 10. QC 和分析输出

### 10.1 summary 新增指标

分析脚本应统计：

```text
helplessness_update_mode
helplessness_update_status counts
mean base_failure_signal
mean noncontingency_harm
mean self_efficacy_harm
mean attribution_multiplier
mean support_harm_multiplier
mean support_recovery_multiplier
avoid_reason distribution
support_style distribution
fallback rate
```

### 10.2 必须检查的 sanity checks

```text
high_friction_low_assist 的 noncontingency_harm 应更高
low_friction_high_assist 的 enabling support 占比应更高
enabling support 不应该直接保证成功
substituting support 可以提高 immediate success，但 mastery recovery 较弱
rational_security_avoid 不应显著推高 helplessness
self_stable_global attribution 的 delta 应高于 system_temporary_task_specific
```

### 10.3 ablation

至少做：

```text
v1 baseline
v2 without attribution multiplier
v2 without support style
v2 without avoid decomposition
v2 full
```

可选：

```text
v2 rule-only semantic appraisal
v2 LLM semantic appraisal with fallback
support_process off vs seeded_stub
```

---

## 11. 推荐实验顺序

不要直接上大规模 full LLM。

### Stage A: 单元测试

```bash
PYTHONPATH=examples/digital_friction_mvp pytest \
  examples/digital_friction_mvp/tests/test_state_update.py \
  examples/digital_friction_mvp/tests/test_outcome_model.py \
  examples/digital_friction_mvp/tests/test_runtime.py -q
```

### Stage B: 1-day smoke

```bash
AGENT_COUNT=2 \
STAGE_MODE=single \
STAGE_SINGLE_NAME=steady \
STAGE_DAYS=1 \
EVENT_DECISION_INTERVAL_MINUTES=120 \
PROTO_HELPLESSNESS_UPDATE_MODE=theory_update_v2 \
PROTO_SUPPORT_PROCESS_MODE=seeded_stub \
python examples/digital_friction_mvp/world_runner.py \
  --group-id exp_h_update_v2_smoke_2a_1d \
  --seed-list 101 \
  --summarize
```

### Stage C: 7-day diagnostic

```bash
AGENT_COUNT=10 \
LLM_CONCURRENCY=20 \
LLM_TIMEOUT=60 \
STAGE_MODE=single \
STAGE_SINGLE_NAME=steady \
STAGE_DAYS=7 \
EVENT_DECISION_INTERVAL_MINUTES=60 \
PROTO_HELPLESSNESS_UPDATE_MODE=theory_update_v2 \
PROTO_SUPPORT_PROCESS_MODE=seeded_stub \
python examples/digital_friction_mvp/world_runner.py \
  --group-id exp_h_update_v2_seed101_7d \
  --seed-list 101 \
  --summarize \
  --summarize-paired
```

### Stage D: multi-seed

```bash
AGENT_COUNT=10 \
LLM_CONCURRENCY=20 \
LLM_TIMEOUT=60 \
STAGE_MODE=single \
STAGE_SINGLE_NAME=steady \
STAGE_DAYS=7 \
EVENT_DECISION_INTERVAL_MINUTES=60 \
PROTO_HELPLESSNESS_UPDATE_MODE=theory_update_v2 \
PROTO_SUPPORT_PROCESS_MODE=seeded_stub \
python examples/digital_friction_mvp/world_runner.py \
  --group-id exp_h_update_v2_7d_multiseed \
  --seed-list 101,202,303,404,505 \
  --summarize \
  --summarize-paired
```

---

## 12. 论文 claim boundary

### 可以说

```text
We replace the direct outcome-to-helplessness rule with a theory-grounded,
auditable state transition.
```

```text
The transition distinguishes response-outcome noncontingency, self-efficacy
damage, attribution scope, avoidance reason, and support style.
```

```text
LLM modules provide bounded semantic appraisals; final state updates remain
rule-constrained and fully logged.
```

```text
Support is modeled as a task-triggered interaction process rather than only a
scalar world parameter.
```

### 不要说

```text
The literature determines our exact numerical deltas.
```

```text
The LLM estimates the true psychological state.
```

```text
All digital non-use is helplessness.
```

```text
We fully reproduce Huys and Dayan's model.
```

更稳写法：

```text
Huys-Dayan-inspired controllability diagnostic
theory-informed bounded update
auditable semantic appraisal
support-process augmentation
```

---

## 13. 最小可发表版本

如果时间紧，最小版本不要做完整 LLM helplessness appraisal。先完成：

```text
U1: mode flag + v1 frozen
U2: v2 audit skeleton
U3: attribution multiplier
U4: avoidance decomposition
U5: seeded support_response
U6: support-aware v2 update
```

可以暂缓：

```text
U7: LLM helplessness appraisal
family_helper_llm
peer/customer-service/volunteer agents
multi-turn social interaction
```

原因：

```text
审稿人最可能质疑的是机制合理性和可审计性，不是 helper 是否真的自由聊天。
```

最小强主线是：

```text
controlled digital task events
+ online mobile entry
+ bounded trajectory outcome model
+ support-process features
+ theory-grounded helplessness state transition
+ QC / ablation / sensitivity
```

---

## 14. Done Criteria

v2 不能只看“代码能跑”。完成标准：

```text
1. rule_v1 默认不变，旧测试通过。
2. theory_update_v2 显式启用。
3. 每次 helplessness update 有完整 terms audit。
4. invalid/low-confidence LLM appraisal 不会让长跑崩掉，而是 fallback with audit。
5. avoidance 至少区分 helpless/risk/low_value/rational_security。
6. support 至少区分 enabling/substituting/dismissive/unavailable。
7. low_friction_high_assist 的支持过程指标确实不同于 baseline。
8. v2 full 与 ablation 的差异能解释，不靠玄学调参。
9. 多 seed 报告均值、方差、置信区间或 bootstrap interval。
10. 论文中所有强 claim 都能回到 evidence matrix 或实验 QC。
```

---

## 15. 建议提交顺序

```text
commit 1: add helplessness update mode flag and freeze rule_v1
commit 2: add v2 audit schema with no behavior change
commit 3: add attribution multiplier to v2
commit 4: add rational_security_avoid and avoidance tests
commit 5: add seeded support process stub
commit 6: add support-aware v2 update
commit 7: add summary/QC fields and smoke experiment docs
```

不要一个大 commit 全塞进去。这个模块以后肯定会反复调，commit 要能回滚。

---

## 16. 最后提醒

这次改动的本质不是：

```text
让 low_friction_high_assist 的 helplessness 数字更好看。
```

而是：

```text
让模型能解释为什么某些帮助真的保护 agent，
为什么某些帮助只是代办，
为什么某些回避是理性的，
为什么同样失败在不同归因下会产生不同心理后果。
```

这样写出来才是 AAAI AISI / workshop 更能接受的机制：有理论、有边界、有 audit、有 ablation，也承认参数不是文献直接给的。
