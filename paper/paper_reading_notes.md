# 逐篇阅读笔记

这份笔记是基于本地 PDF 中可提取的摘要、方法、讨论、结论等关键信息整理的，目标不是做“正式文献综述”，而是用尽量直白的话说明：

- 这篇 paper 在研究什么；
- 它怎么做的；
- 它得出了什么结论；
- 对 `digital_helplessness_proto` 有什么启发。

## 一、方法论 / LLM 社会模拟

### 1. AgentSociety: Large-Scale Simulation of LLM-Driven Generative Agents

- 这篇文章想做的是一个“大型社会模拟平台”，而不是只做几个聊天 agent。作者把 LLM agent、社会环境和大规模仿真引擎整合到一起，想让 agent 像“社会中的人”一样长期生活和互动。
- 它的规模很大，模拟了 1 万多个 agent、500 万次交互，并用 4 类社会问题做例子：极化、煽动性信息传播、UBI 政策、外部冲击（如飓风）。
- 核心结论是：LLM agent 不只是能做个体对话，还能被放进较真实的社会环境里，做调查、访谈、干预和政策实验。
- 对你最有用的点是：它给了一个很强的方法论背书，说明“先做 computational social experiment 的 prototype”是合理的。

### 2. Exploring Large Language Model Agents for Piloting Social Experiments

- 这篇文章的核心目标是把 LLM agent 变成“silicon participants”，也就是可以先替人做实验预演的模拟参与者。
- 文章搭了一个框架，里面不仅有 agent，还有干预条件的实现方式，以及行为数据、问卷数据、访谈数据的采集工具。
- 他们拿 3 个代表性社会实验做复现，结果和真实实验在定量和定性上都比较接近。
- 对你很重要的启发是：你的系统不需要一开始就像“真实人生模拟器”那么大，只要能稳定支持“条件设置 -> 行为 -> 反馈 -> 指标输出”，就已经符合 pilot experiment 的思路。

### 3. Generative Agents: Interactive Simulacra of Human Behavior

- 这篇是生成式 agent 里最经典的一篇。作者关心的不是“实验控制”，而是“如何让 agent 看起来像真的人在生活”。
- 它提出了一个很有名的三件套：observation、planning、reflection，也就是观察、计划、反思。agent 会把经历存成自然语言记忆，再从里面抽取高层反思来指导下一步行为。
- 在一个类似《模拟人生》的小镇里，25 个 agent 能自发传播信息、约人、组织派对，表现出一定的“社会涌现”。
- 对你来说，它更像灵感来源，而不是应该完整照搬的东西。老师说你当前要先收缩，所以你可以借它“状态会随着经历更新”的想法，但不要直接继承它复杂的 memory/reflection 结构。

### 4. From Individual to Society: A Survey on Social Simulation Driven by Large Language Model-based Agents

- 这是一篇综述，主要在帮你把整个 LLM 社会模拟领域“画地图”。
- 它把相关工作分成三层：个体模拟、场景模拟、社会模拟，并讨论了每类工作的架构、任务目标、评估方式、数据集和 benchmark。
- 文章的价值不在于给出一个新模型，而在于告诉你：大家到底在模拟什么、怎么评估、常见问题是什么。
- 对你写 RP 特别有用，因为它能帮你把自己的工作放在一个更清晰的位置上：你现在更像是“场景模拟 + 小型社会实验原型”，而不是完整社会系统模拟。

### 5. GenSim: A General Social Simulation Platform with Large Language Model based Agents

- 这篇 paper 看到的问题是：很多 LLM 社会模拟只能跑某个固定场景，而且 agent 一旦出错，系统就容易崩。
- 所以作者做了一个更通用的平台，强调 3 件事：抽象一套通用函数、支持十万级 agent、加入错误纠正机制。
- 它的贡献更偏工程平台，而不是行为理论。
- 对你来说最有启发的是：哪怕 prototype 很小，流程也最好是“模块化”的，比如任务生成、执行、状态更新、错误兜底最好分开。

### 6. Using Large Language Models to Simulate Multiple Humans and Replicate Human Subject Studies

- 这篇文章提出了一个很关键的概念：Turing Experiment。不是看模型能不能像“某一个人”，而是看它能不能像“实验中的一群人”。
- 作者用几个经典实验来测模型，比如 Ultimatum Game、Garden Path、Milgram Shock、Wisdom of Crowds，看模型能不能复现人类实验结果。
- 结果是：有些实验能复现，但也会出现系统性偏差，比如模型会表现出一种“过度准确”的倾向，不完全像真实人类。
- 对你项目的提醒非常重要：LLM agent 可以拿来做实验预演，但它不是现实本身，所以你后面一定要强调“这是 hypothesis-generating prototype，不是现实替代品”。

## 二、核心理论：helplessness / controllability

### 7. Learned helplessness and learned controllability: from neurobiology to cognitive, emotional and behavioral neurosciences

- 这篇是你“无助感”变量最核心的理论基础。它讲的是：如果一个人长期面对不可控、反复失败、怎么努力都没用的情境，就会形成 learned helplessness。
- learned helplessness 不只是“心情不好”，而是一整套变化：觉得结果和自己的努力无关、动机下降、回避尝试、甚至在后来其实有机会成功时也不再行动。
- 相反，controllability，也就是“我做了会有用”的感觉，会显著保护个体，减少无助和焦虑。
- 对你来说，这篇 paper 基本直接定义了 `helplessness_score` 的逻辑：连续失败、失败的不可控感、努力无效感，会让下一轮更容易回避、更不想尝试。

## 三、老年人数字焦虑 / technophobia / self-efficacy

### 8. Older adults’ self-perception, technology anxiety, and intention to use digital public services

- 这篇研究的是老年人在使用数字公共服务时，心理变量之间怎么连起来。作者特别关心自我老化认知、主观幸福感、technology anxiety、self-efficacy、perceived usefulness、使用意愿之间的关系。
- 方法上是 345 位老年人的问卷加结构方程模型（SEM）。
- 结果显示：technology anxiety 不一定是直接打掉使用意愿，但它会通过 self-efficacy 和 perceived usefulness 间接影响意愿；而 perceived usefulness 是最强的直接因素。
- 对你代码的意义很明确：你的 agent 状态至少应该有 `technology_anxiety`、`self_efficacy` 和 `perceived_usefulness` 这几个中间量，而不是只有“会不会用”。

### 9. Acceptance of digital health services among older adults

- 这篇 paper 关心的是：老年人为什么愿意或不愿意用数字健康服务。
- 它用扩展版 TAM 框架看了几个因素：perceived usefulness、self-efficacy、privacy concerns、ICT knowledge、family/formal support。
- 主要结论是：更高的 usefulness、更强的 self-efficacy、更多的家人和正式支持、更低的隐私担忧，会提高使用意愿；其中 usefulness 的作用最大。
- 这篇对你非常实用，因为它说明“求助”“被支持”“担心隐私”“觉得有没有用”都可以作为 agent 决策前的状态变量。

### 10. Influencing factors of digital health technology anxiety in the elderly: a systematic review and meta-analysis

- 这篇是专门盯着“数字健康技术焦虑”做的系统综述和 meta-analysis。
- 它合并了 11 项研究、4868 名参与者，发现影响焦虑的重要因素包括：年龄、数字健康素养、收入、城乡/户籍条件、家庭支持、社会网络、信息应用能力和 self-efficacy。
- 换句话说，老年人技术焦虑不是一个纯个人心理问题，而是能力、资源和支持共同作用的结果。
- 对你的 prototype 来说，这篇很适合支撑“不同 agent 初始值不一样”，尤其是农村/低收入/低数字素养群体应当被设成更脆弱。

### 11. Technophobia in digital health contexts: A systematic review and meta-analysis with a focus on older adults

- 这篇 paper 关注的是 technophobia，也就是对数字技术的恐惧和回避，放在数字健康环境里来研究。
- 作者发现，老年人的 technophobia 整体偏高，尤其在隐私和安全问题上更明显。高风险人群通常教育程度更低、数字健康素养更弱、语言能力较差、神经质更高、self-efficacy 更低。
- 另外，技术使用频率低、网络接触少、社会联系少，也会让 technophobia 更严重。
- 对你来说，technophobia 可以理解成一个比 technology anxiety 更“稳定”的长期倾向变量，很适合放在 persona 初始化里。

### 12. The mediating role of technology anxiety in the impact of loneliness on technology behavioral intention among community-dwelling older adults

- 这篇文章讨论的是：孤独感为什么会影响老年人的技术使用意愿。
- 它用台湾 250 位老年人的横断面调查发现，loneliness 会提高 technology anxiety，而 technology anxiety 又会降低技术行为意愿，中间起到了中介作用。
- 这意味着一些看似和“技术本身”无关的情绪状态，也会通过焦虑影响技术使用。
- 对你有启发的是：你的状态更新不一定只更新 `helplessness_score`，也可以让负反馈逐渐提高 `technology_anxiety`，从而进一步降低下一轮尝试概率。

### 13. Factors that influence technophobia in Chinese older patients with ischemic stroke

- 这篇聚焦一个更具体的人群：患缺血性脑卒中的中国老年患者。
- 它用横断面调查去看 technophobia 跟 eHealth literacy、general self-efficacy、social support 等变量的关系。
- 核心意思是：technophobia 不只是“怕科技”，而是和疾病背景、能力、自我效能、社会支持一起作用的。
- 对你来说，这篇很有“本土化”价值。它提醒你，如果以后想把场景收敛到中国老年人数字健康任务，这种群体细分会让模拟更可信。

### 14. From Digital Anxiety to Empowerment in Older Adults

- 这篇 paper 想讲的是：老年人的数字素养不仅是技术能力问题，还和家庭支持、社会影响、数字焦虑、成就感这些心理和社会因素强相关。
- 作者对 480 名中国老年人做问卷和 SEM，发现 family support 会降低数字焦虑，social influence 会提高使用意愿，而“成就感”会削弱焦虑对使用意愿的负面影响。
- 也就是说，如果一个人能在使用数字工具时体验到“我做成了”，焦虑对他的伤害会变小。
- 这对你设计 `state_update` 很关键：一次成功不仅能降低 helplessness，还可能通过“achievement / mastery”间接提高后续意愿。

### 15. The mechanism of digital feedback on health information anxiety among older adults

- 这篇文章研究的是：来自子女或他人的“数字反馈”，会怎样影响老年人的健康信息焦虑。
- 作者调查了中国 30 个城市的 1713 名老年人，发现 digital feedback 会直接降低健康信息焦虑，也会通过提升 information processing self-efficacy 间接降低焦虑。
- 但一个很细的发现是：如果反馈方式不耐心、讲不清楚，反而可能加重焦虑。
- 这篇对你超级重要，因为它直接支持“支持不是有没有，而是支持质量如何”。也就是说，assistant 不应该只设成二元变量，还可以有 `support_quality`。

## 四、数字摩擦 / 数字障碍 / 数字素养

### 16. Older Adults Perceptions of Technology and Barriers to Interacting with Tablet Computers

- 这篇是 focus group 研究，讨论老年人怎么看待技术和 tablet。
- 一个很重要的结论是：很多老年人不是“不愿意学”，而是“担心学不会、没人教、指令不清楚、怕出错”。
- 所以 barrier 往往不是单纯的“没有设备”，而是学习过程中的不确定感和缺少支持。
- 对你来说，这篇特别适合拿来提炼任务场景，比如验证码、界面跳转、按钮太多、说明不清楚、没人指导这些 friction。

### 17. Barriers and facilitators to the use of e-health by older adults: a scoping review

- 这篇综述了老年人使用 e-health 的障碍和促进因素。
- 常见障碍包括 self-efficacy 不足、知识不足、缺支持、系统功能问题、缺乏关于“这东西到底有什么用”的清楚说明。
- 常见促进因素则包括以用户为中心的设计、主动支持、清晰指导和合适的功能匹配。
- 对你原型的价值在于：它可以帮你把 friction 分成“能力类摩擦”“界面类摩擦”“支持类摩擦”“价值感知类摩擦”。

### 18. Key Challenges and Barriers to Digital Literacy for Older Adults

- 这是一篇数字素养的 scoping review，重点不只是“不会点按钮”，而是把障碍分成多个层次。
- 它总结出 7 大类障碍：健康限制、支持网络不足、便利性和易用性问题、知识和信息问题、感知/态度问题、资源问题，以及特殊人群问题。
- 文章强调这些障碍往往是叠加的，不是单独存在的。
- 对你来说，这说明 `digital_friction` 不应该只写成一个随机数，而更适合拆成几个来源：身体限制、界面复杂、缺支持、缺资源、认知负担等。

### 19. Latent obstacles in older adults’ digital health participation

- 这篇文章用更“数据驱动”的方式去找老年人数字健康参与的隐藏障碍。
- 它基于 35 位老年人的访谈，用 hybrid NLP clustering 分析，最后归纳出 4 类核心障碍：心理障碍、健康信息清晰度/可理解性问题、技术供给与需求不匹配、UI 与可达性问题。
- 这篇和普通综述不同的地方是：它把障碍看成“潜在分型”，而不是一堆散点问题。
- 对你很有启发的是：你的 agent 不一定都共享一个 friction 机制，可以做 3 到 4 类用户 profile，例如“焦虑型”“不会型”“不匹配型”“界面受阻型”。

## 五、采纳、使用意愿与行为模式

### 20. Barriers to and Facilitators of Digital Health Technology Adoption Among Older Adults With Chronic Diseases

- 这篇研究的是慢性病老年人为什么采纳或不采纳数字健康技术。
- 它是更新版系统综述，特别关注农村/城市差异、co-design 和公平性问题。
- 主要结论可以概括成一句话：采纳不是只看技术好不好，还看健康负担、设计是否贴合、有没有被一起设计、有没有基础资源。
- 对你来说，这篇说明任务设置最好和“真实需求”挂钩，比如预约、复诊、慢病监测，而不是抽象任务。

### 21. Barriers to Digital Health Adoption in Older Adults: Scoping Review Informed by Innovation Resistance Theory

- 这篇 paper 很适合你，因为它不是从“为什么会采纳”出发，而是从“为什么会抵抗”出发。
- 作者用 IRT（innovation resistance theory）去整理障碍，发现老年人的阻抗既包括功能性的，比如难用、复杂、身体能力限制，也包括心理性的，比如不舒服、觉得不适合自己、担心隐私、偏好线下互动。
- 特别重要的是，它指出 low self-efficacy 和 technology anxiety 会形成循环，让回避越来越稳定。
- 这篇对你的项目几乎是直接可用的：它天然支持“数字摩擦 -> 焦虑/无助 -> 回避 -> 更少练习 -> 更无助”的循环模型。

### 22. Factors influencing the intention to use telemedicine services among older adults in China

- 这篇文章关注中国老年人的 telemedicine 使用意愿。
- 它结合 TAM 和情感设计理论，对 377 份问卷做 SEM，发现最主要的驱动因素是 perceived usefulness 和 perceived ease of use，之后还有 cost value、system quality、trust、self-efficacy；而 technology anxiety 是负向因素。
- 这说明“愿不愿意点开”不是单看一个变量，而是认知因素和情绪因素共同决定。
- 对你很有用的是：`policy_choice` 可以不是简单看 helplessness，而是综合 usefulness、ease、trust、anxiety 来决定是否尝试。

### 23. Internet Health Care Service Use Behavioral Pattern Among Older Adults

- 这篇研究的重点不是单个变量，而是“老年人到底有哪些不同的互联网医疗使用模式”。
- 作者调查了山东 1828 名老年人，分出 5 类用户：完全不用、以注册为主、低活跃、中等综合、全服务用户。
- 结果显示，social support、technology acceptance、健康状况、教育程度、年龄等会显著影响落在哪一类。
- 对你项目最大的启发是：你完全可以把 agent 分成 4 到 5 类，而不是用一个连续概率去描述所有人。

## 六、支持、干预、训练

### 24. Effectiveness of Interventions for Addressing Digital Exclusion in Older Adults

- 这是一篇 rapid review，问的是：什么类型的干预，真的能减少老年人的数字排斥？
- 它纳入了 21 项研究，结论比较稳：多种干预都能提升数字技能、知识、数字素养、自我效能，减少 technophobia，并增加技术使用。
- 但它也强调一个现实问题：如果设备、网络、费用这些结构性障碍不解决，单纯培训的效果会受限。
- 对你来说，这篇可以直接支撑你设“有帮助”和“无帮助”条件，而且提醒你 assistant 不能只讲解操作，也要考虑资源条件。

### 25. Experiences of a Community-Based Digital Intervention Among Older People Living in a Low-Income Neighborhood

- 这篇 paper 研究的是低收入社区里的老年人，怎么理解和体验社区数字干预。
- 它的一个很重要发现是：老年人是否愿意学数字工具，并不只由“技术是否好用”决定，还受生活优先级、经济压力、 stigma、周围环境等强烈影响。
- 也就是说，数字工具只是他们生活中的一个部分，不一定是最重要的。
- 对你的系统来说，这意味着支持策略不能想当然。assistant 再强，也要面对“这个任务对他当下有没有意义”这个问题。

### 26. Role of smart phones in improving psychological well-being and successful ageing of Iranian old women living with Technophobia

- 这篇是随机对照试验。研究对象是独居老年女性，干预是 9 次智能手机技能训练。
- 结果显示，这样的训练能显著降低 technophobia，同时提升心理健康和 successful aging。
- 它的意义在于：帮助不只是提升操作能力，也能改变心理状态。
- 对你来说，这篇很适合支撑“assistant 条件不仅提高完成率，也应该降低 helplessness / anxiety，改善长期状态”。

## 七、如果只保留最关键的 8 篇

如果你现在只想先把 prototype 做出来，我建议先抓这 8 篇：

- `learned_helplessness_and_learned_controllability_review_2025.pdf`
- `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`
- `barriers_to_digital_health_adoption_in_older_adults_2026.pdf`
- `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf`
- `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf`
- `community_based_digital_intervention_low_income_older_people_2024.pdf`
- `LLM_Agents_for_Piloting_Social_Experiments.pdf`
- `social_simulation_driven_by_llm_agents_survey_2024.pdf`

原因很简单：

- 第一篇给你“无助感更新”的理论；
- 第二、三篇给你“焦虑 / 自我效能 / 阻抗”逻辑；
- 第四篇帮你写任务 friction；
- 第五、六篇帮你写 support / feedback；
- 最后两篇帮你把整个工作放回“LLM social experiment prototype”的方法论里。
