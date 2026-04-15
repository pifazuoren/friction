# Attribution Memory TODO

## 1. 目的

这份文档只讨论一件事：

在 `digital_friction_mvp` 这个 prototype 里，如何按照 AgentSociety 原生的 memory 组织方式，为“归因”设计一套最小可用的记忆结构。

这里的“归因”特指：

- 失败后，agent 更把原因理解为自己不行，还是系统太难
- 更觉得这是暂时的，还是以后一直都会这样
- 更觉得这只是一个任务的问题，还是很多数字任务都会这样

这份设计不改动四个平行世界，也不改动实验主问题。
它只是在现有链条里补上一层：

`数字摩擦 -> 失败/失控感 -> 归因 -> 数字抵触/习得性无助`


## 2. 官方依据

这份设计主要参考 AgentSociety 官方和原生示例里的 memory 组织方法：

- `docs/02-development-guide/02-profile.md`
- `docs/02-development-guide/04-agent.md`
- `docs/02-development-guide/01-experiment.md`
- `examples/polarization/message_agent.py`

从这些文件里可以抽出一个很清楚的原生分层：

- `Profile / background_story`：放相对稳定的画像信息
- `Status Memory`：放当前状态、结构化变量、少量可持续更新字段
- `Stream Memory`：放按时间发生的经历、事件、决策过程
- `Survey / Interview`：放实验测量，而不是实时心理状态本体

所以，归因不应该全部塞进一种 memory 里。
更原生的做法是：

- 把“当前归因倾向”放进 `Status Memory`
- 把“每次失败后的归因经历”放进 `Stream Memory`


## 3. 设计原则

当前 prototype 阶段，归因 memory 设计遵循四个原则：

- 少字段：先只保留最核心的归因维度，不一开始就做复杂嵌套结构
- 分层清楚：`status` 管状态，`stream` 管经历
- 渐进更新：归因是积累出来的，不应一次失败就完全定型
- 方便后续扩展：以后如果要接 survey、interview、画像脆弱性，再往外扩


## 4. Status Memory 设计

### 4.1 设计目标

`Status Memory` 里只放“当前归因状态”，不放每次失败的完整细节。

### 4.2 建议字段

#### `attribution_locus_score`

- 类型：`float`
- 范围建议：`0-100`
- 含义：当前更偏外部归因还是内部归因
- 解释：
  - `0` 代表更偏“系统太复杂/流程太难/外部环境导致”
  - `100` 代表更偏“是我不会/我能力不够/我不适合做这种事”

#### `attribution_stability_score`

- 类型：`float`
- 范围建议：`0-100`
- 含义：当前更偏不稳定归因还是稳定归因
- 解释：
  - `0` 代表更偏“这次只是碰巧不顺”
  - `100` 代表更偏“以后大概也都会这样”

#### `attribution_scope_score`

- 类型：`float`
- 范围建议：`0-100`
- 含义：当前更偏 specific 还是 global
- 解释：
  - `0` 代表更偏“只是这个任务难”
  - `100` 代表更偏“很多数字任务对我都难”

#### `attribution_summary`

- 类型：`str`
- 含义：一条简短的当前归因总结
- 作用：便于 interview、status summary、prompt 调用时快速读取
- 例子：
  - `最近几次失败后，他越来越觉得不是一次偶然卡住，而是自己长期很难应付这类线上流程。`

#### `attribution_last_updated_day`

- 类型：`int`
- 含义：最近一次更新归因状态的日期标记

### 4.3 为什么这些字段应该放在 Status Memory

因为按官方定义，`Status Memory` 负责当前状态和结构化变量。
这几个字段描述的是“agent 现在总体怎么理解失败”，所以适合放在 `status`。

它们不适合写进 `stream`，因为它们不是一次性事件，而是累计后的当前倾向。


## 5. Stream Memory 设计

### 5.1 设计目标

`Stream Memory` 里记录“每一次失败后的归因经历”。

换句话说：

- `status` 负责回答“他现在总体怎么想”
- `stream` 负责回答“他是怎么一步步变成这样的”

### 5.2 建议 topic

- `digital_failure_attribution`

### 5.3 建议 description 模板

每次写入 `stream memory` 时，尽量让描述里包含下面 5 个信息：

- 这次是什么任务
- 这次发生了什么失败
- agent 当下更偏内部还是外部归因
- agent 当下更觉得是暂时还是长期
- agent 会不会把这次失败推广到别的数字任务

示例模板：

`在[任务名]中失败后，他觉得这次卡住一方面是流程复杂/系统门槛高，另一方面也开始怀疑自己是否学不会。此次归因偏[内部/外部/混合]，并且更觉得这是[暂时/会持续]的问题；他对其他数字任务的信心也[没有明显变化/开始下降]。`

### 5.4 为什么这些内容应该放在 Stream Memory

因为按官方定义，`Stream Memory` 用于记录时间线上发生过的经历、事件和思考过程。

“这一次失败后他是怎么解释的”本质上就是一次事件后的认知反应，最适合进 `stream`。


## 6. Prototype 阶段的最小触发规则

当前阶段建议只在“明确失败”后写归因 memory，不要一开始覆盖所有行为。

建议触发的 outcome：

- `failure_after_attempt`
- `failure_even_with_help`
- `abandon_midway`

当前阶段先不建议把 `avoid_without_attempt` 直接纳入归因主更新。

原因很简单：

- 这类回避有时是无助驱动
- 有时是风险规避
- 有时只是任务价值低

如果 prototype 一上来就把它们全记成归因，会把信号搅混。


## 7. 最小更新逻辑

归因 memory 的最小逻辑建议如下：

### 第一步：失败事件发生

系统已有的 friction、support、outcome、uncontrollability、self-efficacy 信号先照常跑。

### 第二步：生成一次“事件级归因”

对这次失败给出一个简短解释，形成一条 `stream memory`。

重点不是文学表达，而是稳定回答 3 个问题：

- 更像内部还是外部
- 更像暂时还是稳定
- 更像 specific 还是 global

### 第三步：沉淀成“当前归因状态”

不是直接覆盖，而是缓慢更新三个 `status` 分数：

- `attribution_locus_score`
- `attribution_stability_score`
- `attribution_scope_score`

### 第四步：形成短总结

把最近几次失败沉淀成一条 `attribution_summary`，供后续 prompt 或访谈使用。


## 8. 与现有 friction prototype 的关系

这套设计不会替代你们现在已有的变量。

它和当前 prototype 的关系更像：

- 现有变量负责描述“发生了什么”
  - 例如 `helplessness_score`
  - `task_domain_memory`
  - `felt_control`
  - `perceived_uncontrollability`
- 新的 attribution memory 负责描述“agent 怎么理解这件事”

所以它不是另起炉灶，而是在现有心理链条中补一个中间层。


## 9. 当前最小 TODO

prototype 阶段，建议只做下面这些最小项：

- 在 `StatusAttributes` 中增加 3 个归因分数和 1 个归因总结字段
- 明确归因只在三类失败 outcome 后触发
- 每次触发时写一条 `digital_failure_attribution` 到 `Stream Memory`
- 每次触发后缓慢更新三个归因分数
- 在阶段总结或访谈时读取 `attribution_summary`


## 10. 当前先不要做的事

为了避免 prototype 过重，现阶段先不要做这些：

- 不要把归因做成很深的嵌套 dict
- 不要把每次失败的所有结构化细节都放进 `status`
- 不要把 survey 分数直接当作归因 state 本体
- 不要一开始就把所有 avoidance 都算作归因更新
- 不要用实验层面的 `update_state` 硬写归因值作为主方案


## 11. 一句话版本

当前这个 prototype 里，最符合 AgentSociety 原生 memory 组织方法的归因设计是：

- 用 `Status Memory` 保存“当前归因倾向”
- 用 `Stream Memory` 记录“每次失败后的归因经历”
- 让归因成为连接“摩擦失败”和“数字抵触/习得性无助”的中间心理层

