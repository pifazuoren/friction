# Task Appraisal Prompt Refactor Plan

**目标**

- 把 `examples/digital_friction_mvp/proto/llm_psychology.py` 里的 `task appraisal` prompt，从“会自由打分的描述性 prompt”，改成“theory-informed、memory-grounded、strict-output 的中间测量模块”。
- 第一轮只验证 prompt 语义能不能把 `felt_control`、`perceived_task_risk`、`task_value`、`expected_help_effectiveness` 这几层真正拉开，不动下游公式和日志 schema。

**为什么这轮先只改 prompt**

- 当前最大的风险不是“代码里没有 appraisal”，而是 appraisal 这层虽然接上了，但数值可能长期中庸、重复、互相混。
- 如果这一轮同时改 prompt、cache 粒度、memory 公式、helplessness update 参数，就很难判断最后到底是哪一层起作用。
- 所以这轮采用单因素思路：先稳住接口，再重写语义，再做小样本验证。

**参考来源**

- `agentsocietyprompt5.md`
- `AgentSociety_Instructions.md`
- `llm融合.md`
- `examples/digital_friction_mvp/proto/llm_psychology.py`

---

## 1. 这轮要借的 prompt 设计原则

### 1.1 来自 4 篇论文总结的共性

1. `Profile-conditioned prompting`
   - prompt 需要显式注入 profile / status / context，而不是只给任务文本。
2. `Structured output`
   - 输出必须严格结构化，最好是 JSON-only。
3. `Memory-grounded prompting`
   - prompt 不只看当前任务，还要看过去经验和近期经历。
4. `Theory-informed prompting`
   - prompt 里的变量不是随便命名，而是有理论构念边界。
5. `Workflow-level modularity`
   - 一个 prompt 只做一个认知子任务，不要同时做 appraisal、strategy、outcome prediction。

### 1.2 对当前 task appraisal 的直接启发

- 这层应该像“认知测量模块”，不是“自由发挥的打分器”。
- prompt 里要明确标出输入块：
  - profile
  - current task
  - world/stage context
  - task-specific memory
  - recent experience
  - emotion state
- 输出层要继续保持硬约束，不扩展 schema。

---

## 2. 当前 prompt 的主要问题

### 2.1 构念边界不清

- `task_self_efficacy`、`felt_control`、`risk`、`value`、`help effectiveness` 容易混。
- 模型可能把“不会做”“怕被骗”“觉得没必要”都打成类似的分数组合。

### 2.2 没有量表锚点

- prompt 只说 `0-100`，没有说明不同区间各自代表什么状态。
- 模型容易长期停在中间值附近。

### 2.3 numeric example 过于中间

- 当前 example 是 `61 / 58 / 47 / 54 / 63` 这一类中间值。
- 容易形成“围绕中间打分”的锚定。

### 2.4 中间层虽然存在，但没有真正活起来

- 表面上已经有：
  - `felt_control`
  - `perceived_task_risk`
  - `task_value`
  - `expected_help_effectiveness`
- 但如果它们总在 `45-55` 附近晃，或者不同情境下反复复用同类模板，下游 update 虽然结构完整，实际却没有得到有效的中间变量驱动。

---

## 3. 这轮明确不改什么

1. 不改 `examples/digital_friction_mvp/proto/models.py` 里的 `TaskAppraisalResult` schema。
2. 不改 `examples/digital_friction_mvp/proto/state_update.py` 的 helplessness update 公式。
3. 不改 `examples/digital_friction_mvp/proto/experience_memory.py` 的 memory feature 计算。
4. 不改 paired analysis 和 summary 输出逻辑。
5. 不改 cache 的粗分桶策略本身。
6. 不新增 `primary_barrier` 等新输出字段。

---

## 4. 这轮具体要改什么

### 4.1 重写 system prompt

把 system prompt 改成 4 段：

1. 角色边界
   - 你不是策略选择器
   - 你不是结果预测器
   - 你只负责当前 task appraisal

2. 构念定义
   - `perceived_task_difficulty`
   - `perceived_task_risk`
   - `felt_control`
   - `expected_help_effectiveness`
   - `task_value`

3. 构念边界排除
   - “不会做”不等于“高风险”
   - “高风险”不等于“低价值”
   - “低价值”不等于“低控制感”
   - `task_self_efficacy` 是背景能力感，`felt_control` 是当前局面可控感

4. 反中庸约束
   - 只有证据模糊时才允许 `45-55`
   - 情境差异明显时必须拉开分值

### 4.2 重写 user prompt 的输入组织方式

参考 theory-informed workflow 的 prompt 风格，把输入组织成显式信息块：

- `[Agent Profile]`
- `[Current Task]`
- `[World / Stage Context]`
- `[Current Status]`
- `[Task-Specific Memory]`
- `[Recent Experience]`
- `[Digital Emotion State]`

原则：

- 不只是把一整段 JSON 扔给模型
- 而是把“哪部分信息回答哪个问题”写清楚

### 4.3 给 5 个维度补量表锚点

每个维度都写 5 档定义：

- `0-20`
- `21-40`
- `41-60`
- `61-80`
- `81-100`

重点写清：

- 低分到底是什么意思
- 中间分在什么情况下才合理
- 高分需要什么证据

### 4.4 把“先分原因，再打分”写进 prompt 内部流程

虽然第一轮不新增 schema，但要求模型内部先判断主因更接近：

- `skill_deficit`
- `situational_uncontrollability`
- `risk_concern`
- `low_value`
- `mixed`

然后再打 5 个分。

目的是减少：

- “不会做”和“高风险”混淆
- “低价值”和“低控制”混淆
- “怕被骗”和“做不到”混淆

### 4.5 删除当前中间 numeric example

- 去掉 `61 / 58 / 47 / 54 / 63` 这种中间型示例。
- 第一轮改成 schema template only，不给具体数值。
- 如果后续一定要恢复示例，应换成对比例子，而不是单个中间例子。

### 4.6 重写 calibration notes

从零散提醒改成构念判别规则：

1. `difficulty` 看步骤复杂度和理解成本，不等于风险。
2. `risk` 看潜在损失和坏后果，不等于不会做。
3. `felt_control` 看努力是否仍能改变结果。
4. `task_value` 看必要性和收益，不要因为任务难就自动低。
5. `expected_help_effectiveness` 看支持条件和过去 help 经验。
6. 情境明显不同，就必须拉开分值。

### 4.7 增加 prompt version 并写入 task appraisal cache key

新增常量，例如：

- `TASK_APPRAISAL_PROMPT_VERSION = "v2_theory_grounded_rubric_20260406"`

并把它加进 `task appraisal cache key`。

目的：

- 避免新 prompt 复用旧缓存
- 保证这轮验证更干净
- 不改变下游接口

---

## 5. 文件级修改计划

### Task 1: 重写 task appraisal prompt

**Files**

- Modify: `examples/digital_friction_mvp/proto/llm_psychology.py`

**要做的事**

- 改 `resolve_task_appraisal()` 里的 `system_prompt`
- 改 `user_payload` 的组织和说明文本
- 去掉当前 numeric example
- 增强构念定义、边界规则、量表锚点

### Task 2: 隔离 prompt 缓存版本

**Files**

- Modify: `examples/digital_friction_mvp/proto/llm_psychology.py`

**要做的事**

- 新增 `TASK_APPRAISAL_PROMPT_VERSION`
- 写进 `_build_task_appraisal_cache_key()`

### Task 3: 小样本验证

**Files**

- Read/Check:
  - `examples/digital_friction_mvp/proto/agent.py`
  - `examples/digital_friction_mvp/analysis/*.csv`
  - `examples/digital_friction_mvp/analysis/*.json`

**要做的事**

- 先做人造 case sanity check
- 再跑 smoke
- 再看 appraisal 字段分布是否活起来

---

## 6. 这轮验证怎么做

### 6.1 Prompt 级 sanity check

至少手造 6 类 case：

1. 不会做，但并不觉得危险
2. 会做，但怕被骗
3. 会做，也不危险，但觉得没必要
4. 平时会做，但这次界面太乱导致低控制
5. 高支持且过去 help 有效
6. 高支持但过去 help 更像代办

看模型能否输出差异化结构，而不是都中间化。

### 6.2 小样本 smoke

建议先跑：

- `1 seed x 4 worlds x 10 agents x 1 day`

重点检查：

- `felt_control` 是否还大量卡在 `45-55`
- `risk` 和 `value` 是否还高度联动
- `expected_help_effectiveness` 是否在高 assist 条件下更合理
- `reason` 是否能说清主要阻碍

### 6.3 正式配置验证

再跑正式 paired 配置，检查：

- appraisal 的动态范围是否拉开
- 不同 world 下 appraisal 分布是否更可分
- 同一类“不做”是否出现不同分数组合
- 下游 helplessness update 是否更像被中间层驱动

---

## 7. 这轮验收标准

1. `felt_control` 不再像常数层。
2. `risk`、`value`、`control` 的分布更分离。
3. `expected_help_effectiveness` 在高 assist 条件下更敏感。
4. 中间分使用比例下降。
5. prompt 改版后没有因为旧缓存被掩盖。
6. 不破坏下游 schema、日志和 update 链路。

---

## 8. 下一轮再做什么

如果这一轮有效，下一轮优先级是：

1. 再看 task appraisal cache 粒度是否要细化
2. 再看是否要显式输出 `primary_barrier`
3. 再看是否要增强 appraisal -> memory 的反馈
4. 最后才去调 helplessness update 参数强度

---

## 9. 一句话总结

这轮不是为了“让模型更聪明”，而是为了：

- 把 task appraisal 改成一个真正可解释、可区分、可验证的中间测量层
- 先救活 `felt_control` / `risk` / `value` / `help effectiveness`
- 再决定后面要不要调 cache、memory、update 公式
