# Development 2

## 这份文档是干什么的

这份文档用来说明两件事：

1. 现在 `digital_friction_mvp` 的实验流程到底是什么。
2. 最近这几次重构，具体把什么东西改了，为什么要改。

这里说的重点是当前 `proto` 引擎，也就是我们现在主要在跑的这条线。

---

## 当前实验的整体思路

现在的实验不是把 AgentSociety 原生那整套

`needs -> plan -> step_execution -> cognition`

完整搬回来。

而是保留我们自己的 `proto` 主链：

`任务分配 -> 策略选择 -> 结果生成 -> helplessness 更新 -> 记录`

但在“组织方式”上，尽量更像 AgentSociety 原生实验：

- 有明确的 agent status schema
- 有明确的 workflow
- survey 主要做测量
- stage 变化和任务运行尽量由 agent 自己处理

所以现在它可以理解成：

`AgentSociety 外层实验框架 + proto 内层行为机制`

---

## 现在实验是怎么跑的

### 第一层：workflow 外层流程

整个实验的外层流程现在大致是：

1. `init_status`
   - 给每个 agent 初始化 `proto` 相关状态
   - 包括：
     - 基础 profile 派生出来的 `helplessness_score`
     - `trust_in_apps`
     - `avoidance_tendency`
     - 任务经验 memory
     - 帮助经验 memory
     - 最近经历 buffer
     - rationale memory

2. 可选 `economy audit`
   - 这一步只做兼容性检查
   - 确保 economy block 开着时，经济绑定字段没有缺失

3. 先做一轮 survey
   - survey 现在主要是“测量”
   - 用来得到 `survey_helplessness_index`、`survey_withdrawal_index` 等指标

4. `sync_survey_feedback`
   - 读取 survey 结果
   - 但现在只回写“测量字段”
   - 不再直接改核心机制变量

5. 进入 stage 循环
   - 每个 stage 先写入对应环境条件
   - 比如 friction、assist、risk 等环境水平

6. 每个 stage 内部按天和决策间隔循环
   - 每个决策间隔触发一次 `STEP`
   - 对 `proto` 来说，最重要的是 agent 的 `forward()` 被执行

7. 每天结束后记录 step 状态
   - 用 `log_step_status` 写一些 step 级状态快照和平均指标

8. 每个 stage 结束后做 `stage_settlement`
   - 汇总这一阶段的：
     - helplessness
     - trust
     - avoidance
     - success / failure / help / negative feedback
   - `proto` 还会额外汇总：
     - attempt rows
     - stage summary
     - stage explanation

9. 保存阶段上下文
   - 用 `SAVE_CONTEXT` 保留 stage 末的关键状态

10. 再做一轮 survey 和测量同步
   - 用于阶段前后比较
   - 也方便后续 world 间对比

---

### 第二层：agent 在每个 step 里实际做什么

当 `proto` agent 执行一次 `forward()` 时，现在内部流程是：

1. 读取当前环境和自己的核心状态
   - `helplessness_score`
   - `trust_in_apps`
   - `avoidance_tendency`
   - 当前 stage key

2. 检查 stage 是否切换
   - 如果 stage 变了，agent 会自己做 stage transition reset：
     - 清空 `event_log`
     - 清空 `proto_stage_attempt_rows_json`
     - 用当前 helplessness 作为新的 `proto_stage_start_helplessness`

3. 检查自己有没有任务
   - 如果没有任务，就在 agent 内部调用 `assign_task_if_missing(...)`
   - 也就是说，任务分配现在已经内收到 `proto` runtime 里了

4. 读取 experience memory
   - `task_domain_memory`
   - `help_effect_memory`
   - `recent_episode_buffer`
   - `rationale_memory`

5. 从 memory 里提取压缩特征
   - 得到 `MemoryFeatures`
   - 包括：
     - `effective_helplessness`
     - `task_self_efficacy`
     - `help_success_rate_smoothed`
     - `recent_negative_feedback_ratio`
     - `recent_same_task_failure_count`

6. 做策略选择
   - 调 `choose_attempt_strategy(...)`
   - 三个策略仍然是：
     - `attempt_self`
     - `seek_help_then_attempt`
     - `avoid`

7. 生成结果
   - 调 `resolve_attempt_outcome(...)`
   - 结果仍然是规则生成，不是 LLM 直接决定

8. 只对“主观不可控感”做 LLM 校准
   - LLM 不决定：
     - 成功失败
     - 策略
     - helplessness 公式
   - LLM 只校准：
     - `perceived_uncontrollability`

9. 更新 helplessness
   - 调 `apply_helplessness_update(...)`
   - 公式本身没改

10. 更新兼容层状态
   - 例如 `trust_in_apps`
   - `avoidance_tendency`

11. 更新 experience memory
   - 分任务经验
   - 帮助经验
   - 最近经历
   - 简短解释

12. 写审计数据
   - 追加 `event_log`
   - 追加 `proto_stage_attempt_rows_json`
   - 在 `payload_json` 里保留：
     - strategy
     - outcome
     - uncontrollability calibration
     - helplessness update
     - memory snapshot

13. 决定任务是否保留到下一轮
   - 如果是 `avoid_without_attempt` 且还没超过延迟上限，可以 defer
   - 否则清掉当前任务，等待下一轮再分配新任务

---

## 最近几次修改，具体改了什么

下面是最近这几轮最关键的改动。

### 1. 把 proto 的核心状态显式化了

以前很多 `proto` 状态是靠 `init_status()` 和运行时零散写进去的。

现在新增了统一的 schema 层：

- `proto/state_schema.py`

这里把 `proto` 相关状态明确整理成正式的 status attributes，例如：

- `helplessness_score`
- `trust_in_apps`
- `avoidance_tendency`
- `proto_assigned_task_json`
- `proto_stage_attempt_rows_json`
- `task_domain_memory`
- `help_effect_memory`
- `recent_episode_buffer`
- `rationale_memory`
- `proto_active_stage_key`

这次改动的意义是：

- status 更清楚
- 初始化更统一
- 更接近 AgentSociety 原生“agent 有明确状态 schema”的风格

---

### 2. `init_status()` 不再手写一大堆散乱初始化

以前 `main.py` 里 `init_status()` 负责手动塞很多字段。

现在改成主要调用：

- `build_initial_proto_status(...)`

也就是：

- 先根据 profile 推出初始 helplessness / trust / avoidance
- 再统一初始化 memory
- 然后再补位置、home、work 等运行需要的字段

这次改动的意义是：

- 初始化逻辑更集中
- profile 到初始心理状态的映射更清楚
- `main.py` 更像实验装配层，而不是机制实现层

---

### 3. survey 现在改成“测量为主”，不再偷偷改机制变量

以前 `sync_survey_feedback()` 会把 survey 结果再混回核心状态。

这会导致一个问题：

- survey 本来应该是测量工具
- 结果却又参与了机制更新
- 测量和机制纠缠在一起

现在已经改成：

- survey 结果只回写测量字段
- 不再直接改：
  - `helplessness_score`
  - `trust_in_apps`
  - `avoidance_tendency`

所以现在 survey 更像：

- 外部观测
- 阶段对比指标
- 心理测量输出

而不是运行中的“隐性控制器”。

---

### 4. 任务分配从 workflow 外部函数，改成 agent/runtime 内部处理

以前实验里有一个比较“命令式”的感觉：

- workflow 先给 agent 塞任务
- agent 再去执行

现在这部分已经改成：

- 在 `proto/runtime.py` 里提供 `assign_task_if_missing(...)`
- agent 在自己的 `forward()` 里检查：
  - 有没有任务
  - 没有就自己分配

也就是说，现在任务分配更像 agent 自己 runtime 的一部分，而不是 workflow 在外面硬推。

这次改动的意义是：

- `main.py` 更轻
- proto 主链更闭环
- workflow 更像“安排实验条件”，而不是“逐个调度 agent”

---

### 5. stage 切换的 reset，从 workflow 外部，改成 agent 自己处理

这是最近最关键的一次修改。

以前 stage 开始时，workflow 里会显式调用：

- `reset_stage_event_log`

来清空阶段日志。

现在 `proto` 已经改成：

- agent 在 `forward()` 开头读取当前 stage
- 对比自己的 `proto_active_stage_key`
- 如果 stage 变化，就自己做 reset

reset 的内容包括：

- 清空 `event_log`
- 清空 `proto_stage_attempt_rows_json`
- 重新记录 `proto_stage_start_helplessness`

同时：

- 老的 `reset_stage_event_log()` 仍然保留在 `main.py`
- 但现在只给 `legacy` 模式兜底
- `proto` 模式已经不再依赖它

这次改动的意义是：

- stage 级状态边界更清晰
- `proto` 更像自洽的 agent runtime
- workflow 更少承担“替 agent 擦状态”的工作

---

### 6. 重新补上了 legacy 兼容，不让旧模式被这次重构弄坏

在把 stage reset 内收到 `proto` 之后，`legacy` 还需要老的：

- `reset_stage_event_log()`

所以这次我把它补回来了。

现在的状态是：

- `proto`：自己处理 stage reset
- `legacy`：保留旧 reset 函数

也就是说，这次改动不是简单“删除旧函数”，而是把职责分层：

- 新机制给 `proto`
- 兼容逻辑给 `legacy`

---

### 7. 更新了实验流程图，让图和代码一致

之前分析目录里的流程图脚本还在写旧流程，比如：

- `supply_digital_tasks`
- 旧的触发判定流水线
- 旧的匹配链术语

这会直接造成理解混乱。

现在已经把流程图脚本更新成当前真实流程：

- workflow 外层
- agent 内部任务分配
- strategy choice
- outcome generation
- LLM 仅校准不可控感
- helplessness update
- memory update
- stage settlement

也重新生成了：

- `digital_friction_full_workflow_1920x1080.png`
- `digital_friction_full_workflow.svg`

---

## 这些修改背后的总方向

这几次改动并没有去改你的核心理论机制：

- 没改 success / failure 的规则公式
- 没改 helplessness update 的公式
- 没改六个核心 summary 指标口径

真正改的是“实验组织方式”。

更具体地说，就是把这个实验从：

- `AgentSociety 外壳 + 很多 workflow 外部调度`

往下面这个方向推：

- `AgentSociety-native hybrid`

也就是：

- 外层还是 AgentSociety 的实验范式
- 内层保留 proto 的结构化 helplessness 机制
- survey 主要做测量
- stage 和任务运行尽量由 agent 自己管理

---

## 当前可以怎么概括这套实验

现在最准确的一句话描述是：

> 这是一个基于 AgentSociety 实验框架运行的、以结构化 helplessness 机制为核心的 hybrid proto 实验。

如果再说得通俗一点：

> 外面是 AgentSociety 的实验壳子，里面是我们自己的数字无助感行为模型。

---

## 当前状态小结

到目前为止，这套实验已经具备下面这些特点：

- 主链清楚：
  - 任务分配 -> 策略选择 -> 结果生成 -> helplessness 更新 -> 记录
- memory 已经进入策略层
- LLM 只做不可控感校准，不越权
- survey 已经从“机制输入”收敛成“测量输出”
- task 分配和 stage reset 已经内收到 `proto` runtime / agent
- stage 级 summary、attempt rows、payload audit 都还能正常保留

这说明当前版本已经比之前更：

- 清楚
- 可解释
- 可审计
- 更接近 AgentSociety 原生实验组织方式

---

## 最近验证结果

最近一轮与这几次修改相关的检查已经通过：

- `py_compile` 通过
- `proto` 相关测试通过
- 当前测试结果为 `26 passed`

这意味着：

- schema 重构没有把初始化弄坏
- stage transition 内收没有把 stage summary 弄坏
- runtime 层的新 helper 逻辑是稳定的

---

## 下一步最合理的方向

如果继续沿这个方向收敛，下一步最值得做的是：

1. 继续把 `main.py` 里只属于 `proto` 的命令式调度往 agent/runtime 内收
2. 进一步把文档、分析脚本、导出说明和当前代码保持一致
3. 再决定要不要把情绪层、daily reflection、mini survey 等“心理层”轻量接进现有主链

这样后面无论是写论文、做汇报，还是继续加机制，都不会因为实验组织方式太乱而拖后腿。
