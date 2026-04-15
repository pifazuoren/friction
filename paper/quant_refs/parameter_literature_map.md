# Helplessness Parameters -> Literature Constraints (Revised)

这份表的目标不是把论文统计结果“硬翻译”为代码里的事件级参数，而是更严格地回答三件事：

1. 哪些参数的**相对顺序**比较稳
2. 哪些参数的**合理量级**可以被文献弱约束
3. 哪些地方只能说是 **literature-constrained heuristic calibration**

换句话说：

- 这份表适合支持“为什么 `A` 应该大于 `B`”
- 这份表适合支持“为什么某个参数不应过大/过小”
- 这份表**不适合**支持“文献证明一次失败就应该 `+4`”

---

## 0. 使用规则

### 0.1 归一化锚点

建议继续把：

- `failure_after_attempt = 1.0 standard failure unit`

作为归一化锚点。

之后其他参数都先用“相对于一次标准失败”的比例来讨论，再映射回代码值。

### 0.2 证据强度分级

- `强`：文献对方向、相对顺序、机制解释都支持较好
- `中`：文献能支持方向和大致量级，但不能直接推出事件级参数
- `弱-中`：文献主要支持概念关系，量级更多依赖研究者校准

### 0.3 最安全的写法

最稳妥的说法不是：

> 文献证明 `success_self = -5`

而是：

> 我们没有将文献中的回归系数、路径系数或效应量直接等同为事件级状态增量，而是将其用作参数相对顺序、相对强弱和合理区间的约束依据；最终事件级参数是在这些约束下进行归一化和实验校准后得到的。

---

## 1. 修订后的映射表

| 参数 / 规则 | 主要来源 | 证据强度 | 文献可以安全支持什么 | 文献**不能**直接支持什么 | 启发式归一化区间（`failure_after_attempt = 1.0`） | 当前归一化值 | 判断 |
|---|---|---|---|---|---|---|---|
| `failure_after_attempt` | `learned_helplessness_and_learned_controllability_review_2025` | 强 | 失败应提高 helplessness，可作为标准失败单位 | 不能直接给出绝对事件增量 | 固定 `1.0` | `1.00` | 合理 |
| `failure_even_with_help` | `learned_helplessness...`; `digital_feedback_health_information_anxiety_self_efficacy_2025` | 中 | 如果高质量帮助本应缓冲，那么“有帮助仍失败”更接近高不可控失败，应高于普通失败 | 不能把 mediation beta 直接换算成事件级加分 | `1.15 ~ 1.40` | `1.25` | 合理 |
| `abandon_midway` | `learned_helplessness...`; `older_adults_perceptions_of_technology_tablet_barriers_2017` | 弱-中 | “已经进入任务又放弃”应高于单纯回避，但低于明确失败 | 缺少直接事件级量化证据 | `0.60 ~ 0.85` | `0.75` | 合理，但应弱化量化表述 |
| `avoid_without_attempt` | `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024` | 中 | 回避往往是经由效能感/有用性感知等中介累积形成，不应与显性失败等量 | 不能把中介占比直接翻成单轮 avoid delta | `0.20 ~ 0.40` | `0.25` | 合理 |
| `success_with_help` | `digital_feedback_health_information_anxiety_self_efficacy_2025`; `interventions_for_addressing_digital_exclusion_older_adults_2025` | 中 | 帮助成功必须有实质恢复作用，不能接近 0 | 不能由 feedback beta 直接推出单次恢复幅度 | `-0.50 ~ -0.80` | `-0.75` | 合理 |
| `success_self` | `learned_helplessness...`; `smartphone_psychological_wellbeing_technophobia_older_women_2025`; `digital_anxiety_to_empowerment_older_adults_2026` | 强-中 | 自主成功应是最强恢复项，并且恢复应可累计 | RCT 效应量不能直接等于“单次成功事件”的 delta | `-0.90 ~ -1.30` | `-1.25` | 合理 |
| `support_buffer` | `digital_feedback_health_information_anxiety_self_efficacy_2025`; `factors_influencing_technophobia_chinese_older_patients_2025` | 中 | 支持应是中等强度保护因素，不能弱到无效，也不能强到完全抹平失败 | 回归 beta 不能直接映射为 `buffer = x` | `low 0.00 ~ 0.10`; `mid 0.20 ~ 0.35`; `high 0.45 ~ 0.70` | `0 / 0.25 / 0.625` | 合理 |
| `uncontrollability_delta` | `learned_helplessness...`; `digital_feedback_health_information_anxiety_self_efficacy_2025` | 强-中 | “努力与结果脱钩”的主观不可控感应额外加重 helplessness，且高不可控应大于中不可控 | 缺少能直接锁定 `+1`、`+2` 的外部事件级证据 | `mid 0.20 ~ 0.35`; `high 0.40 ~ 0.70` | `0.25 / 0.50` | 合理 |
| `repetition_delta` | `learned_helplessness...`; `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024` | 强-中 | 连续失败应单调上升并逐渐饱和，不能指数爆炸 | 文献不能精确区分“第 2 次应加多少、第 3 次应加多少” | 第2次 `0.20 ~ 0.35`; 第3次 `0.35 ~ 0.60`; 第4次及以上 `0.50 ~ 0.80` | `0.25 / 0.50 / 0.75` | 合理 |

---

## 2. 本表最关键的“安全结论”

这张表目前最稳的，不是具体分值，而是下面这些**顺序约束**：

1. `failure_even_with_help > failure_after_attempt`
2. `abandon_midway > avoid_without_attempt`
3. `success_self > success_with_help`
4. `support_buffer` 应为中等强度，而不是 0 或“万能抵消器”
5. `repetition_delta` 应单调上升但饱和
6. `uncontrollability_delta` 应额外加重失败，但不应大过基础失败本身

如果论文正文只写这些，你的论证会很稳。

---

## 3. 哪些地方要避免过度声称

### 3.1 `abandon_midway`

这一项最适合写成：

> 文献支持“进入任务后受挫退出”比纯回避更具负面意义，但缺少直接事件级量化结果，因此这里只给出概念上与量级上的启发式区间。

不建议写成：

> 文献支持 `abandon_midway = 0.75`

### 3.2 `avoid_without_attempt`

最稳妥的写法是：

> 技术焦虑对行为意向的影响更多通过中介路径表现出来，因此单次回避不宜与单次显性失败等量齐观，但也不应为零。

不建议写成：

> 文献证明 avoid 的合理区间就是 `0.20 ~ 0.40`

### 3.3 `success_self`

最稳妥的写法是：

> 干预研究支持成功经验和技能掌握能显著降低 technophobia，因此自主成功应设为最强恢复项；但这类干预前后效应量并不等同于单次成功事件的状态变化幅度。

---

## 4. 关键证据，重新压成“参数语言”

### A. 为什么帮助不能太弱

`digital_feedback_health_information_anxiety_self_efficacy_2025` 的本地 PDF 文本可核到这些结果：

- digital feedback -> anxiety: `β = -0.396`
- digital feedback -> self-efficacy: `β = 0.700`
- self-efficacy -> anxiety: `β = -0.401`
- indirect effect: `β = -0.2806`

它们支持的是：

- 帮助/反馈是强保护因素
- `success_with_help` 不能几乎无恢复
- `support_buffer` 不能太小
- “有帮助仍失败”应更接近高不可控失败

它们**不**支持的是：

- 直接把 `0.700` 换成某个单次事件恢复分值

### B. 为什么回避不能和失败等量

`older_adults_technology_anxiety_self_efficacy_digital_public_services_2024` 支持：

- technology anxiety 对 behavior intention 没有显著直接作用
- 主要通过 `TA -> PU -> BI` 与 `TA -> SE -> PU -> BI` 等间接路径影响行为
- 其中两条路径分别占总效应 `37.7%` 与 `59.3%`

它支持的是：

- 回避更像累积后果，而不是和“明确失败”同等级的一次性打击

它**不**支持的是：

- 直接从 `37.7%`、`59.3%` 反推出 avoid 的事件级 delta

### C. 为什么自主成功必须强于帮助成功

`learned_helplessness_and_learned_controllability_review_2025` 强调：

- learned helplessness 的核心是“行动与结果脱钩”
- learned controllability 的核心是“行动有效”

`smartphone_psychological_wellbeing_technophobia_older_women_2025` 又给出：

- 技能训练后 technophobia 明显下降
- 干预组 technophobia 的前后变化效应量 `Cohen's d = 1.928`

它们共同支持的是：

- 成功经验确实有较强恢复作用
- “自己做成”应比“被帮助做成”更能恢复 controllability

它们**不**支持的是：

- “单次 success_self 就必须等于某个固定 d 值”

### D. 为什么支持不能设成“万能抵消器”

`factors_influencing_technophobia_chinese_older_patients_2025` 的本地 PDF 文本可核到：

- eHealth literacy: `β = -0.290`
- self-efficacy: `β = -0.138`
- social support: `β = -0.178`
- `R² = 0.372`, `adjusted R² = 0.353`

它支持的是：

- support 确实是保护因素
- 但它只是多因素系统的一部分
- 所以 support buffer 应明显有效，但不能大到“失败被完全抹掉”

---

## 5. 当前代码参数的归一化判断

当前代码若按 `failure_after_attempt = 4 -> 1.0` 归一化：

- `failure_even_with_help = 5 -> 1.25`
- `abandon_midway = 3 -> 0.75`
- `avoid_without_attempt = 1 -> 0.25`
- `success_with_help = -3 -> -0.75`
- `success_self = -5 -> -1.25`
- `support_buffer(mid) = 1 -> 0.25`
- `support_buffer(high) = 2.5 -> 0.625`
- `uncontrollability(mid) = 1 -> 0.25`
- `uncontrollability(high) = 2 -> 0.50`
- `repetition_delta = 1 / 2 / 3 -> 0.25 / 0.50 / 0.75`

结论仍然是：

**当前这一版在“相对大小”和“归一化量级”上是合理的。**

更准确地说：

- 它符合文献最稳的顺序约束
- 它没有明显越过文献可接受的量级上限
- 它依然应被表述为“在文献约束下校准出的启发式参数”

---

## 6. 论文/汇报里最建议使用的表述

建议用下面这段：

> We did not directly equate published regression coefficients, mediation effects, or intervention effect sizes with event-level parameter updates. Instead, we used the literature to constrain the relative ordering, plausible magnitude, and upper/lower bounds of key parameters. Specifically, learned helplessness and controllability theory constrained the ordering among failure, repeated failure, success, and controllability recovery; empirical studies on digital feedback, self-efficacy, technophobia, and social support further constrained the relative strength of support buffering, help-assisted recovery, and avoidance penalties. We then normalized all parameters against a standard failure unit (`failure_after_attempt = 1.0`) and selected final implementation values through simulation calibration.

---

## 7. 证据备注

### 7.1 关于 `digital_feedback_health_information_anxiety_self_efficacy_2025`

本地自动抽取 JSON 曾失败，但其核心系数已通过直接 PDF 文本提取重新核对：

- `β = -0.396`
- `β = 0.700`
- `β = -0.401`
- indirect effect `β = -0.2806`

因此，这篇论文可以继续保留在 map 中，但建议始终作为：

- “帮助强度和中介机制的量化约束来源”

而不是：

- “单次事件参数的直接来源”

### 7.2 这张表最适合的定位

最适合的名字其实是：

**parameter literature constraint map**

而不是：

**parameter derivation table**

前者是稳的，后者会被审稿人或老师追问。
