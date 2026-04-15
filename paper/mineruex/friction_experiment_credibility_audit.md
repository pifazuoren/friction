# Friction 实验文献审计与可信性分析

## 目的

这份文档基于 `/paper/mineruex` 下已经提取好的论文 `md/json`，回答两个问题：

1. 哪些论文适合直接支持当前 `digital_friction` / `helplessness update` 实验中的每一步更新。
2. 论文与实验结果如何做更稳妥的“可信性分析”，避免把综述、横断面、经典理论和事件级动态规则混写成同一种证据。

这里的判断标准不是“这篇论文是否相关”，而是：

- 是否能支持 `friction -> appraisal -> state update -> behavior` 这条机制链；
- 是否足够定量，能支撑你们的实验叙事；
- 是否可以进入论文正文主证，还是更适合放在 appendix / related work / limitation 里。

---

## 一、全部文献的用途判断

| 文献 | 类型 | 定量强度 | 与 friction 实验的关系 | 建议用途 |
|---|---|---:|---|---|
| `failure-to-escape-traumatic-shock` | 经典动物实验 | 高 | 直接支持“不可控而非失败次数”是关键 | Part 1 主证 |
| `Learned Helplessness in Humans` | 人类 helplessness 理论 reformulation | 中 | 直接支持 appraisal / attribution 层 | Part 1 主证 |
| `learned_helplessness_at_fifty_2016` | 神经科学综述 | 中 | 直接支持“control 是保护项、mastery 有免疫效应” | Part 1/4 主证 |
| `learned_helplessness_and_learned_controllability_review_2025` | 综述 | 中 | 支持 learned controllability、长期保护与 agency | Part 1/4 补强 |
| `Self-Efficacy- Toward a Unifying Theory of Behavioral Change` | 理论文献 | 中 | 直接支持 self-efficacy 影响启动、坚持与恢复 | Part 2 主证 |
| `Perceived Usefulness...` | 经典量化研究 | 高 | 支持 usefulness 强于 ease-of-use，且 ease-of-use 常经 usefulness 起作用 | Part 3/5 理论主证 |
| `User Acceptance of Information Technology- Toward a Unified View` | 大样本整合模型 | 高 | 支持 social influence / facilitating conditions / age moderation | Part 3/5 理论主证 |
| `acceptance_of_digital_health_services_among_older_adults_2023` | 老年数字健康 SEM | 高 | 直接支持 usefulness / self-efficacy / privacy / support 共同作用 | Part 2/3/5 主证 |
| `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024` | 老年数字公共服务 SEM | 高 | 直接支持 anxiety 通过 self-efficacy 和 usefulness 间接影响 intention | Part 2 主证 |
| `factors_influencing_technophobia_chinese_older_patients_2025` | 中国情境回归研究 | 高 | 直接支持 technophobia 与 literacy / self-efficacy / support 的负相关 | Part 2/5 主证 |
| `technophobia_in_digital_health_contexts_review_2025` | 系统综述+Meta | 高 | 直接支持 technophobia 的量级与多维风险因素 | Part 2/3/5 主证 |
| `community_based_digital_intervention_low_income_older_people_2024` | 质性研究 | 低 | 直接揭示低收入老人对 usefulness / relevance / ageism / UI friction 的体验 | Part 3/5 场景补强 |
| `digital_anxiety_to_empowerment_older_adults_2026` | SEM+中介+调节 | 高 | 直接支持 family/social support、anxiety、achievement、intention 的路径 | Part 4/5 主证 |

### 核心结论

- 真正适合支撑你们“定量化实验机制”的核心文献，主要是 8 篇：
  - `failure-to-escape-traumatic-shock`
  - `learned_helplessness_at_fifty_2016`
  - `acceptance_of_digital_health_services_among_older_adults_2023`
  - `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024`
  - `factors_influencing_technophobia_chinese_older_patients_2025`
  - `technophobia_in_digital_health_contexts_review_2025`
  - `digital_anxiety_to_empowerment_older_adults_2026`
  - `Perceived Usefulness...` / `UTAUT` 这两篇经典接受模型文献

- 更适合做“理论主轴”而不是参数证据的，是 4 篇：
  - `Learned Helplessness in Humans`
  - `Self-Efficacy...`
  - `learned_helplessness_and_learned_controllability_review_2025`
  - `community_based_digital_intervention_low_income_older_people_2024`

---

## 二、哪些论文能支持 friction 实验“每一步更新”

下面按你们当前 `helplessness update` 的机制链来对齐。

### 1. `perceived_uncontrollability` 应该是主驱动项，而不是 `failure count`

最适合支持：

- `failure-to-escape-traumatic-shock`
  - 直接证明：关键不是受了多少 shock，而是“shock termination 是否与反应有关”。
- `Learned Helplessness in Humans`
  - 直接证明：人在感知 noncontingency 之后，还会经过 attribution / appraisal。
- `learned_helplessness_at_fifty_2016`
  - 进一步说明：默认反应是 passivity，真正被学到的是 control。
- `learned_helplessness_and_learned_controllability_review_2025`
  - 补强 learned controllability 与 agency 的连续谱。

最适合支撑的写法：

- `friction` 不是 helplessness 的直接加分器；
- `friction` 是上游情境；
- 真正进入长期更新主轴的，应当是 `perceived_uncontrollability`。

### 2. `task_self_efficacy` / `felt_control` 应该进入中间层

最适合支持：

- `Self-Efficacy...`
  - 理论源头，说明效能预期影响启动、努力和坚持。
- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024`
  - 明确显示 technology anxiety 不直接打 intention，而是经 `self-efficacy -> usefulness -> intention` 的完全中介路径起作用。
- `acceptance_of_digital_health_services_among_older_adults_2023`
  - 说明老年样本里 self-efficacy 是 intention 的显著预测变量，并且与 perceived usefulness 正相关。
- `factors_influencing_technophobia_chinese_older_patients_2025`
  - 在中国老年数字健康情境里，self-efficacy 对 technophobia 有显著负向关系。
- `technophobia_in_digital_health_contexts_review_2025`
  - 从 meta 层面说明 self-efficacy 是稳定相关因素，不是偶然结果。

最适合支撑的写法：

- `task_self_efficacy` 是任务域可计算的中速控制感指标；
- `felt_control` 是事件层即时波动；
- `outcome -> helplessness` 之间应先经过这层心理中介。

### 3. `avoid` 必须拆开，不能把所有“不做”都算成 helplessness

最适合支持：

- `Perceived Usefulness...`
  - usefulness 通常比 ease-of-use 更直接影响使用。
- `User Acceptance...UTAUT`
  - social influence / facilitating conditions / age 会改变 adoption 结构。
- `acceptance_of_digital_health_services_among_older_adults_2023`
  - privacy concerns、support、usefulness、自我效能共同作用于 intention。
- `technophobia_in_digital_health_contexts_review_2025`
  - technophobia 包括 fear、tension、privacy/security concerns 多维成分。
- `community_based_digital_intervention_low_income_older_people_2024`
  - 质性上直接看到 low relevance、界面负担、语言障碍、年龄刻板印象，会导致不同形式的不用。

最适合支撑的拆分：

- `helpless_avoid`
  - 来自低控制感、低效能、重复失败。
- `risk_avoid`
  - 来自 privacy / scam / safety / high-risk concern。
- `low_value_avoid`
  - 来自 perceived usefulness 低、任务不相关。

### 4. `controllable_success_memory` 或 mastery-like success 应作为长期保护项

最适合支持：

- `failure-to-escape-traumatic-shock`
  - 早期 escapable shock 可以预防后续 passivity。
- `learned_helplessness_at_fifty_2016`
  - 直接提出 learned control / mastery / immunization 的神经机制。
- `learned_helplessness_and_learned_controllability_review_2025`
  - 把 controllability 作为 resilience 资源来讲。
- `digital_anxiety_to_empowerment_older_adults_2026`
  - achievement 能缓冲 anxiety 对 intention 的负效应，说明“掌握感”是重要保护项。
- `community_based_digital_intervention_low_income_older_people_2024`
  - 反向提醒：被动完成的 intervention 不一定转化为长期 mastery。

最适合支撑的写法：

- 不是所有 success 都一样；
- `success_self` 应明显强于 `success_with_help`；
- 长期变量更适合写成“降低未来负向压力敏感度”的 moderator，而不是固定减项。

### 5. `support` 应主要作为“间接修复机制”，而不是直接回血

最适合支持：

- `acceptance_of_digital_health_services_among_older_adults_2023`
  - family / formal support 直接关联 intention，但 support 对 usefulness / self-efficacy 的路径也明显存在。
- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024`
  - technology anxiety 是经 `self-efficacy` 和 `usefulness` 间接影响 intention 的。
- `digital_anxiety_to_empowerment_older_adults_2026`
  - family support 先降低 digital anxiety，再影响 intention；social influence 也通过 intention 影响 literacy。
- `factors_influencing_technophobia_chinese_older_patients_2025`
  - support 是 technophobia 的保护因素，但不是唯一决定项。
- `community_based_digital_intervention_low_income_older_people_2024`
  - personalized learning 和 social interaction 有帮助，但如果只形成依赖，不一定修复 agency。

最适合支撑的写法：

- `support` 先修复理解、控制感和自我效能；
- 再间接影响 helplessness、attempt 和 recovery；
- 最好进一步区分 `enabling_support` 与 `substituting_support`。

### 6. `trust / privacy / avoidance` 这条链可以单独成立

最适合支持：

- `acceptance_of_digital_health_services_among_older_adults_2023`
  - privacy concerns 对 intention 有显著作用；
- `technophobia_in_digital_health_contexts_review_2025`
  - older adults 的 technophobia 中 privacy/security concern 维度最高；
- `factors_influencing_technophobia_chinese_older_patients_2025`
  - technophobia 本身可作为独立负向结果，而不必全部吸收到 helplessness。

这意味着你们现在把 `trust` 和 `avoidance` 独立记录，是对的，不能都塞回 helplessness 一个桶里。

---

## 三、最值得进正文主证的“定量论文组合”

如果目标是让论文和实验更可信，正文最建议围绕下面这组来组织：

### A. 理论主轴

- `failure-to-escape-traumatic-shock`
- `Learned Helplessness in Humans`
- `learned_helplessness_at_fifty_2016`

作用：

- 说明为什么 `failure/friction` 不是直接主项；
- 说明为什么要引入 `controllability` 与 appraisal；
- 说明为什么 controllable success 能形成保护。

### B. 老年数字场景的定量主证

- `acceptance_of_digital_health_services_among_older_adults_2023`
- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024`
- `factors_influencing_technophobia_chinese_older_patients_2025`
- `technophobia_in_digital_health_contexts_review_2025`
- `digital_anxiety_to_empowerment_older_adults_2026`

作用：

- 说明老年数字场景里 self-efficacy / anxiety / usefulness / privacy / support 都是稳定相关因素；
- 说明 support 常通过中介变量起作用；
- 说明 technophobia / anxiety / intention / literacy 可以构成一条结构化路径。

### C. 接受模型底座

- `Perceived Usefulness...`
- `User Acceptance...UTAUT`

作用：

- 解释为什么要拆 `usefulness`、`social influence`、`facilitating conditions`；
- 解释为什么一些 avoid 不是 helplessness，而是 value/risk/condition 驱动。

### D. 场景补强

- `community_based_digital_intervention_low_income_older_people_2024`

作用：

- 为界面混乱、语言障碍、年龄刻板印象、低相关性这类 friction 提供真实语境；
- 适合放 qualitative support，不适合承担参数依据。

---

## 四、哪些文献“不适合”直接拿来证明事件级更新公式

下面这些都可以引用，但不应被写成“单次事件增量已被文献证明”：

- `Self-Efficacy...`
  - 是强理论，不是 episode-level data。
- `Learned Helplessness in Humans`
  - 是理论 reformulation，不是数字场景定量研究。
- `learned_helplessness_and_learned_controllability_review_2025`
  - 是 narrative review，不是系统定量证据。
- `community_based_digital_intervention_low_income_older_people_2024`
  - 是质性研究，不能推出参数大小。
- `Perceived Usefulness...` 与 `UTAUT`
  - 说明结构很强，但不是老年数字摩擦的直接行为动力学数据。

---

## 五、论文和实验需要怎样写“可信性分析”

这一部分最关键。

### 1. 你们真正能声称什么

可以声称：

- 动态机制是 `theory-grounded` 的；
- 路径顺序和变量层级受文献约束；
- 方向性来自经典理论 + 老年数字场景实证 + 接受模型；
- 事件级规则和参数规模经过 simulation calibration；
- 最终可信性靠 paired comparison、ablation、sensitivity 和人工锚定共同建立。

### 2. 你们不应声称什么

不要写成：

- “文献证明一次高 friction 事件会让 helplessness 增加多少”
- “横断面 SEM 系数可以直接翻译成代码中的 event delta”
- “LLM agent 的状态量等同于真实人类心理状态”

### 3. 最稳的可信性分析框架

建议在论文里明确分四层：

- `理论可信性`
  - 机制主轴是否与 learned helplessness / learned controllability 一致。
- `结构可信性`
  - self-efficacy、privacy、support、usefulness、avoid 类型等路径是否与老年数字场景实证一致。
- `实验可信性`
  - 同 seed 配对 world comparison、ablation、sensitivity 是否支持方向稳定。
- `解释可信性`
  - 对 `avoid_reason`、部分 appraisal 中间变量做人工复核或文本锚定。

### 4. 对你们当前实验最需要补的四项验证

- `paired-seed world comparison`
  - 同一个 seed 比较 `baseline_low_friction / high_friction_low_assist / high_friction_high_assist / low_friction_high_assist`
- `ablation`
  - 至少做 `No-Uncontrollability`、`No-Efficacy-Mediator`、`No-Avoid-Split`、`No-Control-Memory`、`Direct-Support-Only`
- `sensitivity analysis`
  - 扰动 `perceived_uncontrollability` 权重、`task_self_efficacy` 权重、support repair 强度、memory 衰减常数
- `human-facing anchoring`
  - 抽样复核 `avoid_reason` 和若干 stage-end interview / appraisal 结果

### 5. 当前实验最适合报告的主指标

- `AttemptRate`
- `SuccessRate`
- `HelplessDelta`
- `TrustDelta`
- `AvoidanceDelta`

如果要和文献更紧密对接，再建议增加两类中间指标：

- `PerceivedUncontrollability` 的 stage 平均值 / 分桶结果
- `task_self_efficacy` 的 stage 前后变化

---

## 六、直接可用于论文写作的总判断

最简洁的结论是：

1. `/paper/mineruex` 里的文献，已经足够支持你们把 `friction` 实验从“结果驱动”改写成“controllability appraisal 驱动”的机制模型。
2. 真正强的定量证据，不在于直接给出事件级参数，而在于稳定支持以下结构：
   - `friction -> anxiety/uncontrollability`
   - `self-efficacy / usefulness / support -> appraisal`
   - `appraisal -> intention / avoidance / technophobia`
   - `achievement / controllable success -> protection`
3. 你们论文最大的风险不是“没有文献”，而是“把不同层级的证据写成同一种证明”。
4. 因此，论文里最重要的不是再堆更多相关论文，而是把证据层级和验证逻辑讲清楚。

---

## 七、建议的写作口径

建议在论文方法或 limitation 里使用类似表述：

> We do not claim that existing cross-sectional or review-based studies directly identify event-level updates. Instead, we use them to constrain mechanism ordering, mediator placement, avoidance decomposition, and plausible relative strength. Event-level rules are then operationalized as theory-grounded and literature-constrained simulation mechanisms, whose credibility is evaluated through paired-seed comparisons, ablation studies, sensitivity analysis, and targeted human-facing validation of selected intermediate variables.

对应中文可以写成：

> 我们并不主张现有横断面研究、综述或经典理论能够直接识别事件级更新幅度。相反，这些文献主要用于约束机制顺序、中介位置、回避行为拆分方式以及相对强弱边界。事件级动态规则是在上述约束下进行的 theory-grounded、literature-constrained 操作化设计，其可信性进一步通过 paired-seed 对照、消融实验、敏感性分析以及对部分中间变量的人工锚定来检验。

