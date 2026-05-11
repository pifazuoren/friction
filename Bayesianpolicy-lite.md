# Bayesian Policy-Lite 设计说明

## 1. 核心定位

Bayesian policy-lite 是介于当前 `Bayesian controllability audit-only` 和完整 Bayesian RL 之间的一条中间路线。

这版设计吸收两个审稿风险：

```text
1. 如果只是 C_hat 低 -> 手动降低 self-try 权重，那仍然是 heuristic policy。
2. 如果公式里长期混入复杂 rule policy，审稿人会质疑结果到底来自 Bayesian posterior，还是来自人工规则。
```

因此，推荐路线改为：

```text
weak prior + Bayesian posterior predictive policy + rule safety guard + LLM bounded semantic adjustment
```

通俗说：

```text
弱先验负责冷启动。
Bayesian posterior 负责从 action-outcome 经历中学习。
rule 不再参与常规策略混合，只做安全保护和异常兜底。
LLM 只做有界语义修正。
```

推荐命名：

```text
Bayesian-inspired posterior predictive policy-lite
```

不建议命名：

```text
full Bayesian RL
```

## 2. 与当前 Phase B 的区别

当前 Phase B 是 audit-only：

```text
outcome -> C_hat(task_family) -> 写入 audit
```

也就是说，当前 `C_hat` 只解释经历，不影响下一次行为。

Bayesian policy-lite 则会变成：

```text
past outcomes
-> posterior over outcome subtypes for each task_family + action
-> expected utility Q_Bayes(action)
-> π_Bayes
-> shadow policy 或 gated policy
```

关键变化是：

```text
策略倾向来自 posterior predictive expected utility，
而不是来自手写 C_hat 调权规则。
```

## 3. 为什么不是完整 Bayesian RL

Bayesian policy-lite 不完整建模：

```text
完整 state transition model
长期 planning
Q-value posterior over multi-step returns
optimal policy learning
regret / convergence
```

它只做一个轻量的 posterior predictive policy：

```text
在当前 task family 下，
不同 action 过去分别更可能导致什么 outcome subtype？
这些 outcome subtype 的期望价值是多少？
```

因此更准确的表述是：

```text
Bayesian-inspired posterior predictive strategy policy
```

而不是：

```text
Bayesian RL policy
```

## 4. 学什么：P(outcome_subtype | task_family, action)

policy-lite 的核心不是单一的：

```text
C_hat(task_family)
```

而是学习：

```text
P(outcome_subtype | task_family, action)
```

这里建议使用 outcome subtype，而不是只用粗粒度 outcome。原因是行动前并不知道具体的 `support_mode / event_level_uncontrollability / avoid_reason`，所以应该把这些信息编码进被学习的结果类型中。

示例 outcome subtype：

```text
success_self
success_with_help_enabling
success_with_help_substituting
failure_after_attempt_u0
failure_after_attempt_u1
failure_after_attempt_u2
failure_even_with_help
abandon_midway
avoid_helpless
avoid_risk
avoid_low_value
avoid_unknown
```

例如对 `payment_risk_confirmation`：

```text
P(success_self | attempt_self)
P(failure_after_attempt_u2 | attempt_self)
P(success_with_help_enabling | seek_help_then_attempt)
P(success_with_help_substituting | seek_help_then_attempt)
P(failure_even_with_help | seek_help_then_attempt)
P(avoid_helpless | avoid)
P(avoid_risk | avoid)
```

这让 agent 能回答更具体的问题：

```text
在这个任务类型里，我自己尝试通常会怎样？
求助后尝试通常是保留 agency，还是被替代完成？
回避通常是理性避险，还是无助性退缩？
```

## 5. Memory 结构建议

第一版按 `task_family + action` 维护 Dirichlet posterior：

```json
{
  "payment_risk_confirmation": {
    "attempt_self": {
      "alpha": {
        "success_self": 2.0,
        "success_with_help_enabling": 0.1,
        "success_with_help_substituting": 0.1,
        "failure_after_attempt_u0": 0.5,
        "failure_after_attempt_u1": 1.0,
        "failure_after_attempt_u2": 4.0,
        "failure_even_with_help": 0.1,
        "abandon_midway": 1.0,
        "avoid_helpless": 0.1,
        "avoid_risk": 0.1,
        "avoid_low_value": 0.1,
        "avoid_unknown": 0.1
      },
      "update_count": 8,
      "last_outcome_subtype": "failure_after_attempt_u2",
      "last_updated_day": 3
    }
  }
}
```

其中：

```text
alpha[outcome_subtype] = 该 action 导致该 subtype 的累积证据
P_hat(outcome_subtype | task_family, action)
  = alpha[outcome_subtype] / sum_subtypes alpha[outcome_subtype]
```

## 6. Weak Prior 作为 Cold-Start

不建议第一版使用复杂 rule prior。越复杂，越容易被质疑是手写规则主导。

推荐使用弱中性先验：

```text
π_prior(attempt_self) = 0.34
π_prior(seek_help_then_attempt) = 0.33
π_prior(avoid) = 0.33
```

如果确实需要 task-risk prior，也应保持很弱：

```text
单个 action 调整不超过 0.05 或 0.10
```

更稳妥的第一版：

```text
只用 neutral prior。
```

这样可以清楚地说：

```text
冷启动不是靠复杂人工规则，而是靠弱先验；
经验积累后，策略主要来自 action-conditioned outcome posterior。
```

## 7. Outcome Utility

Bayesian policy 必须有 utility，否则只是在学概率。

第一版可以定义一个 theory-grounded、可审计的 subtype utility：

```text
U(success_self) = 高正值
U(success_with_help_enabling) = 中高正值
U(success_with_help_substituting) = 中等正值
U(failure_after_attempt_u0) = 小负值
U(failure_after_attempt_u1) = 中负值
U(failure_after_attempt_u2) = 大负值
U(failure_even_with_help) = 大负值
U(abandon_midway) = 中负值
U(avoid_helpless) = 长期负值
U(avoid_risk) = 接近中性或小负值
U(avoid_low_value) = 接近中性
U(avoid_unknown) = 中性或小负值
```

需要诚实说明：

```text
posterior belief 是从经历中学习的；
utility mapping 是研究者基于理论和文献设定的；
utility mapping 必须做 sensitivity analysis。
```

推荐论文表述：

```text
The posterior over action-conditioned outcomes is learned from simulated experience, whereas the outcome utility mapping is theory-grounded and evaluated through sensitivity analysis.
```

## 8. 从 posterior 到 Q_Bayes

对每个 action，计算后验预测概率：

```text
P_hat(o | f, a)
```

其中：

```text
f = task_family
a = action
o = outcome_subtype
```

然后计算 Bayesian expected utility：

```text
Q_Bayes(f, a)
  = Σ_o P_hat(o | f, a) · U(o)
```

这一步是 policy-lite 区别于 heuristic policy 的关键。

策略改变来自：

```text
posterior predictive outcome probabilities
expected utility calculation
```

而不是：

```text
C_hat 低 -> 减少 attempt_self
```

## 9. 从 Q_Bayes 到 π_Bayes

用 softmax 把 action value 转成策略分布：

```text
π_Bayes(a | f) = softmax(Q_Bayes(f, a) / τ)
```

其中：

```text
τ 小：更倾向选最高 Q 的 action
τ 大：更保留探索和行为多样性
```

## 10. Action-Specific Evidence Confidence

不建议只用 task-family-level confidence：

```text
c = min(1, total_updates_for_task_family / K)
```

因为 agent 可能在某个任务类型里大量 `avoid`，但几乎没有 `attempt_self`。这时不能假装它已经知道 `attempt_self` 会怎样。

推荐使用 action-specific confidence：

```text
c_a = min(1, update_count(task_family, action) / K)
```

例如：

```text
c_attempt_self = min(1, updates(f, attempt_self) / K)
c_seek_help = min(1, updates(f, seek_help_then_attempt) / K)
c_avoid = min(1, updates(f, avoid) / K)
```

再混合 weak prior 和 Bayesian policy：

```text
raw_score(a | f)
  = (1 - c_a) · π_prior(a) + c_a · π_Bayes(a | f)
```

归一化：

```text
π_base(a | f) = normalize(raw_score(a | f))
```

这样模型不会“假装知道自己没试过的 action”。

## 11. Rule 只做 Safety Guard

规则模块保留，但不再参与常规策略混合。

不推荐：

```text
π_base = (1 - c)π_rule + cπ_Bayes
```

推荐：

```text
π_base = normalize((1 - c_a)π_prior + c_aπ_Bayes)
π_final = safety_guard(π_base)
```

rule 只处理：

```text
invalid posterior fallback
probability clipping
extreme risk guard
impossible action guard
debugging baseline
```

也就是说：

```text
rule 不再是理论主线，只是工程保护层。
```

## 12. LLM 作为 Bounded Semantic Adjustment

LLM 仍然存在，但不直接控制行为。

LLM 接收：

```text
current state
task appraisal
digital emotion state
daily reflection
π_prior
π_Bayes
Q_Bayes
confidence_by_action
Bayesian posterior summary
```

输出：

```text
π_LLM(a | s)
```

如果 LLM 输出合法且置信度足够：

```text
π_semantic(a | s)
  = (1 - λ) · π_base(a | f) + λ · π_LLM(a | s)
```

其中：

```text
λ = 0.10 或 0.25
```

如果 LLM 输出非法、低置信度或请求失败：

```text
π_semantic = π_base
```

最后再过 safety guard：

```text
π_final = safety_guard(π_semantic)
```

## 13. 推荐先做 Shadow Mode

不建议一开始就让 Bayesian policy-lite 直接控制 agent 行为。

最近一周最稳的路线是：

```text
shadow mode
```

含义：

```text
真实行为仍然按当前主实验机制运行；
Bayesian policy-lite 在旁边计算 π_Bayes、Q_Bayes、confidence；
所有结果写入 payload，供后续分析。
```

这样可以先回答：

```text
Bayesian posterior policy 是否能解释 agent 后续的求助、尝试和回避？
Bayesian posterior policy 是否比 rule 更能预测失败、放弃或求助成功？
Bayesian posterior policy 是否和 helplessness / felt control / avoid_reason 有一致关系？
```

如果 shadow mode 结果不好，不会破坏主实验。

如果 shadow mode 结果好，再考虑 gated mode。

## 14. 模式设计

建议新增四种模式：

```text
off:
  不启用 Bayesian policy-lite

shadow:
  只计算 π_Bayes / Q_Bayes / confidence，不影响真实 action

gated:
  当 evidence confidence 足够时，小幅混入 π_Bayes

on:
  Bayesian posterior policy 成为主策略来源
```

近期只建议做：

```text
off + shadow
```

暂时不建议做：

```text
on
```

因为 `on` 会改变主实验机制，使结果解释变复杂。

## 15. Shadow Payload 字段建议

shadow mode 在每次 episode 写入：

```json
{
  "bayesian_policy_lite": {
    "version": "policy_lite_v1",
    "mode": "shadow",
    "task_family": "payment_risk_confirmation",
    "pi_prior": {
      "attempt_self": 0.34,
      "seek_help_then_attempt": 0.33,
      "avoid": 0.33
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
    "pi_shadow": {
      "attempt_self": 0.28,
      "seek_help_then_attempt": 0.51,
      "avoid": 0.21
    },
    "actual_strategy": "attempt_self",
    "status": "shadow_only"
  }
}
```

后续可以直接分析：

```text
Bayesian shadow policy 和真实 action 是否一致？
Bayesian shadow policy 是否预测了后续失败或求助？
不同 friction 条件下 π_Bayes 是否系统性变化？
```

## 16. 完整决策链

推荐机制链：

```text
state / task_family
-> weak π_prior
-> posterior P(outcome_subtype | task_family, action)
-> Q_Bayes = posterior expected utility
-> π_Bayes = softmax(Q_Bayes)
-> action-specific confidence c_a
-> π_base = normalize((1-c_a)π_prior + c_aπ_Bayes)
-> optional bounded LLM semantic adjustment
-> safety guard
-> π_final
```

如果是 shadow mode：

```text
π_final 只写入 payload，不影响真实 action。
```

如果是 gated/on mode：

```text
π_final 参与实际 strategy sampling。
```

## 17. Outcome 后如何更新 posterior

每次 outcome 后，只更新本次实际采取的 action：

```text
alpha_{f,a,o}' = rho · alpha_{f,a,o} + weight · I(o_t = o)
```

其他 outcome subtype：

```text
alpha_{f,a,o_other}' = rho · alpha_{f,a,o_other}
```

其中：

```text
f = task_family
a = actual action
o_t = observed outcome_subtype
```

第一版也可以不做 decay：

```text
rho = 1.0
```

这样更容易解释为标准 Dirichlet-multinomial update。

## 18. 和 C_hat 的关系

`C_hat` 仍然有用，但不再直接作为策略规则。

它可以作为从 posterior 派生出来的解释指标：

```text
C_hat(f, a)
  = Σ_o P_hat(o | f, a) · controllability_score(o)
```

也就是说：

```text
C_hat 从 posterior 派生出来，
而不是直接手写成 policy adjustment。
```

这能避免 reviewer 说：

```text
你只是用 Bayesian-flavored variable 调权重。
```

## 19. 和 LLM Simulation 的关系

Bayesian policy-lite 不会把系统变成纯 RL simulation。

因为 LLM 仍然负责：

```text
task appraisal
event appraisal
strategy deliberation 的语义修正
stage interview
final interview
qualitative coherence
```

Bayesian posterior policy 只负责给策略选择提供一个可审计的 action-outcome 学习模块。

更合适的定位是：

```text
LLM-based agent simulation with a lightweight Bayesian-inspired posterior predictive action-outcome module.
```

而不是：

```text
Bayesian RL agent simulation.
```

## 20. 必须做的消融和敏感性分析

如果 Bayesian policy-lite 进入主实验，至少需要：

```text
rule + LLM baseline
Bayesian audit-only
Bayesian policy-lite shadow
Bayesian policy-lite gated
Bayesian policy-lite gated without LLM
```

最好再加：

```text
λ=0.10 / 0.25 sensitivity
weak prior sensitivity
utility mapping sensitivity
confidence K sensitivity
```

这样可以回答：

```text
结果是不是 Bayesian posterior policy 带来的？
结果是不是 LLM 黑箱带来的？
结果是不是 utility mapping 手调导致的？
结果是不是 safety guard 仍然主导？
```

## 21. 近期建议完成什么

近期目标不要太大。

优先级最高：

```text
1. 实现 shadow mode，不影响真实行为
2. 新增 proto_bayesian_policy_memory
3. 在 payload 中记录 π_prior / Q_Bayes / π_Bayes / confidence_by_action / π_shadow / actual_strategy
4. 增加最小测试，确认 shadow mode 不改变原策略选择
5. 分析 shadow policy 与实际 action、outcome、helplessness 的关系
```

暂时不建议：

```text
1. 直接 on mode
2. 删除现有 rule 系统
3. 把它写成 full Bayesian RL
4. 大改 LLM strategy deliberation
```

## 22. 审稿表述建议

推荐写法：

```text
We introduce a lightweight Bayesian-inspired posterior predictive policy module that maintains Dirichlet beliefs over task-family and action-conditioned outcome subtypes. The module derives action probabilities from posterior expected utilities, uses only a weak prior for cold-start behavior, keeps rule-based logic as a safety guard rather than a policy driver, and retains LLM deliberation as a bounded semantic adjustment.
```

不推荐写法：

```text
We implement full Bayesian RL.
```

也不建议只写：

```text
C_hat adjusts action weights.
```

因为这会被理解为 heuristic policy。

一句话总结：

```text
Bayesian policy-lite 不是“C_hat 低就手动少尝试”，也不是“rule 和 Bayesian 各占一半”，而是让 agent 学习每个行动会导致什么结果，再用后验期望价值推出策略倾向；规则只做安全保护，LLM 只做有界语义修正。
```
