# 数字摩擦问卷与 Prompt 文献对齐方案（中国老年场景）

## 1. 目标

在不改核心机制（触发引擎、事件三分类）的前提下，把当前实验里的问卷与作答 Prompt 对齐到可追溯的经典构念，减少“题目像是随手写的”方法学风险。

## 2. 构念锚点（文献依据）

本实验建议采用“短量表拼接”：

- **技术接受/使用意愿**：TAM（感知有用性/易用性）  
  来源：Davis, 1989, MIS Quarterly.
- **行为意向与使用驱动**：UTAUT（绩效期望/努力期望/促进条件）  
  来源：Venkatesh et al., 2003, MIS Quarterly.
- **数字任务自我效能**：Computer Self-Efficacy  
  来源：Compeau & Higgins, 1995, MIS Quarterly.
- **掌控感/无助感反向维度**：Mastery（可作为无助构面的反向参照）  
  来源：Pearlin et al., 1981.
- **数字健康信息处理能力（老年常见场景相关）**：eHEALS  
  来源：Norman & Skinner, 2006, JMIR.

中国情境校准建议叠加使用：

- **中国互联网发展统计报告（老年群体）**：场景频率与渠道结构基线  
  来源：CNNIC 第55次报告（2025）。

## 3. 我们当前 10 题如何对齐

### 3.1 题目与构念映射

- `tech_acceptance` → TAM/UTAUT（总接受倾向）
- `trust_in_apps` → 信任构念（系统可信性）
- `avoidance_tendency` → 行为意向反向（回避倾向）
- `helpless_control_loss` → Mastery 反向（控制感缺失）
- `helpless_expect_failure` → 低自我效能/失败预期
- `helpless_effort_futile` → 习得性无助核心认知
- `helpless_low_self_efficacy` → 数字任务自我效能低
- `behavior_delay_online` → 行为后果：拖延
- `behavior_proxy_reliance` → 行为后果：代办依赖
- `behavior_offline_switch` → 行为后果：线上转线下

### 3.2 方法学注意点（必须执行）

- 每题只测一个构念，不混问“态度+行为”。
- 固定回忆窗口（建议“最近 7 天”），避免题间时间基准漂移。
- 行为题用频率措辞（“多常”）而非态度措辞（“是否赞同”）。
- 保留 0-100 连续评分，但后续分析按构念分组聚合。

## 4. Prompt 对齐改造（不改输出 schema）

以下只约束 LLM“如何回答”，不改问卷返回 JSON 结构。

### 4.1 题目生成/定义层（`surveys.py`）

建议每题标题增加统一前缀：

- `请基于最近7天的真实经历作答。`

作用：把全部评分锚定到同一时间窗口，减少随机波动。

### 4.2 题目分析层（`agent.py#do_survey` 的 analysis prompt）

新增 3 条规则：

1. 先判断题目属于哪一类：`acceptance / trust / helplessness / behavior`。
2. `memory_query` 必须优先检索“最近7天的具体事件”。
3. 若记忆不足，允许使用“中性默认值”，但不得极端打分。

### 4.3 作答层（`agent.py#do_survey` 的 answer system prompt）

新增 4 条规则：

1. 优先依据事件证据（做过/没做过、成功/失败、是否求助）。
2. 行为题按“发生频率”打分，态度题按“主观强度”打分。
3. 分数要与证据方向一致（多次失败→无助更高，不可反向）。
4. 仅输出合法 JSON 数值字段（保持当前解析链路兼容）。

## 5. 分析与报告口径（建议）

- 主指标：`survey_helplessness_index`、`survey_withdrawal_index`。
- 次指标：3 个行为后果单项（拖延/代办/转线下）。
- 报告时同时给：
  - 构念均值（组间比较）
  - 构念变化量（world_end - world_start）
  - 与事件暴露强度的相关方向（检验机制一致性）

## 6. 落地顺序（最小风险）

1. 先只改 prompt 文本（不改字段名、不改解析逻辑）。  
2. 跑 1 轮小样本（2 天 × 6 agent）检查分布是否过于极端。  
3. 再跑 paired-seed A/B（同 seed，改前 vs 改后）比较构念稳定性。  
4. 若波动过大，再调 `SURVEY_STATUS_BLEND_ALPHA`，不回退题目结构。

## 7. 参考文献与链接

1. Davis, F. D. (1989). *Perceived Usefulness, Perceived Ease of Use, and User Acceptance of Information Technology*. MIS Quarterly.  
   https://misq.umn.edu/guest/DISPLAY.PHP?ITEM=651
2. Venkatesh, V., et al. (2003). *User Acceptance of Information Technology: Toward a Unified View*. MIS Quarterly.  
   https://misq.umn.edu/guest/DISPLAY.PHP?ITEM=661
3. Compeau, D. R., & Higgins, C. A. (1995). *Computer Self-Efficacy: Development of a Measure and Initial Test*. MIS Quarterly.  
   https://misq.umn.edu/computer-self-efficacy-development-of-a-measure-and-initial-test.html
4. Pearlin, L. I., et al. (1981). *The Stress Process*. Journal of Health and Social Behavior.  
   https://pubmed.ncbi.nlm.nih.gov/203024/
5. Norman, C. D., & Skinner, H. A. (2006). *eHEALS: The eHealth Literacy Scale*. Journal of Medical Internet Research.  
   https://www.jmir.org/2006/4/e27/
6. CNNIC. (2025). *第55次中国互联网络发展状况统计报告*.  
   https://www.cnnic.net.cn/n4/2025/0117/c88-11229.html
