# 多 agent support ecology todo

## 目标定位

本文件记录一个后续扩展方向：把当前“老年人遇到数字摩擦”的实验，从单个 older adult agent 加环境参数，升级为轻量的 **任务触发型多 agent 支持生态**。

核心原则：

- 研究场景是泛化的老年人日常数字服务摩擦，不是养老院专属场景。
- 第一版只做最小闭环：`OlderAdultAgent -> FamilyHelperAgent -> support_response -> outcome_model -> audit / memory`。
- 不做自由闲聊式 multi-agent，而做围绕具体 digital friction 事件触发的单轮互动。
- LLM 负责语义理解、求助沟通、支持回应、心理解释。
- outcome truth 仍由受控环境 / outcome model 决定，避免让 helper LLM 随意编造任务是否成功。
- Bayesian gated-lite2 仍作为 older adult agent 的 action-outcome learning layer，不被 helper agent 替代。
- Huys-Dayan-inspired controllability 仍作为 controllability audit / modulation layer，不被 helper agent 替代。
- `support_response` 第一版只直接进入 outcome model、event appraisal、experience memory 和 audit；不要直接改 helplessness delta、Bayesian posterior key、`C_family` 或 scope spillover。

## 当前判断

**只值得先做最小版。**

当前 support 主要还是：

```text
assist_level + human_support_level + accessibility_level
-> support_quality 0/1/2
```

这足够做 mechanism sanity check，但如果论文要讲 “support ecology”，它会显得过于参数化。最小增强不是做完整社交网络，而是把 help-seeking 变成一次可记录、可回放、可消融的 agent-to-agent support interaction。

第一版目标：

```text
seek_help_then_attempt
-> structured support_request
-> FamilyHelperAgent
-> structured support_response
-> outcome_model consumes response-derived support features
-> downstream psychology / memory / audit updates
```

第一版不做：

```text
free-form social chat
multi-turn helper negotiation
HelperAgent decides task success
support_style enters Dirichlet key
BlockDispatcher controls psychology / posterior / state update
Family + Peer + Customer + Volunteer all at once
```

## 外部审阅后的收敛结论

根据外部审阅意见，本文件后续主线应从“做一个复杂多 agent 社会”收敛为：

```text
只先把 support 从 world scalar 升级为 task-triggered, single-turn, structured, auditable support interaction。
```

也就是说，第一版不是追求“更热闹的 agent 社会”，而是修复当前实验里最薄的一环：

```text
support 现在主要是环境参数
-> support 之后应变成一次可记录、可回放、可消融的帮助过程
```

审稿视角下更稳的判断：

| 口径 | 可以主张什么 | 不要主张什么 |
|---|---|---|
| AAAI AISI | controlled support process 提升构念效度 | 完整真实社会支持生态 |
| AAMAS | support 从参数升级为可观测 agent-to-agent interaction | 只是给 scalar 套一层 agent 外皮 |
| AAAI Main | auditable augmentation + replay + ablation | full AgentSociety-native free simulation |

第一版的论文表达应使用：

```text
task-triggered social support interactions with an auditable cognitive-behavioral update pipeline
```

不要把贡献写成：

```text
full social simulation
free multi-agent behavior
helper agent determines human psychological state
```

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
| FamilyHelperAgent | 提供家庭支持，区分耐心教学、直接代办、不耐烦、不可用 | 第一版必须 |
| PeerOlderAdultAgent | 提供同伴成功 / 失败经验，影响社会规范和风险感知 | 第二阶段，或先用 message intervention |
| CustomerServiceAgent | 提供平台客服回应，区分清楚解释、模板回复、转人工失败 | 第三阶段 |
| CommunityVolunteerAgent | 提供教学式帮助，适合作为 recovery intervention | 暂缓，recovery experiment 再考虑 |

第一版只做 `FamilyHelperAgent` 的原因：

- 它和当前 `seek_help_then_attempt` action 最直接对齐。
- 它能把 support 从 world scalar 升级成 interaction process。
- 它不需要复杂社交网络、peer diffusion 或平台客服状态。
- 它最容易做 coverage、no-leakage、replay determinism 和 ablation。

## 互动方式

不要让 agent 没事聊天。互动只在任务事件触发。

基本流程：

```text
older adult 遇到数字任务
-> LLM appraisal: 难度、风险、可控性、是否值得尝试
-> 策略选择: 自己尝试 / 求助 / 回避 / 线下替代
-> 如果 action = seek_help_then_attempt，向 FamilyHelperAgent 发 support_request
-> FamilyHelperAgent 返回 support_response
-> outcome_model 读取 support_response 派生出的 support features
-> outcome_model 生成真实结果
-> 更新 attribution / helplessness / self-efficacy / memory / Bayesian posterior
-> 写入 audit / replay
```

注意：

- `support_response` 可以影响帮助质量、放弃概率、成功概率和事后 appraisal。
- `support_response` 不直接决定真实 outcome。
- `support_response` 不直接写 helplessness delta、Bayesian posterior count、`C_family` 或 scope spillover。
- Peer / customer service / volunteer 都不是第一版主线。

## 支持行为类型

FamilyHelperAgent 的支持不应该只是“帮了 / 没帮”，至少区分：

| 支持类型 | 通俗解释 | 预期机制影响 |
|---|---|---|
| enabling support | 耐心解释步骤，让老人自己完成 | 提升 perceived control / expected help effectiveness / self-efficacy |
| substituting support | 直接拿手机代办 | 任务可能成功，但增加 proxy reliance，自我效能增益较弱 |
| dismissive support | 不耐烦、责备、催促 | 增加 frustration / anxiety，可能降低未来求助意愿 |
| unavailable support | 没人回应或没时间 | 增加 abandon / delay / offline switching |

实现边界：

- enabling / substituting / dismissive / unavailable 第一版主要影响 `outcome_model` 与 `event_appraisal`。
- `state_update.py` 仍通过 outcome、event-level uncontrollability、self-efficacy、support_mode 等既有接口更新 helplessness。
- 不要写成 `support_style == enabling -> helplessness -= x` 这种直接规则。

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
  "request_id": "req_0001",
  "sender_agent_id": "older_001",
  "target_agent_id": "family_001",
  "task_id": "task_0001",
  "event_id": "event_0001",
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

`support_request` 不应包含：

```text
outcome_type
success_probability_truth
helplessness_delta
Bayesian posterior
Huys-Dayan C_family
future-only labels
full memory dump
```

支持回应示例：

```json
{
  "type": "support_response",
  "response_id": "resp_0001",
  "request_id": "req_0001",
  "source": "family",
  "helper_agent_id": "family_001",
  "responded": true,
  "support_style": "enabling",
  "instruction_quality": 0.8,
  "emotional_tone": "patient",
  "autonomy_preservation": 0.9,
  "proxy_completion_level": "none",
  "requested_help_alignment": 0.9,
  "response_delay_bucket": "immediate",
  "response_text": "我一步一步教你，你先自己点这里。"
}
```

字段优先级：

| 字段 | 第一版是否必须 | 说明 |
|---|---:|---|
| `support_style` | 必须 | enabling / substituting / dismissive / unavailable |
| `instruction_quality` | 必须 | 进入 outcome model 的核心输入之一 |
| `emotional_tone` | 必须 | 用于 event appraisal / audit |
| `autonomy_preservation` | 必须 | 区分教学式帮助与代办式帮助 |
| `proxy_completion_level` | 必须 | 建议 `none / partial / full`，不要只用 bool |
| `requested_help_alignment` | 建议必须 | helper 是否真的回应了老人请求 |
| `response_delay_bucket` | 建议必须 | immediate / delayed / no_response |
| `response_text` | 可选但建议保留 | 只做 replay / audit，不直接进 outcome formula |

`support_response` 不应包含：

```text
outcome_type
success label
helplessness_after
helplessness_delta
posterior_update_weight
C_family
scope_spillover_total
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
LLM appraisal
-> semantic_v2 pi_ref
Bayesian posterior over P(outcome | task_family, action)
-> pi_bayes
confidence gate
-> pi_final
actual action
-> if seek_help_then_attempt: support_request / support_response
-> outcome
-> posterior update only for actual action
```

第一版不建议把 `support_style` 或 `support_context` 立刻放进 Dirichlet key，避免状态空间爆炸。可以先记录在 audit metadata / stream memory / lagged prediction analysis 中，后续再比较：

```text
v1: P(outcome | task_family, action)
v2: P(outcome | task_family, action, support_style)
```

第一版更稳的做法：

```text
support_response
-> response-derived support features
-> outcome_model / event_appraisal / memory / audit
-> actual outcome
-> Bayesian posterior still updates P(outcome | task_family, action)
```

只有当 `support_style` 在 v1 中表现出稳定覆盖、显著区分 outcome/self-efficacy/proxy reliance，并且有 lagged predictive value，才考虑进入 posterior key。

## support_response 接入边界

第一版推荐接入点：

```text
seek_help_then_attempt
-> support_request
-> support_response
-> bounded post-help support features
-> outcome_model
-> existing downstream updates
```

可以直接进入 `outcome_model` 的字段：

```text
responded
support_style
instruction_quality
autonomy_preservation
proxy_completion_level
requested_help_alignment
response_delay_bucket
```

更稳的工程做法是先把这些字段压缩成少数派生量：

```text
effective_support_quality
substitution_pressure
support_unavailability
```

可以影响 event / memory 的字段：

```text
emotional_tone
response_text
support_style
requested_help_alignment
proxy_completion_level
```

这些字段适合进入：

```text
event_appraisal
experience_memory
stream_episode
audit payload
stage summary
```

第一版不直接进入：

```text
helplessness_delta
Bayesian posterior key
Huys-Dayan C_family
scope_spillover formula
true outcome label
```

理由：

- support 是帮助过程，不是真实任务结果。
- helplessness 仍应由 outcome、uncontrollability、self-efficacy、support_mode 等既有机制间接更新。
- Bayesian posterior 第一版继续学习 `P(outcome | task_family, action)`，避免稀疏。
- controllability 第一版读取 actual posterior / audit，而不是让 helper response 直接改分数。

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
| `Block / BlockParams / BlockOutput` | `packages/agentsociety/agentsociety/agent/block.py` | 把行为能力封装成有上下文和结构化输出的 block | 第一版优先用于 `SupportResponseBlock` |
| `BlockDispatcher` | `packages/agentsociety/agentsociety/agent/dispatcher.py` | 根据 current_intention 路由到 block | 只适合可见行为 block，不适合控制心理更新链 |

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
proxy_completion_level
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
- `packages/agentsociety/agentsociety/agent/dispatcher.py` 的 `BlockDispatcher` 边界：只理解它怎么路由 block，第一版不要让它接管心理机制链。
- `packages/agentsociety/agentsociety/cityagent/blocks/social_block.py` 的 block 内部再调度子 block 模式：只作为后续结构参考，不作为第一版主实现。

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
  "request_id": "req_0001",
  "sender_agent_id": "older_001",
  "target_agent_id": "family_001",
  "task_id": "task_0001",
  "event_id": "event_0001",
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
    "response_id": "resp_0001",
    "request_id": "req_0001",
    "source": "family",
    "helper_agent_id": "family_001",
    "responded": true,
    "support_style": "enabling",
    "instruction_quality": 0.8,
    "emotional_tone": "patient",
    "autonomy_preservation": 0.9,
    "proxy_completion_level": "none",
    "requested_help_alignment": 0.9,
    "response_delay_bucket": "immediate",
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

## HelperAgent 继承哪个原生类

第一版 `FamilyHelperAgent` 最适合继承：

```python
CitizenAgentBase
```

而不是：

```python
SocietyAgent
DigitalHelplessnessAgent
```

原因：

- `CitizenAgentBase` 已经提供 `send_message_to_agent(...)`。
- `CitizenAgentBase` 支持重写 `do_chat(message)`。
- `CitizenAgentBase` 有 `memory.status` / `memory.stream` / `llm` / `environment`。
- `examples/polarization/message_agent.py` 里的 `AgreeAgent` / `DisagreeAgent` 就是这种消息型 agent 模式。
- `FamilyHelperAgent` 第一版只需要“收到求助、读取关系和历史、生成结构化回复、发回老人”，不需要完整城市生活规划。

不建议第一版继承 `SocietyAgent` 的原因：

```text
SocietyAgent 会带 needs_block / plan_block / step_execution / dispatcher /
cognition_block / mobility / social / economy / other blocks。
```

这些能力对家庭帮助者太重，容易把 support ecology 变成完整城市生活模拟，反而破坏当前机制实验的可控性。

推荐骨架：

```python
class FamilyHelperAgent(CitizenAgentBase):
    StatusAttributes = [
        MemoryAttribute(name="helper_persona", type=str, default_or_value="patient"),
        MemoryAttribute(name="relationship_profiles", type=dict, default_or_value={}),
        MemoryAttribute(name="support_histories", type=dict, default_or_value={}),
        MemoryAttribute(name="chat_histories", type=dict, default_or_value={}),
    ]

    async def forward(self):
        # 第一版可以 no-op，只被动等待 support_request
        await self.update_motion()

    async def do_chat(self, message):
        # 1. parse support_request
        # 2. read sender relationship/history
        # 3. call SupportResponseBlock or helper function
        # 4. update support_histories/chat_histories
        # 5. send structured support_response back
        ...
```

如果后续做 `CustomerServiceAgent`，可以再考虑 `InstitutionAgentBase`，因为客服/平台更像机构 agent；但 `FamilyHelperAgent` 是家庭成员，第一版用 `CitizenAgentBase` 最合适。

## 对我们最现实的接法

第一版不追求完整 multi-agent society，而是做一个严格受控的 support interaction loop：

```text
Level 1: task-triggered FamilyHelperAgent
-> 老人 action = seek_help_then_attempt
-> OlderAdultAgent 生成 support_request
-> FamilyHelperAgent / SupportResponseBlock 返回 support_response
-> outcome_model 读取 response-derived support features
-> audit 记录 request / response / derived features / outcome / updates

Level 2: workflow message intervention
-> 用 MESSAGE_INTERVENE 注入 peer success/failure story
-> 观察 appraisal / action / survey / posterior / controllability 是否变化
```

顺序上，先做 Level 1，再做 Level 2。因为 FamilyHelperAgent 能直接修复当前 support 过于 scalar 的问题；peer story 更适合作为后续 staged / transfer experiment 的外生干预。

## HelperAgent 逐步原生化计划

这里的“原生化”不是把所有心理机制交给 AgentSociety dispatcher，而是让 helper 更像 AgentSociety 其他实验里的消息型 / 社交互动型 agent。

### Phase H1: 消息型 agent

目标：先像 `polarization/message_agent.py` 那种 agent。

- [ ] `FamilyHelperAgent(CitizenAgentBase)`
- [ ] 重写 `do_chat(message)`
- [ ] 使用 `send_message_to_agent(sender_id, response_json)`
- [ ] 保持单轮 `support_request -> support_response`
- [ ] 不让 helper 决定真实 outcome

### Phase H2-lite: 关系和历史

目标：让 helper 不再像随机回复器，而像“这个具体的人”。

- [ ] 增加 `relationship_strength`
- [ ] 增加 `past_help_success_count`
- [ ] 增加 `past_help_failure_count`
- [ ] 增加 `last_interaction_day`
- [ ] 增加 `trust_or_expectation`
- [ ] 同一 helper 的 support style 受关系和历史影响
- [ ] 仍保持单轮结构化回复

### Phase H3: block 化回复

目标：把 helper 的可见支持行为封装成 AgentSociety-style block。

- [ ] 新增 `SupportResponseBlock`
- [ ] 输出结构化 `BlockOutput`
- [ ] 字段包括 `support_style`、`instruction_quality`、`autonomy_preservation`、`response_delay_bucket`
- [ ] 不让 block 直接决定 success / helplessness / posterior

### Phase H4: 有限多轮

目标：更像真实求助，但仍然可控。

```text
第 1 轮：求助
第 2 轮：澄清
第 3 轮：再试一次或转线下
```

- [ ] 支持 `ask_again`
- [ ] 支持 `partial_help`
- [ ] 支持 `unclear_instruction`
- [ ] 支持 `no_response -> retry / fallback`
- [ ] 不开放无限自由聊天

### Phase H5: helper persona

目标：让不同 helper 有稳定差异。

- [ ] 耐心型
- [ ] 急躁型
- [ ] 代办型
- [ ] 半懂不懂型
- [ ] persona 影响 support style / tone / autonomy preservation

### Phase H6: 接回 friction 主链

目标：helper 更像原生 agent，但 friction 主链仍保持可控。

- [ ] helper response 进入 `outcome_model`
- [ ] helper response 进入 `event_appraisal`
- [ ] helper response 进入 `experience_memory`
- [ ] helper response 进入 audit / replay
- [ ] 不直接写 helplessness delta
- [ ] 不直接写 Bayesian posterior
- [ ] 不直接写 Huys-Dayan `C_family`
- [ ] 不让 `BlockDispatcher` 控制 task appraisal / policy / outcome / state update

## Phase MB 实施建议

### Phase MB0: 文档和边界确认

- [ ] 明确论文定位：`controlled multi-agent support ecology for digital friction`。
- [ ] 明确 support ecology 不是养老院专属。
- [ ] 明确第一版只做 `FamilyHelperAgent`。
- [ ] 明确 support style: `enabling / substituting / dismissive / unavailable`。
- [ ] 明确 helper 不决定真实 outcome。
- [ ] 明确 helper 不直接改 helplessness、posterior、`C_family`、scope。
- [ ] 明确 `support_style` 第一版不进入 posterior key。

### Phase MB0.5: 文件级落点

这一阶段的原则是：先查现有接口，再做最小补丁；以复用现有状态、audit、outcome、memory 为主，不新增大抽象。

| 文件 | 最小改动 | 不做什么 |
|---|---|---|
| `examples/digital_friction_mvp/proto/support_protocol.py` | 新增 `SupportRequest` / `SupportResponse` schema，或先用轻量 dataclass / dict validator | 不引入复杂协议框架 |
| `examples/digital_friction_mvp/proto/agent.py` | 只在 `seek_help_then_attempt` 后触发 support request，并把 response 写入 audit / episode | 不重写整条心理机制 pipeline |
| `examples/digital_friction_mvp/proto/family_helper_agent.py` | 增加最小 `FamilyHelperAgent` 或 helper stub | 不做多轮社交网络 |
| `examples/digital_friction_mvp/proto/support_response_block.py` | 输出结构化 `support_response`，风格可 stub / seeded | 不让 block 决定真实 success |
| `examples/digital_friction_mvp/proto/outcome_model.py` | 增加可选 `support_response` / derived support features 输入 | 不让 raw text 直接进公式 |
| `examples/digital_friction_mvp/proto/experience_memory.py` | 记录 support style、instruction quality、proxy reliance signal | 不把 support style 直接写成 helplessness 规则 |
| `examples/digital_friction_mvp/config_runtime.py` | 视现有命名增加最少 feature flags | 不发明一堆配置项 |
| `examples/digital_friction_mvp/world_runner.py` | 只做必要 agent/helper 装配 | 不改 AgentSociety core |

建议配置开关先保持最少：

```text
SUPPORT_ECOLOGY_ENABLED
FAMILY_HELPER_ENABLED
```

如果需要可复现实验，再加一个 stub / seeded helper 模式，但必须先检查现有 `config_runtime.py` 的配置风格，不能凭空创造一套接口。

### Phase MB1: FamilyHelperAgent 最小消息闭环

目标：先证明 help-seeking 真的触发了 agent-to-agent support process。

- [ ] 新增 `support_protocol.py`：定义 `SupportRequest` / `SupportResponse` schema。
- [ ] 新增 `FamilyHelperAgent`。
- [ ] 新增 `SupportResponseBlock`。
- [ ] `OlderAdultAgent` 只在 `seek_help_then_attempt` 时生成 `support_request`。
- [ ] helper 返回结构化 `support_response`。
- [ ] audit payload 记录 request / response / helper source / support style。
- [ ] helper prompt 做 banned-key scrub，不暴露 outcome truth、posterior、helplessness delta、`C_family`。
- [ ] helper-off 时走旧 `support_quality_from_env()` 或现有 fallback，保证 baseline 可复现。
- [ ] helper assignment 第一版用 deterministic mapping，不做自由找人。
- [ ] 暂时不改 `state_update.py`。
- [ ] 暂时不改 Bayesian posterior key。
- [ ] 暂时不改 Huys-Dayan controllability score 公式。

### Phase MB2: support_response 接入 outcome_model 和 memory

目标：让 helper 不是装饰，而是以受控方式进入机制链。

- [ ] 在 `outcome_model.py` 中增加可选 `support_response` 输入。
- [ ] 新增小函数：`derive_effective_support_features(support_response, env)`。
- [ ] 派生 `effective_support_quality`、`substitution_pressure`、`support_unavailability`。
- [ ] 让这些派生量影响 `success_with_help` / `failure_even_with_help` / `abandon_midway` 概率。
- [ ] `experience_memory.py` 记录 support style、instruction quality、proxy completion signal。
- [ ] event appraisal 可以读取 support tone / response quality。
- [ ] `infer_support_mode()` 优先参考结构化 response，但保留 env-scalar fallback。
- [ ] `bayesian_controllability_lite.py` 第一版只把 support response 放进 audit metadata。
- [ ] `response_text` 只做 replay / audit，不直接进入公式。

### Phase MB3: enabling vs substituting support 实验

目标：先验证最核心的 support style 对比。

建议先做轻量 2x2：

| 因子 | 条件 |
|---|---|
| Friction | low vs high |
| Support style | enabling vs substituting |

第一版先不把 dismissive / unavailable 放进主实验，可以作为 stress test。

核心指标：

- help success rate
- abandon rate after help
- proxy reliance signal
- task self-efficacy
- perceived control
- expected help effectiveness
- helplessness delta
- next-day attempt / help / avoid
- Huys-Dayan controllability audit metrics

### Phase MB4: Peer story / message intervention

目标：先用轻量 intervention 测 peer effect，不急着做真实 peer agent。

- [ ] 用 `MESSAGE_INTERVENE` 注入 peer success / failure / neutral story。
- [ ] peer story 只影响 appraisal、social norm memory、help-seeking willingness。
- [ ] 不直接改 outcome。
- [ ] 不直接改 helplessness。
- [ ] 观察 peer story 对 perceived controllability / avoidance norm / transfer task 的影响。

### Phase MB5: CustomerServiceAgent / PlatformSupportAgent

目标：把平台支持从 family support 中分离出来。

- [ ] 新增 clear explanation / template reply / failed escalation / long wait。
- [ ] 主要影响 platform trust、expected help effectiveness、perceived platform controllability。
- [ ] 不直接替代 environment truth。
- [ ] 不直接决定 success。

### Phase MB6: AgentSociety-native block 增强

目标：只把可见行为与社会互动 block 化，不把心理更新交给 dispatcher。

第一版值得真实 block 化：

```text
SupportResponseBlock
```

第一版 logical block 即可：

```text
HelpSeekingBlock
ReflectionSurveyBlock
InformationSearchBlock
OfflineFallbackBlock
```

后续再做：

```text
PeerExperienceBlock
CustomerServiceResponseBlock
CommunityTrainingBlock
```

不要让 `BlockDispatcher` 自由控制：

```text
task appraisal
semantic_v2
Bayesian gated-lite2
Huys-Dayan controllability
outcome model
attribution
helplessness update
experience memory update
posterior update
audit payload writing
```

## 验证计划

### 必做测试

- [ ] `seek_help_then_attempt` 才触发 `support_request`。
- [ ] `attempt_self` 和 `avoid` 不触发 helper。
- [ ] `support_request` / `support_response` schema 可稳定序列化。
- [ ] helper prompt 不包含 future outcome、helplessness delta、posterior、`C_family`。
- [ ] helper response 不允许生成 outcome truth。
- [ ] 固定 seed 和 helper stub 时 replay deterministic。
- [ ] `SUPPORT_ECOLOGY_ENABLED=false` 时旧 baseline 不变。
- [ ] helper unavailable / malformed response 时不崩溃，并落回受控 fallback。
- [ ] 同一 seed 下 request_id / response_id / helper_id 可追踪。

### 必做分析

- [ ] `support_request coverage = valid_requests / seek_help_actions`。
- [ ] `support_response coverage = valid_responses / requests`。
- [ ] banned-key leakage rate = 0。
- [ ] enabling vs substituting 的 success / abandon / self-efficacy 差异。
- [ ] support style 对 next-day attempt / help / avoid 的 lagged prediction。
- [ ] support style 对 perceived control / expected help effectiveness / proxy reliance 的影响。
- [ ] support style 是否给 Huys-Dayan controllability audit 增加解释力。

### 人工验证

最小做法：

- [ ] 抽取 30-50 条 `support_request -> support_response` vignette。
- [ ] 请人工或专家评估 support style label 是否正确。
- [ ] 评估回应是否 realistic / age-appropriate。
- [ ] 评估是否 preserving autonomy。
- [ ] 评估是否存在过度代办或责备语气。

## 后续如何更像现实

第一版先保证结构化、可控、可审计。后续如果想更像现实，不是放开自由聊天，而是在结构化核心上增加现实细节。

### 1. 加关系和历史

同一个 helper 不要每次都像随机路人，而要逐渐形成固定关系。

- [ ] 记录 `relationship_strength`
- [ ] 记录 `past_help_success_count`
- [ ] 记录 `past_help_failure_count`
- [ ] 记录 `last_interaction_day`
- [ ] 记录 `trust_or_expectation` 的轻量记忆

这样老人会越来越像“这个人以前帮过我 / 这个人总是嫌烦”，而不是每次都重新抽一张卡。

### 2. 加不确定性和延迟

现实里不是每次都能立刻得到帮助。

- [ ] 支持 `immediate / delayed / no_response`
- [ ] 支持 `partial_help`
- [ ] 支持 `unclear_instruction`
- [ ] 支持 `ask_again / retry / fallback`

这样 support 才会像真实日常，而不是每次都整整齐齐回答完美答案。

### 3. 加有限多轮

不是自由聊天，而是有限轮次。

```text
第 1 轮：求助
第 2 轮：澄清
第 3 轮：再试一次或转线下
```

这样会更像现实中的“问一下、再确认、再操作”，但仍然可以审计。

### 4. 用文本生成外壳

结构化字段保留在底层，`response_text` 作为外壳由字段生成。

- [ ] `support_style` 决定语气模板
- [ ] `instruction_quality` 决定解释是否清楚
- [ ] `autonomy_preservation` 决定是教还是代办
- [ ] `relationship_strength` 决定语气亲疏

这会比纯模板化回复更像真人，但不会破坏机制控制。

### 5. 让同一个 helper 有稳定个性

后续可以让 helper 带简单 persona：

- [ ] 耐心型
- [ ] 急躁型
- [ ] 代办型
- [ ] 半懂不懂型

这样会比每次都随机风格更真实，也更适合论文里讲“支持生态”。

## 论文表述

最稳中文定位：

```text
我们构建了一种任务触发的社会支持互动机制，并把它接入可审计的认知-行为更新链条。
```

最稳英文定位：

```text
We introduce task-triggered social support interactions within an auditable
cognitive-behavioral update pipeline for older-adult digital friction.
```

不要写：

```text
We fully reproduce AgentSociety-native social simulation.
We let helper agents freely determine task outcomes.
We model full real-world support ecology.
```

可以写：

```text
The helper agent does not determine task success. Instead, it returns a
structured support response that is consumed by a controlled outcome model and
recorded in audit/replay traces.
```

## 风险和边界

- 不要让 helper LLM 决定真实 outcome。
- 不要把多 agent 做成自由闲聊，成本高且难解释。
- 不要一开始就加入太多角色。
- 不要让 support_style 同时直接决定 action、outcome、helplessness，避免又形成手写自我强化循环。
- 不要把 `support_style` 第一版放进 Bayesian posterior key。
- 不要让 `response_text` 直接进 outcome formula。
- 不要让 `BlockDispatcher` 接管心理机制链。
- 不要把 offline fallback 直接等同于失败或 helplessness。
- 不要把养老院写成唯一场景。养老院 / 社区可以是采样入口，不是外推边界。

## 最近一周建议

最近一周如果要动 multi-agent，只做准备工作和最小闭环，不做大规模扩展。

更合理顺序：

1. 保存当前 main baseline。
2. 新增 `support_protocol.py` 文档化 schema。
3. 设计 `FamilyHelperAgent` 和 `SupportResponseBlock`，但先可用 stub response 跑通。
4. 在 audit payload 中记录 request / response。
5. 给 `outcome_model` 预留可选 `support_response` 输入。
6. 补 no-leakage / coverage / helper-off regression tests。
7. 暂不改 `state_update.py`、Bayesian key、controllability formula。

## 待确认问题

真正动代码前，至少确认下面几件事：

- 当前本地跑的是 GitHub `main` 分支，还是另一个实验分支。
- `config_runtime.py` / `world_runner.py` 中 agent class 的实际装配入口在哪里。
- 第一版 helper loop 是否严格单轮：求助一次、回复一次、直接进入 outcome model。
- 每个 older adult 是否已有固定 family helper 映射；如果没有，第一版需要 deterministic assignment。
- `proxy_reliance` 是要先做 audit 指标，还是已经准备成为显式心理状态变量。
- `response_text` 只用于 replay / audit，还是还要进入人工 vignette validation。
