# Rule Core + Bounded LLM Agent 融合方案

## 1. 文档定位

这份文档只做方案分析，不修改现有代码。

目标是把当前 `digital_friction_mvp` 从：

- `rule core + 少量 LLM 心理层`

进一步推进成：

- `rule core + bounded LLM appraisal/deliberation/planning + survey/interview`

也就是说：

- 继续保留 rule 负责客观机制
- 让 LLM 更多负责主观理解、有限决策、反思和解释输出

这个方向更接近 AgentSociety 团队论文和原生 agent 的思路，但仍然比“全 LLM agent”更可控。

---

## 2. 总原则

### 2.1 不改的部分

以下部分继续由 rule 主导：

- 任务分配主框架
- world / stage 条件本身
- success / failure
- helplessness 主更新公式
- 核心 summary 指标口径

### 2.2 LLM 主要负责的部分

LLM 主要前移到以下几层：

- 任务前主观评估
- 有限策略权衡
- 微型行动计划
- 干预解释
- survey / interview / reflection 解释输出

### 2.3 AgentSociety 风格约束

所有新增 LLM 层都应遵守：

- `JSON-only`
- 有限字段
- 有限选项
- 返回 `judge_confidence`
- 短理由
- 有 fallback
- 有 cache
- 有 payload 审计

### 2.4 一句话原则

不是让 LLM 决定“客观世界发生了什么”，  
而是让 LLM 决定：

- agent 怎么看
- agent 怎么想
- agent 更偏向怎么选
- agent 如何解释自己的经历

---

## 3. 当前系统和目标系统的区别

### 3.1 当前系统

当前 `proto` 更像：

- task assignment
- memory feature extraction
- rule strategy selection
- rule outcome
- rule helplessness update
- bounded LLM 用于少量心理校准和解释

### 3.2 目标系统

目标系统更像：

- task assignment
- LLM 任务主观评估
- rule + LLM 共同形成策略偏向
- LLM 生成微型行动计划
- rule outcome
- rule helplessness update
- LLM 解释干预和阶段经历
- survey / interview / reflection 输出

### 3.3 最重要的变化

真正的变化不是让 LLM 决定成功失败，  
而是把 LLM 从“结果后解释”前移到“决策前参与”。

---

## 4. Phase 1：Task Appraisal Layer

### 4.1 这一步是干什么的

让 agent 在做任务之前，先对当前任务形成一个主观判断：

- 难不难
- 危不危险
- 值不值得
- 我能不能控制
- 求助有没有用

### 4.2 通俗解释

现在的系统更像：

- 任务来了
- 直接算 feature
- 直接选策略

加上这一步以后，会变成：

- 任务来了
- agent 先想一遍“这个任务在我眼里是什么感觉”
- 再去选策略

这一步会让 agent 更像一个“先感受、再行动”的人。

### 4.3 接线位置草案

建议接在：

- `assign_task_if_missing()` 之后
- `extract_memory_features()` 之前

对应当前代码路径：

- `examples/digital_friction_mvp/proto/agent.py`

理想顺序：

1. 取得 `task`
2. 调用 `resolve_task_appraisal(...)`
3. 将 appraisal 写入 status / payload
4. 再进入 `extract_memory_features(...)`

### 4.4 新增状态草案

建议新增：

- `proto_task_appraisal`
- `proto_task_appraisal_history`

建议字段：

- `perceived_task_difficulty`
- `perceived_task_risk`
- `felt_control`
- `expected_help_effectiveness`
- `perceived_support_availability`
- `task_value`
- `judge_confidence`
- `reason`
- `source`
- `status`

### 4.5 Prompt 草案

```text
System:
You are a strict JSON-only task appraisal module for a digital-friction experiment.
You do NOT decide success or failure.
You do NOT choose the final strategy.
You only estimate how the agent subjectively appraises the current task.

User:
Given:
- agent profile summary
- current task
- current world/stage context
- helplessness score
- task-specific memory snapshot
- help-effect memory snapshot
- recent negative experience summary
- current digital emotion state

Please estimate the agent's subjective appraisal of this task.

Return one JSON object only with:
- perceived_task_difficulty
- perceived_task_risk
- felt_control
- expected_help_effectiveness
- perceived_support_availability
- task_value
- judge_confidence
- reason

Rules:
- all appraisal scores are 0-100
- judge_confidence is 0-1
- stay close to the provided evidence
- do not output any extra text
```

### 4.6 JSON Schema 草案

```json
{
  "perceived_task_difficulty": 72,
  "perceived_task_risk": 81,
  "felt_control": 28,
  "expected_help_effectiveness": 54,
  "perceived_support_availability": 60,
  "task_value": 76,
  "judge_confidence": 0.82,
  "reason": "Low prior success and high fraud concern make this task feel risky."
}
```

### 4.7 这一步会带来什么

- 策略层前面多了一层“主观任务理解”
- 不同 profile 对同一任务会有更明显的心理差异
- 更接近文献里的：
  - self-efficacy
  - risk perception
  - usefulness
  - support expectation

---

## 5. Phase 2：Bounded Strategy Deliberation Layer

### 5.1 这一步是干什么的

让 LLM 在固定三种策略里做主观权衡：

- `attempt_self`
- `seek_help_then_attempt`
- `avoid`

### 5.2 通俗解释

这一步不是让 LLM 自由决定“下一步干什么”，  
而是让它在已经定义好的三种策略里说：

- 我现在更偏向哪一个
- 偏向程度有多强

这一步是整个方案里最能让系统变得“更像 LLM agent”的部分。

### 5.3 接线位置草案

建议接在：

- `extract_memory_features()` 之后
- `choose_attempt_strategy()` 之前

对应当前代码路径：

- `examples/digital_friction_mvp/proto/agent.py`

理想顺序：

1. 先得到 `memory_features`
2. 再调用 `resolve_strategy_deliberation(...)`
3. 生成三策略分数
4. 用 blend 方式和 rule weights 融合
5. 最后才进入 `choose_attempt_strategy()`

### 5.4 新增状态草案

建议新增：

- `proto_strategy_deliberation`
- `proto_strategy_deliberation_history`

建议字段：

- `attempt_self_score`
- `seek_help_score`
- `avoid_score`
- `dominant_strategy`
- `judge_confidence`
- `reason`
- `source`
- `status`

### 5.5 Prompt 草案

```text
System:
You are a strict JSON-only bounded strategy deliberation module.
You must reason only over the following three allowed strategies:
- attempt_self
- seek_help_then_attempt
- avoid

You do NOT decide success or failure.
You do NOT change the task.
You do NOT invent new strategies.

User:
Given:
- current task
- task appraisal
- effective helplessness
- task-specific self-efficacy
- help success memory
- recent negative experience
- current digital emotion state
- latest daily reflection if available

Please score the agent's current preference for the three allowed strategies.

Return one JSON object only with:
- attempt_self_score
- seek_help_score
- avoid_score
- dominant_strategy
- judge_confidence
- reason

Rules:
- all scores must be 0-1
- dominant_strategy must be one of the three allowed strategies
- do not output any extra text
```

### 5.6 JSON Schema 草案

```json
{
  "attempt_self_score": 0.18,
  "seek_help_score": 0.57,
  "avoid_score": 0.25,
  "dominant_strategy": "seek_help_then_attempt",
  "judge_confidence": 0.79,
  "reason": "The task feels difficult, but support still seems usable."
}
```

### 5.7 这一步会带来什么

- agent 不再只是被 rule 推着走
- 策略选择更像“有限 deliberation”
- 但仍然保留可控性，因为：
  - 只有 3 个固定选项
  - LLM 不决定 outcome

---

## 6. Phase 3：Micro Plan / Action Rationale Layer

### 6.1 这一步是干什么的

在策略已经选定之后，让 LLM 生成一个超短的：

- 行动计划
- 或行动理由

### 6.2 通俗解释

现在的系统里，agent 选了策略以后，马上进入 outcome。

加上这一步以后，agent 会先形成一个最小计划，例如：

- 自己试：先看验证码，再检查页面
- 先求助：先问家人这一步是不是安全
- 回避：今天先不碰，改线下

这一步不会直接改结果，但会让整个过程更像 AgentSociety 里的“有 plan 的 agent”。

### 6.3 接线位置草案

建议接在：

- `choose_attempt_strategy()` 之后
- `resolve_attempt_outcome()` 之前

对应当前代码路径：

- `examples/digital_friction_mvp/proto/agent.py`

### 6.4 新增状态草案

建议新增：

- `proto_micro_plan`
- `proto_micro_plan_history`

建议字段：

- `plan_type`
- `first_step`
- `second_step`
- `expected_sticking_point`
- `help_target`
- `help_request`
- `after_help_first_step`
- `avoid_reason`
- `fallback_option`
- `judge_confidence`
- `reason`
- `source`
- `status`

注：

- 不同策略只填其中一部分字段
- 不必要求所有字段都存在

### 6.5 Prompt 草案

```text
System:
You are a strict JSON-only micro-plan generator for a bounded digital task experiment.
The strategy has already been chosen.
You must NOT change the chosen strategy.
You only generate a minimal action rationale or micro-plan.

User:
Given:
- current task
- chosen strategy
- task appraisal
- current emotion state
- relevant task/help memory

Generate a minimal micro-plan.

If chosen strategy is attempt_self:
return fields for first_step, second_step, expected_sticking_point

If chosen strategy is seek_help_then_attempt:
return fields for help_target, help_request, after_help_first_step

If chosen strategy is avoid:
return fields for avoid_reason, fallback_option

Also return:
- plan_type
- judge_confidence
- reason

Return one JSON object only.
```

### 6.6 JSON Schema 草案

`attempt_self` 版本：

```json
{
  "plan_type": "attempt_self",
  "first_step": "先识别页面上真正需要点的按钮",
  "second_step": "再按提示完成验证码",
  "expected_sticking_point": "验证码和小字提示",
  "judge_confidence": 0.76,
  "reason": "The agent still wants to try, but expects verification friction."
}
```

`seek_help_then_attempt` 版本：

```json
{
  "plan_type": "seek_help_then_attempt",
  "help_target": "家人",
  "help_request": "先帮我确认这一步是不是安全",
  "after_help_first_step": "按对方确认的步骤继续操作",
  "judge_confidence": 0.83,
  "reason": "The agent prefers reassurance before acting."
}
```

`avoid` 版本：

```json
{
  "plan_type": "avoid",
  "avoid_reason": "怕出错也怕被骗",
  "fallback_option": "改成线下办理或稍后再说",
  "judge_confidence": 0.80,
  "reason": "High perceived risk and low felt control favor avoidance."
}
```

### 6.7 这一步会带来什么

- 输出更像“有行动心理过程”
- 更适合做案例分析、访谈材料、论文图例
- 以后如果要做“卡点识别”或“帮助类型匹配”，这一层也能复用

---

## 7. Phase 4：Intervention Interpretation Layer

### 7.1 这一步是干什么的

让 agent 先主观理解外部干预，再让干预影响后续行为。

这里的干预包括：

- stage 变化
- assist 增强
- friction 增强
- supportive message
- warning message

### 7.2 通俗解释

现在很多环境变化更像：

- 变量变了
- rule 直接读这个变量

Phase 4 想做的是：

- 变量变了
- agent 先想：
  - 现在是不是更安全了
  - 现在是不是更值得试了
  - 这条提醒到底是在帮助我，还是在吓我

这会更像 AgentSociety 里的 `react_to_intervention()` 风格。

### 7.3 接线位置草案

建议接在两个地方：

- stage 切换时
- message / environment intervention 发生时

对应当前代码路径：

- `examples/digital_friction_mvp/main.py`
- `examples/digital_friction_mvp/proto/agent.py`

理想流程：

1. workflow 写入环境或消息干预
2. agent 在下一轮 `forward()` 中读取干预
3. 调用 `resolve_intervention_appraisal(...)`
4. 写入 `proto_intervention_appraisal`
5. 影响下一轮 task appraisal / strategy deliberation

### 7.4 新增状态草案

建议新增：

- `proto_intervention_appraisal`
- `proto_intervention_history`

建议字段：

- `felt_environment_safety`
- `perceived_help_availability`
- `support_signal_strength`
- `warning_salience`
- `motivation_shift`
- `judge_confidence`
- `reason`
- `source`
- `status`

### 7.5 Prompt 草案

```text
System:
You are a strict JSON-only intervention interpretation module for a digital-friction experiment.
You do NOT decide behavior directly.
You only estimate how the agent subjectively interprets the intervention.

User:
Given:
- intervention message or environment change
- current stage/world context
- current helplessness, trust, avoidance
- current task appraisal if available
- current digital emotion state
- recent experience summary

Estimate how this intervention is subjectively interpreted.

Return one JSON object only with:
- felt_environment_safety
- perceived_help_availability
- support_signal_strength
- warning_salience
- motivation_shift
- judge_confidence
- reason

Rules:
- all scores are 0-100
- motivation_shift is in -100 to 100
- no extra text
```

### 7.6 JSON Schema 草案

```json
{
  "felt_environment_safety": 63,
  "perceived_help_availability": 74,
  "support_signal_strength": 68,
  "warning_salience": 22,
  "motivation_shift": 18,
  "judge_confidence": 0.77,
  "reason": "The new guidance makes support feel more available and the task less threatening."
}
```

### 7.7 这一步会带来什么

- 干预不再只是外部参数
- 干预先进入 agent 的主观世界
- world / stage 差异更像“被体验过的实验条件”

---

## 8. Phase 5：Survey + Interview + Explainability Layer

### 8.1 这一步是干什么的

把实验输出做成更完整的：

- 行为数据
- survey 数据
- interview / reflection 数据

### 8.2 通俗解释

现在系统已经有 survey，  
但如果要更像 AgentSociety 团队在 `Piloting Social Experiments` 里的方法论，还要补一层：

- agent 在阶段末怎么解释自己这段经历
- agent 觉得最难的是什么
- agent 觉得帮助有没有用
- agent 下一阶段更想自己试、求助，还是回避

这一步不会改主机制，但会大幅提升论文和汇报质量。

### 8.3 接线位置草案

建议接在：

- `stage_settlement()` 之后
- stage-end survey 之后
- run end 时再做一次 final interview

对应当前代码路径：

- `examples/digital_friction_mvp/main.py`

### 8.4 新增状态草案

建议新增：

- `proto_stage_interview`
- `proto_stage_interview_history`
- `proto_final_interview`

建议字段：

- `main_difficulty_source`
- `support_comment`
- `future_intention`
- `short_quote`
- `judge_confidence`
- `source`
- `status`

### 8.5 Prompt 草案

```text
System:
You are a strict JSON-only stage-end interview summarizer for a digital-friction experiment.
You do NOT modify internal state.
You only summarize the agent's own explanation of the stage.

User:
Given:
- stage summary
- task appraisal summary
- strategy summary
- outcome summary
- survey summary
- latest daily reflections
- current emotion summary

Return one JSON object only with:
- main_difficulty_source
- support_comment
- future_intention
- short_quote
- judge_confidence

Rules:
- short_quote should be concise and natural
- future_intention must be one of: try_self, seek_help, avoid, mixed
- no extra text
```

### 8.6 JSON Schema 草案

```json
{
  "main_difficulty_source": "验证码和风险不确定性",
  "support_comment": "有人帮时会安心一些，但不总是够用",
  "future_intention": "seek_help",
  "short_quote": "如果有人先帮我确认安全，我会更敢继续。",
  "judge_confidence": 0.81
}
```

### 8.7 这一步会带来什么

- 输出更接近真正的社会实验材料
- 可以同时提供：
  - 行为层
  - 心理测量层
  - 解释层
- 非常适合论文方法、结果解释和汇报展示

---

## 9. 五个 Phase 串起来的人话版

### Phase 1

先想：

- 这个任务在我眼里有多难、多险、多值得做

### Phase 2

再想：

- 那我更想自己试、求助，还是躲开

### Phase 3

再想：

- 如果我真这么选，我准备怎么做

### Phase 4

如果环境或帮助变了，再想：

- 这件事对我意味着什么

### Phase 5

最后再说：

- 这一阶段我到底经历了什么
- 我以后会怎么想

---

## 10. 哪几个 Phase 最能让系统变成“更 LLM 主导”

如果只看最关键的部分，其实是前 3 个：

1. `Task Appraisal`
2. `Bounded Strategy Deliberation`
3. `Micro Plan / Action Rationale`

因为这三层直接发生在：

- outcome 之前
- helplessness update 之前
- 真正的行为选择之前

所以它们会明显改变系统气质：

- 从“rule 决策 + LLM 解释”
- 变成“LLM 先理解、再权衡、再形成行动意图，rule 只负责世界约束”

---

## 11. 推荐落地顺序

建议顺序：

1. Phase 1：Task Appraisal
2. Phase 2：Bounded Strategy Deliberation
3. Phase 3：Micro Plan / Action Rationale
4. Phase 5：Survey + Interview + Explainability
5. Phase 4：Intervention Interpretation

原因：

- 前 3 个最直接决定“更不像纯 rule，更像 LLM agent”
- Phase 5 最容易立刻提升论文输出质量
- Phase 4 价值大，但接线更复杂，适合稍后做

---

## 12. 最终一句话总结

如果希望实验真正变得“更像 AgentSociety 风格的 LLM agent”，  
最关键的不是让 LLM 直接决定 success/failure，  
而是让 LLM 接管：

- 任务怎么看
- 策略怎么想
- 行动怎么组织
- 干预怎么理解
- 经历怎么表达

而 rule 继续负责：

- 世界约束
- 成败生成
- helplessness 主机制

这就是最稳的：

- `Rule Core + Bounded LLM Deliberation + Structured Measurement`

