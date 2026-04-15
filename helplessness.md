# Helplessness 更新规则说明

## 一句话定义

`helplessness` 不应该被“摩擦本身”直接更新，  
而应该被“经历一次尝试之后，个体是否学到了‘我努力也没用’”更新。

也就是说：

- 失败会提高 `helplessness`
- 成功会降低 `helplessness`
- 连续失败会额外加重
- 高不可控感会让失败更伤
- 高质量帮助会缓冲失败带来的上升
- 自主成功比帮助成功更能恢复 `helplessness`

---

## 1. 更新规则 -> 文献依据

先提醒一句：

- 下面文献支持的是 **方向、机制、相对强弱**
- 具体数值如 `+6`、`-3` 是 prototype 的参数化设定，不是论文原文直接给出的系数

相关总结可见：

- [paper conclusion.md](/Users/pifazuoren/Downloads/AgentSociety-main/paper%20conclusion.md)
- [literature_variable_code_map.md](/Users/pifazuoren/Downloads/AgentSociety-main/paper/literature_variable_code_map.md)

| 更新规则 | 主要文献依据 | 文献真正支持的意思 | 对应到模型 |
|---|---|---|---|
| 失败后 `helplessness` 上升 | `learned_helplessness_and_learned_controllability_review_2025.pdf` | 反复失败会让人学到“行动和结果无关” | 失败应作为 helplessness 的基础增量 |
| 成功后 `helplessness` 下降 | `learned_helplessness_and_learned_controllability_review_2025.pdf` | 可控感会保护人，成功经验会恢复“我做了有用” | 成功应降低 helplessness |
| 自主成功比帮助成功降得更多 | `learned_helplessness_and_learned_controllability_review_2025.pdf`; `digital_anxiety_to_empowerment_older_adults_2026.pdf` | 最强的保护是“我自己做成了”；成就感能缓冲焦虑 | `success_self` 的恢复幅度大于 `success_with_help` |
| 连续失败要额外加重 | `learned_helplessness_and_learned_controllability_review_2025.pdf`; `barriers_to_digital_health_adoption_in_older_adults_2026.pdf` | 失败不是孤立事件，失败会形成循环，回避会越来越稳定 | 增加 `consecutive_failures` 惩罚项 |
| 回避也会慢慢推高 helplessness | `barriers_to_digital_health_adoption_in_older_adults_2026.pdf` | 回避会减少练习机会，强化“我不行”的循环 | `avoid_without_attempt` 也要加 helplessness，但幅度小于真实失败 |
| 中途放弃比“没试就回避”更伤 | `learned_helplessness_and_learned_controllability_review_2025.pdf`; `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf` | 已经进入任务又卡住，更容易形成受挫感和无力感 | `abandon_midway` 增量应高于 `avoid_without_attempt` |
| 不是所有失败都一样伤人 | `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf`; `latent_obstacles_in_older_adults_digital_health_participation_2025.pdf`; `key_challenges_barriers_digital_literacy_older_adults_2026.pdf` | 有些失败是“可修正的”，有些失败会让人感觉系统根本不可控 | 加一个 `perceived_uncontrollability`，高不可控失败加更多 |
| 说明不清、界面乱、信息过载的失败更伤 | `older_adults_perceptions_of_technology_tablet_barriers_2017.pdf`; `barriers_and_facilitators_ehealth_use_older_adults_scoping_review_2021.pdf`; `latent_obstacles_in_older_adults_digital_health_participation_2025.pdf` | 老人最怕的不是单纯不会，而是“不知道哪里错、也没人解释清楚” | friction 不只影响成功率，还应放大 helplessness 增量 |
| 有帮助时失败也不一定一样伤 | `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf` | 高质量反馈能缓冲焦虑，帮助人重新建立处理能力感 | 失败时加 `support_buffer`，高质量帮助可减轻 helplessness 上升 |
| 帮助不是“有/无”，而是“质量高不高” | `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf`; `interventions_for_addressing_digital_exclusion_older_adults_2025.pdf`; `community_based_digital_intervention_low_income_older_people_2024.pdf` | 支持质量决定它是在增强 self-efficacy，还是只是替你做掉 | `support_quality` 最好分档，而不是二元变量 |
| self-efficacy 低的人，失败更容易转成 helplessness | `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`; `acceptance_of_digital_health_services_among_older_adults_2023.pdf` | 焦虑会通过 self-efficacy 起作用；self-efficacy 越低，越容易放弃 | 后续可让 `self_efficacy` 成为 helplessness 更新的放大器/缓冲器 |
| technology anxiety 高的人，失败后更容易不敢再试 | `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`; `technology_anxiety_loneliness_behavioral_intention_older_adults_2025.pdf`; `digital_health_technology_anxiety_systematic_review_2025.pdf` | 焦虑会压低使用意愿，且与资源、支持、自我效能相关 | 后续可让 `technology_anxiety` 影响“下次还试不试” |
| technophobia 可以作为长期脆弱性底盘 | `technophobia_in_digital_health_contexts_review_2025.pdf`; `factors_influencing_technophobia_chinese_older_patients_2025.pdf` | technophobia 是更稳定的长期恐惧/回避倾向 | 它适合放在 persona 初始值，而不是每轮大幅波动 |
| 帮助成功也能降低 helplessness，但不应超过自主成功 | `digital_anxiety_to_empowerment_older_adults_2026.pdf`; `smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf` | 训练、支持、成功体验都能降低恐惧和焦虑 | `success_with_help` 应为负向更新，但幅度小于 `success_self` |
| 如果帮助后仍失败，伤害可能更大 | `learned_helplessness_and_learned_controllability_review_2025.pdf`; `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf` | 连帮助都救不回来时，更容易形成“彻底没办法”的感觉 | `failure_even_with_help` 可以比普通失败更高 |

---

## 2. 规则核心思想

### 2.1 最核心的心理逻辑

不是“遇到麻烦 -> helplessness 上升”，  
而是“我努力了，但感觉努力没用 -> helplessness 上升”。

### 2.2 为什么要分自主成功和帮助成功

- 自主成功最能恢复“我自己能做到”
- 帮助成功也能恢复状态，但更像“有人帮我能做到”

所以：

- `success_self` 的下降幅度应大于 `success_with_help`

### 2.3 为什么要单独加连续失败惩罚

因为 helplessness 的核心不是一次失败，而是：

- 一次失败：可能只是运气不好
- 连续失败：开始怀疑自己
- 多次连续失败：学会“努力没用”

### 2.4 为什么帮助质量要分档

文献支持：

- 好帮助能增强 self-efficacy
- 差帮助可能只是替你做完，甚至让人更觉得自己不行

所以：

- `support_quality` 不能只做成 `0/1`

---

## 3. 压成代码规则表

## 3.1 核心更新公式

建议 v0.1 先用这条可解释的规则：

```text
H_next = clamp(
  H_now
  + base_delta
  + repetition_delta
  + uncontrollability_delta
  - support_buffer
  - recovery_bonus
)
```

其中：

- `H_now`：当前 helplessness，范围 `0-100`
- `base_delta`：由本轮结果类型决定的基础变化
- `repetition_delta`：连续失败带来的额外惩罚
- `uncontrollability_delta`：这次失败有多像“努力也没用”
- `support_buffer`：高质量帮助带来的缓冲
- `recovery_bonus`：成功经验带来的额外恢复

最后统一：

```text
clamp(x) = min(100, max(0, x))
```

---

## 3.2 输入变量表

| 变量名 | 类型 | 取值建议 | 作用 |
|---|---|---|---|
| `helplessness_now` | float | `0-100` | 当前无助感 |
| `outcome_type` | str | 见下表 | 本轮结果类型 |
| `consecutive_failures` | int | `0+` | 连续失败次数 |
| `support_quality` | int | `0/1/2` | 帮助质量：无/低/高 |
| `perceived_uncontrollability` | int | `0/1/2` | 这次失败的不可控感：低/中/高 |
| `ended_failure_streak` | bool | `True/False` | 这次成功是否终结了连续失败链 |
| `used_help` | bool | `True/False` | 本轮是否求助 |

---

## 3.3 结果类型 -> 基础更新值

| `outcome_type` | 含义 | `base_delta` 建议值 | 解释 |
|---|---|---:|---|
| `success_self` | 自主成功 | `-6` | 最强的可控感恢复 |
| `success_with_help` | 在帮助下成功 | `-3` | 有恢复，但弱于自主成功 |
| `failure_after_attempt` | 自主尝试后失败 | `+6` | helplessness 的核心上升事件 |
| `failure_even_with_help` | 求助后仍失败 | `+7` | 更容易形成“彻底没办法”的感觉 |
| `abandon_midway` | 尝试中途放弃 | `+5` | 比没试就回避更伤 |
| `avoid_without_attempt` | 没试就回避 | `+2` | 会固化回避，但弱于真实失败 |

---

## 3.4 连续失败惩罚

只对失败类事件生效：

- `failure_after_attempt`
- `failure_even_with_help`
- `abandon_midway`

建议规则：

```text
if consecutive_failures <= 1:
    repetition_delta = 0
else:
    repetition_delta = min(2 * (consecutive_failures - 1), 5)
```

对应效果：

| 连续失败次数 | `repetition_delta` |
|---:|---:|
| 1 | 0 |
| 2 | 2 |
| 3 | 4 |
| 4+ | 5 |

解释：

- 第一次失败，先记录基础伤害
- 第二次开始，进入“失败在积累”的阶段
- 第四次以后封顶，避免数值爆炸

---

## 3.5 不可控感惩罚

建议：

| `perceived_uncontrollability` | 含义 | `uncontrollability_delta` |
|---:|---|---:|
| 0 | 失败但原因明确、可修正 | `0` |
| 1 | 有点乱，不太清楚哪里出错 | `1.5` |
| 2 | 非常像“我怎么做都没用” | `3` |

解释：

- 普通失败不一定很伤 helplessness
- 真正伤的是“我完全控制不了结果”

---

## 3.6 帮助缓冲

建议：

| `support_quality` | 含义 | `support_buffer` |
|---:|---|---:|
| 0 | 无帮助 | `0` |
| 1 | 低质量帮助 | `1` |
| 2 | 高质量帮助 | `3` |

解释：

- 低质量帮助只能稍微缓冲
- 高质量帮助能显著缓冲失败带来的 helplessness 上升

这个缓冲主要用于失败类事件。

---

## 3.7 成功恢复奖励

建议：

### 对 `success_self`

- `recovery_bonus = 1`

### 对 `success_with_help`

- 如果 `support_quality == 2`，`recovery_bonus = 1`
- 否则 `recovery_bonus = 0`

### 额外建议

如果这次成功终结了连续失败链：

- 可再额外给 `+1` 的恢复奖励

但要保证：

- `success_self` 的总恢复 > `success_with_help` 的总恢复

---

## 3.8 v0.1 推荐完整规则

### 失败类

```text
H_next = clamp(
  H_now
  + base_delta
  + repetition_delta
  + uncontrollability_delta
  - support_buffer
)
```

### 成功类

```text
H_next = clamp(
  H_now
  + base_delta
  - recovery_bonus
)
```

成功后：

- `consecutive_failures = 0`

失败后：

- `consecutive_failures += 1`

---

## 3.9 推荐的 Python 伪代码

```python
def clamp_score(x: float) -> float:
    return max(0.0, min(100.0, x))


BASE_DELTAS = {
    "success_self": -6.0,
    "success_with_help": -3.0,
    "failure_after_attempt": 6.0,
    "failure_even_with_help": 7.0,
    "abandon_midway": 5.0,
    "avoid_without_attempt": 2.0,
}


UNCONTROLLABILITY_DELTAS = {
    0: 0.0,
    1: 1.5,
    2: 3.0,
}


SUPPORT_BUFFERS = {
    0: 0.0,
    1: 1.0,
    2: 3.0,
}


FAILURE_TYPES = {
    "failure_after_attempt",
    "failure_even_with_help",
    "abandon_midway",
}


SUCCESS_TYPES = {
    "success_self",
    "success_with_help",
}


def repetition_penalty(consecutive_failures: int) -> float:
    if consecutive_failures <= 1:
        return 0.0
    return min(2.0 * (consecutive_failures - 1), 5.0)


def recovery_bonus(
    outcome_type: str,
    support_quality: int,
    ended_failure_streak: bool,
) -> float:
    bonus = 0.0
    if outcome_type == "success_self":
        bonus += 1.0
    elif outcome_type == "success_with_help" and support_quality == 2:
        bonus += 1.0

    if ended_failure_streak:
        bonus += 1.0

    return bonus


def apply_helplessness_update(
    helplessness_now: float,
    outcome_type: str,
    consecutive_failures: int,
    support_quality: int,
    perceived_uncontrollability: int,
    ended_failure_streak: bool = False,
) -> float:
    base_delta = BASE_DELTAS[outcome_type]

    if outcome_type in FAILURE_TYPES:
        return clamp_score(
            helplessness_now
            + base_delta
            + repetition_penalty(consecutive_failures)
            + UNCONTROLLABILITY_DELTAS.get(perceived_uncontrollability, 0.0)
            - SUPPORT_BUFFERS.get(support_quality, 0.0)
        )

    if outcome_type in SUCCESS_TYPES:
        return clamp_score(
            helplessness_now
            + base_delta
            - recovery_bonus(
                outcome_type=outcome_type,
                support_quality=support_quality,
                ended_failure_streak=ended_failure_streak,
            )
        )

    return clamp_score(helplessness_now)
```

---

## 4. 最适合汇报时说的“人话”

你可以直接这么讲：

> 我们把 helplessness 看成一种会随经验变化的状态。它不是由摩擦本身直接决定，而是由个体在任务后是否学到“我努力有用”或“我努力没用”来决定。失败会提高 helplessness，成功会降低 helplessness；连续失败会额外加重，而高质量帮助会缓冲这种上升。其中文献支持最强的一点是：自主成功比在帮助下成功更能恢复可控感。

---

## 5. 后续校准建议

当前这套规则适合：

- prototype
- 早期实验
- 方向验证

后续可以继续校准的部分：

- `base_delta`
- 连续失败惩罚斜率
- `support_buffer`
- `uncontrollability_delta`

校准方式可以来自：

- 问卷前后变化
- 组间实验结果
- 文献中的方向性比较
- 未来的小样本回归

