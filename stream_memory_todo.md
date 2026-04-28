# Digital Friction 引入原生 Stream Memory 的改造方案

## 0. 一句话目标

在 **不破坏当前 helplessness / self-efficacy 结构化主机制** 的前提下，
给 digital friction agent 加上一层更像原生 AgentSociety 的 `stream memory`，
让 agent 不只是“记住一些参数”，还会“记得自己经历过什么”，从而让：

- task appraisal 更像人在判断
- attribution 更像人在解释
- reflection / interview 更像人在回忆

最重要的原则是：

**结构化 memory 继续负责主更新；stream memory 负责经历记录与回忆辅助。**

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

写法不要只写“字段堆叠”，而要更像经历句子。

#### 推荐描述风格

不要写成：

```text
failure_after_attempt; uncontrollability=2; help_used=false
```

更建议写成：

```text
[payment_checkout] 我这次自己尝试支付结算，但还是失败了。页面反复报错，这让我感觉这件事不太受自己控制。
```

或者：

```text
[login_verification] 这次登录验证我自己做成了。虽然过程有些紧张，但最后感觉这类任务还是可以学会。
```

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

- 从 `memory.stream.search(...)` 里检索最近 3~5 条和当前 task family 相关的经历

#### 推荐 query

第一版先用简单 query，不做复杂检索策略：

- `"{task_family} failure success help"`
- 或者 `"[{task_family}] digital task experience"`

第一版重点不是“最强检索”，而是“能稳定检出相似经历”。

### 6.2 第二个接入点：event attribution

原因：

- attribution 本来就是“解释这次失败意味着什么”
- 很适合参考过去相似失败与恢复经历

#### 当前可接入位置

- `examples/digital_friction_mvp/proto/attribution_inference.py`

建议新增一块 prompt 输入：

- `Retrieved Similar Episodes`

让 LLM 在判断：

- `stability`
- `scope_amplitude`

时，不只是看当前结构化字段，还能看到：

- 最近类似失败是不是重复发生
- 类似任务有没有成功恢复过
- 失败是否在相似任务中持续出现

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

---

## 8. 推荐的实现顺序

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

---

## 9. 最小可执行改造清单

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

第一版输出就直接是字符串，不要先过度设计复杂 schema。

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

1. 先补写 `digital_task_episode`
2. 再补写 `digital_help_episode`
3. 做一个最简单的 `stream.search(...)` 检索 helper
4. 先接到 task appraisal prompt
5. 跑 1 seed 看 prompt 和行为有没有明显变得更自然
6. 稳定后再接 attribution prompt
7. 最后再做 daily reflection / stage reflection

---

## 14. 一句话结论

**最好的方向不是把当前 memory 改成纯原生 AgentSociety 风格，而是参考原生实验，把 stream memory 加成一层“经历回忆层”，同时保留你们现在的结构化机制层。**

