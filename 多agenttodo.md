# 多 agent support ecology todo

## 目标定位

本文件记录一个后续扩展方向：把当前“老年人遇到数字摩擦”的实验，从单个 older adult agent 加环境参数，升级为轻量的 **任务触发型多 agent 支持生态**。

核心原则：

- 研究场景是泛化的老年人日常数字服务摩擦，不是养老院专属场景。
- 不做自由闲聊式多 agent，而做围绕具体 digital friction 事件触发的互动。
- LLM 负责语义理解、求助沟通、支持回应、心理解释。
- outcome truth 仍由受控环境 / outcome model 决定，避免让 helper LLM 随意编造任务是否成功。
- Bayesian gated-lite2 仍作为 older adult agent 的 action-outcome learning layer，不被 helper agent 替代。

## 为什么要做

当前 support 如果只是 `support_quality = 0/1/2` 或一个 world scalar，审稿人容易认为机制太手写、太简化。

多 agent support ecology 的价值是：把“支持”从一个冷冰冰的参数，变成真实生活中不同人如何回应老年人的过程。

更强的论文问题可以变成：

> 老年人在日常数字服务中遇到摩擦时，家人、同伴、客服、社区志愿者等支持来源如何影响其可控性感知、自我效能、求助、代理依赖、回避和线下替代？

## 最小角色设计

第一版不要追求大规模。建议从小型 micro-society 开始。

| 角色 | 主要作用 | 是否第一版必须 |
|---|---|---|
| OlderAdultAgent | 核心模拟对象，经历 digital friction，更新 helplessness / self-efficacy / Bayesian posterior | 必须 |
| FamilyHelperAgent | 提供家庭支持，区分耐心教学、直接代办、不耐烦、不可用 | 优先 |
| PeerOlderAdultAgent | 提供同伴成功 / 失败经验，影响社会规范和风险感知 | 优先 |
| CustomerServiceAgent | 提供平台客服回应，区分清楚解释、模板回复、转人工失败 | 可选但推荐 |
| CommunityVolunteerAgent | 提供教学式帮助，适合作为 recovery intervention | 后续扩展 |

## 互动方式

不要让 agent 没事聊天。互动只在任务事件触发。

基本流程：

```text
older adult 遇到数字任务
-> LLM appraisal: 难度、风险、可控性、是否值得尝试
-> 策略选择: 自己尝试 / 求助 / 回避 / 线下替代
-> 如果求助，向 family / peer / customer service / volunteer 发消息
-> helper agent 返回支持行为
-> older adult 根据支持回应继续尝试、放弃或转线下
-> outcome_model 生成真实结果
-> 更新 attribution / helplessness / self-efficacy / memory / Bayesian posterior
-> 写入 audit / replay
```

## 支持行为类型

FamilyHelperAgent 的支持不应该只是“帮了 / 没帮”，至少区分：

| 支持类型 | 通俗解释 | 预期心理影响 |
|---|---|---|
| enabling support | 耐心解释步骤，让老人自己完成 | 提升 self-efficacy 和 perceived control |
| substituting support | 直接拿手机代办 | 任务可能成功，但增加 proxy reliance |
| dismissive support | 不耐烦、责备、催促 | 增加 anxiety / helplessness |
| unavailable support | 没人回应或没时间 | 增加 avoid / offline switching |

PeerOlderAdultAgent 的作用主要是经验传播：

| 同伴经验 | 例子 | 预期影响 |
|---|---|---|
| success story | “我上次也卡住了，后来有人教我，我现在会了。” | 增强可控性感 |
| failure story | “这个太麻烦了，我以后都去线下办。” | 增强回避规范和 scope spillover |
| neutral story | “我不太清楚，你可以问问别人。” | 影响较弱 |

CustomerServiceAgent 的回应可以区分：

| 客服回应 | 例子 | 预期影响 |
|---|---|---|
| clear explanation | 解释错误原因和下一步 | 提高 perceived platform controllability |
| template reply | “请按页面提示操作。” | 支持感弱，可能增加挫败 |
| failed escalation | 转人工失败 / 排队过久 | 降低 trust 和 help effectiveness |

## 建议使用结构化消息

自然语言可以保留给 LLM，但内部记录最好结构化，方便审计和统计。

求助消息示例：

```json
{
  "type": "support_request",
  "task_family": "payment_confirmation",
  "friction_type": "verification_failure",
  "requested_help": "teach_me",
  "current_appraisal": {
    "difficulty": 0.72,
    "perceived_control": 0.38,
    "risk": 0.64
  },
  "day": 3
}
```

支持回应示例：

```json
{
  "type": "support_response",
  "source": "family",
  "support_style": "enabling",
  "instruction_quality": 0.8,
  "emotional_tone": "patient",
  "autonomy_preservation": 0.9,
  "proxy_completion": false,
  "response_text": "我一步一步教你，你先自己点这里。"
}
```

同伴经验示例：

```json
{
  "type": "peer_experience",
  "source": "peer",
  "story_valence": "success",
  "task_family": "appointment_booking",
  "message_text": "我上次也不会，后来有人教我，我自己挂上号了。"
}
```

## 和 Bayesian gated-lite2 的关系

多 agent 不是替代 Bayesian gated-lite2，而是给它提供更真实的 action-outcome experience context。

建议关系：

```text
LLM appraisal + social support response
-> pi_llm_ref
Bayesian posterior over P(outcome | task_family, action, optional support_context)
-> pi_bayes
confidence gate
-> pi_final
actual action
-> outcome
-> posterior update only for actual action
```

第一版不建议把 support_context 立刻放进 Dirichlet key，避免状态空间爆炸。可以先记录在 audit metadata 中，后续再比较：

```text
v1: P(outcome | task_family, action)
v2: P(outcome | task_family, action, support_style)
```

## 当前实验和 AgentSociety 原生多 agent 的差异

当前 `digital_friction_mvp` 已经有多个 agent，但更像“多个 older adult agent 并行做同一套任务”。这些 agent 共享 world condition，但彼此之间基本没有真实互动。

当前机制大致是：

```text
多个 older adult agents
-> 各自遇到 digital task
-> 各自根据 LLM/rule/Bayesian 模块选择 action
-> outcome_model 根据 env scalar 生成结果
-> 各自更新 helplessness / memory / posterior
```

其中 support 主要来自：

```text
assist_level + human_support_level + accessibility_level
-> support_quality 0/1/2
```

这套结构适合做机制 sanity check，但如果要做更像社会模拟的多 agent，需要把 support 从 world scalar 变成“其他 agent 如何回应”的过程。

AgentSociety 原生例子值得学习的是：

```text
agent 有 friends / relationships
agent 可以 send_message_to_agent
agent 可以 do_chat 回应
workflow 可以做 MESSAGE_INTERVENE / ENVIRONMENT_INTERVENE / SAVE_CONTEXT / SURVEY
social network 可以初始化关系结构
```

## AgentSociety 原生多 agent 能力和出处

这些能力不是集中在一个例子里，而是分散在几个原生 examples 和 core agent 代码中。

| 能力 | 主要出处 | 原生实验怎么用 | 我们可以怎么借 |
|---|---|---|---|
| `friends` 状态 | `examples/polarization/message_agent.py` | `AgreeAgent` / `DisagreeAgent` 有 `friends` 列表，定时向朋友发送观点消息 | older adult 可以有 family helper / peer / customer service 联系对象 |
| `send_message_to_agent` | `examples/polarization/message_agent.py` | agent 遍历 friends，把 LLM 生成的消息发给每个 friend | older adult 求助时发送 `support_request` |
| `do_chat(message)` | `examples/polarization/message_agent.py`; `packages/agentsociety/agentsociety/cityagent/societyagent.py` | 收到消息后解析内容，用 LLM 生成回复，再发回 sender | helper 收到求助后返回 `support_response` |
| `relationships` / `relation_types` | `examples/rumor_spreader/utils.py` | 初始化 family / colleague / friend 等关系类型和关系强度 | 区分 family / peer / volunteer / customer service，不同关系影响回应概率和支持风格 |
| `chat_histories` / `interactions` | `examples/rumor_spreader/utils.py`; `SocietyAgent` 默认状态 | 为每对关系初始化聊天历史和互动记录 | 记录老人求助、家人回应、同伴故事、客服回应 |
| 多类 agent 共存 | `examples/polarization/echo_chamber.py` | 100 个普通 citizen + 1 个 AgreeAgent + 1 个 DisagreeAgent | older adult agents + FamilyHelperAgent + PeerOlderAdultAgent + CustomerServiceAgent |
| `SAVE_CONTEXT` | `examples/polarization/echo_chamber.py`; `examples/UBI/main.py` | 保存 attitude、chat histories、ubi_opinion 等状态 | 保存 support_response、support_style、peer_norm、Bayesian audit |
| `MESSAGE_INTERVENE` | `examples/prospect_theory/step_three.py` | 按 profile 给不同 agent 发中奖/未中奖消息，然后再测 survey | 给不同 older adult 注入同伴成功/失败故事或平台提示 |
| `ENVIRONMENT_INTERVENE` | `examples/hurricane_impact/hurricane.py` | RUN 几天后改变 weather，再继续 RUN | 阶段性改变 friction、platform_feedback_clarity、support availability |
| `SURVEY` | `examples/prospect_theory/step_three.py`; 当前 `digital_friction_mvp/main.py` | 干预前后测 happiness 等指标 | 干预前后测 self-efficacy、helplessness、trust、avoidance |

## 原生例子具体怎么用

### 1. Polarization: 消息互动

参考文件：

- `examples/polarization/message_agent.py`
- `examples/polarization/echo_chamber.py`

核心模式：

```text
Agent 有 friends
-> forward() 到时间触发
-> LLM 生成一条消息
-> send_message_to_agent(friend, message)
-> 对方 do_chat(message)
-> 对方解析消息并回复
```

对我们的启发：

```text
OlderAdultAgent 遇到 digital friction
-> 如果选择 seek_help，向 FamilyHelperAgent / CustomerServiceAgent 发 support_request
-> helper do_chat 收到后返回 support_response
-> OlderAdultAgent 根据 support_response 调整 perceived control / expected_help_effectiveness / proxy reliance
```

注意：原生 polarization 里消息是观点传播；我们不要照搬自由聊天，而要用结构化任务消息。

### 2. Rumor spreader: 关系网络初始化

参考文件：

- `examples/rumor_spreader/network_generator.py`
- `examples/rumor_spreader/utils.py`

核心模式：

```text
生成 public_network / private_network
-> simulation.filter(types=(SocietyAgent,)) 获取 agent ids
-> 给每个 agent update friends / public_friends
-> 写入 relationships / relation_types
-> 初始化 chat_histories / interactions
```

对我们的启发：

```text
为 older adult 初始化支持生态：
family helper: 高关系强度
peer older adult: 中等关系强度
community volunteer: 中等支持可得性
customer service: 低关系亲密度但有平台职责
```

实现时要小心：network node index 不一定等于 AgentSociety 的真实 agent id，必须显式映射。

### 3. Hurricane impact: 环境阶段干预

参考文件：

- `examples/hurricane_impact/hurricane.py`

核心模式：

```text
RUN 3 days
-> ENVIRONMENT_INTERVENE weather = hurricane
-> RUN 3 days
-> ENVIRONMENT_INTERVENE weather = normal
-> RUN 3 days
```

对我们的启发：

```text
Stage 1: 普通数字任务
Stage 2: 高摩擦 / 低清晰度平台反馈
Stage 3: 引入 enabling support 或社区数字导师
Stage 4: transfer / scope spillover 测试
```

也就是说，AgentSociety 原生已经支持“跑几天、改环境、再跑几天”的实验节奏。

### 4. Prospect theory: 消息干预 + survey

参考文件：

- `examples/prospect_theory/step_three.py`

核心模式：

```text
先 SURVEY
-> MESSAGE_INTERVENE 给不同 profile 的 agent 发不同消息
-> 再 SURVEY
```

对我们的启发：

```text
先测 self-efficacy / helplessness
-> 给部分 agent 注入 peer success story
-> 给部分 agent 注入 peer failure / avoidance story
-> 再测 self-efficacy / avoidance / trust
```

这适合实现 `peer_norm = success / failure / neutral`，不用一开始就创建复杂 peer agent。

### 5. Echo chamber / UBI: 保存上下文

参考文件：

- `examples/polarization/echo_chamber.py`
- `examples/UBI/main.py`

核心模式：

```text
SAVE_CONTEXT key="attitude"
SAVE_CONTEXT key="chat_histories"
SAVE_CONTEXT key="ubi_opinion"
```

对我们的启发：

每次任务后都应该能保存和复盘：

```text
support_request
support_response
support_style
instruction_quality
emotional_tone
autonomy_preservation
proxy_completion
older adult actual action
outcome
helplessness_delta
Bayesian posterior update
```

## 哪些可以直接学，哪些暂时不要学

优先学习：

- `polarization/message_agent.py` 的 `send_message_to_agent` / `do_chat` 模式。
- `rumor_spreader/utils.py` 的关系初始化模式。
- `hurricane_impact/hurricane.py` 的阶段性环境干预。
- `prospect_theory/step_three.py` 的 message intervention + survey 前后测。
- `echo_chamber.py` / `UBI/main.py` 的 `SAVE_CONTEXT` 保存关键状态。
- `packages/agentsociety/agentsociety/agent/block.py` 的 `Block` / `BlockParams` / `BlockOutput` 模式。
- `packages/agentsociety/agentsociety/agent/dispatcher.py` 的 `BlockDispatcher` 模式。
- `packages/agentsociety/agentsociety/cityagent/blocks/social_block.py` 的 block 内部再调度子 block 模式。

暂时不要学：

- 不要追求 10k agents 或 city-scale。
- 不要做无边界自由聊天。
- 不要让 helper LLM 决定真实 outcome。
- 不要让 SocialBlock 自由接管你的 digital friction 实验逻辑。
- 不要把 support_style 同时硬写进 action、outcome、helplessness，避免新的自我强化循环。

## AgentSociety 原生 block 到底是什么

AgentSociety 原生 `Block` 不是简单的函数拆分，而是 agent 的可插拔行为能力模块。

核心出处：

```text
packages/agentsociety/agentsociety/agent/block.py
packages/agentsociety/agentsociety/agent/dispatcher.py
packages/agentsociety/agentsociety/cityagent/societyagent.py
packages/agentsociety/agentsociety/cityagent/blocks/social_block.py
```

原生 block 的基本结构：

```text
BlockParams:
  block 的配置参数

BlockOutput:
  block 的结构化输出

Block:
  有 toolbox / memory / environment / llm / context
  通过 async forward(context) 执行
```

原生 CityAgent 的流程大致是：

```text
needs_block.forward()
-> plan_block.forward()
-> step_execution()
-> dispatcher 根据 current_intention 选择 block
-> selected_block.forward(context)
-> result 写回 current_step.evaluation
-> cognition_block.forward()
```

常见 block：

```text
NeedsBlock
PlanBlock
CognitionBlock
MobilityBlock
SocialBlock
EconomyBlock
OtherBlock
```

`SocialBlock` 里还会继续拆子 block：

```text
SocialBlock
-> FindPersonBlock
-> MessageBlock
-> SocialNoneBlock
```

也就是说，原生 block 的特点是：

```text
有明确职责
有参数
有上下文
有结构化输出
能访问 LLM / memory / environment
可以由 dispatcher 根据 intention 选择
```

对当前 digital friction 实验的提醒：

```text
不是所有机制都适合交给 dispatcher 自由选择。
```

因为我们的实验链条有严格顺序：

```text
appraisal
-> policy
-> support interaction
-> outcome
-> attribution
-> state update
-> memory / audit
```

这些步骤不能让 LLM dispatcher 随意换顺序，否则会破坏 no-leakage 和因果边界。

因此，短期更适合：

```text
固定实验 pipeline + AgentSociety-style blocks
```

而不是：

```text
让 BlockDispatcher 接管整个 digital friction 主链
```

## HelperAgent 优先用原生 block/message 的设计

后续如果要更像原生 AgentSociety，优先不要从 Bayesian policy 或 helplessness update 开始 block 化，而应从 HelperAgent 开始。

原因：

```text
HelperAgent 本来就是一个独立 agent；
求助本来就是 agent-agent message；
support response 本来就适合做结构化 BlockOutput；
这比把整个 agent.py 重构成原生 block 风险小。
```

推荐设计：

```text
OlderAdultAgent
  seek_help action selected
  -> send_message_to_agent(helper_id, support_request)

FamilyHelperAgent
  do_chat(message)
  -> SupportResponseBlock.forward(context)
  -> return structured support_response

OlderAdultAgent
  receives support_response
  -> outcome_model consumes support_response
  -> state_update / Bayesian audit records support process
```

`support_request` 继续保持结构化：

```json
{
  "type": "support_request",
  "task_family": "payment_confirmation",
  "friction_type": "verification_failure",
  "requested_help": "teach_me",
  "current_appraisal": {
    "difficulty": 0.72,
    "perceived_control": 0.38,
    "risk": 0.64
  },
  "day": 3
}
```

`SupportResponseBlock` 输出结构化 `BlockOutput`：

```json
{
  "success": true,
  "evaluation": "provided enabling support",
  "consumed_time": 8,
  "node_id": null,
  "support_response": {
    "type": "support_response",
    "source": "family",
    "support_style": "enabling",
    "instruction_quality": 0.8,
    "emotional_tone": "patient",
    "autonomy_preservation": 0.9,
    "proxy_completion": false,
    "response_text": "我一步一步教你，你先自己点这里。"
  }
}
```

第一版 HelperAgent block 只需要一个主 block：

```text
SupportResponseBlock
```

后续再拆子 block：

```text
SupportUnderstandingBlock
SupportStyleSelectionBlock
SupportResponseGenerationBlock
```

第一版不要让 HelperAgent 自由决定任务成功与否。HelperAgent 只决定：

```text
怎么帮
语气如何
是否保留自主性
是否代办
解释质量如何
```

真实 outcome 仍由：

```text
outcome_model
```

在读取 `support_response` 后受控生成。

### 为什么不优先把 Bayesian/helplessness 改成原生 block

`bayesian_policy_lite`、`Huys-Dayan-lite controllability`、`state_update` 都是严格时序机制：

```text
必须在 outcome 前或 outcome 后的固定位置执行
必须保证不读取未来信息
必须保持 off / shadow / gated 行为可复现
```

它们可以先做成 logical block：

```text
BayesianPolicyBlock
ControllabilityAuditBlock
PsychologicalUpdateBlock
```

但短期不建议交给 AgentSociety `BlockDispatcher` 选择执行。

更稳的写法：

```text
当前实现采用 AgentSociety-style modular pipeline；
HelperAgent 的支持互动优先采用原生 message / block 模式；
核心实验因果链仍保持固定 orchestrated pipeline。
```

## 对我们最现实的接法

第一步不一定要马上新建很多 agent，可以按两级路线走：

```text
Level 1: workflow message intervention
-> 用 MESSAGE_INTERVENE 注入 peer success/failure story
-> 观察 appraisal / action / survey / Bayesian posterior 是否变化

Level 2: task-triggered helper agent
-> 老人 seek_help 时发送 support_request
-> helper do_chat 返回 support_response
-> outcome_model 仍控制真实结果
-> audit 记录互动全过程
```

这比直接做完整 multi-agent society 更稳。

## Phase C-lite 实施建议

不要最近一周就做完整多 agent。建议等 gated-lite2 shadow-only 稳定后再做。

### Phase C0: 文档和实验设计

- [ ] 明确场景表述：泛化老年人日常数字摩擦。
- [ ] 明确 support ecology 不是养老院专属。
- [ ] 定义支持来源：family / peer / customer_service / community_volunteer / platform_feedback。
- [ ] 定义支持风格：enabling / substituting / dismissive / unavailable。
- [ ] 定义 peer norm：success / failure / neutral。

### Phase C1: 轻量 world 参数拆分

先不创建真实 helper agent，只把 world scalar 拆成更有机制意义的字段。

- [ ] `support_availability`
- [ ] `support_style`
- [ ] `platform_feedback_clarity`
- [ ] `offline_alternative_availability`
- [ ] `peer_norm`
- [ ] 在 audit payload 中记录这些字段。

### Phase C2: 最小 helper agent

引入一个 FamilyHelperAgent，只有在 older adult 求助时触发。

- [ ] 新增 helper agent class。
- [ ] HelperAgent 优先采用 AgentSociety 原生 message 模式：`send_message_to_agent` + `do_chat`。
- [ ] HelperAgent 内部优先实现 `SupportResponseBlock`，返回结构化 `support_response`。
- [ ] 支持结构化 `support_request`。
- [ ] 返回结构化 `support_response`。
- [ ] older adult 根据 `support_response` 调整 expected help effectiveness / perceived control / proxy reliance。
- [ ] outcome 仍由 outcome_model 决定。
- [ ] replay / audit 记录 request 和 response。

### Phase C3: 同伴经验传播

引入少量 PeerOlderAdultAgent。

- [ ] peer 生成 success / failure / neutral story。
- [ ] older adult 在任务前读取 peer norm 或最近 peer stories。
- [ ] peer experience 只影响 appraisal / social norm memory，不直接决定 outcome。
- [ ] 记录 peer story 对 perceived controllability / avoidance norm 的影响。

### Phase C4: 客服 / 平台 agent

引入 CustomerServiceAgent 或 PlatformSupportAgent。

- [ ] 根据 platform_feedback_clarity 生成 clear explanation / template reply / failed escalation。
- [ ] 影响 trust、help effectiveness、platform controllability。
- [ ] 不直接替代 environment truth。

### Phase C5: 小型实验设计

建议做一个轻量 2x2x2：

| 因子 | 条件 |
|---|---|
| Friction | low vs high |
| Support style | enabling vs substituting |
| Peer norm | success vs failure |

核心指标：

- self-attempt rate
- help-seeking type
- proxy reliance
- offline switching
- avoid / delay rate
- self-efficacy
- helplessness
- perceived controllability
- Bayesian posterior confidence
- scope spillover
- attribution / interview coding

## 风险和边界

- 不要让 helper LLM 决定真实 outcome。
- 不要把多 agent 做成自由闲聊，成本高且难解释。
- 不要一开始就加入太多角色。
- 不要让 support_style 同时直接决定 action、outcome、helplessness，避免又形成手写自我强化循环。
- 不要把养老院写成唯一场景。养老院 / 社区可以是采样入口，不是外推边界。

## 最近一周建议

最近一周不建议直接实现完整多 agent。

更合理顺序：

1. 保存当前 baseline。
2. 完成 Bayesian gated-lite2 shadow-only。
3. 把场景和术语统一为“老年人日常数字服务摩擦”。
4. 轻量拆分 support/world 参数。
5. 等 shadow audit 稳定后，再做 Phase C-lite helper agent。
6. 如果做 helper agent，优先采用原生 message/block 方式实现 `SupportResponseBlock`，不要先大规模重构整个 `agent.py`。
