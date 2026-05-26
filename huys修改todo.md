# Huys-Dayan 完善修改 TODO

## 0. 目标

把当前 Huys-Dayan-lite 从“策略末端的小幅调制器”升级为更有解释力的 **controllability belief layer**：

```text
过去行动-结果经验
→ task-family controllability diagnostic
→ cross-family controllability prior
→ bounded policy shaping
→ final strategy
```

核心目标不是把参数简单调大，而是让 Huys-Dayan-inspired controllability 更接近理论含义：

```text
agent 学到“我的行动是否能可靠改变有价值结果”，
并把这种可控性信念带到相似数字任务中。
```

## 1. 当前流程分析

当前策略生成链路大致是：

```text
Task + memory
↓
LLM task appraisal / strategy deliberation
↓
semantic reference policy
↓
Bayesian action-outcome posterior
↓
Bayesian gated-lite pi_final
↓
C_family before-event diagnostic
↓
Huys-Dayan-lite gated modulation
↓
Final strategy sampling
↓
Outcome
↓
Memory / helplessness update
```

其中各层含义如下：

```text
LLM semantic policy:
  根据任务语义、agent 状态、记忆、支持条件，形成初始策略倾向。

Bayesian action-outcome posterior:
  根据 P(outcome | task_family, action) 估计不同 action 的经验价值。

C_family:
  从 posterior 中派生 task-family 级可控性诊断。
  它看同一 action 是否稳定、不同 action 是否有差别、有价值 outcome 是否可控。

当前 Huys modulation:
  在 Bayesian pi_final 之后，用 C_family 对策略做小幅 gated adjustment。
```

当前 Huys 的优点：

```text
1. 不直接改 outcome。
2. 不直接改 helplessness_delta。
3. 使用 before-event C_family，避免当前 outcome 泄漏。
4. 有 confidence gate、max_delta、probability floor，比较安全。
5. audit 比较清楚，适合作为 conservative baseline。
```

当前 Huys 的问题：

```text
1. 位置太靠后，只是末端微调。
2. low-C 主要 shrink 到 reference policy，真实 delta 很小。
3. 还没有跨 task_family 的 controllability prior。
4. 不能清楚表达“agent 对类似数字任务整体是否可控”的学习。
5. 对 high-friction + high-assist 场景缺少明确 support-aware intervention。
```

所以当前版本更适合作为：

```text
conservative Huys-Dayan modulation baseline
```

而不是最终的强干预版本。

## 2. 文献约束

Huys and Dayan (2009) 支持的核心不是“低可控性直接等于回避”，而是：

```text
control prior 会影响：
  exploration
  expected reward
  action-value contrast
  desirable outcomes 是否可控
```

因此，我们不能把 Huys 改成：

```text
low C -> always avoid
```

更稳的解释是：

```text
low C:
  action-value contrast 变弱，
  有价值结果看起来不稳定可达，
  agent 更需要支持、脚手架或保守探索。

high C:
  action-value contrast 更清楚，
  agent 更相信选择正确 action 能改变结果，
  因而更愿意 attempt_self 或减少 avoid。
```

相关机制边界：

```text
Scope spillover:
  归因/自我效能泛化，“我不行”的扩散。

Bayesian controllability generalization:
  action-outcome evidence 泛化，“行动是否有用”的扩散。
```

这两个都可以存在，但不能互相替代。

## 3. 修改总路线

建议分三层推进：

```text
Phase H0: 保留当前 conservative Huys，不破坏现有实验。
Phase H1: 新增 cross-family controllability generalization，先 shadow-only。
Phase H2: 新增 strong controllability-prior policy shaping，作为独立 ablation。
```

不要一次性把所有逻辑接进主实验。先观察，再干预，再比较。

## 4. Phase H0：保留当前 Huys 作为保守对照

当前 `control_centered_modulate` 不删除。

它的定位改为：

```text
Conservative bounded Huys modulation
```

用途：

```text
1. 作为强 Huys 的对照组。
2. 证明末端轻量调制本身是否足够。
3. 保留已有 audit / analysis 兼容性。
```

论文口径：

```text
The conservative Huys-Dayan-lite module applies a bounded, confidence-gated
post-policy modulation based on task-family controllability diagnostics.
```

限制说明：

```text
它不是完整 Huys-Dayan model；
它不代表强 policy intervention；
它主要是保守审计和小幅调节版本。
```

## 5. Phase H1：新增 Cross-Family Controllability Prior

新增一个更接近 Huys-Dayan generalization 的层：

```text
Bayesian controllability generalization
```

它回答：

```text
agent 是否从多个相似数字任务的 action-outcome evidence 中学到：
这些任务整体上是否可控？
```

直觉例子：

```text
付款、登录、上传、服务申请中：
attempt_self 经常失败；
seek_help_then_attempt 也经常失败；
不同 action 带来的结果差异很小。

那么 agent 应该逐渐形成：
类似数字任务的 generalized controllability prior 较低。
```

第一版必须 shadow-only：

```text
只记录，不改策略；
只审计，不改 outcome；
只形成指标，不改 helplessness。
```

需要记录的概念字段：

```text
family_control_score
family_mean_controllability
global_mean_controllability
neighbor_similarity_contribution
generalized_controllability_prior
policy_unchanged
```

评估目标：

```text
1. high_friction_low_assist 是否显示更低 controllability。
2. low_friction_high_assist 是否显示更高 controllability。
3. generalized prior 是否随天数缓慢变化，而不是一天内跳变。
4. 它是否和 scope_spillover 形成不同解释。
5. shadow-only 是否完全不改变 action / outcome / H。
```

## 6. Phase H2：新增 Strong Huys Policy Shaping

当 H1 shadow 指标健康后，再新增强干预版本。

强 Huys 不再只是：

```text
pi_base -> shrink slightly toward pi_ref
```

而是：

```text
controllability prior -> bounded policy shaping
```

它应该在策略生成中扮演更清楚的角色：

```text
LLM semantic policy
→ Bayesian posterior policy
→ C_family / generalized C_prior
→ support-aware controllability shaping
→ final policy
```

建议新增独立实验模式：

```text
strong_controllability_policy_shaping
```

不要覆盖当前 conservative mode。

## 7. Strong Huys 的行为原则

强 Huys 不能写成“低可控性直接回避”。

推荐原则：

```text
Low controllability + support available:
  增加 seek_help_then_attempt；
  减少 avoid；
  解释为 support scaffold。

Low controllability + support unavailable:
  降低过强 action preference；
  保留 exploration floor；
  不让 agent 因少量证据直接塌缩到 avoid。

High controllability:
  增加 attempt_self 或 best_nonavoid action；
  减少 avoid；
  减少不必要的 help dependence。
```

这样可以表达：

```text
低 C 不是“放弃”，而是“当前任务需要脚手架或更谨慎的探索”。
高 C 不是“盲目自信”，而是“行动差异变得更可靠，可以更主动尝试”。
```

## 8. Final Strategy 的组成

修改后的 final strategy 应由这些信号共同决定：

```text
1. LLM semantic policy:
   当前任务语义、风险、难度、支持条件、agent 状态。

2. Bayesian posterior policy:
   当前 task_family 下 P(outcome | action) 的经验价值。

3. C_family:
   当前 task_family 的可控性诊断。

4. generalized controllability prior:
   相似 task families 和 global/domain 层面的可控性信念。

5. support-aware Huys shaping:
   低 C 时是否转向 seek_help，而不是直接 avoid。

6. safety bounds:
   probability floor、max_delta、confidence gate、audit。
```

最终仍然只输出三个策略概率：

```text
attempt_self
seek_help_then_attempt
avoid
```

然后再进行策略采样。

## 9. 明确不做什么

本轮 Huys 完善不应该做：

```text
不让 C_family 直接决定 outcome。
不让 C_family 直接修改 helplessness_delta。
不把低 C 简化成 avoid。
不删除 LLM semantic policy。
不删除 Bayesian action-outcome posterior。
不让 post-outcome C_after_event 影响当前 action。
不把 scope_spillover 和 controllability generalization 合并。
不宣称完整复现 Huys and Dayan 2009。
```

Huys 对 helplessness 的影响路径必须保持间接：

```text
Huys changes strategy distribution
→ strategy changes outcome distribution
→ outcome and attribution enter helplessness update
```

## 10. 推荐实验矩阵

建议后续至少跑以下 ablation：

```text
A. scaled_nonlinear only
B. scaled_nonlinear + Bayesian policy
C. scaled_nonlinear + conservative Huys
D. scaled_nonlinear + controllability generalization shadow
E. scaled_nonlinear + strong Huys policy shaping
```

如果资源有限，最小版本：

```text
A. Bayesian policy only
B. Bayesian + conservative Huys
C. Bayesian + strong Huys
```

关键比较指标：

```text
1. final H mean / helplessness_delta
2. success_rate
3. help_seek_rate
4. abandon_rate / avoid_without_attempt
5. negative share
6. support response effectiveness
7. C_family trajectory
8. generalized controllability prior trajectory
9. policy delta size
10. world ordering 是否保持
```

特别关注：

```text
high_friction_high_assist 是否被 strong Huys 改善；
low_friction_high_assist 是否仍然最好；
high friction worlds 是否仍显著差于 baseline；
help 是否变成真正 scaffold，而不是制造依赖。
```

## 11. 论文叙事

最稳的论文叙事：

```text
We distinguish attributional generalization from action-outcome controllability
generalization. The former captures how negative interpretations spill over to
similar tasks, while the latter summarizes action-conditioned outcome evidence
into a transferable controllability prior. A Huys-Dayan-inspired policy shaping
layer then uses this prior to adjust the balance between self-attempt, help-seeking,
and avoidance under bounded, auditable constraints.
```

中文口径：

```text
我们区分两种泛化：
一种是归因上的“我不行”扩散；
另一种是行动-结果证据上的“行动是否有用”扩散。

完善后的 Huys-Dayan 模块不再只是末端微调，
而是把可控性信念作为策略生成中的核心中介。
```

## 12. 验收标准

完善后的 Huys-Dayan 机制应满足：

```text
1. Conservative Huys 旧行为可复现。
2. Shadow controllability generalization 不改变行为。
3. generalized controllability prior 能区分不同 world。
4. Strong Huys 产生可观察 policy delta。
5. Strong Huys 不直接改 outcome / helplessness。
6. Low C 不被简单解释为 avoid。
7. 有 support 时，low C 可以推动 scaffolded help-seeking。
8. 所有 policy changes 有 audit、gate 和 bounded delta。
9. 多 seed 下结果方向可复现。
10. 论文表述保持 inspired-by，而不是 full Huys-Dayan implementation。
```

## 13. 推荐优先级

```text
P0: 写清楚理论边界和两种泛化区别。
P1: 保留 current Huys，并将其定位为 conservative baseline。
P2: 做 controllability generalization shadow。
P3: 跑 shadow 分析，确认指标健康。
P4: 做 strong Huys policy shaping。
P5: 跑 ablation，判断是否进入主论文结果。
```

当前最值得先做的是：

```text
P2: controllability generalization shadow
```

因为如果 cross-family controllability prior 本身不健康，直接做 strong intervention 很容易变成过度调参。

