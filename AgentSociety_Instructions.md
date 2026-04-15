# AgentSociety 智能体开发指南

> 来源：你提供的 AgentSociety 官方开发指南内容（整理落地版）
> 
> 目标：作为项目内的固定参考文档，便于后续按统一范式开发自定义 Agent / Block / Workflow。

---

## 1. 智能体在 AgentSociety 中的定位

在 AgentSociety 中，智能体是城市环境里的**自主执行单元**，是整个模拟系统的核心。

智能体不是“脚本函数”，而是具备持续状态与交互能力的实体，核心特征包括：

- **自主性**：能基于自身状态 + 环境信息做决策。
- **持续性**：在模拟全程持续存在，维护记忆与历史。
- **交互性**：能与其他智能体及环境系统互动。
- **适应性**：能随环境变化调整行为策略。

智能体的核心职责：

1. **自主决策**：需求识别、计划制定、行为执行。
2. **环境交互**：感知环境、更新状态、对环境施加反馈。
3. **状态维护**：维护实时状态、历史记忆、经验知识。

---

## 2. 智能体核心工作流

### 2.1 主动工作流：`run()`

`run()` 是统一入口，按固定顺序执行生命周期：

```python
async def run(self) -> Any:
    start_time = time.time()
    await self.before_forward()
    await self.before_blocks()
    await self.forward()
    await self.after_blocks()
    await self.after_forward()
    await self.status_summary()
    end_time = time.time()
    return end_time - start_time
```

> 重要：`run()` 为框架入口，不建议修改。

### 2.2 必须实现：`forward()`

```python
@abstractmethod
async def forward(self) -> Any:
    raise NotImplementedError
```

`forward()` 是核心行为逻辑，必须由子类实现。

### 2.3 可选钩子：`before_forward()` / `after_forward()`

用于执行前准备和执行后清理。

### 2.4 Block 生命周期：`before_blocks()` / `after_blocks()`

框架会自动调用每个 Block 的 `before_forward()` 和 `after_forward()`。

---

## 3. 被动响应工作流

### 3.1 干预响应：`react_to_intervention()`

用于处理外部干预（政策、系统通知、实验注入等），建议在其中：

- 解析干预消息
- 更新状态 / 记忆
- 调整后续行为策略

示意：

```python
async def react_to_intervention(self, intervention_message: str):
    intervention_data = json.loads(intervention_message)
    if intervention_data.get("type") == "policy_change":
        await self.memory.status.update("policy_awareness", True)
        await self.memory.stream.add(
            topic="intervention",
            description=f"Received policy intervention: {intervention_data.get('content')}"
        )
    await self.adjust_behavior_for_intervention(intervention_data)
```

### 3.2 CitizenAgentBase 常见被动方法

- `do_chat(message)`：响应社交消息（可重写）。
- `do_survey(survey)`：回答问卷（通常基于记忆和背景）。
- `do_interview(question)`：回答访谈问题（更强调个人经历）。

---

## 4. 工作流执行顺序

### 主动流程（`run()`）

1. `before_forward()`
2. `before_blocks()`
3. `forward()`
4. `after_blocks()`
5. `after_forward()`

### 被动流程（外部触发）

- `react_to_intervention()`
- `do_chat()`
- `do_survey()`
- `do_interview()`

---

## 5. 设计原则

### 主动工作流原则

- 单一职责
- 可扩展性
- 错误处理
- 状态一致性

### 被动工作流原则

- 响应及时
- 与主动状态一致
- 可定制
- 数据记录完整

---

## 6. 智能体核心子系统

### 6.1 记忆系统

#### Status Memory（结构化实时状态）

- 键值访问快
- 类型明确
- 可实时更新
- 可用于嵌入检索

典型内容：

- 基础属性（姓名、年龄、职业）
- 当前状态（心情、位置、活动）
- 实时数值（精力、满意度等）

状态定义示例：

```python
class MyAgent(Agent):
    StatusAttributes = [
        MemoryAttribute(name="mood", type=str, default_or_value="happy", description="Agent's current mood", whether_embedding=True),
        MemoryAttribute(name="energy", type=float, default_or_value=0.8, description="Agent's energy level, 0-1"),
        MemoryAttribute(name="current_activity", type=str, default_or_value="idle", description="Agent's current activity"),
    ]
```

获取 / 更新：

```python
mood = await self.memory.status.get("mood")
await self.memory.status.update("mood", "excited")
```

#### Stream Memory（时序经历记忆）

- 保留时间线
- 可存复杂认知文本
- 支持语义检索
- 支持经验驱动的后续决策

添加与检索：

```python
await self.memory.stream.add(topic="Event", description="I met my friend")
memories = await self.memory.stream.search(query=query, topic="Event", top_k=5)
```

---

### 6.2 Block 系统

Block 是可组合功能模块；Agent 是容器和编排者。

价值：

- 模块化拆分复杂行为
- 复用方便
- 独立测试友好
- 组合灵活

设计原则：

- 单一职责
- 可组合
- 可测试
- 可扩展

自定义 Block 示例：

```python
class MyBlockParams(BlockParams):
    threshold: float = 0.5
    max_iterations: int = 10

class MyBlockOutput(BlockOutput):
    success: bool = True
    result: str = ""
    confidence: float = 0.0

class MyCustomBlock(Block):
    ParamsType = MyBlockParams
    OutputType = MyBlockOutput
    name = "my_custom_block"
    description = "A custom block for specific functionality"

    async def forward(self, agent_context):
        threshold = self.params.threshold
        current_mood = await self.memory.status.get("mood")
        result = await self.process_logic(agent_context, threshold)
        return MyBlockOutput(success=True, result=result, confidence=0.8)
```

生命周期：

```python
class LifecycleBlock(Block):
    async def before_forward(self):
        pass

    async def forward(self, agent_context):
        return result

    async def after_forward(self):
        pass
```

---

### 6.3 Agent 与 Block 集成方式

#### 方案一：Agent 内手动调用 Block

优点：可控性强，便于调试。

```python
class MyAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.analysis_block = MyCustomBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=MyBlockParams(threshold=0.7)
        )
        self.analysis_block.set_agent(self)

    async def forward(self):
        analysis_result = await self.analysis_block.forward(self.context)
        if analysis_result.success and analysis_result.confidence > 0.8:
            pass
```

#### 方案二：Dispatcher 自动选 Block

优点：代码更简洁，适合动态任务分配。

```python
class DispatcherAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 创建并注册多个 block
        self.dispatcher.register_blocks([...])

    async def forward(self):
        self.context.current_intention = "collect and analyze news"
        selected_block = await self.dispatcher.dispatch(self.context)
        if selected_block:
            result = await selected_block.forward(self.context)
```

---

### 6.4 Dispatcher 原理与要点

Dispatcher 使用 LLM，基于：

- 当前任务上下文
- Block 的 `name` 与 `description`

来选择最合适 Block。

默认 prompt 示例：

```python
DEFAULT_DISPATCHER_PROMPT = """
Based on the task information (which describes the needs of the user), select the most appropriate block to handle the task.
Each block has its specific functionality as described in the function schema.

Task information:
${context.current_intention}
"""
```

自定义 prompt 示例：

```python
CUSTOM_DISPATCHER_PROMPT = """
Based on the current situation and agent state, select the most appropriate block to handle the task.

Current situation:
- Agent mood: ${context.current_mood}
- Current activity: ${context.current_activity}
- Task priority: ${context.task_priority}
- Available time: ${context.available_time}

Task information:
${context.current_intention}
"""
```

实践建议：

- Block 名称要清晰可区分。
- Block 描述要具体、可判别。
- context 里放足够可判别信息。

---

### 6.5 工具集合（AgentToolbox）

核心包括：

- **LLM 工具**：理解、推理、生成、知识应用。
- **Environment 工具**：感知环境状态、执行动作、获取反馈。

示例：

```python
response = await self.llm.atext_request([
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "What should I do next?"}
])

current_time = self.environment.get_datetime()
weather = self.environment.sense("weather")
```

---

### 6.6 上下文系统（Context）

上下文用于 Agent 与 Block 间的信息传递。

- `AgentContext`：Agent 级全局上下文。
- `BlockContext`：Block 内局部上下文。

目标：

- 组件间传参
- 状态对齐
- 中间结果保存
- 错误透传

`DotDict` 支持点号访问、嵌套、合并。

AgentContext 示例：

```python
class MyAgentContext(AgentContext):
    current_time: str = ""
    current_location: str = ""
    current_mood: str = ""
    recent_events: list[str] = []
    decision_history: list[dict] = []
```

BlockContext 示例：

```python
class MyBlockContext(BlockContext):
    input_data: str = ""
    processing_stage: str = "initial"
    intermediate_results: list = []
    error_message: str = ""
    confidence_score: float = 0.0
```

---

## 7. 智能体类型与基类选择

| 实体类型 | 对应基类 | 主要功能 | 适用场景 |
|---|---|---|---|
| 城市居民 | `CitizenAgentBase` | 交通、经济绑定、日常行为 | 模拟市民生活 |
| 企业机构 | `FirmAgentBase` | 生产经营、市场决策 | 模拟企业行为 |
| 银行机构 | `BankAgentBase` | 金融服务、资金与风控 | 模拟银行业务 |
| 政府机构 | `GovernmentAgentBase` | 政策制定与监管 | 模拟公共治理 |
| 央行机构 | `NBSAgentBase` | 货币政策与宏观调控 | 模拟央行行为 |
| 其他机构 | `InstitutionAgentBase` | 通用机构功能 | 模拟特殊组织 |

---

## 8. 开发流程（推荐）

1. 需求分析（功能、行为、输入输出）
2. 选择基类（市民/机构等）
3. 记忆设计（Status / Stream）
4. Block 拆分（职责单一）
5. 逻辑实现（forward + 生命周期）
6. 测试验证（功能、稳定性、可解释性）

---

## 9. 新闻传播智能体案例（官方思路）

目标：构建“收集-分析-传播”的新闻 Agent。

功能拆分：

- `NewsCollectorBlock`：多源收集 + 过滤
- `NewsAnalyzerBlock`：重要性分析（可用 LLM）
- `NewsDistributorBlock`：传播策略与覆盖统计

集成方式：在 Agent 的 `forward()` 中按顺序调用三块，并把结果写回：

- `context`
- `status memory`
- `stream memory`

最终返回统一 `BlockOutput`，便于下游评估与记录。

---

## 10. 实战注意事项（给当前项目）

1. **先跑通再细化**：先保证 workflow 完整，再替换参数为论文依据。
2. **参数要可追溯**：摩擦概率、干预强度、阈值都尽量有文献依据。
3. **日志可解释**：为每步决策保留可解释字段（意图、结果、耗时、理由）。
4. **避免过度随机**：随机可用于探索，但实验结论应可复现。
5. **先小规模 smoke test**：1 agent / 1 day / 1 stage 先看链路，再放大。

---

## 11. 一句话总结

AgentSociety 的核心思想是：

- 用 `run()` 固定生命周期保证稳定执行，
- 用 `forward()` 承载行为逻辑，
- 用 `Block + Dispatcher` 提高模块化与可扩展性，
- 用 `Status/Stream Memory + Context` 维持长期一致性与可解释性。

这也是你后续在数字摩擦实验中做“每 step 思考 + 行动 + 反馈”的标准落地框架。

---

## 12. `examples/` 案例逐一分析（排除 `digital_friction_mvp`）

> 本节覆盖目录：`examples/UBI`、`examples/hurricane_impact`、`examples/inflammatory_message`、`examples/polarization`、`examples/prospect_theory`、`examples/rumor_spreader`、`examples/config_templates`。

### 12.1 UBI（基础收入）案例

- 入口文件：`examples/UBI/main.py`
- 核心目标：在经济模块中注入 UBI（Universal Basic Income）并观察居民态度变量变化。

#### Workflow 结构

1. `RUN` 10 天  
2. `SAVE_CONTEXT`：保存 `ubi_opinion` 到 `ubi_opinion`

#### 关键设计点

- 在 citizen 的 `EconomyBlockParams` 中直接设置：
  - `UBI=1000`
  - `num_labor_hours=168`
  - `productivity_per_labor=1`
- 这意味着该实验是**参数内生干预**（通过 Block 参数改变经济环境），而不是中途 message/environment intervene。

#### 适合借鉴到你的点

- 适用于“长期经济变量 -> 心理/行为态度”的干预设计。
- 很适合作为“无显式事件冲击，仅通过制度参数改变系统行为”的 baseline。

---

### 12.2 Hurricane Impact（飓风冲击）案例

- 入口文件：`examples/hurricane_impact/hurricane.py`
- 配置样本：`examples/hurricane_impact/profiles_hurricane.json`
- 核心目标：通过环境天气文本干预，观察社会行为变化。

#### Workflow 结构

1. `RUN` 3 天（基线）
2. `ENVIRONMENT_INTERVENE`：把 `weather` 改为飓风影响描述
3. `RUN` 3 天（冲击期）
4. `ENVIRONMENT_INTERVENE`：把 `weather` 恢复正常描述
5. `RUN` 3 天（恢复期）

#### 关键设计点

- 这是典型的 **A-B-A**（基线-冲击-恢复）时间序列实验结构。
- 干预在环境层完成，智能体通过感知环境文本进行行为变化。

#### 适合借鉴到你的点

- 你当前的 `steady/shock/recovery` 三阶段结构和这个案例理念完全同源。
- 可以借鉴它的“冲击文本可解释性”做实验叙事（论文写作友好）。

---

### 12.3 Inflammatory Message（煽动信息传播）案例组

- 文件：
  - `examples/inflammatory_message/control.py`
  - `examples/inflammatory_message/emotional.py`
  - `examples/inflammatory_message/edge_intercept.py`
  - `examples/inflammatory_message/point_intercept.py`
- 核心目标：向少量种子节点注入系统信息，观察对聊天记忆/流式记忆的影响。

#### 共同 Workflow

1. `FUNCTION(update_chat_histories)`：随机选 3 个 citizen，往其 `chat_histories` 拼接系统消息
2. `RUN` 3 天
3. `FUNCTION(gather_memory)`：导出 `chat_histories.json` 和 `memories.json`

#### 关键设计点

- 干预入口是**直接改状态**（`chat_histories`），不是发送正规 message intervene。
- 更像“信息污染注入实验”，便于研究谣言、情绪传染、记忆演化。
- `control.py` 的文本更中性，其他版本文本更煽动。

#### 你需要注意的现实问题

- 当前 `emotional.py`、`edge_intercept.py`、`point_intercept.py` 注入文本几乎一致，差异主要体现在实验命名；如果你想要“边拦截/点拦截”真实可比较，需要补对应拦截逻辑（目前是模板化示例）。

---

### 12.4 Polarization（极化）案例组

- 文件：
  - `examples/polarization/control.py`
  - `examples/polarization/back_firing.py`
  - `examples/polarization/echo_chamber.py`
  - `examples/polarization/message_agent.py`
  - `examples/polarization/profiles/*.json`
- 核心目标：研究意见极化条件下，不同传播结构（回火效应 vs 回音室）对群体态度的影响。

#### 12.4.1 `control.py`（对照组）

- 不注入额外“宣传 agent”。
- 仅保存：
  - `guncontrol_attitude_initial`
  - 运行 3 天后 `guncontrol_attitude_final`
  - `guncontrol_chat_histories`

这是标准无干预基线。

#### 12.4.2 `message_agent.py`（自定义干预 agent）

定义了两个自定义 `CitizenAgentBase`：

- `AgreeAgent`：持续生成“支持更强枪支管制”的说服消息
- `DisagreeAgent`：持续生成“反对更强枪支管制”的说服消息

它们的机制：

- 每 2 小时触发一次 (`time_diff = 2 * 60 * 60`)
- 向 `friends` 列表广播消息
- `do_chat()` 里递归传播，`propagation_count > 5` 停止扩散

这相当于“观点种子 + 传播深度限制”的可控传播引擎。

#### 12.4.3 `back_firing.py`（回火效应）

- 在普通 citizen 外，加入 1 个 `AgreeAgent` + 1 个 `DisagreeAgent`
- 通过 `profiles/backfiring_profile_*.json` 指定朋友集合
- 设计意图：把相反观点更多推给对立群体，观察“越劝越反感”的回火。

#### 12.4.4 `echo_chamber.py`（回音室）

- 同样加入 2 个宣传 agent
- 但 `profiles/echo_chamber_profile_*.json` 的朋友集合与上面互换
- 设计意图：让观点更多在同温层内部循环，强化原有立场。

#### 适合借鉴到你的点

- 这是“通过自定义 agent 做干预”而不是改 block 的典型范式。
- 如果你未来要做“数字润滑剂推广员 / 反诈宣传员”，直接可复用这个思路。

---

### 12.5 Prospect Theory（前景理论）三步案例

- 文件：
  - `examples/prospect_theory/step_one.py`
  - `examples/prospect_theory/step_two.py`
  - `examples/prospect_theory/step_three.py`
  - `examples/prospect_theory/surveys.py`
  - `examples/prospect_theory/profiles/*.json`
- 核心目标：基于风险偏好分组，比较“收益框架 + 社会比较”对幸福感主观评价的影响。

#### Step 1：人格分型

- 仅发 `personality_survey()`（二选一：确定收益 vs 50%高收益）
- 输入配置来自 `citizen_profile.json`
- 输出用于后续生成带 `personality` 标签的 profile 文件

#### Step 2：收益冲击（无“超级赢家”）

- `happiness_survey()` 前测
- 对不同 personality 做定向 `MESSAGE_INTERVENE`：
  - 风险规避者：1000 元
  - 风险寻求者-好运者：2500 元
  - 风险寻求者-厄运者：0 元
- `happiness_survey()` 后测
- 输入配置：`citizen_profile_with_personality.json`

#### Step 3：收益冲击 + 社会比较

- 与 Step 2 相同，但额外加入“有一位市民中了 100 万”的社会比较信息
- 并给“最大赢家”群体单独消息
- 输入配置：`citizen_profile_with_winner.json`
- 对比 Step 2 可研究“相对剥夺/比较效应”

#### 关键设计点

- 这是一个很标准的“问卷前后测 + 定向消息干预 + 分组比较”实验模板。
- `surveys.py` 展示了如何定义：
  - 单题人格测量（RADIO）
  - 多题幸福感量表（RATING 1~7）

#### 适合借鉴到你的点

- 你的“技术接受度”完全可以照这个流程做：
  - 前测（接受度）
  - 多类摩擦/辅助干预
  - 后测（接受度）
  - 分组比较 + 统计检验

---

### 12.6 Rumor Spreader（谣言扩散）工具案例

- 文件：
  - `examples/rumor_spreader/network_generator.py`
  - `examples/rumor_spreader/utils.py`
- 特点：这个目录主要是**工具函数**，不是完整 `Config + run()` 入口脚本。

#### `network_generator.py`

- 用 Barabási-Albert 模型生成两张图：
  - `public_network`
  - `private_network`
- 支持独立随机种子，便于可复现。

#### `utils.py` / `initialize_social_network_with_graphs(...)`

根据两张图初始化 agent 社交关系：

- `friends`（私域）
- `public_friends`（公域）
- `relationships`（关系强度）
- `relation_types`（family/colleague/friend）
- `chat_histories` / `interactions`

#### 你需要注意

- 该函数用图节点索引直接写入好友列表，默认假设“图节点编号与 agent id 可对应”；如果你的 agent id 不是这种形式，需先做映射。

---

### 12.7 `config_templates`（配置模板，不是实验案例）

- 文件：`examples/config_templates/example_config.yaml`
- 作用：提供最小可运行配置骨架（LLM / env / map / agents / exp）。
- 使用方式：复制模板后补齐 API key、provider、model、map 路径与 workflow。

---

## 13. 如何把这些案例方法映射到你的数字摩擦实验

给你一个可直接套用的“案例 -> 能力”映射：

1. **Hurricane**：学三阶段（基线-冲击-恢复）环境干预结构。  
2. **Prospect Theory**：学前后测问卷 + 分组消息干预。  
3. **Polarization**：学自定义宣传 agent 与传播链控制。  
4. **Inflammatory Message**：学快速注入污染信息与记忆导出。  
5. **UBI**：学通过 block 参数做制度型干预。  
6. **Rumor Spreader**：学先构图再初始化社交网络结构。  

如果你只做一个最小组合，推荐优先级：

- 结构框架用 **Hurricane**，
- 评估方法用 **Prospect Theory**，
- 干预执行策略再按需借 **Polarization**。

---

## 14. 论文附录 Prompt 风格参考（用于本项目硬约束输出）

参考来源：`Exploring Large Language Model Agents for Piloting Social Experiments.pdf` 附录示例（本地 OCR 整理，路径 `.tmp_paper/crops/appB-*.jpg`）。

### 14.1 附录 Prompt 的共同风格（可直接借鉴）

附录里的高稳定 Prompt，核心特征非常统一：

1. **输出格式先行**：先定义输出类型（JSON / 单选 / 精确数组）。
2. **字段与范围明确**：直接约束值域（如 0~1、整数区间）。
3. **只允许目标输出**：明确写“禁止额外文本/解释”。
4. **给一个合法示例**：让模型有可对齐模板。
5. **强格式约束语句**：例如“must respond in this exact format”。

### 14.2 附录中可复用的约束句式（整理版）

- “请按 JSON 返回，除 JSON 外不允许任何其他文本。”
- “输出必须是从候选集合中的单一选择，不得包含附加说明。”
- “你必须严格按此格式输出：`[mode, friend_index]`。”
- “仅返回一个区间内整数，不要解释过程。”
- “字段缺失视为无效输出。”

> 说明：以上为附录截图内容的结构化归纳，便于在当前项目中复用为“硬 Prompt 规范”。

### 14.3 面向 `digital_friction_mvp` 的硬 JSON Prompt（推荐模板）

下面模板可用于 `trigger_event_shocks` 的 LLM 校准请求（风险倍率与影响倍率）：

```text
[System]
You are a strict JSON-only calibration engine for digital-friction simulation.
You must output exactly ONE valid JSON object and nothing else.

Hard constraints:
1) Output must be valid JSON (RFC8259), no markdown, no code fences, no comments.
2) Output keys must be EXACTLY:
   risk_mult, protect_mult, neg_impact_mult, pos_impact_mult, confidence, reason
3) Do not add or remove keys.
4) Value constraints:
   - risk_mult: float in [0.75, 1.35]
   - protect_mult: float in [0.75, 1.35]
   - neg_impact_mult: float in [0.70, 1.45]
   - pos_impact_mult: float in [0.70, 1.45]
   - confidence: float in [0.00, 1.00], required, cannot be null
   - reason: concise string (<= 120 chars)
5) If uncertain, still provide your best estimate; never omit confidence.
6) Keep multipliers near 1.00 unless strong contextual evidence exists.
7) Any non-JSON output is invalid.

Output example (schema reference only):
{"risk_mult":1.03,"protect_mult":0.97,"neg_impact_mult":1.05,"pos_impact_mult":0.96,"confidence":0.41,"reason":"recent step showed mild friction and low support"}

[User]
Context:
{context_json_here}

Return JSON only.
```

### 14.4 工程落地建议（与上面模板配套）

1. **Prompt 层**：使用上面的硬约束模板，禁止额外文本。  
2. **解析层**：先 `json.loads`，再做字段白名单与类型范围校验。  
3. **审计层**：单独记录：
   - `raw_parse_ok`
   - `schema_ok`
   - `repair_used`
   - `confidence_missing`
4. **融合层**：将“可解析”与“可用（有语义）”分开判断，避免把“格式成功”误当成“决策有效”。

智能体开发
本文档主要介绍如何在AgentSociety中设计和实现自定义智能体。

第一部分：智能体在AgentSociety中的定位
智能体的核心定位
在AgentSociety中，智能体是城市环境中的自主执行单元。每个智能体都代表着一个能够在城市环境中独立运行、自主决策的实体，它们构成了整个城市模拟系统的核心组成部分。

智能体不仅仅是简单的程序模块，而是具有以下特征的复杂系统：

自主性：智能体能够根据自身状态和环境信息独立做出决策

持续性：智能体在整个模拟过程中持续存在，维护自己的状态和历史

交互性：智能体能够与其他智能体、环境系统进行交互

适应性：智能体能够根据环境变化调整自己的行为策略

智能体的基本职责
作为城市环境中的自主执行单元，智能体承担着以下核心职责：

1. 自主决策: 智能体需要根据当前状态、历史经验和环境信息，自主决定下一步的行动。这种决策过程可能涉及：

需求分析：识别当前需要解决的问题

计划制定：制定实现目标的行动方案

行为执行：将计划转化为具体的行动

2. 环境交互: 智能体需要与城市环境进行持续的交互，包括：

环境感知：获取环境中的相关信息

状态更新：根据环境变化更新自身状态

行为反馈：通过行动影响环境状态

3. 状态维护: 智能体需要维护自己的内部状态，包括：

实时状态：当前的情绪、位置、活动等

历史记忆：过去的经历和决策

知识积累：从经验中学习到的知识

第二部分：智能体核心工作流
智能体的工作流是智能体运行的核心机制，定义了智能体如何响应和执行任务。理解工作流对于开发有效的智能体至关重要。

主动工作流：run()方法
智能体的主要工作流通过run()方法实现，这是一个统一的入口点，协调整个执行流程。

基于run()方法控制的Agent工作流程
async def run(self) -> Any:
    """
    Unified entry point for executing the agent's logic.
    
    - **Description**:
        - It calls the forward method to execute the agent's behavior logic.
        - Acts as the main control flow for the agent, coordinating when and how the agent performs its actions.
    """
    start_time = time.time()
    # run required methods before agent forward
    await self.before_forward()
    await self.before_blocks()
    # run agent forward
    await self.forward()
    # run required methods after agent forward
    await self.after_blocks()
    await self.after_forward()
    await self.status_summary()
    end_time = time.time()
    return end_time - start_time
重要说明：run()方法是智能体的统一入口点，请勿修改。它按照固定的顺序调用各个生命周期方法。

必须实现的核心方法
forward()方法

@abstractmethod
async def forward(self) -> Any:
    """
    Define the behavior logic of the agent.
    
    - **Description**:
        - This abstract method should contain the core logic for what the agent does at each step of its operation.
        - It is intended to be overridden by subclasses to define specific behaviors.
    """
    raise NotImplementedError
forward()方法是智能体的核心行为逻辑，必须由子类实现。它包含智能体的主要决策和行为逻辑。

before_forward()和after_forward()方法

async def before_forward(self):
    """
    Before forward - prepare context and environment
    """
    pass

async def after_forward(self):
    """
    After forward - cleanup and save state
    """
    pass
这两个方法是可选的，用于执行前的准备工作和执行后的清理工作。

Block相关的生命周期执行方法
async def before_blocks(self):
    """
    Before blocks - prepare all blocks
    """
    if self.blocks is None:
        return
    for block in self.blocks:
        await block.before_forward()

async def after_blocks(self):
    """
    After blocks - cleanup all blocks
    """
    if self.blocks is None:
        return
    for block in self.blocks:
        await block.after_forward()
这两个方法会自动调用所有注册Block的before_forward()和after_forward()方法，确保Block的生命周期管理，请勿修改。Block相关内容请参考后续内容。

被动响应工作流：react_to_intervention()
智能体需要响应外部干预，这是通过react_to_intervention()方法实现的。

async def react_to_intervention(self, intervention_message: str):
    """
    React to an intervention.
    
    - **Args**:
        - `intervention_message` (`str`): The message of the intervention.
    
    - **Description**:
        - React to an intervention from external sources.
    """
    # Parse intervention message
    intervention_data = json.loads(intervention_message)
    
    # Update agent behavior based on intervention
    if intervention_data.get("type") == "policy_change":
        await self.memory.status.update("policy_awareness", True)
        await self.memory.stream.add(
            topic="intervention",
            description=f"Received policy intervention: {intervention_data.get('content')}"
        )
    
    # Adjust behavior accordingly
    await self.adjust_behavior_for_intervention(intervention_data)
重要说明：react_to_intervention()方法是必须实现的，用于处理外部干预。

CitizenAgentBase的被动响应工作流
CitizenAgentBase除了标准的run()工作流外，还提供了几个核心的被动响应方法，这些方法都有默认实现，是可选的实现项。

do_chat()方法
用于响应其他智能体的社交消息

async def do_chat(self, message: Message) -> str:
    """
    Process a chat message received from another agent.
    
    - **Args**:
        - `message` (`Message`): The chat message data received from another agent.
    
    - **Returns**:
        - `str`: Response to the chat message
    """
    # Default implementation
    resp = f"Agent {self.id} received agent chat response: {message.payload}"
    get_logger().debug(resp)
    return resp
特点：

有默认实现，可以直接使用

可以被子类重写以提供自定义的聊天响应逻辑

自动处理消息存储和日志记录

do_survey()方法
用于响应问卷调查

async def do_survey(self, survey: Survey) -> str:
    """
    Process a survey questionnaire.
    
    - **Args**:
        - `survey` (`Survey`): The survey questionnaire to respond to.
    
    - **Returns**:
        - `str`: Survey response based on agent's memory and background
    """
    # Get survey questions
    questions = survey.to_prompt()
    
    # Generate response based on agent's memory
    response = await self.llm.atext_request([
        {"role": "system", "content": "You are a citizen, please answer based on your background"},
        {"role": "user", "content": questions[0]}
    ])
    
    return response
特点：

基于智能体的记忆生成调查回答

自动处理调查数据的存储

可以重写以提供更复杂的回答逻辑

do_interview()方法
用于响应采访

async def do_interview(self, question: str) -> str:
    """
    Process an interview question.
    
    - **Args**:
        - `question` (`str`): The interview question.
    
    - **Returns**:
        - `str`: Interview response based on agent's background
    """
    # Get agent background
    background = await self.memory.status.get("background_story")
    
    # Generate interview response
    response = await self.llm.atext_request([
        {"role": "system", "content": f"You are {background}, please answer the interview question"},
        {"role": "user", "content": question}
    ])
    
    return response
特点：

基于智能体的背景故事生成访谈回答

支持深度交流，比问卷调查更注重个人经历

可以重写以提供更个性化的回答

工作流的执行顺序
智能体的工作流执行遵循以下顺序：

主动工作流（通过run()触发）：

before_forward() - 准备工作

before_blocks() - Block准备工作

forward() - 核心行为逻辑

after_blocks() - Block清理工作

after_forward() - 清理工作

被动响应工作流（由外部事件触发）：

react_to_intervention() - 响应干预

do_chat() - 响应聊天消息

do_survey() - 响应问卷调查

do_interview() - 响应访谈问题

5. 工作流设计原则
主动工作流设计原则
单一职责：每个生命周期方法只负责特定的功能

可扩展性：可以轻松添加新的准备工作或清理工作

错误处理：在每个阶段都要妥善处理异常

状态管理：确保状态在各个环节的一致性

被动响应工作流设计原则
响应性：快速响应外部事件

一致性：保持与主动工作流的状态一致

可定制性：允许子类重写以提供特定行为

数据完整性：确保响应数据的完整记录

第三部分：智能体核心子系统
AgentSociety的智能体设计基于四个核心要素，每个要素都有其独特的设计原理和价值。理解这些核心要素的设计思想对于开发高质量的智能体至关重要。

记忆系统设计原理
智能体的记忆系统是智能体能够保持连续性和学习能力的关键。AgentSociety设计了两种不同类型的记忆，每种都有其特定的用途和优势。

Status Memory：实时状态存储
Status Memory采用键值对的形式存储智能体的实时状态，具有以下特点：

快速访问：通过键名直接访问，响应速度快

结构化存储：每个状态都有明确的类型和默认值

实时更新：状态可以随时更新，反映智能体的当前状况

可嵌入性：支持向量化存储，便于语义检索

Status Memory主要用于存储：

智能体的基本属性（姓名、年龄、职业等）

当前状态（心情、位置、活动等）

实时数据（精力值、满意度等）

Status Memory的功能说明
定义状态属性

在智能体类中通过StatusAttributes类变量定义该智能体所包含的状态属性：

class MyAgent(Agent):
    StatusAttributes = [
        MemoryAttribute(
            name="mood",
            type=str,
            default_or_value="happy",
            description="Agent's current mood",
            whether_embedding=True,
        ),
        MemoryAttribute(
            name="energy",
            type=float,
            default_or_value=0.8,
            description="Agent's energy level, 0-1",
        ),
        MemoryAttribute(
            name="current_activity",
            type=str,
            default_or_value="idle",
            description="Agent's current activity",
        ),
    ]
获取状态值

在智能体中通过memory.status.get()方法获取状态值：

async def forward(self):
    # Get current mood and energy
    mood = await self.memory.status.get("mood")
    energy = await self.memory.status.get("energy")
更新状态值

在智能体中通过memory.status.update()方法更新状态值：

async def update_status(self):
    # Update mood based on recent events
    await self.memory.status.update("mood", "excited")
Stream Memory：流式记忆
Stream Memory采用流式存储的方式记录智能体随时间线的经历，具有以下特点：

时序性：按时间顺序记录事件和经历

丰富性：可以存储复杂的文本描述和认知过程

可检索性：支持语义检索，找到相关的历史经验

学习性：通过历史经验指导未来的决策

Stream Memory主要用于存储：

智能体的经历和回忆

决策过程和思考过程

与其他智能体的交互历史

从环境中获得的事件信息

Stream Memory的功能说明
添加记忆条目

在智能体中通过memory.stream.add()方法添加新的记忆条目：

async def record_experience(self, event: str, thought: str):
    # Record a new experience
    await self.memory.stream.add(
        topic=f"Event",
        description="I met my friend"
    )
检索相关记忆

通过语义检索找到相关的历史记忆：

async def recall_related_memories(self, query: str, limit: int = 5):
    # Search for memories related to the query
    memories = await self.memory.stream.search(
        query=query,
        topic:Optional[str]='Event',
        top_k=limit
    )
    return memories
Block系统设计原理
Block系统是AgentSociety中实现复杂智能体行为的关键设计。Block类似于神经网络中的层，每个Block负责特定的功能模块。

Block与Agent的关系
Agent是容器：Agent负责协调和管理多个Block

Block是功能模块：每个Block专注于特定的功能

组合式设计：通过组合不同的Block构建复杂的智能体行为

可复用性：Block可以在不同的智能体之间复用

Block存在的意义
Block系统的设计解决了以下问题：

模块化开发：将复杂的行为分解为独立的功能模块

代码复用：相同的功能可以在不同智能体中复用

易于测试：每个Block可以独立测试

灵活组合：可以根据需要组合不同的Block

Block设计原则
单一职责：每个Block只负责一个特定的功能

可组合性：Block之间可以灵活组合

可测试性：每个Block都可以独立测试

可扩展性：可以轻松添加新的Block

Block的功能说明
创建自定义Block

通过继承Block基类创建自定义Block：

class MyBlockParams(BlockParams):
    threshold: float = 0.5
    max_iterations: int = 10

class MyBlockOutput(BlockOutput):
    success: bool = True
    result: str = ""
    confidence: float = 0.0

class MyCustomBlock(Block):
    ParamsType = MyBlockParams
    OutputType = MyBlockOutput
    name = "my_custom_block"
    description = "A custom block for specific functionality"
    
    async def forward(self, agent_context):
        # Get parameters
        threshold = self.params.threshold
        max_iterations = self.params.max_iterations
        
        # Access agent memory
        current_mood = await self.memory.status.get("mood")
        
        # Perform block-specific logic
        result = await self.process_logic(agent_context, threshold)
        
        # Return output
        return MyBlockOutput(
            success=True,
            result=result,
            confidence=0.8
        )
    
    async def process_logic(self, context, threshold):
        # Implement specific logic here
        return "Processed result"
Block的生命周期

每个Block都有完整的生命周期, 包括before_forward, forward以及after_forward三个部分，其中必须实现的为forward：

class LifecycleBlock(Block):
    async def before_forward(self):  # Optional
        """Called before forward execution"""
        # Prepare context, validate inputs
        pass
    
    async def forward(self, agent_context):  # You have to rewrite the forward function
        """Main execution logic"""
        # Core block functionality
        return result
    
    async def after_forward(self):  # Optional
        """Called after forward execution"""
        # Cleanup, update state
        pass
Block与Agent的集成

方案一：在Agent中直接使用Block：

class MyAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Create and add blocks
        self.analysis_block = MyCustomBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=MyBlockParams(threshold=0.7)
        )
        
        # Set agent reference for blocks that need it
        self.analysis_block.set_agent(self)
    
    async def forward(self):
        # Use blocks in agent logic
        context = self.context
        
        # Execute analysis block
        analysis_result = await self.analysis_block.forward(context)
        
        # Use block output for decision making
        if analysis_result.success and analysis_result.confidence > 0.8:
            # High confidence result, proceed with action
            pass
方案二：将多个Block注册到dispatcher中：

class DispatcherAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Create multiple blocks
        self.news_collector = NewsCollectorBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=NewsCollectorParams(sources=["rss", "api"])
        )
        
        self.news_analyzer = NewsAnalyzerBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=NewsAnalyzerParams(importance_threshold=0.7)
        )
        
        self.news_distributor = NewsDistributorBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=NewsDistributorParams(distribution_channels=["social"])
        )
        
        # Set agent reference for blocks that need it
        for block in [self.news_collector, self.news_analyzer, self.news_distributor]:
            if block.NeedAgent:
                block.set_agent(self)
        
        # Register blocks to dispatcher
        self.dispatcher.register_blocks([
            self.news_collector,
            self.news_analyzer,
            self.news_distributor
        ])
    
    async def forward(self):
        # Update context with current intention
        self.context.current_intention = "collect and analyze news"
        
        # Let dispatcher automatically select the most appropriate block
        selected_block = await self.dispatcher.dispatch(self.context)
        
        if selected_block:
            # Execute the selected block
            result = await selected_block.forward(self.context)
            
            # Process the result
            if result.success:
                # Update context with block results
                self.context.last_block_result = result
                
                # Record the activity
                await self.memory.stream.add(
                    topic="activity",
                    description=f"Executed {selected_block.name}: {result.evaluation}"
                )
            else:
                # Handle block failure
                await self.memory.stream.add(
                    topic="error",
                    description=f"Block {selected_block.name} failed: {result.error}"
                )
        else:
            # No suitable block found
            await self.memory.stream.add(
                topic="activity",
                description=f"No suitable block found for: {self.context.current_intention}"
            )
        
        return "Agent behavior completed"
Dispatcher工作原理

Dispatcher基于Block的name和description，通过LLM智能选择最合适的Block来执行任务。Dispatcher使用可自定义的prompt模板，自动从context中获取格式化变量：

Block注册：每个Block在注册时需要提供清晰的name和description

Prompt模板：使用可自定义的prompt模板，支持从context中获取变量

智能选择：LLM根据prompt和Block描述进行语义匹配，选择最合适的Block

自定义Dispatcher Prompt

# the default prompt template
DEFAULT_DISPATCHER_PROMPT = """
Based on the task information (which describes the needs of the user), select the most appropriate block to handle the task.
Each block has its specific functionality as described in the function schema.
        
Task information:
${context.current_intention}
"""

# define your dispatcher prompt
CUSTOM_DISPATCHER_PROMPT = """
Based on the current situation and agent state, select the most appropriate block to handle the task.

Current situation:
- Agent mood: ${context.current_mood}
- Current activity: ${context.current_activity}
- Task priority: ${context.task_priority}
- Available time: ${context.available_time}

Task information:
${context.current_intention}

Select the block that best matches the current situation and task requirements.
"""

# register your prompt
class CustomDispatcherAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # register prompt
        self.dispatcher.register_dispatcher_prompt(CUSTOM_DISPATCHER_PROMPT)
        # register blocks
        self.dispatcher.register_blocks([...])
Block描述的重要性

class WellDescribedBlock(Block):
    name = "news_collector"  # A clear name
    description = "Collects news from RSS feeds and APIs, filters content based on keywords, and returns structured news data"  # A clear description helps the LLM to make decisions
    
    async def forward(self, agent_context):
        # Block implementation
        pass
Dispatcher的优势

灵活配置：支持自定义prompt模板

丰富上下文：可以从context中获取任意变量

语义理解：LLM能够理解复杂的上下文信息

智能匹配：基于完整上下文选择最合适的Block

自动扩展：添加新Block时无需修改选择逻辑

智能回退：当没有合适Block时返回None而不是错误

两种方案的区别

特性

方案一：直接使用

方案二：Dispatcher

控制方式

手动控制Block执行顺序

自动选择最合适的Block

灵活性

高，可以精确控制执行逻辑

中等，依赖LLM选择

复杂度

需要手动管理Block调用

自动管理，代码更简洁

适用场景

明确的执行流程

动态的任务分配

调试难度

容易调试，流程清晰

需要理解dispatcher逻辑

Block参数配置

Block支持灵活的参数配置：

# Configure block with specific parameters
analysis_block = MyCustomBlock(
    toolbox=toolbox,
    agent_memory=memory,
    block_params=MyBlockParams(
        threshold=0.8,
        max_iterations=15
    )
)

# Access parameters in block
threshold = self.params.threshold
max_iterations = self.params.max_iterations
工具集合设计原理
AgentToolbox为智能体提供了统一的核心工具集合，每个工具都有其特定的作用和价值。

LLM工具：智能体的大脑
LLM工具是智能体进行推理和决策的核心：

自然语言理解：理解输入的自然语言

推理能力：基于上下文进行逻辑推理

生成能力：生成自然语言的回复

知识应用：应用已有的知识解决问题

Environment工具：环境感知和交互
Environment工具让智能体能够感知和影响环境：

环境感知：获取环境中的信息（天气、位置、其他智能体等）

状态查询：查询环境中的各种状态

行为执行：在环境中执行具体的行动

反馈获取：获取行动的结果和反馈

访问核心工具
智能体可以直接访问工具箱中的核心工具：

class MyAgent(Agent):
    async def forward(self):
        # Access LLM for reasoning
        response = await self.llm.atext_request([
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "What should I do next?"}
        ])
        
        # Access environment for information
        current_time = self.environment.get_datetime()
        weather = self.environment.sense("weather")
上下文系统设计原理
上下文系统不仅为智能体的长时间执行提供了统一的上下文入口，同时也为智能体和Block之间提供了灵活的信息传递机制。

AgentContext：智能体级别的上下文
AgentContext用于维护智能体级别的上下文信息：

全局状态：智能体的全局状态信息

环境信息：从环境获取的信息

配置参数：智能体的配置参数

执行结果：智能体执行的结果

BlockContext：模块级别的上下文
BlockContext用于在Block之间传递信息：

输入数据：Block的输入数据

处理结果：Block的处理结果

中间状态：Block处理过程中的中间状态

错误信息：Block执行过程中的错误信息

上下文的作用
上下文系统解决了以下问题：

信息传递：在不同组件之间传递信息

状态管理：管理智能体和Block的状态

参数配置：配置智能体和Block的参数

结果返回：返回执行结果和错误信息

DotDict的设计
上下文系统基于DotDict实现，提供了点号访问的便利性：

属性式访问：使用点号访问字典元素

嵌套支持：支持嵌套的字典结构

合并操作：支持字典的合并操作

深拷贝：自动进行深拷贝，避免副作用

上下文系统的功能说明
定义AgentContext

创建自定义的AgentContext类：

class MyAgentContext(AgentContext):
    current_time: str = ""
    current_location: str = ""
    current_mood: str = ""
    recent_events: list[str] = []
    decision_history: list[dict] = []
    
    class Config:
        arbitrary_types_allowed = True
定义BlockContext

创建自定义的BlockContext类：

class MyBlockContext(BlockContext):
    input_data: str = ""
    processing_stage: str = "initial"
    intermediate_results: list = []
    error_message: str = ""
    confidence_score: float = 0.0
在Agent中使用上下文

class MyAgent(Agent):
    Context = MyAgentContext
    
    async def before_forward(self):
        # Update context with current information
        self.context.current_time = self.environment.get_datetime()
        self.context.current_location = self.environment.get_location()
        self.context.current_mood = await self.memory.status.get("mood")
        
        # Add recent events to context
        recent_memories = await self.memory.stream.search("", limit=5)
        self.context.recent_events = [mem.content for mem in recent_memories]
    
    async def forward(self):
        # Use context information for decision making
        if self.context.current_mood == "happy":
            # Agent is happy, can work efficiently
            pass
        elif len(self.context.recent_events) > 0:
            # Process recent events
            await self.process_recent_events(self.context.recent_events)
在Block中使用上下文

class MyBlock(Block):
    Context = MyBlockContext
    
    async def forward(self, agent_context):
        # Initialize block context
        self.context.input_data = agent_context.get("input", "")
        self.context.processing_stage = "started"
        
        try:
            # Process input data
            result = await self.process_data(self.context.input_data)
            self.context.intermediate_results.append(result)
            
            # Update processing stage
            self.context.processing_stage = "completed"
            self.context.confidence_score = 0.9
            
            return result
            
        except Exception as e:
            # Handle errors
            self.context.error_message = str(e)
            self.context.processing_stage = "error"
            self.context.confidence_score = 0.0
            raise
DotDict的使用

DotDict提供了便利的点号访问：

# Create DotDict
context = DotDict({
    "user": {
        "name": "Alice",
        "preferences": {
            "color": "blue",
            "food": "pizza"
        }
    },
    "session": {
        "start_time": "2024-01-01 10:00:00"
    }
})

# Access using dot notation
user_name = context.user.name  # "Alice"
user_color = context.user.preferences.color  # "blue"
session_time = context.session.start_time  # "2024-01-01 10:00:00"

# Update values
context.user.preferences.food = "sushi"

# Merge with another DotDict
additional_context = DotDict({
    "user": {
        "age": 25
    },
    "system": {
        "version": "1.0"
    }
})

# Merge contexts
merged_context = context | additional_context
# Now merged_context.user.age = 25, merged_context.system.version = "1.0"
上下文传递示例

class ContextAwareAgent(Agent):
    Context = MyAgentContext
    
    async def forward(self):
        # Prepare agent context
        await self.prepare_context()
        
        # Pass context to blocks
        for block in self.blocks:
            try:
                result = await block.forward(self.context)
                # Update context with block results
                self.context.decision_history.append({
                    "block": block.name,
                    "result": result,
                    "timestamp": self.context.current_time
                })
            except Exception as e:
                # Handle block errors
                self.context.decision_history.append({
                    "block": block.name,
                    "error": str(e),
                    "timestamp": self.context.current_time
                })
    
    async def prepare_context(self):
        # Gather all necessary information
        self.context.current_time = self.environment.get_datetime()
        self.context.current_location = self.environment.get_location()
        self.context.current_mood = await self.memory.status.get("mood")
        
        # Get recent memories for context
        recent_memories = await self.memory.stream.search("", limit=3)
        self.context.recent_events = [mem.content for mem in recent_memories]
第四部分：开发示例
本小节通过具体的开发示例，展示如何在AgentSociety中构建不同类型的智能体。每个示例都包含完整的需求分析、设计思路和实现代码。

智能体类型与基类选择
在开始开发之前，需要根据智能体的功能和职责选择合适的基类：

实体类型

对应基类

主要功能

适用场景

城市居民

CitizenAgentBase

交通模拟、经济系统绑定、日常行为

模拟普通市民的生活行为

企业机构

FirmAgentBase

生产经营、市场交互、决策制定

模拟企业的经营决策

银行机构

BankAgentBase

金融服务、资金管理、风险评估

模拟银行的金融业务

政府机构

GovernmentAgentBase

政策制定、公共服务、监管职能

模拟政府的政策制定

央行机构

NBSAgentBase

货币政策、金融监管、宏观调控

模拟央行的货币政策

其他机构

InstitutionAgentBase

通用机构功能、组织管理

模拟其他类型的机构

开发流程概述
智能体开发遵循以下基本流程：

需求分析：明确智能体的功能需求和行为特征

基类选择：根据功能选择合适的智能体基类

记忆设计：定义Status Memory中的内容，明确Stream Memory在智能体中的作用

Block设计：将复杂功能分解为独立的Block模块

逻辑实现：实现智能体的核心行为逻辑

测试验证：验证智能体的功能和性能

完整开发案例：新闻传播智能体
需求分析
构建一个能够收集、分析和传播新闻的智能体，具备以下功能：

从多个来源收集新闻信息

分析新闻内容的重要性和相关性

决定是否传播新闻以及传播方式

跟踪新闻传播的效果

功能分解与Block设计
通过需求分析，将功能分解为以下Block：

NewsCollectorBlock：新闻收集模块

从不同来源获取新闻

过滤和预处理新闻内容

提取新闻的关键信息

NewsAnalyzerBlock：新闻分析模块

分析新闻的重要性

评估新闻的相关性

生成新闻摘要

NewsDistributorBlock：新闻传播模块

决定传播策略

选择传播渠道

跟踪传播效果

完整实现
Step 1: 定义智能体参数和上下文

class NewsAgentParams(AgentParams):
    collection_interval: int = 300  # collection interval (s)
    analysis_threshold: float = 0.7  # analysis threshold
    distribution_radius: int = 1000  # broadcast radius

class NewsAgentContext(AgentContext):
    current_news_count: int = 0
    last_collection_time: str = ""
    distribution_stats: dict = {}

class NewsBlockOutput(BlockOutput):
    success: bool = True
    news_items: list = []
    analysis_results: dict = {}
    distribution_results: dict = {}
Step 2: 实现新闻收集Block

class NewsCollectorParams(BlockParams):
    sources: list[str] = ["rss", "api", "social"]
    max_items_per_source: int = 10
    filter_keywords: list[str] = []

class NewsCollectorOutput(BlockOutput):
    collected_news: list[dict] = []
    source_stats: dict = {}

class NewsCollectorBlock(Block):
    ParamsType = NewsCollectorParams
    OutputType = NewsCollectorOutput
    name = "news_collector"
    description = "Collects news from various sources"
    
    async def forward(self, agent_context):
        collected_news = []
        source_stats = {}
        
        # Collect from RSS sources
        if "rss" in self.params.sources:
            rss_news = await self.collect_from_rss()
            collected_news.extend(rss_news)
            source_stats["rss"] = len(rss_news)
        
        # Collect from API sources
        if "api" in self.params.sources:
            api_news = await self.collect_from_api()
            collected_news.extend(api_news)
            source_stats["api"] = len(api_news)
        
        # Filter news based on keywords
        filtered_news = await self.filter_news(collected_news)
        
        return NewsCollectorOutput(
            collected_news=filtered_news,
            source_stats=source_stats
        )
    
    async def collect_from_rss(self):
        # Simulate RSS collection
        return [
            {"title": "Breaking News", "content": "Important event", "source": "rss"},
            {"title": "Local Update", "content": "Community news", "source": "rss"}
        ]
    
    async def collect_from_api(self):
        # Simulate API collection
        return [
            {"title": "Tech News", "content": "Technology update", "source": "api"}
        ]
    
    async def filter_news(self, news_list):
        # Filter based on keywords
        filtered = []
        for news in news_list:
            if any(keyword in news["title"].lower() for keyword in self.params.filter_keywords):
                filtered.append(news)
        return filtered
Step 3: 实现新闻分析Block

class NewsAnalyzerParams(BlockParams):
    importance_threshold: float = 0.6
    relevance_keywords: list[str] = []

class NewsAnalyzerOutput(BlockOutput):
    analyzed_news: list[dict] = []
    importance_scores: dict = {}

class NewsAnalyzerBlock(Block):
    ParamsType = NewsAnalyzerParams
    OutputType = NewsAnalyzerOutput
    name = "news_analyzer"
    description = "Analyzes news content for importance and relevance"
    
    async def forward(self, agent_context):
        # Get news from previous block
        news_items = agent_context.get("collected_news", [])
        
        analyzed_news = []
        importance_scores = {}
        
        for news in news_items:
            # Analyze importance using LLM
            importance_prompt = f"""
            Analyze the importance of this news:
            Title: {news['title']}
            Content: {news['content']}
            
            Rate importance from 0-1 and explain why.
            """
            
            importance_response = await self.llm.atext_request([
                {"role": "system", "content": "You are a news analyst"},
                {"role": "user", "content": importance_prompt}
            ])
            
            # Extract importance score (simplified)
            importance_score = 0.7  # In real implementation, parse from response
            
            # Check if news meets importance threshold
            if importance_score >= self.params.importance_threshold:
                analyzed_news.append({
                    **news,
                    "importance_score": importance_score,
                    "should_distribute": True
                })
                importance_scores[news["title"]] = importance_score
        
        return NewsAnalyzerOutput(
            analyzed_news=analyzed_news,
            importance_scores=importance_scores
        )
Step 4: 实现新闻传播Block

class NewsDistributorParams(BlockParams):
    distribution_channels: list[str] = ["social", "email", "broadcast"]
    target_audience: list[int] = []

class NewsDistributorOutput(BlockOutput):
    distribution_results: dict = {}
    audience_reached: int = 0

class NewsDistributorBlock(Block):
    ParamsType = NewsDistributorParams
    OutputType = NewsDistributorOutput
    name = "news_distributor"
    description = "Distributes news to target audience"
    
    async def forward(self, agent_context):
        # Get analyzed news
        analyzed_news = agent_context.get("analyzed_news", [])
        
        distribution_results = {}
        audience_reached = 0
        
        for news in analyzed_news:
            if news.get("should_distribute", False):
                # Distribute through different channels
                for channel in self.params.distribution_channels:
                    result = await self.distribute_through_channel(news, channel)
                    distribution_results[f"{news['title']}_{channel}"] = result
                    audience_reached += result.get("audience_reached", 0)
        
        return NewsDistributorOutput(
            distribution_results=distribution_results,
            audience_reached=audience_reached
        )
    
    async def distribute_through_channel(self, news, channel):
        # Simulate distribution
        if channel == "social":
            # Send to nearby agents
            nearby_agents = self.environment.get_nearby_agents(radius=100)
            await self.messager.send_message_to_multiple(
                agent_ids=nearby_agents,
                content=f"News: {news['title']} - {news['content']}",
                message_type="news"
            )
            return {"audience_reached": len(nearby_agents), "channel": channel}
        
        return {"audience_reached": 0, "channel": channel}
Step 5: 集成为完整的新闻传播智能体

class NewsAgent(CitizenAgentBase):
    ParamsType = NewsAgentParams
    Context = NewsAgentContext
    BlockOutputType = NewsBlockOutput
    
    # Define status attributes
    StatusAttributes = [
        MemoryAttribute(
            name="news_collection_count",
            type=int,
            default_or_value=0,
            description="Total number of news items collected",
        ),
        MemoryAttribute(
            name="distribution_success_rate",
            type=float,
            default_or_value=0.0,
            description="Success rate of news distribution",
        ),
        MemoryAttribute(
            name="last_news_collection",
            type=str,
            default_or_value="",
            description="Timestamp of last news collection",
        ),
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize blocks
        self.collector_block = NewsCollectorBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=NewsCollectorParams(
                sources=["rss", "api"],
                filter_keywords=["breaking", "important", "urgent"]
            )
        )
        
        self.analyzer_block = NewsAnalyzerBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=NewsAnalyzerParams(
                importance_threshold=0.7
            )
        )
        
        self.distributor_block = NewsDistributorBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
            block_params=NewsDistributorParams(
                distribution_channels=["social", "broadcast"]
            )
        )
        
        # Set agent reference for blocks
        self.collector_block.set_agent(self)
        self.analyzer_block.set_agent(self)
        self.distributor_block.set_agent(self)
    
    async def forward(self):
        # Update context
        self.context.current_news_count = await self.memory.status.get("news_collection_count")
        self.context.last_collection_time = self.environment.get_datetime()
        
        # Execute news collection
        collection_result = await self.collector_block.forward(self.context)
        
        # Update context with collection results
        self.context.collected_news = collection_result.collected_news
        
        # Execute news analysis
        analysis_result = await self.analyzer_block.forward(self.context)
        
        # Update context with analysis results
        self.context.analyzed_news = analysis_result.analyzed_news
        
        # Execute news distribution
        distribution_result = await self.distributor_block.forward(self.context)
        
        # Update memory with results
        await self.memory.status.update("news_collection_count", 
                                      self.context.current_news_count + len(collection_result.collected_news))
        
        # Calculate success rate
        total_distributed = len(distribution_result.distribution_results)
        if total_distributed > 0:
            success_rate = distribution_result.audience_reached / total_distributed
            await self.memory.status.update("distribution_success_rate", success_rate)
        
        await self.memory.status.update("last_news_collection", self.context.last_collection_time)
        
        # Record experience in stream memory
        await self.memory.stream.add(
            content=f"Collected {len(collection_result.collected_news)} news items, "
                   f"distributed to {distribution_result.audience_reached} audience",
            metadata={"type": "news_cycle", "timestamp": self.context.last_collection_time}
        )
        
        return NewsBlockOutput(
            news_items=collection_result.collected_news,
            analysis_results=analysis_result.importance_scores,
            distribution_results=distribution_result.distribution_results
        )
