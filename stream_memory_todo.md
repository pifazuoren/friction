# Digital Friction 引入 AgentSociety-native Stream Memory 的改造方案

## 0. 一句话目标

在 **不破坏当前 helplessness / self-efficacy 结构化主机制** 的前提下，
学习 AgentSociety 原生 memory 的设计思想，
给 digital friction agent 加上一层更像原生 AgentSociety 的 `stream memory`，
让 agent 不只是“记住一些参数”，还会“记得自己经历过什么”，从而让：

- task appraisal 更像人在判断
- attribution 更像人在解释
- reflection / interview 更像人在回忆

最重要的原则是：

**结构化 memory 继续负责主更新；stream memory 负责经历记录与回忆辅助。**

核心原则可以浓缩成一句：

```text
Stream memory is not a second state updater. It is an auditable episodic evidence layer.
```

### 0.1 本次改造的核心立场

这次不是把当前 memory 改成纯原生 AgentSociety 风格，而是：

**完整学习 AgentSociety 原生 memory 的设计思想，而不是完整照搬它的实现逻辑。**

原生 AgentSociety 面向的是通用城市生活 agent，强调 agent 在城市中行动、社交、消费、移动和反思的连续经历。我们的实验面向的是数字摩擦场景下老年人的 helplessness 变化，必须保留可解释的心理状态变量、更新方程、参数和消融实验。

因此，本项目最终采用的是：

```text
AgentSociety-native inspired hybrid memory architecture
```

也就是：

- 学习原生的 `status memory + stream memory + cognition/reflection` 架构
- 保留我们已有的 helplessness / self-efficacy / controllability 结构化机制
- 让 stream memory 负责“经历证据”和“回忆上下文”
- 让结构化 memory 负责“正式状态”和“可解释更新”

一句话：

**原生 memory 给我们“像人一样经历和回忆”的框架；我们的结构化机制给论文“可以解释、可以消融、可以复现”的主干。**

### 0.2 研究假设

引入 stream memory 不是为了“让模型更复杂”，而是为了检验它是否能让 agent 的判断更贴近自己的过往经历。建议先把研究假设写清楚：

| 编号 | 假设 |
| --- | --- |
| H1 | 接入 stream retrieval 后，task appraisal 会更符合 agent 自己过去的数字任务经历。 |
| H2 | 有效帮助经历和成功恢复经历会缓和失败后的 stable / broad attribution，也就是降低“我总是不行 / 这类任务都不行”的判断倾向。 |
| H3 | stream 不直接改 `helplessness_delta`，只通过 `felt_control`、`expected_help_effectiveness`、`stability`、`scope_amplitude` 等中间变量间接影响主更新。 |
| H4 | reflection 第一阶段主要服务 interview / qualitative coherence，不先声称它会直接改变主行为轨迹。 |

这四条假设对应的实现边界是：

- H1 对应 task appraisal 接入 stream retrieval
- H2 对应 attribution 接入 help / recovery episodes
- H3 对应 explicit helplessness update equations 继续保留
- H4 对应 reflection 第一阶段不进入 task appraisal，除非单独做 ablation

---

## 1. 参考原生 AgentSociety 的哪些部分

这次改造不建议凭空发明一套“新记忆观”，而是直接借原生 AgentSociety 已经在用的模式。

### 1.1 原生框架的 memory 结构

原生 AgentSociety 的 memory 主要是两层：

- `status memory`
  - 存 agent 的当前状态、profile、plan、emotion 等
- `stream memory`
  - 存 agent 随时间发生过的事件与经历

核心代码：

- `packages/agentsociety/agentsociety/memory/memory.py`

### 1.2 原生实验最值得借的用法

#### 用法 A：事件发生后写进 stream

原生 citizen agent 在生成计划或形成认知后，会把内容写进 stream：

- `packages/agentsociety-community/agentsociety_community/agents/citizens/cityagent/plan_block.py`
- `packages/agentsociety-community/agentsociety_community/agents/citizens/cityagent/societyagent.py`

这说明原生思路是：

**先发生事件，再把事件变成一条经历，写进 stream。**

#### 用法 B：做 cognition / reflection 前先检索 stream

原生 cognition block 会先从 stream 里搜相关经历，再交给 LLM：

- `packages/agentsociety-community/agentsociety_community/agents/citizens/cityagent/cognition_block.py`

这说明原生思路是：

**LLM 不是对着真空做判断，而是先看 agent “记得的事”。**

#### 用法 C：用 `search_today()` 做当天回顾

原生框架已经支持：

- `stream.search(...)`
- `stream.search_today(...)`

这非常适合你们后面做：

- daily reflection
- stage reflection
- interview grounding

### 1.3 完整学习原生 memory，具体学什么

所谓“完整学习”，不是把原生代码原样搬过来，而是学习它的完整闭环：

| 原生 AgentSociety 思想 | 原生做法 | 我们的对应设计 |
| --- | --- | --- |
| 当前状态和经历分开 | `status memory` 存当前状态，`stream memory` 存经历流 | 结构化心理变量继续放在 status / structured memory，任务经历写入 stream |
| 事件发生后进入记忆 | 行动、社交、移动、经济变化后写入 `memory.stream.add(...)` | 每次 digital task / help / recovery / attribution 后写入 episode |
| 判断前先回忆 | cognition / attitude update 前检索 stream | task appraisal / attribution 前检索相关 digital episodes |
| 反思再回写 | daily thought 生成后再写入 stream | daily reflection / stage reflection 写回 stream |
| 经历和认知可关联 | plan step 的 memory ids 可关联 cognition | 一组数字摩擦事件可关联一次阶段性 reflection |

我们不照搬的是：

- 原生通用城市生活任务体系
- 原生对 emotion / attitude 的通用更新逻辑
- 让 LLM 基于 stream 直接生成主要心理变量数值
- 不经过验证就假设原生检索接口在当前实验中稳定可用

### 1.4 代码层面：复用接口，不复制大段逻辑

这套方案在代码层面应该遵循：

**尽量复用 AgentSociety 原生 memory 接口，少造新 memory 系统；但 digital friction 的语义、episode 模板和心理更新逻辑由我们自己定义。**

可以复用的原生接口形态包括：

```python
await self.memory.stream.add(topic=..., description=...)
await self.memory.stream.search(query=..., topic=..., top_k=...)
await self.memory.stream.search_today(topic=..., top_k=...)
await self.memory.stream.get_all()
await self.memory.stream.get_by_ids([...])
```

这些接口在设计上对应了：

- 按时间写入经历
- 按 topic 区分经历类型
- 基于文本的语义检索
- 今日记忆检索
- 按 node id 找回一组经历
- 导出完整 stream 记录

但这里必须区分：

- `add(...)`、`get_all()`、`get_by_ids(...)` 更接近可以直接复用的基础能力
- `search(...)`、`search_today(...)` 只能先视为“接口形态可复用”，不能在 Phase -1 之前默认它们已经可靠

原因是当前原生 `StreamMemory.search()` 默认带有 `type="stream"` metadata filter，而 `StreamMemory.add()` 写入 vectorstore 时主要写入的是 `topic / day / time`。如果这个 metadata 不匹配，语义检索可能返回空结果。

因此，实现时必须先走 Phase -1：

- 要么修复原生写入 metadata，让 stream document 写入 `type="stream"`
- 要么封装一个稳定 retrieval helper，在 `search(...)` 不可靠时用 `get_all()` + topic/time/filter fallback
- 要么在 helper 内显式规避有问题的 filter，并用测试确认检索结果稳定

Phase -1 是硬门槛：

**在写入 / 检索 / metadata / audit packet 没有验证通过前，不允许把 stream retrieval 接入任何 task appraisal 或 attribution prompt。**

因此，不建议新建一套独立的 `DigitalStreamMemory` 从头实现。更稳的做法是做一层很薄的 digital friction helper：

```python
async def _record_task_episode_stream(...):
    await self.memory.stream.add(
        topic="digital_task_episode",
        description=description,
    )

async def _retrieve_task_episodic_memory(...):
    return await _safe_stream_search(
        memory=self.memory,
        query=query,
        topic="digital_task_episode",
        top_k=5,
    )
```

也就是说：

- 原生 `memory.stream` 负责底层存储和检索
- 我们的 helper 负责数字摩擦语义
- 我们的结构化机制负责 helplessness / self-efficacy 更新

helper 写入 stream 时至少要保证每条 episode 可以追踪：

```text
type=stream
memory_id
topic
day
time
location
```

如果底层 `StreamMemory.add()` 暂时不能直接返回或写入这些 metadata，helper 也要通过 `get_all()` 或包装返回值形成可审计记录。

不要直接复制或照搬的部分：

- 原生 `cognition_block.py` 里的通用 attitude / emotion 更新
- 原生 cityagent 的 planning / mobility / economy memory topic
- 原生面向城市生活的自然语言模板
- 原生把 daily thought 当作通用 cognition 的方式

原因是我们的研究问题不是普通城市生活 agent，而是：

```text
digital friction -> uncontrollability appraisal -> helplessness / self-efficacy update
```

所以，最推荐的实现路线是：

```text
复用原生 memory 基础设施
自定义 digital friction episode 写入内容
自定义 retrieval query
自定义 prompt packet
保留 explicit helplessness update equations
```

---

## 2. 当前 digital friction 已经有的 stream 使用

你们现在不是完全没用 stream，只是用得很轻。

目前已有两处：

- 在 `proto/agent.py` 里，把 attribution 结果写进 `memory.stream`
  - topic: `digital_failure_attribution`
- 在 `main.py` 里，把 stage summary 写进 `memory.stream`
  - topic: `digital_friction_stage_summary`

这说明：

**当前代码已经有原生 stream 的基础能力，只是还没有把它接到主心理流程里。**

所以这次改造不是“从 0 开始”，而是：

**把已有的 stream 用法从“日志式记录”升级成“经历式记录 + 回忆式使用”。**

---

## 3. 这次改造的总原则

### 3.1 保留现在的结构化主机制

以下内容继续保留，不建议被 stream 替代：

- `task_domain_memory`
- `help_effect_memory`
- `recent_episode_buffer`
- `rationale_memory`
- `helplessness_score`

原因：

- 这些变量已经进入主更新链
- 它们可解释、可消融、可统计
- 它们更适合做形式化和论文表达

### 3.2 stream memory 不直接改 helplessness 公式

第一阶段必须坚持：

**stream memory 不能直接输出一个值去加减 helplessness。**

它只负责：

- 给 LLM 提供更像人的“过去经历”
- 辅助 task appraisal
- 辅助 attribution
- 支持 reflection / interview / qualitative analysis

### 3.3 stream memory 像“日记本”，结构化 memory 像“账本”

最通俗的理解：

- 结构化 memory：记账
- stream memory：记事

二者不是替代关系，而是互补关系。

### 3.4 status memory 和 stream memory 的边界

为了避免机制变糊，必须明确两类 memory 的责任边界。

| 类型 | 存什么 | 在论文里承担什么角色 |
| --- | --- | --- |
| structured / status memory | `helplessness_score`、`task_self_efficacy`、`controllable_success_memory`、`help_effect_memory`、recent failure pressure | 机制变量、更新方程、参数解释、消融实验 |
| stream memory | 每次数字任务经历、求助经历、恢复经历、归因解释、每日反思 | 经历证据、LLM 回忆上下文、访谈 grounding、定性解释 |

最重要的边界：

**stream memory 可以影响 LLM 怎么理解当前任务，但不能绕过主公式直接改 helplessness。**

### 3.5 stream memory 对主公式的间接影响必须显式记录

“不直接改 helplessness”不等于“对主更新没有影响”。

一旦 stream retrieval 接入 task appraisal，它就可能通过以下路径间接影响主公式：

```text
retrieved past episodes
  -> task appraisal
  -> felt_control / expected_help_effectiveness / perceived_task_difficulty / perceived_task_risk
  -> strategy choice / outcome / uncontrollability appraisal
  -> explicit helplessness update
```

如果 stream retrieval 接入 attribution，它还可能影响：

```text
retrieved similar failures or recoveries
  -> stability / scope_amplitude judgment
  -> scope Gaussian spillover
  -> task_self_efficacy of related task families
  -> later task appraisal and behavior
```

因此，stream memory 虽然不能直接输出 `helplessness_delta`，但它是主机制的间接输入。为了让这个路径可解释、可复现、可消融，后续实现必须记录：

- retrieval query
- retrieved episode text
- retrieved episode hash
- retrieved episode ids，如果能从接口稳定拿到
- retrieved episode count
- retrieval 是否进入 task appraisal payload
- retrieval 是否进入 attribution payload
- 当前实验属于 structured-only、stream-record-only、stream-appraisal，还是 stream-appraisal-attribution

如果系统使用 LLM cache，还必须把 retrieval 内容或 retrieval hash 放入 cache key。否则同一个 task appraisal prompt 可能在“有无 stream memory”两种条件下错误复用缓存结果。

如果写入 attempt payload / event log，也应至少保留：

- `retrieved_episodic_memory_query`
- `retrieved_episodic_memory_hash`
- `retrieved_episodic_memory_count`
- `retrieval_condition`
- `retrieval_status`

这样后续才能做 ablation 和审稿解释。

---

## 4. 推荐的 hybrid 结构

建议把 memory 分成三层来理解：

### Layer 1：Mechanism State（主机制层）

就是现在已有的结构化 memory：

- task-specific self-efficacy
- controllable success memory
- help effectiveness
- recent failure pressure
- helplessness

这层继续负责：

- 更新
- 公式
- 消融
- 统计

### Layer 2：Episodic Stream（经历层）

新加的 stream memory 主要负责存：

- 发生了什么任务
- 当时用了什么策略
- 结果是什么
- 这次感觉是不是不可控
- 这次有没有求助
- 这次是失败、恢复，还是回避

这层负责：

- “像人”的回忆
- 给 prompt 提供案例
- 给访谈提供真实经历脉络

### Layer 3：Prompt Packet（调用层）

把：

- 结构化 memory
- 检索回来的 episodic memory

一起压成给 LLM 的 payload。

这层负责：

- task appraisal prompt
- attribution prompt
- reflection / interview prompt

### Layer 4：Reflection Link（反思关联层）

这是更贴近原生 AgentSociety 的一层。

原生 agent 会把一组行动经历和后续 cognition 关联起来。我们可以借鉴这个思想，把若干 digital episodes 和后续 reflection 关联起来。

例如：

```text
Day 3:
payment_risk_confirmation failed
account_login_verification failed
profile_form_upload succeeded with help

daily reflection:
今天最让我不安的是支付和登录验证，我感觉这些任务容易出错；但资料上传在有人提示后还是能完成。
```

这层的作用不是产生新的主公式，而是让 agent 的后续访谈更像“真的经历过这些事”。

### 4.1 我们的最终 memory 架构图

注意：这里的 retrieval 必须检索“过去的 episodes”，不能先把当前事件写入 stream 再让当前 appraisal / attribution 检索到自己。否则会出现 current-event leakage。

```text
Before Current Task
        |
        v
Structured State + Past Stream Episodes
  - helplessness / self-efficacy / help memory
  - previous digital_task_episode
  - previous digital_help_episode
  - previous digital_recovery_episode
        |
        v
Retrieval Layer
  - retrieve relevant past task episodes
  - retrieve similar past failures / recoveries
  - retrieve today's previous events
        |
        v
LLM Prompt Layer
  - task appraisal
  - strategy deliberation, if enabled
  - event attribution, after outcome is observed
        |
        v
Task Event And Outcome
  - strategy choice
  - success / failure / abandon
  - event-level uncontrollability
        |
        v
Structured Update Layer
  - explicit helplessness update
  - task self-efficacy update
  - controllable success memory
  - help effect memory
  - scope Gaussian spillover
        |
        v
Write Current Stream Episode
  - digital_task_episode
  - digital_help_episode
  - digital_recovery_episode
  - digital_failure_attribution
  - daily / stage reflection when triggered
```

也就是说，单轮任务的安全闭环应是：

```text
检索过去经历
  -> 当前 task appraisal / strategy / outcome / attribution
  -> 结构化状态更新
  -> 写入当前 episode
  -> 留给下一轮任务使用
```

---

## 5. 第一阶段：先加哪些 stream 事件

第一阶段不宜贪多，建议先加 3 类 topic。

### 5.1 `digital_task_episode`

这是最核心的新 topic。

每次数字任务结束后，都写一条。

建议包含的信息：

- task family
- friction type
- strategy type
- outcome type
- whether help used
- whether negative feedback
- event-level uncontrollability
- 当前一轮最关键的自然语言解释

写法不要只写“字段堆叠”，也不要只写自由自然语言。

最稳的格式是：

```text
稳定标签前缀 + 一句自然语言经历描述
```

稳定标签用于检索、filter、debug 和论文统计；自然语言用于 LLM 回忆和访谈 grounding。

#### 推荐描述风格

不要写成：

```text
failure_after_attempt; uncontrollability=2; help_used=false
```

更建议写成：

```text
[digital_task_episode][family=payment_risk_confirmation][outcome=failure_after_attempt][strategy=try_self][help=false][uncontrollability=0.82] 我这次自己尝试支付结算，但还是失败了。页面反复报错，这让我感觉这件事不太受自己控制。
```

或者：

```text
[digital_task_episode][family=account_login_verification][outcome=success_self][strategy=try_self][help=false][uncontrollability=0.15] 这次登录验证我自己做成了。虽然过程有些紧张，但最后感觉这类任务还是可以学会。
```

推荐最小标签包括：

- `topic`
- `family`
- `outcome`
- `strategy`
- `help`
- `uncontrollability`

如果后续做 attribution episode，可以额外加：

- `locus`
- `stability`
- `scope_amplitude`

### 5.2 `digital_help_episode`

当 `seek_help_then_attempt` 发生时，再单独写一条帮助经历。

建议写：

- 为什么去求助
- 求助后是否成功
- 这次帮助更像 enabling 还是没帮上

目的：

- 后面检索“帮助经验”时更自然
- 不用只靠 `help_success_rate_smoothed` 这个数

### 5.3 `digital_recovery_episode`

当出现比较重要的恢复事件时写一条：

- 连续失败后第一次 `success_self`
- 连续失败后通过 enabling support 恢复

目的：

- 让 agent 不只记得失败，也记得恢复
- 避免 stream 变成“失败日记本”

---

## 6. 第二阶段：先把 stream 接到哪里

建议优先接两个位置，不要一上来全接。

### 6.1 优先接到 task appraisal

原因：

- 这是 agent 面对当前任务时最自然会“回想过去”的地方
- 原生 AgentSociety 的 cognition / planning 也很强调先检索相关经历

#### 当前可接入位置

- `examples/digital_friction_mvp/proto/llm_psychology.py`
- `_build_task_appraisal_user_payload(...)`

当前这里已经有：

- `Task-Specific Memory`
- `Recent Experience`

建议再加一块：

- `Retrieved Episodic Memory`

内容来源：

- 通过 `_safe_stream_search(...)` 检索最近 3~5 条和当前 task family 相关的过去经历
- 第一阶段只检索原始 episode，不检索 reflection，避免 reflection 双重计数

#### 推荐 query

第一版先用简单 query，不做复杂检索策略：

- `"{task_family} failure success help"`
- 或者 `"[{task_family}] digital task experience"`

第一版重点不是“最强检索”，而是“能稳定检出相似经历”。

#### retrieval packet

这里不要只返回一段字符串。retrieval helper 至少返回一个结构化 packet：

```text
text
ids
hash
count
query
topic
condition
status
```

其中：

- `text` 进入 prompt
- `hash` 进入 cache key / event log
- `count` 用于判断是否真的检索到经历
- `condition` 标记当前属于 structured-only、stream-record-only、stream-appraisal 等实验条件
- `status` 标记 ok / empty / fallback / error

### 6.2 第二个接入点：event attribution

原因：

- attribution 本来就是“解释这次失败意味着什么”
- 很适合参考过去相似失败与恢复经历

#### 当前可接入位置

- `examples/digital_friction_mvp/proto/attribution_inference.py`

建议新增一块 prompt 输入：

- `Retrieved Similar Episodes`

这里同样使用结构化 retrieval packet，而不是直接把 `stream.search(...)` 的字符串结果塞进 prompt。进入 prompt 的只是 packet 中的 `text` 字段，其他字段进入 cache key、attempt payload 和 event log。

让 LLM 在判断：

- `stability`
- `scope_amplitude`

时，不只是看当前结构化字段，还能看到：

- 最近类似失败是不是重复发生
- 类似任务有没有成功恢复过
- 失败是否在相似任务中持续出现

第一阶段 attribution 可以检索：

- `digital_task_episode`
- `digital_help_episode`
- `digital_recovery_episode`

暂时不要检索 `digital_daily_reflection`，除非单独设置 reflection-in-attribution ablation。

---

## 7. 第三阶段：做更像原生 AgentSociety 的 reflection

这一阶段才开始把 stream 用得更像原生实验。

### 7.1 每日 reflection 使用 `search_today()`

参考原生 AgentSociety cognition block 的做法，
可以每天结束时：

- 检索当天所有 `digital_task_episode`
- 检索当天所有 `digital_help_episode`
- 让 LLM 做一个短反思

比如输出：

- 今天最困难的数字任务是什么
- 今天有没有一次成功恢复改变了判断
- 今天自己对哪类任务更没把握了

然后把这段 reflection 再写回 stream。

建议 topic：

- `digital_daily_reflection`

### 7.2 stage reflection 继续保留，但让它吃到 episode stream

你们现在已有：

- `digital_friction_stage_summary`

后续可以改成：

- stage summary 不只总结结构化结果
- 还参考本阶段检索出来的若干 `digital_task_episode`

这样 interview 时会更像“在回忆阶段经历”，而不是只读表格。

### 7.3 防止 reflection 双重计数

reflection 很有价值，但第一阶段不能让它同时作为“经历总结”和“下一轮 appraisal 证据”反复进入主机制，否则会把同一批原始事件放大两次。

第一阶段规定：

- task appraisal 只检索原始 `digital_task_episode`、`digital_help_episode`、`digital_recovery_episode`
- attribution 只检索原始 task / help / recovery episodes，必要时加 `digital_failure_attribution`
- `digital_daily_reflection` 和 `digital_friction_stage_summary` 主要用于 interview / qualitative coherence
- 如果 reflection 要进入 appraisal 或 attribution，必须单独开一个 ablation 条件

也就是说：

```text
raw episodes -> appraisal / attribution
reflection -> interview / stage summary
```

不要默认做成：

```text
raw episodes -> reflection -> appraisal -> update
```

后者会增加解释难度，也会让主机制和 reflection 机制混在一起。

---

## 8. 推荐的实现顺序

### Phase -1：先核验并修复原生 stream 接口

在正式改造前，必须先验证并修复当前仓库里的原生 stream 接口是否能稳定用于我们的实验。

这是硬门槛，不是可选优化。

需要确认：

- `memory.stream.add(topic, description)` 是否能在 proto agent 中稳定写入
- `memory.stream.search(query, topic=..., top_k=...)` 是否能稳定检索到刚写入的内容
- `memory.stream.search_today(...)` 是否能正确按 day 检索
- `get_all()` 是否能导出完整 stream 记录，方便后续 debug 和论文分析
- 检索结果是否会受到 metadata filter 的影响
- 每条 stream document 是否有可审计 metadata

特别注意：

当前原生 `StreamMemory.search()` 里默认会加 `type="stream"` 的过滤，但 `StreamMemory.add()` 写入 vectorstore 时主要写的是 `topic / day / time`。后续实现前要用最小测试确认检索是否真的能返回结果。如果发现检索不到，不要绕开问题，要先修正或封装一个稳定 helper。

修复或 helper 封装后，至少要保证每条 episode 可以追踪：

```text
type=stream
memory_id
topic
day
time
location
```

只有 Phase -1 测试通过后，才能进入 Phase 1 的 prompt 接入。

### Phase 0：只补写 stream，不改 prompt

先做：

- 每次任务结束写 `digital_task_episode`
- 每次帮助事件写 `digital_help_episode`
- 每次关键恢复写 `digital_recovery_episode`

先不改 LLM prompt。

目的：

- 先保证 stream 里真的有内容
- 先让 episode 数据积累起来

### Phase 1：只接 task appraisal

在 task appraisal 里加入：

- `Retrieved Episodic Memory`

但先不接 attribution。

目的：

- 先观察 appraisal 文本和打分是否变得更自然

### Phase 2：再接 attribution

在 attribution prompt 里加入：

- 最近相似失败
- 最近相似恢复

目的：

- 提高 stability / scope 判断的“经历感”

### Phase 3：再做 daily / stage reflection

等前两阶段稳定后再做。

### Phase 4：做机制消融和论文验证

当 stream memory 接入稳定后，再做面向论文的验证。

基础消融必须至少比较：

- structured-only：只有当前结构化 memory，没有 stream retrieval
- stream-record-only：写 stream，但不把 stream 放进 prompt
- stream-appraisal：stream 接入 task appraisal
- stream-appraisal-attribution：stream 同时接入 task appraisal 和 attribution

建议优先追加：

- failure-only-stream：只给失败 episode，不给 help / recovery episode
- failure+recovery-stream：同时给失败、有效帮助和恢复 episode
- retrieval-empty-control：走同样 retrieval pipeline，但返回空 packet，用来排除“多一个 prompt section”本身造成的影响

robustness 阶段再考虑：

- shuffled-stream：打乱 episode 与 agent / 时间的对应关系
- wrong-agent-stream：给错误 agent 的 stream，测试个体化记忆是否重要
- top_k sensitivity：比较 top_k=1 / 3 / 5 / 10
- reflection-in-appraisal：让 reflection 进入 appraisal，单独测试它是否改变主行为轨迹

这样可以回答一个关键审稿问题：

**stream memory 到底只是让叙述更自然，还是会实质改变 agent 的任务判断、归因和行为轨迹？**

---

## 9. 最小可执行改造清单

### 9.0 新增 stream 接口核验测试

建议先补一个最小测试，确认原生接口真的可用。

测试目标：

- 写入一条 `digital_task_episode`
- 用 `topic="digital_task_episode"` 检索回来
- 用 task family 关键词检索回来
- 用 `search_today()` 检索回来
- 用 `get_all()` 能看到完整字段

如果这里不稳定，后面 task appraisal / attribution 接入都先不要做。

### 9.0.1 新增 metadata 与 audit packet 测试

除了确认能检索回来，还要确认检索结果可审计。

测试目标：

- 写入 episode 后能拿到或恢复 `memory_id`
- metadata 中能追踪 `type=stream`、`topic`、`day`、`time`、`location`
- retrieval helper 能返回结构化 packet
- packet 至少包含 `text`、`ids`、`hash`、`count`、`query`、`topic`、`condition`、`status`
- packet 的 `hash` 会进入 LLM cache key
- packet 的 `hash/count/condition/status` 会进入 event log 或 attempt payload

### 9.1 新增 stream 写入 helper

建议在：

- `examples/digital_friction_mvp/proto/agent.py`

新增几个 helper：

- `_record_task_episode_stream(...)`
- `_record_help_episode_stream(...)`
- `_record_recovery_episode_stream(...)`

### 9.2 新增 episodic retrieval helper

建议也放在：

- `examples/digital_friction_mvp/proto/agent.py`
  或
- `examples/digital_friction_mvp/proto/llm_psychology.py`

比如：

- `_retrieve_task_episodic_memory(...)`

第一版也不要只输出字符串，至少输出一个轻量结构化 packet：

```text
{
  "text": "...",
  "ids": [...],
  "hash": "...",
  "count": 3,
  "query": "...",
  "topic": "digital_task_episode",
  "condition": "stream-appraisal",
  "status": "ok"
}
```

如果检索失败，也要返回：

```text
{
  "text": "Nothing",
  "ids": [],
  "hash": "...",
  "count": 0,
  "query": "...",
  "topic": "digital_task_episode",
  "condition": "stream-appraisal",
  "status": "empty" 或 "fallback" 或 "error"
}
```

### 9.3 task appraisal payload 增加一块

位置：

- `_build_task_appraisal_user_payload(...)`

新增字段：

- `Retrieved Episodic Memory`

### 9.4 attribution payload 增加一块

位置：

- `attribution_inference.py`

新增字段：

- `Retrieved Similar Episodes`

---

## 10. 哪些事第一阶段不要做

### 10.1 不要删现有结构化 memory

第一阶段绝对不要删：

- `task_domain_memory`
- `help_effect_memory`
- `recent_episode_buffer`

### 10.2 不要让 stream 直接决定 helplessness 数值

不要做这种设计：

- “LLM 看了 3 条 stream memory，然后输出 helplessness_delta”

这会让主机制的解释性大幅下降。

### 10.3 不要一开始就做复杂 multi-query retrieval

第一版先简单 query + top_k 即可。

### 10.4 不要把 stream 当作唯一真实记忆

stream 更像经历层，不是用来替代主状态层的。

### 10.5 不要让 stream retrieval 变成新的黑箱

不要让 prompt 只写：

- “请根据记忆判断当前状态”

更好的写法是让 LLM 明确区分：

- 当前结构化状态是什么
- 检索到的过去经历是什么
- 当前任务是什么
- 它只能基于这些信息输出 appraisal / attribution，不直接输出主更新量

### 10.6 不要默认把 reflection 放回 appraisal

第一阶段不要让 `digital_daily_reflection` 或 `digital_friction_stage_summary` 进入 task appraisal。

原因：

- reflection 已经是对原始 episodes 的二次总结
- 如果又进入 appraisal，可能重复计算同一批失败或恢复经历
- 审稿时会更难区分是 raw episode 起作用，还是 reflection 起作用

如果确实要让 reflection 参与 appraisal，必须作为单独实验条件：

```text
reflection-in-appraisal
```

并且与以下条件分开比较：

```text
stream-appraisal
stream-appraisal-attribution
```

---

## 11. 为什么这套方案比“直接改成原生风格”更稳

如果直接改成纯原生风格，会有两个问题：

### 问题 1：机制会变糊

你们现在最重要的是：

- helplessness 怎么更新
- scope 怎么扩散
- self-efficacy 怎么中介

这些都需要结构化、可分解的变量。

### 问题 2：实验很难做消融

如果全靠检索出来的几段经历让 LLM 判断，
后面就会很难回答：

- 为什么这次涨这么多
- 为什么这次是 stable 不是 mixed
- 为什么 world A 和 world B 差这么多

所以更稳的做法一定是：

**原生 stream 用来“更像人”，结构化 memory 用来“更像模型”。**

---

## 12. 最推荐的最终形态

最终比较理想的形态是：

### 12.1 主更新层

继续保留当前：

- helplessness update
- efficacy / controllable success memory
- scope Gaussian spillover

### 12.2 episodic 层

增加：

- task episodes
- help episodes
- recovery episodes
- attribution episodes
- daily reflections

### 12.3 prompt 层

对 LLM 来说，同时看到：

- 结构化 summary
- episodic retrieval

这样既像人，又不会丢机制清晰度。

---

## 13. 建议的下一步

如果按“最小闭环”推进，建议顺序如下：

1. 先完成 Phase -1：验证并修复 stream 写入、检索、metadata 和 audit packet
2. 再补写 `digital_task_episode`
3. 再补写 `digital_help_episode` 和 `digital_recovery_episode`
4. 做 `_safe_stream_search(...)` 和结构化 retrieval packet
5. 先接到 task appraisal prompt，并把 retrieval hash/count/condition 写入 cache key 与 event log
6. 跑 1 seed 看 prompt 和行为有没有明显变得更自然
7. 稳定后再接 attribution prompt
8. 最后再做 daily reflection / stage reflection，且第一阶段只用于 interview / qualitative coherence

---

## 14. 一句话结论

**最好的方向不是把当前 memory 改成纯原生 AgentSociety 风格，而是完整学习原生 AgentSociety 的 memory 设计思想：用 status memory 保存当前状态，用 stream memory 保存经历流，用 reflection 把经历组织成可回忆的心理叙事；同时保留我们现在的结构化机制层，确保 helplessness 更新仍然可解释、可消融、可复现。**

---

## 15. 后续论文里可以怎么表述

如果后续写论文，可以这样表述：

```text
Inspired by the native memory architecture of AgentSociety, we design a hybrid memory mechanism for digital friction agents. The structured memory layer maintains formal psychological states, including helplessness, task-specific self-efficacy, controllable success memory, and help effectiveness. In parallel, an auditable episodic stream memory records digital task experiences, help-seeking episodes, recovery episodes, and attribution reflections. Retrieved stream memories are used as contextual evidence for LLM-based appraisal and attribution, while the final psychological state transitions remain governed by explicit update equations. Stream memory is therefore not a second state updater, but an episodic evidence layer whose retrieval effects are tracked through cache keys, payloads, logs, and ablation conditions.
```

中文讲法：

```text
我们借鉴 AgentSociety 原生的 status memory 与 stream memory 双层设计，但没有直接照搬其通用城市生活 agent 的实现逻辑。对于本研究，结构化 memory 负责保存可解释的心理状态变量并参与正式更新；stream memory 负责记录数字摩擦经历，并在 task appraisal、attribution 和 reflection 中作为可检索、可审计的经历证据。stream memory 不是第二套状态更新器，而是 episodic evidence layer；其检索内容会进入 cache key、payload、日志和消融条件。这样既保留了 agent 的经历连续性，也保证了 helplessness 更新机制的可解释性和可消融性。
```
