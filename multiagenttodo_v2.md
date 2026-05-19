# multiagenttodo_v2.md

## 文档定位

本文件定义 `digital_friction_mvp` 的**后续 support ecology 扩展**边界。

目标不是做一个“更热闹的 agent 社会”，而是把当前过于 scalar 的 support，升级成：

> task-triggered, single-turn, structured, auditable support interaction

也就是：

`OlderAdultAgent -> support_request -> FamilyHelperAgent -> support_response -> outcome_model -> audit / memory / existing downstream updates`

本文件同时明确：

- 什么现在不要做
- 什么以后可以做
- support layer 与 `mobile-intention entry layer` 的关系
- 哪些接口必须复用现有 post-entry 语义

---

## 设计准则

- 以瞎猜接口为耻，以认真查询为荣。
- 以模糊执行为耻，以寻求确认为荣。
- 以臆想业务为耻，以人类确认为荣。
- 以创造接口为耻，以复用现有为荣。
- 以跳过验证为耻，以主动测试为荣。
- 以破坏架构为耻，以遵循规范为荣。
- 以假装理解为耻，以诚实无知为荣。
- 以盲目修改为耻，以谨慎重构为荣。
- 不随意写兜底代码。
- 不过度设计。
- 尽可能少新加抽象。

---

## 已确认的仓库现实（support 设计必须服从这些事实）

### 1) 当前 support 仍主要是 world scalar

`examples/digital_friction_mvp/proto/outcome_model.py` 当前通过：

- `assist_level`
- `human_support_level`
- `accessibility_level`

压成 `support_quality_from_env(env)`，再进入 outcome 计算。

这说明：

- 当前 support 机制是有效 baseline
- 但如果论文要讲 support ecology，它还太参数化

### 2) 当前 help 的语义已经存在，但仍是 post-entry action

`examples/digital_friction_mvp/proto/models.py` 当前：

- `AttemptStrategy.support_requested` 已存在
- `RecentEpisode` 已有 `help_used / help_source`

这意味着：

- help 应继续是**进入具体任务之后**的策略语义
- 不应该在 mobile entry 层伪造 help

### 3) 当前 post-entry 主链不能被 helper 夺权

现有主链仍然是：

`DigitalTask -> task_appraisal -> strategy_deliberation -> Phase4 -> Phase5C -> choose_attempt_strategy -> outcome_model -> helplessness / attribution / memory`

support 的最小版本只能插在：

`strategy == seek_help_then_attempt`

之后，进入 `outcome_model` 之前。

### 4) 当前 `多agenttodo.md` 已给出收敛原则

仓库现有 `多agenttodo.md` 已明确：

- 第一版只做最小闭环：`OlderAdultAgent -> FamilyHelperAgent -> support_response -> outcome_model -> audit / memory`
- 不做自由闲聊式 multi-agent
- 不做多轮 helper negotiation
- outcome truth 仍由 outcome model 决定
- `support_response` 第一版只直接进入 outcome model、event appraisal、experience memory 和 audit；不要直接改 helplessness delta、Bayesian posterior key、`C_family` 或 scope spillover
- 最近一周建议是：只做准备工作和最小闭环，不做大规模扩展；新增 `support_protocol.py`、设计 `FamilyHelperAgent` 和 `SupportResponseBlock`、在 audit 里记录 request/response、给 `outcome_model` 预留可选 `support_response` 输入、补 regression tests，暂不改 `state_update.py` / Bayesian key / controllability formula

本文件沿用这一收敛方向，不再发散。

---

## 总体裁决

### 现在不要把 support ecology 和 mobile-intention entry 一起并入主实验

当前主线应该是：

1. 先完成 `mobile-intention entry layer`
2. 保持 post-entry 心理主链不变
3. support ecology 只做接口预留，最多 appendix prototype

### 为什么

因为现在同时大做：

- entry realism 改造
- support interaction 改造
- Phase4 / Phase5C 继续作为主机制

会让论文主线过散，因果归因变难。

### 当前最稳路线

- **主论文 / 主 patch**：只做 `mobile_intention_rule`
- **support**：先写收紧版 todo + schema 预留 + audit 预留
- **后续 / appendix**：最小 `FamilyHelperAgent`

---

## support 与 mobile-intention entry 的正确关系

必须固定为：

```text
mobile_intention entry
  -> 只决定是否进入手机活动 / 是否生成 DigitalTask

DigitalTask entered
  -> task_appraisal
  -> strategy_deliberation
  -> Phase4 / Phase5C
  -> choose_attempt_strategy

只有当 strategy == seek_help_then_attempt
  -> support_request
  -> FamilyHelperAgent / SupportResponseBlock
  -> support_response
  -> outcome_model
  -> event_appraisal / memory / audit
  -> helplessness update（沿用现有机制）
```

### 因此严格禁止

- `communicate_or_seek_help` 直接触发 helper
- support 进入 entry layer
- helper 直接决定 strategy
- helper 直接决定 outcome
- helper 直接改 helplessness / posterior / controllability

---

## 非目标（必须明确写死）

第一版不做：

- free-form social chat
- multi-turn helper negotiation
- Family + Peer + Customer + Volunteer all at once
- helper decides task success
- support_style enters Dirichlet / Bayesian key
- BlockDispatcher controls psychology / posterior / state update
- helper writes helplessness delta directly
- helper writes self-efficacy delta directly
- helper writes `C_family / C_global` directly
- helper writes Phase4 / Phase5C policy weights directly
- 开放式 helper-older adult 多轮对话
- 复杂社交网络 / diffusion / availability market

---

## 第一版最小 support MVP（仅供后续阶段）

### 角色

只要两个：

1. `OlderAdultAgent`（现有）
2. `FamilyHelperAgent`（新增）

### 为什么只选 FamilyHelperAgent

- 最贴近日常泛老年数字服务场景
- 能直接把 support 从 scalar 升为 interaction
- 工程改动最小
- 最容易做 coverage / replay / ablation

### 不要第一版一起上

- `PeerOlderAdultAgent`
- `CustomerServiceAgent`
- `VolunteerAgent`
- `ServiceCounterAgent`

这些都放后续。

---

## 触发边界

### 只有在以下条件同时满足时才触发 support

1. 已经进入具体 `DigitalTask`
2. 已经完成 post-entry appraisal / deliberation / Phase4 / Phase5C
3. `choose_attempt_strategy(...)` 结果是 `seek_help_then_attempt`

### 明确不触发的情况

- `attempt_self`
- `avoid`
- `abandon_midway` 的前置阶段
- `communicate_or_seek_help` mobile intention
- `browse_entertainment`
- `no_mobile_action`
- `unknown_or_unmapped`

---

## helper 只能输出什么

helper 只能输出：

> structured support_response

而不是心理更新结果。

### 推荐 `SupportRequest` schema

```json
{
  "type": "support_request",
  "request_id": "req_0001",
  "sender_agent_id": "older_001",
  "target_agent_id": "family_001",
  "task_id": "task_0001",
  "event_id": "event_0001",
  "task_family": "payment_risk_confirmation",
  "friction_type": "verification",
  "need_type": "daily_transaction",
  "requested_help": "teach_me",
  "concise_problem_summary": "The user is stuck at a payment risk confirmation step and wants guided help.",
  "current_appraisal": {
    "difficulty": 0.72,
    "perceived_control": 0.38,
    "risk": 0.64
  },
  "day": 3,
  "tick_seconds": 50400,
  "support_source": "family"
}
```

### `SupportRequest` 禁止包含

- future outcome
- helplessness delta
- self-efficacy delta
- posterior update
- `C_family / C_global`
- Phase4 / Phase5C policy
- “this task will succeed” 之类未来事实

### 推荐 `SupportResponse` schema

```json
{
  "type": "support_response",
  "response_id": "resp_0001",
  "request_id": "req_0001",
  "helper_agent_id": "family_001",
  "responded": true,
  "helper_role": "family",
  "support_style": "enabling_support",
  "instruction_quality": 0.82,
  "autonomy_preservation": 0.76,
  "proxy_completion_level": 0.10,
  "requested_help_alignment": 0.88,
  "response_delay_bucket": "immediate",
  "helper_available": true,
  "fallback_used": false,
  "message_summary": "Helper explains the step patiently and encourages the older adult to try it themselves."
}
```

### `SupportResponse` 禁止输出

- `success=true/false` 作为最终 outcome truth
- helplessness delta
- self-efficacy delta
- posterior update delta
- `C_family` delta
- controllability posterior
- Phase4 / Phase5C weights

---

## support_response 的接入边界

### 可以进入 outcome_model 的字段

第一版只允许这些字段进入 bounded post-help support features：

- `responded`
- `support_style`
- `instruction_quality`
- `autonomy_preservation`
- `proxy_completion_level`
- `requested_help_alignment`
- `response_delay_bucket`
- `helper_available`

### 更稳的工程做法

不要把整条 response 原样塞进 outcome formula。

应该先压缩成少量派生量，例如：

- `support_response_received: bool`
- `support_quality_adjustment: float`
- `autonomy_loss_risk: float`
- `proxy_dependency_signal: float`
- `response_timeliness: float`

然后再交给 `outcome_model`。

### outcome truth 仍由 outcome_model 决定

必须保持：

- helper 只提供 support process 特征
- `outcome_model` 仍是 success / failure / abandon / help-use 的 truth generator

---

## helper 绝不能直接改什么

第一版严禁 helper 直接改：

- helplessness delta
- self-efficacy delta
- `C_family / C_global`
- Bayesian posterior key / count
- Phase4 / Phase5C policy weights
- scope spillover
- attribution label

### 正确做法

helper 只影响：

- outcome_model 的 bounded support features
- event appraisal 的上下文输入
- memory / audit 的支持过程记录

真正心理更新仍然走现有：

- `outcome_model`
- `event appraisal`
- `state_update.py`
- existing Bayesian / controllability updates

---

## 与 `communicate_or_seek_help` 的关系

### 是否保留这个 mobile intention

保留。

### 它的定位

- 只是 mobile communication / support-related context intention
- 不是 `seek_help_then_attempt`
- 不是 help event

### 它绝不能做什么

- 不能触发 helper
- 不能生成 `support_request`
- 不能更新 help memory
- 不能算 `is_help_action = true`

### 为什么还要保留

- TalkingData 中 communication/social category 很可能占重要比例
- 如果不保留，会把真实的通信类 exposure 全部挤进 unknown 或错误 task

---

## TalkingData 与 support ecology 的关系

### TalkingData 可以支持什么

只能支持：

- communication/social app exposure
- hour/profile-level communication intention prior
- 某类用户更常出现 communication activity 的 pattern

### TalkingData 不能支持什么

不能支持：

- 真实 help-seeking event
- family support availability truth
- helper response quality
- support style label
- peer / family / customer service ground truth
- support effectiveness label

### 因此禁止

- 把 communication app usage 当成真实求助
- 把 social category 当成 family helper availability ground truth
- 用 TalkingData 为 helper prompt 提供“你现在有家人可帮你”之类事实

---

## 文件级修改计划（后续 support MVP 用）

## 必须改

### `examples/digital_friction_mvp/proto/support_protocol.py`（新增）

定义：

- `SupportRequest`
- `SupportResponse`
- 序列化 / 反序列化
- schema version

### `examples/digital_friction_mvp/proto/family_helper_agent.py`（新增）

最小 `FamilyHelperAgent`：

- 第一版可以 stub
- 第二版再接 LLM block

### `examples/digital_friction_mvp/proto/support_response_block.py`（新增）

- 负责从 request 生成 structured response
- 单轮
- 禁止写未来 outcome

### `examples/digital_friction_mvp/proto/agent.py`

仅做一件事：

- 当 `strategy == seek_help_then_attempt` 时，生成 `support_request`
- 调 helper
- 拿回 `support_response`
- 再把 bounded features 交给 `outcome_model`

### `examples/digital_friction_mvp/proto/outcome_model.py`

只允许新增：

- 可选 `support_response` / derived features 输入
- helper-off 时保持当前 `support_quality_from_env()` fallback

### `examples/digital_friction_mvp/config_runtime.py`

新增少量 flags：

- `PROTO_SUPPORT_MODE=off|family_helper_stub|family_helper_llm`
- `PROTO_SUPPORT_AUDIT_ENABLED`
- `PROTO_SUPPORT_FAIL_CLOSED`

### `examples/digital_friction_mvp/main.py`

- helper 注册 / 初始化
- feature flag 接线

### analysis / tests

- request / response coverage
- helper-off regression
- banned-key leakage
- replay determinism

## 可以改

### `examples/digital_friction_mvp/proto/models.py`

如果你需要轻 dataclass，可仅新增：

- `SupportRequest`
- `SupportResponse`

但也可以全部放在 `support_protocol.py`。

## 不要改

- `proto/task_assignment.py`
- `proto/runtime.py` 的 entry 语义
- `proto/bayesian_policy_lite.py`
- `proto/bayesian_controllability_lite.py`
- `proto/state_update.py`
- `proto/attribution_inference.py`
- `scope_spillover` 公式
- DB schema
- `RecentEpisode` 语义
- attempt sampler

---

## helper-off fallback

这是 support MVP 能否安全落地的关键。

### 必须保证

当：

- `PROTO_SUPPORT_MODE=off`
- helper 调用失败
- response parse 失败
- response schema 不合法

系统要么：

- 严格 fail-fast（实验模式）
- 要么回到现有 `support_quality_from_env()`（baseline-compatible mode）

### 禁止

- silently random fallback
- helper parse fail 后自动编一个 support_response
- helper 失效后改变主链含义

---

## 测试计划

## 必做测试

- 只有 `seek_help_then_attempt` 才触发 `support_request`
- `attempt_self` 和 `avoid` 不触发 helper
- `support_request` / `support_response` schema 可稳定序列化
- helper prompt / stub 输入不包含 future outcome / helplessness delta / posterior / `C_family`
- helper-off 时结果回到当前 baseline 路径
- response parse fail 的行为符合配置（fail-fast 或 fallback）
- banned-key leakage rate = 0
- replay deterministic
- audit 里 request / response / derived features 完整

## 人工验证

最小人工校验：

- 抽 30~50 条 `support_request -> support_response`
- 评估 support style label 是否合理
- 评估是否 realistic / age-appropriate
- 评估是否 preserving autonomy
- 评估是否存在过度代办 / 责备语气

---

## 实验计划建议

### 当前主论文

不把 support MVP 放进主实验。

主实验只做：

- `fixed_assignment`
- `mobile_intention_rule_calibrated`
- `mobile_intention_llm_shadow`

### Appendix / 下一阶段

可以做：

- `mobile_intention_rule + helper_off`
- `mobile_intention_rule + family_helper_stub`
- `mobile_intention_rule + family_helper_llm`

### support 相关关键对照

- helper-off vs helper-on
- stub vs llm-response
- enabling vs dismissive vs unavailable response style（仅在 schema 稳定后）

---

## 需要人类确认的事项（不要自作主张）

这些必须由你确认：

1. 第一版 helper 是否只做 `FamilyHelperAgent`
2. helper-off 的失败策略是 fail-fast 还是 baseline fallback
3. `support_style` 的离散标签集合
4. `instruction_quality / autonomy_preservation / proxy_completion_level` 的取值范围与标度
5. helper 与 older adult 的关系粒度（只 family，还是 family subtype）
6. 是否允许 appendix 中启用 helper LLM
7. `requested_help` 的离散集合（如 `teach_me` / `do_it_for_me` / `check_it`）

---

## 论文表达建议

### 可以说

- We upgrade support from a scalar world parameter to task-triggered, structured, auditable support interactions.
- Helper responses affect bounded support features consumed by the outcome model.
- Psychological updates remain governed by the existing post-outcome pipeline.

### 不要说

- We model a full real-world support ecology.
- Communication app usage proves real help-seeking.
- Helper agents determine helplessness or controllability.
- The helper directly decides task success.
- We jointly model full family/peer/customer/volunteer society in the current MVP.

---

## Done 定义（仅针对后续 support MVP）

只有在以下条件全部满足后才算 support MVP 完成：

- helper 只在 `seek_help_then_attempt` 时触发
- `SupportRequest / SupportResponse` schema 稳定
- helper-off regression 通过
- outcome truth 仍由 `outcome_model` 决定
- banned-key leakage = 0
- `state_update.py` / Bayesian key / controllability formula 未被改动
- replay determinism / coverage / audit 报表齐全

---

## 当前阶段最终决策

当前阶段：

- **做**：`mobile-intention entry layer`
- **不一起做**：完整 multi-agent support MVP
- **预留**：support protocol / audit hook / future integration point

一句话：

> 先把“任务怎么出现”做扎实；再把“求助后别人如何回应”从 scalar 升级成结构化 support interaction。

