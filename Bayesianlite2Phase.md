# Bayesian Gated-Lite2 分阶段推进计划

## 总体定位

`Bayesian gated-lite2` 不是把当前系统改成完整 Bayesian RL agent，而是在保留 LLM social simulation 主链的前提下，引入一个受限、可审计的 Bayesian action-outcome learning 模块。

核心目标：

```text
LLM 负责语义理解、task appraisal、event appraisal、attribution、reflection、interview；
Bayesian policy-lite 负责从 task_family + action -> outcome 的经验中学习；
rule 不再作为常规策略主干，只保留为 fallback / safety guard；
Bayesian 只有在证据足够时，才能小幅影响真实行动概率。
```

完整 gated-lite2 不应一步到位上线。更稳妥的路线是：

```text
shadow validation
-> utility calibration
-> conservative gated-lite pilot
-> gated-lite main experiment
-> ablation / sensitivity / validation
```

## Phase 1: Shadow Validation

当前状态：已完成。

目标：

```text
只计算 Bayesian posterior predictive policy，不干预真实行为。
```

已完成内容：

```text
proto_bayesian_policy_memory
policy_outcome_subtype
action-specific Dirichlet prior
Q_bayes
pi_bayes_shadow
confidence_by_action
posterior_entropy_by_action
payload audit
posterior update for observed action only
```

已验证内容：

```text
shadow payload 全覆盖
uses_post_outcome_information_for_policy=false
strategy_unchanged=true
shadow mode 不改变真实策略
C_hat 与 pi_avoid 呈理论一致关系
```

当前发现：

```text
Bayesian shadow 有解释信号；
但 pi_bayes_shadow 明显偏向 avoid；
因此不能直接进入强行为介入。
```

本阶段可声称：

```text
We implemented a shadow Bayesian posterior predictive audit for action-outcome learning.
```

本阶段不可声称：

```text
Bayesian policy improves agent behavior.
Bayesian posterior already drives agent decisions.
```

## Phase 2: Utility Calibration

目标：

```text
先校准 Bayesian 小顾问的 utility，避免它因为失败成本过高而过度偏向 avoid。
```

要做的修改：

```text
重新检查 no_attempt utility
区分 helpless_avoid / risk_avoid / low_value_avoid 的长期成本
检查 success_with_help 的 utility 是否需要区分 expected enabling support 与 substituting support
确保 pre-outcome Q_bayes 不使用 post-outcome support_mode / avoid_reason / attribution
保留 action-specific prior，不把 impossible outcome 设成高先验
```

建议方向：

```text
helpless_avoid: 应有较明显长期负效用
risk_avoid: 可为轻负或接近中性，尤其在高风险任务中
low_value_avoid: 可接近中性
no_attempt: 不应比所有 failure 都“安全太多”，否则 Bayesian 会过度保守
success_self: 高正效用
success_with_help: 正效用，但应弱于真正可控的 self success；如果预期帮助有效，可适度提高
```

验证方式：

```text
仍然使用 shadow mode
重新跑 3-seed 10-day 4-world shadow 实验
检查 pi_bayes_shadow 是否仍过度偏 avoid
检查 C_hat / pi_avoid / pi_help / pi_attempt 的方向是否合理
```

成功标准：

```text
baseline_low_friction 中 avoid 不应长期成为绝对 dominant
low_friction_high_assist 中 seek_help 或 attempt_self 应该有明显优势
high_friction_low_assist 中 avoid 上升可以接受，但不能完全压倒其他 action
pi_bayes_shadow 与 friction/support 条件保持理论一致方向
```

本阶段仍不可声称：

```text
Bayesian policy has changed behavior.
```

## Phase 3: Conservative Gated-Lite Pilot

含义：

```text
第一次让 Bayesian 小幅影响真实行动概率，但只在证据足够时、以很小幅度介入。
```

推荐初始配置：

```text
PROTO_BAYESIAN_POLICY_LITE_MODE=gated_lite
PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD=0.50
PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA=0.05
PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR=0.05
PROTO_BAYESIAN_POLICY_LITE_TAU=1.0
PROTO_BAYESIAN_POLICY_LITE_CONFIDENCE_K=4
PROTO_BAYESIAN_POLICY_LITE_RHO=1.0
PROTO_BAYESIAN_POLICY_LITE_WEIGHT=1.0
```

要实现的机制：

```text
pi_semantic = bounded LLM semantic policy
pi_bayes = Bayesian posterior predictive policy

if confidence[action] < gate_threshold:
    delta[action] = 0
else:
    raw_delta[action] = pi_bayes[action] - pi_semantic[action]
    delta[action] = clip(raw_delta[action] * confidence[action], -max_delta, +max_delta)

pi_after_bayesian_shift = normalize(pi_semantic + delta)
pi_final = safety_guard(pi_after_bayesian_shift)
```

必须记录的 payload：

```text
pi_prior
pi_llm
llm_confidence
llm_reason
lambda_llm
pi_semantic
q_bayes
pi_bayes
confidence_by_action
gate_by_action
delta_before_normalize
delta_applied
pi_after_bayesian_shift
pi_final
max_delta_per_action
gate_threshold
prob_floor
safety_guard_status
intervention_applied
total_variation_distance
```

pilot 规模：

```text
先跑 1 seed 或 3 seeds
4 worlds
10 days
保持 paired design
```

重点检查：

```text
attempt_rate 是否突然崩塌
avoidance 是否异常升高
help_seek 是否合理变化
helplessness 是否出现 runaway loop
intervention_applied 比例是否合理
Bayesian delta 平均幅度是否足够小
低摩擦高支持世界是否没有被推向过度 avoid
```

成功标准：

```text
intervention_applied 不是 0，但也不是每次都介入
平均 delta 很小
max_delta 生效
gate_threshold 生效
行为方向不崩
payload 能解释每一次 Bayesian 是否介入和介入多少
```

失败信号：

```text
avoidance 在所有 worlds 中异常升高
low_friction_high_assist 也被推向 avoid
helplessness 出现明显 runaway
Bayesian delta 经常达到上限
safety guard 经常 fallback
```

## Phase 4: Gated-Lite Main Experiment

目标：

```text
在 conservative pilot 稳定后，正式评估 gated-lite2 的行为机制效果。
```

建议实验设置：

```text
seeds >= 10
4 worlds
10 days 或更长
same paired design
显式记录所有 gated-lite2 env configs
```

核心对照：

```text
current rule+LLM baseline
Bayesian controllability audit-only
Bayesian policy-lite shadow-only
Bayesian gated-lite2
```

主要问题：

```text
gated-lite2 是否减少 rule-heavy dependence？
gated-lite2 是否保留 LLM semantic coherence？
gated-lite2 是否让 action-outcome learning 更可解释？
gated-lite2 是否没有导致过度 avoid？
gated-lite2 是否在不同 seeds 下稳定？
```

主要指标：

```text
attempt_rate
help_seek_rate
avoid_rate
success_rate
negative_feedback_rate
helplessness_delta
trust_delta
avoidance_delta
intervention_applied_rate
mean_bayesian_delta
total_variation_distance(pi_semantic, pi_final)
gate_open_rate
safety_guard_fallback_rate
```

本阶段可声称：

```text
gated-lite2 behavior is influenced by a bounded Bayesian posterior predictive module.
```

仍需谨慎：

```text
如果没有 human validation，不能声称真实老年人行为已被验证。
```

## Phase 5: Ablation, Sensitivity, And Validation

目标：

```text
为 AAAI / AISI / AAMAS 审稿准备机制证据，证明结果不是由某个手调参数或 prompt 偶然制造。
```

必要消融：

```text
gated-lite2 without Bayesian shift
gated-lite2 without LLM semantic adjustment
gated-lite2 without evidence gate
gated-lite2 without max_delta
gated-lite2 max_delta=0
gated-lite2 without avoid-as-evidence
shadow-only vs gated-lite2
```

敏感性分析：

```text
max_delta_per_action = 0.00 / 0.05 / 0.10 / 0.15
gate_threshold = 0.33 / 0.50 / 0.67
tau sensitivity
confidence_k sensitivity
prob_floor sensitivity
rho sensitivity
utility mapping sensitivity
```

shadow/prediction 分析：

```text
pi_bayes_shadow 是否预测下一步 action
pi_bayes_shadow 是否预测下一步 outcome
Q_bayes 是否与 success / failure / avoid 方向一致
C_hat 与 pi_avoid / helplessness_delta / avoidance_delta 的关系
posterior confidence 是否随经验增加而上升
```

human / qualitative validation：

```text
expert trajectory validation
older adult / caregiver vignette validation
LLM attribution coding validation
interview grounding validation
```

本阶段要防的 reviewer 问题：

```text
是不是 rule 仍在主导？
是不是 Bayesian 只是 heuristic？
是不是 utility 手调制造结果？
是不是 LLM prompt artifact？
是不是没有现实数据支撑？
是不是过度回避？
是不是缺少 calibration？
```

## 推荐当前下一步

当前项目已经完成 Phase 1。

最合理的下一步是：

```text
进入 Phase 2: Utility Calibration
```

不建议立刻做：

```text
full gated-lite2 main experiment
Bayesian policy 完全接管
max_delta >= 0.10 的正式实验
声称 Bayesian policy 已改善行为
```

推荐短期路线：

```text
1. 调整 utility，降低 shadow 过度 avoid 倾向。
2. 重新跑 shadow-only 小实验。
3. 如果 shadow 分布更合理，再做 conservative gated-lite pilot。
4. pilot 稳定后，再进入 main experiment 和 ablation。
```

