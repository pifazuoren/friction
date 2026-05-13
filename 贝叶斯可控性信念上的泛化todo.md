# 贝叶斯可控性信念上的泛化 TODO

## 0. 一句话目标

在现有 `scope_spillover` 的基础上，新增一个更接近 Huys & Dayan 2009 的 **Bayesian controllability belief generalization**：

```text
agent 不只记住“某个 task_family + action 过去导致什么结果”，
还要形成一个“类似数字任务整体上有多可控”的贝叶斯信念，
并把这个信念作为新任务/相似任务中的弱先验。
```

通俗说：

```text
现在已有：
付款失败 -> agent 觉得类似任务也可能不行 -> self-efficacy spillover

想新增：
付款/登录/上传等任务多次显示“行动不太改变结果”
-> agent 形成“数字任务整体可控性较低”的 Bayesian belief
-> 新任务开始时，先验上更不相信行动能稳定带来好结果
```

## 1. 先明确：这不是替代现有 scope

现有 scope 机制应该保留。

当前已有泛化：

```text
event_attribution_scope_amplitude
-> scope_spillover
-> neighbor task_family 的 task_self_efficacy 下降
```

它回答的是：

```text
agent 是否把当前失败归因扩散到类似任务？
```

新增 Bayesian controllability belief 回答的是：

```text
从 action-outcome evidence 看，类似数字任务整体上到底有多可控？
```

两者分工：

| 层次 | 当前是否已有 | 作用 |
|---|---:|---|
| attribution/scope 泛化 | 有 | 心理归因扩散，影响 self-efficacy |
| Bayesian action-outcome posterior | 有 | 每个 task_family/action 学结果分布 |
| Bayesian controllability generalization | 暂无 | 跨 task_family 学“数字任务整体可控性” |

最终论文里可以说：

> We distinguish attributional scope spillover from Bayesian controllability-prior generalization.

中文就是：

> 我们区分了“心理归因上的泛化”和“贝叶斯可控性信念上的泛化”。

## 2. 和 Huys & Dayan 2009 的关系

Huys & Dayan 2009 的核心不是简单学习某个 action 的成功率，而是学习：

```text
这个环境中，有价值的结果到底有多少是行动可以可靠控制到的？
```

他们提出的关键思想包括：

1. outcome entropy：同一个动作导致的结果是否稳定。
2. achievable outcomes：不同动作是否能可靠达到不同结果。
3. controllably achievable reinforcement：有价值/避害的结果是否能被行动控制。
4. generalization：一个环境里学到的可控性信念，会影响新环境的先验。

我们不需要完整复刻他们的数学模型，但可以做一个轻量版本：

```text
每个 task_family 学 action-outcome posterior
-> 从 posterior 中计算 controllability estimate
-> 汇总成 domain/global controllability posterior
-> 给新 task_family 或低证据 task_family 提供弱先验
```

这比当前 gated-lite2 更接近 Huys & Dayan 的地方在于：

```text
不只学 action -> outcome，
还学“类似任务整体上是否可控”，并把这个信念泛化出去。
```

## 3. 推荐最小实现：Phase C0 Shadow-Only

第一阶段不要直接影响真实策略。

建议先做 shadow-only：

```text
PROTO_BAYESIAN_CONTROLLABILITY_GENERALIZATION_MODE=shadow
```

只记录：

- per-family controllability estimate；
- global/domain controllability belief；
- generalized prior that would be used；
- 和现有 `pi_bayes / pi_final / action / outcome / helplessness` 的关系。

不改变：

- actual strategy；
- outcome；
- helplessness；
- attribution；
- DB schema；
- existing `proto_bayesian_policy_memory` 更新逻辑。

这样最安全，也最容易和审稿人解释。

## 4. 新增 memory 建议

不要混进现有 `proto_bayesian_policy_memory`。

建议新增：

```text
proto_bayesian_controllability_memory
```

示例结构：

```json
{
  "version": "controllability_generalization_v1",
  "global": {
    "alpha_control_high": 1.0,
    "alpha_control_low": 1.0,
    "mean_controllability": 0.5,
    "update_count": 0,
    "last_updated_day": -1
  },
  "families": {
    "payment_risk_confirmation": {
      "alpha_control_high": 1.0,
      "alpha_control_low": 1.0,
      "mean_controllability": 0.5,
      "evidence_count": 0,
      "last_entropy_control": 0.0,
      "last_reward_control": 0.0,
      "last_generalization_weight": 0.0,
      "last_updated_day": -1
    }
  }
}
```

这里不要一开始就做复杂连续分布。最小版本可以用 Beta-Bernoulli 风格：

```text
alpha_control_high / alpha_control_low
```

代表：

```text
这个 task/domain 的经验更像“行动有控制”还是“行动没控制”
```

## 5. 每个 task_family 的 controllability 怎么算

第一版建议做一个简单、可解释、可审计的指标。

从现有 `proto_bayesian_policy_memory` 里拿：

```text
P(outcome_subtype | task_family, action)
```

然后计算三类信号：

### 5.1 outcome entropy control

看每个 action 的结果分布是否稳定。

```text
低熵 = 同一个 action 常导致少数几个稳定结果 = 更可控
高熵 = 同一个 action 结果很散 = 更不可控
```

示意：

```text
entropy_control(action) = 1 - normalized_entropy(P(outcome | family, action))
family_entropy_control = weighted_mean(entropy_control(action))
```

注意：这只是“稳定性”，不是完整可控性。

### 5.2 action contrast control

看不同 action 的结果分布是否真的不同。

如果三个 action 的结果分布很像：

```text
attempt_self -> failure
seek_help_then_attempt -> failure
avoid -> no_attempt/failure-like
```

那说明行动选择不太改变结果。

如果不同 action 结果差异明显：

```text
attempt_self -> success_self
seek_help_then_attempt -> success_with_help
avoid -> no_attempt
```

那说明 action 有控制力。

可以用分布距离：

```text
action_contrast_control = mean_pairwise_TVD(P(outcome|action_i), P(outcome|action_j))
```

### 5.3 reward/control relevance

Huys & Dayan 最重视的是“有价值结果是否可控”。

所以还要看：

```text
成功/低不可控失败/避免高损害 这些有价值结果，
是否能被某些 action 稳定提高概率。
```

第一版可以定义：

```text
good_outcomes = success_self + success_with_help + failure_after_attempt_low_uncontrollability
bad_outcomes = failure_high_uncontrollability + failure_even_with_help + abandon_midway + no_attempt
```

然后：

```text
best_good_prob = max_a P(good_outcomes | family, action=a)
worst_good_prob = min_a P(good_outcomes | family, action=a)
reward_control = best_good_prob - worst_good_prob
```

直觉：

```text
如果最好的 action 明显比最差的 action 更可能带来好结果，
说明 agent 有可控性。
```

## 6. 第一版 family controllability score

建议先用简单加权：

```text
family_control_score =
  0.30 * entropy_control
  + 0.30 * action_contrast_control
  + 0.40 * reward_control
```

范围 clamp 到 `[0, 1]`。

解释：

- entropy_control：行动结果是否稳定；
- action_contrast_control：不同行动是否真的带来不同结果；
- reward_control：好结果是否能被行动提高。

其中 `reward_control` 权重略高，因为它最接近 Huys & Dayan 的 controllably achievable reinforcement。

## 7. 怎么更新 controllability posterior

第一版可以把 `family_control_score` 离散成一条软证据：

```text
alpha_control_high += weight * family_control_score
alpha_control_low += weight * (1 - family_control_score)
```

然后：

```text
mean_controllability =
  alpha_control_high / (alpha_control_high + alpha_control_low)
```

global posterior 也同步更新：

```text
global.alpha_control_high += generalization_weight * family_control_score
global.alpha_control_low += generalization_weight * (1 - family_control_score)
```

注意：第一版不要让单次事件强烈改变 global belief。建议：

```text
generalization_weight = 0.05 ~ 0.20
```

或者只在 family evidence_count 达到阈值后更新 global。

## 8. 如何做跨 task_family 泛化

当前已经有 task family similarity，可复用 `experience_memory.py` 里的 `_TASK_FAMILY_SIMILARITY` 思路。

新增 generalized prior：

```text
generalized_controllability_prior(family)
  = (1 - eta) * family_mean_controllability
    + eta * weighted_neighbor_mean
```

如果当前 family 证据很少，则 eta 大一些：

```text
evidence_count low -> eta high
evidence_count high -> eta low
```

示例：

```text
eta = confidence_k / (evidence_count + confidence_k)
```

直觉：

```text
这个任务自己没多少经验时，更多参考类似任务和 global belief；
这个任务自己经验多了，就更多相信自己。
```

## 9. 如何接入现有 Bayesian gated-lite2

第一阶段 shadow-only 不接入策略，只记录：

```text
family_control_score
family_mean_controllability
global_mean_controllability
generalized_controllability_prior
would_adjust_prior_alpha
```

第二阶段 gated-lite 接入时，建议只影响 Bayesian policy prior，不直接改 LLM reference。

可以这样做：

```text
如果 generalized_controllability_prior 低：
  增加 outcome posterior 的不确定性 / flatten action-outcome contrast

如果 generalized_controllability_prior 高：
  保留或增强 action-outcome contrast
```

更保守的做法：

```text
只在 low evidence family 中使用 generalized prior；
已有足够 family evidence 时，不用 global 泛化覆盖本地经验。
```

避免：

```text
一次坏经验 -> 全局不可控 -> 所有任务马上 avoid
```

这是最重要的安全点。

## 10. 审计 payload 建议

新增 audit payload：

```json
{
  "version": "controllability_generalization_v1",
  "mode": "shadow",
  "task_family": "payment_risk_confirmation",
  "family_control_score": 0.42,
  "entropy_control": 0.51,
  "action_contrast_control": 0.31,
  "reward_control": 0.39,
  "family_mean_controllability_before": 0.50,
  "family_mean_controllability_after": 0.48,
  "global_mean_controllability_before": 0.50,
  "global_mean_controllability_after": 0.49,
  "generalization_eta": 0.33,
  "neighbor_family_weights": {},
  "generalized_controllability_prior": 0.47,
  "would_apply_to_policy_prior": false,
  "policy_unchanged": true,
  "day": 7
}
```

可以写入：

```text
payload_json.auxiliary_audit.bayesian_controllability_generalization
```

## 11. 测试计划

### 11.1 helper 单测

新增测试：

```text
empty memory 安全初始化
malformed memory 安全恢复
entropy_control 在确定性分布时更高
entropy_control 在均匀分布时更低
action_contrast_control 在 action 分布相同时接近 0
action_contrast_control 在 action 分布差异大时升高
reward_control 在好结果可由某个 action 提高时升高
family_control_score clamp 到 [0,1]
global posterior 不被单次事件大幅拖动
low evidence family 更多使用 generalized prior
high evidence family 更多使用 local prior
shadow mode 不改变 policy / outcome / helplessness
```

### 11.2 agent 行为不变测试

shadow-only 必须保证：

```text
同 seed 下，打开 controllability generalization shadow 不改变 sampled action
不改变 outcome
不改变 helplessness_after
不改变 attribution
不改变 proto_bayesian_policy_memory
只新增 audit payload 和 controllability memory
```

### 11.3 audit 导出测试

新增导出 CSV：

```text
bayesian_controllability_generalization_summary_*.csv
bayesian_controllability_generalization_by_world_*.csv
bayesian_controllability_generalization_by_world_day_*.csv
bayesian_controllability_generalization_by_task_family_*.csv
bayesian_controllability_generalization_qc_*.csv
```

关键字段：

```text
payload_coverage
mean_family_control_score
mean_entropy_control
mean_action_contrast_control
mean_reward_control
mean_global_controllability
mean_generalized_controllability_prior
policy_unchanged_rate
```

## 12. 实验设计建议

### 12.1 先做 shadow-only

第一组：

```text
PROTO_BAYESIAN_CONTROLLABILITY_GENERALIZATION_MODE=shadow
```

和现有 gated-lite2 一起跑。

目标不是改变结果，而是看：

- high_friction_low_assist 是否学到更低 controllability；
- low_friction_high_assist 是否保持更高 controllability；
- global belief 是否缓慢移动；
- generalized prior 是否在早期/低证据 family 更明显。

### 12.2 再做 gated-lite 接入

等 shadow 指标健康后，再考虑：

```text
PROTO_BAYESIAN_CONTROLLABILITY_GENERALIZATION_MODE=gated_lite
```

第一版只允许小幅影响 `pi_bayes`，不直接动 `pi_ref`。

建议限制：

```text
max_controllability_prior_shift <= 0.03
只在 family evidence_count < threshold 时启用
不允许单日 global shift > 0.02
```

## 13. AAAI/AISI 叙事价值

这一步的价值很高。

当前 gated-lite2 可以说：

```text
agent learns action-outcome posterior.
```

加上 controllability generalization 后，可以说：

```text
agent also learns and generalizes a Bayesian belief about controllability across related digital tasks.
```

这会更接近 Huys & Dayan 2009，也更贴合 learned helplessness 的理论核心：

```text
不只是某个任务失败，
而是个体学到“类似环境中我的行动影响有限”，
并把这种信念带到后续任务。
```

推荐论文表述：

> Inspired by Bayesian formulations of behavioral control, we separate attributional scope spillover from Bayesian controllability-prior generalization. The former captures narrative/psychological generalization, while the latter summarizes action-outcome evidence into a transferable prior over controllability across related digital task families.

## 14. 风险与防线

### 风险 1：自证循环

如果低 controllability prior 太快影响策略，agent 会更少尝试，导致更少成功经验，再进一步降低 controllability。

防线：

```text
先 shadow-only
gated-lite 时只小幅影响
保留 exploration floor
不让 avoid 反向证明 attempt 不可控
```

### 风险 2：和 scope_spillover 重复

如果写不清，审稿人会觉得两个泛化机制重复。

防线：

```text
scope_spillover = attribution/self-efficacy generalization
controllability generalization = Bayesian action-outcome evidence generalization
```

### 风险 3：过度声称完整 Bayesian RL

不能说这是完整 Huys & Dayan model。

应该说：

```text
lightweight approximation inspired by Bayesian behavioral control
```

### 风险 4：utility 仍然手写

reward_control 依赖 good/bad outcome 定义和 utility profile。

防线：

```text
做 sensitivity analysis
后续用老人访谈/专家标注校准
不声称 human-calibrated
```

## 15. 推荐优先级

### P0：只写设计，不动主链

- 明确和 scope_spillover 的区别。
- 明确不声称 full Bayesian RL。
- 明确 shadow-only 先行。

### P1：实现 shadow helper

- 新增纯函数 helper。
- 只读 `proto_bayesian_policy_memory`。
- 输出 controllability audit。
- 不改变任何真实行为。

### P2：导出 audit CSV

- summary/by_world/by_day/by_task_family/qc。
- 看 world 区分是否符合预期。

### P3：低风险 gated-lite 接入

- 只在 evidence low 的 family 上用 generalized prior。
- 小幅影响 `pi_bayes`。
- 不直接改 LLM semantic reference。

### P4：论文实验

- shadow calibration；
- gated-lite ablation；
- sensitivity；
- staged learned helplessness；
- human/expert validation。

## 16. 最小版本完成标准

最小版本做完后，应该能回答：

1. 高摩擦低支持世界是否产生更低 Bayesian controllability belief？
2. 低摩擦高支持世界是否保持更高 controllability belief？
3. 这种 belief 是否会随天数和经验逐步变化，而不是第一天就跳变？
4. 它和现有 scope_spillover 是否有区别？
5. shadow-only 是否完全不改变外显行为？

如果这五个问题都能回答，就值得进入下一阶段。
