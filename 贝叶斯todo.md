# Bayesian controllability belief TODO

## 目标

把 Huys & Dayan 的 *A Bayesian formulation of behavioral control* 作为我们 digital friction 实验的理论支撑，但不直接复刻其完整 MDP / Bayesian RL 模型，也不替换当前 `event_level_uncontrollability` 主流程。

核心方向：

```text
过去数字任务经历
  -> Bayesian controllability belief
  -> 解释 agent 对某类数字任务“重要结果是否受自己控制”的长期信念
  -> 先用于 post-hoc 分析和 audit
  -> 如果结果稳定，再小幅接入 task appraisal
```

## 设计原则

- 不新增复杂行为链，避免当前机制过度膨胀。
- 不把 Bayesian control 直接等同于 `event_level_uncontrollability`。
- 不声称完整实现 Huys & Dayan 的数学模型。
- 优先复用已有事件日志、task family、outcome、uncontrollability、support mode、task memory。
- 先做分析指标，再做审计字段，最后才考虑进入决策。
- 所有新增指标必须能从 `payload_json` 或 attempt rows 中复现。

## 理论解释

Huys & Dayan 的关键思想不是“失败次数越多越无助”，而是：

```text
个体从过去经历中学习一个关于可控性的先验：
我在乎的结果，是否能通过自己的行为可靠控制？
```

在我们的实验中，这个思想可以转写为：

```text
agent 对每个 digital task family 形成一个长期控制信念。
这个信念由过去的成功、失败、帮助是否有效、失败是否不可控共同更新。
```

## 不做什么

- 不直接照搬原论文的 action-outcome matrix。
- 不为每个数字任务强行定义完整动作集合和结果集合。
- 不把 `event_level_uncontrollability` 改成 Bayesian posterior。
- 不让 LLM 直接决定 Bayesian belief 数值。
- 第一阶段不让 Bayesian belief 影响 strategy、attribution、scope 或 helplessness 主公式。

## 核心变量

对 agent `i` 和 task family `f`，定义控制信念：

```text
C_i,f,t in [0, 1]
```

含义：

```text
agent i 在时间 t 认为 task family f 的重要结果有多大程度受自己行为控制。
```

用 Beta 分布表示：

```text
C_i,f,t ~ Beta(alpha_i,f,t, beta_i,f,t)
```

均值：

```text
C_hat_i,f,t = alpha_i,f,t / (alpha_i,f,t + beta_i,f,t)
```

直觉：

```text
alpha = 可控证据
beta = 不可控证据
```

## 事件证据映射

每次 digital task 结束后，把 outcome 转成一条 evidence `z`：

```text
z = 1.0 表示强可控证据
z = 0.0 表示强不可控证据
z = 0.5 表示中性或混合证据
```

初始建议：

| 事件条件 | z |
|---|---:|
| `success_self` | 1.00 |
| `success_with_help` + `enabling_support` | 0.75 |
| `success_with_help` + `substituting_support` | 0.45 |
| `failure_after_attempt` + `event_level_uncontrollability=0` | 0.45 |
| `failure_after_attempt` + `event_level_uncontrollability=1` | 0.25 |
| `failure_after_attempt` + `event_level_uncontrollability=2` | 0.05 |
| `failure_even_with_help` | 0.00 |
| `abandon_midway` | 0.15 |
| `avoid_without_attempt` + `helpless_avoid` | 0.10 |
| `avoid_without_attempt` + `risk_avoid` | 0.50 |
| `avoid_without_attempt` + `low_value_avoid` | 0.55 |

备注：

- `risk_avoid` 不应被强解释为不可控，因为它可能是理性避险。
- `low_value_avoid` 不应被强解释为不可控，因为它可能只是任务价值低。
- `failure_even_with_help` 是强不可控证据，尤其当帮助也没有保留 agency 时。

## 更新公式

轻量 Bayesian 更新：

```text
alpha' = rho * alpha + w * z
beta'  = rho * beta  + w * (1 - z)
```

其中：

```text
rho = 记忆保留率，例如 0.98
w   = 事件重要性权重
z   = 本次事件的可控性证据
```

事件重要性 `w` 第一版可以先固定为 1.0。

后续可扩展：

```text
w = 1.0 + task_value_weight + friction_salience_weight
```

但第一阶段不建议复杂化。

## Phase A: Post-hoc 分析，不改 agent 行为

目标：

用已有实验日志重建每个 agent / task family 的 Bayesian controllability belief 曲线。

输入：

- attempt rows
- `payload_json.outcome`
- `payload_json.task`
- `payload_json.event_level_uncontrollability`
- `payload_json.task_appraisal`
- `payload_json.update`

输出：

- 每个 agent、每个 task family 的 `alpha / beta / C_hat`
- 每个 world 的平均 `C_hat` 曲线
- `C_hat` 与 helplessness、avoidance、help seeking、success rate 的关系

要验证的问题：

- 高摩擦低帮助 world 是否让 `C_hat` 更快下降。
- 高帮助 world 是否保护 `C_hat`。
- `C_hat` 下降是否领先或伴随 helplessness 上升。
- `C_hat` 下降是否预测 avoid / seek help 增加。

建议新增脚本：

```text
examples/digital_friction_mvp/analysis_bayesian_control.py
```

建议输出：

```text
examples/digital_friction_mvp/analysis/bayesian_control_timeseries_<group_id>.csv
examples/digital_friction_mvp/analysis/bayesian_control_world_summary_<group_id>.csv
examples/digital_friction_mvp/analysis/bayesian_control_plots_<group_id>/
```

## Phase B: Audit-only runtime variable

目标：

如果 Phase A 结果清楚，再在 runtime 中记录 Bayesian control belief，但暂时不影响 agent 决策。

建议新增 status memory 字段：

```text
proto_bayesian_control_memory
```

结构：

```json
{
  "payment_risk_confirmation": {
    "alpha": 2.0,
    "beta": 4.0,
    "belief": 0.3333,
    "last_evidence_z": 0.05,
    "last_updated_day": 3
  }
}
```

写入位置：

```text
update_experience_memory(...) 之后
payload_json 生成之前
```

审计字段：

```text
payload_json.auxiliary_audit.bayesian_control
```

记录：

- enabled
- task_family
- alpha_before
- beta_before
- belief_before
- evidence_z
- evidence_reason
- alpha_after
- beta_after
- belief_after

## Phase C: 小幅接入 task appraisal

只有在 Phase A/B 结果稳定后，再考虑让 Bayesian belief 影响 task appraisal。

最小接入：

```text
low C_hat -> slightly lower felt_control
high C_hat -> slightly higher felt_control
```

建议不要直接改 helplessness 主公式。

建议公式：

```text
felt_control_adjustment = lambda_c * (C_hat - 0.5) * 100
```

例如：

```text
lambda_c = 0.10
```

则：

```text
C_hat = 0.2 -> felt_control -3
C_hat = 0.8 -> felt_control +3
```

这属于温和影响，不会压倒 LLM appraisal 或现有规则。

## 消融设计

如果 Phase C 接入，需要新增消融：

```text
full
no_bayesian_control
audit_only_bayesian_control
```

比较指标：

- helplessness_delta
- avoidance_tendency
- success_rate
- help_request_rate
- scope_spillover_total
- stage interview 中的控制感表达

## 论文写法

推荐表述：

```text
Inspired by Bayesian formulations of behavioral control, we model digital helplessness as a learned belief about whether valued digital outcomes are controllably achievable. Rather than replicating the full Bayesian RL model, we operationalize controllability through auditable task-level evidence and optionally reconstruct a lightweight Beta belief over each task family.
```

中文解释：

```text
我们受 Bayesian behavioral control 理论启发，把数字无助感理解为 agent 对“重要数字结果是否可控”的长期信念。我们不复刻完整 Bayesian RL，而是用已有事件证据重建轻量 Beta control belief，并把它作为可审计的理论桥梁。
```

## 风险

- 如果直接接入太多模块，会让机制链变得过复杂。
- 如果没有消融，审稿人会质疑 Bayesian belief 是否必要。
- 如果只做 post-hoc，需要诚实说明它是 analysis proxy，不是 runtime driver。
- 如果声称完整实现 Huys & Dayan，会被熟悉 computational psychiatry 的审稿人质疑。

## 推荐执行顺序

1. 先实现 post-hoc analysis，不改 agent 行为。
2. 用现有 10-day world_runner 结果重建 `C_hat` 曲线。
3. 检查 `C_hat` 是否和 helplessness / avoidance / world condition 有清楚关系。
4. 如果结果好，再加 audit-only runtime 记录。
5. 最后才考虑小幅接入 task appraisal。

## 当前最小可投稿版本建议

AAAI AISI 冲刺版优先采用：

```text
Phase A + 理论形式化
```

也就是：

- 代码主机制不大改。
- 论文中用 Huys & Dayan 支撑 controllability belief。
- 分析中用已有日志重建 Bayesian control belief。
- 用结果证明高摩擦 / 低帮助世界会降低 control belief，并伴随 helplessness 与 avoidance 上升。

这比直接新增复杂 Bayesian 模块更稳，也更符合当前项目节奏。
