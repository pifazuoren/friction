# Literature -> Variable -> Code Map

这份表的目标不是做传统综述，而是直接回答一个工程问题：

- 这篇论文能支持你 prototype 里的哪个变量？
- 它更适合落到哪一段代码或实验流程？

## 一、先看代码模块

为了让文献和实现真正对齐，这里先把 `digital_helplessness_proto` 粗分成 7 个模块：

1. `simulation_framework`
   作用：说明为什么可以用 LLM/agent 做模拟，实验怎么组织。
2. `agent_state`
   作用：定义初始状态，如 `helplessness_score`、`technology_anxiety`、`self_efficacy`、`digital_literacy`。
3. `task_pool_and_friction`
   作用：定义数字任务类型，以及高/低 friction 场景。
4. `policy_choice`
   作用：代理面对任务时，选择尝试、回避、求助还是重试。
5. `outcome_and_feedback`
   作用：给一次尝试返回成功、失败、求助成功、卡住等结果。
6. `state_update`
   作用：把本轮反馈转成状态变化，尤其是无助感更新。
7. `intervention_and_metrics`
   作用：定义 assistant/support 的作用，并输出完成率、回避率、重试率、状态变化等指标。

## 二、全量映射表

| 文件 | 类别 | 对应变量 | 更适合支持的代码模块 | 备注 |
|---|---|---|---|---|
| `AgentSociety_2025_Large-Scale_Simulation_of_LLM-Driven_Generative_Agents.pdf` | 方法论 / 平台 | agent profile, workflow, experiment config | `simulation_framework` | 支撑你为什么以 AgentSociety 为底座做 prototype |
| `LLM_Agents_for_Piloting_Social_Experiments.pdf` | 方法论 / 社会实验 pilot | simulated participants, experimental condition, outcome comparison | `simulation_framework`, `intervention_and_metrics` | 很适合支撑“小规模 pilot 先行” |
| `generative_agents_interactive_simulacra_of_human_behavior_2023.pdf` | 方法论 / 生成式 agent | memory, reflection, behavior generation | `simulation_framework` | 可参考，但你现在不必照着做复杂 memory system |
| `social_simulation_driven_by_llm_agents_survey_2024.pdf` | 方法综述 | simulation validity, scenario design | `simulation_framework` | 最适合写 RP 的“方法相关工作”部分 |
| `gensim_general_social_simulation_platform_with_llm_agents_2024.pdf` | 方法论 / 社会模拟系统 | scalable agents, scenario orchestration | `simulation_framework` | 可作为“平台类工作”的补充引用 |
| `using_llms_to_simulate_multiple_humans_2022.pdf` | 方法论 / 模拟有效性 | persona simulation, study replication | `simulation_framework`, `intervention_and_metrics` | 可支撑“模拟不是纯拍脑袋” |
| `learned_helplessness_and_learned_controllability_review_2025.pdf` | 核心理论 | `helplessness_score`, controllability, repeated failure, avoidance | `agent_state`, `state_update` | 你无助感更新机制最核心的理论来源 |
| `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf` | 心理机制 | `technology_anxiety`, `self_efficacy`, use intention | `agent_state`, `policy_choice`, `state_update` | 很适合定义老年人初始心理状态 |
| `acceptance_of_digital_health_services_among_older_adults_2023.pdf` | 心理机制 / 采纳 | perceived usefulness, `self_efficacy`, privacy concern, support seeking | `agent_state`, `policy_choice`, `intervention_and_metrics` | 可支撑“求助”与“采纳倾向” |
| `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf` | 摩擦 / 障碍 | usability barrier, fear, frustration | `task_pool_and_friction`, `outcome_and_feedback` | 很适合提炼高 friction 事件模板 |
| `barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf` | 摩擦 / 促进因素 | barriers, facilitators, access support | `task_pool_and_friction`, `intervention_and_metrics` | 可用来定义高 friction 与低 friction 对照 |
| `digital_health_adoption_older_adults_chronic_disease_systematic_review_2024.pdf` | 采纳 / 使用 | adoption barrier, facilitator, support | `policy_choice`, `task_pool_and_friction`, `intervention_and_metrics` | 很适合支撑你的任务集合设计 |
| `barriers_to_digital_health_adoption_in_older_adults_2026.pdf` | 采纳 / 阻抗理论 | resistance, emotional barrier, identity barrier, anxiety loop | `task_pool_and_friction`, `policy_choice`, `state_update` | 对“数字摩擦 -> 无助感累积”很关键 |
| `interventions_for_addressing_digital_exclusion_older_adults_2025.pdf` | 干预 / 支持 | support intensity, inclusion support, training effect | `intervention_and_metrics` | 可支撑 assistant 强弱条件设置 |
| `technophobia_in_digital_health_contexts_review_2025.pdf` | 心理机制 / 综述 | technophobia, anxiety, adoption resistance | `agent_state`, `state_update`, `policy_choice` | 很适合把 technophobia 纳入人物画像 |
| `digital_health_technology_anxiety_systematic_review_2025.pdf` | 心理机制 / 综述 | `technology_anxiety`, risk perception, negative expectation | `agent_state`, `state_update` | 可支撑焦虑初始值和敏感度差异 |
| `factors_influencing_telemedicine_intention_older_adults_china_2025.pdf` | 行为结果 | intention to use, trust, usability perception | `policy_choice`, `intervention_and_metrics` | 可以支持“是否尝试任务”的决策逻辑 |
| `internet_healthcare_service_use_older_adults_2026.pdf` | 行为模式 | service-use pattern, ecology, context | `task_pool_and_friction`, `policy_choice` | 可支撑任务池不只一类任务 |
| `latent_obstacles_in_older_adults_digital_health_participation_2025.pdf` | 异质性 / 人群分层 | latent barrier profile, subgroup differences | `agent_state`, `task_pool_and_friction` | 非常适合做人群分型，而不是只做一个平均老人 |
| `digital_health_access_older_adults_perspective_2025` | 未保留 PDF | access difficulty, lived difficulty | 暂无 | 当前目录未保留 PDF，可后续补 |
| `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf` | 反馈机制 | feedback, anxiety, `self_efficacy` mediation | `outcome_and_feedback`, `state_update` | 这篇非常适合你写“成功/失败反馈如何改状态” |
| `social_support_technophobia_self_efficacy_ehealth_literacy_2025` | 未保留 PDF | social support, technophobia, eHealth literacy | 暂无 | 这篇概念上很重要，后面建议继续补 |
| `digital_anxiety_to_empowerment_older_adults_2026.pdf` | 干预 / 赋能 | empowerment, literacy, psychosocial driver | `state_update`, `intervention_and_metrics` | 适合支撑“支持后状态改善” |
| `technology_anxiety_loneliness_behavioral_intention_older_adults_2025.pdf` | 心理机制 / 行为 | `technology_anxiety`, behavioral intention | `policy_choice`, `state_update` | 可把 anxiety 直接连到回避或尝试 |
| `digital_reverse_mentoring_older_adults_digital_literacy_2026` | 未保留 PDF | mentoring, literacy, self-efficacy | 暂无 | 如果后面要做人类助手干预，很值得补 |
| `key_challenges_barriers_digital_literacy_older_adults_2026.pdf` | 摩擦 / 数字素养 | digital literacy barrier, skill gap | `agent_state`, `task_pool_and_friction` | 适合区分“不会”和“怕用” |
| `smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf` | 干预 / 心理结果 | smartphone intervention, technophobia reduction, wellbeing | `intervention_and_metrics`, `state_update` | 可支持“帮助后状态改善”的实验假设 |
| `factors_influencing_technophobia_chinese_older_patients_2025.pdf` | 心理机制 / 本土化 | technophobia, Chinese older adults | `agent_state`, `policy_choice` | 对中国情境特别有价值 |
| `community_based_digital_intervention_low_income_older_people_2024.pdf` | 干预 / 真实支持情境 | community support, digital intervention, practical barriers | `intervention_and_metrics`, `task_pool_and_friction` | 很适合你设计 assistant 的帮助方式 |

## 三、如果按变量来倒排

### 1. `helplessness_score`

最关键文献：

- `learned_helplessness_and_learned_controllability_review_2025.pdf`
- `barriers_to_digital_health_adoption_in_older_adults_2026.pdf`
- `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf`

最适合落到：

- `agent_state`
- `state_update`

### 2. `technology_anxiety`

最关键文献：

- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`
- `digital_health_technology_anxiety_systematic_review_2025.pdf`
- `technology_anxiety_loneliness_behavioral_intention_older_adults_2025.pdf`
- `factors_influencing_technophobia_chinese_older_patients_2025.pdf`

最适合落到：

- `agent_state`
- `policy_choice`
- `state_update`

### 3. `self_efficacy`

最关键文献：

- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`
- `acceptance_of_digital_health_services_among_older_adults_2023.pdf`
- `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf`
- `digital_anxiety_to_empowerment_older_adults_2026.pdf`

最适合落到：

- `agent_state`
- `state_update`
- `intervention_and_metrics`

### 4. `digital_friction`

最关键文献：

- `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf`
- `barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf`
- `barriers_to_digital_health_adoption_in_older_adults_2026.pdf`
- `key_challenges_barriers_digital_literacy_older_adults_2026.pdf`

最适合落到：

- `task_pool_and_friction`
- `outcome_and_feedback`

### 5. `support_level / assistant_effect`

最关键文献：

- `interventions_for_addressing_digital_exclusion_older_adults_2025.pdf`
- `community_based_digital_intervention_low_income_older_people_2024.pdf`
- `digital_anxiety_to_empowerment_older_adults_2026.pdf`
- `smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf`

最适合落到：

- `intervention_and_metrics`
- `state_update`

## 四、如果按代码优先级来读

### 1. 先写 `state_update`

先读：

- `learned_helplessness_and_learned_controllability_review_2025.pdf`
- `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf`
- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`

### 2. 再写 `task_pool_and_friction`

再读：

- `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf`
- `barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf`
- `barriers_to_digital_health_adoption_in_older_adults_2026.pdf`

### 3. 再写 `intervention_and_metrics`

再读：

- `interventions_for_addressing_digital_exclusion_older_adults_2025.pdf`
- `community_based_digital_intervention_low_income_older_people_2024.pdf`
- `smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf`

### 4. 最后补 `simulation_framework`

最后读：

- `LLM_Agents_for_Piloting_Social_Experiments.pdf`
- `social_simulation_driven_by_llm_agents_survey_2024.pdf`
- `using_llms_to_simulate_multiple_humans_2022.pdf`

## 五、对你现在最有用的“极简核心包”

如果你现在只想先把 prototype 跑起来，其实先抓 8 篇就够了：

- `learned_helplessness_and_learned_controllability_review_2025.pdf`
- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`
- `barriers_to_digital_health_adoption_in_older_adults_2026.pdf`
- `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf`
- `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf`
- `community_based_digital_intervention_low_income_older_people_2024.pdf`
- `LLM_Agents_for_Piloting_Social_Experiments.pdf`
- `social_simulation_driven_by_llm_agents_survey_2024.pdf`

这 8 篇基本就足够支撑你先写出一个：

- 有状态
- 有摩擦
- 有反馈
- 有无助感更新
- 有 assistance 条件对照

的最小可运行版本。
