# helplessness update support

这份文件按“论文可回查”的标准，整理 [helplessnessupdatetodo.md](/Users/pifazuoren/Downloads/AgentSociety-main/helplessnessupdatetodo.md) 里引用到的外部论文。每篇都说明：

- 它在 todo 里到底支持哪一层意思。
- 原文里哪一句最能直接支撑这层意思。
- 这句话为什么能支持当前机制设计。
- 这篇文献的使用边界在哪里，哪些话不能从它身上过度推出。

说明：

- 为了便于核查，这里尽量保留“原文句子级”证据。
- 为避免大段复制原文，这里只放短引；如果需要更长上下文，请回到对应 PDF 或官方网页继续核对。
- “原文出处”尽量细化到“哪一段”，例如 `abstract 第1段`、`discussion 第2段`，少数无法稳定编号的网页条目则写成“讨论某主题的那一段”。
- 重复短标题已合并。例如 `Barriers to and Facilitators of Older People’s Engagement With Web-Based Services` 与带副标题的版本视为同一篇。

## P0. 经典源头文献补充

这一组不是替代下面那些“老年人数字服务场景”论文，而是补最上层的理论源头。如果后面论文要按 CCF-B 的标准来写，这几篇最好放在 `theoretical background`、`construct definition` 或 `model justification` 里，用来回答两个问题：

- 你们的核心变量最早从哪里来
- 为什么 `controllability / self-efficacy / usefulness / acceptance` 要分开讲，而不是混成一个总分

### P0-1. Failure to Escape Traumatic Shock

- 在 todo 里主要支持：Stage 1 和 Stage 4 背后的最源头逻辑，也就是 helplessness 的起点不是“失败次数多”，而是个体学到了“结果和自己的反应脱钩”；同时，先有 controllable experience 会影响后续表现。
- 原文短引：`"shock termination was independent of responding"`
- 原文短引：`"prevented interference with later responding"`
- 原文出处：第一句来自 `abstract 末句`；第二句来自 `abstract` 中讨论 `initial experience with escape in the shuttle box` 的那一句。
- 本地文件：暂无；在线来源：[PubMed 元数据](https://pubmed.ncbi.nlm.nih.gov/6032570/)、[ResearchGate 摘要预览（页面注明 preview provided by APA）](https://www.researchgate.net/publication/17152847_FAILURE_TO_ESCAPE_TRAUMATIC_SHOCK)
- 这两句具体支持什么：第一句几乎就是你们 Stage 1 的原点。它告诉我们，真正让后续逃避/放弃发生的，不是“出错过”本身，而是主体学到“我怎么做都不会改变结果”。第二句则补了 Stage 4 很关键的一层：如果个体先经历过可控、能生效的行动，这种经历会对后续不可控处境产生保护作用，所以把 `controllable_success_memory` 作为长期保护痕迹，不是凭空造变量。
- 使用边界：这是动物电击范式中的经典起点文献。它最适合支持“response-outcome contingency”这条理论主线，不适合直接外推到老年人数字服务，更不能直接拿来给你们事件级更新公式定量。

### P0-2. Learned Helplessness in Humans: Critique and Reformulation

- 在 todo 里主要支持：Stage 1、Stage 3 和 Stage 6 背后的“不是所有失败都会同样伤人”的逻辑，尤其是为什么 `perceived_uncontrollability` 之后还需要一层“主观解释 / 归因层”。
- 原文短引：`"once people perceive noncontingency, they attribute their helplessness to a cause"`
- 原文短引：`"chronic or acute, broad or narrow"`
- 原文出处：第一句来自 `abstract` 中讨论 reformulation 的那一段；第二句来自同一段后半部分，说明 attribution 会影响 helplessness 的持续时间和泛化范围。
- 本地文件：暂无；在线来源：[DOI 页面](https://doi.org/10.1037/0021-843X.87.1.49)、[ResearchGate 摘要预览（页面注明 preview provided by APA）](https://www.researchgate.net/publication/22492163_Learned_helplessness_in_humans_Critique_and_reformulation)
- 这两句具体支持什么：第一句告诉我们，“感到不可控”之后，个体还会继续解释这件事到底意味着什么。这正是为什么你们不能把所有 failure 一律翻译成同样的 helplessness 增量。第二句更直接，它说明 helplessness 可以是狭窄的、任务特定的，也可以是广泛和持久的。因此，Stage 3 里把 `avoid` 拆开、把 task/domain 解释层保留下来，是有经典人类 helplessness 理论基础的。
- 使用边界：这篇是人类 helplessness 的理论 reformulation，不是老年数字服务论文，也不是纵向行为追踪研究。它最强的是“概念分层”和“归因逻辑”，不提供你们场景里的系数。

### P0-3. Learned Helplessness at Fifty: Insights from Neuroscience

- 在 todo 里主要支持：Stage 1、Stage 4 和 Stage 6 的理论升级版，也就是 helplessness 不应被写成“学会了被动”，而更应写成“默认被动反应 + 学会控制后的抑制与保护”。
- 原文短引：`"Passivity in response to shock is not learned."`
- 原文短引：`"This passivity can be overcome by learning control"`
- 原文出处：两句都来自 `abstract 第1段`，分别位于中段和后半段。
- 本地文件：[learned_helplessness_at_fifty_2016.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/learned_helplessness_at_fifty_2016.pdf)；在线来源：[PubMed](https://pubmed.ncbi.nlm.nih.gov/27337390/)、[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC4920136/)
- 这两句具体支持什么：第一句非常适合你们在论文里纠正“无助 = 失败计数”的旧写法。它把重点从“学会无助”转成了“默认被动 + 缺少控制检测”。第二句则直接支持 Stage 4 的长期保护链，也就是 controllability 不是一次性好运，而是可以被学习、并在以后抑制 helplessness 的资源。对于 `controllable_success_memory`，这篇比一般综述更像真正的理论源头。
- 使用边界：这是神经科学视角下的高层理论综述。它非常适合做机制合法性论证，但仍然不是老年数字服务中的直接场景证据。

### P0-4. A Guide to Constructs of Control

- 在 todo 里主要支持：Stage 2、Stage 4，以及论文 `Mechanism Section` 里对 `felt_control`、`task_self_efficacy`、`perceived_uncontrollability`、`controllable_success_memory` 的拆分说明。
- 原文短引：`"objective, subjective, and experiences of control"`
- 原文短引：`"agents, means, and ends of control"`
- 原文出处：两句都来自 `abstract 第1句`，分别是该句提出的两组基础区分。
- 本地文件：暂无；在线来源：[PubMed 摘要页](https://pubmed.ncbi.nlm.nih.gov/8831161/)、[ResearchGate 摘要预览](https://www.researchgate.net/publication/14374538_A_Guide_to_Constructs_of_Control)
- 这两句具体支持什么：这篇最重要的作用，不是告诉你哪条路径系数更大，而是提醒“control”不是一个单层构念。第一组区分说明，客观控制条件、主观判断、以及控制体验不应混写；第二组区分说明，主体、手段和结果的关系也要分开讨论。对你们来说，这正好支持为什么 `perceived_uncontrollability`、`felt_control`、`task_self_efficacy`、`controllable_success_memory` 不能被压成一个大变量：它们对应的是不同层级、不同时间尺度、不同功能位置的 control-related constructs。
- 使用边界：这是概念整理论文，不是老年数字服务研究，也不提供任何事件级或路径系数。它最适合支撑“变量拆分为何合理”，不适合用来证明哪条机制在你们场景里效应更强。

### P0-5. Self-Efficacy: Toward a Unifying Theory of Behavioral Change

- 在 todo 里主要支持：Stage 2、Stage 4 和 Stage 5 中 `task_self_efficacy` 的概念底座，也就是为什么低效能感会影响尝试、坚持、恢复，而 mastery experience 会留下后续保护。
- 原文短引：`"expectations of personal efficacy determine whether coping behavior will be initiated"`
- 原文短引：`"through experiences of mastery, further enhancement of self-efficacy"`
- 原文出处：两句都来自 `Author Abstract`；第一句是该摘要第2句前半段，第二句是该摘要第2句后半段。
- 本地文件：暂无；在线来源：[PubMed 元数据](https://pubmed.ncbi.nlm.nih.gov/847061/)、[Stanford Center on Longevity 作者摘要页](https://longevity.stanford.edu/self-efficacy-toward-a-unifying-theory-of-behavior-change/)
- 这两句具体支持什么：第一句直接支持你们把 `task_self_efficacy` 放在“是否继续尝试、是否遇阻后还能坚持”的中介位置，而不是把它当成一个装饰性背景变量。第二句则解释了为什么 Stage 4 里“自己可控地做成过一次”比“被带着完成一次”更值得进入长期记忆项，因为真正提升效能感的是 mastery experience。
- 使用边界：这里的短引来自 Stanford 页面整理的作者摘要，不是期刊官网全文页；PubMed 仅提供元数据且无摘要。这篇最适合支撑 `self-efficacy` 的基础定义和作用方向，不适合单独证明老年数字任务中的具体效应大小。

### P0-6. Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology

- 在 todo 里主要支持：Stage 3 以及论文层面的 `construct definition`，也就是为什么 `perceived usefulness` 不该被塞进 helplessness，而应单独作为“价值/是否值得做”的中段变量。
- 原文短引：`"fundamental determinants of user acceptance"`
- 原文短引：`"usefulness had a significantly greater correlation with usage behavior"`
- 原文出处：第一句来自 `Abstract 第1段前半段`；第二句来自 `Abstract` 后半段总结两项研究结果的那一段。
- 本地文件：暂无；在线来源：[MIS Quarterly 官方文章页](https://misq.umn.edu/perceived-usefulness-perceived-ease-of-use-and-user-acceptance-of-information-technology.html)、[AIS eLibrary 条目页](https://aisel.aisnet.org/misq/vol13/iss3/6/)
- 这两句具体支持什么：第一句说明 `perceived usefulness` 和 `perceived ease of use` 从一开始就不是“杂项感受”，而是技术接受的核心构念。第二句更关键，它告诉我们 usefulness 往往比 ease of use 更贴近后续 usage，因此你们在 Stage 3 中拆出 `low_value_avoid` 是有经典 TAM 源头根据的，而不是看到几篇近年老年论文后临时起意。
- 使用边界：这篇是一般 IT 接受模型的源头文献，不是 helplessness 文献。它最适合支持“为什么 usefulness 值得单列”，不适合用来证明 helplessness 的更新机制。

### P0-7. User Acceptance of Information Technology: Toward a Unified View

- 在 todo 里主要支持：Stage 3、Stage 5 以及论文 related work 中“acceptance / intention / facilitating conditions 不能简单并入 helplessness”的理论层说明。
- 原文短引：`"four core determinants of intention and usage"`
- 原文短引：`"understand the drivers of acceptance"`
- 原文出处：第一句来自 `abstract` 中介绍 UTAUT 形成结果的那一段；第二句来自 `abstract` 最后一段前半句，讨论模型帮助理解 adoption drivers 的地方。
- 本地文件：暂无；在线来源：[AIS eLibrary 官方摘要页](https://aisel.aisnet.org/misq/vol27/iss3/5/)、[MIS Quarterly 官方文章页](https://misq.umn.edu/user-acceptance-of-information-technology-toward-a-unified-view.html)
- 这两句具体支持什么：第一句支持你们在论文里把 intention / usage 写成独立结果层，而不是把所有“不用”都往 helplessness 里塞。第二句则支持 Stage 5 的一个关键判断：支持、培训、组织条件之所以重要，不是因为它们神奇地“直接回血”，而是因为它们改变了 acceptance 的驱动因素，所以 support 更像“修复中介层”的条件，而不是万能减分器。
- 使用边界：UTAUT 是广义 IT 接受模型，场景主要是组织和制度化技术采用。它能帮助你们把 acceptance 变量讲清楚，但不能单独支撑老年人数字服务中的 episode-level 心理动态。

## 1. Exploring Large Language Model Agents for Piloting Social Experiments

- 在 todo 里主要支持：Stage 0 里把 LLM 仿真组织成“有参与者、有干预、有数据采集”的结构化社会实验，而不是把它当成一次性 prompt 试玩。
- 原文短引：`"This work provides the first framework for designing LLM-driven agents to pilot social experiments."`
- 原文出处：`abstract 第1段末句`；同一段前半段还写到 `behavioral, survey, and interview data`。
- 本地文件：[LLM_Agents_for_Piloting_Social_Experiments.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/LLM_Agents_for_Piloting_Social_Experiments.pdf)
- 这句话具体支持什么：它直接支持“LLM agent 可以被组织成实验参与者，且实验不是只看最终回答，而是要连行为、问卷、访谈数据一起设计”。这正好支撑 todo 里 Stage 0 的实验化组织思路。
- 使用边界：它支持的是方法框架，不直接规定 `freeze baseline`、`multi-seed baseline`、日志字段清单或你们的心理变量更新式。

## 2. AgentSociety: Large-Scale Simulation of LLM-Driven Generative Agents

- 在 todo 里主要支持：Stage 0 里“既然已经是结构化社会仿真系统，就应保留中间状态、任务过程和实验条件”的判断。
- 原文短引：`"These four issues serve as valuable cases for assessing AgentSociety’s support for typical research methods – such as surveys, interviews, and interventions."`
- 原文出处：`abstract 第1段后半段`，也就是列举 `surveys, interviews, and interventions` 的那一段。
- 本地文件：[AgentSociety_2025_Large-Scale_Simulation_of_LLM-Driven_Generative_Agents.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/AgentSociety_2025_Large-Scale_Simulation_of_LLM-Driven_Generative_Agents.pdf)
- 这句话具体支持什么：这句话不是在讲某个具体心理机制，而是在讲“系统应该支持什么样的研究动作”。它支持的是你们把仿真搭成可做 survey、interview、intervention 的实验平台，而不是单轮问答脚本。
- 使用边界：它更像系统/平台论文，不能直接拿来证明 `helplessness`、`self-efficacy`、`felt_control` 的更新规则。

## 3. Using Large Language Models to Simulate Multiple Humans and Replicate Human Subject Studies

- 在 todo 里主要支持：Stage 0 中“LLM 人群模拟要警惕系统性偏差，因此 baseline 和中间变量都要留痕”的做法。
- 原文短引：`"A TE requires simulating a representative sample of participants in human subject research."`
- 原文短引：`"A TE can also reveal consistent distortions in a language model’s simulation of a specific human behavior."`
- 原文出处：两句都来自 `abstract 第1段`，分别位于该段前半部分和中段。
- 本地文件：[using_llms_to_simulate_multiple_humans_2022.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/using_llms_to_simulate_multiple_humans_2022.pdf)
- 这两句具体支持什么：第一句支持你们不要只看单个 agent 的“像不像”，而要看一组 agent 的分布与条件差异。第二句支持你们保留 baseline 和中间变量，因为 LLM 可能会稳定地“歪向某个方向”，不能只看最终表面结果。
- 使用边界：它支持的是“分布比较”和“偏差警惕”，不直接给出你们模型里的参数大小。

## 4. Learned helplessness and learned controllability: from neurobiology to cognitive, emotional and behavioral neurosciences

- 在 todo 里主要支持：Stage 1 到 Stage 6 的理论主轴，也就是 `helplessness` 的核心不是“失败次数”，而是“行动和结果是否脱钩”；同时，过去的 controllability 经验可能带来保护作用。
- 原文短引：`"In 'learned helplessness' an organism learns that outcomes are independent of their actions."`
- 原文短引：`"Conversely the sense of control offers the ability to effectively respond to environmental stressors."`
- 原文出处：两句都来自 `conclusion 第1段`。
- 本地文件：[learned_helplessness_and_learned_controllability_review_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/learned_helplessness_and_learned_controllability_review_2025.pdf)
- 这两句具体支持什么：第一句是 todo 里“不要把 helplessness 当失败计分器”的最直接理论依据。它说清楚了真正关键的是 `outcome independence`，也就是“我做不做都没区别”。第二句则支持你们把 `controllability` 看成一个可学习、可保护的资源，因此 `controllable_success_memory` 作为操作化变量是有理论基础的。
- 使用边界：这是理论综述，不是老年数字服务的直接场景证据。它最适合支撑机制主轴，不适合单独支撑老年数字服务里的具体系数。

## 5. Older adults’ self-perception, technology anxiety, and intention to use digital public services

- 在 todo 里主要支持：Stage 2 和 Stage 6 的中介链与循环解释，也就是 technology anxiety 不直接决定使用意图，而是通过 `self-efficacy / perceived usefulness` 这类中介层发生作用。
- 原文短引：`"Technology anxiety indirectly affects the intention to use digital public services."`
- 原文短引：`"The relationship between negative self-perception of aging and technological anxiety might form a vicious circle."`
- 原文出处：第一句来自 `abstract 第1段后半段`；第二句来自 `discussion` 中讨论 `negative self-perception of aging` 与 `technology anxiety` 可能形成恶性循环的那一段。
- 本地文件：[older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf)
- 这两句具体支持什么：第一句支持你们把 `task_self_efficacy` 和 `perceived usefulness` 放在机制中段，而不是把“焦虑 -> 放弃”写成一跳直达。第二句支持 Stage 6 的 loop 写法，也就是负面自我认知、焦虑、减少接触机会之间可能会互相强化。
- 使用边界：这篇是横断面 SEM。它直接支持“中介结构存在”和“循环可能存在”，但不能直接验证你们 episode-level 的动态更新公式。

## 6. Factors that influence technophobia in Chinese older patients with ischemic stroke: a cross-sectional survey

- 在 todo 里主要支持：Stage 2 和 Stage 5 中，`self-efficacy`、`social support`、`e-health literacy` 是 technophobia 的重要相关因素，因此你们把这些变量放入长期脆弱性结构是有邻近场景根据的。
- 原文短引：`"electronic health literacy, self-efficacy, and social support were the main influencing factors of technophobia"`
- 原文短引：`"the research can only reveal the correlations between variables"`
- 原文出处：第一句来自 `abstract 第1段结果概括处`；第二句来自 `limitations` 中讨论横断面设计局限的那一段。
- 本地文件：[factors_influencing_technophobia_chinese_older_patients_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/factors_influencing_technophobia_chinese_older_patients_2025.pdf)
- 这两句具体支持什么：第一句支持你们不要把 technophobia 或 helplessness 写成单一来源，它通常和效能感、识读能力、支持系统一起出现。第二句提醒你们：这篇文献适合拿来支持“变量应该入模”，但不适合拿来支持强因果或更新方向。
- 使用边界：样本是“卒中老年患者 + 数字健康”语境，属于邻近支持，不宜直接外推到所有数字公共服务场景。

## 7. Technophobia in digital health contexts: A systematic review and meta-analysis with a focus on older adults

- 在 todo 里主要支持：Stage 2 中“low self-efficacy 是老年 technophobia 的稳定风险因素之一”，所以效能感更适合被放在脆弱性结构中，而不只是临时情绪变量。
- 原文短引：`"At the behavioral level, low self-efficacy, limited technology use, and infrequent Internet use emerged as significant risk factors."`
- 原文出处：`conclusion 第1段`。
- 本地文件：[technophobia_in_digital_health_contexts_review_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/technophobia_in_digital_health_contexts_review_2025.pdf)
- 这句话具体支持什么：它直接告诉我们，`self-efficacy` 不是边缘变量，而是风险结构的一部分。这和你们在 todo 里把 `task_self_efficacy` 放在中速变化层、长期脆弱性层之间是相符的。
- 使用边界：它支持“self-efficacy 是重要相关因素”，但不能把文中的总体相关范围硬解释成 self-efficacy 单一变量的效应大小。

## 8. The mechanism of digital feedback on health information anxiety among older adults: information processing self-efficacy as a mediating variable

- 在 todo 里主要支持：Stage 2 和 Stage 5 中“外部支持/反馈不是只起安抚作用，它还会通过 self-efficacy 中介改变负面状态”；同时，support quality 需要单独建模。
- 原文短引：`"the relationship between digital feedback and health information anxiety was partially mediated by information processing self-efficacy."`
- 原文短引：`"inappropriate digital feedback ... may exacerbate health information anxiety among older adults."`
- 原文出处：第一句来自 `results` 中报告中介分析结果的那一段；第二句来自 `conclusion 第1段后半段`。
- 本地文件：[digital_feedback_health_information_anxiety_self_efficacy_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/digital_feedback_health_information_anxiety_self_efficacy_2025.pdf)
- 补充核查文本：[extracted_text_from_redownloaded_pypdf.md](/Users/pifazuoren/Downloads/AgentSociety-main/papers/digital_feedback_health_information_anxiety_self_efficacy_2025/extracted_text_from_redownloaded_pypdf.md)
- 这两句具体支持什么：第一句直接支撑 `support / feedback -> self-efficacy -> anxiety` 这条中介链。第二句说明“有反馈”不等于“好反馈”，所以你们在模型里把 `support_quality` 拆出来是合理的。
- 使用边界：这篇同时报告了直接效应和中介效应，因此它支持“以间接修复为主”，但不支持“只能通过中介起作用”。

## 9. Barriers to and Facilitators of Older People’s Engagement With Web-Based Services: Qualitative Study of Adults Aged >75 Years

- 在 todo 里主要支持：Stage 3 和 Stage 5 中“avoid 有不同来源”“support quality 需要单独建模”，尤其是 fear/risk/offline preference 和耐心支持这两条。
- 原文短引：`"The participants also valued the one-to-one support given to them but stressed that this needed to be ongoing support."`
- 原文短引：`"narrow use and restricted activity on the web"`
- 原文出处：第一句来自官方网页 `discussion` 中讨论一对一支持需要持续进行的那一段；第二个短引来自 `abstract 第1段` 中概括 `narrow use and restricted activity on the web` 的那一段。
- 本地文件：[older-web-based-services.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/papers/digital-friction-older-adults/older_adults/older-web-based-services.pdf)
- 这两处原文具体支持什么：第一句说明支持不是“给一次帮助就结束”，而是需要持续、耐心、可重复，这正对应你们的 `support_quality` 和 `support_reliability_memory`。第二个短引说明回避不只是“完全不用”，还可能表现为“只敢做最窄的一部分”，这支持 `avoid_reason` 的细分。
- 使用边界：这是定性研究，最适合支撑机制现象和变量拆分，不适合直接给更新式参数赋值。

## 10. Acceptance of digital health services among older adults: Findings on perceived usefulness, self-efficacy, privacy concerns, ICT knowledge, and support seeking

- 在 todo 里主要支持：Stage 3 和 Stage 5 中“使用意图不是 helplessness 的简单外壳”，以及“support 既有直接作用，也会通过 `SE / PU` 间接起作用”。
- 原文短引：`"higher perceived usefulness and self-efficacy, more perceived family and formal support ... contributed to a higher intention to use digital health services"`
- 原文短引：`"perceived usefulness was the dominant factor in the model"`
- 原文出处：两句都来自 `discussion 第1段总结模型结果的部分`；路径系数细节来自正文 `results` 中汇报 path model 的那一段。
- 本地文件：[acceptance_of_digital_health_services_among_older_adults_2023.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/acceptance_of_digital_health_services_among_older_adults_2023.pdf)
- 这两句具体支持什么：第一句说明 family/formal support、self-efficacy、usefulness 都在同一结构里起作用，因此 `support` 不能被写成单独一个万能负号。第二句说明 `perceived usefulness` 很强，这支持你们把一部分 avoid 单独解释成 `low_value_avoid`，而不是一律解释成 helplessness。
- 使用边界：这篇直接支持的是“结构上有 direct + indirect paths”，但你们在 todo 里进一步写成“以间接修复为主”，仍然是模型层归纳，不是作者原句。

## 11. Older adults' digital technology experiences: a qualitative study

- 在 todo 里主要支持：Stage 3 和 Stage 5 中“older adults 不是同质人群”“support 会影响 autonomy 还是 dependence”，因此不要把所有负面使用状态都归结成 helplessness。
- 原文短引：`"Older persons can therefore not be seen as a homogeneous group in their use of and feelings related to digital technology."`
- 原文短引：`"Otherwise, older persons may become more dependent on others in society."`
- 原文出处：第一句来自 `abstract 第1段结尾`；第二句来自 `conclusion 第1段` 中讨论缺乏支持会增加依赖的那一段。
- 本地文件：[older-digital-technology-experiences.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/papers/digital-friction-older-adults/older_adults/older-digital-technology-experiences.pdf)
- 这两句具体支持什么：第一句支持你们把回避、犹豫、偏好差异拆开看，而不是假设所有老人都走同一条“失败 -> helplessness”通道。第二句说明 support 的问题不只是“有没有帮助”，而是帮助之后个体是更能自主，还是更依赖他人。
- 使用边界：这是定性研究，适合支撑异质性和依赖机制，不适合直接支持某条路径的效应大小。

## 12. From Digital Anxiety to Empowerment in Older Adults: Cross-Sectional Survey Study on Psychosocial Drivers of Digital Literacy

- 在 todo 里主要支持：Stage 4 中“achievement 不是一次性情绪奖励，它可能削弱 anxiety 对后续使用的伤害”，因此 `controllable_success_memory` 作为长期保护痕迹是有邻近支持的。
- 原文短引：`"Higher family support was associated with lower digital anxiety"`
- 原文短引：`"this relationship was significantly weaker among those reporting a higher sense of achievement."`
- 原文出处：两句都来自 `abstract 第1段结果概括部分`，第一句在中段，第二句在后半段。
- 本地文件：[digital_anxiety_to_empowerment_older_adults_2026.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/digital_anxiety_to_empowerment_older_adults_2026.pdf)
- 这两句具体支持什么：第一句支持 support 可以先作用于 anxiety，再影响后续 intention。第二句更关键，它说明 achievement 不是纯粹附属变量，而可能改变 anxiety 的破坏性强度，这就是你们保留 `controllable_success_memory` 的邻近依据。
- 使用边界：这篇是横断面模型，它支持缓冲关系和调节思路，但不能直接证明“长期记忆项”的衰减速度或精确更新规则。

## 13. Experiences of a Community-Based Digital Intervention Among Older People Living in a Low-Income Neighborhood: Qualitative Study

- 在 todo 里主要支持：Stage 4 中“不是所有完成任务的经历都会沉淀成长期保护”，尤其当任务与当事人的日常需求不贴、只是跟着别人完成时，这种保护可能很弱。
- 原文短引：`"most expressed ambivalence about the perceived utility and relevance of the smartphone to their current needs and priorities."`
- 原文短引：`"participants valued the social interaction with volunteers and the personalized learning model"`
- 原文出处：两句都来自 `abstract 第1段结果概括部分`，第一句对应 utility / relevance 的结果总结，第二句对应 volunteer support / personalized learning 的结果总结。
- 本地文件：[community_based_digital_intervention_low_income_older_people_2024.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/community_based_digital_intervention_low_income_older_people_2024.pdf)
- 这两句具体支持什么：第一句说明“完成了干预”不等于“真觉得有用、以后还会用”，所以 `success_count` 不能直接等同于长期保护。第二句说明支持和陪伴有价值，但这种价值不必然自动转化成 mastery。
- 使用边界：这是低收入社区中的定性研究，特别适合用来反驳“只要做成一次就行”的简单模型，但不适合直接给长期记忆项定量。

## 14. Role of smart phones in improving psychological well-being and successful ageing of Iranian old women living with Technophobia: a randomized controlled trial

- 在 todo 里主要支持：Stage 4 中“技能训练和掌握确实可能降低 technophobia”，因此“控制经验可积累”并不只是纯理论推演。
- 原文短引：`"nine virtual training sessions on smartphone skills significantly reduced Technophobia"`
- 原文出处：`discussion 第1段`。
- 本地文件：[smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf)
- 这句话具体支持什么：它说明训练型、掌握型经历确实可能改变 technophobia 水平，所以你们把 mastery 看成会留下保护痕迹，不是没有依据。
- 使用边界：样本非常窄，只能作为弱到中等强度的干预支持，不能直接外推到一般老年数字服务场景。

## 15. Barriers and facilitators to the use of e-health by older adults: a scoping review

- 在 todo 里主要支持：Stage 5 中“support 最合理的作用方式，是先改善理解、效能、支持感和 benefit understanding，而不是简单给 helplessness 扣分”。
- 原文短引：`"The most prevalent barriers to e-health engagement were a lack of self-efficacy, knowledge, support, functionality, and information provision about the benefits"`
- 原文短引：`"enhancing self-efficacy in the use of technology"`
- 原文出处：两句都来自 `abstract 第1段结果总结部分`。
- 本地文件：[barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf)
- 这两句具体支持什么：第一句告诉我们，真正的问题常常出在“不会、没人帮、不知道为什么值得用”，这和你们的中介层写法是一致的。第二句则更直接地支持“支持应该先提升 self-efficacy”这一路径。
- 使用边界：这是 scoping review，适合支撑 barrier inventory 和变量组织方式，不适合直接支撑 episode 级动态更新。

## 16. Barriers to Digital Health Adoption in Older Adults: Scoping Review Informed by Innovation Resistance Theory

- 在 todo 里主要支持：Stage 3 和 Stage 6 中“avoid 要拆分”和“负面体验可能通过 anxiety / low self-efficacy 循环强化回避”。
- 原文短引：`"Data were extracted into a structured matrix and coded to the IRT domains: usage, value, risk, tradition, and image barriers."`
- 原文短引：`"low self-efficacy and technology anxiety creating feedback loops that reinforce avoidance behaviors."`
- 原文出处：第一句来自 `abstract 第1段 methods/results 交界处`；第二句来自官方网页 `results` 中综合讨论 `low self-efficacy`、`technology anxiety` 与 `avoidance` 循环关系的那一段。
- 本地文件：[barriers_to_digital_health_adoption_in_older_adults_2026.pdf](/Users/pifazuoren/Downloads/AgentSociety-main/paper/barriers_to_digital_health_adoption_in_older_adults_2026.pdf)
- 这两句具体支持什么：第一句几乎就是你们 `avoid_reason` 细分的直接框架依据，它明确告诉我们至少可以从 `usage / value / risk / tradition / image` 这些维度看阻力。第二句则支持 Stage 6 的 loop 写法，也就是低效能和焦虑不是静态背景，它们可能在反复负面体验中持续推高回避。
- 使用边界：这篇最强的直接支持点是“barrier typology”和“feedback-loop 方向”；但它仍然不是你们 steady-shock-recovery 设计下的纵向轨迹证据。

## 内部资料说明

下面这些在 todo 里可能会被提到，但不能和上面的外部论文混为一类：

- [AgentSociety_Instructions.md](/Users/pifazuoren/Downloads/AgentSociety-main/AgentSociety_Instructions.md)
- [意见.md](/Users/pifazuoren/Downloads/AgentSociety-main/意见.md)
- [paper/quant_refs/parameter_literature_map.md](/Users/pifazuoren/Downloads/AgentSociety-main/paper/quant_refs/parameter_literature_map.md)

它们可以支持工程组织、参数校准、写作决策和内部讨论，但不应在论文中作为正式外部证据引用。
