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

## AgentSociety 可参考例子

本仓库中比较值得参考的原生例子：

- `examples/polarization/message_agent.py`
  - 定义 `AgreeAgent` / `DisagreeAgent`
  - 使用 `send_message_to_agent(friend, message)`
  - 使用 `do_chat(message)` 处理收到的信息并回复
- `examples/polarization/echo_chamber.py`
  - 多类 agent 共存
  - 运行后保存 attitude 和 chat histories
- `examples/rumor_spreader/utils.py`
  - 初始化 social network
  - 设置 `friends`、`public_friends`、`relationships`、`relation_types`、`chat_histories`、`interactions`
- `examples/inflammatory_message/edge_intercept.py`
  - 对 chat histories 做 intervention
  - 适合参考消息干预流程

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

