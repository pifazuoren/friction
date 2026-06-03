# App Context Gate TODO

## 1. 核心问题

当前 app-context 入口层已经比旧的 mobile-intention 入口层更稳：

```text
TalkingData app category
-> app_context
-> task_opportunity_distribution
-> DigitalTask / context-only
```

但现在仍有一个关键问题：只要 `selected_app_context` 属于 task-eligible context，系统就几乎必然生成一个困难 `DigitalTask`。

这会把“用户进入某类 app 场景”误当成“用户遇到困难数字任务”。例如：

```text
finance_context
```

不一定等于：

```text
payment_risk_confirmation
```

它也可能只是查看余额、扫一眼通知、打开后退出、浏览账单，或者进行没有明显摩擦的普通操作。

因此下一步要把链路改成：

```text
TalkingData app_context exposure
-> Task Occurrence Gate
-> if gate passed: task_opportunity_distribution -> DigitalTask
-> if gate not passed: context-only session
```

一句话：TalkingData 负责“什么时候进入什么手机使用场景”；Task Occurrence Gate 负责“这个场景是否真的变成困难数字任务”。

## 2. 论文依据

### 2.1 Peng & Zhu 2020

Citation:

```text
Peng, T.-Q., & Zhu, J. J. H. (2020).
Mobile Phone Use as Sequential Processes: From Discrete Behaviors to Sessions of Behaviors and Trajectories of Sessions.
Journal of Computer-Mediated Communication.
DOI: 10.1093/jcmc/zmz029
```

原文证据 1：

```text
Mobile phone use is an unfolding process by nature.
```

含义：手机使用不是一个个孤立 app event，而是连续展开的过程。

原文证据 2：

```text
mobile sessions composed of an uninterrupted set of behaviors
```

含义：app 使用记录应该先聚合成 session，而不是每一条记录都直接当成一次完整任务。

原文证据 3：

```text
mobile trajectories composed of mobile sessions and mobile-off time
```

含义：手机使用还包括“用手机”和“不用手机”之间的交替。我们不能只看 app 出现，还要看它在日常轨迹里的位置。

原文证据 4：

```text
5.5 million mobile sessions are constructed out of the 11.5 million records
```

含义：论文明确把原始 app use records 转换成 mobile sessions。这支持我们在 TalkingData app event 和 DigitalTask 之间加一个 session / gate 层。

原文证据 5：

```text
3.7 million (67%) are solo-app sessions
```

含义：大量手机 session 只涉及一个 app 类别。也就是说，很多手机使用是短的、简单的、场景性的，不应该默认变成复杂数字任务。

原文证据 6：

```text
time-budget approach reduces mobile phone use to a duration or frequency
```

含义：只用频率或时长理解手机使用是不够的。我们也不应该只因为某类 app_context 出现频率高，就让困难任务高频出现。

### 2.2 Zhu et al. 2018

Citation:

```text
Zhu, J. J. H., Chen, H. X., Peng, T. Q., Liu, X. F., & Dai, H. X. (2018).
How to measure sessions of mobile phone use? Quantification, evaluation, and applications.
Mobile Media & Communication.
DOI: 10.1177/2050157917748351
```

使用方式：作为 session measurement 的方法依据。Peng & Zhu 2020 明确引用它来说明 mobile sessions 的构造。

注意：我们当前没有把这篇全文纳入 MinerU，因此暂不在论文中引用更细原文。后续如果要写正式 related work，应下载并抽取全文后再补原文句子。

### 2.3 Boase & Ling 2013

Citation:

```text
Boase, J., & Ling, R. (2013).
Measuring mobile phone use: Self-report versus log data.
Journal of Computer-Mediated Communication.
DOI: 10.1111/jcc4.12021
```

使用方式：支持用 log data 校准手机使用 exposure，而不是完全依赖自报或纯模拟。

注意：这篇支持“为什么 TalkingData 有价值”，但不能直接告诉我们困难 DigitalTask 发生概率。

### 2.4 Oulasvirta et al. 2012

Citation:

```text
Oulasvirta, A., Rattenbury, T., Ma, L., & Raita, E. (2012).
Habits make smartphone use more pervasive.
Personal and Ubiquitous Computing.
DOI: 10.1007/s00779-011-0412-2
```

使用方式：支持很多手机使用可能是习惯性、短时、低任务强度的行为。

注意：这篇可以帮助解释“app_context exposure 不一定是困难任务”。但在当前计划中，它只作为辅助依据；主依据仍是 Peng & Zhu 2020 的 session / trajectory 框架。

## 3. 我们的论文口径

不要写成：

```text
Peng & Zhu 2020 directly gives DigitalTask occurrence probabilities.
```

应该写成：

```text
Peng & Zhu 2020 motivates a boundary between app-use exposure and task occurrence.
```

更准确的说法：

```text
TalkingData anchors app-context exposure.
The app-context gate is a calibrated simulation layer that converts exposure into potential digital-friction tasks.
World presets then manipulate task difficulty, risk, accessibility, and support after the task occurs.
```

中文解释：

```text
TalkingData 告诉我们老人可能什么时候进入什么手机场景；
gate 决定这个场景有没有真的变成困难任务；
world setting 决定这个困难任务有多难、有多风险、有没有帮助。
```

## 4. 计划中的新链路

目标链路：

```text
TalkingData event
-> app_context prior
-> selected_app_context
-> Task Occurrence Gate
-> context-only session OR DigitalTask
-> strategy selection
-> outcome realization
-> helplessness / controllability update
```

更具体：

```text
1. 从 TalkingData prior 抽样 selected_app_context。
2. 如果 selected_app_context 是 context-only，直接记录 context-only session。
3. 如果 selected_app_context 是 task-eligible，进入 Task Occurrence Gate。
4. Gate 通过，才从 task_opportunity_distribution 抽样 task_family。
5. Gate 不通过，记录为 task-eligible context exposure but no difficult task.
```

## 5. Gate 应该怎么设计

第一版采用保守、可审计、少抽象的规则表。

新增 artifact 可以叫：

```text
task_occurrence_prior_by_context.json
```

建议第一版字段：

```json
{
  "schema_version": "task_occurrence_prior_by_context_v1",
  "source": "calibrated_simulation_layer",
  "notes": [
    "TalkingData anchors app-context exposure, not app-internal difficult tasks.",
    "Occurrence probabilities are calibrated assumptions, not direct labels from TalkingData."
  ],
  "task_occurrence_by_context": {
    "finance_context": 0.25,
    "public_service_context": 0.25,
    "health_service_context": 0.22,
    "shopping_lifestyle_context": 0.18,
    "navigation_transport_context": 0.18,
    "education_work_context": 0.15
  }
}
```

这些数值不是最终定稿，只是 smoke / calibration 起点。

建议同时跑三档敏感性：

```text
low exposure:
  base multiplier = 0.50

medium exposure:
  base multiplier = 1.00

high exposure:
  base multiplier = 1.50
```

目标不是强行调出某个结果，而是检查：

```text
不同 gate 强度下，world ordering 是否稳定；
high friction 是否仍比 baseline 差；
high assist 是否仍有缓冲作用；
helplessness 是否不再因为任务过密而快速撞顶。
```

## 6. World 设置和 Gate 的边界

主实验中，Task Occurrence Gate 应该先保持 world-neutral。

也就是说：

```text
同一个 selected_app_context，在四个 world 中具有相同的 task occurrence probability。
```

原因：

```text
主实验要让四个 world 的差异来自任务发生后的 friction severity / support availability，
而不是让 high_friction world 同时拥有更多任务和更难任务。
```

主实验中：

```text
TalkingData / gate:
  控制 exposure 和 task occurrence。

world preset:
  控制 task difficulty、risk、accessibility、support quality、outcome probability。
```

后续 ablation 可以测试 world-sensitive gate，例如 high friction world 让任务更容易暴露。但这不应作为第一版主机制。

## 7. Runtime 修改范围

### 7.1 config_runtime.py

新增 env：

```text
PROTO_TASK_OCCURRENCE_GATE_ENABLED=true|false
PROTO_TASK_OCCURRENCE_PRIOR_PATH=...
PROTO_TASK_OCCURRENCE_GATE_MULTIPLIER=1.0
```

默认建议：

```text
enabled=false
multiplier=1.0
```

这样不破坏旧实验可比性。新实验显式打开。

### 7.2 task_assignment.py

在 `_evaluate_app_context_entry_for_agent(...)` 中插入 gate：

当前：

```text
selected_app_context
-> if task eligible
-> task_opportunity_distribution
-> DigitalTask
```

修改为：

```text
selected_app_context
-> if task eligible
-> task_occurrence_probability
-> stable gate draw
-> if failed: context-only exposure
-> if passed: task_opportunity_distribution -> DigitalTask
```

稳定抽样要复用现有 stable hash 风格，不引入新随机系统。

Gate seed 建议包含：

```text
seed
agent_id
day
tick_seconds
profile_bucket
selected_app_context
version
```

### 7.3 audit 字段

每次 app-context entry 需要记录：

```text
task_occurrence_gate_enabled
task_occurrence_probability
task_occurrence_multiplier
task_occurrence_gate_roll
task_occurrence_gate_passed
task_occurrence_gate_source
task_occurrence_gate_reason
task_eligible_context_exposure
context_only_reason
generated_task_family
```

如果 gate 没通过：

```text
task_generated=false
entry_status=task_eligible_context_no_task
context_only_reason=task_occurrence_gate_not_passed
```

如果 gate 关闭：

```text
task_occurrence_gate_enabled=false
task_occurrence_probability=1.0 for eligible contexts
task_occurrence_gate_passed=true for eligible contexts
```

这样旧逻辑和新逻辑可以在 summary 里对齐比较。

## 8. Summary / Validation 修改

### 8.1 summary 新增指标

```text
app_context_exposure_count
task_eligible_context_exposure_count
task_occurrence_gate_pass_count
task_occurrence_gate_pass_rate
context_only_session_count
task_generated_count
tasks_per_agent_day
tasks_per_task_eligible_context_exposure
task_occurrence_probability_mean
task_occurrence_gate_roll_mean
```

### 8.2 May 4-7 validation 口径

May 4-7 可以验证：

```text
app_context distribution
hourly app_context distribution
task_eligible_context_mass
context_only_mass
LLM rerank 是否扭曲 app_context prior
```

May 4-7 不能直接验证：

```text
真实困难 DigitalTask 发生率
真实失败率
真实 helplessness 变化
```

因为 TalkingData 只有 app 使用记录和类别，不知道用户是否遇到登录失败、付款风险、材料上传卡住等 app-internal friction。

## 9. Test Plan

### 9.1 Unit tests

```text
gate disabled:
  app_context_rule 行为与当前版本一致。

context-only context:
  不进入 gate，不生成 DigitalTask。

task-eligible context + gate failed:
  不生成 DigitalTask；
  entry_status=task_eligible_context_no_task；
  audit 字段完整。

task-eligible context + gate passed:
  正常进入 task_opportunity_distribution；
  生成 DigitalTask；
  audit 中记录 gate_passed=true。

stable gate:
  同 seed / agent / day / tick / context 下 gate roll 可复现。

invalid occurrence artifact:
  非法 context 或概率不在 [0,1] 时明确报错。
```

### 9.2 Smoke tests

先跑：

```text
1-day / 4-world / app_context_rule / gate enabled
```

再跑：

```text
1-day / 4-world / app_context_llm_rerank_online_mc / gate enabled
```

检查：

```text
app_context distribution 是否仍接近 TalkingData reference；
task_generated_count 是否明显下降；
baseline negative event density 是否下降；
trajectory fallback / app-context fallback 是否没有异常飙升。
```

### 9.3 Calibration tests

跑三档：

```text
gate_multiplier=0.50
gate_multiplier=1.00
gate_multiplier=1.50
```

对比：

```text
tasks_per_agent_day
success_rate
negative_feedback_rate
helplessness_delta
world ordering
high/low friction separation
assist buffering effect
```

## 10. 预期影响

预期好处：

```text
baseline 不再每天遇到过多困难任务；
helplessness 不再主要由任务密度推高；
high friction 的效果更清楚地来自任务难度/风险/低支持；
TalkingData validation 的边界更清晰；
论文方法更容易解释给审稿人。
```

可能风险：

```text
gate 过低会让任务太少，world differences 变弱；
gate 过高会回到当前问题；
如果 LLM rerank 过度偏向 task-eligible context，仍可能推高任务率。
```

因此必须报告：

```text
task occurrence gate pass rate
tasks per agent-day
selected_app_context distribution
task_eligible_context exposure mass
DigitalTask family distribution
```

## 11. 推荐第一步

先不动 outcome、helplessness、Bayesian、Huys。

第一步只做入口层最小修改：

```text
1. 新增 task_occurrence_prior_by_context.json
2. 新增 gate config
3. 在 app_context entry 内插入 stable gate
4. 补 audit 和 summary
5. 跑 1-day smoke
```

如果 smoke 稳定，再跑：

```text
7-day / 4-world / gate_multiplier=0.50, 1.00, 1.50
```

主论文先报告 `gate_multiplier=1.00`，把另外两组放 robustness / sensitivity。

