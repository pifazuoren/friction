# Helplessness Update 改进策略（全文献支撑版）

---

## 一、当前机制的三个核心问题

### 问题1：结局标签权重过大，心理中介过弱

当前 `state_update.py` 的公式：

```
delta_h = BASE_DELTAS[outcome] + repetition + uncontrollability - support_buffer
```

其中 `BASE_DELTAS` 固定为 success_self=-5, failure_after_attempt=+4 等。这本质上是**事件打分**，不是**心理过程建模**。

**理论依据**：*Learned helplessness and learned controllability: review* (2025) 明确指出——不是失败本身导致无助感，而是"学到了自己的行动无法改变结果"。*Older adults' self-perception, technology anxiety, and intention to use digital public services* (2024) 的 SEM 发现 Technology Anxiety → Behavioral Intention 的直接路径**不显著** (β=0.048)，必须经过 Self-efficacy → Perceived Usefulness 的中介。

### 问题2：Support被当作直接缓冲，而非间接修复机制

当前 `SUPPORT_BUFFERS = {0: 0.0, 1: 1.0, 2: 2.5}` 直接从 helplessness delta 中减去。

**理论依据**：*Older adults' digital technology experiences: a qualitative study* (2025) 区分了"替代性帮助"（别人帮你做完）和"赋能性帮助"（教你理解流程）。*Barriers to and facilitators of older people's engagement with web-based services* (2024) 强调支持需要连续、耐心、可重复。帮助应通过**修复 felt_control 和 task_self_efficacy** 间接作用，而非直接降低 helplessness。

### 问题3：所有回避都隐式归入无助感，未区分原因

当前 `avoid_without_attempt` 固定 +1.0 helplessness。

**理论依据**：*Barriers to and facilitators of older people's engagement with web-based services* (2024) 明确指出老年人不完成数字任务有三种原因——"努力没用"(helplessness)、"怕出错/怕诈骗"(risk avoidance)、"线下更好"(channel preference)。只有第一种应更新 helplessness。

---

## 二、改进策略

---

### 改进点1：将「感知不可控」提升为更新公式的主驱动项，降低结局标签的直接权重

**当前问题**：`state_update.py` 中 `BASE_DELTAS` 按结局标签直接赋值（如 failure_after_attempt=+4.0），结局标签是 helplessness 变化的最大贡献项。

**改进方向**：降低 `BASE_DELTAS` 的绝对权重（约降至原来的 40%），将 `perceived_uncontrollability` 从附加修正项提升为主项。

**文献支撑**：

- ***Learned helplessness and learned controllability: review* (2025)**：明确指出「真正让人变得无助的，不是挨了多少次打击，而是大脑逐渐形成了一种因果判断——'我的行动不会改变结果'」。原文 conclusion："In 'learned helplessness' an organism learns that outcomes are independent of their actions." 因此，无助感的更新驱动应是**主观不可控感**，而非事件结局本身。

- ***Older adults' self-perception, technology anxiety, and intention to use digital public services* (2024)**：N=345 老年人 SEM 分析发现，Technology Anxiety → Behavioral Intention 的直接路径**不显著**（β=0.048, p=0.456）。这说明即使在老年数字场景中，负面体验也不会直接跳到行为改变——必须经过中间心理变量的传导。同理，一次事件的结局标签不应直接大幅改变长期 helplessness。

---

### 改进点2：引入 task_self_efficacy 作为核心中介变量

**当前问题**：`experience_memory.py` 中已有 `task_self_efficacy` 并且每次事件后更新，但它只影响策略选择权重，**不参与** helplessness 更新公式。

**改进方向**：让 task_self_efficacy 进入 helplessness 更新公式——低自我效能下的失败对 helplessness 的冲击更大，高自我效能下的失败对 helplessness 的冲击更小。

**文献支撑**：

- ***Older adults' self-perception, technology anxiety, and intention to use digital public services* (2024)**：SEM 路径系数显示，TA → SE 路径 β=-0.736（显著），SE → PU 路径 β=0.634（显著），TA → SE → PU → BI 这条完整中介链解释了 **59.3%** 的总效应。但 SE → BI 直接路径不显著（β=0.096）。这说明自我效能是负面体验到行为变化之间的**关键中介层**，而非直接终点。对应到模型：失败 → task_self_efficacy 下降 → helplessness 上升，而非失败 → helplessness 直接上升。

- ***Factors that influence technophobia in Chinese older patients with ischemic stroke* (2025)**：*BMC Geriatrics*，204名中国老年脑卒中患者，多元回归显示 self-efficacy 是 technophobia 的显著影响因素，且可解释 35.3% 的总变异。说明自我效能在老年数字场景中是一个有实证支持的核心中间变量。

- ***Technophobia in digital health contexts: a systematic review and meta-analysis with a focus on older adults* (2025)**：纳入19项研究的元分析，在行为层面（behavioral level）中发现 low self-efficacy 是 technophobia 的显著风险因素（r 范围 -0.537 to 0.235, P<0.05）。进一步验证了自我效能在老年人数字恐惧/无助形成中的中介地位。

---

### 改进点3：将 felt_control（感知控制感）纳入更新公式

**当前问题**：`task_appraisal` 中已经有 `felt_control`（0-100），但它目前只在 `experience_memory.py` 的 `task_appraisal_shift` 中间接影响 `effective_helplessness`（影响策略选择），**不直接参与** helplessness 长期更新。

**改进方向**：在 helplessness 更新中加入 `control_loss_term`：当 felt_control 低时，同一个失败事件对 helplessness 的影响更大。

**文献支撑**：

- ***Learned helplessness and learned controllability: review* (2025)**：核心理论框架——"The sense of control offers the ability to effectively respond to environmental stressors by taking purposeful actions through goal-oriented behaviors." 以及 "a subjective perception of control plays a crucial role in developing more effective coping strategies." 因此，helplessness 的变化应直接受控制感调节。

- ***Latent obstacles in older adults' digital health participation: a community-based hybrid cluster analysis with natural language processing* (2026)**：*BMC Public Health*，通过对35名老年人的社区焦点小组访谈进行 NLP 聚类分析，识别出四个核心潜在障碍，其中第一个就是「psychological barriers to digital technology use」。研究指出：「The lack of positive technology learning experiences and external support makes older adults prone to a sense of low self-efficacy.」这里的 low self-efficacy 本质上就是 felt_control 的丧失。

---

### 改进点4：条件化重复失败惩罚——仅在不可控条件下累加

**当前问题**：`repetition_delta()` 函数对连续失败次数无条件加惩罚（2次→+1, 3次→+2, 4+→+3），不论失败发生在什么环境条件下。

**改进方向**：仅当 `perceived_uncontrollability >= 1` 时才触发 repetition_delta。在可控条件下的重复失败（如低 friction、高 support 环境）不应自动累加惩罚。

**文献支撑**：

- ***Learned helplessness and learned controllability: review* (2025)**：明确区分——「Prolonged exposure to **uncontrollable** stressors may lead to learned helplessness」，而可控条件下的失败不会产生无助效应。论文进一步说明 controllability 可以被训练，产生免疫效应——因此，在可控条件下（低 friction、高 support）重复失败，反而可能是学习过程，不应自动惩罚。

- ***Impact of regular smartphone use in decreasing technophobia and improving mental health and successful ageing for older adults* (2025)**：*BMC Research Notes*，N=80 的 RCT 实验发现，仅 9 次在线智能手机技能培训就能显著降低老年女性的 technophobia（p<0.001, Cohen's d=0.778 for successful aging）。这说明在有支持的可控条件下，即使过程中有失败和挫折，重复接触技术反而是修复而非损伤——不应在此条件下惩罚重复失败。

---

### 改进点5：区分三种回避行为，仅「无助性回避」更新 helplessness

**当前问题**：`avoid_without_attempt` 统一给 +1.0 的 base_delta，不区分回避原因。

**改进方向**：区分三种回避——
1. **无助性回避**（effort futile）：连续失败+低 felt_control+低 self_efficacy → 更新 helplessness
2. **风险性回避**（fear of error/fraud）：高 risk_level 环境 → 不更新 helplessness
3. **低价值回避**（not worth it）：低 task_value → 不更新 helplessness

**文献支撑**：

- ***Barriers to and facilitators of older people's engagement with web-based services* (2024)**：*JMIR Aging*，24名75+老年人定性访谈发现，老年人不完成数字任务有多种原因——「Fear of pressing wrong button」「Fear of fraud」「Offline feels safer」「Can do task but only dare low-risk version」。论文明确指出参与模式是 **narrow use and restricted activity**，而非全面无助。许多老年人是选择性参与，不是因为无助，而是因为风险评估或渠道偏好。

- ***Older adults' self-perception, technology anxiety, and intention to use digital public services* (2024)**：发现 Perceived Usefulness → Behavioral Intention 路径 β=**0.961**（最强效应），说明「不愿意用」在很大程度上是「觉得不值得用」，这和「觉得努力没用」是完全不同的心理机制。将二者混入同一个 helplessness 指标会混淆因果。

- ***Older adults' digital technology experiences: a qualitative study* (2025)**：*BMC Digital Health*，17名72-101岁老年人定性访谈，核心发现之一是 **divided preferences**：老年人不是统一地接受或拒绝数字技术，而是根据场景、风险、价值选择性使用。论文明确指出 "older persons cannot be seen as a homogeneous group regarding the use of digital technology"。

---

### 改进点6：将支持（support）从直接缓冲改为间接作用

**当前问题**：`SUPPORT_BUFFERS = {0: 0.0, 1: 1.0, 2: 2.5}` 直接从 helplessness delta 中减去。

**改进方向**：support 的主要作用路径改为——提升 `expected_help_effectiveness` → 修复 `task_self_efficacy` → 恢复 `felt_control` → 间接降低 helplessness。仅保留很小的直接缓冲项。

**文献支撑**：

- ***Barriers to and facilitators of older people's engagement with web-based services* (2024)**：对支持的核心发现是，有效的支持需要是 **continuous, patient, repeatable** 的。单次帮助不会自动修复信心，支持的价值在于重建 familiarity 和 controllability。

- ***Older adults' digital technology experiences: a qualitative study* (2025)**：明确区分了两种帮助——**赋能性帮助**（builds understanding and capability → increases controllability）vs **替代性帮助**（others do the task → may not repair helplessness, potentially increases dependence）。论文原文："support and education are essential; without adequate support, older persons may become more dependent on others to manage everyday life." 这说明帮助对 helplessness 的修复取决于帮助的**性质**，不能简单按数值减去。

- ***Barriers and facilitators of eHealth use in older adults: a scoping review* (2021)**：*BMC Public Health*，scoping review 纳入 14 篇文献，发现 lack of self-efficacy 是老年人 e-health 参与的最主要障碍之一，而 support for enhancing self-efficacy 是最关键的促进因素。这说明支持的真正作用机制是修复自我效能，而非直接消除负面状态。

- ***Community-based digital intervention for low-income older people* (2024)**：*JMIR Aging*，19名60+低收入老年人的社区数字干预研究发现，「the internalization of ageist stereotypes of being less worthy learners and the perception of smartphone use as being in the realm of the privileged other further reduced self-efficacy and interest in learning」。这说明即使有社区支持，如果支持没有修复自我效能，反而可能强化依赖和无力感。

---

### 改进点7：增加可控成功的免疫效应（controllable success memory）

**当前问题**：当前 `success_self` 仅产生单次 base_delta=-5.0 和 recovery_bonus，没有长期积累的保护效应。

**改进方向**：新增 `controllable_success_memory` 状态变量，记录累积的自主成功经验（带衰减）。该变量越高，未来高 friction 任务中 helplessness 的增长敏感度越低。

**文献支撑**：

- ***Learned helplessness and learned controllability: review* (2025)**：论述了 learned controllability 的核心机制——"Establishing a causal link between voluntary actions and desired outcomes enhances subjective perception of control, which may be perceived as rewarding, hence providing positive feedback to the learning process." 以及对免疫效应的论述——早期的可控经验能降低未来无助感形成的风险。原文："The goal-directed system assesses potential changes in outcomes"——这意味着过去的可控成功经验不是一次性的，而是积累为一种保护性认知资源。

- ***From digital anxiety to empowerment: older adults' assistive digital tools and digital literacy* (2026)**：*JMIR Aging*，N=480 老年人结构方程模型发现，sense of achievement 对 digital anxiety → intention to use 的关系有显著**调节效应**——成就感越高，焦虑对使用意愿的负面影响越弱。这直接支持了"过去成功经验能缓冲未来负面体验冲击"的免疫效应假设。

---

### 改进点8：区分「成功的质量」——自主成功 vs 依赖性成功

**当前问题**：`success_self` 和 `success_with_help` 只是 base_delta 不同（-5 vs -3），没有在 controllability 层面做区分。

**改进方向**：`success_self` 产生强烈的 controllability 修复效果和免疫积累；`success_with_help` 的修复效果取决于帮助是否保留了 agent 的主体性（即帮助质量），低质量帮助甚至可能增加 dependence 而不修复 helplessness。

**文献支撑**：

- ***Learned helplessness and learned controllability: review* (2025)**：对控制感的核心论述——"The perceived efficacy of **voluntary actions** in achieving desired goals provides essential feedback for developing a subjective sense of controllability." 关键词是 **voluntary**——如果成功是别人帮你做完的，你并没有学到"我的行动有效"，controllability 没有真正恢复。

- ***Older adults' digital technology experiences: a qualitative study* (2025)**：区分了两种成功路径——(1) 通过教导理解流程后自主完成 → 增强 autonomy；(2) 他人代替完成 → 增加 dependence。论文原文："Digital technology can support independence but **may increase dependence on others** without adequate support."

- ***Community-based digital intervention for low-income older people* (2024)**：发现低收入老年人在社区干预中即使完成了技术学习，如果没有真正理解过程，「ambivalence about the perceived utility and relevance of the smartphone」依然存在，自我效能并未得到有效修复。

---

## 三、改进策略一览

| # | 改进点 | 核心文献 |
|---|--------|---------|
| 1 | 降低结局标签直接权重，提升 perceived_uncontrollability 为主驱动 | *Learned helplessness and learned controllability: review* (2025); *Older adults' self-perception, technology anxiety, and intention to use digital public services* (2024) |
| 2 | 引入 task_self_efficacy 作为 helplessness 更新的核心中介 | *Older adults' self-perception, technology anxiety, and intention to use digital public services* (2024, β=-0.736); *Factors that influence technophobia in Chinese older patients with ischemic stroke* (2025); *Technophobia in digital health contexts: a systematic review and meta-analysis with a focus on older adults* (2025) |
| 3 | 纳入 felt_control 直接调节 helplessness 变化幅度 | *Learned helplessness and learned controllability: review* (2025); *Latent obstacles in older adults' digital health participation: a community-based hybrid cluster analysis with natural language processing* (2026) |
| 4 | 重复失败惩罚仅在不可控条件下触发 | *Learned helplessness and learned controllability: review* (2025); *Impact of regular smartphone use in decreasing technophobia and improving mental health and successful ageing for older adults* (2025) |
| 5 | 区分三种回避（无助/风险/低价值），仅无助性回避更新 helplessness | *Barriers to and facilitators of older people's engagement with web-based services* (2024); *Older adults' self-perception, technology anxiety, and intention to use digital public services* (2024, β=0.961); *Older adults' digital technology experiences: a qualitative study* (2025) |
| 6 | 支持从直接缓冲改为间接作用（经由 self-efficacy / felt_control） | *Barriers to and facilitators of older people's engagement with web-based services* (2024); *Older adults' digital technology experiences: a qualitative study* (2025); *Barriers and facilitators of eHealth use in older adults: a scoping review* (2021); *Community-based digital intervention for low-income older people* (2024) |
| 7 | 新增可控成功免疫效应（controllable_success_memory） | *Learned helplessness and learned controllability: review* (2025); *From digital anxiety to empowerment: older adults' assistive digital tools and digital literacy* (2026) |
| 8 | 区分自主成功 vs 依赖性成功的修复质量 | *Learned helplessness and learned controllability: review* (2025); *Older adults' digital technology experiences: a qualitative study* (2025); *Community-based digital intervention for low-income older people* (2024) |
