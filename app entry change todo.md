# App Entry Change Todo

这份 todo 用来整理后续 app entry 改造方向。核心思想是：不要把 AgentSociety 原生流程硬搬进来，而是借用它的“需求 -> 计划 -> 执行 -> 反馈 -> 反思”决策骨架，嵌入我们现有的数字摩擦与习得性无助实验。

更新后的关键口径：我们的仿真 step 是 1 小时，但这不等于 1 小时只能选择 1 个 app context。TalkingData 中一个小时可能有多个 event，一个 event 也可能有多个 active app。因此 app entry 应该从“单个 app context”升级为“小时级 app entry bundle”：

```text
一个小时 app entry bundle =
是否活跃
+ 这一小时 active app exposure 强度
+ 各 app_context 的 exposure counts
+ 一个 primary_context 用于进入 task occurrence gate
```

也就是说：

```text
数据 / memory / validation 层：保留多个 app_context
task / strategy / outcome 层：只选一个 primary_context 进入任务链
```

## 总体定位

当前实验核心仍然是数字摩擦下的习得性无助形成机制。

TalkingData 的作用不是直接验证 helplessness，而是提供可观测的 app entry / app context 行为窗口，用来校准和验证 agent 的 baseline 数字行为是否像真实老人。

整体关系：

```text
Day 1-3 TalkingData
-> replay 真实小时级 app entry bundle，强制 agent 经历前三天 app-context exposure
-> 后续 task gate / strategy / outcome / helplessness 按 baseline 正常机制更新
-> 形成 Day 4 开始时的 habit memory / episodic memory / structured state

Day 4-7 baseline world
-> agent 依靠 memory / needs / controllability / reflection 自主生成小时级 app entry bundle
-> 与真实 Day 4-7 app entry bundle 做 held-out validation

Day 4-7 friction worlds
-> 在同一 agent 底座上加入 friction
-> 分析 helplessness / avoidance / help-seeking / task persistence 相对 baseline 的变化
```

一句话版本：

```text
TalkingData 负责校准和验证“人像不像”；
friction worlds 负责研究“无助感怎么形成”。
```

## 设计原则

- Day 1-3 只用于生成个体 habit / memory / persona，不直接作为 Day 4-7 的答案模板。
- Day 1-3 的 app entry bundle 由 TalkingData 强制给定，agent 不自主选择 app entry。
- Day 1-3 的 app entry 之后，task occurrence gate、strategy、outcome、helplessness update 按 baseline 正常机制运行。
- Day 4-7 baseline 必须由 agent 自己滚动生成 hourly app entry bundle。
- Day 4-7 真实数据只能用于最终验证，不能在 rollout 时提供给 agent。
- 1 小时仿真步长不等于 1 小时只能有 1 个 app context；完整 bundle 保留多 context，任务链只消费 primary_context。
- App entry 是 observable behavior，helplessness 是 latent state。
- Helplessness 必须影响后续 app entry，否则它只是结果曲线，不是 learned helplessness 机制。
- 当前小时的 outcome 只能影响下一小时及之后，不能回流影响当前小时 app entry。
- App 使用不等于 DigitalTask。只有 task occurrence gate 通过后，才进入 strategy / outcome / helplessness update 链条。
- Baseline world 应保持低摩擦正常生活状态，不能本身就产生过强 helplessness。

## 目标流程

实验需要区分两个运行模式。

### Hourly App Entry Bundle

目标：解决 TalkingData 高频 event 与我们 1 小时仿真步长之间的粒度差异。

Day 1-3 和 Day 4-7 都统一成同一种 bundle schema：

```json
{
  "device_id": "...",
  "day": 4,
  "hour": 9,
  "active": true,
  "active_event_app_exposures": 32,
  "app_context_counts": {
    "finance_context": 16,
    "finance_candidate_review": 10,
    "communication_social_context": 2,
    "education_work_context": 2,
    "taxonomy_profile_only": 2
  },
  "primary_context": "finance_context",
  "source": "talkingdata_replay_or_simulated"
}
```

字段含义：

- `active`: 这一小时有没有手机活跃记录。
- `active_event_app_exposures`: 这一小时有多少条 `event_id + app_id + is_active=1` exposure。
- `app_context_counts`: 这一小时各 app_context 分别出现多少次。
- `primary_context`: 从 bundle 中选出的主要 context，用于 task occurrence gate。
- `source`: Day 1-3 为 `talkingdata_replay`，Day 4-7 rollout 为 `simulated`。

原则：

- 不把一个小时压缩成单一 app context。
- 不让一个小时生成多个 DigitalTask，避免任务密度失控。
- 所有 context 都写入 app exposure / habit memory。
- 只有 `primary_context` 进入 task occurrence gate。
- 如果 gate fail，这一小时只是普通 app 使用；如果 gate pass，才生成一个 DigitalTask。

### Day 1-3 Replay Mode

```text
t 小时真实 TalkingData app entry bundle
-> 强制写入所有 app-context exposure
-> 更新 app-entry habit memory / hourly intensity memory
-> 从 bundle 中选择 primary_context
-> task occurrence gate 判断 primary_context 是否生成 DigitalTask
-> 若无 DigitalTask：记录 context-only app use
-> 若有 DigitalTask：进入 strategy selection / outcome realization / helplessness update
-> 写入 episodic memory 与 structured state
-> 每日 reflection 更新 thought / attitude / confidence
```

注意：

- Replay mode 中 app entry 不由 agent 选择。
- Replay mode 中后续机制仍然正常运行。
- Replay mode 结束后，Day 1-3 经历沉淀为 Day 4 的初始 memory / state。
- Replay mode 的输入优先使用新清洗后的 hourly summary / event-app context 表。

### Day 4-7 Rollout Mode

```text
t 时刻开始
-> 读取截至 t-1 的 habit memory / episodic memory / helplessness state
-> 生成 digital need
-> 生成 candidate app contexts 及其权重
-> TPB-style decision 生成 hourly app entry bundle
-> 记录 bundle 中所有 app-context exposure
-> 从 bundle 中选择 primary_context
-> task occurrence gate 判断 primary_context 是否生成 DigitalTask
-> 若无 DigitalTask：轻量更新 memory，本小时结束
-> 若有 DigitalTask：进入 strategy selection / outcome realization / helplessness update
-> 写入 episodic memory 与 structured state
-> 每日 reflection 更新 thought / attitude / confidence
```

## 任务拆分

### 1. Calibration Layer

目标：用 Day 1-3 TalkingData 通过 replay mode 生成这个人的初始数字行为底座。

需要产出：

- 每个 device_id 的常用 app context 分布
- 每小时活跃节律
- 每小时 app entry bundle 分布
- 每小时 active_event_app_exposures 强度分布
- 每小时 app_context_counts 分布
- 每小时 primary_context 分布
- 常用时段与连续使用习惯
- 高频 app context / 低频 app context
- 个体是否偏社交、娱乐、金融、工具、健康等
- 初始 digital confidence
- 初始 friction sensitivity
- 初始 device / phone price proxy
- Day 1-3 replay 后形成的 recent app memory
- Day 1-3 replay 后形成的 task / support / helplessness 结构化状态
- Day 1-3 daily reflection

注意：

- Day 1-3 是 habit source，不是 Day 4-7 prediction template。
- 不要把 Day 1-3 和 Day 4-7 的相似分布直接当作仿真能力。
- Day 1-3 的真实 app entry 只能强制 app exposure，不能提供真实 task outcome，因为 TalkingData 没有 outcome / helplessness 标签。
- Day 1-3 的 task/outcome/helplessness 是模型机制生成的 latent state，需要在论文中说明不是观测标签。
- Day 1-3 不应只沉淀 top context，也要沉淀 context counts 和 intensity，否则 Day 4-7 只能生成过粗的行为。

### 2. Digital Needs Layer

目标：替换 AgentSociety 原生 hungry / tired / social 等需求，形成数字行为需求层。

候选 needs：

```text
social_need
entertainment_need
finance_need
tool_need
health_need
habitual_check_need
idle_browse_need
avoidance_need
no_app_need
```

输入：

- 当前小时、星期、日内节律
- Day 1-3 habit memory
- 最近几小时 app 使用
- 昨日 reflection
- 当前 helplessness / confidence / frustration
- friction world 设置
- support availability

输出：

- current_digital_need
- active_probability
- expected_intensity_level
- preferred_context_weight_hint
- need_confidence
- need_reasoning

Todo：

- [ ] 设计 digital needs schema
- [ ] 明确每类 need 与 app context 的候选映射
- [ ] 决定 needs 是 rule-first、LLM-first 还是 hybrid
- [ ] 增加 no_app / avoidance 作为合法 need
- [ ] 让 needs 不只决定 primary_context，也影响 active_or_not 与 intensity

### 3. Candidate App Context Layer

目标：从 digital need 生成候选 app contexts 及其权重，而不是让 LLM 无边界生成。

候选来源：

- 个体 Day 1-3 使用过的 app contexts
- 老年群体全局常见 app contexts
- 当前 digital need 对应的 app contexts
- no_app / context_only 选项

原则：

- 强习惯 app context 要保留惯性。
- 不能因为一次任务失败就让所有 app context 都消失。
- 高 helplessness 主要影响高任务压力、高摩擦 app context，不应过度影响娱乐、社交等普通使用。

Todo：

- [ ] 构建 per-device candidate app context pool
- [ ] 加入 global elderly fallback pool
- [ ] 给每个 candidate 标注 task pressure / friction sensitivity
- [ ] 增加 no_app 作为候选项
- [ ] 输出候选 context 权重，用于生成 context_counts，而不只是单选

### 4. TPB Decision Layer

目标：借用 AgentSociety 原生 PlanBlock 的 Theory of Planned Behavior 思路，让 hourly app entry bundle 的生成有心理解释。

三个核心评分：

```text
attitude:
这个老人是否喜欢/习惯这个 app context？

subjective_norm:
这个时间、生活场景、日常节律下是否合理？

perceived_control:
当前 friction、手机能力、数字信心、疲劳、挫败感下，是否觉得自己能顺利用？
```

建议输出：

```json
{
  "active": true,
  "active_event_app_exposures": 12,
  "app_context_counts": {
    "finance_context": 6,
    "communication_social_context": 3,
    "device_tool_context": 2,
    "taxonomy_profile_only": 1
  },
  "primary_context": "finance_context",
  "selected_need": "finance_need",
  "attitude": 0.72,
  "subjective_norm": 0.64,
  "perceived_control": 0.48,
  "confidence": 0.70,
  "reasoning": "...",
  "helplessness_effect": "mild avoidance pressure"
}
```

Todo：

- [ ] 设计 app entry decision prompt
- [ ] 限制 LLM 只能从候选 app contexts 中选择
- [ ] 输出 bundle，而不是只输出单个 selected_app_context
- [ ] 约束 active_event_app_exposures 的范围来自 Day 1-3 个体强度分布
- [ ] 约束 app_context_counts 的总和等于 active_event_app_exposures
- [ ] 约束 primary_context 必须来自 app_context_counts 中出现的 context
- [ ] 把 helplessness / controllability / recent memory 作为输入
- [ ] 记录 TPB 分数，方便后续分析和消融

### 5. Execution, Task Gate, and Feedback

目标：把 app entry 与 DigitalTask 解耦。

流程：

```text
Hourly app entry bundle generated
-> 记录 bundle 中所有 app-context exposure
-> 选择 primary_context
-> 判断 primary_context 是否 task-eligible context
-> task occurrence gate
-> gate fail: context-only memory update
-> gate pass: generate DigitalTask
-> strategy selection
-> outcome realization
-> helplessness update
```

Todo：

- [ ] 保留当前 Task Occurrence Gate
- [ ] 检查 gate prior 是否只来自 reference，不使用 validation
- [ ] 将 gate pass/fail 写入日志
- [ ] 区分 context_only app use 和 task_episode
- [ ] 确保非任务型 app use 不直接触发 helplessness update
- [ ] 确保一个小时最多生成一个 DigitalTask
- [ ] 确保非 primary context 只进入 exposure / memory，不直接进入 task chain

## Memory 设计

### Habit Memory

来自 Day 1-3 TalkingData，用于描述稳定行为习惯。

内容：

- 常用 app context
- 常用时间段
- 日内节律
- 每小时 active_or_not 习惯
- 每小时 intensity 习惯
- 每小时 app_context_counts 习惯
- 每小时 primary_context 习惯
- app context 转移习惯
- 高频/低频类别

作用：

- 决定 baseline app entry 是否像真实老人。

### Episodic Memory

模拟过程中形成的经历流，对应 AgentSociety 原生 stream memory。

内容示例：

```text
昨天支付 app 打开后卡在验证码。
上午尝试挂号时求助家人后成功。
某个金融场景多次带来风险提示和困惑。
晚上娱乐 app 使用顺利，没有明显挫败。
```

作用：

- 给 app entry decision、task appraisal、attribution、daily reflection 提供经历证据。

### Helplessness State

结构化心理状态，不直接由 LLM 任意改写。

建议变量：

```text
global_helplessness
payment_helplessness
healthcare_helplessness
service_helplessness
tool_helplessness
digital_confidence
perceived_controllability
frustration
support_expectation
avoidance_tendency
controllable_success_memory
```

作用：

- 作为 latent state 影响后续 app entry、strategy selection 和 outcome appraisal。

Todo：

- [ ] 明确哪些状态是 global，哪些按 task family / app context 存储
- [ ] 防止 stream memory 直接输出 helplessness_delta
- [ ] 让 structured state 负责正式心理更新
- [ ] 让 stream memory 作为 retrieval evidence

## Helplessness 如何影响 App Entry

目标：形成完整闭环。

```text
App Entry
-> DigitalTask / Strategy
-> Outcome
-> Helplessness Update
-> Memory / Belief Update
-> 下一小时 App Entry
```

影响方式：

- helplessness 高：降低高摩擦、高任务压力 app context 的进入概率
- helplessness 高：降低 active_probability 或 active_event_app_exposures，尤其是任务压力较高的 context
- perceived controllability 低：更倾向 avoid 或 seek help
- frustration 高：降低连续尝试意愿
- support expectation 高：遇到任务型 app 时更可能 seek help
- 某类 app 失败记忆多：该类 app context 权重下降
- controllable success memory 高：降低未来负向经历的冲击敏感度

建议 app entry score：

```text
App Entry score =
个人习惯
+ 当前小时需求
+ app 类别偏好
+ 最近使用惯性
- helplessness / avoidance penalty
- perceived friction cost
+ support availability bonus
```

在 bundle 版本中，可以拆成三个分数：

```text
active_score:
这一小时是否使用手机

intensity_score:
这一小时使用强度是多少

context_weight_score:
这一小时各 app_context 占多少
```

`primary_context` 再从生成后的 context counts 中选择。

Todo：

- [ ] 设计 helplessness 对 app context 的 penalty 函数
- [ ] 区分强习惯 app 与高任务压力 app
- [ ] 避免一次失败导致全局 app 使用崩塌
- [ ] 验证 friction world 是否通过 helplessness 间接影响 app entry

## Baseline 与 Friction Worlds

### Baseline World

用途：

- 验证 agent 的 Day 4-7 app entry 是否接近真实 held-out TalkingData。
- 作为 normal-world control。

要求：

- helplessness 可以自然波动，但不应明显塌陷。
- DigitalTask 密度应受 occurrence gate 控制。
- baseline 不应成为隐性 high-friction world。

建议检查：

- app-context distribution vs real Day 4-7
- hourly activity pattern
- hourly active_or_not F1
- hourly exposure intensity MAE
- hourly app_context bundle distance
- task_generated_rate
- task_occurrence_gate_pass_rate
- baseline helplessness_delta
- negative_feedback_rate
- avoid / abandon rate

### Friction Worlds

用途：

- 在相同 agent 底座上加入 counterfactual friction。
- 分析 helplessness、avoidance、help-seeking、task persistence 相对 baseline 的变化。

比较方式：

```text
friction effect = friction world - baseline world
```

注意：

- 不要把 friction world 直接和真实 Day 4-7 比绝对准确率。
- 真实 Day 4-7 只用于校验 baseline 行为底座。

## 实验验收

### App Entry Validation

- [ ] Day 4-7 baseline app-context bundle 分布接近真实 validation
- [ ] 小时级 active_or_not 接近真实 validation
- [ ] 小时级 active_event_app_exposures 强度接近真实 validation
- [ ] 小时级 app_context_counts 接近真实 validation
- [ ] primary_context 分布接近真实 validation
- [ ] 个体层面 app context 偏好有一定保留
- [ ] no_app / context_only / task_episode 比例合理

### Mechanism Validation

- [ ] baseline helplessness_delta 不应过大
- [ ] high friction low assist 的 helplessness_delta 高于 baseline
- [ ] high friction high assist 的上升被 support 缓冲
- [ ] low friction high assist 应更接近恢复或低伤害
- [ ] helplessness 上升能影响后续 app entry / avoid / seek-help

### Ablation

- [ ] No occurrence gate
- [ ] No memory feedback
- [ ] No helplessness feedback to app entry
- [ ] No controllability
- [ ] No helper support
- [ ] Rule-only app entry vs LLM/TPB app entry

## 推荐实现顺序

### Phase 0: 固化当前可跑 baseline

- [ ] 保存当前 occurrence gate 版本结果
- [ ] 记录 task density、helplessness_delta、app context 分布
- [ ] 确保所有关键中间变量进入 summary

### Phase 1: Day 1-3 Replay Calibration

- [ ] 为选出的 device_id 读取 Day 1-3 真实 hourly app entry bundle
- [ ] 将 Day 1-3 bundle 作为 forced exposure 输入 agent
- [ ] 将 bundle 中所有 context counts 写入 habit memory
- [ ] 从 bundle 中选择 primary_context 进入 gate
- [ ] 在 forced exposure 后运行 task occurrence gate
- [ ] gate fail 时记录 context-only app use
- [ ] gate pass 时按 baseline 正常流程运行 strategy / outcome / helplessness update
- [ ] 每天结束运行 daily reflection
- [ ] 生成 per-device habit memory
- [ ] 生成 per-device hourly app context summary
- [ ] 生成 initial digital confidence / friction sensitivity
- [ ] 保存 Day 4 开始时的 memory / state snapshot
- [ ] 检查 Day 1-3 replay 后 helplessness 是否异常飙升

### Phase 2: Memory-Driven Day 4-7 App Entry

- [ ] Day 4-7 不直接读取 validation prior
- [ ] Day 4-7 app entry 不再 forced by TalkingData
- [ ] 每小时根据 Day 1-3 memory / needs / TPB 生成 hourly app entry bundle
- [ ] 决定 active_or_not
- [ ] 决定 active_event_app_exposures
- [ ] 决定 app_context_counts
- [ ] 决定 primary_context
- [ ] 输出 app entry decision audit
- [ ] 与真实 Day 4-7 做 held-out validation

### Phase 3: Helplessness Feedback

- [ ] 将 helplessness / controllability / frustration 接入 app entry decision
- [ ] 检查 feedback 是否只影响 t+1 及以后
- [ ] 进行 no-feedback 消融

### Phase 4: Friction Worlds Counterfactual

- [ ] 固定同一批 agent 与 seed
- [ ] 跑 baseline / high friction low assist / high friction high assist / low friction high assist
- [ ] 输出 paired diffs
- [ ] 解释 friction effect

### Phase 5: Paper/Report 写法

- [ ] 明确 app entry 是 observable validation layer
- [ ] 明确 helplessness 是 latent mechanism
- [ ] 明确 TalkingData 不能验证 helplessness，只验证 baseline behavior
- [ ] 把结论写成 counterfactual simulation，而不是真实心理状态预测

## 论文表述建议

更稳的表述：

```text
We study learned-helplessness-like dynamics under digital friction.
Because real-world data only observes app entry, we use TalkingData to ground
and validate the baseline digital behavior of agents. After validating the
normal-world behavior against held-out app entry records, we introduce
counterfactual friction worlds to analyze changes in helplessness, avoidance,
help-seeking, and task persistence.
```

不要写成：

```text
We accurately predict older adults' learned helplessness from TalkingData.
```

## 当前最重要的判断

- App entry 不是主研究问题，但它是我们唯一能用真实数据校验的行为层。
- App entry 的运行单位应是小时级 bundle，而不是单个 app context。
- Helplessness 是主机制，但不能声称被 TalkingData 直接验证。
- Occurrence gate 必须保留，否则 baseline 中 DigitalTask 会过密。
- Helplessness 必须反馈到 app entry，否则 learned helplessness 链条不完整。
- Baseline world 要先像真实老人，friction world 的差异才有解释价值。
