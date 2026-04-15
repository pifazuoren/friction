# Quantitative References for Helplessness Calibration

这个目录不是重新联网下载的重复副本，而是从上层 `paper/` 中挑出来的一组“最适合约束参数相对大小和合理区间”的论文拷贝。

## Included Papers

### 1. `learned_helplessness_and_learned_controllability_review_2025.pdf`
- 用途：提供最核心的理论约束。
- 能约束什么：
  - 失败应提高 helplessness
  - 成功应降低 helplessness
  - 连续失败应额外加重
  - 自主成功应强于被帮助成功
  - `failure_even_with_help` 应高于普通失败
- 局限：主要给相对顺序，不直接给事件级 delta 数值。

### 2. `older_adults_technology_anxiety_self_efficacy_digital_public_services_2024.pdf`
- 用途：提供 technology anxiety / self-efficacy / intention 的路径量化。
- 能约束什么：
  - 失败影响行为不是一步直达，而是先伤 self-efficacy / controllability
  - `avoid_without_attempt` 应小于真实失败
  - 帮助与自我效能恢复应有明显作用
- 你可重点找：
  - SEM 路径系数
  - 间接效应占比

### 3. `digital_feedback_health_information_anxiety_self_efficacy_2025.pdf`
- 用途：提供“高质量数字反馈/帮助”缓冲焦虑与提升 self-efficacy 的量化证据。
- 能约束什么：
  - `support_buffer` 不能太小
  - `success_with_help` 不能弱到几乎无恢复
  - 帮助质量应分档，而非简单有/无
- 你可重点找：
  - digital feedback -> self-efficacy 的 beta
  - self-efficacy -> anxiety 的 beta
  - 间接效应比例

### 4. `factors_influencing_technophobia_chinese_older_patients_2025.pdf`
- 用途：提供 self-efficacy / social support / eHealth literacy 的回归量化。
- 能约束什么：
  - `support_buffer` 是中等强度保护，不应强到把失败完全抹掉
  - self-efficacy 和 support 是稳定保护因素
  - 初始脆弱性底盘可以不低
- 你可重点找：
  - 多元回归 beta
  - Adjusted R²
  - technophobia 总体均值和标准差

### 5. `technophobia_in_digital_health_contexts_review_2025.pdf`
- 用途：提供 older adults technophobia 的 meta-level量级参考。
- 能约束什么：
  - 老年群体焦虑/恐惧底盘本身较高
  - 影响因素的相关强度范围可以作为参数上限参考
  - 不能把单次事件 delta 设得过大，否则几轮就超过真实人群差异尺度
- 你可重点找：
  - MD / SMD
  - 相关系数范围 `r`

### 6. `smartphone_psychological_wellbeing_technophobia_older_women_2025.pdf`
- 用途：提供训练/成功经验可累计降低 technophobia 的干预证据。
- 能约束什么：
  - 成功恢复应是“累积型”而非“一次归零”
  - `success_self` 与 `success_with_help` 应持续拉低 helplessness
  - 恢复项不能设成完全无效
- 你可重点找：
  - 干预前后均值变化
  - Cohen's d

## Recommended Mapping

如果你要把这些文献直接映射到代码参数，优先使用这套对应关系：

- `BASE_DELTAS`：
  - 主要由 1、2、6 约束相对顺序
- `SUPPORT_BUFFERS`：
  - 主要由 3、4 约束强度区间
- `UNCONTROLLABILITY_DELTAS`：
  - 主要由 1 加上任务场景文献共同约束
- `repetition_delta`：
  - 主要由 1 约束“单调上升但有上限”
- 初始 persona 脆弱性：
  - 主要由 4、5 约束

## Practical Note

这些文献更适合帮助你确定：

1. 哪些事件应该比哪些更伤
2. 帮助应有多大缓冲作用
3. 成功恢复应有多强
4. 参数不应大到什么程度

它们不太可能直接给出：

- `failure_after_attempt = +4`
- `success_self = -5`

这种事件级代码数值。
