# Bayesian Gated-Lite 2 设计说明

## 1. 一句话定位

`gated-lite2` 是当前实验更适合冲 AAAI / AISI 的主路线：

```text
LLM social simulation 是主体；
weak prior 负责冷启动；
LLM bounded semantic adjustment 负责当前情境理解；
Bayesian posterior predictive learning 负责 action-outcome 经验学习；
rule 不再生成主策略，只做 safety guard；
Bayesian 只有在证据足够时，才小幅影响真实行为。
```

推荐论文表述：

```text
LLM-based social simulation with gated Bayesian-inspired posterior predictive action-outcome learning.
```

不推荐表述：

```text
full Bayesian RL agent
```

也不推荐表述：

```text
hand-crafted rule-based strategy policy
```

## 2. 相比 gated-lite v1 的核心修改

原版 `bayesian gated-lite.md` 的关键问题是：`pi_current` 仍然可能来自“当前 strategy deliberation”，而当前 strategy deliberation 里仍有较强的 rule 权重。

这会带来一个审稿风险：

```text
Bayesian 看起来在工作，但真实行为仍然主要由 rule-heavy pi_current 决定。
```

因此 v2 把主链明确改成：

```text
pi_prior = weak neutral prior
pi_semantic = bounded LLM semantic adjustment(pi_prior, current context)
pi_bayes = posterior predictive policy from action-outcome memory
pi_gated = gated_lite_shift(pi_semantic, pi_bayes)
pi_final = safety_guard(pi_gated)
```

这意味着：

```text
rule 不再参与常规策略权重生成；
rule 只处理非法概率、不可执行 action、极端风险保护和兜底。
```

修改原因：

```text
1. 减少 hand-crafted rule dependence。
2. 让 Bayesian posterior 在经验足够时真正解释策略适应。
3. 保留 LLM 对人设、语义和主观解释的主体作用。
4. 避免系统变成纯 RL agent。
```

## 3. 为什么需要 gated-lite2

我们的目标不是把 AgentSociety 改造成 RL 系统，而是：

```text
保留 LLM simulation 的 persona、语义理解、访谈、归因和主观解释能力；
同时加入一个有文献依据、可审计的 action-outcome learning 机制；
减少人工 rule 参数对策略选择的主导。
```

原来的 rule-heavy 策略有一个审稿风险：

```text
helplessness 高 -> attempt_self 降低多少？
support_quality 高 -> seek_help 增加多少？
连续失败多 -> avoid 增加多少？
```

这些方向在心理学上合理，但具体阈值和权重很难完全用文献支撑。

gated-lite2 的优势是把策略适应解释为：

```text
agent 在某类任务里采取了什么 action
-> 得到什么 outcome subtype
-> 更新 P(outcome_subtype | task_family, action)
-> 计算该 action 的 posterior expected utility
-> 在证据足够时轻量影响下一次策略
```

这更贴近 learned helplessness / learned controllability 的核心：

```text
个体从过去经验中学习 action 和 outcome 是否有关；
当有价值结果被体验为不可控时，后续主动尝试会下降，求助或回避会增加。
```

## 4. 模式设计

建议保留四种模式：

```text
off:
  不计算 Bayesian policy。

shadow:
  计算 pi_bayes / q_bayes / confidence / pi_shadow，但不影响真实行为。

gated-lite:
  Bayesian posterior 在证据足够时小幅影响真实行为，并且影响幅度受限。

on:
  Bayesian posterior policy 成为主策略来源。
```

近期推荐：

```text
shadow -> small gated-lite pilot -> gated-lite main experiment
```

近期不推荐：

```text
on
```

原因：

```text
shadow 可以先验证 Bayesian posterior 是否有解释力；
gated-lite 可以减少 rule-heavy strategy 的审稿风险；
on 太激进，会削弱 LLM social simulation 的主体性。
```

## 5. 主机制链

gated-lite2 的完整决策链是：

```text
state / task_family / persona / memory
-> weak neutral prior
-> LLM bounded semantic adjustment
-> Bayesian posterior predictive policy
-> evidence gate
-> max_delta limited shift
-> safety guard
-> sampled action
-> outcome
-> appraisal / attribution / helplessness update
-> posterior update
-> payload audit
```

更形式化地说：

```text
pi_prior(a) = weak neutral prior

pi_semantic(a | s)
  = (1 - lambda_llm) * pi_prior(a)
    + lambda_llm * pi_llm(a | s)

pi_bayes(a | f)
  = softmax(Q_bayes(f, a) / tau)

pi_gated(a)
  = gated_lite_shift(pi_semantic(a), pi_bayes(a), confidence_a, max_delta)

pi_final(a)
  = safety_guard(pi_gated(a))
```

其中：

```text
s = current state / task appraisal / persona / digital emotion
f = task_family
a = action
```

## 6. Weak Prior

weak prior 是没有经验时的冷启动起点。

第一版建议使用中性先验：

```text
pi_prior(attempt_self) = 0.34
pi_prior(seek_help_then_attempt) = 0.33
pi_prior(avoid) = 0.33
```

不建议第一版使用复杂 rule prior。

原因：

```text
越复杂，越容易被质疑为手写 rule 继续主导策略。
```

如果未来确实需要 task-risk prior，也应非常弱：

```text
单个 action 调整不超过 0.05。
```

## 7. LLM Bounded Semantic Adjustment

LLM 不应被删除。它是 LLM social simulation 的主体能力来源。

LLM 继续负责：

```text
profile / persona 的语义一致性
task appraisal
event appraisal
support_mode 语义解释
avoid_reason 判断
event attribution
daily reflection
stage interview
final interview
qualitative coherence
```

在策略选择中，LLM 只做有界语义修正。

LLM 接收：

```text
persona / profile summary
current task description
task appraisal
digital emotion state
recent memory summary
pi_prior
```

LLM 输出：

```text
pi_llm(a | s)
llm_confidence
llm_reason
```

如果 LLM 输出合法且置信度足够：

```text
pi_semantic(a | s)
  = (1 - lambda_llm) * pi_prior(a)
    + lambda_llm * pi_llm(a | s)
```

建议：

```text
lambda_llm = 0.10 或 0.25
```

如果 LLM 输出非法、低置信度或请求失败：

```text
pi_semantic = pi_prior
```

注意：

```text
LLM 可以根据语义轻推策略，但不能无边界覆盖 Bayesian/posterior 机制。
```

## 8. 学习对象：P(outcome_subtype | task_family, action)

不建议只学习粗粒度 outcome：

```text
success_self
success_with_help
failure_after_attempt
avoid_without_attempt
```

更建议学习 outcome subtype，因为行动前不知道未来的 support_mode、avoid_reason、uncontrollability，但这些信息会影响 utility。

建议 outcome subtype：

```text
success_self
success_with_help_enabling
success_with_help_substituting
failure_after_attempt_low_uncontrollability
failure_after_attempt_mid_uncontrollability
failure_after_attempt_high_uncontrollability
failure_even_with_help
abandon_midway
avoid_without_attempt_helpless
avoid_without_attempt_risk
avoid_without_attempt_low_value
neutral_unknown
```

核心 posterior：

```text
P_hat(o | f, a) = alpha[f][a][o] / sum_o alpha[f][a][o]
```

其中：

```text
f = task_family
a = action
o = outcome_subtype
```

## 9. Memory 结构

建议新增独立 memory，不要复用 `proto_bayesian_control_memory`。

推荐：

```text
proto_bayesian_policy_memory
```

示例：

```json
{
  "version": "policy_lite_v2",
  "families": {
    "payment_risk_confirmation": {
      "attempt_self": {
        "alpha": {
          "success_self": 1.0,
          "success_with_help_enabling": 0.1,
          "success_with_help_substituting": 0.1,
          "failure_after_attempt_low_uncontrollability": 0.1,
          "failure_after_attempt_mid_uncontrollability": 0.1,
          "failure_after_attempt_high_uncontrollability": 1.0,
          "failure_even_with_help": 0.1,
          "abandon_midway": 0.1,
          "avoid_without_attempt_helpless": 0.1,
          "avoid_without_attempt_risk": 0.1,
          "avoid_without_attempt_low_value": 0.1,
          "neutral_unknown": 0.1
        },
        "update_count": 2,
        "last_outcome_subtype": "failure_after_attempt_high_uncontrollability",
        "last_updated_day": 3
      }
    }
  }
}
```

`proto_bayesian_control_memory` 和 `proto_bayesian_policy_memory` 应该分开：

```text
Bayesian controllability audit memory:
  解释 task_family 的总体可控性。

Bayesian policy memory:
  学习 task_family + action 下的 outcome subtype 分布。
```

## 10. Utility 设计

Bayesian 模块必须有 utility，否则只是学概率，不是在选择策略。

第一版建议使用 theory-grounded utility：

```text
U(success_self) = high positive
U(success_with_help_enabling) = medium-high positive
U(success_with_help_substituting) = medium positive
U(failure_after_attempt_low_uncontrollability) = mild negative
U(failure_after_attempt_mid_uncontrollability) = medium negative
U(failure_after_attempt_high_uncontrollability) = high negative
U(failure_even_with_help) = high negative
U(abandon_midway) = medium negative
U(avoid_without_attempt_helpless) = high long-term negative
U(avoid_without_attempt_risk) = neutral or mild negative
U(avoid_without_attempt_low_value) = near neutral
U(neutral_unknown) = neutral
```

必须在论文中诚实说明：

```text
posterior belief 是从 agent experience 中更新的；
utility mapping 是 theory-grounded design choice；
utility 参数需要做 sensitivity analysis。
```

推荐英文表述：

```text
The posterior over action-conditioned outcome subtypes is learned from simulated experience, whereas the outcome utility mapping is theory-grounded and evaluated through sensitivity analysis.
```

## 11. Q_Bayes 和 pi_bayes

对每个 action 计算：

```text
Q_bayes(f, a) = sum_o P_hat(o | f, a) * U(o)
```

然后通过 softmax 得到：

```text
pi_bayes(a | f) = softmax(Q_bayes(f, a) / tau)
```

其中：

```text
tau 小：更偏向最高 Q 的 action
tau 大：更保留探索和行为多样性
```

第一版建议 tau 不要太小，避免 Bayesian policy 过早变得确定。

## 12. Evidence Gate

gated-lite2 必须有证据门槛。

不建议用 task-family 总经验：

```text
c = total_updates(task_family) / K
```

推荐 action-specific confidence：

```text
confidence_a = min(1.0, update_count(task_family, action) / K)
```

建议初始参数：

```text
K = 4 或 6
gate_threshold = 0.50
```

也就是：

```text
某个 action 至少有 2 到 3 次相关经验后，才允许 Bayesian 对它产生明显影响。
```

这样可以避免：

```text
agent 大量 avoid，却假装自己知道 attempt_self 的结果。
```

## 13. Influence Cap

gated-lite2 必须限制每次策略变化幅度。

建议：

```text
max_delta_per_action = 0.10
```

更激进但仍可接受：

```text
max_delta_per_action = 0.15
```

不建议超过：

```text
0.20
```

原因：

```text
如果 Bayesian 一次把 action probability 改太多，系统就会逐渐变成 Bayesian policy agent，而不是 LLM social simulation。
```

## 14. Gated-Lite Shift 公式

输入：

```text
pi_semantic(a)
pi_bayes(a)
confidence_a
gate_threshold
max_delta_per_action
```

对每个 action：

```text
if confidence_a < gate_threshold:
    delta_a = 0
else:
    raw_delta_a = pi_bayes(a) - pi_semantic(a)
    delta_a = clip(raw_delta_a * confidence_a, -max_delta_per_action, max_delta_per_action)
```

然后：

```text
pi_gated(a) = pi_semantic(a) + delta_a
pi_gated = normalize(pi_gated)
```

最后再过 safety guard：

```text
pi_final = safety_guard(pi_gated)
```

这样有三个好处：

```text
1. Bayesian 有证据才生效。
2. Bayesian 每次影响有限。
3. 可以清楚记录 Bayesian 到底改了多少。
```

建议额外记录：

```text
delta_before_normalize
delta_after_normalize
total_variation_distance(pi_semantic, pi_final)
```

原因：

```text
normalize 之后，即使某些 action 没有通过 gate，它们的最终概率也可能被动变化。
```

## 15. Safety Guard

rule 只做 safety guard，不做常规策略混合。

触发条件可以包括：

```text
posterior invalid
pi_final contains NaN
all probabilities are zero
action impossible in current task
extreme risk task with no support available
probability below minimum floor
```

安全保护可以做：

```text
normalize
probability floor
fallback to weak prior
fallback to pi_semantic
```

不建议做：

```text
根据 helplessness 阈值重新大幅调权
根据 support_quality 手动大幅加减策略概率
根据 consecutive_failures 手动覆盖 Bayesian 结果
```

否则又会回到 rule-heavy policy。

## 16. Payload 必须记录什么

gated-lite2 最大的价值之一是可审计。

每次 episode 建议写入：

```json
{
  "bayesian_policy_lite": {
    "version": "policy_lite_v2",
    "mode": "gated_lite",
    "task_family": "payment_risk_confirmation",
    "actual_strategy": "seek_help_then_attempt",
    "pi_prior": {
      "attempt_self": 0.34,
      "seek_help_then_attempt": 0.33,
      "avoid": 0.33
    },
    "pi_llm": {
      "attempt_self": 0.20,
      "seek_help_then_attempt": 0.50,
      "avoid": 0.30
    },
    "llm_confidence": 0.78,
    "llm_reason": "The task involves payment risk, so seeking help before attempting is semantically plausible.",
    "lambda_llm": 0.25,
    "pi_semantic": {
      "attempt_self": 0.305,
      "seek_help_then_attempt": 0.373,
      "avoid": 0.323
    },
    "q_bayes": {
      "attempt_self": -0.20,
      "seek_help_then_attempt": 0.55,
      "avoid": -0.05
    },
    "pi_bayes": {
      "attempt_self": 0.22,
      "seek_help_then_attempt": 0.60,
      "avoid": 0.18
    },
    "confidence_by_action": {
      "attempt_self": 0.50,
      "seek_help_then_attempt": 0.67,
      "avoid": 0.17
    },
    "gate_by_action": {
      "attempt_self": true,
      "seek_help_then_attempt": true,
      "avoid": false
    },
    "delta_applied": {
      "attempt_self": -0.043,
      "seek_help_then_attempt": 0.100,
      "avoid": 0.000
    },
    "pi_after_bayesian_shift": {
      "attempt_self": 0.262,
      "seek_help_then_attempt": 0.473,
      "avoid": 0.323
    },
    "pi_final": {
      "attempt_self": 0.248,
      "seek_help_then_attempt": 0.447,
      "avoid": 0.305
    },
    "max_delta_per_action": 0.10,
    "gate_threshold": 0.50,
    "tau": 1.0,
    "status": "gated_lite_applied"
  }
}
```

这样后续可以回答审稿人的问题：

```text
LLM 语义修正了多少？
Bayesian policy 什么时候介入？
Bayesian 介入了多少？
哪些 action 有足够证据？
最终策略到底改变了多少？
结果是否由 Bayesian posterior 而不是 rule 导致？
```

## 17. 后验更新

每次 outcome 后，只更新实际采取的 action：

```text
alpha[f][a_actual][o_observed] += weight
update_count[f][a_actual] += 1
```

第一版建议：

```text
rho = 1.0
```

也就是不做 decay，更接近标准 Dirichlet-multinomial update。

如果未来要模拟非平稳环境，可以再考虑：

```text
rho < 1.0
```

但这时要说明是 forgetting posterior，而不是标准 Dirichlet update。

## 18. 和 Bayesian Controllability Audit 的关系

当前 Phase B 的 Bayesian controllability audit 是：

```text
outcome -> C_hat(task_family) -> audit
```

它主要解释：

```text
这个任务类型总体上被 agent 学成了多可控？
```

gated-lite2 policy 学的是：

```text
在这个任务类型下，不同 action 分别会导致什么 outcome subtype？
```

二者关系：

```text
Bayesian audit:
  解释可控性感知。

Bayesian gated-lite2:
  轻量影响下一次策略。
```

可以从 policy posterior 派生 action-level controllability：

```text
C_hat(f, a) = sum_o P_hat(o | f, a) * controllability_score(o)
```

但不建议再把 C_hat 直接写成：

```text
C_hat 低 -> 减少 attempt_self
```

因为那会退回 heuristic policy。

## 19. 消融和验证

如果 gated-lite2 进入论文，至少要有这些对照：

```text
baseline: 当前 LLM simulation 主机制
audit-only: Bayesian controllability audit 不影响行为
shadow: Bayesian policy 只计算不影响行为
gated-lite2: weak prior + LLM semantic adjustment + Bayesian gated shift
gated-lite2 without LLM adjustment
gated-lite2 without Bayesian shift
```

最好加敏感性分析：

```text
max_delta_per_action = 0.05 / 0.10 / 0.15
gate_threshold = 0.33 / 0.50 / 0.67
lambda_llm = 0.10 / 0.25
utility mapping sensitivity
tau sensitivity
```

关键指标：

```text
attempt_self rate
seek_help_then_attempt rate
avoid rate
success rate
abandon_midway rate
helpless_avoid rate
risk_avoid rate
helplessness trajectory
felt_control trajectory
posterior confidence trajectory
Bayesian delta magnitude
LLM semantic delta magnitude
qualitative coherence
```

核心审稿问题：

```text
gated-lite2 是否减少了 hand-crafted rule dependence？
gated-lite2 是否保留 LLM social simulation 的语义一致性？
gated-lite2 是否让 action-outcome learning 更可解释？
gated-lite2 是否导致策略过早收敛或过度回避？
```

## 20. 风险和保护

### 风险 1：越来越不像 LLM social simulation

保护：

```text
保留 LLM appraisal / attribution / interview
保留 LLM bounded semantic adjustment
max_delta_per_action <= 0.10
不做 full Bayesian RL
不做 long-term optimal planning
不让 pi_bayes 直接等于 pi_final
```

### 风险 2：Bayesian 过早学坏

保护：

```text
action-specific confidence
weak neutral prior
minimum evidence threshold
shadow comparison
posterior uncertainty logging
```

### 风险 3：utility 被质疑手调

保护：

```text
理论依据说明
sensitivity analysis
不要声称 utility 是学出来的
养老院数据用于校准 utility 和 outcome subtype
```

### 风险 4：LLM 黑箱主导

保护：

```text
lambda_llm <= 0.25
记录 pi_prior / pi_llm / pi_semantic
记录 llm_confidence 和 llm_reason
LLM 输出非法或低置信度时 fallback 到 pi_prior
```

### 风险 5：rule 暗中回到主策略

保护：

```text
safety guard 不允许使用 helplessness/support_quality/consecutive_failures 做大幅手动调权
payload 记录 safety_guard_triggered 和 safety_guard_reason
消融报告 rule guard 触发率
```

## 21. 最近一周建议

最推荐的一周目标：

```text
1. 实现 proto_bayesian_policy_memory。
2. 实现 weak prior + LLM bounded semantic adjustment。
3. 实现 shadow mode，不影响真实行为。
4. 实现 gated-lite2 mode，但默认不开。
5. gated-lite2 只在小规模实验中试跑。
6. payload 完整记录 LLM 语义修正和 Bayesian 影响。
7. 不做 on mode。
```

不建议本周做：

```text
1. 让 Bayesian policy 完全接管策略。
2. 继续让 rule 参与主策略混合。
3. 大幅删除 LLM appraisal / attribution / interview。
4. 把 utility 做得过复杂。
5. 声称 full Bayesian RL。
```

## 22. 最终审稿口径

推荐写法：

```text
We preserve the LLM-based social simulation architecture while introducing a gated Bayesian-inspired posterior predictive module for action-outcome learning. Strategy selection starts from a weak neutral prior, is semantically adjusted by the LLM within a bounded range, and is then lightly shifted by a Bayesian posterior predictive policy only when action-specific evidence is sufficient. Rule-based logic is retained only as a safety guard. This design reduces reliance on hand-crafted strategy weights while retaining LLM-based appraisal, attribution, interview, and qualitative coherence.
```

中文解释：

```text
我们没有把系统改成纯 RL agent。
我们保留 LLM social simulation 的主体，让 LLM 继续理解任务、解释事件和生成主观叙事。
策略冷启动来自弱先验，当前语义由 LLM 小幅修正，长期经验由 Bayesian posterior 学习。
rule 只做安全保护，不再主导策略。
```

## 23. 总结

gated-lite2 是当前更适合 AAAI / AISI 的路线，因为它同时满足四个目标：

```text
1. 保留 LLM social simulation 的主体和 AgentSociety 优势。
2. 引入具有理论解释力的 Bayesian action-outcome learning。
3. 明确降低 rule-heavy strategy 的主导性。
4. 避免直接进入 full Bayesian RL 带来的实现和审稿风险。
```

一句话：

```text
gated-lite2 不是让 Bayesian 接管 agent，而是让 LLM agent 在弱先验和语义理解的基础上，从过去 action-outcome 经验中学习，并在证据足够时轻轻调整下一次行动倾向。
```
