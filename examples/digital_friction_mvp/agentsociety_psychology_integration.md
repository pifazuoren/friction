# How to Translate AgentSociety Psychology Designs into `digital_friction_mvp/proto`

## 1. 目标

把 AgentSociety 原生的心理状态机制，以及其他 examples 中“心理变化”的设计方式，吸收进我们当前的 `proto`，但不破坏现在这条主线：

`任务分配 -> 策略选择 -> 结果生成 -> helplessness 更新 -> 记录`

这意味着：

- 不恢复旧 `needs -> plan -> step_execution -> cognition` 主链
- 不让 LLM 直接决定 success / failure
- 不让自由文本反思主导策略
- 继续以 `helplessness + structured memory` 为核心

我们真正要借用的是：

1. **可观察的心理状态层**
2. **日级别反思层**
3. **量表式验证层**
4. **干预注入模式**

而不是照搬整个 CityAgent 认知大系统。

---

## 2. 仓库里现有机制，各自可以借什么

## 2.1 `SocietyAgent` / `CognitionBlock`

原生 AgentSociety 有：

- `emotion`
- `thought`
- `emotion_types`
- `attitude`

这些状态主要靠 LLM 更新。

对我们最值得借用的不是“让 LLM 自由发挥整套 cognition”，而是这两个模式：

- **incident-level emotional reaction**
- **cross-day summary / reflection**

翻译到 `proto` 里，最合适的改写是：

- 增加一个**数字任务情绪层**
- 增加一个**日级别简短反思层**

但都要保持结构化、受限、可审计。

---

## 2.2 `NeedsBlock`

`NeedsBlock` 不是在做复杂人格建模，而是在做：

- 某件事情发生后
- 某些 satisfaction 维度被拉高或拉低

这个模式非常值得借。

我们不需要复制：

- `hunger_satisfaction`
- `energy_satisfaction`

但可以翻译出数字任务版本的 satisfaction：

- `digital_autonomy_satisfaction`
- `digital_safety_satisfaction`
- `digital_support_satisfaction`

它们可以作为 `helplessness` 之外的中间心理状态。

---

## 2.3 `EconomyBlock`

`EconomyBlock` 的价值不在于 depression 这个变量本身，而在于它展示了一个重要模式：

- 用**量表式、周期性、结构化**的方法来测心理状态
- 而不是完全依赖 narrative

对我们来说，可直接翻译成：

- 周期性 `proto mini survey`
- 测量 technology anxiety / self-efficacy / avoidance intention / perceived support

这个层最适合拿来做：

- 验证
- 导出
- 对照

而不是直接拿来决定 outcome。

---

## 2.4 `mobility_block`

`mobility_block` 的思路是：

- 心理状态不只是被记录
- 它还会影响后续行为参数

这条思路值得借，但不需要借 mobility 本身。

因为我们这个实验不以地图和移动为核心。

对 `proto` 来说，最合理的翻译不是：

- 用情绪去改 travel radius

而是：

- 用情绪去轻量修正 re-engagement tendency
- 用情绪去影响下一次是否更愿意再试

---

## 2.5 `polarization`

`polarization` 的实验做法很简单：

- 记录前测
- 跑一段时间
- 记录后测
- 比较 attitude 变化

这个设计很适合我们借。

翻译到 `proto` 就是：

- 阶段前记录 `helplessness / self-efficacy / tech-anxiety proxy`
- 阶段后再记录一次
- 做 world 对比、stage 对比

也就是说：

`polarization` 借给我们的不是“attitude 变量”，而是**前后测比较框架**。

---

## 2.6 `inflammatory_message/emotional.py`

这个 example 的核心不是情绪公式，而是：

- 先注入一类信息暴露
- 再观察后续心理变化

这对我们非常有用。

在 `proto` 里可以翻译成两种干预：

- `supportive guidance message`
- `friction / scam / warning message`

它们不需要进入聊天系统，也不需要恢复复杂社交链。

它们可以作为：

- stage 开始时的标准化 exposure
- 对 `perceived_uncontrollability`
- 对 `digital_emotion`
- 对 `help confidence`

产生有限影响。

---

## 2.7 `prospect_theory`

这里值得借的是：

- survey 作为结果测量，而不是机制本身

所以它对我们的启发是：

- 可以补一个非常短的数字困境 survey
- 用来做实验输出和外部解释

而不是拿 survey 直接驱动 agent 决策。

---

## 3. 最值得改写进 `proto` 的 4 层

## 3.1 第一层：数字任务情绪层

这是从 `emotion_update()` 改写来的。

### 建议新增状态

- `digital_emotion_state: dict`

结构建议：

```json
{
  "anxiety": 4.0,
  "frustration": 3.0,
  "relief": 2.0,
  "confidence": 5.0,
  "last_updated_day": 0
}
```

### 第一阶段更新方式

先不用自由 LLM，先用规则更新：

- `failure_even_with_help`
  - `anxiety +2`
  - `frustration +2`
  - `confidence -2`
- `failure_after_attempt`
  - `anxiety +1.5`
  - `frustration +1.5`
  - `confidence -1.5`
- `avoid_without_attempt`
  - `anxiety +0.5`
  - `confidence -0.5`
- `success_self`
  - `relief +2`
  - `confidence +2`
  - `anxiety -1`
- `success_with_help`
  - `relief +1.5`
  - `confidence +1`
  - `anxiety -0.5`

之后做简单裁剪和衰减。

### 这层怎么进入决策

第一阶段建议只轻量进入：

- `emotion_pressure = 0.4 * anxiety + 0.4 * frustration - 0.5 * confidence`

然后只把它加到 `effective_helplessness` 上的一小部分：

- `effective_helplessness += clamp(emotion_pressure, -5, +8)`

这样可以借到 AgentSociety 的“情绪会影响行为”思路，但不会把主链打乱。

---

## 3.2 第二层：日级别简短反思层

这是从 `thought_update()` 改写来的。

### 建议新增状态

- `proto_daily_reflection: dict`

结构建议：

```json
{
  "day": 2,
  "dominant_pattern": "repeated_verification_failure",
  "reflection_text": "验证码老失败，让我更没把握",
  "confidence_tag": "medium"
}
```

### 第一阶段怎么做

第一阶段甚至可以先不用 LLM。

直接根据最近 episode buffer 规则生成：

- 最近 3 次同类任务失败较多
- 最近求助失败偏多
- 最近自主成功出现

生成一句短反思。

### 第二阶段怎么升级

如果后面要用 LLM，也只让它做：

- 结构化总结
- 输出受限 JSON
- 最多生成一句短 reflection

这层的主要用途是：

- 提高可解释性
- 给老师/论文展示“agent 最近在经历什么”

而不是主导 outcome。

---

## 3.3 第三层：数字版 satisfaction 层

这是从 `NeedsBlock` 改写来的。

### 建议新增状态

- `digital_autonomy_satisfaction`
- `digital_safety_satisfaction`
- `digital_support_satisfaction`

范围建议都用 `0~1`。

### 各自含义

- `digital_autonomy_satisfaction`
  - 我是否感觉自己能独立完成数字任务
- `digital_safety_satisfaction`
  - 我是否感觉数字环境可控、可信、不会轻易出错或被骗
- `digital_support_satisfaction`
  - 我是否感觉需要时能获得有效帮助

### 更新思路

- `success_self`
  - autonomy 明显升
- `success_with_help`
  - support 升，autonomy 小幅升
- `failure_even_with_help`
  - safety 降，support 也可能降
- `payment_risk_popup` 失败
  - safety 降得更明显
- `seek_help_then_attempt` 且成功
  - support satisfaction 升

### 这层怎么进入决策

第一阶段不要直接改 outcome。

只建议：

- autonomy 低 -> 增强 avoid / help
- support 高 -> 增强 help
- safety 低 -> 降低 attempt_self

也就是说，这层本质上是对你现在 memory 的一个更“心理过程化”的补充。

---

## 3.4 第四层：周期性 mini survey 层

这是从 `EconomyBlock` 和 `prospect_theory` survey 改写来的。

### 目标

不是用来驱动 agent 每一步决策。

而是用来：

- 做内部验证
- 做阶段输出
- 做 world 对比

### 建议题项

每个 stage 或每天末尾做一次 4 题或 6 题短问卷：

1. 我觉得自己能独立完成常见数字任务
2. 使用数字服务让我感到紧张
3. 遇到问题时我觉得能获得有效帮助
4. 遇到数字任务时我更想回避

都用 `1~7` 或 `0~10`。

### 使用方式

- 可以由规则从状态直接映射
- 也可以由 LLM 在结构化上下文下作答

更建议先做：

- rule-derived survey proxy

这样最稳。

### 这层的意义

它会让你的实验输出更像：

- “机制变量 + 可解释的测量变量”

而不只是内部状态分数。

---

## 4. 最推荐的改写顺序

## Phase 1：现在最值得做

### 4.1 加 `digital_emotion_state`

原因：

- 它和当前 `helplessness` 很互补
- 能借用 AgentSociety 最成熟的“incident -> emotion”模式
- 但又不需要恢复 CityAgent 全链路

### 4.2 加 `proto_daily_reflection`

原因：

- 这是最便宜的可解释性增强
- 对汇报、周报、论文都非常有帮助

### 4.3 加 `proto mini survey`

原因：

- 这是把 `EconomyBlock` 的量表化优势吸收过来的最好方式
- 能让结果更像“心理实验输出”而不只是 simulation log

---

## Phase 2：中等优先级

### 4.4 加 `digital_*_satisfaction`

原因：

- 能把 `NeedsBlock` 的“事情会改变满足感状态”模式翻译过来
- 让心理过程更丰富

### 4.5 加 message/exposure 干预

原因：

- 能借用 `inflammatory_message` 的“先暴露，再演化”设计
- 非常适合做老师会喜欢的额外实验组

例如：

- `high_friction_high_assist + supportive_message`
- `high_friction_low_assist + scam_warning_exposure`

---

## Phase 3：后面再考虑

### 4.6 让更多心理状态影响 outcome

这一步要慎重。

因为一旦：

- emotion
- satisfaction
- reflection

都开始影响 outcome，你的模型自由度会迅速变大。

所以更建议在 Phase 1、2 跑稳之后，再决定是否让：

- `confidence`
- `digital_autonomy_satisfaction`

进入 outcome probability。

---

## 5. 对当前 `proto` 的最小侵入实现路径

## 5.1 文件层面建议

### `proto/models.py`

建议新增：

- `DigitalEmotionState`
- `ProtoReflection`
- `ProtoMiniSurveyResult`

### `proto/experience_memory.py`

建议扩展为统一入口，额外处理：

- `build_initial_digital_emotion_state()`
- `update_digital_emotion_state()`
- `build_daily_reflection()`
- `build_mini_survey_proxy()`

### `proto/agent.py`

建议在现有流程中插入：

1. outcome 后更新 `digital_emotion_state`
2. 如果跨天，生成一次 `proto_daily_reflection`
3. stage 结束或日末生成 `proto mini survey`

### `main.py`

初始化新状态：

- `digital_emotion_state`
- `proto_daily_reflection`
- `proto_mini_survey_history`

### `config_runtime.py`

建议新增 feature flags：

- `PROTO_DIGITAL_EMOTION_ENABLED=true`
- `PROTO_DAILY_REFLECTION_MODE=off|rule|llm`
- `PROTO_MINI_SURVEY_ENABLED=true`
- `PROTO_EXPOSURE_INTERVENTION_MODE=off|supportive|risk`

### `analysis_parallel_worlds.py`

建议新增导出但不改六个核心指标主口径：

- `avg_stage_anxiety`
- `avg_stage_confidence`
- `mini_survey_self_efficacy`
- `mini_survey_avoidance`

---

## 6. 什么不要做

为了不把实验又做回旧 `frictionMVP`，下面这些不要做：

### 6.1 不要恢复完整 CityAgent 主链

不要改成：

- `needs -> plan -> step_execution -> cognition`

我们的 `proto` 现在最大的优点就是主链短、干净、可审计。

### 6.2 不要让自由文本 thought 直接决定 success/failure

`thought` 最适合做：

- audit
- explanation
- summary

不适合直接做 outcome engine。

### 6.3 不要一次加太多心理变量进 outcome

建议保持：

- 第一阶段只让新增状态影响 strategy
- 不改 success/failure 公式

这样最好控制解释性。

---

## 7. 最推荐的总体路线

如果只用一句话总结：

> 我们不把 AgentSociety 的原生心理机制整套搬进 `proto`，而是只吸收其中最有价值的四种设计模式：事件级情绪更新、日级简短反思、量表式周期测量、暴露式干预注入，并把它们都改写成受限、结构化、可审计的 `proto` 扩展层。

如果按优先级排序：

1. `digital_emotion_state`
2. `proto_daily_reflection`
3. `proto mini survey`
4. `digital_*_satisfaction`
5. `message / exposure intervention`

---

## 8. 这对论文定位意味着什么

这样改完以后，你的实验定位会更清楚：

- 核心仍然是 **theory-informed, structured simulation**
- 但不再只是一个单分数规则系统
- 而是：
  - 有主机制变量：`helplessness`
  - 有经验记忆层：task/help/recent episodes
  - 有情绪层：`digital_emotion_state`
  - 有解释层：`daily_reflection`
  - 有测量层：`mini survey`

这会比现在更接近一个：

**可解释的轻量心理过程模型**

而不是单纯规则引擎。
