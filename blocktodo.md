# DigitalTaskBlock Migration Plan

> 说明：这份文档专门记录“是否把数字任务从顶层主循环迁移为独立 block”这条结构升级路线。当前先不做代码修改，只作为后续可选规划保留。

## 1. 这件事在说什么

这里的核心想法是：

- 不再让数字任务占据 agent 的顶层主循环
- 而是把数字任务做成一个独立的 `DigitalTaskBlock` 或 `DigitalFrictionBlock`
- 让它在 agent 的日常生活框架里按需被调用

也就是说，未来更理想的结构不是：

`agent run -> 主要处理数字任务 -> helplessness 更新`

而是：

`agent run -> needs -> plan -> step_execution -> 如果碰到数字事务 -> 调用 DigitalTaskBlock -> 回到日常生活流`

## 2. 为什么值得考虑

- 这样数字任务会变成“老人生活中的一类事”，而不是全部事情
- 更接近 AgentSociety 原生的外层行为框架
- 更有利于把“数字抵触/数字无助”解释成嵌入日常生活中的过程，而不是单独的任务系统
- 后续如果要扩展其他生活行为模块，会比现在更自然

## 3. 为什么暂时不先做

- 实现成本明显高于当前第一阶段的机制收敛
- 对当前最核心的论文问题不是必要条件
- 如果现在一起改，容易把“机制收窄”和“结构迁移”混在一起，增加调试和解释成本

## 4. 目标结构

理想状态下，外层重新由 AgentSociety 原生风格主导：

- `needs`
- `plan`
- `step_execution`
- `cognition`

而数字任务相关内容下沉到 block 内部：

- `task appraisal`
- `strategy deliberation`
- `outcome`
- `event-level uncontrollability`
- `event-level attribution`
- `helplessness / mastery / support / memory update`

## 5. 主要涉及文件

- `examples/digital_friction_mvp/proto/agent.py`
- `examples/digital_friction_mvp/main.py`
- `examples/digital_friction_mvp/world_runner.py`
- 可能新增 block 文件
- 可能需要回看 AgentSociety 原生 `needs_block / plan_block / cognition_block` 的挂接方式

## 6. 推荐策略

- 先完成当前 `changetodo.md` 里的第一阶段机制收敛
- 等 helplessness / attribution 主链稳定后，再单独评估这条结构迁移
- 后续如果真开始做，应单独作为一个 block 迁移任务推进，不与当前机制修改混做
