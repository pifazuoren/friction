# Helplessness Update Todo

这份文档把 `helplessness update` 的后续修改，整理成一个可逐步落地的阶段计划。

目标不是一次把机制改到最复杂，而是：

- 先保住当前 baseline
- 先把最核心的心理机制改对
- 再逐步把支持、回避、controllability 恢复这些层补进去

同时，这份计划遵循 [AgentSociety_Instructions.md](/Users/pifazuoren/Downloads/AgentSociety-main/AgentSociety_Instructions.md) 的基本思路：

- 不去改框架级 `run()` 主入口
- 主要在自定义 agent 的 `forward()` 编排和 `proto` 子模块里做机制改造
- 长期状态继续放在 `Status Memory`
- 事件与经历继续放在日志、stream 和记忆缓冲里

## 论文呈现顺序和工程实现顺序

这里还需要额外区分两件事：

- 论文里怎么讲
- 工程里怎么做

从工程角度，机制可以分阶段落地，逐步加变量、逐步调参。

但从论文和投稿角度，最终呈现出来的应当是一套**完整 mechanism**，而不是“只改了一半的 prototype”。这一点来自 [意见.md](/Users/pifazuoren/Downloads/AgentSociety-main/意见.md) 的提醒，也很重要：

- 如果 related work 里已经论证 support 更像间接修复机制
- 但模型实现里 support 仍然只是直接 buffer
- 审稿人很容易认为理论主张和实现不一致

因此，这份 todo 的正确使用方式是：

- 工程推进：按阶段逐步实现
- 论文叙事：最后要把 8 个改进点组织成一套完整机制，一起说明

---

## 理论核心和操作化核心

还有一个需要提前说清楚的问题，是 `felt_control` 和 `task_self_efficacy` 的关系。

理论上，`learned helplessness / learned controllability` 这一条线的核心概念是：

- `control`
- `controllability`
- `action-outcome contingency`

而不是 Bandura 意义上的 `self-efficacy` 本身。

但是从实现角度看：

- `task_self_efficacy` 更稳定，适合跨事件积累和衰减
- `felt_control` 更像当次任务 appraisal 的短期波动值

所以这里建议采用一套“理论层和实现层对齐，但不硬等同”的写法：

- 论文里：用 `control / controllability` 作为核心叙事
- 代码里：用 `task_self_efficacy` 作为主要可计算中介
- 同时让 `felt_control` 做事件层调节项

最稳的表述是：

> `task_self_efficacy` can be treated as an operationalized task-domain indicator of perceived control, while `felt_control` captures the immediate event-level fluctuation of controllability under the current task context.

## 文献使用原则

这里有一个原则要先说清楚：

- 文献可以很好地约束“哪一项应该比哪一项更重要”
- 文献可以约束“参数不应该太大或太小”
- 但文献通常不能直接推出“单次失败必须加几分”

因此，这份计划里所有参数性建议，都应理解为：

- literature-constrained heuristic calibration

而不是：

- paper-derived exact event delta

这一点和 [paper/quant_refs/parameter_literature_map.md](/Users/pifazuoren/Downloads/AgentSociety-main/paper/quant_refs/parameter_literature_map.md) 的写法保持一致。

## 动态推断与验证原则

这一节是给后续论文写作和审稿防御准备的。

如果目标是冲 CCF-B，仅仅把机制“改得更像文献”还不够，还必须提前说明：

- 为什么可以从现有文献推到 episode-level 的动态更新方向
- 为什么你们没有把横断面系数硬翻译成代码里的事件级增量
- 为什么这套机制虽然包含启发式校准，但仍然是可验证、可消融、可比较的

### 1. 动态推断的合法来源

这份计划里允许使用的动态推断，主要来自四类证据的组合，而不是来自任何单一论文：

- 第一类：`理论直接支持`
  - 用来约束因果主轴和变量层级，例如：
  - helplessness 的核心应放在 `control / controllability / action-outcome contingency`
  - controllability history 可能带来长期保护

- 第二类：`直接支持`
  - 用来约束路径结构和中介顺序，例如：
  - anxiety / feedback / support 往往不是直接决定行为，而是通过 `self-efficacy / usefulness / felt control` 等中介起作用

- 第三类：`邻近支持`
  - 用来约束变量是否应入模、哪些维度值得拆分、哪些关系方向较稳定，例如：
  - risk/value/tradition/image 这类 barrier typology
  - self-efficacy、social support、literacy 是常见保护因素

- 第四类：`内部参考`
  - 用来做归一化、量级约束和工程校准
  - 只能支持“相对顺序”和“合理区间”，不能在论文里冒充外部证据

### 2. 这份计划允许推断什么，不允许推断什么

最稳妥的说法是：

- 文献可以支持：
  - 哪个变量应是主驱动项
  - 哪个变量更适合做中介
  - 哪类路径应更强、哪类路径应更弱
  - 哪些回避类型应拆分
  - 哪些保护机制应被视为长期记忆

- 文献通常不能直接支持：
  - 一次 failure 必须 `+4`
  - 一次 success_self 必须 `-5`
  - 第 2 次连续失败应精确额外 `+1`
  - `controllable_success_memory` 的具体衰减常数

因此，最终代码中的事件级更新值，必须统一表述为：

- theory-grounded
- literature-constrained
- simulation-calibrated

而不是：

- directly estimated from human longitudinal data

### 3. 从横断面到动态机制，论文里应怎样解释

后续论文中，建议明确写出下面这条方法原则：

> We do not claim that cross-sectional SEM coefficients or regression effects directly identify event-level updates. Instead, we use them to constrain pathway ordering, mediator placement, relative strength, and plausible bounds. Event-level updates are then operationalized as theory-grounded and literature-constrained dynamic rules, and are evaluated through paired-seed comparison, ablation, and sensitivity analysis.

换成中文，就是：

- 横断面/定性/综述文献负责约束“方向、顺序、边界”
- 动态规则本身是研究者在这些约束下做出的操作化设计
- 动态规则的可信度，最终要靠对照实验、消融和敏感性分析来检验

### 4. 验证不是附录补丁，而是机制的一部分

如果目标是投稿，这份机制至少要接受四类验证：

- `paired-seed world comparison`
  - 比较同一 seed 下 A/B/C 世界的差值，而不是只看单次 run
- `ablation`
  - 去掉某个机制项后，看主指标是否按理论预期退化
- `sensitivity analysis`
  - 检查关键参数在合理区间内扰动时，结论方向是否稳定
- `human-facing anchoring`
  - 对至少一部分关键中介变量或分类结果，提供人工核查、访谈锚点或文本质检

### 5. 当前项目里已经可直接复用的验证基础

下面这些文件已经提供了比普通 prototype 更严谨的验证骨架，后续应明确并入论文方法部分，而不是只留在工程说明里：

- [examples/digital_friction_mvp/parallel_world.md](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/parallel_world.md)
  - 已经定义了 paired repeated design、主指标、配对差值、CI 和 Wilcoxon 方案
- [examples/digital_friction_mvp/analysis_parallel_paired.py](/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/analysis_parallel_paired.py)
  - 已经实现了 bootstrap CI、方向一致性统计和 paired world 聚合
- [paper/quant_refs/parameter_literature_map.md](/Users/pifazuoren/Downloads/AgentSociety-main/paper/quant_refs/parameter_literature_map.md)
  - 已经明确把参数定位为 literature constraint，而不是 paper-derived exact delta

### 6. 建议新增的最小验证矩阵

真正写论文时，最少建议补下面这组消融：

- `No-Uncontrollability`
  - 去掉 `perceived_uncontrollability` 主项，只保留 outcome 基础项
- `No-Efficacy-Mediator`
  - 去掉 `task_self_efficacy / felt_control`
- `No-Avoid-Split`
  - 把所有 avoid 重新并回一个桶
- `No-Control-Memory`
  - 去掉 `controllable_success_memory`
- `Direct-Support-Only`
  - support 只做 direct buffer，不走中介修复
- `No-Damping`
  - 去掉基础阻尼

最少建议报告的主指标是：

- `AttemptRate`
- `NegShare`
- `HelplessDelta`
- `TrustDelta`
- `AvoidanceDelta`

### 7. 最需要避免的三种过度声称

- 不要写成：
  - “文献证明一次失败就应增加多少 helplessness”
- 不要写成：
  - “LLM agent 的输出可直接替代真实人群参数”
- 不要写成：
  - “这组动态方程已被老年数字服务纵向研究直接验证”

最稳妥的写法应是：

- 这套动态规则是一个 theory-grounded simulation mechanism
- 它的方向、结构和相对强弱受现有文献约束
- 它的事件级形式和参数规模则通过 paired-seed 对照、消融实验和敏感性分析进一步检验

## 证据标签约定

为了避免把不同层级的文献写成同一种“支持”，下面各阶段的引用统一按以下标签理解：

- `理论直接支持`：直接支持核心理论主张，但不等于老年数字场景中的直接经验证据
- `直接支持`：在老年数字服务 / 数字健康 / 数字技术使用等直接相关场景里，能支持某个机制片段或路径结构
- `邻近支持`：支持方向和建模思路，但场景、样本或设计与目标问题不完全重合
- `方法启发`：方法论文或平台论文，主要用于启发实验组织、记录方式和验证思路
- `内部参考`：仅用于工程和校准，不是正式外部文献

---

## 第 0 阶段：冻结 baseline，补观测并固化多 seed 对照

### 目标

先保留当前版本，形成一个稳定的 `v0 baseline`，并跑出一组固定保存的多 seed 对照结果，后面所有修改都和它做对照。

### 这一阶段要改什么

这一阶段分两部分：

- 第一部分：补日志和分析字段，不改长期更新公式
- 第二部分：用当前版本跑完整 baseline，并把结果固定保存

建议在 `attempt_row` 或 `payload_json` 中显式保留：

- `outcome_type`
- `perceived_uncontrollability`
- `support_quality`
- `task_self_efficacy`
- `felt_control`
- `task_value`
- `avoid_reason_raw` 或 `avoid_reason_hint`
- `event_appraisal.source`
- `event_appraisal.confidence`

同时建议立刻跑一组固定 baseline：

- 至少 `10+ seeds`
- 至少覆盖 `4` 组 world 条件
- 将 summary、plot、config snapshot 固定保存到后续对照路径

### 主要代码位置

- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/proto/models.py`

### 为什么先做这个

因为后面每改一次公式，都要能回答：

- helplessness 上升主要是因为 `outcome`
- 还是因为 `perceived_uncontrollability`
- 还是因为 `task_self_efficacy` 已经很低
- 还是因为 `avoid` 被误判成 helplessness

如果这一层观测不先补齐，后面调公式很容易变成“看结果猜原因”。

如果 baseline 结果不先固定保存，后面每改一轮都要回头重跑旧版本，对照会很乱。

### 文献支持

1. `Exploring Large Language Model Agents for Piloting Social Experiments`

- 证据标签：`方法启发`

- 这篇方法论文的关键点，是把 LLM agent 当成 “silicon participants”，并强调要同时收集行为、问卷、访谈和条件信息。
- 对你们的直接启发是：在 prototype 阶段，结构化记录每轮条件和中间变量，本身就是合理的实验组织方式。

2. `AgentSociety: Large-Scale Simulation of LLM-Driven Generative Agents` (2025)

- 证据标签：`方法启发`

- 这篇平台论文强调 agent、environment、workflow、survey、interview 的统一组织。
- 对你们的启发是：你们现在已经不是单一 prompt 试验，而是一个结构化实验系统，因此中间状态必须留痕。

3. `Using Large Language Models to Simulate Multiple Humans and Replicate Human Subject Studies` (2022)

- 证据标签：`方法启发`

- 这篇文章提醒：LLM 模拟容易出现系统性偏差，不能只看最后结果是否“像”。
- 对你们的启发是：必须保留 baseline，并把关键中间变量记录下来，后面才知道偏差是从哪一步来的。

这里要特别说明：

- “冻结 baseline 并保存多 seed 对照”是你们的实验实践安排
- 它是受上述文献对结构化记录、条件控制和偏差警惕的启发
- 但不是这些论文直接提出的标准操作步骤

### 预期实验变化

- 日志补齐本身不会改变行为结果
- 但会显著提高你们后续做对照和解释的能力
- 同时会得到一组固定可复用的 baseline 数值结果，后续可以直接比较 delta 和趋势变化

### 完成判据

你能在一次 run 的 `attempt_row` 中清楚拆出：

- 这次 helplessness 为什么涨
- 是 outcome 导致
- 还是 uncontrollability 导致
- 还是 avoid 原因被混了

并且已经完成：

- 一组固定保存的 multi-seed baseline
- 后续所有阶段都默认与这组 baseline 做对照

---

## 第 1 阶段：降低 outcome 直接权重，提升 uncontrollability 主导性

### 目标

把长期 helplessness 从“事件记分器”改成“主观不可控感主导”的更新机制。

### 这一阶段要改什么

在 `state_update.py` 中：

- 整体缩小 `BASE_DELTAS`
- 提高 `UNCONTROLLABILITY_DELTAS` 的相对权重
- 先保留 `SUPPORT_BUFFERS`，但整体缩小
- 暂时不改 `repetition_delta` 的结构

建议的机制方向是：

```text
helplessness_delta
= small_base(outcome)
+ strong_uncontrollability_term
+ repetition_term
- small_support_term
```

### 主要代码位置

- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/uncontrollability_calibrator.py`

### 文献支持

1. `Learned helplessness and learned controllability: from neurobiology to cognitive, emotional and behavioral neurosciences`  
Frontiers in Psychiatry, 2025

- 证据标签：`理论直接支持`

- 这篇是整个机制的主理论骨架。
- 它最关键的结论不是“失败会伤人”，而是：
  - prolonged exposure to uncontrollable stressors may lead to learned helplessness
  - critical factor is lack of control
  - learned helplessness 的核心是 outcomes are independent of actions
- 对你们的直接启发是：
  - 长期 helplessness 的主驱动项应该是 `perceived_uncontrollability`
  - `outcome_type` 只能保留为弱事件信号，不能继续当主项

2. `Older adults’ self-perception, technology anxiety, and intention to use digital public services`  
BMC Public Health, 2024

- 证据标签：`直接支持`

- 这篇对 345 名老年人做 SEM，关键结果是：
  - `TA -> BI` 不显著，`β = 0.048`
  - `TA -> SE` 显著，`β = -0.736`
  - `SE -> PU` 显著，`β = 0.634`
  - `PU -> BI` 显著且最强，`β = 0.961`
- 对你们的启发是：
  - 单次负面事件不应直接大幅改长期状态
  - 中间必须经过主观解释层
  - 这支持“弱 outcome、强 uncontrollability”的方向

3. 内部参考：[paper/quant_refs/parameter_literature_map.md](/Users/pifazuoren/Downloads/AgentSociety-main/paper/quant_refs/parameter_literature_map.md)

- 证据标签：`内部参考`

- 这份映射表已经给出一个很稳的约束：
  - `uncontrollability_delta` 应额外加重失败
  - 但不应大过基础失败本身
- 这说明 Stage 1 的修改应是“提高权重”，不是“让 uncontrollability 完全吞掉所有其他项”。
- 它是你们自己的参数校准参考，不是外部学术文献；写论文时不能把它当作正式引用。

### 预期实验变化

- 高 friction 且高不可控的 world，helplessness 上升会更明显
- 同样失败但 felt control 尚未崩掉的情形，helplessness 不再机械上涨
- `success_self` 仍然会恢复 helplessness，但不再是唯一主导项

### 完成判据

你能在分析里清楚看到：

- 高不可控失败比普通失败更伤 helplessness
- 同样是 failure，差别开始主要来自 uncontrollability，而不是 outcome label

---

## 第 2 阶段：把 task_self_efficacy 接进长期更新，并让 felt_control 做事件层调节，同时加入基础阻尼

### 目标

让 helplessness 的长期变化真正经过一个心理中介层，而不是从 outcome 直接跳过去；同时开始把 `felt_control` 接成事件层调节项，并同步加入最基础的阻尼，避免反馈环在这一阶段就过快冲向极端值。

### 这一阶段要改什么

给 `HelplessnessUpdateInput` 增加：

- `task_self_efficacy`
- `felt_control`

然后在 `state_update.py` 中增加一个 `efficacy_loss_term` 或 `low_efficacy_multiplier`。

同时加入一个最基本的 `damping` 项，先控制极端爆炸，再去观察环路行为。可以先从很保守的写法开始，例如：

```python
# helplessness 越高，同样失败的边际冲击越小
damping = 1.0 - (helplessness_now / 100.0) * 0.3
effective_delta = raw_delta * damping
```

建议方向：

```text
helplessness_delta
= small_base(outcome)
+ uncontrollability_term
+ repetition_term
+ efficacy_loss_term
+ control_loss_term * event_weight
- mastery_recovery_term
- tiny_support_term
```

其中建议：

- `task_self_efficacy` 作为较稳定的任务域中介
- `felt_control` 作为本轮事件层调节项
- 不要把两者都做成等权主项，避免重复计数
- `damping` 先做成基础稳定器，不追求一步到位

### 主要代码位置

- `examples/digital_friction_mvp/proto/models.py`
- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`

### 文献支持

1. `Older adults’ self-perception, technology anxiety, and intention to use digital public services`  
BMC Public Health, 2024

- 证据标签：`直接支持`

- 这篇最重要的启发，不是焦虑本身，而是：
  - `TA -> SE = -0.736`
  - `SE -> PU = 0.634`
  - `SE -> BI` 不显著
- 这说明：
  - 自我效能不是结果终点
  - 但它是从负面体验走向后续行为变化的关键中介层
- 对机制的直接翻译就是：
  - failure 不应该直接大幅推高 helplessness
  - 更合理的是先伤 `task_self_efficacy`
  - 再由较低效能感推动 helplessness 上升

2. `Learned helplessness and learned controllability: from neurobiology to cognitive, emotional and behavioral neurosciences`  
Frontiers in Psychiatry, 2025

- 证据标签：`理论直接支持`

- 这篇的核心概念是 control，而不是 efficacy。
- 它强调：
  - helplessness 的核心是行动与结果脱钩
  - controllability 的恢复来自重新建立 voluntary action 和 desired outcome 的因果联系
- 对你们的启发是：
  - 论文叙事里应以 `control / controllability` 为核心
  - 代码里再用 `task_self_efficacy + felt_control` 去操作化它

3. `Factors that influence technophobia in Chinese older patients with ischemic stroke`  
BMC Geriatrics, 2025

- 证据标签：`邻近支持`

- 这篇研究指出：
  - education level、monthly income、number of smart devices、eHealth literacy、self-efficacy、social support 都是 technophobia 的显著影响因素
  - 其中 `self-efficacy` 是一个明确的保护因素之一
  - 上述 6 个变量组成的回归模型可解释 `35.3%` 的总变异
- 对你们的启发是：
  - 在中国老年人情境里，把 `task_self_efficacy` 放进长期状态更新是有本土实证支撑的

4. `Technophobia in digital health contexts: A systematic review and meta-analysis with a focus on older adults` (2025)

- 证据标签：`邻近支持`

- 这篇 19 项研究的综述/元分析指出：
  - older adults 的 technophobia 显著偏高
  - 在行为层面，low self-efficacy 被识别为显著风险因素
  - 该元分析中，跨生态层各类相关因素的总体相关系数范围为 `r = -0.537 to 0.235`
- 对你们的启发是：
  - 低效能感不只是短期情绪噪声
  - 它可以被视为长期脆弱性结构的一部分

5. `The mechanism of digital feedback on health information anxiety among older adults` (2025)

- 证据标签：`直接支持`

- 这篇对 1713 名中国老年人的研究表明：
  - digital feedback -> anxiety：`β = -0.396`
  - digital feedback -> self-efficacy：`β = 0.700`
  - self-efficacy -> anxiety：`β = -0.401`
  - indirect effect：`β = -0.2806`
- 对你们的启发是：
  - 自我效能确实是外部经历影响长期心理状态的重要中介路径

### 额外说明

- `damping` 这一项主要是工程上的稳定性设计，不是直接从某篇论文里抄出一个事件级公式
- 论文里更稳的写法是：它是一个 `bounded-state heuristic`，与 helplessness / controllability 文献中“负面状态不会无限线性累积”的叙事相容
- 如果需要一句更直观的解释，可以写成：当 agent 已经接近稳定被动状态时，再来一次同类型失败，边际伤害应小于早期失败
- 它的具体数值应视为 `literature-constrained heuristic calibration`

### 预期实验变化

- 同样失败的两个 agent，helplessness 涨幅不再一致
- 高 `task_self_efficacy` agent 会更耐挫
- 低 `task_self_efficacy` agent 会更快进入负向循环

### 完成判据

你能解释：

- 为什么 outcome 相同，但 helplessness 的变化幅度不同
- 并且这种差异能被 `task_self_efficacy` 合理解释

同时系统不会因为这一轮改动，马上把大量 agent 推到 `100` 或 `0`。

---

## 第 3 阶段：拆分 avoid，避免把所有回避都当成 helplessness

### 目标

把行为层和心理层分开，减少“把所有不做都算成 helplessness”的误判。

### 这一阶段要改什么

给 `avoid_without_attempt` 增加原因分类。

至少分成：

- `helpless_avoid`
- `risk_avoid`
- `low_value_avoid`

然后让长期更新只对 `helpless_avoid` 明显加分。

建议行为层逻辑：

- `helpless_avoid`：主要由低 control、低 efficacy、连败累积触发
- `risk_avoid`：主要由高 risk、诈骗担忧、错误后果担忧触发
- `low_value_avoid`：主要由低 `task_value` / 低 `perceived_usefulness` 触发

### 主要代码位置

- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/outcome_model.py`
- `examples/digital_friction_mvp/proto/llm_psychology.py`
- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/agent.py`

### 文献支持

1. `Barriers to and Facilitators of Older People’s Engagement With Web-Based Services: Qualitative Study of Adults Aged >75 Years`  
JMIR Aging, 2024

- 证据标签：`直接支持`

- 这篇 qualitative study 最大的价值是把“为什么不继续做数字任务”拆开了。
- 它揭示的不是简单“不会用”，而是：
  - 怕按错
  - 怕转错钱
  - 怕被骗
  - 网站改版后原来学会的路径失效
  - 线下更安心
- 对你们的启发是：
  - `avoid` 的来源至少有一部分不是 helplessness
  - 如果不拆开，后面会把 risk avoidance 和 helplessness avoidance 混在一起

2. `Older adults’ self-perception, technology anxiety, and intention to use digital public services`  
BMC Public Health, 2024

- 证据标签：`直接支持`

- 这篇说明：
  - `PU -> BI = 0.961` 是最强路径
- 对你们的启发是：
  - 有些“不想做”，更像是“觉得不值得”
  - 这类 low-value avoidance 不应直接推高 helplessness

3. `Acceptance of digital health services among older adults` (2022)

- 证据标签：`直接支持`

- 这篇表明：
  - 更高的 perceived usefulness
  - 更强的 self-efficacy
  - 更多 family/formal support
  - 会带来更高的 intention
- 对你们的启发是：
  - 基于这篇论文和前述研究，我们在模型上把 use intention 视为多因素产物
  - 因此它不宜被粗暴并入 helplessness

4. `Older adults' digital technology experiences: a qualitative study`  
BMC Digital Health, 2025

- 证据标签：`邻近支持`

- 这篇强调：
  - 老年人对数字技术常常是 mixed feelings
  - 同一个人也可能在不同任务上有不同偏好
- 对你们的启发是：
  - 有些 avoid 本质上是 preference，不是 helplessness

### 实现建议

这一阶段不建议用纯规则，也不建议直接把全部判断塞给 LLM。

建议采用和 `uncontrollability_calibrator` 类似的 hybrid 方式：

- 规则先按 `risk_level / task_value / recent_failures / felt_control / task_self_efficacy` 给初判
- LLM 只在边界样本上做辅助修正

### 分类可靠性补充

这一阶段最好不要只做“分类后看曲线”，还要补一个最小的分类可靠性检查。

建议：

- 从 `avoid_without_attempt` episode 中随机抽一个子集做人工复核，例如 `100-200` 条或总量的 `5%-10%`
- 由至少两名标注者按 `helpless_avoid / risk_avoid / low_value_avoid / other` 独立标注
- 报一个最基本的一致性指标，例如 percent agreement 或 Cohen's kappa
- 如果一致性太低，就先收紧规则、减少边界样本的 LLM 自由度，必要时把类型先简化

论文里可以把这一步写成：对 `avoid_reason` 这一“注释型中间变量”做最小人工锚定，而不是把它当成无需验证的真值。

### 预期实验变化

- 总 avoid rate 可能不变
- 但 helplessness 曲线会更干净
- 高 risk world 中，一部分 avoid 不再被错误计入 helplessness

### 完成判据

后续分析图里，你可以把 avoid 分成三类，而不是只给一个总桶。

---

## 第 4 阶段：加入 controllability 的长期保护效应

### 目标

在 avoid 输入已经清理过之后，再把“可控成功如何形成保护”接进机制里，让系统不只会学到 helplessness，也会学到 controllability。

### 这一阶段要改什么

引入一个长期记忆量，例如：

- `control_mastery_memory`
- 或 `controllable_success_memory`

它的作用：

- 累积高质量自主成功
- 随时间缓慢衰减
- 在未来高 friction 任务中，降低 helplessness 的增长敏感度

这一阶段先不要求把 dependence 完全拉出来，只需要先把 controllable success 的保护作用接进主链。

这里要特别说明：

- `controllable_success_memory` 是一个 theory-grounded operationalization
- 它不是老年数字服务文献里被直接测量和命名的现成变量
- 它更像是把“成功被归因为自己可控制、可复现”这一长期保护痕迹，操作化成可计算状态

### 操作化建议

这里需要把 `task_self_efficacy` 和 `controllable_success_memory` 明确区分开，否则审稿人会自然追问“为什么不用一个变量就够了”。

建议分工：

- `task_self_efficacy`：中速变化，表示“我现在觉得自己做这类任务能不能行”；它更容易被最近几轮成败、反馈质量、求助体验改变
- `controllable_success_memory`：慢速变化，表示“我过去是否反复积累过自己可控地做成任务的证据”；它不该被每次普通成功都快速推高，也不该像 `task_self_efficacy` 一样频繁起伏

建议把“高质量自主成功”限定为同时满足以下条件：

- 本轮任务确实完成，而不是中途退出或由别人完全代做
- 主体性仍在本人身上：`success_self` 给予最强积累；`success_with_help` 只有在 `enabling_support` 且不是 substitutional takeover 时才给较小积累
- `felt_control` 达到中高水平，且 `perceived_uncontrollability` 维持在较低水平
- 最好再加一个“可复现 / 理解到位”信号，例如任务后自述把握感、是否能解释关键步骤、或一个简化的 `mastery_flag`
- 纯运气成功、看不懂为什么成功、被别人代做后的成功，不应积累到这个长期记忆项里

如果需要更明确的工程落地，可以把它写成：

```text
M_{t+1} = clip((1 - rho_m) * M_t + mastery_gain_t, 0, 1)

mastery_gain_t > 0, only if episode_t is a high-quality controllable success
```

其中：

- `rho_m` 是慢速衰减常数，明显慢于 `task_self_efficacy` 的衰减
- `mastery_gain_t` 可按 `success_self > enabling_help_success > 0` 设计成分级增量
- 如需排除 trivial case，可以再乘一个 `difficulty_weight`

### 在公式里的作用形式

`controllable_success_memory` 最稳的写法不是“固定减一个保护分”，而是“降低后续负向压力对 helplessness 的敏感度”。

因此建议写成：

```text
positive_pressure_t =
  weak_outcome_term
  + uncontrollability_term
  + repetition_term
  + low_efficacy_term
  + event_control_loss_term
  + helpless_avoid_term

repair_t =
  indirect_support_repair
  + mastery_recovery_term

Delta_t =
  positive_pressure_t * (1 - protection(M_t))
  - repair_t
```

这里的含义是：

- `mastery_recovery_term` 表示“本轮确实做成并感到自己掌控”的即时恢复
- `protection(M_t)` 表示长期 controllability memory 对未来负向冲击的乘性调节
- 这两个都和 success 有关，但不是一回事：一个是当下恢复，一个是未来敏感度下降

论文里如果想写得更紧，可以明确一句：

- `task_self_efficacy` 进入 `positive_pressure_t`，因为它决定当前是否脆弱
- `controllable_success_memory` 进入 `protection(M_t)`，因为它决定未来负向压力打进来时有多伤

### 主要代码位置

- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/models.py`

### 文献支持

1. `Learned helplessness at fifty: Insights from neuroscience`  
Psychological Review, 2016

- 证据标签：`理论直接支持`

- 这篇最关键的改写是：
  - passivity 不是后来才学会的
  - control 才是后天学到、并能抑制 helplessness 的那一部分
- 对你们的启发是：
  - `controllable_success_memory` 更适合被写成“长期保护性抑制项”
  - 而不是把 success 简单记成一个正向分数

2. `Learned helplessness and learned controllability: from neurobiology to cognitive, emotional and behavioral neurosciences`  
Frontiers in Psychiatry, 2025

- 证据标签：`理论直接支持`

- 这篇明确指出：
  - controllability may also be trained and learned
  - previous experiences of control can reduce susceptibility to helplessness
  - controllability experience 具有长期保护作用
- 这不是边角发现，而是 learned controllability 这条线最核心的推论之一。
- 对你们的启发是：
  - 不能只建模 helplessness 的累积
  - 也要建模 controllability 的长期恢复和免疫作用

3. `From Digital Anxiety to Empowerment in Older Adults: Cross-Sectional Survey Study on Psychosocial Drivers of Digital Literacy`  
2026

- 证据标签：`邻近支持`

- 这篇对 480 名中国老年人做问卷和 SEM。
- 它指出：
  - family support 会降低 digital anxiety
  - social influence 会提高 intention
  - `sense of achievement` 会削弱 anxiety 对 intention 的负向影响
- 对你们的启发是：
  - 成就感不应只被看成一次性的情绪奖励
  - 但把它进一步操作化为长期保护性 `memory` 项，仍然属于你们的模型解释，不是原文直接测得的状态变量

4. `Experiences of a Community-Based Digital Intervention Among Older People Living in a Low-Income Neighborhood: Qualitative Study`  
JMIR Aging, 2024

- 证据标签：`邻近支持`

- 这篇 qualitative study 的关键点不是“完成了干预就一定变好”，而是：
  - 受访者虽然完成了社区数字干预
  - 但如果工具和日常生活关联不强，或只是跟着志愿者做完
  - sustained use、self-efficacy 和继续学习意愿仍然可能不稳
- 对你们的启发是：
  - 不是所有 completion 都会形成长期保护
  - `controllable_success_memory` 应更偏向记录“真正理解并感到自己做成”的 mastery，而不是任何一次表面成功

5. `Role of smart phones in improving psychological well-being and successful ageing of Iranian old women living with Technophobia`  
BMC Research Notes, 2025

- 证据标签：`邻近支持`

- 这是随机对照试验。
- 研究显示：
  - 9 次智能手机技能训练后
  - 论文报告 technophobia 显著下降
- 对你们的启发是：
  - 技能掌握带来的保护作用可以被视为可积累效应，而不只是单次恢复
  - 但由于样本语境较窄，这篇更适合作为弱到中等的干预支持，而不是主支撑文献

### 预期实验变化

- 早期形成高质量 controllable success 的 agent，在 shock stage 中不会那么快塌
- 同样遇到高 friction 时，不同 agent 会因为过去的 mastery history 出现不同敏感度
- “被动完成一次”和“真正学会一次”开始在后续轨迹上拉开差距

### 完成判据

你能开始讲：

- helplessness 如何累积
- controllability 如何恢复
- 为什么过去的成功经验会改变后续脆弱性
- 为什么不是所有 success 都会形成同样强的保护
- 为什么 `task_self_efficacy` 和 `controllable_success_memory` 不是同一个变量
- 为什么 `controllable_success_memory` 在公式里更像 moderator，而不是固定减项

---

## 第 5 阶段：把 support 从“直接回血”改成“以间接修复为主”

### 目标

让 support 更像真实帮助，而不是一个万能减分器。

### 这一阶段要改什么

把 support 的作用分成两层：

第一层，短期作用到中介变量：

- `expected_help_effectiveness`
- `felt_control`
- `task_self_efficacy`

第二层，再由这些中介变量间接影响长期 helplessness。

工程上建议保留一个很小的 direct buffer，但把主要效果迁到中介路径。

### 主要代码位置

- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/llm_psychology.py`

### 文献支持

1. `Older adults' digital technology experiences: a qualitative study`  
BMC Digital Health, 2025

- 证据标签：`邻近支持`

- 这篇明确指出：
  - support and education are essential
  - without adequate support, older persons may become more dependent on others
- 这说明 support 的关键作用不是“直接把状态减掉一点”，而是：
  - 决定任务之后个体是更自主，还是更依赖

2. `Barriers to and Facilitators of Older People’s Engagement With Web-Based Services`  
JMIR Aging, 2024

- 证据标签：`直接支持`

- 这篇强调帮助需要：
  - continuous
  - patient
  - repeatable
- 对你们的启发是：
  - support 不是一个静态二元变量
  - 它更像“帮助能否真正修复 control 和 willingness”

3. `The mechanism of digital feedback on health information anxiety among older adults` (2025)

- 证据标签：`直接支持`

- 关键结果：
  - digital feedback -> anxiety：`β = -0.396`
  - digital feedback -> self-efficacy：`β = 0.700`
  - self-efficacy -> anxiety：`β = -0.401`
  - indirect effect：`β = -0.2806`
- 对你们的启发是：
  - support / feedback 的主要作用路径可以经过 `self-efficacy`
  - 但原文同时报告了 direct effect，因此这里更适合支持“间接路径显著存在”，而不是“只能间接起作用”

4. `Factors that influence technophobia in Chinese older patients with ischemic stroke`  
BMC Geriatrics, 2025

- 证据标签：`邻近支持`

- 这篇邻近场景横断面研究显示：
  - self-efficacy 是保护因素
  - social support 也是保护因素
  - 但 support 只是多因素系统中的一部分，不是万能项
- 对你们的启发是：
  - 在中国老年数字健康邻近场景里，support 可以被建模成明显但非万能的保护因素
  - 更稳妥的实现是把它作为多因素系统的一部分，而不是单一大缓冲项

5. `Barriers and facilitators to the use of e-health by older adults: a scoping review` (2021)

- 证据标签：`邻近支持`

- 这篇综述指出：
  - self-efficacy 不足
  - 缺知识
  - 缺支持
  - 功能性不足
  - 缺少关于 usefulness 的清楚说明
  - 都是主要障碍
- 对你们的启发是：
  - support 的作用最好是“先提理解、提控制、提效能”
  - 而不是直接给 helplessness 减分

### 推荐的小扩展

把 support 再分成：

- `enabling_support`
- `substituting_support`

含义：

- `enabling_support`：帮助理解流程，保留主体性
- `substituting_support`：别人代做，任务成功但 agency 修复较弱

### 预期实验变化

- support 对成功率的提升不一定立刻更大
- 但对后续 `attempt_self` 的促进会更明显
- `success_with_help` 内部会出现质量差异

### 完成判据

你能解释：

- 为什么同样是“求助后成功”
- 有的 agent 后面更敢自己试
- 有的 agent 只是越来越依赖帮助

---

## 第 6 阶段：反馈环路行为分析

### 目标

在基础阻尼已经加入之后，系统性分析动态反馈环的行为特征，把“稳定、崩塌、恢复”从工程现象提炼成可分析的 research finding。

### 这一阶段要改什么

重点不是第一次去补阻尼，而是分析这条环：

```text
helplessness
-> strategy choice
-> outcome
-> task_self_efficacy / felt_control
-> helplessness
```

这一阶段建议重点检查：

- 现有基础阻尼是否足够
- repeated failure 是否需要饱和项
- controllability memory 是否需要更严格的上限与衰减
- 哪些 world 更容易触发快速崩塌
- 哪些保护机制真正让系统稳定下来

### 主要代码位置

- `examples/digital_friction_mvp/proto/experience_memory.py`
- `examples/digital_friction_mvp/proto/state_update.py`
- `examples/digital_friction_mvp/proto/models.py`

### 文献支持

1. `Learned helplessness and learned controllability: from neurobiology to cognitive, emotional and behavioral neurosciences`  
Frontiers in Psychiatry, 2025

- 证据标签：`理论直接支持`

- 这篇明确指出：
  - helplessness 和 controllability 都是通过经验逐步学习出来的
  - previous experiences of control can reduce susceptibility to helplessness
- 对你们的启发是：
  - 这本来就是一个动态反馈系统
  - 稳定性、加速崩溃和免疫效应，都应该出现在仿真分析里

2. `Barriers to Digital Health Adoption in Older Adults: Scoping Review Informed by Innovation Resistance Theory` (2026)

- 证据标签：`邻近支持`

- 这篇指出：
  - low self-efficacy 和 technology anxiety 会形成循环
  - 这些 feedback loops 会在 repeated negative experience 下持续强化 avoidance behaviors
- 对你们的启发是：
  - 动态循环本身就是机制的一部分
  - 不能只看单轮事件，还要看系统是否会锁死在某种轨道

3. `Older adults’ self-perception, technology anxiety, and intention to use digital public services`  
BMC Public Health, 2024

- 证据标签：`直接支持`

- 这篇虽然是横断面 SEM，但它清楚表明：
  - anxiety
  - self-efficacy
  - usefulness
  - intention
 之间不是一跳完成，而是层层传导
- 对你们的启发是：
  - 如果仿真里每一轮都直接强推极端状态，就会和这种层层传导结构不匹配
  - 但这篇更多是旁证，不是 Stage 6 反馈环路论证的主文献

### 预期实验变化

- 极端 world 中，曲线不会太快贴边
- 中间型 agent 会更多，异质性更明显
- 你们可以开始研究：
  - 哪些条件下系统会稳定
  - 哪些条件下会快速崩塌
  - 基础阻尼、support 间接化、controllable success memory 分别贡献了什么

### 完成判据

你能回答：

- 为什么系统没有过快塌到极端
- 哪些 world 条件更容易触发恶性循环
- 哪些保护机制真正让系统稳定下来

---

## 最推荐的实际推进顺序

按最稳路线，建议这样推进：

1. 第 0 阶段：冻结 baseline，补日志并固定 multi-seed baseline
2. 第 1 阶段：弱化 outcome，强化 uncontrollability
3. 第 2 阶段：把 `task_self_efficacy` 接进长期更新，并让 `felt_control` 做事件层调节，同时加入基础阻尼
4. 第 3 阶段：拆分 avoid，并采用 `rule + LLM hybrid` 分类
5. 第 4 阶段：加入 `controllable_success_memory`
6. 第 5 阶段：support 改成间接作用为主
7. 第 6 阶段：分析反馈环路行为特征

---

## 当前最值得先做的最小版本

如果只是为了继续调试工程，最小可行版建议先完成前 4 步：

- 保留 baseline
- 先让 `perceived_uncontrollability` 成为主项
- 再把 `task_self_efficacy + felt_control + damping` 接进来
- 再把 avoid 拆开

如果是为了后续论文机制成型，最小完整版至少应做到前 6 步：

- baseline 固定保存
- `uncontrollability` 主导
- `task_self_efficacy + felt_control + damping`
- avoid 分类
- `controllable_success_memory`
- support 间接化

因为论文里最后呈现的，不应是“改了一半的 prototype”，而应是一套前后自洽的完整 mechanism。

---

## 论文 Mechanism Section 的呈现结构

这一节不是按工程顺序写，而是按论文最终呈现顺序写。

### 1. 不要按阶段史写，要按完整机制写

论文里不建议写成：

- 我们先改了 `uncontrollability`
- 后来又补了 `self_efficacy`
- 再后来补了 support 和 memory

更合适的是直接给出一套完整机制，并说明各部分分别对应什么理论来源。

### 2. 最终公式应以“完整形态”呈现

论文中可以把最终 helplessness update 写成类似：

```text
H_{t+1} = clip(H_t + lambda(H_t) * Delta_t, lower, upper)

positive_pressure_t =
  weak_outcome_term
  + uncontrollability_term
  + repetition_term
  + low_efficacy_term
  + event_control_loss_term
  + helpless_avoid_term

repair_t =
  mastery_recovery_term
  + indirect_support_repair

Delta_t =
  positive_pressure_t * (1 - protection(controllable_success_memory_t))
  - repair_t
```

其中：

- `lambda(H_t)` 表示基础阻尼
- `protection(controllable_success_memory_t)` 来自长期 mastery / controllability memory，它降低的是“未来负向压力的伤害敏感度”，不是一个固定减项
- `mastery_recovery_term` 表示本轮高质量 controllable success 的即时恢复
- `indirect_support_repair` 表示 support 主要先修复 control / efficacy，再间接作用于 helplessness

### 3. 机制图应把主链和保护链一起画出来

论文里的机制图建议至少包含：

- `digital friction / support context`
- `task appraisal`
- `strategy choice`
- `outcome`
- `perceived_uncontrollability`
- `task_self_efficacy`
- `felt_control`
- `avoid type`
- `controllable_success_memory`
- `helplessness`

推荐的主链是：

```text
friction / support context
-> task appraisal
-> strategy choice
-> outcome
-> perceived_uncontrollability / task_self_efficacy / felt_control
-> helplessness update
-> next strategy choice
```

同时加两条旁路：

- `avoid classification -> helplessness update`
- `controllable_success_memory -> future helplessness sensitivity`

### 4. 变量和理论映射要单独讲清楚

论文中建议单独说明：

- `control / controllability` 是理论核心
- `task_self_efficacy` 是任务域中的中速可操作化控制感指标
- `felt_control` 是事件层的即时波动
- `perceived_uncontrollability` 是负向主驱动项
- `controllable_success_memory` 是 learned controllability 的慢速长期保护项，主要作用是调节 future negative pressure 的敏感度
- `support` 不是直接回血，而是通过 control / efficacy 修复间接起作用
- `avoid` 不是单一变量，至少要区分 helpless / risk / low-value

### 5. 工程顺序和论文顺序要分开管理

因此这份 todo 的正确用法是：

- 开发时：按阶段做，逐步调试
- 写论文时：按完整 mechanism 重组叙事
- 做实验时：始终拿 Stage 0 固定 baseline 做对照

---

## 相关文件

- 当前工程内，来自外部版本的完整副本已经保留为：
  - [helplessness_04012236.md](/Users/pifazuoren/Downloads/AgentSociety-main/helplessness_04012236.md)
- 当前阶段计划文件：
  - [helplessnessupdatetodo.md](/Users/pifazuoren/Downloads/AgentSociety-main/helplessnessupdatetodo.md)
- CCF-B 理论补引清单：
  - [ccfb_classic_literature_checklist.md](/Users/pifazuoren/Downloads/AgentSociety-main/ccfb_classic_literature_checklist.md)
