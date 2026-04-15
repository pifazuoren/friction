# 0325 Report: Current Hybrid `proto` Experiment

## 1. 一句话定位

当前 `digital_friction_mvp/proto` 不是纯 rule-based，也不是 pure LLM agent。

它现在是一个 **Rule Core + Bounded LLM Psychology** 的 hybrid：

- `rule core` 负责世界条件、任务分配、策略骨架、outcome、helplessness 主更新
- `LLM layers` 负责主观任务评估、有限策略权衡、事件级心理评估、survey、reflection、interview

最重要的边界是：

- LLM 不直接决定 success / failure
- LLM 不直接改 helplessness 主公式
- LLM 不绕过现有三策略结构

---

## 2. 当前实验的完整流程

### 2.1 World 层

每次运行会先由 `world_runner.py` 或 `main.py` 决定实验世界参数：

- `world_name`
- `seed`
- `stage_mode`
- `stage_days`
- `decision_interval_minutes`

如果是 `world_runner.py`，就会并行或顺序跑多个 worlds，例如：

- `baseline_low_friction`
- `high_friction_low_assist`
- `high_friction_high_assist`
- `low_friction_high_assist`

---

### 2.2 Workflow 层

每个 world 内部的 workflow 当前是：

1. `init_status`
2. 初始 `survey`
3. `sync_survey_feedback`
4. 进入各个 `stage`
5. 每个 stage 开始时写入对应环境条件
6. 在 stage 内按固定时间间隔循环执行 `STEP`
7. 每天/每轮写 step metrics
8. 每个 stage 结束后做 `stage_settlement`
9. 保存 stage context
10. stage-end `survey`
11. `sync_survey_feedback`
12. 如果开启 Phase 5，则做 stage interview
13. 所有 stage 结束后，如果开启 final interview，则再做一次 final interview

如果 `STAGE_MODE=full`，当前默认 stage plan 是：

- `steady`
- `shock`
- `recovery`

---

### 2.3 单次 agent 决策层

每次 workflow 进入一次 `STEP`，会触发 `DigitalHelplessnessAgent.forward()`。

当前单次数字任务决策链条是：

`读取状态 -> 跨天情绪衰减 -> daily reflection -> stage transition 检查 -> 分配任务 -> baseline memory features -> task appraisal -> 正式 memory features -> strategy deliberation -> choose strategy -> outcome -> uncontrollability calibration -> event appraisal -> helplessness update -> memory update -> logs/payload -> 清理或延后任务`

---

## 3. Rule 链和 LLM 链怎么并在一起

最清楚的理解方式，是把整个实验拆成两条并排的链。

### 3.1 Rule 链

rule 负责“客观结构”和“主结果”：

- world / stage 条件
- task assignment
- memory 的基础聚合
- 三策略骨架
- outcome 计算
- helplessness 主更新
- counters / logs / summary 主口径

可以把它写成：

`world/stage 条件 -> 分配任务 -> 提取 memory features -> 选策略 -> 算 outcome -> 更新 helplessness -> 记录结果`

---

### 3.2 LLM 链

LLM 负责“主观心理加工”和“解释输出”：

- survey
- task appraisal
- strategy deliberation
- event appraisal
- daily reflection
- stage interview
- final interview

它不是完全单独运行，而是插在 rule 链里面。

---

### 3.3 合并后的主链

当前更准确的主链是：

`world/stage 条件 -> 分配任务 -> task appraisal -> memory features -> strategy deliberation -> choose strategy -> outcome -> uncontrollability/event appraisal -> helplessness update -> memory/log -> survey/interview`

一句话概括：

- `rule` 决定“发生什么”
- `LLM` 决定“怎么看、怎么权衡、怎么解释”

---

## 4. LLM 现在主要作用在哪

很多时候会误以为“LLM 用得不多”，是因为它没有直接接管 outcome。

但实际上，LLM 已经深度进入了下面这些层：

### 4.1 Survey 层

LLM 负责帮助 agent 回答 survey，包括：

- helplessness
- withdrawal / avoidance
- self-efficacy
- support
- usefulness
- anxiety

这属于 **测量层**。

---

### 4.2 Phase 1: Task Appraisal

这是“怎么看当前任务”。

在正式选策略前，LLM 会先对任务做结构化主观评估：

- `perceived_task_difficulty`
- `perceived_task_risk`
- `felt_control`
- `expected_help_effectiveness`
- `task_value`

它的作用是：

- 把客观任务条件转成主观感受
- 再通过 `task_appraisal_shift` 进入 `effective_helplessness`

所以 Phase 1 是：

- `主观任务评估层`

---

### 4.3 Phase 2: Strategy Deliberation

这是“怎么在三种策略里权衡”。

当前三种策略仍然固定为：

- `attempt_self`
- `seek_help_then_attempt`
- `avoid`

LLM 在这里不发明新动作，而是：

- 对三种已有策略给一个有限分布
- 再与 rule weights 混合

所以 Phase 2 是：

- `bounded hybrid 决策层`

---

### 4.4 Event Appraisal / Digital Emotion

一次任务成功或失败后，LLM 会参与更新数字任务相关情绪：

- `anxiety`
- `frustration`
- `relief`
- `confidence`

其中更核心、也更接近论文主构念的是：

- `anxiety`
- `confidence`

这属于：

- `事件级心理评估层`

---

### 4.5 Daily Reflection

这是“每天的简短总结”。

它会根据前一天经历生成一个简短 reflection，帮助说明：

- 昨天主要卡在什么任务
- 帮助有没有用
- 最近更像成功、挣扎、回避还是混合波动

它更偏：

- `解释层`
- `审计层`

不是主 outcome 公式的一部分。

---

### 4.6 Phase 5: Interview / Explainability

这是“阶段末和实验末的解释输出层”。

它会在：

- 每个 stage 末
- 全部实验结束后

生成结构化访谈结果，例如：

- 当前阶段主要困难是什么
- 支持是 helpful / limited / ineffective / not_used
- 以后更想 `try_self / seek_help / avoid / mixed`
- 整体 trajectory 是 `improved / worsened / mixed / stable`

Phase 5 的作用是：

- 强化可解释性
- 生成适合论文和汇报的主观总结
- 更贴近 AgentSociety 原生 workflow 的 interview 范式

它不负责：

- 决定 success / failure
- 决定 helplessness 主更新

---

## 5. Phase 1 / 2 / 5 各自是什么

最简单的区分方式：

- `Phase 1`：看任务
- `Phase 2`：选策略
- `Phase 5`：做解释

稍微展开一点：

- `Phase 1 task appraisal`
  - 决定 agent 主观上觉得这个任务多难、多危险、多可控
- `Phase 2 strategy deliberation`
  - 决定 agent 如何在三种现有策略里做有限权衡
- `Phase 5 interview`
  - 解释 agent 在一个阶段或整个实验里“发生了什么、为什么会这样”

---

## 6. 为什么当前版本是 hybrid，而不是 pure rule 或 pure LLM

### 6.1 不是 pure rule

因为 agent 不再只是按几个固定阈值机械行动。

现在 LLM 已经参与：

- 主观任务评估
- 有界策略权衡
- 事件后的心理状态更新
- survey 回答
- reflection
- interview

所以它已经不只是“规则+日志”。

---

### 6.2 也不是 pure LLM

因为最关键的硬约束仍然由 rule 维持：

- world 条件是规则给的
- task assignment 是规则给的
- outcome 不是 LLM 自由生成的
- helplessness 主公式不是 LLM 改写的
- 最终策略空间仍被限制在三种已有策略里

所以它也不是“全交给 LLM 自由扮演”。

---

### 6.3 当前最准确的表述

当前实验最准确的定位是：

> 一个以规则机制为骨架、以结构化 LLM 心理层增强主观评估与解释输出的 hybrid simulation。

或者更简短地说：

> `Rule Core + Bounded LLM Psychology`

---

## 7. 汇报时可以直接说的话

如果需要一句适合口头汇报的话，可以直接说：

> 我们现在的实验不是让 LLM 直接决定世界和结果，而是让规则负责客观结构与主更新，让 LLM 负责 agent 对任务的主观理解、三策略之间的有限权衡，以及阶段性心理解释输出。

如果需要再短一点，可以说：

> 规则决定发生什么，LLM 决定 agent 怎么看、怎么想、怎么说。

---

## 8. PPT Page 2: 为什么先聚焦 `helplessness`

这一页如果要“每一点都要有 paper 支持”，最稳的写法不是说“文献证明 helplessness 一定比别的变量更重要”，而是：

- 文献直接支持 `helplessness / lack of control` 是一个合理核心构念
- 文献也直接支持 `anxiety / self-efficacy / support / usefulness` 会影响后续数字使用行为
- “先聚焦 helplessness，再把其他变量放到辅助解释层”是基于文献做出的研究收敛策略

### 8.1 `helplessness / lack of control` 作为核心构念

原文短摘录：

> “uncontrollable stressors may lead to learned helplessness”

中文：

> “不可控压力源可能导致习得性无助。”

它支持什么：

- `helplessness / perceived lack of control` 是一个有直接理论基础的核心构念
- 失败和不可控感的累积，可以被建模为无助感上升

具体来源：

- 原始 PDF：[learned_helplessness_and_learned_controllability_review_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/learned_helplessness_and_learned_controllability_review_2025.pdf)
- 提取文本：[learned_helplessness_and_learned_controllability_review_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/learned_helplessness_and_learned_controllability_review_2025.json)

### 8.2 `anxiety / self-efficacy` 会影响后续数字使用行为

原文短摘录：

> “Technology anxiety indirectly affects the intention”

中文：

> “技术焦虑会间接影响使用意愿。”

它支持什么：

- `anxiety` 不只是情绪噪声，而是和后续使用行为有关
- `self-efficacy` 和 `usefulness` 是 anxiety 影响行为的重要路径

具体来源：

- 原始 PDF：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf)
- 提取文本：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json)

### 8.3 `self-efficacy / support / usefulness` 都与使用意愿相关

原文短摘录：

> “higher perceived usefulness and self-efficacy”

原文短摘录：

> “more perceived family and formal support”

原文短摘录：

> “contributed to a higher intention”

中文：

> “更高的感知有用性、自我效能和支持，会带来更高的使用意愿。”

它支持什么：

- `self-efficacy`、`support`、`usefulness` 都是有文献支持的重要解释变量
- 所以把它们放到辅助解释层是合理的，不是随便挑的

具体来源：

- 原始 PDF：[acceptance_of_digital_health_services_among_older_adults_2023.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/acceptance_of_digital_health_services_among_older_adults_2023.pdf)
- 提取文本：[acceptance_of_digital_health_services_among_older_adults_2023.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/acceptance_of_digital_health_services_among_older_adults_2023.json)

### 8.4 老年人数字焦虑/技术恐惧底盘较高，且与低自我效能相关

原文短摘录：

> “older adults exhibit elevated levels of technophobia”

原文短摘录：

> “low self-efficacy”

原文短摘录：

> “protective effect”

中文：

> “老年人在数字健康情境下 technophobia 更高；低自我效能是风险因素，而社会连接具有保护作用。”

它支持什么：

- 老年群体本身更容易出现数字焦虑/技术恐惧
- `self-efficacy` 和 `support` 适合作为解释 helplessness 变化的辅助变量

具体来源：

- 原始 PDF：[technophobia_in_digital_health_contexts_review_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/technophobia_in_digital_health_contexts_review_2025.pdf)
- 提取文本：[technophobia_in_digital_health_contexts_review_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/technophobia_in_digital_health_contexts_review_2025.json)

### 8.5 `self-efficacy / social support` 是 technophobia 的主要影响因素

原文短摘录：

> “electronic health literacy, self-efficacy, and social support”

原文短摘录：

> “were the main influencing factors”

中文：

> “电子健康素养、自我效能和社会支持，是 technophobia 的主要影响因素。”

它支持什么：

- `support` 和 `self-efficacy` 不是边缘变量，而是主要相关因素
- 所以把它们放在辅助解释层，是有经验研究依据的

具体来源：

- 原始 PDF：[factors_influencing_technophobia_chinese_older_patients_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/factors_influencing_technophobia_chinese_older_patients_2025.pdf)
- 提取文本：[factors_influencing_technophobia_chinese_older_patients_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/factors_influencing_technophobia_chinese_older_patients_2025.json)

### 8.6 这一页最稳的讲法

你在 PPT 或口头里可以直接说：

> 文献一方面支持 `helplessness / lack of control` 是一个合理核心构念；另一方面也表明 `anxiety`、`self-efficacy` 和 `support` 会影响后续数字使用行为。基于这些文献，我当前先把 `helplessness` 作为主状态，把 `anxiety / confidence(self-efficacy) / support` 作为辅助解释层。

需要特别说明：

- “所以我们先专精 helplessness”不是某一篇 paper 的直接结论
- 它更准确地说，是基于上述文献做出的研究收敛策略

---

## 9. PPT Page 3: 核心机制对应的 paper 支持

这一页建议只讲最小主线：

`任务出现 -> 选择策略 -> 得到反馈 -> 更新 helplessness`

如果要求“每一步都要有 paper 支持”，最稳的讲法是：不是说文献直接给出了这条完整流程，而是说这条流程中的关键构件都有文献基础。

### 9.1 “失败 / 不可控反馈 -> helplessness 上升”

原文短摘录：

> “outcomes are independent of their actions”

原文短摘录：

> “decreased motivation to exert any effort”

中文：

> “当个体学到结果与自己的行动无关时，会出现更低的努力动机。”

它支持什么：

- 为什么实验里可以把 repeated failure / uncontrollability 建模为 helplessness 上升
- 为什么 helplessness 会进一步影响后续是否还愿意尝试

具体来源：

- 原始 PDF：[learned_helplessness_and_learned_controllability_review_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/learned_helplessness_and_learned_controllability_review_2025.pdf)
- 提取文本：[learned_helplessness_and_learned_controllability_review_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/learned_helplessness_and_learned_controllability_review_2025.json)

### 9.2 “anxiety / self-efficacy / usefulness -> 影响后续使用意愿”

原文短摘录：

> “Technology anxiety indirectly affects the intention”

原文短摘录：

> “through the perceived usefulness”

原文短摘录：

> “self-efficacy and perceived usefulness”

中文：

> “技术焦虑会通过感知有用性、自我效能等路径，间接影响后续使用意愿。”

它支持什么：

- 为什么在“任务出现”之后，不同 agent 会有不同主观判断
- 为什么系统里需要一个主观评估层，而不是把任务难度只当作客观固定值

具体来源：

- 原始 PDF：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf)
- 提取文本：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json)

### 9.3 “support / self-efficacy / usefulness -> 更高 intention”

原文短摘录：

> “higher perceived usefulness and self-efficacy”

原文短摘录：

> “more perceived family and formal support”

原文短摘录：

> “higher intention”

中文：

> “更高的有用性感知、自我效能和支持，会带来更高的后续使用意愿。”

它支持什么：

- 为什么核心机制里要允许 `seek_help_then_attempt`
- 为什么帮助不是边缘补丁，而是会真实改变后续行为倾向

具体来源：

- 原始 PDF：[acceptance_of_digital_health_services_among_older_adults_2023.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/acceptance_of_digital_health_services_among_older_adults_2023.pdf)
- 提取文本：[acceptance_of_digital_health_services_among_older_adults_2023.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/acceptance_of_digital_health_services_among_older_adults_2023.json)

### 9.4 “self-efficacy / support -> technophobia 风险或保护因素”

原文短摘录：

> “low self-efficacy”

原文短摘录：

> “protective effect”

原文短摘录：

> “main influencing factors”

中文：

> “低自我效能会增加 technophobia 风险，而支持因素具有保护作用。”

它支持什么：

- 为什么策略层里不仅有“自己试”，还应该有“求助后再试”和“回避”
- 为什么 `support effectiveness` 适合作为核心 memory 之一

具体来源：

- 原始 PDF：[technophobia_in_digital_health_contexts_review_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/technophobia_in_digital_health_contexts_review_2025.pdf)
- 提取文本：[technophobia_in_digital_health_contexts_review_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/technophobia_in_digital_health_contexts_review_2025.json)
- 原始 PDF：[factors_influencing_technophobia_chinese_older_patients_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/factors_influencing_technophobia_chinese_older_patients_2025.pdf)
- 提取文本：[factors_influencing_technophobia_chinese_older_patients_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/factors_influencing_technophobia_chinese_older_patients_2025.json)

### 9.5 “训练 / 支持性经验可以降低 technophobia”

原文短摘录：

> “significantly reduced Technophobia”

中文：

> “训练显著降低了 technophobia。”

它支持什么：

- 为什么实验里“反馈”不只是决定一次成败，还会影响下一轮心理状态
- 为什么正向支持经验可以被看作一种缓冲机制

具体来源：

- 原始 PDF：[smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf)
- 提取文本：[smartphone_psychological_wellbeing_technophobia_older_women_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/smartphone_psychological_wellbeing_technophobia_older_women_2025.json)

### 9.6 这一页最稳的讲法

你在 PPT 或口头里可以直接说：

> 我这一页的核心机制不是说文献已经直接给出了“任务出现、选择策略、得到反馈、更新 helplessness”这条完整流程，而是这条流程中的关键构件都有文献支撑：不可控失败会累积成 helplessness，anxiety / self-efficacy / usefulness 会影响后续使用意愿，而 support 会改变 technophobia 和后续参与程度。基于这些构件，我把它们组织成当前这条最小机制主线。

---

## 10. PPT Page 4: 实验设计对应的 paper 支持

这一页最需要诚实地区分两类内容：

- 哪些是文献直接支持的实验构件
- 哪些是为了把问题做成 simulation 而做出的设计选择

最稳的表达不是说“4 个 worlds、3 个 stages、每 stage 2 天”这些都有 paper 直接规定，
而是说：

- 文献支持我们操纵 `friction / barrier` 和 `support / intervention`
- 文献支持我们观察使用行为、回避和心理状态变化
- 具体的 world-stage 时间组织方式，是本研究的实验设计选择

### 10.1 为什么实验里要有 `friction / barrier`

原文短摘录：

> “The most prevalent barriers”

原文短摘录：

> “lack of self-efficacy, knowledge, support, functionality”

中文：

> “最常见的障碍包括缺乏自我效能、知识、支持和功能可用性。”

它支持什么：

- 为什么实验里要显式操纵数字摩擦/障碍
- 为什么 `high friction` 和 `low friction` 的世界条件是合理的

具体来源：

- 原始 PDF：[barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf)
- 提取文本：[barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.json)

### 10.2 为什么实验里要有 `support / assistance`

原文短摘录：

> “improve older adults’ skills, knowledge, digital literacy”

原文短摘录：

> “perceived self-efficacy”

原文短摘录：

> “reduce technophobia”

中文：

> “干预可以提升技能、知识、数字素养和感知自我效能，并降低 technophobia。”

它支持什么：

- 为什么实验里要显式操纵 `assist / support`
- 为什么 `high assist` 与 `low assist` 可以作为重要 treatment 条件

具体来源：

- 原始 PDF：[interventions_for_addressing_digital_exclusion_older_adults_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/interventions_for_addressing_digital_exclusion_older_adults_2025.pdf)
- 提取文本：[interventions_for_addressing_digital_exclusion_older_adults_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/interventions_for_addressing_digital_exclusion_older_adults_2025.json)

### 10.3 为什么实验里要观测“支持能否缓冲焦虑/技术恐惧”

原文短摘录：

> “family support”

原文短摘录：

> “digital anxiety”

原文短摘录：

> “intention to use”

中文：

> “家庭支持、数字焦虑和使用意愿之间存在结构关系。”

它支持什么：

- 为什么实验里可以把 `support` 看成缓冲因素
- 为什么我们要同时看行为结果和心理状态变化

具体来源：

- 原始 PDF：[digital_anxiety_to_empowerment_older_adults_2026.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/digital_anxiety_to_empowerment_older_adults_2026.pdf)
- 提取文本：[digital_anxiety_to_empowerment_older_adults_2026.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/digital_anxiety_to_empowerment_older_adults_2026.json)

### 10.4 为什么实验里要看“训练/支持后 technophobia 是否下降”

原文短摘录：

> “significantly reduced Technophobia”

中文：

> “显著降低了 technophobia。”

它支持什么：

- 为什么“高支持”不仅可能影响一次成功率，也可能影响后续心理状态
- 为什么在实验里把帮助看成持续性缓冲因素是合理的

具体来源：

- 原始 PDF：[smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf)
- 提取文本：[smartphone_psychological_wellbeing_technophobia_older_women_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/smartphone_psychological_wellbeing_technophobia_older_women_2025.json)

### 10.5 这一页哪些部分不是 paper 直接规定的

下面这些不是某篇 paper 直接规定的，而是本研究的实验设计选择：

- 用 `4` 个 worlds 组织条件比较
- 用 `steady / shock / recovery` 三阶段组织实验时间
- 每个 stage 设为 `2` 天
- 每 `30` 或 `60` 分钟一个 decision step

更准确的说法是：

- 文献支持我们操纵 barrier/support，并观察心理与行为变化
- 上述具体 world-stage-timestep 结构，是为了让这些构念在 simulation 中可操作化

### 10.6 这一页最稳的讲法

你在 PPT 或口头里可以直接说：

> 文献支持数字使用中的障碍和支持会显著影响老年人的数字参与、自我效能、technophobia 和后续使用意愿。因此我在实验里把 `friction` 和 `assist` 作为主要可操纵条件。至于 `4 个 worlds + 3 个 stages` 的组织方式，则是为了把这些构念做成可运行的 simulation 设计，而不是某篇 paper 直接规定的实验模板。

---

## 11. PPT Page 5: `LLM` 在哪里起作用，对应的 paper 支持

这一页最容易说过头，所以要非常注意区分：

- `paper-backed construct`
- `LLM-based implementation`

最稳的说法不是：

- “论文证明了必须用 LLM 做这些事”

而是：

- 论文支持这些主观构念本来就存在
- 我们用结构化 LLM 去 operationalize 这些主观构念

### 11.1 `task appraisal` 对应什么 paper-backed 构念

原文短摘录：

> “technology anxiety”

原文短摘录：

> “self-efficacy”

原文短摘录：

> “perceived usefulness”

中文：

> “技术焦虑、自我效能和感知有用性会共同影响后续数字使用意愿。”

它支持什么：

- 为什么 agent 在“面对同一任务”时应该先有一个主观评估层
- 为什么 `difficulty / risk / control / value` 这类 appraisal 不是完全凭空设定

更准确的说法：

- 这些构念有 paper 支持
- 用 `LLM task appraisal` 去生成结构化主观判断，是模型实现方式

具体来源：

- 原始 PDF：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf)
- 提取文本：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json)
- 原始 PDF：[acceptance_of_digital_health_services_among_older_adults_2023.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/acceptance_of_digital_health_services_among_older_adults_2023.pdf)
- 提取文本：[acceptance_of_digital_health_services_among_older_adults_2023.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/acceptance_of_digital_health_services_among_older_adults_2023.json)

### 11.2 `strategy deliberation` 对应什么 paper-backed 构念

原文短摘录：

> “higher intention”

原文短摘录：

> “technology anxiety indirectly affects the intention”

中文：

> “支持、自我效能、焦虑等因素会影响后续意愿和参与。”

它支持什么：

- 为什么 agent 不应该只按固定客观难度机械决策
- 为什么在“自己试 / 求助 / 回避”之间需要一个主观权衡层

更准确的说法：

- 论文支持“影响意愿的主观因素”
- 用 `LLM strategy deliberation` 去把这些因素映射成三策略分布，是实现方式

具体来源：

- 原始 PDF：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf)
- 提取文本：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json)
- 原始 PDF：[acceptance_of_digital_health_services_among_older_adults_2023.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/acceptance_of_digital_health_services_among_older_adults_2023.pdf)
- 提取文本：[acceptance_of_digital_health_services_among_older_adults_2023.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/acceptance_of_digital_health_services_among_older_adults_2023.json)

### 11.3 `event appraisal / digital emotion` 对应什么 paper-backed 构念

原文短摘录：

> “digital feedback had a negative effect on health information anxiety”

原文短摘录：

> “self-efficacy”

中文：

> “数字反馈会降低焦虑，并与自我效能变化相关。”

它支持什么：

- 为什么任务反馈之后，不只是更新一个 outcome 计数
- 为什么还要更新 `anxiety / confidence` 这种事件级心理状态

具体来源：

- 原始 PDF：[digital_feedback_health_information_anxiety_self_efficacy_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/digital_feedback_health_information_anxiety_self_efficacy_2025.pdf)
- 提取文本：[digital_feedback_health_information_anxiety_self_efficacy_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/digital_feedback_health_information_anxiety_self_efficacy_2025.json)
- 原始 PDF：[smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf)
- 提取文本：[smartphone_psychological_wellbeing_technophobia_older_women_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/smartphone_psychological_wellbeing_technophobia_older_women_2025.json)

### 11.4 `survey` 对应什么 paper-backed 构念

原文短摘录：

> “self-efficacy”

原文短摘录：

> “social support”

原文短摘录：

> “technology anxiety”

中文：

> “self-efficacy、support、technology anxiety 这些变量本来就是被直接测量过的。”

它支持什么：

- 为什么 survey 是当前 hybrid 里最稳的 LLM 使用层
- 因为这里对应的是已有文献中的成熟测量构念

具体来源：

- 原始 PDF：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf)
- 提取文本：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.json)
- 原始 PDF：[acceptance_of_digital_health_services_among_older_adults_2023.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/acceptance_of_digital_health_services_among_older_adults_2023.pdf)
- 提取文本：[acceptance_of_digital_health_services_among_older_adults_2023.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/acceptance_of_digital_health_services_among_older_adults_2023.json)
- 原始 PDF：[factors_influencing_technophobia_chinese_older_patients_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/factors_influencing_technophobia_chinese_older_patients_2025.pdf)
- 提取文本：[factors_influencing_technophobia_chinese_older_patients_2025.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/factors_influencing_technophobia_chinese_older_patients_2025.json)

### 11.5 `daily reflection / interview` 应该怎么讲

这里要最诚实。

`daily reflection` 和 `structured interview` 很适合保留，但它们不太适合讲成“强文献机制”。

更稳的说法是：

- `daily reflection`：解释层 / 审计层
- `interview`：可解释性输出层

它们帮助你做：

- 阶段总结
- 主观解释
- 汇报输出

但不应讲成：

- 论文已经直接证明“每天都会形成这种 reflection 机制”

所以这两层更接近：

- 受 AgentSociety 工作流风格启发的结构化实现
- 而不是强心理学因果机制

### 11.6 这一页最稳的讲法

你在 PPT 或口头里可以直接说：

> 当前实验里，LLM 的作用不是替代 rule core 去决定 outcome，而是把文献里已经被反复讨论的主观构念结构化地接进来：比如 task appraisal 对应 anxiety / self-efficacy / usefulness，strategy deliberation 对应意愿和回避倾向，event appraisal 对应反馈后的 anxiety / confidence 变化，survey 对应成熟测量构念。至于 daily reflection 和 interview，我把它们定位成解释层和输出层，而不是主因果机制。

## 12. 我们对于 AgentSociety 的借鉴和改造

这一部分很适合单独讲清楚，因为老师很容易追问：

- 你到底是直接用了 AgentSociety，还是自己重新做了一套？
- 你现在的创新点到底在框架层，还是机制层？

最稳的回答是：

- 我们借用了 AgentSociety 的实验框架外壳
- 但把中间真正与 `digital helplessness` 相关的机制链条，改成了一个更短、更可解释的 domain-specific prototype

### 12.1 AgentSociety 原论文能支持什么

AgentSociety 论文里最适合引用的两句短摘录是：

> “integrates LLM-driven agents, a realistic societal environment, and a powerful large-scale simulation engine”

中文：

> “它把 `LLM agent`、社会环境和大规模模拟引擎整合在一起。”

这句支持什么：

- 为什么我们适合把它当成一个实验外壳
- 因为它本来就不是单一 agent prompt，而是完整 simulator

另一句短摘录：

> “support for typical research methods – such as surveys, interviews, and interventions”

中文：

> “它支持 survey、interview、intervention 这类典型研究流程。”

这句支持什么：

- 为什么我们会沿用它的 `survey / interview / intervention` 工作流
- 为什么我们不是完全另起炉灶

具体来源：

- 原始 PDF：[AgentSociety_2025_Large-Scale_Simulation_of_LLM-Driven_Generative_Agents.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/AgentSociety_2025_Large-Scale_Simulation_of_LLM-Driven_Generative_Agents.pdf)
- 提取文本：[AgentSociety_2025_Large-Scale_Simulation_of_LLM-Driven_Generative_Agents.json](/Users/pifazuoren/Downloads/AgentSociety-main/paper/_extracted/AgentSociety_2025_Large-Scale_Simulation_of_LLM-Driven_Generative_Agents.json)

### 12.2 我们具体借鉴了 AgentSociety 的什么

如果讲人话，可以概括成四个层面。

第一，借它的 simulator 外壳。

- agent 容器
- environment / world
- workflow 调度
- 数据落库和回读

对应代码位置：

- [main.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/main.py#L2207)
- [main.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/main.py#L2299)

第二，借它的原生 workflow 类型。

现在这套实验不是手写一个 while-loop 在外面硬跑，而是继续沿用 AgentSociety 的 workflow step 类型，比如：

- `STEP`
- `SURVEY`
- `INTERVIEW`
- `SAVE_CONTEXT`
- `ENVIRONMENT_INTERVENE`

这一点很重要，因为它说明：

- 我们保留了 AgentSociety 原生实验组织方式
- 只是往里面换了更适合 `digital helplessness` 的 agent 内部机制

第三，借它的 `SocietyAgent` 基类和 memory/status 框架。

我们现在的核心 agent 不是从零造的，而是直接继承了 `SocietyAgent`：

- [proto/agent.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py#L158)

这意味着我们沿用了它的：

- agent 生命周期
- memory/status 存取方式
- 原生 survey / interview 接口

第四，借它“survey + interview + intervention”这套研究工作流思路。

这个借鉴不只是代码层面，也是研究范式层面：

- world 里做条件操控
- 中间观察 agent 行为
- stage 末做 survey
- 再补 interview 作为主观解释输出

这就是为什么我们的 Phase 5 虽然是自己定制的 structured interview，但它的 workflow 位置仍然是 AgentSociety 风格，而不是额外拼一层完全脱离原框架的后处理。

### 12.3 我们改造了什么

这里才是你自己的工作重点。

最核心的一句话是：

- 我们没有直接照搬 AgentSociety 的通用 open-ended agent 链，而是把 agent 内核收缩成了一个面向 `digital helplessness` 的短链条

具体来说，改造主要有五点。

第一，把通用社会生活 agent 改成了领域化 agent。

我们没有把重点放在“尽可能真实地模拟城市日常生活”，而是收缩到：

- 数字任务
- 摩擦/支持条件
- helplessness 变化
- 后续策略选择

也就是说，我们更关心：

- 失败之后无助如何更新
- 无助又如何影响下一次行为

而不是让 agent 无边界地生成很多与研究问题无关的日常行为。

第二，把内部决策链改成了 `rule core + bounded LLM psychology`。

在现在的 `proto` 里，真正起决定作用的 backbone 仍然是 rule：

- task assignment
- outcome
- helplessness 主更新
- stage/world 条件

LLM 只在有限位置进入：

- `task appraisal`
- `strategy deliberation`
- `event appraisal`
- `daily reflection`
- `interview`

接线位置可以直接看：

- [proto/agent.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py#L381)
- [proto/agent.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py#L447)
- [proto/agent.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py#L486)
- [proto/llm_psychology.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py#L915)
- [proto/llm_psychology.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py#L1555)

第三，把 open-ended 文本输出改成了受约束的结构化 JSON 心理层。

这一步是为了两个目标：

- 更可解释
- 更容易回退

所以我们加的 Phase 1 / 2 / 5 都不是自由发挥式 prompt，而是：

- 有固定输入证据窗口
- 有固定 JSON schema
- 有低置信度回退
- 有规则层兜底

这和纯 generative agent 很不一样。

第四，把 interview 从“自由对话”改成“结构化 explainability 输出”。

这里我们没有抛弃 AgentSociety 的 interview step，而是：

- 仍然走原生 `INTERVIEW`
- 但只在特殊 marker 下 override `do_interview()`
- 再把回答解析回 status/history/metrics

对应代码位置：

- [proto/agent.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py#L162)
- [main.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/main.py#L2299)
- [main.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/main.py#L2313)

第五，把实验目标从“通用社会模拟”改成“可解释的小机制实验”。

这点非常适合在汇报时强调。

AgentSociety 更像一个通用 simulator 平台；而我们当前这套更像：

- 在 AgentSociety 外壳里
- 针对老年人数字摩擦场景
- 做一个 `helplessness-centered` 的机制原型

所以我们的贡献重点不是：

- 又做了一个更大的社会模拟平台

而是：

- 在现有平台上，把一个具体心理机制讲得更清楚、更可控、更适合实验操控

### 12.4 为什么不直接照搬 AgentSociety 原生链条

这部分一定要讲清楚，不然老师会觉得“你是不是又把系统搞复杂了”。

最稳的理由有三个。

第一，研究目标更窄。

AgentSociety 面向的是更一般的社会模拟问题；但你当前想讲透的是：

- friction
- support
- helplessness
- behavior change

所以如果继续用一个过于通用、过于开放的生成链条，反而会稀释研究重点。

第二，当前阶段更需要机制清晰，而不是表面真实感最大化。

老师上次已经明确提到：

- 先专精一个点
- 把核心更新链讲透

在这个前提下，短链条比大而全链条更适合现在这个阶段。

第三，bounded hybrid 更容易解释，也更容易做 ablation。

因为现在可以很明确地区分：

- 哪些是 rule 决定的
- 哪些是 LLM 参与解释和权衡的
- 新层关掉之后旧行为是否保持一致

这对后面做：

- 对照实验
- 消融实验
- 汇报答辩

都会更友好。

### 12.5 这一部分最诚实的讲法

下面这段可以直接口头说：

> 我们没有从零重做一个 simulator，而是借用了 AgentSociety 的 agent-world-workflow 外壳，尤其是它对 survey、interview 和 intervention 这类研究流程的原生支持。在这个外壳里，我没有直接照搬它那种更通用的 open-ended agent 链，而是把中间的决策机制收缩成了一个更短的、围绕 digital helplessness 的 prototype。也就是说，框架层我借鉴 AgentSociety，机制层我做了有边界的改造。

### 12.6 如果老师继续追问“那你的创新到底在哪”

你可以继续这样答：

- 创新不在于重新造一个 AgentSociety 替代品
- 创新在于把一个通用生成式 agent 框架，收缩成一个适合研究 `digital helplessness` 的机制型实验系统

再往细一点说，就是三层：

- 第一层，提出了 `helplessness` 作为主状态、其它变量作为辅助解释层的收敛方式
- 第二层，把内部链条改成 `rule core + bounded LLM psychology`
- 第三层，用 Phase 1 / 2 / 5 把主观判断、有限 deliberation 和结构化 explainability 接进了原生 workflow

### 12.7 这一页 PPT 可以怎么做

如果你想把这块单独做成一页 PPT，建议只放三栏，不要太复杂：

- 左边：`Borrowed from AgentSociety`
- 中间：`Our Modification`
- 右边：`Why This Matters`

每栏只放 3 句以内：

`Borrowed from AgentSociety`

- workflow shell
- survey / interview / intervention
- SocietyAgent + memory/status

`Our Modification`

- helplessness-specific short chain
- rule core + bounded LLM
- structured interview and readback

`Why This Matters`

- 更聚焦
- 更可解释
- 更适合机制实验
