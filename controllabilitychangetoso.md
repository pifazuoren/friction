# Controllability 机制改造注意点

## 当前要注意的点

1. `C_family` 不能替代 `event_attribution_scope`。

   `scope_spillover` 的理论来源主要是 Abramson, Seligman & Teasdale (1978) 的 attributional reformulation。也就是说，扩散范围应该由 attribution 的 global-specific 维度决定，而不是由 Huys-Dayan controllability 直接决定。

2. `C_family` 不能直接等同于 helplessness。

   `C_family` 是从 action-outcome posterior 推出来的 task-family controllability diagnostic。它回答的是“在这个任务族里，行动是否能可靠地产生有价值结果”。`helplessness` 是 agent 的心理状态，受到 outcome、uncontrollability、self-efficacy、attribution、memory 等共同影响。

3. Bayesian gated-lite2 仍然是 evidence layer，不是心理中介本身。

   当前 `bayesian_policy_lite.py` 学的是：

   ```text
   P(outcome_subtype | task_family, action)
   ```

   它回答“做某个 action 后通常会发生什么”。真正适合作为中间心理机制的是从这个 posterior 派生出来的 controllability belief。

4. `event_level_uncontrollability` 和 `C_family` 是不同层级。

   `event_level_uncontrollability` 是单次事件层面的 perceived noncontingency，当前用于 helplessness update 和 scope spillover。

   `C_family` 是跨多次经验累积出来的 family-level learned controllability。

5. 不要让 controllability 同时强影响 outcome、policy 和 helplessness。

   如果 `C_family` 既影响行动，又影响 outcome，又影响 helplessness，而 outcome 又反过来更新 `C_family`，机制会变成自我强化闭环。第一阶段应保持低扰动、可审计，并用 ablation 检查。

6. `avoid -> no_attempt` 不能抬高 task controllability。

   回避可能很稳定，但这只说明行为稳定，不说明任务可控。主 `C_family` 应继续主要使用 `attempt_self` 和 `seek_help_then_attempt`。

7. utility profile 是手写的，不能过度声称。

   `reward_control_chi_lite` 依赖 outcome utility。它适合做 theory-informed diagnostic，但需要 sensitivity analysis，不能声称是 human-calibrated utility。

## 和现有机制的区别

### 现有 Bayesian gated-lite2

当前 Bayesian gated-lite2 的主链是：

```text
LLM semantic pi_ref
→ action-outcome posterior
→ Q_bayes / pi_bayes
→ confidence + entropy gate
→ bounded pi_final
```

它的作用是给 LLM reference policy 外面加一层低扰动的 action-outcome 学习修正。

它不是直接建模“我是否觉得任务可控”，而是先学习不同 action 过去对应什么 outcome。

### 现有 helplessness update

当前 helplessness update 是 post-outcome state transition：

```text
outcome_type
+ event_level_uncontrollability
+ low task_self_efficacy
- controllable_success_memory protection
→ helplessness_delta
```

它用的是单次事件的不可控判断和当前心理状态，还没有直接使用 `C_family`。

### 现有 scope spillover

当前 scope spillover 是：

```text
event_attribution_scope_amplitude
× normalized_event_uncontrollability
× task-family similarity
→ neighboring task_self_efficacy penalty
```

它更接近 Abramson et al. (1978)：global attribution 决定 helplessness 是否跨情境扩散。

### 改造后的 controllability 主中介

建议目标链是：

```text
Task Event
→ LLM Appraisal
→ Action-Outcome Evidence
→ Learned Controllability Belief
→ Policy / Helplessness / Scope
→ Outcome
→ Memory + Posterior Update
```

这里 `Learned Controllability Belief` 可以聚合：

```text
C_event: LLM/appraisal perceived control
C_family: posterior-derived family controllability
C_global: global controllability trace
confidence: evidence confidence
```

但第一阶段最好先作为 audit/shadow：

```text
C_pre_action
C_after_event
lagged prediction
policy unchanged or bounded modulation only
```

### 最稳的论文表述

不要说：

```text
Bayesian posterior directly causes learned helplessness.
```

更稳的是：

```text
Action-outcome posterior provides evidence for a learned controllability belief.
This belief can be audited and tested as a mediator between digital friction experience and later avoidance, help-seeking, helplessness, and scope generalization.
```

## 推荐改造原则

1. 先新增统一 audit 对象，而不是立刻重写行为。

   ```text
   learned_controllability_belief
   ```

2. 先让它记录：

   ```text
   C_event
   C_family
   C_global
   C_pre_action
   confidence
   source_breakdown
   ```

3. 再做 lagged prediction：

   ```text
   C_t-1 → avoid / seek_help / helplessness_delta / scope_spillover
   ```

4. 如果要接入行为，只允许 bounded modulation。

   低 controllability 不应直接推高 avoid；更安全是 flatten policy。高 controllability 可以轻微降低 avoid、提高 best non-avoid action。

5. 如果要接入 helplessness update，应使用 lagged or post-event controllability，并保留 ablation。

   不建议第一版让 `C_family` 直接大幅改变 helplessness。

6. scope 仍然保留 attributional globality 主导。

   可以把 noncontingency strength 从单次 `event_level_uncontrollability` 轻微扩展为：

   ```text
   0.75 * normalized_event_uncontrollability
   + 0.25 * (1 - C_family) * family_confidence
   ```

   但主控变量仍应是：

   ```text
   event_attribution_scope_amplitude
   ```

