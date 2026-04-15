# AgentSociety 与当前 Friction 实验的关系

这份文档用于记录：

1. 当前 `digital_friction_mvp` 和 AgentSociety 原生框架到底是什么关系
2. 以后如果要把 friction 机制更深地并回 AgentSociety 原生流程，应该怎么做
3. 哪种路线工作量最合理，适合在论文阶段之后再考虑

---

## 1. 当前我们和 AgentSociety 的关系

当前状态不是“完全脱离 AgentSociety 自己单跑”，也不是“完全使用 AgentSociety 原生 citizen 行为链”。

更准确地说：

- **底层外壳仍然是 AgentSociety**
- **核心 digital friction / helplessness 机制已经主要是我们自己写的 proto 主链**

### 1.1 现在仍然在使用的 AgentSociety 原生部分

- 仿真引擎
  - 负责时间推进、workflow 调度、step 执行、状态落盘
- workflow 系统
  - 负责 `survey / function / environment / step` 这些阶段的执行顺序
- agent 生命周期
  - 每步仍然会走 `before_forward -> before_blocks -> forward -> after_blocks -> after_forward -> status_summary`
- memory / status 容器
  - 我们所有 `memory.status.get/update(...)` 仍然是 AgentSociety 原生 memory 体系
- profile 加载
  - 仍然通过 `memory_from_file` 把画像灌入 agent memory
- environment / storage
  - 时间、环境变量、地图、数据库状态表仍然走 AgentSociety 原生底层

### 1.2 现在已经主要绕开的 AgentSociety 原生行为部分

当前 friction `proto` 版已经没有真正依赖以下原生主行为链来决定数字任务行为：

- `needs_block`
- `plan_generation`
- `cognition_block`
- `step_execution`
- 通过 dispatcher 将 step 分发到：
  - `mobility`
  - `social`
  - `economy`
  - `other`

也就是说，当前真正决定数字任务行为的是我们自己的 proto 主链：

- task assignment
- task appraisal
- memory features
- strategy
- outcome
- uncontrollability calibration
- helplessness update

### 1.3 一句话总结

当前关系最准确的表述是：

> 我们是在 AgentSociety 的仿真底座上，运行一个自定义的 digital friction / helplessness proto 机制。

所以：

- AgentSociety 仍然提供了正规的 simulation infrastructure
- 但当前实验的核心心理与任务机制，不再是 AgentSociety 原生 citizen 行为链本身

---

## 2. 能不能直接用 AgentSociety 的有效性来证明我们现在这个实验有效

可以借力，但不能直接继承。

### 2.1 可以说什么

可以说：

- 我们的系统是 **基于 AgentSociety 搭建的**
- 它运行在一个已有论文支撑的多 agent simulation framework 上
- 因此它不是一个随意拼起来的脚本，而是建立在成熟仿真底座上的扩展实验系统

### 2.2 不能直接说什么

不能直接说：

- 因为 AgentSociety 有效，所以我们这个 helplessness 机制也已经被证明有效

AgentSociety 最多证明：

- **底座靠谱**

但不能替我们证明：

- task appraisal 的构念划分已经有效
- helplessness update 的因果结构已经有效
- support / avoid / uncontrollability 的中间变量已经有效

### 2.3 当前最稳妥的定位

如果以后写论文，当前系统更适合表述为：

> a theory-informed pilot simulation system for digital helplessness, built on top of AgentSociety

而不是：

> a fully validated social simulation model

---

## 3. 以后如果想更深并回 AgentSociety，可以怎么走

不建议直接一步回到原生 `needs -> plan -> cognition -> step_execution -> dispatcher` 全流程。

更合理的是分三档推进。

---

## 4. 三档并回路线

## 路线 A：最小接回

### 目标

不改变当前 proto 主链，只让它和 AgentSociety 原生状态接口更顺。

### 做法

- 保留 `DigitalHelplessnessAgent.forward()` 作为主行为链
- 不改变 helplessness update 的核心顺序
- 只增强这些状态和原生语义的对齐：
  - `current_need`
  - `current_intention`
  - `friction_step_signal`
  - `status_summary`
  - 与状态表/审计的输出一致性

### 好处

- 改动最小
- 风险最低
- 不会推翻现有实验结果口径

### 局限

- 本质上仍然是“自定义 proto 链挂在 AgentSociety 底座上”
- 还没有真正进入原生 citizen 行为主流程

### 适用时机

- 当前论文推进阶段
- 想先把系统整理干净，但不想大改架构

---

## 路线 B：中间版 `DigitalTaskBlock`

### 目标

让数字任务成为 AgentSociety 原生 step/block 体系中的一个正式成员，但保留我们自己的 helplessness 机制。

### 核心思想

新增一个 `DigitalTaskBlock`，让数字任务不再完全旁路原生流程，而是作为一种 step 被原生调度。

### 可能的结构

1. 原生层保留 `current_plan`
2. plan 中允许出现数字任务 step
3. dispatcher 可以识别并分发到 `DigitalTaskBlock`
4. `DigitalTaskBlock` 内部仍然调用我们现有的：
   - task assignment / task surface
   - task appraisal
   - strategy
   - outcome
   - uncontrollability
   - helplessness update

### 这一档最关键的接口问题

必须重新定义：

- `DigitalTask` 和 `current_step` 的关系
- 一个数字任务是单个 step，还是一组 step
- 数字任务 outcome 如何写回：
  - `current_plan`
  - `execution_context`
  - `stream`
  - `friction_step_signal`
- 当前 `proto_assigned_task_json` 是否仍保留，还是迁移到 plan step payload

### 好处

- 和 AgentSociety 的结合度明显增强
- 更适合以后做“数字任务 + 日常生活任务”共存
- 更适合往真正的 social simulation 方向扩展
- 论文里也更容易说是 “AgentSociety-based extension”

### 风险

- 已经是中到大的架构改动
- 需要重新验证实验分布和口径
- 很可能需要重跑关键实验

### 综合判断

这是**最值得的中间路线**。

如果未来真的想更像 AgentSociety 原生实验，而不是一直保持 proto 平行链，这一档最合适。

---

## 路线 C：完整回归 AgentSociety 原生主流程

### 目标

让数字摩擦成为整个 citizen 行为体系中的一个子系统，而不是一条独立 proto 主链。

### 典型形态

- `needs_block` 决定是否出现数字需求
- `plan_generation` 生成包含数字任务的日常计划
- `step_execution` 执行当前 step
- dispatcher 分发到 mobility/social/economy/other/digital
- cognition block 与数字情绪、数字 helplessness 更深交互

### 这意味着什么

这不只是“把代码接回去”，而是：

- 重新定义数字任务如何被 need 触发
- 重新定义数字任务与日常行为如何竞争时间
- 重新定义 support / avoidance / failure 的时序语义
- 重新定义 helplessness 对 planning / cognition 的反向影响

### 为什么这档工作量很大

因为当前 proto 链是：

- 任务驱动
- 单步内完成 appraisal -> strategy -> outcome -> helplessness update

而原生链是：

- need 驱动
- plan 驱动
- block 执行驱动
- step 完成时间驱动

这两种控制流不是简单拼接关系，而是两套不同的行为架构。

### 风险

- 很可能要重写大量接口
- 很可能要重跑全部核心实验
- 分析脚本和论文口径都可能重做

### 综合判断

这是**下一代系统版本**，不适合当前论文冲刺阶段立刻做。

---

## 5. 工作量判断

### 路线 A

- 工作量：小到中
- 性质：工程整理、接口对齐
- 对当前实验破坏：低

### 路线 B

- 工作量：中到大
- 性质：功能性重构
- 对当前实验破坏：中
- 长期价值：最高

### 路线 C

- 工作量：大
- 性质：结构性重构
- 对当前实验破坏：高
- 更适合做成下一阶段的大版本

---

## 6. 当前建议

如果目标仍然是：

- 先把当前论文做出来
- 先把 helplessness 机制验证闭环补齐

那么建议：

- **当前阶段只做路线 A**
- **未来如果要升级，优先考虑路线 B**
- **路线 C 暂时不要启动**

一句话版本：

> 当前最现实的策略，不是“立刻完全回归 AgentSociety 原生 citizen 行为流”，而是先把现有 proto 机制稳定下来，之后再通过 `DigitalTaskBlock` 这种中间路线逐步并回。

