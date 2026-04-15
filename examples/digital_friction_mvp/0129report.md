# 0129 MVPreport 演讲稿（原稿归档）

## P1 标题页｜讲稿

今天汇报的是“数字摩擦 MVP：基于 AgentSociety 的最小闭环实验”。目标是把“数字摩擦/润滑剂如何影响无助感、信任与回避”做成一个可运行、可观测的模拟闭环，并输出阶段指标用于对比。实验输出目录对应 ID：`6b0cc2fb-05a1-4bc3-9251-7eb3eb9d9496`。

## P2 实现总览：MVP流程闭环｜讲稿

MVP 的执行链在 `main.py` 中构建。流程是：

1. `init_status()` 初始化画像与心理状态；
2. 一次 `SURVEY`（技术接受度）；
3. 进入每个阶段，先多次 `ENVIRONMENT_INTERVENE` 写入摩擦/润滑剂参数；
4. 触发 `trigger_event_shocks()`；
5. RUN 一天（`ticks_per_step=3600`，每步 1 小时）；
6. 阶段末执行 `monthly_settlement()`；
7. `SAVE_CONTEXT` 保存阶段快照到 `artifacts.json`；
8. 再做一次 `SURVEY`。

这条闭环让“环境变量变化 → 事件冲击 → 心理状态变化 → 阶段指标”可被观测。完整 workflow 顺序可在实验目录的 `experiment_info.yaml` 中核对。

## P3 阶段与环境参数设计｜讲稿

阶段配置在 `main.py` 的 `STAGES` 与 `STAGE_DAYS=2`。共有 3 阶段，每阶段 2 天：

- Stage1 `baseline_low_friction`：friction/malicious/complexity/risk/assist/accessibility/human_support 全部为 1；
- Stage2 `high_friction_low_assist`：摩擦类变量设为 3，辅助类设为 0；
- Stage3 `low_friction_high_assist`：摩擦类为 0，辅助类为 3，risk 为 1。

这些 0–3 是“强度档位”，不直接改变行为 block，而是进入事件概率公式，作用路径是环境变量 → 事件概率 → 状态变化。

这 7 个是环境强度参数，用于控制事件概率（不是直接改行为）。含义如下：

摩擦类（提高负面事件概率）

- friction：总体摩擦强度（流程繁琐、步骤多的综合感受）
- malicious：恶意摩擦（诱导/误导设计、暗坑、欺诈风险）
- complexity：复杂度（操作复杂、理解门槛高）
- risk：风险暴露（出错/被骗/资金风险强度）

润滑剂类（提高正面事件概率）

- assist：总体辅助程度（系统提示/引导是否充分）
- accessibility：适老化/无障碍程度（大字、语音、简化流程）
- human_support：人工支持程度（家人/社区/客服帮助）

它们只进入概率公式：

- 摩擦类 ↑ → 负面概率 ↑
- 润滑剂类 ↑ → 正面概率 ↑

## P4 事件触发机制（含公式）｜讲稿

核心函数是 `trigger_event_shocks()`：
先从 `current_intention` 匹配 4 个场景（广告误触/支付转账/打车/验证码），匹配失败则 20% 随机触发。

概率模型是：

`p_neg = 0.05 + 0.05*friction + 0.06*malicious + 0.04*complexity + 0.06*risk + 0.05*vision_limit + 0.04*past_fraud - 0.05*digital_experience`

`p_pos = 0.04 + 0.06*assist + 0.05*accessibility + 0.05*human_support + 0.03*digital_experience`

公式体现：摩擦越高、个体越脆弱 → 负面概率越高；辅助越强、经验越高 → 正面概率越高。
触发后用 `EVENT_SCENARIOS` 的正/负叙事文本进行干预。

## P5 状态更新与阶段结算｜讲稿

事件发生后立刻更新状态（在 `trigger_event_shocks()`）：

- 负面事件：helplessness +6、trust -8、avoidance +5、negative_event_count +1、failure_count +1
- 正面事件：helplessness -4、trust +5、avoidance -3、intercept_count +1、help_request_count +1、success_count +1

同时写入 `event_log`。

阶段末 `monthly_settlement()` 再次结算：

`helplessness += negative*3 + failure*2 - intercept*2 - success*1`

`trust += -negative*2 - failure*2 - friction*1 + intercept*2 + success*1 + assist*1`

`avoidance += negative*2 + failure*1 - success*1 - help*1`

然后清零计数器，并写入 `metric` 表。阶段快照通过 `SAVE_CONTEXT` 写入 `artifacts.json`。

### 技术化讲法（原稿补充）

在 `trigger_event_shocks()` 中，事件一旦触发会立即写入状态变量与过程计数器：

负面事件（negative）：

- `helplessness_score += 6`
- `trust_in_apps -= 8`
- `avoidance_tendency += 5`
- `negative_event_count += 1`
- `failure_count += 1`

正面事件（positive）：

- `helplessness_score -= 4`
- `trust_in_apps += 5`
- `avoidance_tendency -= 3`
- `intercept_count += 1`
- `help_request_count += 1`
- `success_count += 1`

同时写入 `event_log`（含 `day/t/scenario/outcome/message`）。

阶段末由 `monthly_settlement()` 进行汇总结算，以累计计数器为输入，再次更新状态：

`helplessness += 3*negative + 2*failure - 2*intercept - 1*success`

`trust += -2*negative - 2*failure - 1*friction + 2*intercept + 1*success + 1*assist`

`avoidance += 2*negative + 1*failure - 1*success - 1*help`

结算后将所有计数器清零，并通过 `db_writer.log_metric()` 写入阶段指标，同时由 `SAVE_CONTEXT` 保存阶段快照到 `artifacts.json`。

核心结构可以概括为：
“即时事件冲击（step-level） + 阶段结算（stage-level）”的双层更新机制。

## P6 结果与数据输出｜讲稿

实验输出位于：`agentsociety_data/exps/6b0cc2fb-...`

关键文件：

- `artifacts.json`：保存阶段快照（stage_1/2/3 的 helplessness/trust/avoidance 与 event_log）
- `metric_stage_summary.csv`：阶段均值
- `metric_full.csv`：阶段级指标记录

数据库 `sqlite.db` 中还保存了 `agent_status / agent_survey / agent_dialog / metric` 等表。
这些文件构成了可复现、可审计的证据链。

### 三类输出的具体含义（原稿）

1) 阶段状态（`artifacts.json`）

这是按阶段保存的“个体状态快照 + 事件日志”。它不是平均值，是每个 agent 的原始状态值。

文件内容（结构）：

- `stage_1_helplessness` / `stage_2_helplessness` / `stage_3_helplessness`
- `stage_1_trust` / `stage_2_trust` / `stage_3_trust`
- `stage_1_avoidance` / `stage_2_avoidance` / `stage_3_avoidance`
- `stage_1_events` / `stage_2_events` / `stage_3_events`

含义：

- 每个 `stage_*_helplessness` 是 `{agent_id: 分值}`
- `stage_*_events` 是 `{agent_id: [事件列表]}`
- 每条事件包含 `day, t, scenario, outcome, message`

2) 阶段均值（`metric_stage_summary.csv`）

这是把阶段状态汇总成群体平均值。汇报时常用的均值趋势从这里来。

字段示例：

- `helplessness_avg`
- `trust_avg`
- `avoidance_avg`
- `negative_event_avg`
- `intercept_avg`
- `help_request_avg`
- `success_avg`
- `failure_avg`

3) 阶段级指标（`metric_full.csv`）

这是数据库里记录的全量指标日志，包括阶段均值写入的记录。

特点：

- 会有 key 类似：
  - `baseline_low_friction.helplessness_avg`
  - `high_friction_low_assist.trust_avg`
- 每条都有 `key, value, step`
- 仍然是“阶段级”，不是逐步或逐日趋势

一句话总结给导师：

- `artifacts.json` = 每个 agent 的阶段原始状态 + 事件日志
- `metric_stage_summary.csv` = 阶段群体均值
- `metric_full.csv` = 阶段均值的数据库日志版（key/value）

## P7 结果展示：核心指标（图）｜讲稿

这三张图分别是：

- `metric_helplessness_avg.png`
- `metric_trust_avg.png`
- `metric_avoidance_avg.png`

阶段均值来自 `artifacts_stage_avg.csv`：

- Stage1：helplessness 44.958 / trust 60.833 / avoidance 42.167
- Stage2：helplessness 48.625 ↑ / trust 53.833 ↓ / avoidance 44.833 ↑
- Stage3：helplessness 46.958 ↓ / trust 58.833 ↑ / avoidance 43.667 ↓

结论：高摩擦低辅助阶段无助上升、信任下降；高辅助阶段信任回升、无助回落，方向符合设想。

### 原稿中的波动说明

和阶段设计直觉不完全一致：

- Stage1（低摩擦）反而下降
- Stage2（高摩擦）反而上升
- Stage3（高辅助）又回落

原因可能包括：

- 样本太小（6 agents）
- 事件次数少、LLM回答噪声大
- survey 结果容易被随机波动影响

## P8 结果展示：事件过程指标（图）｜讲稿

两张图分别是：

- `metric_negative_event_avg.png`
- `metric_success_avg.png`

从 `metric_stage_summary.csv` 可读出：

- baseline：negative_event_avg 0.5 / success_avg 0.0
- high_friction_low_assist：negative_event_avg 0.333 / success_avg 0.0
- low_friction_high_assist：negative_event_avg 0.166 / success_avg 0.5

说明在高辅助阶段，正面事件明显增加，负面事件减少，与阶段设计一致。

## P9 机制层不足｜讲稿

机制层主要问题：

1. 事件是概率注入，不是支付/打车 block 的真实结果触发；
2. `current_intention` 不稳定，缺失时退回随机触发；
3. 事件冲击强度固定（+6/-8 等常数），个体差异只影响概率；
4. 无助/回避变化不会反向影响行为计划，缺少闭环。

这些都在 `main.py` 的 `trigger_event_shocks()` 和 `monthly_settlement()` 体现。

## P10 数据层不足｜讲稿

数据层限制包括：

- 只有阶段均值，没有逐日/逐步趋势；
- Survey 只有 1 题（技术接受度）；
- 样本规模仅 6 个 agent，噪声大；
- 对话/行为痕迹在 sqlite 中偏少。

所以结果只能用于方向性验证，不适合做强统计推断。

## P11 改进方向：机制增强｜讲稿

“摩擦/润滑剂”写入真实行为链条，并形成可解释机制闭环。具体四点：

1. 把摩擦变量接入操作场景，而不是仅作为概率注入。  
2. 用事件叙事形成“转折点”，并写入 Stream Memory。  
3. 个体异质性决定冲击幅度。  
4. 形成“意图链—事件—状态—行为”的闭环（让回避倾向反向影响后续计划与行动）。

## P12 改进方向：数据与实验设置｜讲稿

数据层改进包括：

- 扩展问卷维度（信任、回避、线下意愿）；
- 记录逐日/逐步指标趋势；
- 扩大样本与模拟时长；
- 长周期实验增大步长（如 6h/12h/1day step）以控制成本；
- 结合文献或真实数据校准参数，提高解释力。

## P13 结语页｜讲稿

以上是 MVP 的技术实现、阶段结果、机制不足与改进方向。后续重点补齐行为闭环与长期趋势数据。谢谢老师。
