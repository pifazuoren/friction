# Bayesian Gated-Lite 设计说明

## 1. 一句话定位

`gated-lite` 是当前实验最合适的中间路线：

```text
LLM simulation 是主体；
Bayesian posterior predictive learning 提供轻量的 action-outcome 经验学习；
rule 不再作为主策略来源，只做 safety guard；
Bayesian 只有在证据足够时，才小幅影响真实行为。
```

推荐论文表述：

```text
LLM-based agent simulation with gated Bayesian posterior predictive action-outcome learning.
```

不推荐表述：

```text
full Bayesian RL agent
```

也不推荐表述：

```text
hand-crafted rule-based strategy policy
```

## 2. 为什么需要 gated-lite

我们当前实验的目标不是把 AgentSociety 改造成纯 RL 系统，而是：

```text
保留 LLM simulation 的人设、语义、访谈、主观解释能力；
同时加入一个有文献依据、可审计的经验学习机制；
减少人工 rule 参数对策略选择的主导。
```

原来的 rule 策略有一个审稿风险：

```text
helplessness 高 -> attempt_self 降低多少？
support_quality 高 -> seek_help 增加多少？
连续失败多 -> avoid 增加多少？
```

这些方向在心理学上合理，但具体阈值和权重很难完全用文献支撑。

Bayesian gated-lite 的优势是：它把策略适应的主要解释从手写权重，转移到 action-outcome 经验学习：

```text
agent 在某类任务里做了什么 action
-> 得到什么 outcome subtype
-> 更新 P(outcome_subtype | task_family, action)
-> 计算该 action 的 posterior expected utility
-> 在证据足够时轻量影响下一次策略
```

这更接近 learned helplessness / learned controllability 文献中的核心思想：

```text
个体从过去经验中学习 action 和 outcome 是否有关；
当有价值结果被体验为不可控时，后续主动尝试会下降，求助或回避会增加。
```

## 3. gated-lite 和其他模式的区别

建议保留四种模式：

```text
off:
  不计算 Bayesian policy。

shadow:
  计算 pi_bayes / q_bayes / confidence，但不影响真实行为。

gated-lite:
  Bayesian posterior 在证据足够时小幅影响真实行为，并且影响幅度受限。

on:
  Bayesian posterior policy 成为主策略来源。
```

近期推荐：

```text
shadow + gated-lite
```

近期不推荐：

```text
on
```

原因：

```text
shadow 太安全，但不能替代缺乏文献支撑的 rule 参数；
on 太激进，会削弱 LLM simulation 的主体性；
gated-lite 正好在中间。
```

## 4. gated-lite 的核心原则

### 4.1 LLM simulation 仍然是主体

LLM 继续负责：

```text
profile / persona 的语义一致性
task appraisal
event appraisal
avoid_reason 判断
support_mode 语义解释
event attribution
daily reflection
stage interview
final interview
qualitative coherence
```

Bayesian 模块只负责：

```text
action-outcome 经验记录
posterior outcome prediction
posterior expected utility
轻量策略校正
```

### 4.2 rule 不再主导策略

不推荐：

```text
pi_base = (1 - c) * pi_rule + c * pi_bayes
```

推荐：

```text
pi_prior = weak neutral prior
pi_bayes = posterior predictive policy
pi_shifted = gated_lite_shift(pi_current, pi_bayes)
pi_final = safety_guard(pi_shifted)
```

其中 `pi_current` 可以来自当前主实验链路：

```text
weak prior
LLM bounded semantic adjustment
当前 strategy deliberation
```

但不应再依赖复杂 rule 权重作为理论主线。

### 4.3 Bayesian 只能轻推，不能接管

gated-lite 的核心不是：

```text
pi_final = pi_bayes
```

而是：

```text
pi_final = lightly_shift(pi_current, pi_bayes, gate, max_delta)
```

通俗说：

```text
Bayesian 模块有证据时，可以把方向轻轻推向更符合历史经验的一边；
但不能一把夺走方向盘。
```

## 5. 学习对象：P(outcome_subtype | task_family, action)

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

## 6. Memory 结构

建议新增独立 memory，不要复用 `proto_bayesian_control_memory`。

推荐：

```text
proto_bayesian_policy_memory
```

示例：

```json
{
  "version": "policy_lite_v1",
  "families": {
    "payment_risk_confirmation": {
      "attempt_self": {
        "alpha": {
          "success_self": 1.0,
          "success_with_help_enabling": 0.1,
          "success_with_help_substituting": 0.1,
          "failure_after_attempt_low_uncontrollability": 1.0,
          "failure_after_attempt_mid_uncontrollability": 0.1,
          "failure_after_attempt_high_uncontrollability": 0.1,
          "failure_even_with_help": 0.1,
          "abandon_midway": 0.1,
          "avoid_without_attempt_helpless": 0.1,
          "avoid_without_attempt_risk": 0.1,
          "avoid_without_attempt_low_value": 0.1,
          "neutral_unknown": 0.1
        },
        "update_count": 2,
        "last_outcome_subtype": "failure_after_attempt_low_uncontrollability",
        "last_updated_day": 3
      }
    }
  }
}
```

注意：

```text
Bayesian controllability audit memory:
  解释 task_family 的总体可控性。

Bayesian policy memory:
  学习 task_family + action 下的 outcome subtype 分布。
```

这两个 memory 应该分开。

## 7. Utility 设计

Bayesian 模块必须有 utility，否则只是学概率，不是在选择策略。

建议第一版使用 theory-grounded utility：

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

## 8. Q_Bayes 和 pi_bayes

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

## 9. Evidence gate

gated-lite 必须有证据门槛。

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

## 10. Influence cap

gated-lite 必须限制每次策略变化幅度。

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
如果 Bayesian 一次把 action probability 改太多，系统就会逐渐变成 Bayesian policy agent，而不是 LLM simulation。
```

## 11. gated-lite 混合公式

第一版推荐用“限制偏移”的方式，而不是直接线性混合。

输入：

```text
pi_current(a)
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
    raw_delta_a = pi_bayes(a) - pi_current(a)
    delta_a = clip(raw_delta_a * confidence_a, -max_delta_per_action, max_delta_per_action)
```

然后：

```text
pi_shifted(a) = pi_current(a) + delta_a
pi_final = normalize(pi_shifted)
```

最后再过 safety guard：

```text
pi_final = safety_guard(pi_final)
```

这样有三个好处：

```text
1. Bayesian 有证据才生效
2. Bayesian 每次影响有限
3. 可以清楚记录 Bayesian 到底改了多少
```

## 12. Safety guard

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
fallback to current strategy distribution
```

不建议做：

```text
根据 helplessness 阈值重新大幅调权
根据 support_quality 手动大幅加减策略概率
根据 consecutive_failures 手动覆盖 Bayesian 结果
```

否则又会回到 rule-heavy policy。

## 13. LLM bounded semantic adjustment

LLM 不应被删除。

在 gated-lite 中，LLM 的角色是：

```text
解释任务语义
判断当前任务是否适合自主尝试
区分 risk_avoid / low_value_avoid / helpless_avoid
解释 support 是 enabling 还是 substituting
生成访谈和主观解释
在小幅范围内修正策略语义
```

建议：

```text
lambda_llm = 0.10 或 0.25
```

LLM 修正也应被记录，并且不能无边界覆盖 Bayesian/posterior 机制。

推荐链路：

```text
pi_current
-> Bayesian gated-lite shift
-> optional bounded LLM semantic adjustment
-> safety guard
-> pi_final
```

如果想更保守，也可以：

```text
pi_current
-> optional bounded LLM semantic adjustment
-> Bayesian gated-lite shift
-> safety guard
-> pi_final
```

第一版建议选择一种固定顺序，并在文档和 payload 中写清楚。

## 14. Payload 必须记录什么

gated-lite 最大的价值之一是可审计。

每次 episode 建议写入：

```json
{
  "bayesian_policy_lite": {
    "version": "policy_lite_v1",
    "mode": "gated_lite",
    "task_family": "payment_risk_confirmation",
    "actual_strategy": "seek_help_then_attempt",
    "pi_current": {
      "attempt_self": 0.40,
      "seek_help_then_attempt": 0.40,
      "avoid": 0.20
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
      "attempt_self": -0.09,
      "seek_help_then_attempt": 0.10,
      "avoid": 0.00
    },
    "pi_after_bayesian_shift": {
      "attempt_self": 0.31,
      "seek_help_then_attempt": 0.50,
      "avoid": 0.19
    },
    "pi_final": {
      "attempt_self": 0.31,
      "seek_help_then_attempt": 0.50,
      "avoid": 0.19
    },
    "max_delta_per_action": 0.10,
    "gate_threshold": 0.50,
    "status": "gated_lite_applied"
  }
}
```

这样后续可以回答审稿人的问题：

```text
Bayesian policy 什么时候介入？
介入了多少？
哪些 action 有足够证据？
最终策略到底改变了多少？
结果是否由 Bayesian posterior 而不是 rule 导致？
```

## 15. 后验更新

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

## 16. 和 Bayesian controllability audit 的关系

当前 Phase B 的 Bayesian controllability audit 是：

```text
outcome -> C_hat(task_family) -> audit
```

它主要解释：

```text
这个任务类型总体上被 agent 学成了多可控？
```

gated-lite policy 学的是：

```text
在这个任务类型下，不同 action 分别会导致什么 outcome subtype？
```

二者关系：

```text
Bayesian audit:
  解释可控性感知。

Bayesian gated-lite:
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

## 17. 消融和验证

如果 gated-lite 进入论文，至少要有这些对照：

```text
baseline: 当前 LLM simulation 主机制
audit-only: Bayesian controllability audit 不影响行为
shadow: Bayesian policy 只计算不影响行为
gated-lite: Bayesian policy 有门控地轻量影响行为
```

最好加敏感性分析：

```text
max_delta_per_action = 0.05 / 0.10 / 0.15
gate_threshold = 0.33 / 0.50 / 0.67
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
```

核心审稿问题：

```text
gated-lite 是否减少了 hand-crafted rule dependence？
gated-lite 是否保留 LLM simulation 的语义一致性？
gated-lite 是否让 action-outcome learning 更可解释？
gated-lite 是否导致策略过早收敛或过度回避？
```

## 18. 风险和保护

### 风险 1：越来越不像 LLM simulation

保护：

```text
max_delta_per_action <= 0.10
保留 LLM appraisal / attribution / interview
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

### 风险 4：结果解释不清

保护：

```text
完整记录 pi_current / pi_bayes / delta / pi_final
保留 off / shadow / gated-lite 对照
不要同时大改其他主机制
```

## 19. 最近一周建议

最推荐的一周目标：

```text
1. 实现 proto_bayesian_policy_memory
2. 实现 shadow mode
3. 实现 gated-lite mode，但默认不开
4. gated-lite 只在小规模实验中试跑
5. payload 完整记录 Bayesian 影响
6. 不做 on mode
```

不建议本周做：

```text
1. 让 Bayesian policy 完全接管策略
2. 大幅删除当前 LLM strategy deliberation
3. 把 utility 做得过复杂
4. 让 rule 继续参与主策略混合
5. 声称 full Bayesian RL
```

## 20. 最终审稿口径

推荐写法：

```text
We preserve the LLM-based social simulation architecture while introducing a gated Bayesian posterior predictive module for action-outcome learning. The module maintains Dirichlet beliefs over task-family and action-conditioned outcome subtypes, derives posterior expected utilities, and lightly shifts strategy probabilities only when action-specific evidence is sufficient. This design reduces reliance on hand-crafted rule weights while retaining LLM-based appraisal, attribution, interview, and qualitative coherence.
```

中文解释：

```text
我们没有把系统改成纯 RL agent。
我们保留 LLM simulation 的主体，只加入一个受门控限制的 Bayesian 经验学习模块。
它从过去 action-outcome 经验中学习，并在证据足够时轻量影响策略。
这样既减少人工 rule 参数，又保持 AgentSociety 的原有优势。
```

## 21. 总结

gated-lite 是当前最合理的路线，因为它同时满足三个目标：

```text
1. 保留 LLM simulation 的主体和 AgentSociety 优势。
2. 引入具有理论解释力的 Bayesian action-outcome learning。
3. 避免直接进入 full Bayesian RL 带来的实现和审稿风险。
```

一句话：

```text
gated-lite 不是让 Bayesian 接管 agent，而是让 Bayesian 在有证据时替代一部分缺乏文献支撑的手写 rule 权重，轻轻推动 agent 的策略倾向。
```

