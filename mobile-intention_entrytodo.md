# mobile-intention entrytodo.md

## 文档定位

本文件定义 `digital_friction_mvp` 的**任务入口改造**，目标是在**不改 post-entry 主链**的前提下，把当前 fixed assignment 的数字任务入口升级为：

> AgentSociety-inspired, data-calibrated, constrained mobile-intention entry layer

中文：**受限手机动作意图入口层**。

它只回答两个问题：

1. 这个 agent 在当前 evaluation tick 是否进入某类手机活动？
2. 如果进入，该手机活动是否能高置信映射为现有 6 类 `DigitalTask` 之一？

它**不回答**：

- outcome 是什么
- success / failure 是什么
- 是否 avoid
- 是否 seek_help_then_attempt
- helplessness delta
- self-efficacy delta
- controllability posterior
- Phase4 / Phase5C policy weights

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

## 已确认的仓库现实（设计必须服从这些事实）

### 1) 当前任务入口是 fixed assignment

`examples/digital_friction_mvp/proto/task_assignment.py` 当前有：

- 6 类 `TASK_LIBRARY`
- 固定任务窗口 `09:00 / 14:00 / 19:00`
- 非窗口 `select_task_for_agent(...) -> None`
- 命中窗口后按 `seed + agent_id + day` rotation 取模板并实例化 `DigitalTask`

### 2) 当前 runtime 只在有 task 时写 task surface

`examples/digital_friction_mvp/proto/runtime.py` 当前的 `assign_task_if_missing(...)` 行为是：

- 已有 task：直接保留
- 没有 task：调用 `select_task_for_agent(...)`
- 返回 `None`：不写 task surface
- 返回 task：写
  - `proto_assigned_task_json`
  - `digital_todo_pending`
  - `digital_todo_active_task_id`
  - `digital_task_hint`
  - `digital_task_hint_need`

这条边界必须保留。

### 3) 当前 agent 层已经有 no-task idle 写回

`examples/digital_friction_mvp/proto/agent.py` 当前 `_write_idle_step_state()` 会写：

- `current_intention = "No digital task assigned"`
- `friction_step_signal.step_type = "idle"`
- `step_intention = "No digital task assigned"`
- `step_outcome = "none"`

新入口层不能破坏这条“无任务就 idle”的总体形状，只能把语义从“未分配 task”改成“未进入 mobile activity / 未生成 digital task”。

### 4) post-entry 主链必须原样保留

当前数字任务进入后，已有主链是：

`DigitalTask -> task_appraisal -> strategy_deliberation -> semantic_v2 pi_ref -> Bayesian policy lite / Phase4 -> Huys-Dayan-lite controllability / Phase5C -> choose_attempt_strategy(...) -> outcome_model -> helplessness / attribution / scope_spillover / memory update`

这条链是本项目当前最有价值的部分，不是这轮重构对象。

### 5) 当前 outcome truth 仍由 outcome_model 决定

`examples/digital_friction_mvp/proto/outcome_model.py` 当前仍通过 `support_quality_from_env(env)` 和 task / strategy / helplessness / env 等计算结果。入口层不能越权决定 outcome。

### 6) 当前 memory 里 help / avoid / episode 都是 post-entry 语义

`examples/digital_friction_mvp/proto/models.py` 里：

- `AttemptStrategy.support_requested` 已存在
- `RecentEpisode` 包含 `strategy_type / outcome_type / avoid_reason / help_used / help_source / helplessness_delta`

因此：

- `no_mobile_action` 不能伪装成 `avoid`
- `communicate_or_seek_help` 不能伪装成 `seek_help_then_attempt`
- no-op 不应写 `RecentEpisode`

### 7) Phase4 / Phase5C 当前明确不读取 post-outcome 信息做 pre-event policy

入口层不能把任何“结果后”信息偷塞回 pre-entry 决策，否则会与现有 no-leakage 边界冲突。

### 8) AgentSociety 原生机制是“context/need -> plan/intention -> block/action”

参考 `SocietyAgent.forward()`、`PlanBlock.forward()`、`BlockDispatcher`：

- `forward()` 先 `needs_block.forward()`，再 `plan_generation()`，再 `step_execution()`
- `PlanBlock` 会从 `current_need` 生成带 `steps` 的 plan
- 每个 step 需要 `intention` 和 `type`
- `Dispatcher` 只在受限 block 集和 `no_suitable_block` 之间选

因此这轮入口改造应借鉴的是：

- 先有 intention，再有 concrete action/task
- 选择空间受限
- 无合适映射时允许 `no-op`

而不是上来做完整自由计划。

---

## 总体裁决

### 现在该做什么

现在主线应该做：

1. 保留 `fixed_assignment` baseline
2. 新增 `mobile_intention_rule`
3. 新增 `mobile_intention_llm_shadow`
4. Phase 2 可新增 `mobile_intention_llm_rerank_online_mc`，作为 LLM entry 条件下的 Monte Carlo 主/辅助实验

### 为什么

因为当前项目主论文的主线仍然应是：

> controllability-centered post-entry policy modulation

入口层是为了让 exposure 更像 agent-conditioned mobile activity。Phase 1 先用规则入口保证稳定基线；Phase 2 如果让 LLM rerank 进入主线，必须把它写成在线随机组件，通过多轮 Monte Carlo runs、均值和置信区间报告，而不是写成单次 deterministic paired-world 结论。

---

## 非目标（必须明确写死）

本轮不做：

- full AgentSociety native PlanBlock 接管数字任务入口
- DigitalTaskBlock + Dispatcher 重构
- free-form LLM action generation
- 让 LLM 直接生成新 task_family
- 让 entry 层读取 outcome / helplessness / posterior / Phase4 / Phase5C
- 让 entry 层决定 avoid / help / success / failure
- DB schema 迁移
- 新建 sampler 框架
- 用 runtime 直接读百万行 CSV
- 把 TalkingData 解释成 friction/help/avoid/outcome/helplessness ground truth

---

## Mobile Intention Set

第一版固定集合：

- `check_information`
- `use_payment_or_finance`
- `login_or_verify_account`
- `submit_service_application`
- `upload_or_manage_profile`
- `find_location_or_service`
- `communicate_or_seek_help`
- `browse_entertainment`
- `no_mobile_action`
- `unknown_or_unmapped`

### 设计要求

- 只能从这个集合中选
- 不能生成集合外动作
- 不能隐式扩展新枚举
- 不能把低置信映射硬塞进现有 6 类 task

---

## 必须区分的两个概念

### 1) `mobile_intention`

表示：

> 此刻像哪类手机活动

### 2) `digital_task_opportunity`

表示：

> 该手机活动是否高置信映射成现有 6 类 `DigitalTask`

这两个概念必须显式区分，不能混用。

例子：

- `communicate_or_seek_help`：是 mobile intention，不是 digital task opportunity
- `browse_entertainment`：是 mobile intention，不是 digital task opportunity
- `no_mobile_action`：不是 avoid
- `unknown_or_unmapped`：不是 fallback task

---

## 与现有 6 类 DigitalTask 的映射

### 高置信映射

- `check_information` -> `information_search_judgment`
- `use_payment_or_finance` -> `payment_risk_confirmation`
- `login_or_verify_account` -> `account_login_verification`
- `submit_service_application` -> `service_application_submission`
- `upload_or_manage_profile` -> `profile_form_upload`
- `find_location_or_service` -> `navigation_service_location`

### context-only / no-op

- `communicate_or_seek_help`
  - context-only
  - 不生成 `DigitalTask`
  - 不等于 `seek_help_then_attempt`
  - 不触发 helper
  - 不写 help memory

- `browse_entertainment`
  - context-only / no-op
  - 不生成 `DigitalTask`

- `no_mobile_action`
  - no-op
  - 不生成 `DigitalTask`
  - 不算 `avoid`

- `unknown_or_unmapped`
  - no-op / audit-only
  - 不 fallback 到随机 task

---

## TalkingData 的使用边界

### 可以做

May1-May3 `elder_reference.csv` 只能用于离线校准：

- hourly mobile activity profile
- category -> mobile intention map
- mobile intention prior by age/gender/device/hour
- user-level preference profile
- unknown/unmapped mass
- mapping confidence
- calibration artifact hash

### 不可以做

不能把 TalkingData 直接用作：

- friction 标签
- success / failure 标签
- help / avoid 标签
- helplessness / controllability 标签
- helper availability ground truth

### Held-out validation

May4-May7 `elder_validation.csv` 只能用于：

- 模拟 mobile intention 分布 vs held-out 分布
- 小时分布相似度
- mapped task family 分布相似度
- unknown/unmapped 比例是否被保留

不能进入 runtime，不进入 prompt，不进入 entry decision。

---

## Agent 自有 profile 的使用边界

TalkingData 只提供非常粗的可观测行为上下文，例如：

- age / gender
- device / phone brand / model
- hour
- app category trace
- user-level category preference

它不提供完整的老人心理画像。

因此，mobile-intention entry 可以结合两类信息：

```text
TalkingData calibration:
age / gender / device / hour / category prior

agent stable initial profile:
进入实验前已经固定的人口、能力、设备熟悉度等画像
```

但必须严格区分：

### 可以作为 entry feature 的稳定 profile

这些特征如果是初始化时固定的、不会被不同 world 的任务结果改变，可以进入 `mobile_intention_rule` 或 LLM shadow / online MC rerank：

- age
- gender
- education / literacy level（如果 profile 中已有）
- baseline digital experience
- baseline device familiarity
- baseline vision / health limitation
- baseline support access / living arrangement（如果初始化固定）
- baseline digital confidence（仅限初始化固定值）

这些信息表示：

> 这个 agent 原本是什么样的人。

### 不能作为主 paired-world entry feature 的动态状态

这些特征会被不同 world 的 outcome history 改变，第一版主 paired-world entry 不能读取：

- previous task outcome
- recent failure count
- recent avoid ratio
- recent help-seeking ratio
- current helplessness score / delta
- current self-efficacy delta
- `C_family / C_global`
- Bayesian posterior / counts
- Phase4 `pi_final`
- Phase5C `pi_final_controllability`
- last strategy / last outcome
- any post-task memory feature

这些信息属于：

> 实验过程中被摩擦和支持条件影响的后验心理/行为状态。

### 为什么要这样分

主 paired-world 实验要求同一个 agent 在同一 seed / day / tick 下拥有一致的 entry opportunity。

如果 entry layer 读取 recent failures、helplessness、posterior 等动态状态，那么 high-friction world 和 low-friction world 会逐渐得到不同的任务入口，最后很难判断结果差异来自：

```text
post-entry Phase4 / Phase5C 机制
```

还是来自：

```text
entry exposure 已经被 world-specific outcome history 改变
```

### LLM 介入时的 prompt 边界

如果开启 `mobile_intention_llm_shadow` 或 `mobile_intention_llm_rerank_online_mc`，LLM 只能看到：

- constrained top-k mobile intention candidates
- candidate priors
- current hour
- TalkingData-derived coarse observable context
- stable initial agent profile
- mapping confidence / mapping rule explanation

LLM 不能看到：

- outcome history
- helplessness
- controllability posterior
- Bayesian posterior
- Phase4 / Phase5C policy weights
- any future outcome or downstream label

推荐 prompt 表述为：

```text
Given this coarse observable context and stable initial profile,
choose one mobile intention from the constrained candidates.
Do not infer success, failure, avoidance, help-seeking strategy, or psychological update.
```

不要写成：

```text
Given the elder's current psychological state after recent task failures...
```

除非以后单独做 ecological feedback experiment。

---

## 入口机制设计

## Mode 0: `fixed_assignment`

保留当前实现，作为 baseline。

## Mode 1: `mobile_intention_rule`

主实验推荐模式。

规则：

1. 使用 reference artifact + deterministic rules 生成 top-k intention candidates
2. 从 top-k 中用**确定性**规则选择一个 intention
3. 若 intention 高置信映射到 task_family，则生成 `DigitalTask`
4. 否则 no-op / context-only / audit

### 为什么它应该成为第一版主模式

- 可复现
- paired-world 最稳
- 审稿最容易解释
- 不会把论文重心从 controllability modulation 转移到 LLM

## Mode 2: `mobile_intention_llm_shadow`

第一版允许，但只做 shadow。

规则：

- 接收 rule mode 的 top-k candidates
- 只做“如果让 constrained LLM 选，它会选哪个”的 shadow 记录
- **不能**驱动真实 task entry
- 只做一致率分析 / prompt sanity check

## Mode 3: `mobile_intention_llm_rerank_online_mc`

Phase 2 可启用，作为 LLM entry 条件下的 Monte Carlo 主/辅助实验。

仅允许：

- rule/data top-k candidates 内 rerank
- online LLM call
- run-level shared entry schedule
- 多轮 Monte Carlo runs
- 均值 / 方差 / 置信区间报告

不允许：

- LLM 自由生成集合外 mobile intention
- LLM 直接生成 `DigitalTask`
- LLM 决定 strategy / outcome / helplessness / posterior
- 同一 run 内四个 paired worlds 各自独立调用 LLM 造成 entry exposure 不一致

可选 robustness：

- 如果未来需要 deterministic ablation，可以另做 `mobile_intention_llm_rerank_replay`。

---

## 执行阶段

### Phase 1: baseline + rule entry + validation + LLM shadow

这是当前主 patch / 主实验阶段。

目标：

1. 保留 `fixed_assignment` baseline，确保旧实验可复现。
2. 实现 `mobile_intention_rule`，作为第一版主入口机制。
3. 使用 May1-May3 `elder_reference.csv` 生成离线 calibration artifact。
4. runtime 只读取 reference artifact，不读取原始百万行 CSV，不读取 May4-May7 validation 数据。
5. 实现 no-op / context-only 语义：
   - `no_mobile_action`
   - `unknown_or_unmapped`
   - `communicate_or_seek_help`
   - `browse_entertainment`
   - `low_confidence_mapping_noop`
6. 实现 entry audit，证明 entry 层不读 outcome / helplessness / posterior / Phase4 / Phase5C。
7. 使用 May4-May7 `elder_validation.csv` 做 held-out exposure validation：
   - hourly profile similarity
   - mobile intention distribution similarity
   - mapped task family similarity
   - unknown/unmapped mass similarity
8. 可选启用 `mobile_intention_llm_shadow`：
   - LLM 只看 top-k candidates / coarse observable context / stable initial profile
   - 只记录 shadow decision 和 agreement rate
   - 不驱动真实 entry

Phase 1 的验收标准：

- `fixed_assignment` baseline 完整保留并通过回归测试。
- `mobile_intention_rule` 可以生成 mapped task 或 no-op。
- mapped task 仍进入原 DigitalTask 主链。
- no-op / context-only 不进入 post-task chain，不更新心理变量。
- paired-world 中同一 agent / seed / day / tick 的 entry decision 一致。
- runtime 不读取 May4-May7 validation artifact。
- held-out validation 报表可以生成。
- LLM shadow 即使失败，也不影响真实实验。

### Phase 2: online LLM rerank Monte Carlo

这是后续 LLM entry 条件实验阶段。它不要求 persistent replay/cache 锁死 LLM 输出，而是把 LLM rerank 作为在线随机组件，通过多轮 Monte Carlo runs 估计平均效果。

关键原则：

```text
不要求跨所有实验永久复用同一份 LLM cache
但同一个 Monte Carlo run 内，四个 paired worlds 必须共享同一份 entry decision schedule
```

也就是说：

```text
run 1:
  在线生成一份 LLM rerank entry schedule
  world A/B/C/D 都使用这份 schedule

run 2:
  可以重新在线生成另一份 schedule
  world A/B/C/D 再共享 run 2 的 schedule
```

这样既允许 LLM 随机性进入主线，又避免同一轮中不同 world 因为 LLM 随机差异看到完全不同的 entry exposure。

目标：

1. 启用 `mobile_intention_llm_rerank_online_mc`，但只允许在 rule/data top-k candidates 内 rerank。
2. LLM 可以在线读取 constrained candidates、candidate priors、hour、coarse observable context、stable initial profile。
3. 同一 Monte Carlo run 内，四个 paired worlds 必须共享同一份 `selected_mobile_intention` schedule。
4. LLM invalid JSON / out-of-set intention / low confidence 不能 fallback 到随机 task。
5. 跑多轮实验，报告 entry distribution、mapped task distribution、downstream outcome metrics 的均值、方差、置信区间。
6. 和 Phase 1 `mobile_intention_rule` 分开报告，说明这是 LLM-entry-conditioned simulation。

Phase 2 的验收标准：

- 每个 Monte Carlo run 有唯一 `run_id`。
- 同一 `run_id / agent_id / day / tick` 在四个 worlds 中返回完全相同的 `selected_mobile_intention`。
- LLM 不能生成集合外 intention。
- LLM 不能决定 strategy / outcome / helplessness / posterior。
- invalid / low-confidence handling policy 必须预先声明。
- 每次 LLM 调用记录 prompt version / model id / candidate priors / selected intention / confidence / parse status / response hash。
- Phase 2 报告 Monte Carlo mean / standard error / confidence interval。
- Phase 2 与 Phase 1 主规则结果分开报告。

---

## world-neutral 原则

主 paired-world 模式下，同一：

- seed
- agent_id
- day
- tick
- profile bucket
- calibration artifact

必须得到相同：

- `selected_mobile_intention`
- `entry_status`
- `mapped_task_family`

不同 world 只能影响：

- task difficulty
- friction/support env
- outcome
- downstream psychological updates

### 所以 entry 层绝对不能读取

- previous task outcome
- success/failure history
- recent avoid ratio
- helplessness score / delta
- self-efficacy delta
- `C_family / C_global`
- Bayesian posterior
- Phase4 `pi_final`
- Phase5C `pi_final_controllability`
- world-specific outcome history

### `current_need / current_intention`

第一版只允许：

- `shadow`
- 或非常保守的 bounded logging

不作为 paired-world 主实验的 active feature。

---

## 评估 tick 设计

### 第一版建议

`PROTO_MOBILE_INTENTION_EVAL_INTERVAL_MINUTES = 60`

### 原因

- 与 TalkingData hourly profile 对齐
- 观察口径更好解释
- 不会像每个 simulator tick 一样爆量
- 保留足够多的 entry opportunities

### 可选敏感性分析

- 30 分钟
- 60 分钟

第一版不要：

- 5 分钟
- 每 step 都评估
- 不规则自适应间隔

---

## mapping confidence 规则

默认阈值建议：`0.70`

### 判定

- `>= 0.70`：允许实例化 `DigitalTask`
- `0.40 ~ 0.70`：`low_confidence_mapping_noop`
- `< 0.40`：`unknown_or_unmapped_noop`

### 为什么

- 0.70 作为主阈值足够保守
- 但必须做敏感性分析：0.60 / 0.70 / 0.80

---

## No-op / Context-only 语义

### `no_mobile_action`

必须保证：

- 不生成 `DigitalTask`
- 不算 `avoid`
- 不写 `RecentEpisode`
- 不更新 helplessness
- 不更新 Bayesian policy memory
- 不更新 controllability memory
- 不进入 attempt/help/avoid denominator

### `unknown_or_unmapped`

必须保证：

- 不生成 `DigitalTask`
- 不 fallback
- 只记录 audit
- 不更新心理变量

### `communicate_or_seek_help`

必须保证：

- 不生成 `DigitalTask`
- 不等于 `seek_help_then_attempt`
- 不触发 helper
- 不更新 help memory
- 不算 help action
- 只作为 context-only / communication context

### `browse_entertainment`

必须保证：

- 第一版不映射 task
- 只作为 context-only / no-op

---

## 最小新增数据结构（尽量少抽象）

第一版建议**不要**新搞复杂类层次。

只建议新增一个很轻的结果结构，二选一：

### 选项 A：dict

在 `task_assignment.py` 内部直接返回：

```python
{
  "selected_mobile_intention": ...,
  "mapped_task_family": ...,
  "mapping_confidence": ...,
  "entry_status": ...,
  "task": DigitalTask | None,
  "audit": {...}
}
```

### 选项 B：轻 dataclass

如果你更想要类型安全，可以在 `models.py` 加一个非常轻的：

- `MobileEntryDecision`

但禁止继续往外扩成新框架。

### 不建议

- 新建 sampler 模块
- 新建复杂 planner hierarchy
- 新建 dispatcher integration layer
- 新建 DB models

---

## 文件级修改计划

## 必须改

### `examples/digital_friction_mvp/proto/task_assignment.py`

新增：

- `MOBILE_INTENTION_SET`
- `MOBILE_INTENTION_TO_TASK_FAMILY`
- candidate generation
- deterministic selection for `mobile_intention_rule`
- mapping confidence threshold
- no-op / context-only handling
- entry audit builder
- mode dispatch

保留：

- 当前 `TASK_LIBRARY`
- 当前 fixed windows
- 当前 `select_task_for_agent(...)` 路径作为 baseline
- `encode_task / decode_task`

### `examples/digital_friction_mvp/proto/runtime.py`

新增：

- `assign_task_if_missing(...)` 支持 entry mode
- no-op 只写 audit / `friction_step_signal`
- mapped task 才写 `proto_assigned_task_json / digital_todo_pending`

### `examples/digital_friction_mvp/proto/agent.py`

必须改：

- early return 改成 mode-aware
- fixed mode 仍用旧 task windows
- mobile intention mode 使用新的 evaluation schedule
- idle 文案从
  - `No digital task assigned`
  - 改成
  - `No mobile digital activity entered`
- no-entry 不进入 post-task chain

### `examples/digital_friction_mvp/config_runtime.py`

新增配置：

- `PROTO_TASK_ENTRY_MODE`
- `PROTO_MOBILE_INTENTION_CALIBRATION_PATH`
- `PROTO_MOBILE_INTENTION_MAPPING_PATH`
- `PROTO_MOBILE_INTENTION_CONFIDENCE_THRESHOLD`
- `PROTO_MOBILE_INTENTION_EVAL_INTERVAL_MINUTES`
- `PROTO_MOBILE_INTENTION_WORLD_NEUTRAL`
- `PROTO_MOBILE_INTENTION_LLM_PROMPT_VERSION`
- `PROTO_MOBILE_INTENTION_LLM_MIN_CONFIDENCE`

要求：

- 默认仍是 `fixed_assignment`
- 配置校验必须 fail-fast

### `examples/digital_friction_mvp/main.py`

- 读取新配置
- run metadata 记录 entry mode / artifact hash
- runtime 只读 reference artifact

### `examples/digital_friction_mvp/world_runner.py`

必须把新环境变量加入 `FINGERPRINT_ENV_KEYS`。

### analysis / tests

新增 entry 层分析与测试。

## 可以改

### `examples/digital_friction_mvp/proto/models.py`

仅允许轻量新增：

- `MobileEntryDecision`（可选）

禁止：

- 改 `RecentEpisode` 语义
- 把 no-entry 写成 episode

## 不要改

- `proto/outcome_model.py`
- `proto/state_update.py`
- `proto/bayesian_policy_lite.py`
- `proto/bayesian_controllability_lite.py`
- `proto/attribution_inference.py`
- `scope_spillover` 公式
- DB schema
- attempt strategy sampler

---

## Audit 设计

每次 entry evaluation 记录：

- `agent_id`
- `world`
- `day`
- `tick_seconds`
- `hour`
- `entry_mode`
- `entry_eval_interval_minutes`
- `candidate_intentions`
- `candidate_priors`
- `selected_mobile_intention`
- `mapped_task_family`
- `mapping_confidence`
- `entry_status`
- `calibration_split = elder_reference_may1_may3`
- `calibration_artifact_hash`
- `mapping_artifact_hash`
- `uses_validation_data = false`
- `uses_post_outcome_information = false`
- `uses_helplessness_state = false`
- `uses_controllability_posterior = false`
- `uses_phase4_policy = false`
- `uses_phase5c_policy = false`
- `does_not_decide_strategy = true`
- `does_not_decide_outcome = true`
- `does_not_update_psychology = true`
- `is_avoidance = false`
- `is_help_action = false`
- `reason`

如果开 `mobile_intention_llm_shadow`，再额外记录：

- `llm_prompt_version`
- `llm_model_id`
- `llm_cache_key`
- `llm_cache_hit`
- `llm_confidence`
- `llm_parse_status`
- `llm_selected_intention_raw`
- `llm_response_hash`

---

## 测试计划

## 必做单元测试

- `fixed_assignment` backward compatibility
- mobile intention mode 不依赖 `09 / 14 / 19` fixed window
- rule candidate generation deterministic
- mapping_confidence 低于阈值 -> no-op
- `unknown_or_unmapped` 不 fallback
- `no_mobile_action` 不算 avoid
- `communicate_or_seek_help` 不等于 `seek_help_then_attempt`
- `browse_entertainment` 不映射任务
- no-entry 不写 `RecentEpisode`
- no-entry 不更新 helplessness
- no-entry 不更新 Bayesian policy memory
- no-entry 不更新 controllability memory
- entered mapped task 仍走原 `DigitalTask` 主链
- runtime 不读取 May4-May7 validation artifact
- audit 中 `uses_post_outcome_information=false`

## paired-world 测试

- world-neutral mode 下四个 worlds：
  - `selected_mobile_intention` 一致
  - `entry_status` 一致
  - `mapped_task_family` 一致

## LLM shadow / rerank 测试

- LLM 只能选 top-k candidate
- LLM 选集合外 intent 被拒绝
- low LLM confidence -> no-op / rejected according to mode
- invalid LLM JSON 不隐式 fallback 到 random task
- online MC rerank 记录 run_id / prompt version / candidate priors / profile bucket / hour
- 同一 run_id / agent_id / day / tick 在四个 worlds 中 entry decision 一致
- 不同 run_id 可以有不同 LLM rerank schedule
- Phase 2 汇总报告 mean / standard error / confidence interval

## analysis 测试

- held-out validation 只比较 exposure distribution
- avoid denominator 不含 no-entry
- no-leakage audit 报表完整

---

## 推荐实验分组

### E0: `fixed_assignment`

当前 baseline。

### E1: `mobile_intention_rule_uncalibrated`

不使用 TalkingData calibration，只用弱规则 / 均匀 prior。

### E2: `mobile_intention_rule_calibrated`

主实验。

### E3: `mobile_intention_llm_shadow`

只做 shadow，不驱动真实 entry。

### E4: `mobile_intention_llm_rerank_online_mc`

LLM entry 条件下的 Monte Carlo 实验。

要求：

- LLM 只能在 rule/data top-k candidates 内 rerank。
- 同一个 run 内，四个 paired worlds 共享 entry schedule。
- 多轮 runs 报告均值、方差、置信区间。
- 不声称单次 run 的逐 tick paired-world 差异完全来自 Phase4 / Phase5C。

### E5: `mobile_intention_llm_rerank_replay_ablation`

可选 appendix / robustness，如果未来需要 deterministic replay/cache 对照再做。

### Held-out validation

May4-May7 只做：

- hourly profile similarity
- mobile intention distribution similarity
- mapped task family similarity
- unknown/unmapped mass similarity

---

## 推荐指标

### entry 层

- `entry_evaluation_count`
- `mobile_intention_distribution`
- `mobile_activity_rate`
- `digital_task_opportunity_rate`
- `mapped_task_family_distribution`
- `no_mobile_action_rate`
- `unknown_or_unmapped_rate`
- `communicate_context_only_rate`
- `browse_context_only_rate`
- `task_generated_count`
- `task_generated_per_agent_day`

### post-entry 层

只在 `task_generated=true` 上算：

- `attempt_self_rate`
- `seek_help_then_attempt_rate`
- `avoid_rate`
- `abandon_midway_rate`
- `success_self_rate`
- `success_with_help_rate`
- `failure_after_attempt_rate`
- `failure_even_with_help_rate`

### Phase4 / Phase5C

- Phase4 intervention rate
- Phase4 TVD from semantic `pi_ref`
- Phase5C intervention rate
- Phase5C TVD from Phase4 `pi_final`
- `pi_ref -> pi_final -> pi_final_controllability` drift

### 心理层

- `helplessness_delta`
- `helplessness trajectory`
- `controllability trajectory`

### Held-out validation

- hourly TVD / JS divergence
- mobile intention distribution TVD
- mapped task family TVD
- unknown/unmapped mass difference

### QC / audit

- no-leakage audit
- world separation audit
- LLM shadow agreement rate

---

## 需要人类确认的事项（不要自作主张）

以下内容必须由你确认后才能锁死，不要拍脑袋写进代码：

1. category -> mobile intention 映射表的最终人工规则
2. age/gender/device bucket 的分桶粒度
3. `vision_limit` / `digital_experience` 是否已经在 profile 中稳定存在
4. entry evaluation interval 最终取 30 还是 60 分钟
5. mapping_confidence 的人工校准来源与审核标准
6. 是否启用 `mobile_intention_llm_rerank_online_mc` 作为 Phase 2，以及 Monte Carlo run 数量
7. `communicate_or_seek_help` 是否允许在未来作为 support availability proxy 留痕

---

## 论文表达建议

### 可以说

- 我们把 fixed task assignment 升级为 agent-conditioned mobile-intention entry。
- TalkingData-style traces 只用于 exposure calibration 和 heterogeneity calibration。
- non-entry 表示 no modeled mobile digital activity，不等于 avoidance。
- post-entry psychological mechanism 保持不变。

### 不要说

- TalkingData 证明了 digital friction / learned helplessness。
- app non-use 就是 avoid。
- communication app usage 等于 help-seeking。
- LLM 决定老人真实会不会做某任务。
- 这已经是 full AgentSociety-native planning。

---

## Done 定义

本 todo 只有在下列条件全部满足后才算完成：

- `fixed_assignment` baseline 完整保留并通过回归测试
- `mobile_intention_rule` 跑通
- no-op / context-only 语义严格成立
- paired-world entry comparability 成立
- runtime 不读取 validation artifact
- held-out validation 报表跑通
- Phase4 / Phase5C / outcome / helplessness 主链未被修改
- 文档 / audit / tests 与实现一致
