# Helplessness Mechanism Refactor Plan

> 说明：这是一份“先收窄主机制”的完整修改计划。当前不改代码，只明确后续应该怎么改、先改什么、每一步改到哪些文件、如何验证是否改对。

**Goal:** 把当前 `digital_friction_mvp` 中的 helplessness / attribution 机制重构为一个更收敛、更容易解释、也更适合 CCF-B 论文表达的机制主干。

**Architecture:** 保留现有数字任务实验框架和平行世界实验能力，不推翻现有系统；第一阶段重构 helplessness 核心机制，并补上一层轻量 `attribution layer`，把主干收窄为“事件级不可控体验 -> 事件级归因 -> helplessness 持续性 / task-family 泛化更新”，并把 `self-efficacy`、`avoid_reason`、`controllable_success_memory`、`support_mode` 重新放到更清楚的位置。

**Tech Stack:** Python, AgentSociety, `examples/digital_friction_mvp/proto/*`, pytest, analysis scripts, parallel world experiments

---

## 1. 这次重构的总目标

这次重构不是为了“再加更多变量”，而是为了把已经有的变量重新组织成一个更像论文机制、而不是手工调参系统的结构。

目标状态应当满足下面 10 点：

1. helplessness 的最近端主驱动是 `event-level uncontrollability`，而不是失败次数本身。
2. 在 `event-level uncontrollability` 之后增加一个轻量 `event-level attribution` 层，用来补上 human reformulation。
3. `attribution_stability` 主要决定打击会不会拖久、恢复会不会变慢，而不是直接成为 raw delta 的大正项。
4. `attribution_scope` 主要决定受挫会不会从当前任务扩散到相近 `task_family`，而不是第一版就做“全数字生活塌缩”。
5. `attribution_locus` 第一版主要用于 narrative / stage explanation / interview / summary，不作为 helplessness 主公式中的强主项。
6. `task_self_efficacy` 是核心中介/放大器，而不是和所有变量并列堆加。
7. `felt_control` 主要留在 appraisal 层，用来影响事件级不可控体验、事件级归因和 mastery 判断，不再被重复计入最终 helplessness 主公式。
8. `avoid_reason` 必须维持三分：`helpless_avoid / risk_avoid / low_value_avoid`，且只有第一类应显著进入 helplessness 通道。
9. `controllable_success_memory` 保留，但压缩表达，避免同时存在太多 recovery/protection 小项；高质量 mastery 还应能把 attribution 往更可恢复的方向拉回。
10. `support` 主要通过修复 `self-efficacy / felt_control / mastery_quality` 起作用，而不是在 helplessness 上做强 direct buffer。

---

## 2. 当前代码的主要问题

### 2.1 主机制已经有了，但还不够“窄”

当前代码已经不是简单的 `failure_count += helplessness`，这点方向是对的；但 `state_update.py` 里仍保留了太多并列加项：

- `BASE_DELTAS`
- `repetition_delta`
- `uncontrollability`
- `efficacy_loss`
- `control_loss`
- `support_buffer`
- `avoid_reason_multiplier`
- `controllable_success_protection`
- `mastery_recovery_term`

这样的问题不是“变量多”，而是主次关系不够清楚。论文写出来会像：

- 机制很多
- 每条都在加减 helplessness
- 但哪条才是理论主线不够明确

### 2.2 重复计入比较明显

当前版本中，`felt_control` 同时出现在：

- task appraisal
- `effective_helplessness`
- `state_update.py` 的 `control_loss_term`
- mastery / support 判断

这会导致一个风险：同一个“低控制感”既影响事件解释，又单独惩罚 helplessness，容易形成双重或三重计入。

### 2.3 support 现在有点“太万能”

当前 support 同时：

- 直接减 helplessness (`support_buffer`)
- 影响 `task_self_efficacy`
- 影响 `mastery_recovery_term`
- 影响 `controllable_success_memory`

理论上 support 当然可能有直接效应，但如果在论文主机制里保留这么强的 direct path，很容易让评审感觉：

- 帮助像一个万能减分器
- 解释空间过大
- 规则设计感强于理论约束

### 2.4 `effective_helplessness` 混合了太多东西

`experience_memory.py` 里的 `effective_helplessness` 当前混合了：

- 原始 helplessness
- task-specific pressure
- recent failure pressure
- appraisal shift
- emotion pressure

这在“驱动策略选择”上未必有问题，但如果它在论文叙述里继续叫 helplessness，就会把行为门槛、情绪压力、任务难度、主观无助混在一起。

### 2.5 当前机制对 CCF-B 风格来说还是略复杂

如果目标是偏 CCF-B 的机制论文，目前最大的风险不是“不够先进”，而是：

- 规则很多
- 变量很多
- 需要解释的并列路径太多
- 缺少一眼就能说清楚的主链条

### 2.6 目前还缺一层更人类化的 attribution

当前系统已经有：

- `event_level_uncontrollability`
- `avoid_reason`
- `task_self_efficacy`
- `controllable_success_memory`

但它仍然缺一层明确回答下面问题的机制：

- 这次失败是“我不行”，还是“系统太难”
- 这是“暂时不顺”，还是“以后都这样”
- 只是“这一个任务的问题”，还是“这一类数字任务都不适合我”

这会导致一个问题：

- 现在系统能较好解释“这次伤不伤”
- 但还不够好地解释“为什么有的 agent 拖得久，有的恢复快；为什么有的只在某一类任务上退缩，有的会扩散到相近任务”

### 2.7 当前系统还不够区分“伤得重”与“拖得久 / 扩得开”

如果没有 attribution 层，系统会比较像：

- 同类负事件
  -> 同类 helplessness 累积

但人类式机制更像：

- 同类负事件
  -> 不同的不可控体验
  -> 不同的归因解释
  -> 不同的持续性与泛化范围

换句话说，当前系统还缺一个能把：

- acute vs chronic
- task-specific vs family-generalizing

区分开的中间层。

---

## 3. 推荐的目标机制图

建议最终把论文主图收成下面这条线：

`Profile / World Context`
-> `Task Appraisal`
-> `Attempt / Outcome`
-> `Event-level Uncontrollability`
-> `Event-level Attribution`
-> `Helplessness Persistence / Task-family Generalization / Future Avoidance`

其中各层的角色建议如下：

### 3.1 上游背景层

保留在上游，不进 episode-level helplessness 主公式：

- `digital_experience`
- `vision_limit`
- `past_fraud_experience`
- `friction_level`
- `risk_level`
- `assist_level`
- `accessibility_level`
- `human_support_level`

### 3.2 appraisal 层

这一层是判断层，不是最终 helplessness 公式本身：

- `task_self_efficacy`
- `felt_control`
- `task_value`
- `perceived_task_risk`
- `expected_help_effectiveness`

### 3.3 event-level uncontrollability 层

这一层仍然是 helplessness 的最近端主驱动，负责回答：

- 这次是不是形成了“我做了也没用”的体验
- 这次打击本身伤不伤

它仍然是第一阶段最核心的主干，不被 attribution 取代。

### 3.4 event-level attribution 层

这一层放在 `event_level_uncontrollability` 之后，而不是放在 appraisal 最前面。

第一版建议使用离散 event-level 标签，而不是一上来做很多 0-100 连续分数：

- `event_attribution_locus`
  - `self / mixed / situation`
- `event_attribution_stability`
  - `transient / mixed / stable`
- `event_attribution_scope`
  - `task_specific / family_generalizing / mixed`
- `event_attribution_explanation`

这层的职责要收窄：

- `stability`
  - 主要影响 helplessness 的持续性 / 恢复速度
- `scope`
  - 主要影响 task-family 内的泛化
- `locus`
  - 第一版主要用于 narrative、summary、interview、trajectory explanation
  - 暂不做 helplessness 主公式中的强主项

### 3.5 helplessness 核心更新层

真正直接进入 helplessness 主公式的建议只保留：

- `event_level_uncontrollability`
- `task_self_efficacy` 的放大/缓冲作用
- 很弱的 outcome base
- `controllable_success_memory` 的长期保护

attribution 第一版不作为一组新的并列加项硬塞进主公式。

它更适合通过两条后果支路发挥作用：

- `attribution_stability`
  - 决定这次打击会不会更久地残留
- `attribution_scope`
  - 决定这次受挫会不会扩到相近 `task_family`

同时，高质量 mastery 和 `enabling_support` 不只是降低 helplessness，也应把 attribution 往：

- `stable -> transient`
- `family_generalizing -> task_specific`

方向拉回。

### 3.6 并行支路

下面这些不应再和 helplessness 主公式并列：

- `task_value / perceived usefulness`
- `risk / privacy / security concerns`
- `support` 的大部分作用
- `digital_emotion_state`
- `trust_in_apps`

它们可以存在，但应更多影响：

- `attempt/use`
- `avoid_reason`
- `strategy`
- `continued engagement`

### 3.7 实验机制重构表（含 `mineruex` 正文整句支持）

说明：

- 下表只纳入能在 `/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex` 正文 `*.md` 中找到完整句子或完整段落支撑的机制项。
- 如果某个修改建议暂时找不到正文整句支持，就不放进这张表。
- 引文保留原文表述；若 MinerU 提取存在少量 OCR 问题，这里不主动润色原句，只在“重构建议”里做理论解释。

| 机制部件 | 当前实现（代码） | 建议重构 | `mineruex` 正文整句支持 | 为什么这句能支持修改 |
| --- | --- | --- | --- | --- |
| `helplessness` 主驱动 | 当前 `apply_helplessness_update()` 同时把 `base + repetition_delta + uncontrollability + efficacy_loss + control_loss - support_buffer` 一起加入 `raw_delta`，失败次数仍直接进主公式。见 [state_update.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py#L100)。 | 把主驱动收窄为 `event_level_uncontrollability`；`failure` 和 `failure streak` 只作为上游线索，不再直接作为 helplessness 主加项。 | “These results were interpreted as supporting a learned "helplessness" explanation of interference with escape responding: Ss failed to escape shock in the shuttle box following inescapable shock in the harness because they had learned that shock termination was independent of responding.” [failure-to-escape-traumatic-shock-nnwn6t036k.md#L13](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/failure-to-escape-traumatic-shock-nnwn6t036k/auto/failure-to-escape-traumatic-shock-nnwn6t036k.md#L13)<br><br>“Both the old and reformulated hypotheses hold the expectation of noncontingency to be the crucial determinant of the symptoms of learned helplessness.” [Learned Helplessness in Humans..md#L45](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/Learned%20Helplessness%20in%20Humans./auto/Learned%20Helplessness%20in%20Humans..md#L45) | 这两句都把 helplessness 的核心放在 action-outcome noncontingency / expectation of noncontingency 上，而不是失败次数本身。 |
| `event-level attribution` 层 | 当前系统没有 dedicated attribution layer；负向事件主要直接进入 helplessness / memory 更新，`avoid_reason` 只解释回避而不解释失败后的理解方式。 | 在 `event_level_uncontrollability` 之后增加 `event_attribution_locus / stability / scope`；第一版让 `stability` 主要影响持续性，让 `scope` 主要影响 task-family 泛化，并把 `locus` 先保留为弱解释项。 | “Our reformulation regards the attribution the individual makes for noncontingency between his acts and outcomes in the here and now as a determinant of his subsequent expectations for future noncontingency. These expectations, in turn, determine the generality, chronicity, and type of his helplessness symptoms.” [Learned Helplessness in Humans..md](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/Learned%20Helplessness%20in%20Humans./auto/Learned%20Helplessness%20in%20Humans..md)<br><br>“The generality of the depressive deficits will depend on the globality of the attribution for helplessness, the chronicity of the depression deficits will depend on the stability of the attribution for helplessness, and whether selfesteem is lowered will depend on the internality of the attribution for helplessness.” [Learned Helplessness in Humans..md](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/Learned%20Helplessness%20in%20Humans./auto/Learned%20Helplessness%20in%20Humans..md) | 这两句直接支持把 attribution 放在 noncontingency 之后，并把 stability / globality / internality 分别对应到持续性、泛化性和 self-related meaning。 |
| `task_self_efficacy` 与 `felt_control` 的分工 | 当前 `task_self_efficacy` 和 `felt_control` 都直接进入 `state_update.py` 的最终公式；同时 `felt_control` 又已进入 appraisal 和 `effective_helplessness`。见 [state_update.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py#L139)、[experience_memory.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py#L352)。 | `task_self_efficacy` 保留为关键中介/放大器；`felt_control` 主要留在 appraisal 层，用于影响 `event_level_uncontrollability`、`support_mode` 和 mastery 质量，不再作为最终 helplessness 的强独立惩罚项。 | “An outcome expectancy is defined as a person's estimate that a given behavior will lead to certain outcomes. An efficacy expectation is the conviction that one can successfully execute the behavior required to produce the outcomes.” [Self-Efficacy...md#L36](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/Self-Efficacy-%20Toward%20a%20Unifying%20Theory%20of%20Behavioral%20Change./auto/Self-Efficacy-%20Toward%20a%20Unifying%20Theory%20of%20Behavioral%20Change..md#L36)<br><br>“Efficacy expectations determine how much effort people will expend and how long they will persist in the face of obstacles and aversive experiences.” [Self-Efficacy...md#L40](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/Self-Efficacy-%20Toward%20a%20Unifying%20Theory%20of%20Behavioral%20Change./auto/Self-Efficacy-%20Toward%20a%20Unifying%20Theory%20of%20Behavioral%20Change..md#L40) | 原文清楚区分了 outcome expectancy 和 efficacy expectation，因此 `task_self_efficacy` 应保留；但它也提示我们不要把所有“控制”相关量都混成一个并列加法项。 |
| `task_value / perceived usefulness` 的位置 | 当前代码已经部分把 `risk/value` 放在 avoidance interpretation，而不是 helplessness 核心通道中。见 [outcome_model.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/outcome_model.py#L74)、[experience_memory.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py#L352)。 | 正式把 `task_value / perceived usefulness` 归入 `attempt/use / low_value_avoid` 支路，不再让它和 helplessness 主机制并列。 | “Although difficulty of use can discourage adoption of an otherwise useful system, no amount of ease of use can compensate for a system that does not perform a useful function.” [Perceived Usefulness...md#L243](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/Perceived%20Usefulness,%20Perceived%20Ease%20of%20Use,%20and%20User%20Acceptance%20of%20Information%20Technology/auto/Perceived%20Usefulness,%20Perceived%20Ease%20of%20Use,%20and%20User%20Acceptance%20of%20Information%20Technology.md#L243)<br><br>“Thus, we could conclude that perceived usefulness was a decisive factor in the behavior intention of older adults to use digital public services.” [older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.md#L162](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024/auto/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.md#L162) | 这两句都说明 usefulness 主要解释 use/intention，而不是 helplessness 本身，因此应当分流到 use/avoid 支路。 |
| `avoid_reason` 三分而不是把所有 non-use 都并入 helplessness | 当前 `infer_avoid_reason()` 已经区分 `helpless_avoid / risk_avoid / low_value_avoid`，但下游仍有进一步细分空间。见 [outcome_model.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/outcome_model.py#L74)、[state_update.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py#L159)。 | 保留三分法，并进一步确保只有 `helpless_avoid` 显著进入 helplessness 和记忆主通道；`risk_avoid` 与 `low_value_avoid` 主要影响 attempt/use。 | “We concluded that the technology anxiety experienced by older people did not have a direct impact on their willingness to use digital public services, meaning that the discomfort or uneasiness that older people might feel about using technology did not necessarily translate into their unwillingness to use digital public services.” [older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.md#L160](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024/auto/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.md#L160)<br><br>“In summary, higher perceived usefulness and self-efficacy, more perceived family and formal support, and low privacy concerns contributed to a higher intention to use digital health services, among our relatively well-educated and healthy sample of older adults.” [acceptance_of_digital_health_services_among_older_adults_2023.md#L127](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/acceptance_of_digital_health_services_among_older_adults_2023/auto/acceptance_of_digital_health_services_among_older_adults_2023.md#L127) | 这两句直接说明“不用/不想用”是多因素共同决定的，因此 non-use 不能简单等同于 helplessness。 |
| `controllable_success_memory` / mastery 保护项 | 当前 `_controllable_success_gain()` 只在较高 `felt_control`、较低不可控、且 `success_self` 或高质量 `enabling_support` 时增加保护；同时 `state_update.py` 里还有 `controllable_success_protection`。见 [experience_memory.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py#L85)、[state_update.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py#L162)。 | 保留这一思想，但压缩成一个更单一的长期保护构件，例如统一叫 `controllable_success_memory` 或 `mastery_quality_memory`，避免太多 recovery/protection 小项并列。 | “In this regard, it has been shown that previous experiences of control over adverse situations may reduce the susceptibility to helplessness, hence providing “immunization” against certain stressful conditions (9, 112), which then may be recognized as “controllable”.” [learned_helplessness_and_learned_controllability_review_2025.md#L106](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/learned_helplessness_and_learned_controllability_review_2025/auto/learned_helplessness_and_learned_controllability_review_2025.md#L106)<br><br>“When they successfully use digital tools—such as conducting a video call, managing a mobile payment, or accessing web-based health services—this sense of accomplishment becomes a powerful motivator for further learning and sustained engagement [56].” [digital_anxiety_to_empowerment_older_adults_2026.md#L196](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md#L196) | 这两句共同支持“可控成功经验具有保护性”，而且保护不是抽象成功次数，而是与 control / accomplishment 质量相关。 |
| `support` 主要作为间接修复机制，而非强 direct buffer | 当前 support 既直接进入 `support_buffer`，又通过 `support_mode` 影响 `task_self_efficacy`、mastery 和记忆。见 [state_update.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py#L144)、[outcome_model.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/outcome_model.py#L135)、[experience_memory.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py#L107)。 | 弱化或取消 `support_buffer` 这条强 direct path，保留 `enabling_support / substituting_support` 区分，让 support 主要通过修复 `self-efficacy / felt_control / expected_help_effectiveness / mastery_quality` 起作用。 | “One of the most consistently supported buffers against digital anxiety is family support. Beyond emotional reassurance, family members often provide practical technical guidance and encouragement, helping older adults feel less overwhelmed and more motivated to engage with digital tools.” [digital_anxiety_to_empowerment_older_adults_2026.md#L128](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md#L128)<br><br>“However, overly reliant support can have mixed effects. While moderate, empowering support improves outcomes, excessive dependence may inadvertently signal incompetence or fuel learned helplessness, thereby reinforcing anxiety [7, 34].” [digital_anxiety_to_empowerment_older_adults_2026.md#L130](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md#L130) | 第一条支持“support 会修复资源”；第二条明确支持“帮助方式不同，效果不同”，因此不适合把 support 写成统一直接减分器。 |
| 结构性脆弱性应保留在 `profile/world context` 上游，而非 episode-level 主公式 | 当前代码已把 `digital_experience / vision_limit / past_fraud_experience` 放入初始 task-domain memory，并把 `risk_level / accessibility_level / human_support_level` 放入环境层。见 [experience_memory.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py#L121)、[agent.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py#L751)。 | 继续把结构性处境留在上游：它们可以影响初始效能感、风险感知、帮助可得性和任务解释，但不应作为每次 helplessness 更新的直接加项。 | “These ageist stereotypes that depict older adults as “inflexible” or unable to “adapt to new ideas and to the use [of technology]” contribute to older adults’ feelings of low self-efficacy and discomfort and beliefs that efforts to learn will be unproductive or embarrassing [46].” [community_based_digital_intervention_low_income_older_people_2024.md#L165](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md#L165)<br><br>“Overall, our findings reinforce how older adults’ aversion to digital technologies are shaped by factors such as age-related barriers and negative self-perceptions and a lack of user-friendly digital devices. However, our findings add to the existing literature by highlighting how individual-level factors are intertwined with and situated within the structural vulnerabilities that older adults confront such as age and income-related stigma and marginality.” [community_based_digital_intervention_low_income_older_people_2024.md#L173](/Users/pifazuoren/Downloads/AgentSociety-main/paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md#L173) | 这两句都把结构性因素放在更上游的位置，说明它们塑造 self-efficacy、motivation、attitude，而不是简单等同于一次事件后的 helplessness 增量。 |

---

## 4. 第一阶段必须完成的重构

第一阶段是论文最关键的部分，也是最值得先做的版本。

### Task 1: 把 `perceived_uncontrollability` 正式改成 `event_level_uncontrollability`

**目标**

把命名和理论口径统一，避免后面继续在 “felt control / perceived uncontrollability” 两个近义词之间摇摆。

**涉及文件**

- `examples/digital_friction_mvp/proto/models.py`
- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/uncontrollability_calibrator.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/tests/test_state_update.py`
- `examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`

**要做什么**

- 把对外主命名改成 `event_level_uncontrollability`。
- 若担心一次性改太多，可短期保留兼容别名：
  - 输入层允许旧字段名
  - 内部统一转成新字段
- 日志、导出字段、状态表述也统一改名。

**这样改的原因**

- `felt_control` 更像一个 appraisal state。
- `event_level_uncontrollability` 更像一次具体事件后的近端解释。
- 这两个概念可以相关，但不应该同名或混名。

**测试**

- [ ] 更新 `test_state_update.py` 的输入构造器和断言字段名
- [ ] 更新 `test_uncontrollability_calibrator.py` 的返回字段断言
- [ ] 运行：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_state_update.py \
  examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py \
  examples/digital_friction_mvp/tests/test_experience_memory.py -q
```

---

### Task 1.5: 建立 attribution state shell（先做壳，不先做大公式）

**目标**

把 attribution 从“零散想法”升级为正式机制层，但第一版先只建壳：

- 事件层记录每次失败后的 attribution
- 状态层沉淀 task-family 级轻量 summary

**涉及文件**

- `examples/digital_friction_mvp/proto/models.py`
- `examples/digital_friction_mvp/proto/state_schema.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`
- `examples/digital_friction_mvp/attributionmemorytodo.md`

**推荐做法**

第一版不要先做很多全局 0-100 attribution 大分数。

更稳的做法是：

- 事件层新增：
  - `event_attribution_locus`
  - `event_attribution_stability`
  - `event_attribution_scope`
  - `event_attribution_explanation`
- `stream memory` 新增 topic：
  - `digital_failure_attribution`
- `status / task_family memory` 只保留轻量 summary：
  - `dominant_attribution_stability`
  - `dominant_attribution_scope`
  - `recent_stable_attribution_ratio`
  - `recent_generalizing_attribution_ratio`
  - `attribution_summary`

**为什么这样改**

- 更接近人类式表述
- 更容易写 prompt、日志和访谈摘要
- 不会一上来又回到“很多连续分数一起调参”
- 更贴合当前已经存在的 `task_family` memory 结构

**测试**

- [ ] event-level attribution 结构能被正常写入 log / stream
- [ ] task-family 级 attribution summary 能在多次失败后更新
- [ ] 不会因为一次失败就直接把 attribution state 全局定型

---

### Task 2: 收窄 helplessness 主公式，去掉失败次数的直接主导地位

**目标**

让 helplessness 更新真正围绕“做了也没用”的体验展开，而不是围绕失败累计展开。

**涉及文件**

- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/models.py`
- `examples/digital_friction_mvp/tests/test_state_update.py`

**当前问题**

`repetition_delta` 仍直接进入 `raw_delta`，这会让失败次数仍然以主项方式推 helplessness。

**推荐改法**

把失败相关因素重构成两层：

1. 上游线索层
   - `consecutive_failures`
   - `friction`
   - `failure_even_with_help`
   - `same_task_failure_history`

2. 近端驱动层
   - `event_level_uncontrollability`

建议的新思路：

- `outcome_type` 只提供一个很小的 base signal。
- `consecutive_failures` 不再直接加 helplessness。
- 连续失败只提高“这次事件更可能被解释为不可控”的概率，或提高 LLM/rule calibration 的上限。
- helplessness 主公式只保留：
  - 小 base
  - `event_level_uncontrollability`
  - `task_self_efficacy` 放大器
  - `controllable_success_memory` 缓冲器

**推荐保留的直观逻辑**

- 同样失败，如果 agent 仍觉得“这次主要是偶然/可修复/下次我能做成”，helplessness 不应机械上涨。
- 同样结果，如果 agent 明确觉得“无论我怎么做都没用”，helplessness 才应明显上升。

**不建议继续保留的设计**

- `repetition_delta` 直接做主加项
- `control_loss_term` 和 `event_level_uncontrollability` 同时强力并列

**建议的最低限度公式**

可先收成：

```text
delta_helplessness
= small_outcome_base
+ uncontrollability_core
* efficacy_amplifier
- mastery_buffer
```

其中：

- `small_outcome_base`：只保留非常弱的结果信号
- `uncontrollability_core`：主驱动
- `efficacy_amplifier`：低效能时放大，高效能时缓冲
- `mastery_buffer`：长期保护

**测试**

- [ ] 新增或重写这些断言：
  - 同样失败，不同 `event_level_uncontrollability`，高不可控那组 delta 明显更高
  - 同样失败次数，但低不可控条件下 helplessness 不应机械上涨
  - 失败 streak 本身不应在低不可控条件下造成大幅额外惩罚
- [ ] 运行：

```bash
python -m pytest examples/digital_friction_mvp/tests/test_state_update.py -q
```

---

### Task 3: 把 `task_self_efficacy` 定位为关键中介，把 `felt_control` 退回 appraisal 层

**目标**

减少重复计入，让两者分工更清楚。

**涉及文件**

- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/tests/test_state_update.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`

**推荐分工**

- `task_self_efficacy`
  - 保留在 helplessness 核心更新中
  - 作为核心中介/放大器
  - 也保留在 attempt strategy 中

- `felt_control`
  - 保留在 appraisal 层
  - 用于判断：
    - `event_level_uncontrollability`
    - `support_mode`
    - `controllable_success_memory` 的积累门槛
  - 不建议继续作为最终 helplessness 主公式中的强独立惩罚项

**为什么这样改**

- `task_self_efficacy` 回答的是“我能不能做成”
- `felt_control` 回答的是“这件事现在是不是在我掌控之中”
- 两者可以相关，但不是一个东西
- 如果两者在 appraisal 和 final update 里反复叠加，机制会变得难解释

**测试**

- [ ] 让 `test_state_update.py` 体现出：
  - `task_self_efficacy` 低会放大不可控事件伤害
  - `felt_control` 主要通过 appraisal / calibration 发挥作用，而不是在最终公式里双重惩罚
- [ ] 运行：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_state_update.py \
  examples/digital_friction_mvp/tests/test_experience_memory.py -q
```

---

### Task 3.5: 增加 `infer_event_attribution()`，把 human reformulation 正式接进来

**目标**

在 `event_level_uncontrollability` 之后增加一层轻量 attribution，回答：

- 这次更像是 `self / mixed / situation`
- 这是 `transient / mixed / stable`
- 这是 `task_specific / family_generalizing / mixed`

**涉及文件**

- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/proto/models.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/outcome_model.py`
- 可能新增 `examples/digital_friction_mvp/proto/attribution_inference.py`
- `examples/digital_friction_mvp/tests/test_outcome_model.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`
- 可能新增 `examples/digital_friction_mvp/tests/test_attribution_inference.py`

**推荐做法**

触发范围先收窄，只在明确负向事件后触发：

- `failure_after_attempt`
- `failure_even_with_help`
- `abandon_midway`

第一版先不要把 `avoid_without_attempt` 作为 attribution 主入口；如果后面需要，可以只给 `helpless_avoid` 一个弱入口。

第一版 attribution 不采用开放式自由生成，也不先做 rule baseline；更推荐：

- 由 LLM 直接在受限标签空间内判别 attribution
- 输出必须是结构化 JSON
- 必须包含 `judge_confidence`
- 如果置信度不足，则回退到保守标签或“不施加额外 attribution effect”

推荐输入信号：

- `event_level_uncontrollability`
- `task_self_efficacy`
- `felt_control`
- `support_mode`
- `recent_same_task_failure_count`
- `task_family`
- `friction_tier`

推荐输出先离散化：

- `event_attribution_locus = self / mixed / situation`
- `event_attribution_stability = transient / mixed / stable`
- `event_attribution_scope = task_specific / family_generalizing / mixed`
- `event_attribution_explanation`
- `judge_confidence`

**为什么这样改**

- attribution 不是最前面的 appraisal，也不是最后的 memory 注释
- 它应该卡在：
  - `uncontrollability` 之后
  - `helplessness / generalization` 后果展开之前
- 这样更接近 AgentSociety 原生分工：语义解释交给 LLM，状态推进与机制后果交给规则
- 也比 `rule-first` 版本更少“手工调参”痕迹，更适合把 attribution 解释为 human-like interpretation

**测试**

- [ ] 同样失败，不同输入条件下 attribution 能区分 `stable` 与 `transient`
- [ ] attribution 的 `scope` 能区分 `task_specific` 与 `family_generalizing`
- [ ] attribution 输出稳定，不依赖开放式自由发挥
- [ ] 低置信度时 attribution 会稳定回退到保守标签或“不施加额外 attribution effect”

---

### Task 4: 维持 `avoid_reason` 三分，但把下游通道真正分开

**目标**

把 “不做” 和 “无助” 彻底拆开，避免把所有 non-use 都算成 helplessness。

**涉及文件**

- `examples/digital_friction_mvp/proto/outcome_model.py`
- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/compat.py`
- `examples/digital_friction_mvp/tests/test_outcome_model.py`
- `examples/digital_friction_mvp/tests/test_state_update.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`
- `examples/digital_friction_mvp/tests/test_compat_mapping.py`

**当前优点**

当前系统已经有：

- `helpless_avoid`
- `risk_avoid`
- `low_value_avoid`

这是非常值得保留的。

**仍需修改的地方**

- 只有 `helpless_avoid` 应显著增加 helplessness。
- `risk_avoid` 应主要进入风险回避和 use/intention 支路。
- `low_value_avoid` 应主要进入任务价值/非使用支路。
- 在 memory 中，三者也不应留下相同性质的伤害痕迹。

**特别要改的点**

- `compat.py` 目前仍然对 `avoid_without_attempt` 做统一线性更新，这过粗。
- 建议让 `avoidance_tendency` 或信任相关指标能区分：
  - 因无助而退缩
  - 因风险而谨慎
  - 因觉得没用而不值得做

**测试**

- [ ] `test_outcome_model.py` 继续保证三分判断正确
- [ ] `test_state_update.py` 保证 `helpless_avoid > risk_avoid > low_value_avoid`
- [ ] `test_experience_memory.py` 保证不同 avoid 原因对 memory 的影响不同
- [ ] `test_compat_mapping.py` 根据新逻辑补测
- [ ] 运行：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_outcome_model.py \
  examples/digital_friction_mvp/tests/test_state_update.py \
  examples/digital_friction_mvp/tests/test_experience_memory.py \
  examples/digital_friction_mvp/tests/test_compat_mapping.py -q
```

---

### Task 4.5: 让 attribution 影响“持续性”和“task-family 泛化”，而不是变成大杂烩主公式

**目标**

把 attribution 从“记下来”升级为“真的起作用”，但作用方式要非常克制：

- `stability` 管持续性
- `scope` 管 task-family 泛化
- `locus` 先弱化

**涉及文件**

- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/proto/compat.py`
- `examples/digital_friction_mvp/tests/test_state_update.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`
- `examples/digital_friction_mvp/tests/test_compat_mapping.py`

**推荐做法**

- attribution 的识别采用 bounded LLM classification + confidence gating
- attribution 的后果映射保持 rule-based 固定
- 不让 LLM 直接输出 helplessness 增量、扩散范围或恢复速度

- `attribution_stability`
  - 不直接作为 helplessness raw delta 的大正项
  - 主要影响：
    - helplessness 残留时长
    - 恢复速度
    - 一次成功能不能很快拉回来
- `attribution_scope`
  - 不直接做“全局 digital collapse”
  - 第一版只作用到相近 `task_family`
  - 例如：
    - 降低相近 family 的初始 `felt_control`
    - 提高 anticipatory difficulty
    - 提高 future avoidance 倾向
- `attribution_locus`
  - 第一版主要进入：
    - `attribution_summary`
    - stage explanation
    - interview / trajectory interpretation
  - 暂不做强公式项

**特别注意**

- `avoid_reason` 回答的是“这次为什么没做”
- `attribution` 回答的是“失败以后，我怎么理解这次失败”

两者必须分开，不能混。

同时也要分开：

- `LLM` 负责 attribution 标签判别
- `rule` 负责 attribution 生效后的 persistence / generalization 更新

**测试**

- [ ] 同样失败，`stable` attribution 比 `transient` attribution 恢复更慢
- [ ] `family_generalizing` 比 `task_specific` 更容易影响相近 `task_family`
- [ ] 去掉 attribution 层后，模型对 chronicity / generality 的区分明显变差
- [ ] LLM 只负责标签判别，不直接决定 helplessness 数值增量

---

### Task 5: 精简 mastery 相关机制，只保留一个长期保护主项

**目标**

保留“真正自己学会且感到可控的成功会形成保护”这个核心思想，但把表达压缩得更像论文机制，而不是多个细小奖励项并列。

**涉及文件**

- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/models.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`
- `examples/digital_friction_mvp/tests/test_state_update.py`

**推荐做法**

保留两个层次，但不再扩张：

1. 一个长期保护项
   - 名称建议统一为 `controllable_success_memory`
   - 或改名为 `mastery_quality_memory`

2. 一个短期即时恢复项
   - 用于成功后的当次回落
   - 不再拆出过多 bonus 分支

同时补上一层 attribution rewrite：

- 高质量 mastery 不只是降低 helplessness
- 还应把 attribution 往：
  - `stable -> transient`
  - `family_generalizing -> task_specific`
  拉回

**建议删除或弱化的复杂度来源**

- 太多并列的 `+0.15 / +0.35 / +0.4 / +0.2`
- 过多 episode-level bonus 叠加

**建议保留的判定门槛**

成功能否进入长期保护，应至少满足：

- agent 不是纯代办完成
- `felt_control` 足够高
- `event_level_uncontrollability` 低
- 任务完成后 agent 有一定“自己会了”的证据

**测试**

- [ ] `success_self` 比 `success_with_help` 更容易积累长期保护
- [ ] `enabling_support` 比 `substituting_support` 更容易积累保护
- [ ] 高质量 mastery 能缓冲后续高摩擦打击
- [ ] 高质量 mastery 能降低 stable/generalizing attribution 的残留概率
- [ ] 运行：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_experience_memory.py \
  examples/digital_friction_mvp/tests/test_state_update.py -q
```

---

### Task 6: 把 support 从“万能减分器”改成“间接修复机制”

**目标**

让 support 的论文表达更稳，也让系统更不容易给人“纯靠参数调出来”的感觉。

**涉及文件**

- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/outcome_model.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/tests/test_state_update.py`
- `examples/digital_friction_mvp/tests/test_outcome_model.py`
- `examples/digital_friction_mvp/tests/test_experience_memory.py`

**推荐做法**

- 把 `support_buffer` 降到极弱，甚至第一版直接删掉。
- 保留 `support_mode` 区分：
  - `enabling_support`
  - `substituting_support`
- support 主要通过下面几条线起作用：
  - 修复 `task_self_efficacy`
  - 改善 `felt_control`
  - 改善 `expected_help_effectiveness`
  - 影响 `controllable_success_memory` 是否累积
  - 降低 stable / family_generalizing attribution 的形成概率

第一版建议明确区分：

- `enabling_support`
  - 更容易阻止 stable/generalizing attribution 形成
- `substituting_support`
  - 可能提高这次成功率
  - 但不一定改变失败解释方式

**论文表达对应**

最稳的说法不是 “support only works indirectly”，而是：

- support works primarily through repairing mediating resources
- direct effect, if any, is limited

**测试**

- [ ] enabling support 比 substituting support 更能提升 `task_self_efficacy`
- [ ] support 不应在 helplessness 上表现为过强的一步到位下降
- [ ] 高 assist 条件应先改善 `attempt/use`，再逐渐反映到 helplessness
- [ ] enabling support 更容易把 attribution 拉向 `transient / task_specific`
- [ ] 运行：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_state_update.py \
  examples/digital_friction_mvp/tests/test_outcome_model.py \
  examples/digital_friction_mvp/tests/test_experience_memory.py -q
```

---

## 5. 第一阶段不建议继续扩张的内容

下面这些内容在系统里可以保留，但不建议继续往 helplessness 主机制里加：

- `digital_emotion_state` 直接进入 helplessness 核心公式
- `trust_in_apps` 直接和 helplessness 主机制绑定
- 新增更多情绪变量
- 新增更多 profile 特征直接进入 episode-level 更新
- 再增加新的 avoid 分类
- 把 task_value、risk、support、emotion 全都做成并列主项
- 把 `attribution_locus` 直接写成 helplessness 的强主加项
- 第一版就做“全局 digital helplessness across everything”
- 把 attribution 做成很多连续大分数并直接并列入主公式
- 把 `avoid_reason` 和 `attribution` 混成同一个解释字段

第一阶段的核心不是“再变丰富”，而是“先变干净”。

---

## 6. 文件级修改地图

| 文件 | 当前角色 | 第一阶段修改重点 |
| --- | --- | --- |
| `examples/digital_friction_mvp/proto/models.py` | 数据结构定义 | 重命名 `perceived_uncontrollability`；补 `event-level attribution` 事件结构；统一新旧字段；收窄模型表达 |
| `examples/digital_friction_mvp/proto/state_schema.py` | status schema | 增加 task-family 级 attribution summary 所需字段；避免第一版引入过重的全局 attribution 分数 |
| `examples/digital_friction_mvp/proto/state_update.py` | helplessness 主公式 | 移除/弱化 `repetition_delta` 直接作用；让 `event_level_uncontrollability` 成为主驱动；弱化 `support_buffer`；压缩 mastery 规则 |
| `examples/digital_friction_mvp/proto/experience_memory.py` | task-domain memory、help memory、effective helplessness | 重新定义 `task_self_efficacy`、`controllable_success_memory` 的职责；增加 task-family attribution summary；减少 appraisal/emotion 对 helplessness 核心的污染 |
| `examples/digital_friction_mvp/proto/outcome_model.py` | avoid_reason / support_mode 推断 | 维持三分法；让 `support_mode` 更清楚服务于间接修复逻辑 |
| `examples/digital_friction_mvp/proto/attribution_inference.py`（可能新增） | event-level attribution 推断 | 采用 bounded LLM classification + confidence gating 方式判别 `locus / stability / scope / explanation`；最终后果仍由固定规则生效 |
| `examples/digital_friction_mvp/proto/uncontrollability_calibrator.py` | 事件级不可控体验校准 | 正式改名为 `event_level_uncontrollability`；让失败历史更多成为上游线索而不是最终主项 |
| `examples/digital_friction_mvp/proto/agent.py` | 机制串联与日志输出 | 在 `uncontrollability` 之后插入 `infer_event_attribution()`；对齐新字段名；清理日志和状态摘要；避免旧名残留 |
| `examples/digital_friction_mvp/proto/compat.py` | trust / avoidance 更新 | 避免把所有 avoid 统一做同质线性更新 |
| `examples/digital_friction_mvp/tests/test_state_update.py` | 核心更新单测 | 重点重写 |
| `examples/digital_friction_mvp/tests/test_experience_memory.py` | memory 与 mastery 单测 | 根据新 mastery 逻辑补测 |
| `examples/digital_friction_mvp/tests/test_outcome_model.py` | avoid_reason / support_mode 单测 | 继续保留并增强 |
| `examples/digital_friction_mvp/tests/test_attribution_inference.py`（可能新增） | attribution 推断单测 | 保证 `stability / scope / locus` 的事件级推断稳定 |
| `examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py` | uncontrollability 校准单测 | 跟随命名和规则改动更新 |
| `examples/digital_friction_mvp/tests/test_compat_mapping.py` | compat 支路单测 | 需要按新的 avoid 区分逻辑补测 |
| `examples/digital_friction_mvp/attributionmemorytodo.md` | attribution memory 草案 | 同步到正式机制计划，避免 memory 方案与主机制方案脱节 |

---

## 7. 重构完成后的验收标准

如果第一阶段改对了，至少应满足下面这些可观察标准：

### 机制层

- [ ] 同样失败，只有在 `event_level_uncontrollability` 高时 helplessness 才明显上升
- [ ] 同样失败次数，低不可控条件下 helplessness 不会机械上涨
- [ ] `task_self_efficacy` 的高低会改变同样事件的 helplessness 涨幅
- [ ] 同样失败，`stable` attribution 比 `transient` attribution 更难恢复
- [ ] `family_generalizing` attribution 比 `task_specific` attribution 更容易扩散到相近 `task_family`
- [ ] `helpless_avoid` 与 `risk_avoid / low_value_avoid` 在 helplessness 上表现出明显不同
- [ ] `success_self` 的保护效果强于 `success_with_help`
- [ ] `enabling_support` 的长期帮助强于 `substituting_support`

### 代码层

- [ ] 主公式中的并列项明显减少
- [ ] `event-level attribution` 位于 `uncontrollability` 之后、后果展开之前
- [ ] `felt_control` 不再被多处重复计入
- [ ] `support_buffer` 不再是强 direct effect
- [ ] 变量命名统一，不再混用 `perceived_uncontrollability`
- [ ] `avoid_reason` 与 `attribution` 在结构和日志中被清楚区分

### 实验层

- [ ] `high_friction_low_assist` 相比 baseline 仍显著更差
- [ ] `low_friction_high_assist` 相比 baseline 仍显著更好
- [ ] `high_friction_high_assist` 可能改善 attempt/use，但 helplessness 改善不应像“直接减分”那样过强
- [ ] 结果能清楚解释为：环境改变先影响 appraisal 和事件解释，再影响 helplessness
- [ ] with attribution vs without attribution 时，模型对 chronicity / generality 的区分更清楚
- [ ] task-family 级泛化能被观察到，而不是只有单一 helplessness 总分累积

---

## 8. 推荐的测试与实验顺序

### 8.1 单元测试顺序

先跑最小机制测试，再跑整体行为测试：

```bash
python -m pytest examples/digital_friction_mvp/tests/test_state_update.py -q
python -m pytest examples/digital_friction_mvp/tests/test_experience_memory.py -q
python -m pytest examples/digital_friction_mvp/tests/test_outcome_model.py -q
python -m pytest examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py -q
python -m pytest examples/digital_friction_mvp/tests/test_compat_mapping.py -q
```

然后再跑更完整的一组：

```bash
python -m pytest examples/digital_friction_mvp/tests -q
```

### 8.2 实验验证顺序

建议沿用现有两套实验口径：

1. 1-day smoke / tolerance smoke
2. 10-day 3-seed logical clock 平行世界

优先复用已存在的实验基线：

- `examples/digital_friction_mvp/analysis/config_snapshot_stage6_single_1day_logical_clock_smoke_20260408.json`
- `examples/digital_friction_mvp/analysis/config_snapshot_stage6_single_1day_logical_clock_tolerance_smoke_20260408.json`
- `examples/digital_friction_mvp/analysis/config_snapshot_stage6_single_10day_3seed_logical_clock_20260408.json`

实验后继续复用当前分析脚本：

- `examples/digital_friction_mvp/analysis_parallel_worlds.py`
- `examples/digital_friction_mvp/analysis_parallel_paired.py`

### 8.3 最值得补的 ablation

如果后面要写论文，最建议补 6 组对照：

1. outcome-count baseline vs uncontrollability-core
2. with vs without attribution layer
3. attribution logging only vs stability/scope actually affect persistence/generalization
4. with vs without avoid_reason split
5. with vs without controllable_success_memory
6. support direct-buffer vs support indirect-repair

---

## 9. 论文与答辩表达也要同步修改

代码改完以后，论文和答辩里的表述也必须同步收口，不然会出现：

- 代码比文稿复杂
- 文稿比代码简单
- 术语前后不一致

### 论文主图里建议只保留的构件

- `event-level uncontrollability`
- `event-level attribution`
- `task_self_efficacy`
- `avoid_reason`
- `controllable_success_memory`
- `support_mode` 作为间接修复机制
- `task-family generalization` 作为第一版保守后果

### 论文里建议降级为“上游/并行因素”的构件

- `task_value / perceived usefulness`
- `perceived_task_risk / privacy concerns`
- `digital_emotion_state`
- `trust_in_apps`
- 收入、教育、年龄主义、语言障碍等结构性脆弱性
- `attribution_locus` 的强公式化写法（第一版先降级为解释项）

### 最推荐的论文口径

可以统一成下面这句话：

> 数字摩擦事件并不会因为失败本身就线性累积为 helplessness；更关键的是，agent 是否形成事件级的不可控体验。对于更接近人类的 agent，这种不可控体验还会进一步被解释为暂时还是持久、局部还是可泛化，从而影响 helplessness 的持续性与任务家族内扩散。

---

## 10. 推荐的实际执行顺序

如果真的开始改，我推荐按下面顺序做，不要跳：

- [ ] Step 1: 统一命名，先把 `perceived_uncontrollability` 改成 `event_level_uncontrollability`
- [ ] Step 2: 建 attribution state shell，把 event / task-family attribution 结构先落地
- [ ] Step 3: 先改 `state_update.py`，把主公式收窄
- [ ] Step 4: 再改 `experience_memory.py`，把 `task_self_efficacy / mastery / effective_helplessness` 重新分工
- [ ] Step 5: 增加 `infer_event_attribution()`，先让 `stability / scope / locus` 能稳定产生
- [ ] Step 6: 让 `attribution_stability / scope` 进入 persistence / task-family generalization，而不是直接塞进主公式
- [ ] Step 7: 改 `outcome_model.py` 和 `compat.py`，把 `avoid_reason` 和 `support_mode` 的下游真正分流
- [ ] Step 8: 改 `agent.py`、日志、状态输出，清理旧字段残留
- [ ] Step 9: 跑核心单测
- [ ] Step 10: 跑 1-day smoke
- [ ] Step 11: 跑 10-day 3-seed 平行世界
- [ ] Step 12: 重新生成分析表格、结论和论文中的机制图 / 文献-机制对照表

### 10.1 通俗动手版：真正开始改时，最小可行地一处一处改

这一小节是给“真正开始动手”的版本。  
上面的 12 步更像完整工程顺序；下面这 8 步更像“我现在就开始改代码，先改哪一行”的路线。

#### Step A: 先改 `state_update.py`，把失败次数从 helplessness 主公式里拿掉

最先改的函数是：

- `examples/digital_friction_mvp/proto/state_update.py`
- `apply_helplessness_update()`

最先盯住的代码是：

- `rep_delta = repetition_delta(next_failures)`
- `raw_delta = base + rep_delta + uncontrollability + efficacy_loss + control_loss - support_buffer`

最小可行修改：

- 先把 `rep_delta` 从最终 `raw_delta` 里移出去，或降到几乎没有
- 让失败次数更多去影响 `event_level_uncontrollability` 的形成，而不是直接推 helplessness

通俗解释：

- 不是“又失败了一次，所以更无助”
- 而是“这次失败让我更觉得做了也没用，所以更无助”

#### Step B: 再改 `experience_memory.py`，别让 `felt_control` 提前假装成 helplessness

第二个最该盯的函数是：

- `examples/digital_friction_mvp/proto/experience_memory.py`
- `extract_memory_features()`

最先盯住的代码是：

- `control_shift = (50.0 - float(task_appraisal.felt_control)) * 0.04`
- `effective_helplessness = effective_helplessness + task_appraisal_shift`

最小可行修改：

- 先把 `control_shift` 从 `effective_helplessness` 里去掉或大幅弱化
- 让 `felt_control` 主要留在 appraisal 层，去影响：
  - `event_level_uncontrollability`
  - `support_mode`
  - mastery 质量判断

通俗解释：

- `felt_control` 更像“这次局面在不在我掌控里”
- 不应该在事件前就被当成 helplessness 直接加一遍

#### Step C: 再加 `infer_event_attribution()`，但先只做轻量离散标签

第三个最该盯的挂点是：

- `examples/digital_friction_mvp/proto/agent.py`
- 或一个新 helper：`examples/digital_friction_mvp/proto/attribution_inference.py`

最小可行修改：

- 在 `calibrate_uncontrollability()` 之后，增加 `infer_event_attribution()`
- 不做开放式 attribution 生成，而是让 LLM 只在有限标签空间里判别
- 第一版只产出：
  - `event_attribution_locus = self / mixed / situation`
  - `event_attribution_stability = transient / mixed / stable`
  - `event_attribution_scope = task_specific / family_generalizing / mixed`
  - `event_attribution_explanation`
  - `judge_confidence`
- 触发范围先只限于：
  - `failure_after_attempt`
  - `failure_even_with_help`
  - `abandon_midway`
- 如果 `judge_confidence` 过低：
  - 回退到 `mixed / mixed / mixed`
  - 或只记录 explanation，不施加额外 attribution effect

通俗解释：

- 先经历“这次努力没用”
- 再解释“这是我不行、系统太难，还是只是暂时倒霉”

#### Step D: 再改 `compat.py`，让三种 `avoid_reason` 真正分流

第四个最该盯的函数是：

- `examples/digital_friction_mvp/proto/compat.py`
- `apply_compatibility_updates()`

最先盯住的代码是：

- `elif outcome_type == "avoid_without_attempt":`
- `trust_delta = -2.0`
- `avoidance_delta = 4.0`

最小可行修改：

- 给 `apply_compatibility_updates()` 增加 `avoid_reason`
- 不再把所有 `avoid_without_attempt` 都按同一种后果处理

建议第一版先粗分成：

- `helpless_avoid`
  - 明显提高 `avoidance_tendency`
  - 可小幅降低 `trust_in_apps`
- `risk_avoid`
  - 提高 `avoidance_tendency`
  - 但不要自动等于 trust 或 helplessness 崩掉
- `low_value_avoid`
  - 只做很弱的 avoid 更新
  - 尽量不要让 trust 明显下降

通俗解释：

- 前面已经知道“为什么不做”
- 后面就不要再把所有“不做”当成一种回避

#### Step E: 再让 attribution 只管“拖得久”和“扩不扩”，不要回到大杂烩主公式

第五个最该盯的地方是：

- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`

最小可行修改：

- `attribution_stability` 不直接做大正项
- 它主要控制：
  - 恢复速度
  - 残留时长
- `attribution_scope` 第一版只影响相近 `task_family`
- 不做“全局 digital helplessness”
- attribution 的最终后果仍由规则固定映射
- 不让 LLM 直接决定 helplessness 加多少或扩散多远

通俗解释：

- `uncontrollability` 负责“这次伤不伤”
- `attribution` 负责“这个伤会不会拖久、会不会扩散”

#### Step F: 再改 `experience_memory.py`，让 `controllable_success_memory` 真正表示“学会了”

第六个最该盯的函数是：

- `examples/digital_friction_mvp/proto/experience_memory.py`
- `_controllable_success_gain()`

最小可行修改：

- 只让“高质量成功”进入长期保护
- 把长期保护的核心判断收成：
  - 主要自己完成
  - 或 `enabling_support`
  - `felt_control` 高
  - `event_level_uncontrollability` 低

第一版就先坚持一个原则：

- `success_self` 容易积累长期保护
- `success_with_help + enabling_support` 少量积累
- `success_with_help + substituting_support` 尽量不积累长期保护

并且再加一句：

- 高质量 mastery 还应把 attribution 往 `transient / task_specific` 拉回

通俗解释：

- “做成了”不等于“学会了”
- 只有“真正自己掌握了”的成功，才算长期保护

#### Step G: 再改 `state_update.py`，把 `support_buffer` 从直接减分器变成弱效甚至去掉

第七个最该盯的代码仍然在：

- `examples/digital_friction_mvp/proto/state_update.py`

最先盯住的代码是：

- `support_buffer = ...`
- `raw_delta = ... - support_buffer`

最小可行修改：

- 先把 `support_buffer` 大幅弱化，甚至第一版直接置得非常小
- 保留 `support_mode` 区分，不要删
- 把 support 的主要作用转移到：
  - `task_self_efficacy`
  - `felt_control`
  - `expected_help_effectiveness`
  - `controllable_success_memory`
  - `stable / family_generalizing attribution` 的形成概率

通俗解释：

- 帮助最重要的作用，不是直接替 agent 减无助
- 而是让 agent 重新觉得“我有办法”

#### Step H: 最后再收 `effective_helplessness`，不要把所有压力都混进去

最后盯住：

- `examples/digital_friction_mvp/proto/experience_memory.py`
- `effective_helplessness`

最小可行修改：

- 保留与 helplessness 主线更接近的东西：
  - 原始 helplessness
  - 少量 recent failure pressure
  - 少量 self-efficacy pressure
- 把这些更多从 `effective_helplessness` 里分离出去：
  - risk
  - value
  - emotion
  - 太多 appraisal 混合项

通俗解释：

- `effective_helplessness` 不该变成“所有不想做任务的原因总和”
- 它最好更像“当前的无助压力”

### 10.2 如果只想先做最小版本，优先顺序就是这 4 步

如果时间有限，不要试图一次改完所有东西。  
最值得先做的是这 6 步：

- [ ] 先把 `state_update.py` 里的 `rep_delta` 从主公式移出去
- [ ] 再把 `experience_memory.py` 里的 `control_shift` 从 `effective_helplessness` 里移出去
- [ ] 再加 `infer_event_attribution()`，但先只做 `stability / scope / locus` 离散标签
- [ ] 再让 `stability / scope` 只影响 persistence / task-family generalization
- [ ] 再把 `compat.py` 里的 `avoid_without_attempt` 按 `avoid_reason` 分流
- [ ] 最后把 `_controllable_success_gain()` 收成真正的“高质量成功保护”

为什么是这 6 步：

- 第 1 步解决“失败累计模型”问题
- 第 2 步解决“低控制感重复计入”问题
- 第 3 步补上“人类会怎么解释失败”这一层
- 第 4 步解决“为什么有人拖得久、有人只在一类任务上退缩”问题
- 第 5 步解决“所有 non-use 都像 helplessness”问题
- 第 6 步解决“成功率高不等于真正学会”问题

如果只先做这 6 步，论文解释力就已经会提升很多。

---

## 11. 最终建议

这次重构最重要的不是把系统做得更“丰富”，而是把它做得更“干净”。

对于当前课题，第一阶段最值得完成的版本就是：

- 保留现有实验框架
- 不大改整体工程结构
- 把 helplessness 主干收窄，并补一层轻量 attribution layer
- 让理论主线、代码主线和实验主线三者对齐

如果这一步做好了，已经足够支撑一篇更像 CCF-B 风格的机制论文。
