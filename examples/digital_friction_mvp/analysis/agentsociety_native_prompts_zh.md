# AgentSociety 原生 Prompt 中文注释版

> 原文完整版本见：`examples/digital_friction_mvp/analysis/agentsociety_native_prompts.md`
>
> 说明：本文件不改原文，仅做“人话解释”。

## 使用说明

- 你当前实验链路里主要会用到：`Dispatcher + PlanBlock + NeedsBlock + Mobility/Social/Other`。
- `EconomyBlock` 的 prompt 也列出，但你当前 `main.py` 配置默认未启用 `EconomyBlock`。

---

## 1) `DISPATCHER_PROMPT`
- 来源：`packages/agentsociety/agentsociety/agent/dispatcher.py:12`
- 作用：让 LLM 在多个 block（如 mobility/social/other）里选“这一步该交给谁处理”。
- 输入核心：`${context.current_intention}`（当前意图）。
- 输出预期：函数调用参数（`block_name` + `reason`）。

## 2) `GUIDANCE_SELECTION_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/plan_block.py:11`
- 作用：先从“指导选项”里挑一个较合适的目标方向（比如吃饭、休息、社交）。
- 输入核心：天气、地点、时间、画像、情绪、思考、候选选项。
- 输出预期：JSON（`selected_option` + `evaluation`）。

## 3) `DETAILED_PLAN_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/plan_block.py:52`
- 作用：把上一步目标拆成具体 steps。
- 关键约束：`type` 只能是 `mobility/social/economy/other` 四类。
- 输出预期：JSON 计划（`target` + `steps[{intention,type}]`）。

## 4) `INITIAL_NEEDS_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/needs_block.py:10`
- 作用：初始化需求满足度（饥饿/精力/安全/社交）。
- 输入核心：画像 + 当前时间。
- 输出预期：JSON（`current_satisfaction`，0~1）。

## 5) `EVALUATION_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/needs_block.py:44`
- 作用：根据执行结果回调需求满足度。
- 输入核心：目标、执行情况、当前 satisfaction。
- 输出预期：JSON（单一 need 或 `whatever` 时双字段）。

## 6) `REFLECTION_PROMPT`（Needs）
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/needs_block.py:78`
- 作用：收到外部干预后，重估需求状态；必要时建议中断当前动作。
- 输出预期：JSON（新 satisfaction，或 `do_something` + `description`）。

## 7) `ENVIRONMENT_REFLECTION_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/societyagent.py:25`
- 作用：让 agent 对“当前环境信息”做主观感受反思。
- 输入核心：职业、年龄、情绪、区域信息。

---

## 8) `PLACE_TYPE_SELECTION_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:24`
- 作用：先选一级地点类型（如 shopping/restaurant 等）。
- 输出预期：JSON（`place_type`）。

## 9) `PLACE_SECOND_TYPE_SELECTION_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:40`
- 作用：再选二级地点类型（更细分类）。
- 输出预期：JSON（`place_type`）。

## 10) `PLACE_ANALYSIS_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:57`
- 作用：在候选地点列表里选一个更合适的目的地类型。
- 输出预期：JSON（`place_type`）。

## 11) `RADIUS_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/mobility_block.py:74`
- 作用：根据情绪估计“最大出行半径”。
- 输出预期：JSON（`radius`，3000~200000 米）。

---

## 12) `TIME_ESTIMATE_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/utils.py:4`
- 作用：通用“动作耗时估计”模板（分钟）。
- 输出预期：JSON（`time`）。

## 13) `SLEEP_TIME_ESTIMATION_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/other_block.py:22`
- 作用：睡眠类动作专用耗时估计。
- 输出预期：JSON（`time`，分钟）。

## 14) `WORKTIME_ESTIMATE_PROMPT`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/economy_block.py:24`
- 作用：工作类动作专用耗时估计。
- 输出预期：JSON（`time`，分钟）。

---

## 15) Social 内联 Prompt：`FindPersonBlock.prompt`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/social_block.py:164`
- 作用：从社交网络里选目标对象，并决定线上/线下互动模式。
- 输出预期：JSON（`mode` + `target_id`）。

## 16) Social 内联 Prompt：`MessageBlock.default_message_template`
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/social_block.py:310`
- 作用：生成具体社交消息文本。
- 约束：100 字以内、第一人称、符合人格和背景。

---

## 17) Cognition 内联 Prompt：`update_attitude` 描述段
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:124`
- 作用：构建“我是怎样一个人 + 当前情绪 + 当前想法”的人格上下文。

## 18) Cognition 内联 Prompt：`thought_update` 描述段
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:206`
- 作用：同上，用于“日总结思考”任务。

## 19) Cognition 内联 Prompt：`thought_update` 问题段
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:226`
- 作用：要求模型总结当天想法并给出情绪词。
- 输出预期：JSON（必须含非空 `thought`）。

## 20) Cognition 内联 Prompt：`emotion_update` 描述段
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:348`
- 作用：给“情绪重估”任务提供画像和当前心理上下文。

## 21) Cognition 内联 Prompt：`emotion_update` 问题段
- 来源：`packages/agentsociety/agentsociety/cityagent/blocks/cognition_block.py:362`
- 作用：要求重新评估 6 维情绪强度（0~10）。
- 输出预期：JSON（sadness/joy/fear/disgust/anger/surprise + conclusion + word）。

---

## 你当前最该关注的 3 个 Prompt（和你实验最相关）

- `DETAILED_PLAN_PROMPT`：决定 `step_type` 只有 4 类的根因。
- `DISPATCHER_PROMPT`：决定当步走哪个 block。
- `scenario_matching.py` 里的 unified prompt（非 AgentSociety 原生，但与你当前场景判定最直接相关）。

