# 多 Agent & Block 化后续 TODO

## 0. 总体定位

本文件记录后续把当前 `digital_friction_mvp` 从“固定 workflow 的单类 older adult agent 实验”，升级为更像 AgentSociety 风格的 **多 agent + blockized components** 的路线。

核心判断：

```text
保留固定实验 workflow
+ 把可见行为和社会互动 block 化
+ 引入 task-triggered helper / peer / service agents
```

不要把整个数字无助主链交给 LLM dispatcher 自由调度。当前论文需要的是可控、可审计、可复现的机制模拟，而不是开放式自由社会模拟。

## 1. 论文定位要讲清楚

后续论文中更稳的说法：

```text
We build an AgentSociety-based controlled multi-agent simulation for older-adult digital friction, combining task-triggered social support interactions with an auditable cognitive-behavioral update pipeline.
```

不要说：

```text
We fully reproduce AgentSociety-style human society simulation.
We let agents freely simulate human behavior.
We use an LLM dispatcher to autonomously control all cognitive mechanisms.
```

更准确的中文定位：

```text
我们基于 AgentSociety 的 agent / message / block 思路，构建一个受控的老年数字摩擦多 agent 实验环境。
```

## 2. 必须保留固定顺序的机制链

以下模块不要交给 LLM dispatcher 自由决定是否执行、何时执行、以什么顺序执行：

```text
task appraisal
semantic_v2 reference policy
Bayesian gated-lite policy
Huys-Dayan-lite controllability audit / modulation
outcome model
event-level attribution
helplessness update
self-efficacy update
scope spillover
Bayesian posterior update
audit payload writing
```

原因：

```text
这些模块决定实验因果边界。
如果顺序被 LLM dispatcher 改动，会破坏 no-leakage、ablation 和可复现性。
```

推荐主链继续保持：

```text
digital task event
-> appraisal
-> Phase4 policy / Phase5 controllability
-> action selection
-> optional support interaction
-> outcome
-> attribution / helplessness / self-efficacy
-> memory / posterior / audit update
```

## 3. 适合 block 化的部分

优先 block 化“可见行为”和“社会互动”，而不是心理状态更新公式。

### 3.1 OlderAdultAgent 行为 block

第一批可做成 AgentSociety-style block：

```text
DigitalTaskBlock
HelpSeekingBlock
OfflineFallbackBlock
InformationSearchBlock
ReflectionSurveyBlock
```

职责划分：

| Block | 要做什么 | 不做什么 |
|---|---|---|
| `DigitalTaskBlock` | 承载一次数字任务事件，组织 appraisal / policy / action / outcome 的调用 | 不自由改写 helplessness 更新 |
| `HelpSeekingBlock` | 当 action 是 seek_help 时，生成 structured support_request 并发给 helper | 不决定任务真实成功 |
| `OfflineFallbackBlock` | 表示线下替代、推迟办理、找窗口等行为 | 不把 offline 直接等同于失败或无助 |
| `InformationSearchBlock` | 表示搜索教程、看平台提示、查 FAQ | 不直接篡改 outcome truth |
| `ReflectionSurveyBlock` | 记录任务后的自我效能、挫败感、信任、未来意愿 | 不替代 state update 主链 |

### 3.2 HelperAgent block

最优先做：

```text
FamilyHelperAgent
  -> SupportResponseBlock
```

`SupportResponseBlock` 输出结构化支持回应：

```json
{
  "support_style": "enabling",
  "instruction_quality": 0.8,
  "emotional_tone": "patient",
  "autonomy_preservation": 0.9,
  "proxy_completion": false,
  "response_text": "我一步一步教你，你先自己操作。"
}
```

HelperAgent 可以决定：

```text
是否回应
回应是否耐心
是教学式帮助还是代办式帮助
解释质量
情绪语气
是否保留老人自主性
```

HelperAgent 不可以决定：

```text
任务是否真实成功
老人 helplessness 增减多少
Bayesian posterior 怎么更新
Huys-Dayan C_family 怎么更新
```

### 3.3 PeerOlderAdultAgent block

第二优先级：

```text
PeerExperienceBlock
```

输出：

```json
{
  "story_valence": "success",
  "task_family": "appointment_booking",
  "message_text": "我上次也卡住了，后来有人教我，我自己挂上号了。"
}
```

作用：

```text
影响社会规范、风险感知、求助意愿和 scope spillover。
```

但第一版不要让 peer 直接改 outcome。peer 只提供经验叙事。

### 3.4 CustomerServiceAgent block

第三优先级：

```text
CustomerServiceResponseBlock
```

回应类型：

```text
clear_explanation
template_reply
failed_escalation
long_wait
```

它主要影响：

```text
platform trust
expected_help_effectiveness
perceived platform controllability
future help-seeking
```

### 3.5 CommunityVolunteerAgent block

后续 recovery experiment 再做：

```text
CommunityTrainingBlock
```

适合放在 staged experiment 的 recovery phase：

```text
acquisition: 高摩擦 / 低支持
recovery: 引入 enabling support / community volunteer
transfer: 测新 task family
```

## 4. 多 Agent 第一版最小闭环

不要一上来做完整社会网络。第一版只做任务触发型互动。

最小结构：

```text
OlderAdultAgent x N
FamilyHelperAgent x K
PeerOlderAdultAgent x K
```

最小流程：

```text
OlderAdultAgent 遇到数字任务
-> action = seek_help
-> HelpSeekingBlock 生成 support_request
-> send_message_to_agent(helper_id, support_request)
-> FamilyHelperAgent.do_chat(message)
-> SupportResponseBlock 生成 support_response
-> OlderAdultAgent 接收 support_response
-> outcome_model 读取 support_response 作为受控输入
-> state update / posterior update / audit
```

第一版只需要一个 helper 回应，不需要多轮对话。

## 5. 结构化消息格式

### 5.1 Support Request

```json
{
  "type": "support_request",
  "sender_agent_id": "older_001",
  "receiver_agent_id": "family_001",
  "task_family": "payment_confirmation",
  "friction_type": "verification_failure",
  "requested_help": "teach_me",
  "current_appraisal": {
    "difficulty": 0.72,
    "perceived_control": 0.38,
    "risk": 0.64
  },
  "day": 3,
  "event_id": "..."
}
```

### 5.2 Support Response

```json
{
  "type": "support_response",
  "source": "family",
  "support_style": "enabling",
  "instruction_quality": 0.8,
  "emotional_tone": "patient",
  "autonomy_preservation": 0.9,
  "proxy_completion": false,
  "response_text": "我一步一步教你，你先点这里。"
}
```

### 5.3 Peer Experience

```json
{
  "type": "peer_experience",
  "source": "peer",
  "story_valence": "failure",
  "task_family": "medical_appointment",
  "message_text": "这个太麻烦了，我后来都去线下窗口。"
}
```

## 6. AgentSociety 原生能力要优先借哪些

后续实现优先借这些原生思想或接口：

```text
Block / BlockParams / BlockOutput
send_message_to_agent
do_chat(message)
relationships / friends
chat_histories / interactions
SAVE_CONTEXT
MESSAGE_INTERVENE
ENVIRONMENT_INTERVENE
SURVEY
```

推荐学习文件：

```text
packages/agentsociety/agentsociety/agent/block.py
packages/agentsociety/agentsociety/agent/dispatcher.py
packages/agentsociety/agentsociety/cityagent/societyagent.py
packages/agentsociety/agentsociety/cityagent/blocks/social_block.py
examples/polarization/message_agent.py
examples/polarization/echo_chamber.py
examples/rumor_spreader/utils.py
examples/prospect_theory/step_three.py
examples/hurricane_impact/hurricane.py
examples/UBI/main.py
```

## 7. 不建议第一版做的事情

暂时不要做：

```text
不做 city-scale 大规模社会模拟
不做全天候自由聊天
不让 LLM dispatcher 接管全部 action pipeline
不让 HelperAgent 决定 outcome truth
不把 support_style 同时硬塞进 action、outcome、helplessness 多个地方
不把 Bayesian / Huys-Dayan / helplessness 更新改成 LLM 自由生成
不一开始就把 support_context 加进 Dirichlet key
```

尤其不要一开始做：

```text
P(outcome | task_family, action, helper_id, support_style, relationship_strength)
```

这会导致状态空间太快爆炸。第一版先保留：

```text
P(outcome | task_family, action)
```

同时把 support 信息写入 audit metadata，后续再分析 support style 是否应该进入 posterior key。

## 8. 推荐实施阶段

### Phase MB0: 文档和边界确认

要做：

```text
确认论文表述：AgentSociety-based controlled multi-agent simulation
确认 fixed workflow + blockized components
确认哪些模块不能 dispatcher-controlled
确认 HelperAgent 不决定 outcome truth
```

产物：

```text
多agent&blocktodo.md
多agenttodo.md 更新或互相引用
blocktodo.md 更新或互相引用
```

### Phase MB1: HelperAgent 最小消息闭环

要做：

```text
新增 FamilyHelperAgent
新增 SupportResponseBlock
OlderAdultAgent seek_help 时发送 support_request
FamilyHelperAgent 返回 support_response
audit 记录 support_request / support_response
outcome_model 读取 support_response 的质量字段
```

第一版支持类型：

```text
enabling
substituting
dismissive
unavailable
```

验收：

```text
seek_help event 中 support payload coverage = 1.0
helper response 不直接写 outcome
no post-outcome leakage
same seed 下关闭 helper mode 时 Phase4/Phase5 行为不变
```

### Phase MB2: OlderAdult 可见行为 block 化

要做：

```text
把 digital task event 外壳整理为 DigitalTaskBlock 或 DigitalFrictionBlock
把求助流程整理为 HelpSeekingBlock
把线下替代整理为 OfflineFallbackBlock
```

注意：

```text
这一步可以先做 logical block，不急着完全接入 AgentSociety BlockDispatcher。
```

验收：

```text
block 输出结构化
原有 Phase4/Phase5 audit 不丢失
off/shadow/gated_modulate 行为保持可复现
```

### Phase MB3: Peer experience / message intervention

要做：

```text
实现 PeerOlderAdultAgent 或先用 MESSAGE_INTERVENE 注入 peer story
区分 success story / failure story / neutral story
记录 peer_norm_exposure
观察对 appraisal、avoidance、self-efficacy、scope spillover 的影响
```

推荐先做 message intervention，再做真实 peer agent。

验收：

```text
peer story 不直接改 outcome
peer story 对后续 action / survey / attribution 有可分析字段
```

### Phase MB4: Customer service / platform support

要做：

```text
新增 CustomerServiceAgent
新增 CustomerServiceResponseBlock
区分 clear_explanation / template_reply / failed_escalation / long_wait
把 platform feedback clarity 从纯 world scalar 部分迁移为 service response
```

验收：

```text
客服响应可以解释 why help helped or failed
仍由 outcome_model 决定真实任务结果
```

### Phase MB5: Community volunteer recovery experiment

要做：

```text
新增 CommunityVolunteerAgent
新增 CommunityTrainingBlock
设计 staged experiment:
  acquisition -> uncontrollable high friction
  recovery -> enabling volunteer support
  transfer -> new task family
```

验收：

```text
recovery phase self-efficacy 上升
helplessness 增长放缓或下降
C_family / C_global trace 有恢复趋势
transfer task 中 avoid / help / attempt pattern 有可解释变化
```

### Phase MB6: AgentSociety 原生化增强

要做：

```text
把 helper / peer / service 的关系写入 relationships / friends
保存 chat_histories / interactions
用 SAVE_CONTEXT 导出关键状态
必要时接 MESSAGE_INTERVENE / ENVIRONMENT_INTERVENE / SURVEY
```

谨慎尝试：

```text
只让 dispatcher 在可见行为 blocks 之间选择
不要让 dispatcher 控制心理更新和 posterior update
```

## 9. 实验优先级

为了留出写论文时间，建议优先级如下：

```text
P0: Phase5A/5B controllability 稳定
P1: FamilyHelperAgent + SupportResponseBlock
P2: support_response audit + no-leakage tests
P3: staged experiment with enabling vs substituting support
P4: peer story intervention
P5: customer service block
P6: full AgentSociety-native dispatcher integration
```

如果时间紧，做到 P3 就可以写成论文增强点：

```text
The simulation includes task-triggered support interactions with helper agents, while preserving a fixed auditable cognitive update pipeline.
```

## 10. 必须记录的 audit 字段

每次 support event 至少记录：

```text
support_request_present
support_response_present
helper_agent_id
helper_type
relationship_type
relationship_strength
support_style
instruction_quality
emotional_tone
autonomy_preservation
proxy_completion
response_latency
support_unavailable
outcome_used_support_response
helper_decided_outcome=false
```

每次 block 执行至少记录：

```text
block_name
block_mode
input_context_hash or event_id
output_schema_version
success
fallback_reason
consumed_time
```

## 11. 测试计划

必须新增或扩展测试：

```text
helper response schema validation
support_request / support_response round trip
helper does not write outcome
outcome_model can consume support_response
no support mode equals old baseline
same seed reproducibility when helper disabled
block output does not mutate input state unexpectedly
message history saved when enabled
SAVE_CONTEXT includes support fields
```

回归重点：

```text
Phase4 semantic_v2 gated-lite 不被破坏
Phase5 Huys-Dayan-lite off/shadow/gated_modulate 行为边界不被破坏
helplessness / attribution / scope_spillover 更新顺序不变
```

## 12. 论文中可以展示的图

推荐画一张架构图：

```text
OlderAdultAgent
  DigitalTaskBlock
  HelpSeekingBlock
  OfflineFallbackBlock
  ReflectionSurveyBlock

FamilyHelperAgent
  SupportResponseBlock

PeerOlderAdultAgent
  PeerExperienceBlock

Fixed Auditable Mechanism Pipeline
  Bayesian gated-lite
  Huys-Dayan-lite
  outcome model
  helplessness / self-efficacy / attribution update
```

图里要强调：

```text
blocks handle visible behavior and communication
fixed pipeline handles causal psychological and Bayesian updates
```

## 13. 最小可发版本

如果只做一个最小但有论文价值的版本，建议是：

```text
OlderAdultAgent x 10
FamilyHelperAgent x 3-5
SupportResponseBlock
structured support_request / support_response
enabling vs substituting vs dismissive vs unavailable support
Phase5 Huys-Dayan-lite audit/modulation
staged acquisition / recovery / transfer experiment
```

这个版本已经能支撑一个更强的问题：

```text
不同支持方式如何影响老年 agent 在数字摩擦中的可控性感知、自我效能、求助、回避和数字无助恢复？
```

## 14. 一句话结论

后续不要把项目改成完全自由的 AgentSociety city simulation。更好的路线是：

```text
AgentSociety-style multi-agent support interaction
+ blockized visible behaviors
+ fixed auditable helplessness / Bayesian / controllability mechanism pipeline
```

这样既能体现 AgentSociety 的多 agent 和 block 优势，又不会牺牲当前实验最重要的可控性和论文可解释性。
