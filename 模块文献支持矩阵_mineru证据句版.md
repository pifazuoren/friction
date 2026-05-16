# 模块-文献支持矩阵（MinerU 行号 + 证据句版）

这份文件的用途是把当前实验机制拆成模块，并为每个模块标注：

- 相关文献；
- MinerU 提取文件路径与行号；
- MinerU 提取句中的原文证据片段；
- 该证据句的中文机制释义；
- 它能支持我们实验设计中的哪一层；
- 它不能支持什么，避免论文中过度声称。

说明：这里没有整段复制 MinerU 里的长句，原因有三个。第一，汇报和论文 claim matrix 更需要“可核查锚点”，也就是 `路径:行号 + 原文片段 + 中文释义`，而不是把原文大段塞进表格。第二，许多 MinerU 行本身很长，一整行可能包含半段论文，直接复制会让矩阵不可读。第三，正式写作时更稳的是引用短原文片段并用中文/英文转述机制含义，完整原句可通过路径和行号回到本地 MinerU 文件核查。

因此，本文件中的“证据句”采用：

```text
MinerU路径:行号 + 原文关键片段 + 中文机制释义
```

如果后续要做附录级 evidence appendix，可以再单独生成一个更长的“逐条原文证据附录”，但正文和汇报建议用当前这种形式。

## 0. 当前实验最稳的三层叙事

| 层级 | 我们的模块 | 最稳表述 |
|---|---|---|
| 经验证据层 | Bayesian gated-lite2 action-outcome posterior | agent 记录在某个 task family 中，采取某个 action 后通常出现什么 outcome。 |
| 核心中介层 | Huys-Dayan-inspired controllability | 从 action-outcome posterior 派生 controllability diagnostic，估计行动是否能可靠地产生有价值结果。 |
| 心理轨迹层 | LLM appraisal、attribution、helplessness、self-efficacy、scope、stream memory | 这些模块描述数字摩擦经历如何被解释、累积、泛化，并影响后续行动倾向。 |

最稳英文口径：

```text
We use action-conditioned outcome posterior learning as the evidence layer,
derive a Huys-Dayan-inspired controllability diagnostic as the central
psychological mediator, and combine it with LLM-based appraisal, attribution,
self-efficacy, scope spillover, and episodic memory mechanisms to simulate
auditable digital helplessness trajectories.
```

不建议声称：

- 我们复现了 Huys & Dayan 2009 的完整模型；
- 我们实现了 full Bayesian RL；
- 我们已经用当前 0513/0514 pilot 证明了 learned helplessness 的因果机制；
- 老年数字服务文献直接给出了我们每个参数的数值。

## 1. 模块证据矩阵

| 模块 | 文献 | MinerU 行号 + 原文证据片段 | 支持我们什么 | 边界 |
|---|---|---|---|---|
| Digital Friction / Task Event | Davis (1989), TAM | `paper/mineruex/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology/auto/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology.md:41` “use or not use” / “usefulness” / “effort” | 数字摩擦不只是客观失败，还会进入 agent 对有用性、难度和努力成本的主观评估。 | TAM 支持技术接受构念，不直接证明 helplessness。 |
| Digital Friction / Task Event | Venkatesh et al. (2003), UTAUT | `paper/mineruex/User Acceptance of Information Technology- Toward a Unified View. /auto/User Acceptance of Information Technology- Toward a Unified View. .md:35` “four core determinants” | 支持 task event 需要包含 performance、effort、social influence、facilitating conditions 等维度。 | UTAUT 是广义 IT 接受模型，不是事件级心理更新公式。 |
| Digital Friction / Older Adult Context | acceptance_of_digital_health_services_among_older_adults_2023 | `paper/mineruex/acceptance_of_digital_health_services_among_older_adults_2023/auto/acceptance_of_digital_health_services_among_older_adults_2023.md:42` “usefulness, self-efficacy, privacy concerns” | 支持老年数字服务场景中同时考虑有用性、效能感、隐私担忧和支持寻求。 | 这是使用意向研究，不直接测 learned helplessness。 |
| LLM Task Appraisal | Davis (1989), TAM | `paper/mineruex/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology/auto/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology.md:257` “subjective appraisal of performance and effort” | 支持让 LLM 先做任务语义评估：难度、收益、风险、控制感都是主观 appraisal。 | 不能说 Davis 支持 LLM 生成评估；它支持 appraisal 构念。 |
| LLM Task Appraisal | Fiore et al. (2014) | `paper/mineruex/Corticolimbic catecholamines in stress: a computational model of the appraisal of controllability/auto/Corticolimbic catecholamines in stress: a computational model of the appraisal of controllability.md:19` “appraisal ... controllable/unavoidable” | 支持把 stress/friction 先经过 controllability appraisal，再影响 active/passive coping。 | 这是压力与神经计算模型，不是老年数字任务模型。 |
| LLM Task Appraisal | Tafet & Ortiz Alonso (2025) | `paper/mineruex/learned_helplessness_and_learned_controllability_review_2025/auto/learned_helplessness_and_learned_controllability_review_2025.md:56` “assessment of available resources” | 支持 appraisal 要综合情境、资源、预测和控制感，而不只是失败次数。 | 该综述是理论整合，不提供仿真参数。 |
| Stream Memory / Episodic Retrieval | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:67` “stored as a memory entry” | 支持长程 agent simulation 中显式记录和检索记忆，用来影响后续 emotion/action。 | LifeSim 支持 memory 机制合理性，不支持我们具体 stream search 一定有效。 |
| Stream Memory / Long-Horizon Coherence | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:158` “memory or emotion modules” | 支持 memory/emotion 模块对长程行为一致性有意义。 | 这是另一个 simulator 的 ablation，不是我们实验结果。 |
| Scope Spillover / Similarity-Based Generalization | Tiggemann & Winefield (1978) | `paper/mineruex/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy)/auto/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy).md:17` “situation similarity” / “generalization” | 支持 scope spillover 不应无边界扩散，而应依赖 task similarity。 | 该实验不是数字任务；支持的是泛化原则。 |
| Scope Spillover / Similarity Boundary | Tiggemann & Winefield (1978) | `paper/mineruex/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy)/auto/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy).md:111` “similar ... dissimilar” | 支持我们把 similar task family 和 dissimilar task family 分开处理。 | 不支持任何具体 similarity 权重数值。 |
| Attribution Scope / Stable-Global-Internal | Abramson et al. (1978) | `paper/mineruex/Learned Helplessness in Humans./auto/Learned Helplessness in Humans..md:7` “stable or unstable, global or specific” | 支持 attribution scope 维度：稳定性、广泛性、内外归因会影响无助泛化。 | 这是理论 reformulation，不是 LLM prompt 设计证明。 |
| Attribution → Future Expectation | Abramson et al. (1978) | `paper/mineruex/Learned Helplessness in Humans./auto/Learned Helplessness in Humans..md:45` “attribution ... subsequent expectations” | 支持 post-outcome attribution 影响未来 noncontingency expectation。 | 不应把归因模块写成已被老年数字场景验证。 |
| LLM Semantic Reference Policy | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:38` “whether they will even try” | 支持行动选择需要参考自我效能、威胁感和 coping 判断，而不是纯规则权重。 | Bandura 支持心理构念，不支持 LLM 输出概率本身。 |
| LLM Semantic Reference Policy | UTAUT | `paper/mineruex/User Acceptance of Information Technology- Toward a Unified View. /auto/User Acceptance of Information Technology- Toward a Unified View. .md:61` “intention or usage as a dependent variable” | 支持 reference policy 可以输出 attempt/help/avoid 这类行为意向，而非只输出情绪分。 | UTAUT 不支持我们的三动作 action set 是唯一正确。 |
| Old Rule Context / Audit / Fallback | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:281` “structured and transparent design” | 支持把旧规则降级为可检查的 context/audit/fallback，有助于透明与审计。 | 这是工程可审计性支撑，不是心理理论支撑。 |
| Bayesian Action-Outcome Posterior | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:533` “action-outcome observations” / “optimal action choice” | 直接支持从 action-outcome observations 推断 action 的未来 outcome，并用于行动选择。 | 我们只是 lightweight posterior，不是 Huys & Dayan 全模型。 |
| Bayesian Action-Outcome Posterior | Tafet & Ortiz Alonso (2025) | `paper/mineruex/learned_helplessness_and_learned_controllability_review_2025/auto/learned_helplessness_and_learned_controllability_review_2025.md:58` “causal associations between actions and outcomes” | 支持 learned control 的基础是区分行动相关结果和行动无关结果。 | 综述支持理论逻辑，不支持 Dirichlet 是唯一形式。 |
| Utility(outcome) / Q_bayes | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:66` “utilities of the outcomes” | 支持 outcome 不只是标签，还要有价值/效用维度。 | 我们的 utility profile 是手写、theory-informed，不是 human-calibrated。 |
| Utility(outcome) / Reward Relevance | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:88` “desirable outcomes” / “controllable reinforcement” | 支持把“有价值结果能否被行动实现”作为关键，而不只是 outcome 是否稳定。 | 不能把我们的 chi-lite 称为原论文的精确 χ。 |
| Evidence Gate / Entropy Gate | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:68` “outcome entropy” | 支持 entropy 是 controllability 相关的核心证据信号。 | confidence gate 和 max-delta 是工程保守设计，不是原文公式。 |
| Evidence Gate / Bounded Shift | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:281` “systematic inspection and auditing” | 支持将 policy change 做成可审计、可检查、低扰动的研究型机制。 | 这支持审计原则，不支持具体 gate threshold。 |
| Huys-Dayan Controllability Metrics | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:60` “contingency, reliability or entropy” | 支持 controllability 不等于 success rate，而要看 action-outcome mapping 的可靠性/熵。 | 我们只能说 inspired by。 |
| Huys-Dayan Controllability Metrics | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:64` “three major notions of control” | 支持三层指标：outcome reliability、achievable outcomes、desirable outcomes。 | 我们的三指标是简化 operationalization。 |
| Huys-Dayan Controllability Metrics | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:78` “dependably achieved” | 支持 action contrast：不同 action 是否能可靠地产生不同 outcome。 | 不能直接用 raw subtype TVD 夸大差异。 |
| Controllability Belief / Generalization | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:92` “taking actions and observing outcomes” | 支持从行动和结果观察中推断 control，并研究其泛化。 | 当前 0513/0514 single-stage 还不是充分 staged causal test。 |
| Controllability Prior / Transfer | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:529` “posterior distribution over ... control parameter” | 支持 family/global controllability memory 的思想：把 control belief 从训练经验带到新任务。 | 我们没有完整 hierarchical Bayesian RL。 |
| Huys-Dayan Modulation | Karvelis & Diaconescu (2022) | `paper/mineruex/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022/auto/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022.md:79` “hopelessness and controllability ... distinct but coupled” | 支持把 action-outcome belief、hopelessness、controllability 区分但耦合，而不是混成一个分数。 | 该文场景是 suicidality，不是老年数字摩擦。 |
| Huys-Dayan Modulation | Karvelis & Diaconescu (2022) | `paper/mineruex/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022/auto/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022.md:136` “modulating stress sensitivity” | 支持低 controllability 更适合作为调制项，而不是直接替代所有心理更新。 | 不支持我们当前参数数值。 |
| Outcome / Event-Level Uncontrollability | Seligman & Maier (1967) | `paper/mineruex/failure-to-escape-traumatic-shock-nnwn6t036k/auto/failure-to-escape-traumatic-shock-nnwn6t036k.md:63` “termination was independent of responding” | 支持 outcome subtype 中区分 controllable failure 与 uncontrollable failure。 | 电击实验不能直接外推数字任务强度。 |
| Outcome / Event-Level Uncontrollability | Maier & Seligman (2016) | `paper/mineruex/learned_helplessness_at_fifty_2016/auto/learned_helplessness_at_fifty_2016.md:19` “nothing one does matters” | 支持 event appraisal 中的 perceived uncontrollability 是 helplessness 的核心近端含义。 | 现代修正认为被动本身未必是学来的；要小心表述。 |
| Helplessness Update | Seligman & Maier (1967) | `paper/mineruex/failure-to-escape-traumatic-shock-nnwn6t036k/auto/failure-to-escape-traumatic-shock-nnwn6t036k.md:61` “degree of control ... determinant” | 支持 helplessness update 不应由 failure count 单独驱动，而应看控制感/contingency。 | 不提供我们的 delta 公式。 |
| Helplessness Update | Abramson et al. (1978) | `paper/mineruex/Learned Helplessness in Humans./auto/Learned Helplessness in Humans..md:35` “Objective noncontingency” | 支持从客观 noncontingency 到 perception、attribution、future expectation、symptoms 的链条。 | 这是理论图式，不是实时仿真算法。 |
| Helplessness Update | Maier & Seligman (2016) | `paper/mineruex/learned_helplessness_at_fifty_2016/auto/learned_helplessness_at_fifty_2016.md:215` “if control is possible” | 支持 learned control / control detection 能维持 active responding。 | 不应说“失败自动产生无助”。 |
| Self-Efficacy / Felt Control | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:36` “outcome expectancy” / “efficacy expectation” | 支持区分“这个 action 会不会有好结果”和“我能不能执行这个 action”。 | 不支持把 self-efficacy 与 outcome utility 混为一个变量。 |
| Self-Efficacy / Persistence | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:40` “how much effort” / “how long” | 支持 self-efficacy 影响 attempt、persistence 和 abandon。 | 仍需数字任务验证。 |
| Self-Efficacy / Mastery Memory | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:56` “Successes raise ... failures lower” | 支持 controllable success / repeated failure 对 task_self_efficacy 的方向性更新。 | 不给具体加减分参数。 |
| Self-Efficacy / Similar Transfer | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:58` “generalization ... most predictably” | 支持 self-efficacy 和 scope spillover 更应在相似任务间泛化。 | 不是所有任务都应强泛化。 |
| Avoid Reason Decomposition | Davis (1989), TAM | `paper/mineruex/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology/auto/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology.md:243` “usefulness ... usage relationship” | 支持 avoid 可能来自低 perceived usefulness，而不是 helplessness。 | TAM 不区分所有 avoid subtype。 |
| Avoid Reason Decomposition | Technophobia Review (2025) | `paper/mineruex/technophobia_in_digital_health_contexts_review_2025/auto/technophobia_in_digital_health_contexts_review_2025.md:25` “may lead to ... avoidance behaviors” | 支持 risk/anxiety-driven avoidance 是独立来源。 | technophobia 不是 helplessness 的同义词。 |
| Avoid Reason Decomposition | factors_influencing_technophobia_chinese_older_patients_2025 | `paper/mineruex/factors_influencing_technophobia_chinese_older_patients_2025/auto/factors_influencing_technophobia_chinese_older_patients_2025.md:35` “will lead individuals to avoid” | 支持老年数字健康技术恐惧可导致 avoidance。 | 横断面研究不能证明 episode-level 因果。 |
| Support / HelperAgent | UTAUT | `paper/mineruex/User Acceptance of Information Technology- Toward a Unified View. /auto/User Acceptance of Information Technology- Toward a Unified View. .md:71` “provision of support for users” | 支持把 support 从世界标量变成 facilitating condition / support process。 | 不支持 helper 话术由 LLM 自由决定真实 outcome。 |
| Support / HelperAgent | Community-Based Intervention (2024) | `paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md:70` “one-to-one coaching” | 支持 HelperAgent 作为一对一帮助过程，而不是静态 assist_level。 | 质性干预研究，不给 outcome probability。 |
| Support / HelperAgent | Community-Based Intervention (2024) | `paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md:181` “needs, preferences, and social circumstances” | 支持 helper response 需要考虑个人需求和生活情境，而不只是给答案。 | 不能说所有帮助都一定提高自我效能。 |
| Enabling vs Substituting Support | digital_anxiety_to_empowerment_older_adults_2026 | `paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md:130` “overly reliant support” | 支持区分 enabling support 与可能强化依赖的 substituting support。 | 这篇是横断面 survey，不是因果实验。 |
| Support Repair Path | digital_anxiety_to_empowerment_older_adults_2026 | `paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md:148` “technical guidance” / “shared experiences” | 支持 support 通过 confidence/readiness 修复，而非简单直接减 helplessness。 | 不排除 support 有残余直接效应。 |
| Multi-Agent Support Ecology | Technophobia Review (2025) | `paper/mineruex/technophobia_in_digital_health_contexts_review_2025/auto/technophobia_in_digital_health_contexts_review_2025.md:168` “social connections” / “supportive social environments” | 支持做 peer/family/community support ecology，而不是只做单 agent。 | 文献支持社会支持重要，不要求自由聊天式多 agent。 |
| Multi-Agent Support Ecology | Community-Based Intervention (2024) | `paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md:191` “family members, peers, or volunteers” | 支持后续 HelperAgent / PeerAgent / VolunteerAgent 的角色设计。 | 当前主实验可先做 HelperAgent，不必一次做完整社会网络。 |
| Staged Learned Helplessness Design | Maier & Seligman (2016) | `paper/mineruex/learned_helplessness_at_fifty_2016/auto/learned_helplessness_at_fifty_2016.md:25` “triadic design” | 支持主实验从 single-stage pilot 转向 staged / yoked-style design，用来隔离 noncontingency。 | 我们不能把 0513/0514 single-stage 当最终因果证据。 |
| Staged Transfer / Recovery | Seligman & Maier (1967) | `paper/mineruex/failure-to-escape-traumatic-shock-nnwn6t036k/auto/failure-to-escape-traumatic-shock-nnwn6t036k.md:77` “prior experience with escapable shock” | 支持 baseline controllable experience、uncontrollable exposure、recovery/transfer 的阶段设计。 | 需要数字任务场景化，不是照搬动物实验。 |
| Expert / Vignette Validation | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:156` “human assessment” | 支持用 human/expert evaluation 检查模拟行为是否可信。 | LLM-as-judge 不能替代所有人类验证。 |
| Reproducibility / Audit Artifact | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:281` “inspection and auditing” | 支持 replay/audit payload、manifest、config snapshot、coverage/leakage 检查。 | 这是研究框架伦理与审计支持，不是心理机制证据。 |

## 2. 哪些模块证据最强

| 证据强度 | 模块 | 说明 |
|---|---|---|
| 强 | action-outcome posterior / controllability / helplessness noncontingency | Huys & Dayan、Seligman & Maier、Maier & Seligman、Abramson 是理论源头级支持。 |
| 强 | self-efficacy / mastery / persistence | Bandura 是源头文献，且与数字老年文献方向一致。 |
| 中高 | older adult digital friction / technophobia / support | TAM、UTAUT、老年数字健康、technophobia review 支持情境变量合理，但多为横断面或综述。 |
| 中 | stream memory / LLM social simulation / audit | LifeSim 支持长程记忆与审计式模拟设计，但不是数字无助理论源头。 |
| 中 | HelperAgent / support ecology | 社区数字干预和社会支持文献支持“帮助过程”重要，但具体 agent protocol 仍是我们的工程设计。 |

## 3. MinerU 完整原句定位卡

这一节是更硬的“完整原句定位卡”。每条都给出 MinerU 文件路径和行号，并保留一个短原文片段。完整原句不在本文件中批量复制；核查时直接打开对应 `MinerU 位置`，跳到该行即可看到 MinerU 提取出的完整原句。

使用方式：

```text
1. 在表中找到证据 ID，例如 E13。
2. 复制 MinerU 位置，例如 paper/mineruex/.../A Bayesian formulation of behavioral control.md:533。
3. 打开该 markdown 文件并跳到第 533 行。
4. 该行就是 MinerU 提取出的完整原句；本表中的“原文证据片段”只是短引锚点。
```

| ID | 对应模块 | 文献 | MinerU 位置 | 原文证据片段 | 中文机制释义 | 可支撑 claim |
|---|---|---|---|---|---|---|
| E01 | Digital friction / task appraisal | Davis (1989) | `paper/mineruex/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology/auto/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology.md:41` | “use or not use an application” | 技术使用/不使用取决于用户对系统有用性和努力成本的判断。 | 数字摩擦需要先进入 subjective appraisal，而不是直接等同于失败。 |
| E02 | Task appraisal | Davis (1989) | `paper/mineruex/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology/auto/Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology.md:257` | “subjective appraisal of performance and effort” | perceived usefulness/ease of use 是主观评估，不一定等于客观系统状态。 | LLM task appraisal 可以作为 subjective appraisal 层。 |
| E03 | Digital friction / support conditions | UTAUT | `paper/mineruex/User Acceptance of Information Technology- Toward a Unified View. /auto/User Acceptance of Information Technology- Toward a Unified View. .md:35` | “four core determinants” | 技术使用由多个核心因素共同决定，不是单一难度变量。 | task event 需要包括 usefulness、effort、social/support 等条件。 |
| E04 | Support / facilitating condition | UTAUT | `paper/mineruex/User Acceptance of Information Technology- Toward a Unified View. /auto/User Acceptance of Information Technology- Toward a Unified View. .md:71` | “provision of support for users” | 支持条件可以是影响系统使用的环境因素。 | HelperAgent 可以被建模为 support process，而非只做 world scalar。 |
| E05 | Older adult digital context | Older adults digital health acceptance (2023) | `paper/mineruex/acceptance_of_digital_health_services_among_older_adults_2023/auto/acceptance_of_digital_health_services_among_older_adults_2023.md:42` | “usefulness, self-efficacy, privacy concerns” | 老年数字服务接受同时涉及有用性、效能感、隐私担忧和支持寻求。 | 数字摩擦任务应包含风险、隐私、效能和支持维度。 |
| E06 | LLM appraisal / controllability appraisal | Fiore et al. (2014) | `paper/mineruex/Corticolimbic catecholamines in stress: a computational model of the appraisal of controllability/auto/Corticolimbic catecholamines in stress: a computational model of the appraisal of controllability.md:19` | “controllable/avoidable” | 压力情境需要被评估为可控/不可控，进而影响 active/passive coping。 | LLM appraisal 中的 perceived control 是机制性变量。 |
| E07 | Action-outcome learning | Tafet & Ortiz Alonso (2025) | `paper/mineruex/learned_helplessness_and_learned_controllability_review_2025/auto/learned_helplessness_and_learned_controllability_review_2025.md:56` | “actions and their consequent results” | 主观控制感建立在行动与结果之间关联的学习之上。 | action-outcome posterior 是 controllability 的证据层。 |
| E08 | Action-outcome contingency | Tafet & Ortiz Alonso (2025) | `paper/mineruex/learned_helplessness_and_learned_controllability_review_2025/auto/learned_helplessness_and_learned_controllability_review_2025.md:58` | “causal associations between actions and outcomes” | adaptive behavior 需要识别哪些结果和自己的行动有关，哪些无关。 | Bayesian gated-lite2 追踪 response-outcome 是否脱钩。 |
| E09 | Scope spillover | Tiggemann & Winefield (1978) | `paper/mineruex/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy)/auto/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy).md:17` | “situation similarity” | learned helplessness 的泛化受情境相似性限制。 | scope spillover 应依赖 task similarity，而不是全域扩散。 |
| E10 | Scope boundary | Tiggemann & Winefield (1978) | `paper/mineruex/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy)/auto/Situation Similarity and the Generalization of Learned Helplessness - Tiggemann and Winefield 1978 (OCR copy).md:111` | “similar ... dissimilar” | 相似任务中出现强 helplessness，非相似任务中泛化不足。 | task-family scope 比 global scope 更稳。 |
| E11 | Attribution scope | Abramson et al. (1978) | `paper/mineruex/Learned Helplessness in Humans./auto/Learned Helplessness in Humans..md:7` | “stable or unstable, global or specific” | 归因的稳定性、广泛性和内外部性决定 helplessness 的范围和持续性。 | attribution/scope 模块有理论来源。 |
| E12 | Attribution chain | Abramson et al. (1978) | `paper/mineruex/Learned Helplessness in Humans./auto/Learned Helplessness in Humans..md:35` | “Objective noncontingency” | 从客观 noncontingency 到感知、归因、未来预期，再到 helplessness symptoms。 | post-outcome state transition 应区分 outcome、attribution、future expectation。 |
| E13 | Bayesian action-outcome posterior | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:533` | “action-outcome observations” | 给定 action-outcome observations，可以形成对各 action 后续 outcome 的预测。 | Bayesian gated-lite2 的 P(outcome\|family, action) 是合理证据层。 |
| E14 | Controllability metrics | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:60` | “contingency, reliability or entropy” | controllability 可以从 action-outcome mapping 的 contingency、reliability、entropy 出发形式化。 | Huys-Dayan-inspired audit 不应只看 success rate。 |
| E15 | Controllable reinforcement | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:88` | “desirable outcomes” | 关键不只是结果稳定，而是有价值结果是否受行动控制。 | chi-lite / reward achievability 是核心指标。 |
| E16 | Controllability generalization | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:92` | “taking actions and observing outcomes” | 个体通过采取行动、观察结果来推断自己是否有控制，并可能泛化。 | family/global controllability memory 有理论依据。 |
| E17 | Utility / value | Huys & Dayan (2009) | `paper/mineruex/A Bayesian formulation of behavioral control/auto/A Bayesian formulation of behavioral control.md:66` | “utilities of the outcomes” | outcome 需要有价值权重，才能从 posterior 转成 action utility。 | Q_bayes 可以解释为 posterior expected utility。 |
| E18 | Learned helplessness noncontingency | Seligman & Maier (1967) | `paper/mineruex/failure-to-escape-traumatic-shock-nnwn6t036k/auto/failure-to-escape-traumatic-shock-nnwn6t036k.md:63` | “independent of their responding” | 无助的关键是结果被学习为与反应无关。 | failure_after_attempt_high_uncontrollability 不是普通失败。 |
| E19 | Control as determinant | Seligman & Maier (1967) | `paper/mineruex/failure-to-escape-traumatic-shock-nnwn6t036k/auto/failure-to-escape-traumatic-shock-nnwn6t036k.md:61` | “degree of control” | 初始经验中的控制程度决定后续逃避/尝试是否受干扰。 | helplessness update 应重视 control，而非 failure count。 |
| E20 | Prior controllable experience | Seligman & Maier (1967) | `paper/mineruex/failure-to-escape-traumatic-shock-nnwn6t036k/auto/failure-to-escape-traumatic-shock-nnwn6t036k.md:77` | “prior experience with escapable shock” | 先前可控经验可以缓冲后续不可控经验。 | staged design 需要 baseline controllable acquisition。 |
| E21 | Learned helplessness core | Maier & Seligman (2016) | `paper/mineruex/learned_helplessness_at_fifty_2016/auto/learned_helplessness_at_fifty_2016.md:19` | “nothing one does matters” | helplessness 的直觉核心是“我做什么都不重要”。 | controllability belief 更适合作为核心心理中介。 |
| E22 | Triadic design | Maier & Seligman (2016) | `paper/mineruex/learned_helplessness_at_fifty_2016/auto/learned_helplessness_at_fifty_2016.md:25` | “triadic design” | 经典实验用可控、不可控 yoked、无刺激三组隔离 noncontingency。 | 0513/0514 single-stage 只能是 mechanism sanity test。 |
| E23 | Learned control | Maier & Seligman (2016) | `paper/mineruex/learned_helplessness_at_fifty_2016/auto/learned_helplessness_at_fifty_2016.md:267` | “bad events will be controllable” | 现代修正强调真正被学习的是未来事件可控。 | 我们应把 controllability 作为核心中介，而不是把失败直接写成无助。 |
| E24 | Self-efficacy vs outcome expectancy | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:36` | “outcome expectancy ... efficacy expectation” | 能否执行行动和行动是否带来结果是两个不同构念。 | task_self_efficacy 不应和 Q_bayes 混在一起。 |
| E25 | Persistence | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:40` | “how long they will persist” | self-efficacy 影响努力投入和坚持时间。 | self-efficacy 可影响 attempt/abandon/persistence。 |
| E26 | Mastery experience | Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md:56` | “Successes raise ... failures lower” | 成功提高 mastery expectation，重复失败降低它。 | controllable success memory 有理论依据。 |
| E27 | Avoidance / technophobia | Technophobia review (2025) | `paper/mineruex/technophobia_in_digital_health_contexts_review_2025/auto/technophobia_in_digital_health_contexts_review_2025.md:25` | “avoidance behaviors” | 技术恐惧可以导致技术回避。 | avoid 可能来自 risk/anxiety，不一定是 helplessness。 |
| E28 | Social networks / support ecology | Technophobia review (2025) | `paper/mineruex/technophobia_in_digital_health_contexts_review_2025/auto/technophobia_in_digital_health_contexts_review_2025.md:168` | “supportive social environments” | 社会连接和支持性环境可缓解 technophobia。 | 多 agent support ecology 有情境依据。 |
| E29 | One-to-one coaching | Community intervention (2024) | `paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md:70` | “one-to-one coaching” | 老年数字学习中，一对一、个性化帮助是现实干预形式。 | HelperAgent 比 assist_level 更接近过程机制。 |
| E30 | Contextualized support | Community intervention (2024) | `paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md:181` | “needs, preferences, and social circumstances” | 帮助需要贴合老人的需求、偏好和社会处境。 | Helper response 应结构化记录帮助质量和自主性。 |
| E31 | Family/peer/volunteer ties | Community intervention (2024) | `paper/mineruex/community_based_digital_intervention_low_income_older_people_2024/auto/community_based_digital_intervention_low_income_older_people_2024.md:191` | “family members, peers, or volunteers” | 家人、同伴、志愿者都可以作为数字学习中的关系性支持。 | 后续 multi-agent 可从 HelperAgent 扩展到 Peer/Volunteer。 |
| E32 | Over-reliant support | Niu et al. (2026) | `paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md:130` | “overly reliant support” | 过度依赖式支持可能传递“我不行”的信号，加剧依赖/焦虑。 | support_style 需要区分 enabling 和 substituting。 |
| E33 | Family support mechanism | Niu et al. (2026) | `paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md:148` | “technical guidance” | 家庭支持可通过技术指导、鼓励和共同经验提高 readiness。 | support 更像修复 self-efficacy/readiness 的过程。 |
| E34 | Digital anxiety avoidance | Niu et al. (2026) | `paper/mineruex/digital_anxiety_to_empowerment_older_adults_2026/auto/digital_anxiety_to_empowerment_older_adults_2026.md:170` | “more likely to avoid digital tools” | 数字焦虑会抑制使用意向并诱发回避。 | avoid_reason 需要区分 anxiety/risk 与 uncontrollability。 |
| E35 | Hopelessness-controllability distinction | Karvelis & Diaconescu (2022) | `paper/mineruex/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022/auto/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022.md:79` | “distinct but coupled” | hopelessness 与 controllability 可区分但耦合。 | Bayesian posterior、C_family、helplessness update 不应混成一个变量。 |
| E36 | Stress sensitivity modulation | Karvelis & Diaconescu (2022) | `paper/mineruex/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022/auto/A Computational Model of Hopelessness and Active-Escape Bias in Suicidality - Karvelis and Diaconescu 2022.md:136` | “modulating stress sensitivity” | controllability 可作为调节压力/负性学习敏感性的变量。 | Huys-Dayan-lite 适合做 modulation，而非完全替代 policy。 |
| E37 | Stream memory | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:67` | “stored as a memory entry” | 长程模拟中，交互信息可被抽象成 memory entry 并用于后续行为。 | stream memory 是经验累积机制，而非直接 outcome 生成器。 |
| E38 | Memory/emotion ablation | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:158` | “memory or emotion modules” | 去掉 memory/emotion 会影响长程行为真实感和一致性。 | 支持保留 stream memory 和心理状态层。 |
| E39 | Auditability | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:281` | “inspection and auditing” | 结构化透明设计有助于系统检查和审计。 | audit payload / manifest / reproducibility artifact 是论文防守点。 |
| E40 | Expert validation | LifeSim (2026) | `paper/mineruex/2603.12152v1/auto/2603.12152v1.md:156` | “human assessment” | 长程 agent simulation 可以结合人工评价来验证轨迹质量。 | expert/vignette validation 是必要补强。 |

## 4. 模块到证据编号速查

| 模块 | 推荐引用证据 ID | 论文里最稳用法 |
|---|---|---|
| Digital friction / task event | E01, E03, E05 | 支持任务输入包含有用性、努力、风险、支持条件。 |
| LLM task appraisal | E02, E06, E07 | 支持先做主观 appraisal，再进入行动选择。 |
| Stream memory | E37, E38, E39 | 支持经验流记录和长程一致性，而不是声称记忆一定改善结果。 |
| Scope spillover | E09, E10, E11 | 支持相似任务间泛化和 attribution scope。 |
| LLM semantic reference policy | E24, E25, E03 | 支持行动倾向与效能、使用意向、任务评估有关。 |
| Bayesian action-outcome posterior | E08, E13, E17 | 支持 action-outcome evidence layer。 |
| Huys-Dayan controllability | E14, E15, E16, E21, E23 | 支持 controllability 是核心中介，且应关注有价值结果是否可控。 |
| Evidence gate / bounded shift | E14, E39 | 支持 entropy/evidence 和 auditability；gate 阈值仍是工程选择。 |
| Helplessness update | E18, E19, E21, E22 | 支持无助来自 noncontingency / low control，而不是失败次数。 |
| Self-efficacy / mastery | E24, E25, E26 | 支持自我效能影响尝试、坚持和 mastery memory。 |
| Avoid reason decomposition | E27, E34, E01 | 支持 avoid 有 anxiety/risk/value 等多来源。 |
| HelperAgent support ecology | E04, E28, E29, E30, E31, E32, E33 | 支持把 support 做成过程、质量和关系，而不只是 scalar。 |
| Staged design | E20, E22 | 支持 baseline/uncontrollable/recovery/transfer 的实验设计。 |
| Expert/vignette validation | E40, E39 | 支持用人工评价和审计 artifact 防守模拟可信度。 |

## 5. 最适合写进论文的 claim

可以写：

```text
The model operationalizes digital helplessness as an auditable trajectory in
which digital friction events are appraised by an LLM-based semantic layer,
action-outcome posteriors provide evidence about response-outcome contingency,
and a Huys-Dayan-inspired controllability diagnostic estimates whether actions
can reliably produce valuable outcomes.
```

也可以写：

```text
Rather than treating non-use as a unitary signal of helplessness, the model
distinguishes avoidance driven by perceived difficulty, risk/anxiety, low
perceived usefulness, and learned uncontrollability.
```

更防守的写法：

```text
The literature supports the theoretical organization of these mechanisms, but
does not determine the numerical update parameters. We therefore treat the
current mechanism as theory-informed and audit-driven, and evaluate it through
coverage, leakage checks, bounded perturbation, ablations, lagged prediction,
and human/expert sanity validation.
```

## 6. 不建议写的 claim

不要写：

```text
We implement the Huys and Dayan model.
```

更稳：

```text
We implement a Huys-Dayan-inspired controllability diagnostic derived from
action-conditioned outcome posteriors.
```

不要写：

```text
The Bayesian module directly models learned helplessness.
```

更稳：

```text
The Bayesian module tracks action-outcome evidence; the derived controllability
diagnostic is used as a mediator/audit signal related to helplessness.
```

不要写：

```text
All avoidance means helplessness.
```

更稳：

```text
Avoidance is decomposed into multiple mechanisms, including risk avoidance,
low perceived usefulness, difficulty/incapability, and uncontrollability-driven
withdrawal.
```

不要写：

```text
Support simply reduces helplessness.
```

更稳：

```text
Support is modeled as a process that can repair self-efficacy, perceived
usefulness, and controllability when it is enabling, but may have weaker or
even adverse effects when it becomes substituting or dismissive.
```

## 7. 当前还缺的文献补强

| 缺口 | 建议补什么 | 原因 |
|---|---|---|
| Balleine & Dickinson (1998) 原文 MinerU 提取 | 补 `Goal-directed instrumental action` 原文 PDF 的 MinerU 解析 | 当前只能通过 Huys & Dayan 和 learned controllability review 的转引支持 goal-directed/action-outcome。 |
| Innovation Resistance Theory / older adult nonuse | 补 Money et al. 2024、Birati & Tzemah-Shahar 2026 或同类 IRT 文献 MinerU | 用来更强支持 avoid_reason 的 usage/value/risk/tradition/image 拆分。 |
| HelperAgent enabling vs substituting | 补 human support / autonomy support / intergenerational learning 文献 | 当前社区干预与 family support 文献支持方向，但还不足以精细区分 support_style。 |
| Expert/vignette validation | 补 LLM social simulation validation 或 human-in-the-loop evaluation 文献 | 用于写评估方法，而不只是工程审计。 |
