# Helplessness Update 机制 - 文献对应表

每条机制设计决策，对应到具体的文献依据和原文句子。用于导师汇报。

---

## 机制 1：把主驱动从"失败次数"改成"主观不可控感"

### 代码里做了什么

- `BASE_DELTAS` 全面压低（failure_after_attempt 只有 +0.6）
- `UNCONTROLLABILITY_DELTAS` 成为失败路径最重的单项（level 2 = +2.4，远超 base）
- 一次 level-2 不可控失败的总压力中，base 只贡献 0.6，而 uncontrollability 贡献 2.4（实际总压力还会叠加 repetition、efficacy_loss、control_loss 等项，再经过 protection 和 damping 调节）

### 为什么这样做——文献依据

**Seligman & Maier (1967)**
> "Shock termination was independent of responding."

这是 learned helplessness 的经典起点。核心不是"失败了几次"，而是个体学到"我的反应不会改变结果"。

**Abramson, Seligman & Teasdale (1978)**
> "Once people perceive noncontingency, they attribute their helplessness to a cause."

人类 helplessness 的 reformulation。不是所有失败都同样伤人，关键是主观解释层。

**Maier & Seligman (2016)**
> "This passivity can be overcome by learning control, with the activity of the medial prefrontal cortex, which subserves the detection of control leading to the automatic inhibition of the dorsal raphe nucleus."

50 年后的理论升级：被动不是学来的，它是默认状态；真正关键的是是否检测到了 control。

**Learned helplessness and learned controllability review (2025)**
> "In 'learned helplessness' an organism learns that outcomes are independent of their actions, and it was suggested that in humans this process involves, in addition to a subjective perception of helplessness, a learned attitude of decreased motivation to exert any effort or coping with perceived stressors."

直接把 helplessness 的核心写成 action-outcome contingency 被破坏。

**Older adults' self-perception, technology anxiety, and intention to use digital public services (2024)**
> "Technology anxiety indirectly affects the intention to use digital public services, which has an impact on the intention to use through the perceived usefulness and the complete mediating path of self-efficacy and perceived usefulness."

老年数字服务场景下的 SEM 证据：焦虑/负面事件不是一跳直接打到行为意图，中间必须经过主观解释层。

---

## 机制 2：加入 self-efficacy 中介层

### 代码里做了什么

- `efficacy_loss_term = (50 - task_self_efficacy) / 22`，clamp [0, 1.6]
- 效能感越低，同样的失败对 helplessness 的伤害越大
- SE 本身按 outcome 和 support_mode 差异化更新：success_self +6.0；success_with_help 在 enabling_support 时 +4.5、substituting_support 时 +1.5；failure_even_with_help 在 enabling 时 -4.5、substituting 时 -6.0；avoid 按 helpless/risk/low_value 分别 -2.0/-0.5/0.0

### 为什么这样做——文献依据

**Bandura (1977)**
> "Expectations of personal efficacy determine whether coping behavior will be initiated, how much effort will be expended, and how long it will be sustained."

self-efficacy 不是装饰性背景变量，它决定人会不会开始做、会投入多少、会坚持多久。

**Skinner (1996)**
> "The framework is used to analyze more than 100 terms, such as sense of control, proxy control, and primary control."

control 不是单层构念。perceived_uncontrollability、felt_control、task_self_efficacy 不能被压成一个总分。

**Factors that influence technophobia in Chinese older patients with ischemic stroke (2025)**
> "Education level, monthly income, number of smart devices, electronic health literacy, self-efficacy, and social support were the main factors affecting technophobia of older patients with ischemic stroke."

在中国老年人情境里，self-efficacy 是 technophobia 的显著影响因素之一，不是边缘变量。

**Technophobia in digital health contexts: systematic review and meta-analysis (2025)**
> "At the behavioral level, low self-efficacy, limited technology use, and infrequent Internet use emerged as significant risk factors."

跨 19 项研究的元分析确认：low self-efficacy 是跨研究一致的显著相关因素。

**Digital feedback on health information anxiety among older adults (2025)**
> "The analysis further revealed that the relationship between digital feedback and health information anxiety was partially mediated by information processing self-efficacy (β=−0.2806, SE = 0.0157, 95% CI=−0.3115, −0.2503)."

self-efficacy 确实是外部经历影响长期心理状态的中介路径（N=1713）。

---

## 机制 3：加入 felt_control 事件层调节

### 代码里做了什么

- `control_loss_term = (50 - felt_control) / 28`，clamp [0, 0.9]
- 事前越觉得"这事我控制不了"，失败后越伤
- felt_control 由 LLM task appraisal 每轮生成，波动较快

### 为什么这样做——文献依据

**Skinner (1996)**
> "The framework is used to analyze more than 100 terms, such as sense of control, proxy control, and primary control."

felt_control 和 task_self_efficacy 虽然都和 control 有关，但在 Skinner 的框架里对应不同层面：felt_control 是即时感受，TSE 是跨事件积累的效能判断。

**Learned helplessness and learned controllability review (2025)**
> "In 'learned helplessness' an organism learns that outcomes are independent of their actions, and it was suggested that in humans this process involves, in addition to a subjective perception of helplessness, a learned attitude of decreased motivation to exert any effort or coping with perceived stressors."

理论主轴本身就是 control / controllability，不是 efficacy。代码里用 felt_control 做事件层调节，正是保留这条理论主线。

---

## 机制 4：基础阻尼（damping）——工程启发式，非文献直推

### 代码里做了什么

- `damping = 1 - 0.45 * H / 100`，clamp [0.55, 1.0]
- 当前 helplessness 已经很高时，再一次失败的边际伤害变小
- H=0 时全额冲击，H=100 时打 55 折

### 为什么这样做——设计理由与理论相容性

damping 不是某篇论文直接推出的公式，而是一个 **bounded-state heuristic**。它的设计理由是：

1. 从理论方向看，Maier & Seligman (2016) 把被动重新定义为"默认状态"而非"无限累积的学习结果"。如果被动本身有上限，那"已经很无助时再失败一次"的边际效应理应递减。但这条推理是我们的模型解释，不是原文的直接结论。

2. 从工程稳定性看，一旦 self-efficacy 和 helplessness 形成反馈环路（高 helplessness → 更多 avoid → 更少 success → SE 下降 → helplessness 更高），没有阻尼的系统会过快收敛到极端值。damping 的作用是保留循环的动态特征，同时防止数值失控。

3. 具体的阻尼系数（0.45、下限 0.55）是 simulation-calibrated heuristic，不是从文献系数反推出来的。

**总结**：damping 是一个与理论方向相容、但主要由仿真稳定性需求驱动的工程设计。论文中应表述为 bounded-state heuristic，不应写成"文献直接支持的机制项"。

---

## 机制 5：Avoid 拆分（helpless / risk / low_value）

### 代码里做了什么

- avoid_without_attempt 不再一律计入 helplessness
- 三类乘数：helpless_avoid ×1.0，risk_avoid ×0.35，low_value_avoid ×0.15
- 分类规则综合 helplessness、SE、felt_control、perceived_risk、task_value、env risk

### 为什么这样做——文献依据

**Davis (1989), TAM**
> "In both studies, usefulness had a significantly greater correlation with usage behavior than did ease of use."

有些"不做"本质上是"觉得不值得"，不是 helplessness。usefulness 在 TAM 中是独立的 acceptance 驱动因子。

**Venkatesh et al. (2003), UTAUT**
> "UTAUT was formulated, with four core determinants of intention and usage, and up to four moderators of key relationships."

intention / acceptance 不应被粗暴并入 helplessness，也可能是价值判断、条件约束或社会影响。

**Barriers to and Facilitators of Older People's Engagement With Web-Based Services (2024)**
> "Many participants adopted a granular approach to use, in which they had specific and limited web-based tasks they would undertake within particular domains of activity, such as banking or shopping."

很多老人不是"完全不用"，而是只敢做一小部分，被 fear/risk/scam concern 限制。avoid 的来源至少有一部分不是 helplessness。

**Barriers to Digital Health Adoption in Older Adults: IRT scoping review (2026)**
> "Data were extracted into a structured matrix and coded to the IRT domains: usage, value, risk, tradition, and image barriers."

直接提供了 barrier typology 框架（usage/value/risk/tradition/image），支持 avoid_reason 的细分。

**Acceptance of digital health services among older adults (2022)**
> "In summary, higher perceived usefulness and self-efficacy, more perceived family and formal support, and low privacy concerns contributed to a higher intention to use digital health services, among our relatively well-educated and healthy sample of older adults."

"是否使用"是 usefulness、self-efficacy、support、privacy concern 共同作用的结果，不是 helplessness 的单一外壳。

**Older adults' digital technology experiences (2025)**
> "Otherwise, older persons may become more dependent on others to manage their everyday life."

老年人对数字技术常常是 mixed feelings，有些 avoid 本质上是 preference，不是 helplessness。

---

## 机制 6：Controllable success memory（长期保护项）

### 代码里做了什么

- 只有高质量自主成功才积累：success_self 在 FC≥45 且 U≤1 时 gain=0.07；进一步 FC≥60 且 U=0 时额外 +0.05；之前同任务连败≥2 时再 +0.03
- enabling_support 成功在严格条件下给极小积累（基础 0.025；quality≥2 且 FC≥60 时额外 +0.015）
- 所有 gain 还会乘以 `difficulty_weight`（任务难度 0.5 时 ×0.85，难度 1.0 时 ×1.15）
- 每天衰减 ×0.985（半衰期约 46 天）
- 在失败路径中做乘性保护：`raw_delta * (1 - CSM * 0.45)`，最多降低 45% 负向压力

### 为什么这样做——文献依据

**Seligman & Maier (1967)**
> "Initial experience with escape in the shuttle box led to enhanced panel pressing during inescapable shock in the harness and prevented interference with later responding in the shuttle box."

这句直接描述了"先前可控经验的保护作用"：先经历过可控逃避的动物，后续面对不可控电击时不会出现 helplessness 干扰。controllable_success_memory 的操作化源头在这里。

**Maier & Seligman (2016)**
> "This passivity can be overcome by learning control, with the activity of the medial prefrontal cortex, which subserves the detection of control leading to the automatic inhibition of the dorsal raphe nucleus."

controllability 不是一次性好运，而是可以被学习的；学到之后，它能主动抑制后续的 helplessness 反应。

**Learned helplessness and learned controllability review (2025)**
> "Conversely the sense of control offers the ability to effectively respond to environmental stressors by taking purposeful actions through goal-oriented behaviors."

这句直接讲的是 controllability 的保护功能（而不是 helplessness 本身）。同一段还写到这种能力"may be stimulated, trained or learned"，支持把它看成可积累的长期资源。

**From Digital Anxiety to Empowerment in Older Adults (2026)**
> "Digital anxiety showed a strong negative association with intention; however, this relationship was significantly weaker among those reporting a higher sense of achievement."

achievement 不只是"让人开心"——它会削弱 anxiety 的破坏力。这支持 controllable_success_memory 作为调节项（moderator），而不是一次性情绪奖励。但需要注意：原文测量的是横断面的"成就感"，把它进一步操作化为"长期记忆项"是我们的模型设计，不是作者的原始结论。

**Community-Based Digital Intervention Among Older People (2024)**
> "Although older learners stated varying levels of motivation to learn, most expressed ambivalence about the perceived utility and relevance of the smartphone to their current needs and priorities."

反面证据：完成干预不等于真觉得有用。所以不是所有 success 都该积累到 memory 里，只有"真正理解并感到自己做成"的才算。

**Smartphone RCT for Iranian Old Women with Technophobia (2025)**
> "The findings indicate that nine virtual training sessions on smartphone skills significantly reduced Technophobia, improved psychological well-being, and promoted successful aging among older women."

干预层面的正面证据：掌握型、可控型的成功经历确实可以降低 technophobia（RCT, N=80）。

**Bandura (1977)**
> "Persistence in activities that are subjectively threatening but in fact relatively safe produces, through experiences of mastery, further enhancement of self-efficacy and corresponding reductions in defensive behavior."

这句直接把 mastery experience 和 self-efficacy 增强联系起来。Bandura 在正文中进一步指出 performance accomplishments 是四种效能信息来源中最可靠的一种（"the more dependable the experiential sources, the greater are the changes in perceived self-efficacy"），但"最强来源"这一层级判断来自正文论述，不是这句引文本身的直接含义。

---

## 机制 7：Support 从直接减分器改成间接修复

### 代码里做了什么

- 直接 buffer 极小化：SUPPORT_BUFFERS = {0: 0.0, 1: 0.05, 2: 0.12}，且只在 failure_even_with_help 和 abandon_midway 时触发
- 分为 enabling_support（赋能型）和 substituting_support（替代型）
- 主效果通过三条间接路径：
  - SE 差异化更新（enabling +4.5 vs substituting +1.5）
  - CSM 选择性积累（只有 enabling 才允许积累）
  - mastery_recovery 分级（enabling 时 recovery +0.35 vs substituting 最多 +0.15）

### 为什么这样做——文献依据与建模判断

文献直接支持的是"support 通过 self-efficacy 中介发挥作用"和"support 可能导致依赖而非自主"这两个方向。在此基础上，我们做出了"以间接修复为主、直接 buffer 极小化"的建模判断，并把 support 分成 enabling/substituting 两类。这个建模判断受文献方向约束，但"三条间接路径的具体工程实现"是我们的操作化设计，不是文献直接规定的。

**Digital feedback on health information anxiety among older adults (2025)**
> "The analysis further revealed that the relationship between digital feedback and health information anxiety was partially mediated by information processing self-efficacy (β=−0.2806, SE = 0.0157, 95% CI=−0.3115, −0.2503)."

feedback→self-efficacy→anxiety 的中介路径被直接验证。这是"support 应先修复中介层"这一方向最直接的定量证据。但原文同时报告了直接效应，所以更适合支持"以间接修复为主"，而不是"只能间接作用"。

**Older adults' digital technology experiences (2025)**
> "Otherwise, older persons may become more dependent on others to manage their everyday life."

support 可能制造依赖而非修复自主性。这支持把 substituting_support 和 enabling_support 区分开，但"区分后具体怎么差异化作用于 SE 和 CSM"是我们的实现设计。

**Barriers to and Facilitators of Older People's Engagement With Web-Based Services (2024)**
> "The participants also valued the one-to-one support given to them but stressed that this needed to be ongoing support, noting that sometimes they would 'get the hang of' one task (eg, shopping) only to find that the next time they logged on to the website, the landing page may have changed, which would 'throw them off' and result in them feeling unsure whether they could continue in the manner they had been taught."

帮助需要持续、可重复，不是一次性给完就结束。这支持 support 不该被写成一个固定的一次性 buffer。

**Barriers and facilitators to the use of e-health by older adults: scoping review (2021)**
> "The most prevalent barriers to e-health engagement were a lack of self-efficacy, knowledge, support, functionality, and information provision about the benefits of e-health for older adults."

主要障碍是"不会、没人帮、不知道有什么好处"。这和"support 应先修复理解和效能"的方向一致。

**Factors that influence technophobia in Chinese older patients (2025)**
> "Education level, monthly income, number of smart devices, electronic health literacy, self-efficacy, and social support were the main factors affecting technophobia of older patients with ischemic stroke."

support 是多因素系统中的一部分，不是万能项。

**Acceptance of digital health services among older adults (2022)**
> "In summary, higher perceived usefulness and self-efficacy, more perceived family and formal support, and low privacy concerns contributed to a higher intention to use digital health services, among our relatively well-educated and healthy sample of older adults."

family/formal support、self-efficacy、usefulness 都在同一结构里起作用，support 不能被写成单独一个万能负号。

---

## 机制 8：成功恢复的差异化（mastery_recovery_term）

### 代码里做了什么

- success_self 最强恢复：base -1.4 + recovery 最高 1.85 = delta 最大 -3.25
- success_with_help + enabling：recovery 最高 0.70（enabling 0.35 + ended_streak 0.35）= delta 约 -1.40
- success_with_help + substituting：recovery 最高 0.50（quality=2 时 0.15 + ended_streak 0.35）= delta 约 -1.20
- 结束连败 streak 额外 +0.35 recovery（对所有成功结果生效，不限 support_mode）
- 高 felt_control 时 success_self 有额外 recovery 加成

### 为什么这样做——文献依据与建模判断

"自己做成比被帮着做成修复力更强"这一方向受文献支持，但具体的恢复分值设计（success_self 最高 -3.25 vs substituting 最多 -0.85）是 simulation-calibrated 的建模选择。

**Bandura (1977)**
> "Persistence in activities that are subjectively threatening but in fact relatively safe produces, through experiences of mastery, further enhancement of self-efficacy and corresponding reductions in defensive behavior."

mastery experience 直接增强 self-efficacy 并减少防御行为。Bandura 在正文中进一步指出 performance accomplishments 是四种效能信息来源中最可靠的一种，但这一层级判断来自正文论述，不是这句引文的直接含义。

**Maier & Seligman (2016)**
> "This passivity can be overcome by learning control, with the activity of the medial prefrontal cortex, which subserves the detection of control leading to the automatic inhibition of the dorsal raphe nucleus."

controllability 的恢复来自重新检测到 control。"自己做成"比"被帮着做成"更可能触发这种 control detection。

**Community-Based Digital Intervention Among Older People (2024)**
> "Although older learners stated varying levels of motivation to learn, most expressed ambivalence about the perceived utility and relevance of the smartphone to their current needs and priorities."

"完成了干预"不等于"真觉得有用、以后还会用"。所以 success_with_help 的恢复应当比 success_self 弱。

**Older adults' digital technology experiences (2025)**
> "Otherwise, older persons may become more dependent on others to manage their everyday life."

如果帮助只是"代办"，任务虽然完成但 agency 修复很弱。这支持 substituting_support 恢复最低的设计方向。

---

## 机制 9：helplessness 不按天自然回落——建模选择，受理论方向约束

### 代码里做了什么

- helplessness_score 没有每日 decay
- 只靠后续成功事件把它拉下来
- 会按天衰减的是 controllable_success_memory（×0.985/天）和 recent_negative_feedback_ema（×0.9/天）

### 为什么这样做——理论方向与建模选择

"不加每日自动回落"是一个建模操作化选择。它的理论相容性来自以下方向，但不是某句引文的直接推论：

**Abramson, Seligman & Teasdale (1978)**
> "Once people perceive noncontingency, they attribute their helplessness to a cause."

这句本身讲的是归因过程。Abramson 在正文中进一步指出，如果归因是 stable / global 的，helplessness 倾向于持续更久。我们的"不自动回落"设计与这一理论方向兼容：如果无助感来自稳定归因，它不应仅靠时间流逝消退。但需要注意，这是模型设计者的推理，不是作者对仿真参数的直接建议。

**Learned helplessness and learned controllability review (2025)**
> "In 'learned helplessness' an organism learns that outcomes are independent of their actions, and it was suggested that in humans this process involves, in addition to a subjective perception of helplessness, a learned attitude of decreased motivation to exert any effort or coping with perceived stressors."

helplessness 被描述为一种"学到的态度"，暗示它不是一时情绪波动。但"learned attitude"是否意味着"分数不该有 daily decay"，仍然是我们的操作化解释，不是原文的直接结论。

---

## 机制 10：trust 和 avoidance 是独立更新链——建模决策

### 代码里做了什么

- trust_in_apps 和 avoidance_tendency 在 compat.py 中按 outcome 离散更新
- 和 helplessness 公式完全独立，不互相输入
- 三者在同一事件后同步更新，但各走各的公式

### 为什么这样做——建模理由

这是一个合理的建模决策，而不是强文献要求。以下文献支持的是"多维构念不应折叠"的一般原则，不是"必须实现三条独立更新链"的具体工程规定：

**Venkatesh et al. (2003), UTAUT**
> "UTAUT was formulated, with four core determinants of intention and usage, and up to four moderators of key relationships."

acceptance 在 UTAUT 框架里本身就是多维的（performance expectancy / effort expectancy / social influence / facilitating conditions），暗示把 trust、avoidance、helplessness 分开跟踪是合理的方向。

**Skinner (1996)**
> "The framework is used to analyze more than 100 terms, such as sense of control, proxy control, and primary control."

不同 control-related constructs 之间虽然相关，但功能位置不同。这支持"不要把一切混成一个总分"的一般原则。

---

## 快速索引

| 机制 | 核心文献 | 一句话理由 |
|---|---|---|
| 不可控感主驱动 | Seligman 1967; Abramson 1978; Maier 2016; Review 2025 | 关键不是失败次数，是 action-outcome contingency |
| SE 中介层 | Bandura 1977; Technophobia meta 2025; Digital feedback 2025 | 效能感决定是否尝试和坚持 |
| Felt control 调节 | Skinner 1996; Review 2025 | control 不是单层构念，即时感受和积累判断分开 |
| 阻尼 | （工程启发式） | bounded-state heuristic，与"被动是默认状态"方向相容，非文献直推 |
| Avoid 拆分 | Davis 1989; UTAUT 2003; Web services 2024; IRT 2026 | 不做不等于无助，可能是风险规避或价值判断 |
| 可控成功记忆 | Seligman 1967; Maier 2016; Empowerment 2026; Community 2024 | 可控经验提供长期保护，但不是所有成功都算 |
| Support 间接化 | Digital feedback 2025; Digital experiences 2025; eHealth review 2021 | 帮助应修复中介层，不是直接减分 |
| 成功恢复差异化 | Bandura 1977; Maier 2016; Community 2024 | 自己做成比被帮着做成修复力强 |
| 无自动回落 | Abramson 1978; Review 2025 | 建模选择：与"learned attitude 不随时间自动消退"方向相容 |
| Trust/avoidance 独立 | UTAUT 2003; Skinner 1996 | 建模决策：多维构念不应折叠，但具体独立链是工程选择 |
