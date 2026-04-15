# Digital Friction MVP 开发日志

更新时间：2026-02-26  
文件范围：`examples/digital_friction_mvp/main.py`

## 本次目标

针对最小实验中暴露的结果偏置、可解释性不足、问卷回写不稳、LLM 实际未生效等问题，按条目逐项落地改造。

## 逐项修改记录

### 1) 冒烟强制事件只在 smoke 模式生效（避免污染正式实验）

- 修改点：
  - 新增 `EXP_MODE` / `SMOKE_MODE_ENABLED`
  - `SMOKE_FORCE_EVENT` 增加模式门控（仅 `EXP_MODE in {smoke, debug_smoke, stress}` 且开关为真时启用）
- 位置：
  - `main.py` 变量区（约 `136-183`）
- 结果：
  - 正式实验不会因误开 `SMOKE_FORCE_EVENT=1` 被强制事件污染。

### 2) 强制事件从“默认第一个 agent”改成“每 step 选定目标 agent”

- 修改点：
  - 每个 step 预选一个 `smoke_force_target_agent_id`
  - 仅该 agent 允许触发 forced roll
  - 审计中记录 `smoke_force_target_agent_id`
- 位置：
  - `trigger_event_shocks`（约 `1879-1881`, `2023`, `2046-2050`）
- 结果：
  - 冒烟场景下事件注入更公平，不再长期集中到同一 agent。

### 3) 修复 LLM 调用预算：按“step 总预算”而非“每 agent 重置”

- 修改点：
  - 判断条件改为 `llm_calls_this_step < LLM_DECIDER_MAX_CALLS_PER_STEP`
- 位置：
  - `trigger_event_shocks`（约 `1954`）
- 结果：
  - 预算语义与配置一致，避免“每个 agent 都能单独吃满预算”的偏差。

### 4) LLM 失败类型拆分：请求失败 vs 解析失败

- 修改点：
  - `_query_llm_event_suggestion` 返回 `(suggestion, status)`
  - `status` 包含 `ok/request_error/parse_failed`
  - 新增 step 指标：
    - `step.llm_request_error_count`
    - `step.llm_parse_fail_count`
- 位置：
  - `_query_llm_event_suggestion`（约 `1136-1214`）
  - `trigger_event_shocks`（约 `1955-1974`, `2220-2221`）
- 结果：
  - 可以明确定位 LLM 不生效是网络/接口问题还是输出格式问题。

### 5) 提升 LLM JSON 解析鲁棒性

- 修改点：
  - `_extract_json_object` 支持：
    - 代码块包裹
    - 二次字符串包裹 JSON
    - list 中包含 dict 的情况
- 位置：
  - `main.py`（约 `945-981`）
- 结果：
  - 降低“llm_no_suggestion”中的格式误伤比例。

### 6) 场景匹配增加多源上下文与 step_type 先验

- 修改点：
  - 新增：
    - `_preferred_scenario_from_step_type`
    - `_is_digital_interaction_context`
    - `_is_scenario_aligned_with_context`
  - `_match_scenario` 改为支持 `step_signal`
  - `fallback` 前先判断是否属于数字交互语境
- 位置：
  - 场景相关函数（约 `361-618`）
  - 触发入口（约 `1894-1908`）
- 结果：
  - 降低“意图与事件不一致”的语义漂移。

### 7) 正向事件中的 help/intercept 由更真实证据驱动

- 修改点：
  - `_infer_positive_process_signals` 引入：
    - `failure_pressure`
    - `step_eval_text`
    - 更严格的 `help_requested` / `intercepted` 判据
- 位置：
  - `main.py`（约 `621-654`）
- 结果：
  - 统计语义更接近真实行为，不再“场景即拦截”。

### 8) 阶段结算去除二次放大（避免重复加权）

- 修改点：
  - `stage_settlement` 不再二次改写 `helplessness/trust/avoidance`
  - 保留阶段统计与计数归零
- 位置：
  - `stage_settlement`（约 `2267-2331`）
- 结果：
  - 避免“事件已更新一次 + 阶段再放大一次”导致快速饱和到 0/100。

### 9) 问卷解析兼容大小写与多种字段名

- 修改点：
  - `_extract_survey_result_values` 新增大小写无关读取
  - 支持 `answer/rating/value/response/score` 与大小写变体
- 位置：
  - `main.py`（约 `657-722`）
- 结果：
  - 减少问卷字段缺失，提高回写稳定性。

### 10) 问卷同步改为增量拉取（避免每次全表扫描）

- 修改点：
  - 新增全局游标 `_LAST_SURVEY_SYNC_CURSOR`
  - `sync_survey_feedback` 按 `(day, t, id)` 增量读取
- 位置：
  - 全局变量（约 `142`）
  - `sync_survey_feedback`（约 `1611-1662`）
- 结果：
  - 实验变长后性能更稳定。

### 11) 增加 step 级公平性/一致性监控指标

- 修改点：
  - 新增指标：
    - `step.scenario_alignment_rate`
    - `step.agent_event_count_std`
    - `step.agent_event_count_min`
    - `step.agent_event_count_max`
- 位置：
  - `trigger_event_shocks`（约 `2024-2032`, `2192-2226`）
- 结果：
  - 可直接监控事件是否偏斜到个别 agent、语义是否对齐。

### 12) 消除 `stage=unknown` 初始快照

- 修改点：
  - 初始 workflow 去掉 stage 环境未设定时的 `log_step_status`
  - `log_step_status` 增加 `bootstrap` 兜底
- 位置：
  - `workflow_steps`（约 `2367-2375`）
  - `log_step_status`（约 `1523-1525`）
- 结果：
  - 输出表中 stage 标签更稳定。

### 13) 最小实验默认移除 EconomyBlock（降低无经济体 warning 噪声）

- 修改点：
  - `DigitalFrictionAgent` block 配置移除 `EconomyBlock`
  - `default(config)` 兜底配置同步移除
- 位置：
  - Agent 配置（约 `2485-2489`, `2509-2512`）
- 结果：
  - 在仅 citizen 的 MVP 运行中减少 `MonthPlanBlock` 相关 warning。

### 14) 增加可控 mobility nudge（缓解“全程不出行”）

- 修改点：
  - 新增 `nudge_mobility_if_stuck`
  - 新增参数：
    - `MOBILITY_NUDGE_PROB`
    - `MOBILITY_NUDGE_START_HOUR`
    - `MOBILITY_NUDGE_END_HOUR`
  - 在每个 step 前执行 nudge
- 位置：
  - 参数区（约 `188-192`）
  - 函数（约 `1747-1778`）
  - workflow（约 `2392-2395`）
- 结果：
  - 对“长期 stay-at-home 导致 trip=0”提供干预入口。

## 本次未改动

- 保持 `LLMProviderType.ZhipuAI` 不变（按需求保留现状）。

## 快速验证

- 已执行语法检查：
  - `python -m py_compile examples/digital_friction_mvp/main.py`
  - 结果：通过

## 2026-02-27 实验问题清单（exp_id=22f03983-ffd2-4450-affe-0b586f1ff783）

### 运行结论（先给结论）

- 本次实验已完成并落盘（`status=2`，`error=''`），不是崩溃中断。
- 但“可用事件信号”严重不足，导致阶段对比解释力偏弱。

### P0（优先修，直接影响结论可信度）

1) 事件触发率过低，几乎无有效干预样本  
- 证据：
  - `step.event_emitted_count` 总和 = `1`（72 个 step 内仅 1 次事件）
  - 6 个 agent × 72 step = 432 个潜在决策机会，事件率约 `0.23%`
  - `artifacts.json` 中仅 `stage_1_events.agent=1` 有 1 条，`stage_2_events`/`stage_3_events` 全空
- 影响：
  - shock/recovery 阶段几乎没有“摩擦刺激”，无法验证阶段机制是否生效。
- 改进方向：
  - 先把“每 step 可进入决策”的门槛调高命中率（降低 skip）。
  - 在正式实验中将目标事件率先稳定到可分析区间（例如 5%~15%）再做统计对比。

2) 大多数 agent-step 被直接跳过，决策入口过窄  
- 证据：
  - `step.scenario_skip_count` 总和 = `365`（平均每 step 跳过 `5.07/6` 个 agent）
  - `step.decision_attempt_count` 总和 = `67`，只占 432 机会中的 `15.5%`
- 影响：
  - “是否进入事件决策”本身成为主导变量，掩盖事件概率模型本身效果。
- 改进方向：
  - 放宽 `_is_digital_interaction_context` 触发条件，或对“中性语境”引入低概率试探。
  - 对 `scenario_skip` 做分原因统计（非数字场景/缺字段/语义不明）后逐项收窄。

3) hybrid 模式在本次运行中等价于“LLM未生效”  
- 证据：
  - `step.llm_query_success_count` 总和 = `0`
  - `step.llm_parse_fail_count` 总和 = `67`（与 attempt 数一致）
  - `step.rule_fallback_count` 总和 = `67`
  - 唯一触发事件记录中 `fallback_reason=llm_parse_failed`、`llm_status=llm_parse_failed`
- 影响：
  - 名义上是 hybrid，实际全量退回规则分支，无法评估 LLM 决策增益。
- 改进方向：
  - 优先修 LLM 输出协议（强约束 JSON schema + 失败重试 + 容错字段映射）。
  - 增加“原始回复样本存档”与“解析失败分类”便于定位失败类型。

4) 事件分布明显偏斜，公平性不足  
- 证据：
  - 唯一事件只发生在 `agent_id=1`，其他 5 个 agent 全 0
  - `step.agent_event_count_max` 最大为 1，`step.agent_event_count_min` 恒为 0
- 影响：
  - 个体差异会被单一 agent 噪声放大，结果不具备群体代表性。
- 改进方向：
  - 增加“每 agent 最低事件覆盖”机制（例如每阶段至少一次候选尝试）。
  - 保持随机性同时加公平约束，避免同一 agent 被重复命中。

### P1（会显著影响解释质量）

5) 阶段差异信号弱，核心指标缺少可解释变化  
- 证据：
  - `step.helplessness_avg` 三阶段均为 `40.5203`（几乎完全平）
  - `step.negative_event_avg` 仅 day=1 为 `0.1667`，day=2/3 均为 `0`
- 影响：
  - 难以支撑“steady→shock→recovery”因果叙事，统计检验空间不足。
- 改进方向：
  - 提升 stage2/stage3 的有效事件样本，再观察 helplessness/trust 的阶段漂移。
  - 设定阶段最小事件量阈值，未达阈值时标记“该阶段结果不可解释”。

6) `scenario_alignment_rate` 聚合口径会低估真实对齐  
- 证据：
  - 全 step 平均 `0.5833`
  - 但仅在“有尝试的 step”上平均为 `1.0`
  - 30 个零尝试 step 被按 0 计入平均
- 影响：
  - 指标看起来像“语义对齐一般”，实际是“很多 step 根本没进入判定”。
- 改进方向：
  - 统一改为“条件平均”（仅 attempt>0 时统计）并单独报告覆盖率。

7) 移动行为成效无法评估，关键字段未入库  
- 证据：
  - `agent_status.status` 中未发现 `num_completed_trips` / `total_travel_distance` / `total_travel_time` 字段（均缺失）
  - 当前无法从本次结果直接判断 mobility nudge 是否有效
- 影响：
  - “是否真的改善了出行活跃度”无法量化验证。
- 改进方向：
  - 在 `log_step_status` 明确写入 trip/distance/time 三个指标并加 step 级 metric。
  - 增加 `step.mobility_nudge_sent_count`、`step.mobility_nudge_effective_count`。

### P2（成本与观测层面）

8) LLM 资源投入与有效事件产出不匹配  
- 证据：
  - 终端日志末尾 `LLM request count: 2286`
  - `experiment_info.yaml` 记录 `input_tokens=838467`、`output_tokens=129763`
  - 但事件产出仅 1 条
- 影响：
  - 成本高、实验迭代慢，且信号密度低。
- 改进方向：
  - 对“会被 skip 的样本”前置裁剪，避免无效 LLM 调用。
  - 增加按 agent/step 的 LLM 调用预算与早停策略。

### 本次实验中“表现正常”的点（用于区分问题边界）

- 冒烟强制注入未污染正式实验：`step.smoke_forced_event` 总和 = `0`。
- 问卷回写链路可用：`agent_survey` 共 `24` 行，`mvp_status` 三个核心字段（helplessness/trust/avoidance）均完整落表。
- stage 标签正常：仅出现 `baseline_low_friction:{steady,shock,recovery}`，无 `unknown`。

## 2026-02-27 第一轮改造（P0 修复包）

文件：`examples/digital_friction_mvp/main.py`

### A. 提高事件覆盖率（修复“几乎都 skip”）

- 改造点：
  - 新增“非数字语境低概率探索”参数：`NON_DIGITAL_EXPLORATORY_DAILY_PROB`（默认 `0.06`）
  - 新增“每阶段每个 agent 最低决策尝试次数”参数：`EVENT_MIN_STAGE_DECISION_ATTEMPTS`（默认 `2`）
  - `_fallback_scenario_from_context` 支持 `allow_non_digital=True`，并补充 `need/step_type` 兜底映射
- 结果：
  - 不再只有“数字语境 + 随机命中”才有机会进入事件判定；
  - 每个 agent 在每个阶段至少会被拉起一定次数的决策尝试（公平性与覆盖率同步提升）。

### B. 增强公平性（修复“事件集中在个别 agent”）

- 改造点：
  - 新增阶段内追踪器：
    - `_STAGE_DECISION_ATTEMPT_TRACKER`
    - `_STAGE_EVENT_EMIT_TRACKER`
  - 新增过曝抑制参数：
    - `EVENT_OVEREXPOSED_GAP`（默认 `1`）
    - `EVENT_OVEREXPOSED_SCALE`（默认 `0.65`）
  - 当某 agent 的阶段事件数显著高于最小值时，自动下调其本 step 事件概率
- 结果：
  - 减少“同一 agent 连续吃到事件”的偏斜，提升群体层面的可解释性。

### C. 提升 hybrid 可用性（修复“LLM 全部 parse_failed”）

- 改造点：
  - `_extract_json_object` 增强：
    - 支持代码块清洗、智能引号、`ast.literal_eval`、首个平衡花括号抽取
  - 新增 `_extract_llm_suggestion_from_text`，支持半结构化文本直接提取 multiplier/confidence
  - `_query_llm_event_suggestion` 升级为：
    - 主请求失败分类（`request_error`）
    - 解析失败后可选“修复重试”请求（`LLM_DECIDER_PARSE_REPAIR_ENABLED=1`）
    - 返回实际 API 调用次数，主流程按真实调用扣减预算
  - 新增参数：
    - `LLM_DECIDER_PARSE_REPAIR_ENABLED`（默认开启）
    - `LLM_DECIDER_PARSE_REPAIR_TIMEOUT`（默认 `8`）
- 结果：
  - hybrid 不再轻易退化成纯 rule fallback；
  - LLM 预算统计更真实，便于控制成本与复现实验。

### D. 增强可观测性（nudge 与 mobility）

- 改造点：
  - `nudge_mobility_if_stuck` 新增 step 级指标：
    - `step.mobility_nudge_window_active`
    - `step.mobility_nudge_candidate_count`
    - `step.mobility_nudge_random_hit_count`
    - `step.mobility_nudge_sent_count`
    - `step.mobility_nudge_sent_rate`
  - `log_step_status` 新增状态落盘与指标：
    - `num_completed_trips`
    - `total_travel_distance`
    - `total_travel_time`
    - `step.num_completed_trips_avg`
    - `step.total_travel_distance_avg`
    - `step.total_travel_time_avg`
- 结果：
  - 现在可以直接判断“是否真的 nudged 成功、是否真的动起来”。

### E. 新增审计与诊断指标

- 事件侧新增 step 指标：
  - `step.decision_coverage_rate`
  - `step.llm_repair_success_count`
  - `step.llm_budget_exhausted_count`
  - `step.llm_calls_this_step`
  - `step.scenario_forced_min_attempt_count`
  - `step.scenario_exploratory_count`
  - `step.fairness_downscaled_count`
- 单事件审计新增字段：
  - `scenario_entry_reason`
  - `stage_attempt_count_before`
  - `stage_event_count_before`
  - `fairness_downscaled`

### F. 本轮校验

- 语法检查通过：
  - `python -m py_compile examples/digital_friction_mvp/main.py`

## 2026-02-27 第一轮改造后实验复盘（exp_id=3b7739ee-95e7-469f-b2ff-4f1473c5ee22）

### 运行状态确认

- 本次实验完成状态正常，不是失败中断：
  - `status = 2`
  - `error = ''`
  - 位置：`agentsociety_data/exps/3b7739ee-95e7-469f-b2ff-4f1473c5ee22/experiment_info.yaml`
- 终端尾部 `CancelledError` 为 gRPC 关闭阶段常见噪声，不影响结果落盘。

### P0 对照结果（未达标项）

1) `P0-事件覆盖率`：仍未达标（仅部分改善）  
- 指标：
  - 决策尝试：`102 / 432 = 23.61%`（上次 `15.5%`）
  - skip 率：`330 / 432 = 76.39%`
  - 事件触发率：`2 / 432 = 0.463%`
  - stage 分布：`stage1=1, stage2=1, stage3=0`
- 结论：
  - 仍远低于可分析事件密度，恢复期没有事件样本。

2) `P0-hybrid 真正生效`：仍未达标（核心未解决）  
- 指标：
  - `llm_parse_fail_count = 0`（格式解析问题已修复）
  - `hybrid_applied_count = 0`
  - `rule_fallback_count = 102`
- 审计证据（单事件）：
  - `llm_status = ok_repaired`
  - `llm_confidence = 0.0`
  - `fallback_reason = low_confidence`
  - 位置：`agentsociety_data/exps/3b7739ee-95e7-469f-b2ff-4f1473c5ee22/artifacts.json:45`
  - 位置：`agentsociety_data/exps/3b7739ee-95e7-469f-b2ff-4f1473c5ee22/artifacts.json:59`
  - 位置：`agentsociety_data/exps/3b7739ee-95e7-469f-b2ff-4f1473c5ee22/artifacts.json:126`
  - 位置：`agentsociety_data/exps/3b7739ee-95e7-469f-b2ff-4f1473c5ee22/artifacts.json:140`
- 结论：
  - 当前是“可解析但低置信”，因此融合权重为 0，整体仍退回 rule。

3) `P0-公平性`：仍未达标  
- 指标：
  - 事件只出现在 agent `1` 和 `5`，其余 `4` 人为 `0`
  - `fairness_downscaled_count = 0`
- 结论：
  - 由于事件总量仍太低，公平性抑制机制几乎没有触发机会。

### 已改善项（本轮有效）

- LLM 解析鲁棒性显著改善：
  - `llm_parse_fail_count: 67 -> 0`
- 决策入口有所提升：
  - `decision_attempt_count: 67 -> 102`
  - `scenario_skip_count: 365 -> 330`

### 额外观察（非 P0，但要继续跟踪）

- mobility 观测链路已打通，但行为转化仍为 0：
  - `num_completed_trips_avg = 0`
  - `total_travel_distance_avg = 0`
  - `total_travel_time_avg = 0`
- `nudge` 有触发：
  - `mobility_nudge_sent_count` 总和 = `9`
  - 但未转化为可观测出行完成量。

## 2026-02-27 讨论结论补记（针对 hybrid 不生效）

### 1) 现象复述（达成共识）

- 当前核心问题不是“LLM 没返回”，而是“返回内容在融合门槛下不可用”。
- 典型链路：
  - `llm_status = ok_repaired`
  - `llm_confidence = 0.0`
  - `fallback_reason = low_confidence`
  - 最终 `source = rule_fallback`，`hybrid_applied_count = 0`

### 2) 为什么会出现“parse_fail=0 但 hybrid=0”

- 第一层（格式层）已修复成功：
  - `llm_parse_fail_count = 0`
- 第二层（语义可信层）仍失败：
  - 融合要求 `confidence >= LLM_DECIDER_MIN_CONFIDENCE`（当前阈值 0.35）
  - 但大量 repaired 结果给出 `confidence=0.0`
  - 因此 `alpha=0`，全量回退 `rule_fallback`

### 3) 为什么 repair 触发频率这么高

- 本次实验数据：
  - `decision_attempt_count = 102`
  - `llm_cache_hit_count = 4`
  - `llm_repair_success_count = 98`
  - 等价于：非缓存查询 98 次几乎全部走 repair
- 讨论后确认的主要原因：
  1. 主提示词对输出格式约束偏软（“Return JSON only”不足以稳定约束模型）
  2. 主调用可返回解释性文本，第一层解析器难以直接命中
  3. repair 逻辑是“解析失败即进入”，导致 repair 成为常规路径而非异常路径

### 4) 讨论后的方向（下一轮优先）

- 采用“硬 JSON 契约”：
  - 明确固定字段、固定类型、固定范围
  - 明确禁止 markdown/code fence/额外解释文本
  - 提供单一合法示例 JSON
- 程序端增加 schema 校验（语义与格式双校验）：
  - 仅“可解析”不等于“可用”
  - 区分 `raw_parse_ok`、`schema_ok`、`repair_used`
- 目标：
  - 降低 repair 触发率
  - 避免 repaired 结果天然落到 `confidence=0.0`
  - 让 `hybrid_applied_count` 从 0 提升到可观测区间

## 2026-02-27 硬 JSON Prompt 落地（第二轮）

文件：`examples/digital_friction_mvp/main.py`

### 改动内容

1) 主 LLM 调用 Prompt 升级为硬约束格式  
- 由“Return JSON only”软提示，升级为明确的硬规则：
  - 只能返回一个 JSON 对象
  - 只能包含固定 6 个键：
    - `risk_mult`
    - `protect_mult`
    - `neg_impact_mult`
    - `pos_impact_mult`
    - `confidence`
    - `reason`
  - 明确值域、类型、禁止 markdown/解释文本
  - 加入合法 JSON 示例作为 schema 参照

2) repair Prompt 升级  
- 由“缺失时 confidence=0.0”改为：
  - 先基于原始输出推断保守值
  - `confidence` 必须非空
  - 仅在“无可用证据”时才允许 `confidence=0`

3) 清洗函数调用联动  
- 主路径 `ok` 调用：
  - `_sanitize_llm_suggestion(..., source_status="ok")`
- 修复路径 `ok_repaired` 调用：
  - `_sanitize_llm_suggestion(..., source_status="ok_repaired")`
- 作用：
  - 让清洗层可基于来源状态做差异化处理，避免 repaired 输出天然被当作“原始高质量输出”或“默认 0 信心”。

### 预期效果

- 提高原始输出的结构化成功率，降低 repair 触发率。
- 降低 repaired 样本中“默认 0 信心”占比。
- 给 `hybrid_applied_count` 提供从 0 上升的机会（配合后续实验验证）。

### 追加修正（同轮补丁）

1) 提高 LLM 输出 token 上限（缓解截断）  
- 主请求：
  - `max_tokens: 220 -> 320`
- repair 请求：
  - `max_tokens: 180 -> 220`
- 目的：
  - 降低“回答稍长即被截断 -> 进入 repair”的概率。

2) 扩展兜底文本抽取规则（中英文/同义映射）  
- `_extract_llm_suggestion_from_text`：
  - 增加中文关键词匹配：
    - 风险倍率/保护倍率/负面影响倍率/正面影响倍率/置信度/信心/把握度
  - `reason` 扩展到：
    - `reason/rationale/原因/理由/依据/说明`
- `_sanitize_llm_suggestion`：
  - 增加字段别名标准化映射，支持：
    - 中英文字段名混用
    - 大小写、下划线、连字符、空格差异
  - 作用：
    - 即使模型返回中文键或同义键，也能归一化为标准字段。

## 2026-02-27 晚间复盘补记（exp_id=eed4971a-6ddd-4454-bf88-5946cb54030d）

### 运行状态确认

- 实验成功完成（非异常中断）：
  - `status = 2`
  - `error = ''`
  - 位置：`agentsociety_data/exps/eed4971a-6ddd-4454-bf88-5946cb54030d/experiment_info.yaml`
- 尾部 `CancelledError2` 仍为 gRPC 关闭噪声，不影响结果有效性。

### 本次关键结论（对照上一轮）

1) `P0-hybrid 真正生效`：本轮已明显改善  
- 指标：
  - `hybrid_applied_count = 80`
  - `rule_fallback_count = 0`
  - `llm_parse_fail_count = 0`
  - `llm_repair_success_count = 0`
- 结论：
  - 本轮已不是“全量 fallback”，hybrid 决策链路真正跑通。

2) `P0-事件覆盖率`：仍未达标，且较上一轮回落  
- 指标（本轮）：
  - 决策尝试：`80 / 432 = 18.52%`
  - skip：`352 / 432 = 81.48%`
  - 事件触发：`1 / 432 = 0.231%`
- 对比（上一轮 `3b7739ee...`）：
  - `23.61% -> 18.52%`（覆盖率下降）
- 结论：
  - 事件样本依然不足，阶段对比解释力偏弱。

3) `P0-公平性`：仍未达标  
- 指标：
  - 事件仅命中 1 个 agent（其余为 0）
  - `fairness_downscaled_count = 0`
- 结论：
  - 低事件基数下，“过曝下调”几乎无触发机会。

4) `P1-mobility 转化`：仍未达标  
- 指标：
  - `num_completed_trips_avg = 0`
  - `total_travel_distance_avg = 0`
  - `total_travel_time_avg = 0`
  - `mobility_nudge_sent_count` 有值但未形成可观测出行转化。
- 结论：
  - nudge 已触发，但行为链路没有稳定转化。

### 新增根因判断（本轮补充）

1) 场景匹配入口仍偏窄（高优先）  
- 现象：
  - 大量 step 卡在 `scenario_skip`，未进入事件判定。
- 判断：
  - 当前“关键词匹配 + fallback 小概率”入口对真实意图文本覆盖仍不足；尤其当 intention 文本较生活化/抽象时，更容易失配。
  - `RANDOM_SCENARIO_FALLBACK_DAILY_PROB` 与 `NON_DIGITAL_EXPLORATORY_DAILY_PROB` 经“日->小时”缩放后，实际命中偏低，进一步放大了入口偏窄问题。
- 影响：
  - 决策覆盖率直接受限，后续 hybrid/fairness/mobility 都缺样本。

2) 概率链路存在“双重稀释”  
- 先在入口环节低概率触发 fallback；
- 进入决策后又将事件概率按 interval 缩放；
- 导致“可尝试样本少 + 可触发样本更少”叠加。

3) 公平机制仍是“抑制过曝”，缺“提升低曝”  
- 当前只会下调高曝光 agent，没有对低曝光 agent 的补偿提升；
- 在低事件密度条件下几乎不生效。

4) mobility 仍缺闭环成功判定  
- 当前 nudge 主要修改 `need/intention`；
- 但缺少“从意图到实际 mobility 完成”的强约束或校验链路。

### 下轮优先事项（保持最小改动）

1) 扩展场景匹配词表与同义归一（中英混合）并增加“意图模板映射”。
2) 提升入口覆盖（适度提高非数字探索与 fallback 触发率，减少极端 skip）。
3) 增加“阶段最少事件数”保障（不仅是最少尝试次数）。
4) 公平机制补充“低曝光 boost”分支。
5) mobility 增加“nudge->实际出行完成”闭环指标与最小行为保障。

## 2026-02-27 方案讨论补记（A vs B）

### 定义

- 方案 A（当前实现）：
  - `STEP` 先执行 agent 行为；
  - `trigger_event_shocks` 在 step 后统一判定并注入摩擦/润滑事件。
- 方案 B（讨论中的内生方案）：
  - 在 agent 的 `forward/block` 内部直接判断并处理摩擦/润滑事件。

### 对比结论（概要）

1) 可解释性与实验可比性  
- A 更优：
  - 行为与干预分离，因果链条更清晰，便于 A/B 对照与复现实验。
- B 较弱：
  - 行为与干预耦合，后验解释“是行为变化还是干预变化”更困难。

2) 全局约束能力（公平性/预算/覆盖率）  
- A 更优：
  - 可在单一函数集中控制跨 agent 的预算、公平性和覆盖率指标。
- B 较弱：
  - 分散到 agent 内后，全局约束难统一，跨 agent 调度复杂度上升。

3) 工程复杂度与风险  
- A 更优：
  - 改动集中，迭代快，回归风险相对可控。
- B 较弱：
  - 需要改动多个 block/生命周期逻辑，耦合面更大，调试成本更高。

4) 行为内生性与“真实感”  
- B 更优：
  - 事件可在行为过程中即时影响决策，内生性更强。
- A 略弱：
  - 事件是 step 后注入，更像“实验层外部反馈”。

5) 成本与稳定性  
- A 更可控：
  - 可通过本地规则先筛选，减少 LLM 调用；
  - 但若入口偏窄会造成 `scenario_skip` 偏高。
- B 视实现而定：
  - 若每步都走 LLM，成本和不稳定性可能显著上升。

### 当前阶段建议

- 短期（P0 未达标阶段）：
  - 继续采用 A，优先修复覆盖率、公平性、mobility 转化。
- 中期（P0 达标后）：
  - 采用 A+B 折中：
    - 在 STEP 内只产出“摩擦信号”特征；
    - 仍由 `trigger_event_shocks` 统一裁决、审计与全局约束。

## 2026-02-27 P0 第三轮改造（覆盖率/公平性/mobility 闭环）

文件：`examples/digital_friction_mvp/main.py`

### 1) 覆盖率改造（场景入口增强）

- 入口概率新增“每小时保底”参数：
  - `EVENT_FALLBACK_INTERVAL_PROB_FLOOR`（默认 `0.02`）
  - `EVENT_EXPLORATORY_INTERVAL_PROB_FLOOR`（默认 `0.008`）
- fallback/exploration 的实际概率改为：
  - `max(日->小时换算值, 每小时保底值)`
- 增加 `preferred_step_type_direct` 直达入口：
  - 当 `step_type` 已明确映射到场景且语境可信时，直接进入场景，不再完全依赖关键词命中。
- `_match_scenario` 放宽：
  - 不再因为 `intention=planning/空` 立刻返回 `None`；
  - 允许继续使用 `step_intention/step_type` 做匹配。
- 调整默认阶段最小尝试：
  - `EVENT_MIN_STAGE_DECISION_ATTEMPTS: 2 -> 4`

### 2) 公平性改造（新增低曝光 boost）

- 保留原有“过曝下调”：
  - `EVENT_OVEREXPOSED_*`
- 新增“低曝光提升”：
  - `EVENT_UNDEREXPOSED_GAP`（默认 `1`）
  - `EVENT_UNDEREXPOSED_SCALE`（默认 `1.25`）
- 机制：
  - 当某 agent 阶段事件数显著低于当前高曝光者时，适度放大其本 step 事件概率（非强制命中）。
- 新增审计与指标：
  - `decision.fairness_boosted`
  - `step.fairness_boosted_count`

### 3) mobility 闭环指标改造（从 sent 到 effective）

- `nudge_mobility_if_stuck` 增强：
  - 记录 nudge 基线快照：
    - `mobility_nudge_baseline_trips`
    - `mobility_nudge_baseline_distance`
    - `mobility_nudge_baseline_time`
  - 记录 pending 状态与发送时刻：
    - `mobility_nudge_pending`
    - `mobility_nudge_sent_day`
    - `mobility_nudge_sent_t`
  - 新增指标：
    - `step.mobility_nudge_accepted_count`
    - `step.mobility_nudge_accepted_rate`
- `trigger_event_shocks` 增强闭环追踪：
  - 检测 pending nudge 是否进入 mobility-like 行为；
  - 计算并累计：
    - `trip/distance/time` 增量
  - 新增指标：
    - `step.mobility_nudge_pending_count`
    - `step.mobility_nudge_executed_count`
    - `step.mobility_nudge_effective_count`
    - `step.mobility_nudge_expired_count`
    - `step.mobility_nudge_trip_delta_sum`
    - `step.mobility_nudge_distance_delta_sum`
    - `step.mobility_nudge_time_delta_sum`
  - 新增超时参数：
    - `MOBILITY_NUDGE_PENDING_MAX_HOURS`（默认 `6`）

### 4) 本轮状态

- 语法检查通过：
  - `python -m py_compile examples/digital_friction_mvp/main.py`
- 下一步：
  - 运行 3 天回归实验，对比 `decision_attempt_count / scenario_skip_count / fairness_boosted_count / mobility_nudge_effective_count`。

## 2026-02-27 P0 第四轮改造（阶段最少事件保障 + skip 拆解）

文件：`examples/digital_friction_mvp/main.py`

### 1) 新增“每阶段最少事件数”保障（补齐此前仅保尝试次数的缺口）

- 新增参数：
  - `EVENT_MIN_STAGE_EVENT_EMITS`（默认 `2`）
  - `EVENT_MIN_STAGE_EVENT_ENFORCE_PROGRESS`（默认 `0.75`）
  - `EVENT_MIN_STAGE_EVENT_FORCE_TOTAL_PROB`（默认 `0.70`）
- 新增阶段索引映射：
  - `_STAGE_NAME_TO_INDEX`（用于根据 `stage_name` 推断阶段进度）。
- 在 `trigger_event_shocks` 内新增保障逻辑：
  - 当阶段进度超过阈值、当前阶段累计事件仍低于目标、且 agent 属于低曝光层时，
    对该 agent 的事件总概率做保底提升，并启用强制 roll 保障命中。
- 新增审计字段：
  - `decision.stage_progress`
  - `decision.stage_min_event_gap_before`
  - `decision.stage_min_event_forced`
  - `decision.stage_min_event_forced_roll`
- 新增 step 指标：
  - `step.stage_progress`
  - `step.stage_min_event_emit_target`
  - `step.stage_min_event_force_count`

### 2) 公平性低曝光 boost 判定修正（提升低事件场景触发机会）

- 原条件（过严）：
  - `stage_event_count + gap < max_stage_event_count`
- 新条件（更直观）：
  - `(max_stage_event_count - stage_event_count) >= EVENT_UNDEREXPOSED_GAP`
- 影响：
  - 当 `max=1, current=0` 且 `gap=1` 时，低曝光 boost 可以触发；
  - 修复了“低事件密度下 boost 基本不触发”的问题。

### 3) skip 原因拆解（便于后续精准调参）

- 新增统计：
  - `scenario_pre_match_miss_count`（初始场景匹配失败）
  - `scenario_skip_fallback_not_triggered_count`（fallback 未触发导致跳过）
  - `scenario_skip_fallback_failed_count`（fallback 触发后仍无场景）
- 新增 step 指标：
  - `step.scenario_pre_match_miss_count`
  - `step.scenario_skip_fallback_not_triggered_count`
  - `step.scenario_skip_fallback_failed_count`
- 作用：
  - 后续可区分是“词表/匹配问题”还是“概率门限问题”，避免盲目加大总概率。

### 4) 兼容性修正

- 将 `smoke_forced_event` 与“阶段最少事件强制命中”拆分：
  - 仅 smoke 分支会计入 `smoke_forced_event`；
  - 避免把阶段保障误记成 smoke 命中。

### 5) 本轮状态

- 代码已完成，待你跑下一轮 3 天回归实验验证：
  - 覆盖率：`decision_attempt_count`、`scenario_skip_count`、新增三类 skip 拆解指标
  - 阶段保障：`stage_min_event_force_count`、`stage_min_event_emit_target`
  - 公平性：`fairness_boosted_count`、`agent_event_count_min/max/std`

## 2026-02-27 P0 第五轮改造（场景扩展：医疗/政务）

文件：`examples/digital_friction_mvp/main.py`

### 1) 新增两个高频数字摩擦场景

- `medical_appointment`（挂号/缴费/就诊链路）
- `gov_service`（政务办事/实名核验/材料上传链路）

新增位置：
- `EVENT_SCENARIOS`
- 兼顾 `negative/positive` 两类提示文本，保持与原场景结构一致。

### 2) 扩展场景入口映射

- `INTENTION_SCENARIO_MAP` 新增中英关键词：
  - 医疗：`hospital/clinic/appointment/医院/挂号/就诊/医保...`
  - 政务：`government/certificate/document/政务/办事/材料/实名认证...`
- `_STEP_TYPE_SCENARIO_MAP` 新增：
  - `medical/health -> medical_appointment`
  - `gov/government/public -> gov_service`
- `_fallback_scenario_from_context` 新增医疗/政务上下文路由与 `need` 路由。

### 3) 正向过程信号兼容更新

- `_infer_positive_process_signals` 的 `intercepted` 场景集合扩展为：
  - `medical_appointment`
  - `gov_service`
- 风险关键词补充：`实名/核验/挂号/就诊/政务`，避免新场景被低估。

### 4) 预期收益

- 提升“生活化真实行为文本 -> 可匹配场景”的覆盖面；
- 减少高频医疗/政务行为被误归到 `login_captcha` 或直接 `skip` 的情况；
- 为后续公平性和事件密度提升提供更多可触发入口。

## 2026-02-28 实验复盘（digital_friction_p0_r4_20260228_011256）

实验目录：`agentsociety_data/exps/8877dbcd-4892-481a-a0a7-ece13b18ca7b`  
实验状态：成功完成（`status=2`，`error=''`）  
结尾 `CancelledError` 仍为环境关闭时的 gRPC 尾部噪声，不构成实验失败。

### 1) 本次结果（按 P0/P1 口径）

- 总机会数：`6 agents × 72 steps = 432`
- 决策尝试：`decision_attempt_count=126`（覆盖率 `29.17%`）
- 跳过：`scenario_skip_count=306`（`70.83%`）
- 事件触发：`event_emitted_count=7`（触发率 `1.62%`）
- hybrid 生效：`hybrid_applied_count=126`、`rule_fallback_count=0`
- LLM 稳定性：`llm_parse_fail_count=0`、`llm_query_success_count=123`、`llm_repair_success_count=0`
- 公平性：事件分布（按 agent）=`2,1,0,2,1,1`，较前轮显著改善，但仍有 1 人为 0
- mobility 闭环：`mobility_nudge_sent_count=18`，但 `executed=0`、`effective=0`、`trip/distance/time delta=0`

### 2) 与上一轮（eed4971a...）对比

- 决策尝试：`80 -> 126`（+46）
- 跳过：`352 -> 306`（-46）
- 事件触发：`1 -> 7`（+6）
- hybrid：持续稳定，仍为“全量 hybrid，不回退 rule”
- 公平性：从“极端集中”转向“多数 agent 有事件”，但未实现全员覆盖
- mobility 转化：仍无实质进展（sent 有了，executed/effective 仍 0）

### 3) 仍未解决的问题（核心）

1. `P0-事件覆盖率`：未达标  
   - 虽然覆盖率提升到 29.17%，但仍有 70.83% 的机会点被 skip。
2. `P0-公平性`：部分未达标  
   - 分布改善明显，但仍存在 `0` 事件 agent。
3. `P1-mobility 转化`：未达标  
   - nudge 发出后没有形成“执行/有效”的闭环行为证据。

### 4) 为什么“决策尝试率还行”，但“触发率仍低”

这是两层概率门叠加导致的正常现象，不是单点 bug：

1. 第一层门：是否进入决策尝试  
   - 本次已有改进（`126/432`），但仍有大量机会没进决策（`skip=306`）。

2. 第二层门：进入决策后是否真的触发事件  
   - 事件触发条件是：`roll < p_negative_interval + p_positive_interval`。
   - 这里用的是“interval 概率”（小时级），不是 daily 概率；daily 经过换算后会显著变小。
   - 从审计样本看，许多 case 的 `p_negative_interval + p_positive_interval` 只有约 `0.02~0.04` 量级。
   - 这意味着即使进入了 126 次决策，随机命中期望也不会高（本次触发 7 次里还有一部分是阶段保障强制命中）。

3. 阶段最少事件保障尚未成为主流触发路径  
   - `stage_min_event_force_count=4`，说明目前“硬保障”只在少量时刻启动；
   - 大部分 case 仍依赖自然随机命中。

### 5) 代码与指标侧根因定位

- 场景前匹配 miss 仍高：`scenario_pre_match_miss_count=366`
- skip 主因是 fallback 未触发：`scenario_skip_fallback_not_triggered_count=306`（而不是 fallback 失败）
- 公平性 boost 已触发（`fairness_boosted_count=45`），但在低密度总事件下仍不足以保证全员命中
- mobility pending 有积压（`mobility_nudge_pending_count=113`）且超时清理（`expired=12`），说明“发提醒 -> 进入 mobility-like 行为”这一步卡住

### 6) 下一步改进方向（按优先级）

1. 覆盖率优先（P0）
   - 继续提升 fallback 触发强度（概率或 floor），优先降低 `fallback_not_triggered`；
   - 继续扩充前匹配词表与 step_type 映射，压低 `pre_match_miss_count`。

2. 触发率优先（P0）
   - 适度提高“非强制 case”的 interval 总概率下限（或分场景下限）；
   - 在阶段后段对低曝光 agent 提前启动最少事件保障，减少“有尝试无触发”。

3. 公平性收口（P0）
   - 增加“阶段末尾零事件 agent”的定向保底策略（仍保持概率式，不做硬指派）。

4. mobility 闭环打通（P1）
   - 放宽 mobility-like 执行判定关键词和步态信号；
   - 增加“nudge 后 N 步内是否出现可观测出行增量”的专门统计，以区分“行为没发生”与“判定没识别”。

## 2026-02-28 行为合理性复盘（long 视图）与画像驱动初步方案（仅讨论，未改代码）

数据来源：
- `examples/digital_friction_mvp/analysis/step_actions_8877_long.csv`
- `examples/digital_friction_mvp/analysis/step_actions_8877_wide.csv`
- 审计脚本：`examples/digital_friction_mvp/analysis/audit_behavior_fit.py`
- 审计报告：`examples/digital_friction_mvp/analysis/behavior_audit_8877.md`

### 1) long 视图行为合理性结论

1. 结构完整性较好  
   - `432` 条行为记录（`72 step × 6 agent`），每个 step 均为 `6` 条记录，时间步长基本稳定（每步约 1 小时）。

2. 日常生活链条基本合理  
   - 主要行为集中在 `meal_cooking` 与 `sleep_rest`，存在“做饭/用餐/清理/休息/睡眠”可解释链条；
   - 核心 agent 相邻 step 动作重复率较低，未见严重“动作卡死循环”。

3. 与“数字摩擦实验”目标匹配偏低  
   - 数字动作仅 `1` 条，含数字动作 step 仅 `1/72 = 1.39%`；
   - mobility step 也较低（`5/72 = 6.94%`）；
   - 审计评分约 `4/10`（低）。

4. 数据追踪存在轻微一致性风险  
   - 发现核心 ID 与额外 ID 的替换步数 `7`（行为不断裂，但会影响按个体纵向统计的稳定性）。

### 2) 为什么任务匹配会低（共识）

- 当前行为供给以“线下日常生活”任务为主，数字任务在上游生成阶段占比偏小；
- 选择层没有对“数字路径”形成足够稳定的偏置（更多是自然涌现）；
- 识别层对“数字行为信号”仍可能漏检（若只看 action 短句，容易丢失 status/intention 中的信息）。

### 3) 初步改进想法（你已确认方向：供给层 + 选择层 + 识别层）

> 说明：以下为讨论方案，当前未实施代码修改。

1. 供给层（提高数字任务供给）
   - 不仅依赖自然涌现；在 stage 起点与每日早晨给每个 agent 提供 `1~2` 个“硬数字任务候选”；
   - 场景优先：线上挂号/政务上传/线上缴费/登录验证/网约车；
   - 用“候选任务池”而非“强制执行”，保持行为自然性。

2. 选择层（提升数字路径被选中概率）
   - 在 step 规划中加入轻量偏置：满足健康/办事/支付需求时，优先考虑数字路径；
   - 保留线下选项，但对数字路径给出“步骤清晰/省时/可回退”描述，降低放弃率。

3. 识别层（减少数字暴露漏检）
   - 数字暴露判定从单一 `action` 扩展到 `action + status + intention + step_signal` 联合判定；
   - 增补中文同义词与生活化表达（如：挂号、上传材料、实名核验、扫码、缴费、认证、进度查询）。

### 4) 画像驱动的可执行思路（讨论版）

基于当前 6 个 agent 的画像差异（数字熟练度、风险敏感性、求助倾向）可分层：
- 高数字组：增加任务复杂度（挂号+缴费、政务+认证），提升真实数字摩擦暴露；
- 中数字组：以“单页可完成 + 低跳转”任务为主，逐步提高复杂度；
- 低数字组：先给低门槛数字任务（查询/确认/通知），再引入支付与多步验证。

目标是“同样提高数字暴露率，但保留个体差异”，避免所有 agent 被同质化驱动。

### 5) 下一步验证口径（讨论确定）

- 目标区间：含数字动作 step 从 `1.39%` 提升到 `10%~15%`；
- 联动观察：
  - `decision_attempt_count` 是否继续上升；
  - `scenario_pre_match_miss_count` 与 `scenario_skip_fallback_not_triggered_count` 是否下降；
  - 事件分布是否更均衡（避免再次集中于少数 agent）。

## 2026-02-28 P0 第六轮（第0步）改造：数字暴露识别层增强

文件：`examples/digital_friction_mvp/main.py`

### 1) 联合数字暴露判定（多源）

- 新增 `_detect_digital_exposure`：
  - 联合 `step_intention(action)`、`step_eval_text/status`、`intention+need`、`step_signal(step_type/effort)` 四类来源做判定；
  - 返回结构化来源标记：
    - `is_digital`
    - `from_action`
    - `from_status`
    - `from_intention`
    - `from_signal`
- `_is_digital_interaction_context` 改为复用该函数，不再仅靠单一拼接文本判断。

### 2) 词表扩展（中英混合）

- 在 `_DIGITAL_CONTEXT_TOKENS` 中补充数字摩擦常见表达：
  - 中文：`线上/网上/小程序/认证/核验/实名/上传材料/挂号/预约/办事/缴费/电子支付` 等；
  - 英文：`portal/platform/verification/authenticate/upload/miniprogram` 等。

### 3) 新增 step 级可观测指标

- 新增并写入数据库指标：
  - `step.digital_exposure_count`
  - `step.digital_exposure_from_action_count`
  - `step.digital_exposure_from_status_count`
  - `step.digital_exposure_from_intention_count`
  - `step.digital_exposure_from_signal_count`
- 同步在事件审计 `decision_audit` 中记录同名布尔标记，便于逐事件排查漏检来源。

### 4) 状态

- 语法检查通过：
  - `python -m py_compile examples/digital_friction_mvp/main.py`
- 说明：
  - 本轮仅做识别层增强，未改供给层/选择层逻辑与参数。

## 2026-02-28 P0 第六轮（第1步）改造：供给层（数字任务自然出现）

文件：`examples/digital_friction_mvp/main.py`

### 1) 新增数字任务供给配置（env）

- `DIGITAL_SUPPLY_ENABLED`
- `DIGITAL_SUPPLY_DAILY_TASKS_PER_AGENT`
- `DIGITAL_SUPPLY_MAX_QUEUE`
- `DIGITAL_SUPPLY_SURFACE_PROB`
- `DIGITAL_SUPPLY_SURFACE_IDLE_ONLY`
- `DIGITAL_SUPPLY_CARRYOVER_ENABLED`
- `DIGITAL_SUPPLY_PENDING_MAX_HOURS`
- `DIGITAL_SUPPLY_MORNING_START_HOUR / DIGITAL_SUPPLY_MORNING_END_HOUR`
- `DIGITAL_SUPPLY_EVENING_START_HOUR / DIGITAL_SUPPLY_EVENING_END_HOUR`

### 2) 新增数字任务池与队列工具

- 任务池 `DIGITAL_SUPPLY_TASK_CATALOG`：
  - 医疗挂号、政务上传、线上缴费、登录核验、网约车预约。
- 新增队列函数：
  - `_decode_digital_todo_queue`
  - `_encode_digital_todo_queue`
  - `_digital_supply_time_bucket`
  - `_pick_supply_tasks_for_queue`

### 3) 新增供给函数 `supply_digital_tasks`

- 每个 step（在 `STEP` 前）执行：
  1. 每日按时间窗向每个 agent 队列注入数字任务（供给层）；
  2. 支持“未完成任务”跨天保留（carryover）；
  3. 以软概率将队列头任务上屏为 `current_need/current_intention`（非强制）；
  4. pending 超时后自动回收，避免长期悬挂。

### 4) 新增状态字段

- 初始化并维护：
  - `digital_todo_queue_json`
  - `digital_todo_pending`
  - `digital_todo_active_task_id`
  - `digital_todo_active_day`
  - `digital_todo_active_t`
  - `digital_todo_seed_day`

### 5) 与触发链路对接

- 在 `trigger_event_shocks` 中：
  - 若本 step 检测到数字暴露且任务 pending，则标记该待办完成并出队；
  - 新增 `step.digital_supply_completed_count`。

### 6) 新增供给层指标

- `step.digital_supply_queue_active_count`
- `step.digital_supply_seeded_count`
- `step.digital_supply_surface_count`
- `step.digital_supply_carryover_agent_count`
- `step.digital_supply_pending_timeout_reset_count`
- `step.digital_supply_candidate_count`
- `step.digital_supply_surface_rate`
- `step.digital_supply_completed_count`（在触发函数侧记录）

### 7) workflow 接入

- 在每个决策 interval 中，顺序调整为：
  - `supply_digital_tasks`
  - `nudge_mobility_if_stuck`
  - `STEP`
  - `trigger_event_shocks`

### 8) 状态

- 语法检查通过：
  - `python -m py_compile examples/digital_friction_mvp/main.py`

## 2026-02-28 结果复盘补记：`meal` 占比偏高（跨实验对比）

### 1) 背景

- 用户提出问题：`digital_friction` 中 `meal` 动作是否异常偏高，其他实验是否也同样偏高。
- 因此补做了一次“同口径跨实验比对”。

### 2) 对比口径（统一）

- 分类口径：`digital -> mobility -> meal -> sleep -> other`（严格关键词匹配，避免 `app/verify` 误判）。
- 关键过滤：对 `hurricane_local_1day` 只统计 `parent_id 非空` 且 `action 非空` 的记录（剔除系统空行）。

### 3) 对比结果

- `digital_friction_p0_r5_supply_20260228_150745`：
  - 总动作 `864`
  - `meal = 384 (44.44%)`
- `hurricane_impact_local_1day`（过滤空 action 后）：
  - 总动作 `360`
  - `meal = 106 (29.44%)`
- 差值：
  - `hurricane - friction = -15.00` 个百分点

### 4) 结论

- `meal` 高占比并非所有实验都同样严重；
- 但在当前 `digital_friction` 任务里，`meal` 占比确实偏高，且显著高于本次对照实验；
- 因此“数字摩擦任务信号被日常生活流稀释”的判断成立。

### 5) 相关产物（用于复核）

- `examples/digital_friction_mvp/analysis/action_rationality_report_dd948d54.md`
- `examples/hurricane_impact/analysis/hurricane_local_1day_meal_check.md`
- `examples/hurricane_impact/analysis/hurricane_local_1day_by_agent.csv`
- `examples/digital_friction_mvp/analysis/experiment_meal_ratio_comparison.csv`

## 2026-02-28 实验归档记录（exp_id=`dd948d5489764ebf8989fc22906bce45`）

### 结论先说

- 这次实验正常完成：`as_experiment.status=2`，实验名 `digital_friction_p0_r5_supply_20260228_150745`。
- 末尾出现的 `asyncio.exceptions.CancelledError` 发生在关闭环境阶段，属于 gRPC 异步收尾常见日志，不是主流程失败。

### 核心结果（本次）

- 总 step：`144`；候选决策位点（agent-step）：`864`（`6 agent × 144`）。
- 决策尝试：`199`，覆盖率约 `23.0%`（`199/864`）。
- 事件触发：`7`，触发率约 `3.5%`（`7/199`），对全部位点约 `0.81%`（`7/864`）。
- 数字暴露：`149`（约 `17.2%` 的 agent-step）。
- 供给链路：`seeded=42 -> surfaced=82 -> completed=39`（完成/露出约 `47.6%`，说明供给机制本身在运转）。

### 为什么“决策尝试还行，但触发率低”

- 主要瓶颈在匹配前段：
  - `scenario_pre_match_miss_count=730`（约 `84.5%` 位点预匹配失败）。
  - `scenario_skip_count=665`（约 `77.0%` 位点被跳过）。
  - `scenario_skip_fallback_not_triggered_count=665`（大量样本未进入后续概率判定）。
- 进入决策后的触发仍偏低：
  - `no_event_count=192`，即 `199` 次尝试里仅 `7` 次落事件。
- 行为文本仍偏生活流：
  - `meal≈41.0%`、`sleep≈24.4%`、`mobility≈0.8%`、`digital(action文本)≈0%`，
  - 导致“可触发场景上下文”整体偏弱。

### 事件结构与阶段表现

- 7 次事件场景分布：
  - `payment_transfer=3`
  - `ride_hailing=3`
  - `info_ad_click=1`
- 结果分布：`positive=3`、`negative=4`。
- 分阶段事件数：`steady=2`、`shock=2`、`recovery=3`（每阶段“至少 2 次”目标达成）。
- 阶段心理指标：
  - shock 阶段 `trust` 下滑、`helplessness` 上升；
  - recovery 阶段 `trust` 回升到 `50.102`，`helplessness` 回落到 `41.733`，方向合理。

### 一句诊断

- 供给层已经“能喂任务”，但主瓶颈仍是 **匹配层 + 选择层**：大量样本没有进入场景决策，进入后触发概率仍偏保守。

### 全量动作 + 合理性评估（同次实验）

- 总动作：`864`，唯一动作：`655`，每个 step 固定 `6` 条（结构完整）。
- 分类占比（严格口径）：
  - `meal 44.44%`
  - `sleep 25.93%`
  - `other 28.70%`
  - `mobility 0.93%`
  - `digital≈0%`
- 高频动作前 4：
  - `Enjoy the meal(20)`
  - `Serve the meal(18)`
  - `Clean up after eating(15)`
  - `Ensure a comfortable sleeping environment(15)`
- day 维度：
  - `meal` 最高为 day6 的 `52.8%`；
  - day1/day3 约 `48.6%`。
- agent 维度：
  - `meal` 最高为 `500055778`（`75/144=52.1%`），
  - 其次 `500019134`（`46.5%`）、`500038614`（`45.1%`）。
- 连续“吃饭链”最长：
  - `500055517` 连续 `11` 步 meal（`day2 t75601 -> day3 t25201`）。

### 合理性评估结论

- 生活行为合理性：中高（退休画像下吃饭/休息高占比可解释，动作文本丰富，非模板死循环）。
- 数字摩擦任务匹配性：偏低（动作文本层面 digital 几乎没有，mobility 也偏低）。
- 触发短板明确：`pre_match_miss/skip` 高，导致大量 step 未进入有效事件触发链路。

### 本次分析产物路径

- `examples/digital_friction_mvp/analysis/action_rationality_report_dd948d54.md`
- `examples/digital_friction_mvp/analysis/action_freq_dd948d54_full.csv`
- `examples/digital_friction_mvp/analysis/action_category_by_day_dd948d54.csv`
- `examples/digital_friction_mvp/analysis/action_category_by_agent_dd948d54.csv`
- `examples/digital_friction_mvp/analysis/action_meal_ratio_by_day_agent_dd948d54.csv`
- `examples/digital_friction_mvp/analysis/event_step_action_context_dd948d54.csv`
- `examples/digital_friction_mvp/analysis/metric_chain_by_day_dd948d54.csv`

## 2026-02-28 识别层补丁：分层数字词规则（anchor + conditional）

文件：`examples/digital_friction_mvp/main.py`

### 1) 背景与问题

- 观察到 `status` 文本里出现了较多“弱数字词”（如 `shopping list / inventory / update`），但这些词并非总是数字行为；
- 同时旧规则使用纯子串匹配，`app` 容易误命中 `appropriate / appreciate`；
- 因此将识别层改为“强锚点 + 条件词”的分层判定，降低误判并保留可解释性。

### 2) 规则改写内容

- 新增词层：
  - `_DIGITAL_ANCHOR_TOKENS`：`phone/online/account/app/portal/platform/...` 及对应中文锚点；
  - `_DIGITAL_SOFT_TOKENS`：`shopping list/inventory/cart/grocery/supplies/check/service/work/access`；
  - `_DIGITAL_STATUS_CONDITIONAL_TOKENS`：`update/updates`（仅条件触发）。
- 新增匹配函数：
  - `_token_in_text`（英文按词边界匹配，中文按包含匹配）；
  - `_contains_any_token`（统一 token 检测入口）。
- `_contains_any_digital_token` 新逻辑：
  1. 先命中 `_DIGITAL_DIRECT_TOKENS`（强直接词）即判数字；
  2. 否则需先命中锚点，再命中弱词/条件词才判数字；
  3. 避免“仅有弱词”就算数字暴露。

### 3) status 信号接入增强

- 在 `friction_step_signal` 中新增 `status_text` 字段；
- `DigitalFrictionAgent.after_forward` 将 agent 当前 `status` 同步写入 `friction_step_signal["status_text"]`；
- `_detect_digital_exposure` 的 `from_status` 由
  - `step_eval_text + step_outcome`
  - 扩展为 `status_text + step_eval_text + step_outcome`
  使状态长文本中的数字语境可被识别。

### 4) 预期影响

- 预期减少弱词引发的假阳性（尤其 `app` 子串误命中）；
- `shopping list/inventory/update` 只在有 `phone/online/account` 等锚点时贡献数字暴露；
- 提升识别口径的可解释性：可明确区分“直接数字词命中”与“锚点+弱词命中”。

### 5) 状态

- 语法检查通过：
  - `python -m py_compile examples/digital_friction_mvp/main.py`

## 2026-03-01 实验复盘记录（exp_id=`b6dc304d6ec745cda863687dc915d209`）

### 1) 结论概览

- 实验正常完成：`status=2`。
- 收尾阶段出现 `asyncio.exceptions.CancelledError`，属于 gRPC 关闭阶段常见日志，不影响主流程结果有效性。
- 本次实际运行 `864` step（`15` 分钟间隔），约 `9` 天模拟时长。
- 当前链路“识别 + 供给”可用，但主瓶颈仍是：**前段匹配损耗高 + 进入判定后触发概率偏低**。

### 2) 核心指标（全局）

- 总位点（agent-step）：`5184`（`864 step × 6 agent`）。
- 决策尝试：`1633`（`31.50%` 位点进入尝试）。
- 事件触发：`13`（`0.80%` of attempts；`0.25%` of slots）。
- 预匹配漏损：`scenario_pre_match_miss_count=3642`（`70.25%`）。
- 跳过：`scenario_skip_count=3551`（`68.50%`，且大多为 fallback 未触发）。
- 数字暴露：`924`（`17.82%` 位点）。
- 供给链路：`seeded=60 -> surfaced=119 -> completed=59`（完成/露出 `49.58%`）。

### 3) 分阶段结果（steady / shock / recovery）

- 事件触发数：`3 / 5 / 5`（shock 与 recovery 高于 steady）。
- 事件场景分布：`ride_hailing=6`、`info_ad_click=4`、`payment_transfer=2`、`medical_appointment=1`。
- 结果分布：`negative=7`、`positive=6`。
- 心理均值：
  - trust：`39.67 -> 42.24 -> 41.43`
  - helplessness：`39.06 -> 44.15 -> 43.66`
  - avoidance：`61.31 -> 55.61 -> 56.20`
- 解释：shock 阶段负事件增多，但 trust 未显著下行，说明扰动强度与行为映射仍需继续校准。

### 4) 行为结构（旧口径）

- `meal 31.85%`
- `sleep 25.58%`
- `other 35.88%`
- `mobility 5.57%`
- `digital(action文本) 1.12%`

对比上一轮（meal 约 44%），本轮 meal 已下降，mobility 上升，`15` 分钟步长对行为结构有改善作用。

### 5) 解释性风险提示

- 尽管每 step 仍为 6 条动作，但 `parent_id` 在全程出现 `112` 个，且 `86.11%` step 发生 ID 换入换出。
- 该现象会削弱“单 agent 纵向轨迹”解释力度（横截面统计仍可用）。

### 6) LLM 计数口径说明

- 日志中的 `LLM request count ~1.98万` 是全流程累计请求；
- 本文指标中的 `step.llm_calls_this_step=952` 是事件决策器子链路计数，二者口径不同，不冲突。

### 7) 本轮分析产物

- `examples/digital_friction_mvp/analysis/experiment_analysis_b6dc304d.md`
- `examples/digital_friction_mvp/analysis/stage_funnel_b6dc304d.csv`
- `examples/digital_friction_mvp/analysis/action_category_by_stage_b6dc304d.csv`
- `examples/digital_friction_mvp/analysis/stage_psych_summary_b6dc304d.csv`
- `examples/digital_friction_mvp/analysis/event_details_b6dc304d.csv`

## 2026-03-01 行为动作重分类（从头定义，不沿用旧口径）

### 1) 新分类结果（基于 `5184` 条动作）

- `饮食相关`：`1743`（`33.62%`）
- `睡眠相关`：`1407`（`27.14%`）
- `放松与情绪调节`：`554`（`10.69%`）
- `购物采购`：`422`（`8.14%`）
- `出行移动`：`285`（`5.50%`）
- `家居环境管理`：`248`（`4.78%`）
- `其他`：`174`（`3.36%`）
- `数字设备与账号操作`：`105`（`2.03%`）
- `社交沟通`：`95`（`1.83%`）
- `工作任务`：`86`（`1.66%`）
- `计划与决策`：`65`（`1.25%`）

### 2) 重分类产物

- 全量逐行动作 + 新分类：
  - `examples/digital_friction_mvp/analysis/step_actions_b6dc304d_reclass_coarse_long.csv`
- 新分类汇总：
  - `examples/digital_friction_mvp/analysis/step_actions_b6dc304d_reclass_coarse_summary.csv`
- action 到新分类映射：
  - `examples/digital_friction_mvp/analysis/action_reclass_coarse_map_b6dc304d.csv`
- 每个 step 的新分类计数：
  - `examples/digital_friction_mvp/analysis/step_actions_b6dc304d_reclass_coarse_step_summary.csv`

## 2026-03-01 第二道门（status补匹配）改造思路 + 数字痕迹占比记录

### 1) 背景与目标

- 现状：第一道门（`intention + step_intention + step_type`）在本轮实验中 `pre_match_miss` 偏高，存在前段损耗；
- 观察：`status_text` 能补充不少“动作文本没写出来但状态里出现的数字线索”；
- 风险：`status_text` 为长叙事文本，若直接并入第一道门，容易放大误判（例如 `ad` 子串误击中 `day/glad/already`）。
- 目标：引入“第二道门”用于**补漏**，而不是替换第一道门。

### 2) 第二道门分层策略（设计稿）

- 第一道门保持不变：先用 `intention + step_intention + step_type` 做主匹配；
- 仅当第一道门 miss 时，才进入第二道门；
- 第二道门触发前置条件：`digital_exposure.from_status=True`；
- 第二道门匹配约束：
  - 先检查数字锚点（如 `phone/app/online/account/登录/验证码`）；
  - 使用词边界匹配（避免子串误命中）；
  - 设定最低得分阈值（建议 `min_score>=2`，或“`step_type` 先验一致时放宽”）；
- 第三道门（fallback/exploratory）继续保留，不改整体兜底逻辑。

### 3) 本轮“action+status 联合口径”数字痕迹统计（严格电子技术词表）

> 注：该口径用于“数字痕迹暴露”统计，不等价于“场景必然匹配/事件必然触发”。

- 合并 6 类总样本：`1547`
- `action-only`：`106 / 1547 = 6.85%`
- `status-only 命中`：`290 / 1547 = 18.75%`
- `action 或 status 任一命中`：`319 / 1547 = 20.62%`

分类型（`action 或 status` 任一命中）：

- `放松与情绪调节`：`64 / 554 = 11.55%`
- `购物采购`：`75 / 422 = 17.77%`
- `出行移动`：`47 / 285 = 16.49%`
- `数字设备与账号操作`：`104 / 105 = 99.05%`
- `社交沟通`：`24 / 95 = 25.26%`
- `工作任务`：`5 / 86 = 5.81%`

### 4) 解释与结论

- `status-only` 占比显著高于 `action-only`，说明很多“数字行为线索”只出现在状态叙事，不在动作短句中；
- 因此第二道门有价值：能提升补漏能力；
- 但仍需分层与阈值约束，避免把“有数字词痕迹”直接等同于“应命中具体摩擦场景”。

### 5) 关联产物

- 汇总：`examples/digital_friction_mvp/analysis/explicit_tech_action_status_by_behavior_class_b6dc304d.csv`
- `status-only` 示例：`examples/digital_friction_mvp/analysis/explicit_tech_status_only_examples_b6dc304d.csv`

## 2026-03-01 摩擦分类扩展（基于 action+status 数字痕迹分布）

### 1) 扩展动机

- 现有场景在“电子相关但不够具体”的样本上存在分流损耗；
- 根据 `action+status` 统计，`购物采购/出行移动/社交沟通` 均存在明显数字痕迹；
- 因此新增更贴近行为语义的摩擦分类，减少“有线索但无合适场景”的漏判。

### 2) 新增场景

- `social_contact`（社交联系类数字摩擦）
- `ecommerce_order`（电商下单/购物流程摩擦）
- `digital_general`（电子相关但场景不明确的轻量兜底摩擦）

### 3) 配套改动（`examples/digital_friction_mvp/main.py`）

- `EVENT_SCENARIOS` 增加上述 3 个场景及正负事件文案；
- `INTENTION_SCENARIO_MAP` 增加对应关键词：
  - `social_contact`：`contact/chat/message/friend/call` 等；
  - `ecommerce_order`：`shopping list/cart/inventory/order/delivery` 等；
  - `digital_general`：`app/phone/online/account/update/permission` 等；
- `_STEP_TYPE_SCENARIO_MAP` 中 `social` 由 `info_ad_click` 调整为 `social_contact`；
- `_fallback_scenario_from_context` 增加新场景优先分流规则，并补充 `need` 映射；
- 对“仅失败但未识别到细分场景”改为优先落入 `digital_general`，避免过度默认 `login_captcha`；
- `_infer_positive_process_signals` 的可拦截场景集合纳入新场景。

### 4) 校验

- `python -m py_compile examples/digital_friction_mvp/main.py` 通过。

## 2026-03-01 数字痕迹 `319` 池提取与摩擦子类型归类（配额采样）

### 1) 口径说明

- 总样本 `1547`（6类行为）；
- 数字命中池 `319`（`action OR status`）；
- 因原始严格词表结果为分类汇总表，故本次采用“按类别配额 + 行级关键词打分”的抽样法构造 `319` 候选池用于子类型发现。

### 2) 结果文件

- 抽样明细（319行）：
  - `examples/digital_friction_mvp/analysis/sampled_digital_candidates_319_b6dc304d.csv`
- 子类型汇总：
  - `examples/digital_friction_mvp/analysis/sampled_digital_candidates_319_subtype_summary_b6dc304d.csv`
- 子类型 × 行为大类：
  - `examples/digital_friction_mvp/analysis/sampled_digital_candidates_319_subtype_by_class_b6dc304d.csv`
- 说明文档：
  - `examples/digital_friction_mvp/analysis/friction_subtype_extraction_319_b6dc304d.md`

### 3) 子类型分布（N=319）

- `app_update_permission`: `142`（`44.51%`）
- `ecommerce_order_flow`: `80`（`25.08%`）
- `social_contact_coordination`: `73`（`22.88%`）
- `account_auth_security`: `14`（`4.39%`）
- `notification_risk_interrupt`: `10`（`3.13%`）

### 4) 用于扩展摩擦分类的建议

- 高优先：`app_update_permission`、`ecommerce_order_flow`、`social_contact_coordination`
- 中优先：`account_auth_security`、`notification_risk_interrupt`
- 迁移策略：
  - 保留既有主干场景；
  - 强化 `social_contact/ecommerce_order/digital_general`；
  - 需要更细粒度时，再从 `digital_general/login_captcha` 拆分出上面中优先子类。

## 2026-03-01 第二道门（status gate）正式落地 + 五类场景日志核对

文件：`examples/digital_friction_mvp/main.py`

### 1) 第二道门接入位置与流程

- 保持第一道门不变：先执行 `_match_scenario(intention + step_intention + step_type)`；
- 仅当第一道门 miss 时，进入 `_match_scenario_second_gate(...)`；
- 第二道门前置：
  - `digital_exposure.from_status=True`
  - `status_text` 非空
- 第二道门匹配规则：
  - 可选锚点门槛（`STATUS_GATE_REQUIRE_ANCHOR`，默认开）；
  - 仅用 `status_text` 对场景词表打分（边界匹配，避免 `ad/day` 子串误命中）；
  - `top_score >= STATUS_GATE_MIN_SCORE` 才命中（默认 `2`）；
  - `top_gap >= STATUS_GATE_TOP_GAP` 才命中（默认 `1`，控制歧义）；
  - 若 `step_type` 先验与 top 场景一致，可放宽最低分（`STATUS_GATE_STEP_TYPE_RELAX`，默认开）。

### 2) 新增环境参数（可调）

- `STATUS_GATE_ENABLED=1`
- `STATUS_GATE_MIN_SCORE=2`
- `STATUS_GATE_TOP_GAP=1`
- `STATUS_GATE_REQUIRE_ANCHOR=1`
- `STATUS_GATE_STEP_TYPE_RELAX=1`

### 3) 新增审计字段与 step 指标

- `decision_audit` 新增：
  - `status_gate_attempted`
  - `status_gate_matched`
  - `status_gate_reason`
  - `status_gate_anchor_hit`
  - `status_gate_top_score`
  - `status_gate_second_score`
  - `status_gate_top_gap`
  - `status_gate_effective_min_score`
  - `status_gate_scenario`
- `step` 指标新增：
  - `step.scenario_status_gate_attempt_count`
  - `step.scenario_status_gate_hit_count`
  - `step.scenario_status_gate_no_anchor_count`
  - `step.scenario_status_gate_low_score_count`
  - `step.scenario_status_gate_ambiguous_count`

### 4) 五类场景日志核对（已记录）

- 五类场景均已在日志中记录并具备分布统计：
  - `app_update_permission`
  - `ecommerce_order_flow`
  - `social_contact_coordination`
  - `account_auth_security`
  - `notification_risk_interrupt`
- 见本文件“数字痕迹 `319` 池提取与摩擦子类型归类（配额采样）”章节（子类型分布）。

## 2026-03-02 实验复盘（`dc6d9388-2bd3-4f61-88ed-a7eea7491f3c`，status gate 版本）

### 1) 运行状态

- 实验名称：`digital_friction_r7_statusgate_20260301_233847`
- 实验状态：`status=2`（正常完成）
- 结尾 `asyncio.exceptions.CancelledError` 仍为环境关闭阶段的常见收尾日志，不影响主流程结果有效性。

### 2) 核心漏斗（本轮）

- 总 step：`288`（15 分钟间隔）
- 总位点（6 agent）：`1728`
- 决策尝试：`542`（`31.37%`）
- 事件触发：`6`（占尝试 `1.11%`；占全部位点 `0.35%`）
- `no_event_count`：`536`
- `pre_match_miss`：`1238`（`71.64%`）
- `scenario_skip`：`1186`（`68.63%`）

### 3) 第二道门（status gate）表现

- `status_gate_attempt_count`：`2`
- `status_gate_hit_count`：`0`
- `status_gate_no_anchor_count`：`2`
- `status_gate_low_score_count`：`0`
- `status_gate_ambiguous_count`：`0`

结论：本轮第二道门已执行，但进入量很低且无命中，暂未形成对触发率的可观提升。

### 4) 阶段表现（steady/shock/recovery）

- steady：`attempt=175`，`event=2`，`pre_match_miss=411`，`status_gate=2/0`
- shock：`attempt=213`，`event=2`，`pre_match_miss=389`，`status_gate=0/0`
- recovery：`attempt=154`，`event=2`，`pre_match_miss=438`，`status_gate=0/0`

阶段事件数基本由保底机制托起：
- `stage_min_event_force_count=6`

### 5) 事件与行为结构

- 场景分布：`ride_hailing=3`、`info_ad_click=2`、`payment_transfer=1`
- 结果分布：`positive=5`、`negative=1`
- 行为结构（动作口径）：
  - `meal 35.71%`
  - `sleep 27.31%`
  - `other 32.52%`
  - `digital 2.26%`
  - `mobility 2.20%`

### 6) 数字暴露与供给链路

- `digital_exposure_count=222`（`12.85%` 位点）
- 来源拆分：
  - `from_action=99`
  - `from_status=81`
  - `from_intention=167`
  - `from_signal=110`
- 供给链路：
  - `seeded=24 -> surfaced=56 -> completed=23`
  - `completed/surfaced=41.07%`

### 7) 产物文件

- 总结报告：`examples/digital_friction_mvp/analysis/experiment_analysis_dc6d9388.md`
- 阶段漏斗：`examples/digital_friction_mvp/analysis/stage_funnel_dc6d9388.csv`
- 事件明细：`examples/digital_friction_mvp/analysis/event_details_dc6d9388.csv`
- 动作分类：`examples/digital_friction_mvp/analysis/action_category_dc6d9388.csv`
- Top 动作：`examples/digital_friction_mvp/analysis/action_top20_dc6d9388.csv`

## 2026-03-02 第二道门 C 方案修正（提升 status gate 实际命中机会）

文件：`examples/digital_friction_mvp/main.py`

### 1) 修正内容

- 第二道门匹配文本由“仅 `status_text`”改为与 `from_status` 同口径：
  - `status_text + step_eval_text + step_outcome`
- 保持判定阈值不变：
  - `STATUS_GATE_MIN_SCORE=2`
  - `STATUS_GATE_TOP_GAP=1`
- 补充第二道门锚点词（更贴近样本）：
  - `shopping list/grocery list/shopping cart/cart/checkout/contacts/contact list/map/map app/navigation`
  - 中文补充：`通讯录/联系人列表/地图/导航`

### 2) 预期影响

- 解决“`from_status=True` 但第二门只看 `status_text` 导致补漏失败”的口径不一致问题；
- 提升第二道门尝试率与命中率（尤其购物/联系人/地图类状态文本）；
- 在不放宽 `min_score/top_gap` 的前提下尽量提升召回，控制误判。

## 2026-03-02 运行参数确认（方案 C + LLM 权重上调）

### 1) 采用方案

- 继续使用第二道门 **方案 C**（已在代码中生效）：
  - 第二道门文本口径：`status_text + step_eval_text + step_outcome`
  - 阈值保持：`STATUS_GATE_MIN_SCORE=2`、`STATUS_GATE_TOP_GAP=1`
  - 扩展锚点词：`shopping list/cart/checkout/contacts/map/navigation` 及中文对应

### 2) 本轮 LLM 融合参数（仅运行参数，不改代码）

- `LLM_DECIDER_ALPHA=0.85`
- `LLM_DECIDER_MIN_CONFIDENCE=0.20`
- `LLM_DECIDER_ALPHA_MIN_HYBRID=0.30`

### 3) 目的与预期

- 在不改第一道门与概率基础公式的前提下，提高 hybrid 模式中 LLM 对最终概率的影响权重；
- 降低因置信度门槛导致的纯 rule 回退；
- 与方案 C 联合使用，观察“入池后触发率”是否提升，同时监控负事件占比与心理指标波动。

## 2026-03-02 实验复盘（`df0a570e-119c-491c-8f99-f23ad18033b2`，历史参数 `EVENT_ALWAYS_EMIT=1`）

### 1) 运行状态

- 实验名称：`digital_friction_single30_c_llm085_20260302_161452`
- 实验状态：`status=2`（正常完成）
- 配置特征：`STAGE_MODE=single`、`STAGE_SINGLE_NAME=steady`、`STAGE_DAYS=1`、`EVENT_DECISION_INTERVAL_MINUTES=30`、`EVENT_EMIT_POLICY=force`（历史记录里使用的是旧参数 `EVENT_ALWAYS_EMIT=1`）
- 运行日志中的以下告警未导致实验失败：
  - `Failed to dispatch block: 'NoneType' object is not subscriptable`
  - `Huggingface无法连通，切换国内源`

### 2) 核心漏斗（本轮）

- 总 step：`48`（30 分钟间隔）
- 总位点（6 agent）：`288`
- 决策尝试：`119`（`41.32%` 位点）
- 事件触发：`119`（占尝试 `100%`；占全部位点 `41.32%`）
- `no_event_count`：`0`
- `always_emit_forced_count`：`119`
- `pre_match_miss`：`179`（`62.15%`）
- `scenario_skip`：`169`（`58.68%`）

### 3) 第二道门（status gate）表现

- `status_gate_attempt_count`：`1`
- `status_gate_hit_count`：`0`
- `status_gate_no_anchor_count`：`1`
- `status_gate_low_score_count`：`0`
- `status_gate_ambiguous_count`：`0`

结论：本轮第二道门仍几乎未参与；本轮事件数提升主要来自 `EVENT_EMIT_POLICY=force`，不是 status gate 命中提升。

### 4) 事件结构与来源

- 结果分布：`negative=103`、`positive=16`（负面占 `86.55%`）
- 场景 Top：
  - `info_ad_click=30`
  - `ride_hailing=21`
  - `payment_transfer=18`
  - `app_update_permission=18`
- 入场来源：
  - `matched=109`
  - `min_stage_attempt_force=8`
  - `digital_context_fallback=1`
  - `non_digital_exploration=1`

### 5) LLM 融合表现

- `hybrid_applied_count=119`，`rule_applied_count=0`，`rule_fallback_count=0`
- `llm_query_success_count=96`，`llm_cache_hit_count=23`
- `llm_request_error_count=0`，`llm_parse_fail_count=0`
- 事件审计中 `alpha` 约在 `0.3053 ~ 0.3085`，均为正权重融合（非纯 rule）。

### 6) 状态结果（阶段末）

- `helplessness_avg=83.21`
- `trust_avg=14.95`
- `avoidance_avg=81.95`
- 过程均值：
  - `negative_avg=17.17`
  - `success_avg=2.67`
  - `failure_avg=17.17`

解释：在 `EVENT_EMIT_POLICY=force` 下，事件密度显著上升且负向占比偏高，心理指标呈“高无助/高回避/低信任”的压力态。

### 7) 与上一轮（未开启 ALWAYS_EMIT）对比（`fb09921c...`）

- `decision_attempt_count`：`73 -> 119`
- `event_emitted_count`：`2 -> 119`
- `no_event_count`：`71 -> 0`

结论：`EVENT_EMIT_POLICY=force` 成功实现“尝试即出事件”，但会显著改变自然触发分布，不适合作为“自然发生率”评估基线。

### 8) 本轮新增分析产物

- 全量事件明细（119条）：`examples/digital_friction_mvp/analysis/event_details_df0a570e_full.csv`
- 事件-状态不一致样本：`examples/digital_friction_mvp/analysis/event_outcome_status_mismatch_df0a570e.csv`

## 2026-03-02 触发机制结构性修正（第一门/第二门/message/emit policy）

文件：`examples/digital_friction_mvp/main.py`

### 1) 第一门匹配改造（边界感知 + 低置信门控）

- 新增配置：
  - `FIRST_GATE_MIN_SCORE`（默认 `2`）
  - `FIRST_GATE_TOP_GAP`（默认 `1`）
  - `FIRST_GATE_REQUIRE_DIGITAL_FOR_WEAK_MATCH`（默认 `1`）
- `_match_scenario` 改为复用 `_token_in_text` 口径，避免 `ad` 命中 `reading` 这类子串误判。
- 新增 `_match_scenario_with_meta`，输出 `top_score/top_gap/confidence/reason`，并写入审计字段：
  - `first_gate_reason`
  - `first_gate_top_score`
  - `first_gate_top_gap`
  - `first_gate_confidence`
- `_is_scenario_aligned_with_context` 与 `_fallback_scenario_from_context` 同步改为 token 级匹配口径。

### 2) 第二道门改造（可覆盖低置信第一门）

- 新增配置：
  - `STATUS_GATE_ALLOW_OVERRIDE`（默认 `1`）
  - `STATUS_GATE_OVERRIDE_MIN_SCORE`（默认 `3`）
- 第二门不再只在“第一门 miss”时触发；当第一门低置信时也进入第二门复核。
- 新增漏斗审计字段：
  - `status_gate_eligible`
  - `status_gate_override_applied`
- 新增 step 指标：
  - `step.status_gate_eligible_count`
  - `step.status_gate_override_count`
  - `step.status_gate_blocked_from_status_count`
  - `step.status_gate_blocked_anchor_count`

### 3) message 改造（上下文模板 + 可选 LLM）

- 新增配置：
  - `EVENT_MESSAGE_MODE=template|llm|hybrid`（默认 `template`）
  - `EVENT_MESSAGE_LLM_TIMEOUT`（默认 `8`）
  - `EVENT_MESSAGE_MAX_LEN`（默认 `80`）
- 新增 `_render_event_message`，默认模板渲染，`llm/hybrid` 模式下调用 LLM 失败自动回退模板。
- 新增审计字段：
  - `message_mode`
  - `message_source`

### 4) Emit 策略改造（natural/soft/force）

- 新增配置：
  - `EVENT_EMIT_POLICY=natural|soft|force`（默认 `natural`）
  - `EVENT_EMIT_SOFT_RATE`（默认 `0.25`）
  - `EVENT_EMIT_SOFT_REQUIRE_DIGITAL`（默认 `1`）
  - `EVENT_EMIT_SOFT_MAX_SHARE_PER_STEP`（默认 `0.35`）
- 历史兼容说明（已失效）：
  - 旧逻辑曾支持：仅设置 `EVENT_ALWAYS_EMIT=1` 且未设置 `EVENT_EMIT_POLICY` 时，自动映射为 `force`。
  - 当前代码已移除该兼容分支，仅以 `EVENT_EMIT_POLICY` 为准。
- 新增审计字段：
  - `emit_policy`
  - `emit_forced_by_policy`
- 新增 step 指标：
  - `step.emit_policy_forced_count`
  - `step.emit_policy_soft_skip_count`

### 5) 分析脚本新增

- 新增：`examples/digital_friction_mvp/analysis/check_event_quality.py`
- 输出核心质量项：
  - 非数字暴露下 `matched` 占比
  - `reading/hobby -> info_ad_click` 误判样本计数
  - 第二门漏斗（eligible/attempt/hit/override/blocked）
  - emit policy 分布与策略强制计数

## 2026-03-03 触发概率重构：`daily_rescaled` + `attempt_hazard` 双模型并存

文件：`examples/digital_friction_mvp/main.py`

### 1) 概率模型开关与新配置

- 新增 `EVENT_PROB_MODEL=daily_rescaled|attempt_hazard`（默认 `daily_rescaled`，兼容旧实验）。
- 新增 attempt-hazard 相关配置：
  - `ATTEMPT_HAZARD_TARGET_RATE`
  - `ATTEMPT_HAZARD_CALIBRATE_ENABLED`
  - `ATTEMPT_HAZARD_CALIBRATE_LR`
  - `ATTEMPT_HAZARD_CALIBRATE_CLIP`
  - `ATTEMPT_HAZARD_REQUIRE_DIGITAL`
  - `ATTEMPT_HAZARD_REFRACTORY_DECAY`
  - `ATTEMPT_HAZARD_HISTORY_WINDOW`
  - `ATTEMPT_HAZARD_MIN_P`
  - `ATTEMPT_HAZARD_MAX_P`

### 2) 新增 attempt-level hazard 计算

- 新增函数 `_build_attempt_hazard_params(...)`：
  - 以环境、画像、状态、step 信号和历史项直接计算本次尝试 `p_total`。
  - 通过 `r_negative` 拆分 `p_negative/p_positive`。
  - 支持短期抑制（refractory）和失败压力趋势项。
- `daily_rescaled` 路径保留原逻辑；`attempt_hazard` 路径不再执行日概率到 interval 概率折算。

### 3) 稳态校准与历史缓存

- 新增 stage/agent 级缓存：
  - `_STAGE_ATTEMPT_HAZARD_CALIBRATION_OFFSET_TRACKER`
  - `_STAGE_ATTEMPT_HAZARD_EMA_TRACKER`
  - `_STAGE_ATTEMPT_HAZARD_EVENT_HISTORY_TRACKER`
  - `_STAGE_ATTEMPT_HAZARD_FAILURE_HISTORY_TRACKER`
- 在每个 step 结束时计算：
  - `attempt_hazard_natural_emit_rate`
  - `EMA` 平滑触发率
  - `calibration_offset` 更新（按 `target - ema` 纠偏）

### 4) 决策审计字段扩展

- 在 `decision_audit` 新增：
  - `prob_model`
  - `hazard_z_total`
  - `hazard_p_total`
  - `hazard_r_negative`
  - `hazard_calibration_offset`
  - `hazard_refractory_penalty`

### 5) step 指标扩展

- 新增：
  - `step.attempt_hazard_eligible_attempt_count`
  - `step.attempt_hazard_natural_emit_count`
  - `step.attempt_hazard_natural_emit_rate`
  - `step.attempt_hazard_ema_emit_rate`
  - `step.attempt_hazard_calibration_offset`
  - `step.attempt_hazard_refractory_hit_count`

## 2026-03-04 实验复盘（full3stage / hazard / natural）

- 实验名：`digital_friction_full3stage_30min_hazard_natural_20260303_155531`
- `exp_id`：`0e9eace8-abed-417a-af98-29344b8676af`
- 状态：`status=2`（完成）
- 说明：日志末尾 `CancelledError` 为环境关闭阶段常见收尾，不视为实验失败。

### 总体漏斗（3 stage）

- 总机会：`6 agents × 144 steps = 864`
- 进入决策尝试：`173`（`20.0%`）
- 触发事件：`53`，未触发：`120`
- 尝试后触发率：`53/173 = 30.6%`
- 全机会触发率：`53/864 = 6.1%`
- `emit_policy_forced_count=0`（无 policy 强制触发）

### 分 stage 结果

- Stage1（steady）：`50` attempts，`14` events，`28.0%`，正/负=`8/6`
- Stage2（shock）：`63` attempts，`23` events，`36.5%`，正/负=`11/12`
- Stage3（recovery）：`60` attempts，`16` events，`26.7%`，正/负=`15/1`
- 方向上符合设计预期：shock 更负向、recovery 更正向。

### 触发合理性

- 高合理样本（`matched + digital_exposure=true + scenario_aligned=true`）：`27/53 = 50.9%`
- `matched` 总数：`28`，其中 `27` 条为数字且对齐。
- 问题主要来自 `min_stage_attempt_force`：`21/53 = 39.6%`
  - 其中 `digital_exposure=false`：`19/21 = 90.5%`
  - 其中 `aligned=false`：`18/21 = 85.7%`
- 非数字事件总体：`23/53 = 43.4%`（偏高）
- `reading/hobby -> info_ad_click`：`1` 条（较历史下降，但未清零）

### 机制诊断

- 当前 natural hazard 已可稳定触发，但偏高偏硬：
  - 事件样本 `p_total` 均值偏高；约 `24.5%` 事件触及 `ATTEMPT_HAZARD_MAX_P=0.45` 上限。
  - Stage2 强度明显更高。
- 第二道门仍弱：
  - 全局 `status_gate_eligible=781`，`attempt=37`，`hit=1`，`override=0`
  - 主要被 `from_status_false` 拦截。

### Warning 记录

- `Failed to dispatch block ... Reflect on the uneventful day`：属于 action-block 路由未命中（文本意图未映射到合适 block）。
- 本轮表现为局部噪声，不影响主流程完成；但建议后续补充 block 路由词表。

## 2026-03-04 去除“非数字上下文触发事件”路径

文件：`examples/digital_friction_mvp/main.py`

- 新增硬门：`digital_exposure=False` 时，直接跳过该 agent 的事件触发流程（不再进入场景匹配/概率判定）。
- `preferred_step_type_direct` 改为仅在 `digital_context=True` 时可用（删除了此前 `step_outcome in {success,failure}` 的非数字放行）。
- 删除 `non_digital_exploration` 触发分支，不再在非数字上下文中做探索触发。
- fallback 调用固定为 `allow_non_digital=False`，禁止通过 fallback 在非数字上下文中落地场景。

## 2026-03-04 实验复盘（full3stage / hazard / natural / 6-agent）

- 实验名：`digital_friction_full3stage_30min_hazard_natural_20260304_035352`
- `exp_id`：`7889369e-0b42-414f-bacc-250ba1ca2020`
- 状态：`status=2`（完成）

### 总体漏斗

- 总机会：`6 agents × 3 days × 48 steps/day = 864`
- 决策尝试：`63`（`7.3%`）
- 事件触发：`18`，未触发：`45`
- 尝试后触发率：`18/63 = 28.6%`
- 全机会触发率：`18/864 = 2.1%`
- `emit_policy_forced_count=0`（全程 natural，无 policy 强制）

### Stage 结果（按 48 step/stage 拆分）

- Stage1（steady）：`attempt=30`，`event=8`，触发率 `26.7%`，正/负=`3/5`
- Stage2（shock）：`attempt=21`，`event=9`，触发率 `42.9%`，正/负=`4/5`
- Stage3（recovery）：`attempt=12`，`event=1`，触发率 `8.3%`，正/负=`1/0`

### 触发质量与机制观察

- `matched_non_digital_count=0`，事件中的 `digital_exposure=True` 且 `scenario_aligned=True` 均为 `18/18`
- `scenario_entry_reason=matched` 为 `18/18`（无 `min_stage_attempt_force`）
- 事件分布：`ride_hailing=13`，`social_contact_coordination=4`，`account_auth_security=1`
- `status_gate` 仍偏弱：`eligible=45`，`attempt=30`，`hit=0`，主要阻塞于 `no_anchor` 与 `from_status_false`

### 导出文件

- 已导出“进入尝试决策 63 条”CSV：`examples/digital_friction_mvp/analysis/decision_attempts_full63_7889369e.csv`
- 说明：其中 `18` 条为事件触发记录（含完整 `decision_audit`）；`45` 条为未触发尝试，由 `step.no_event_count` 展开。当前 artifacts/db 未持久化每条 no-event 的逐条审计字段，因此在 CSV 中标记 `attempt_detail_available=0`。

## 2026-03-05 legacy 移除收口（trigger_event_shocks）

- 变更原因：`trigger_event_shocks` 已完成 7 子流程拆分，legacy 版本仅造成维护负担与对照误用风险。
- 影响范围：仅删除 `examples/digital_friction_mvp/main.py` 中旧版 `trigger_event_shocks` 实现，不改 workflow 入口与参数接口。
- 兼容性：`mvp_decision_attempt` 字段、metrics key、环境变量解析保持不变；实际运行仍使用 `trigger_event_shocks`。
- 验证项：`ruff`、`py_compile`、smoke run、旧版函数符号全仓检索为 0。

## 2026-03-05 统一主判管线落地（预筛→LLM统一判定→规则兜底）

### 代码改造记录

- `examples/digital_friction_mvp/config_runtime.py`
  - 新增 `MATCH_PIPELINE_MODE`：`llm_unified_primary`
  - 新增：
    - `LLM_UNIFIED_MIN_CONFIDENCE`（默认 `0.45`）
    - `LLM_UNIFIED_DIGITAL_MIN_CONFIDENCE`（默认 `0.45`）
    - `LLM_UNIFIED_PREFILTER_ENABLED`（默认 `1`）
  - 后续版本已移除 `two_stage` 兼容路径，固定为 unified 主判管线。

- `examples/digital_friction_mvp/scenario_matching.py`
  - 新增 `UnifiedMatchResult`
  - 新增 `sanitize_unified_match_payload(...)`（严格 schema 校验，不合法降级失败）
  - 新增 `llm_match_unified_context(...)`，一次输出：
    - `is_digital`
    - `digital_confidence`
    - `scenario_name`
    - `scenario_confidence`
    - `reason/tags/status/source`

- `examples/digital_friction_mvp/main.py`
  - `_build_agent_context(...)` 保留 `digital_exposure` 审计，但不再在此处对非数字直接 `return None`。
  - `_match_scenario_for_agent(...)` 新增 unified 分支：
    1. 轻量预筛（token）
    2. `llm_match_unified_context`
    3. 高置信数字+场景直通
    4. 高置信非数字直接 skip
    5. 低置信/异常/预算不足进入规则链兜底
  - `decision_audit` 新增：
    - `match_pipeline_mode`
    - `digital_gate_source`
    - `digital_gate_status`
    - `digital_gate_confidence`
    - `digital_gate_reason`
  - step 指标新增：
    - `step.llm_unified_called_count`
    - `step.llm_unified_non_digital_skip_count`
    - `step.llm_unified_digital_accept_count`
    - `step.llm_unified_rule_fallback_count`

### 校验记录（本轮）

- `ruff check examples/digital_friction_mvp/main.py examples/digital_friction_mvp/config_runtime.py examples/digital_friction_mvp/scenario_matching.py` 通过
- `python -m py_compile examples/digital_friction_mvp/main.py examples/digital_friction_mvp/config_runtime.py examples/digital_friction_mvp/scenario_matching.py` 通过
- 按当前确认：本次未追加新的 smoke 运行。

### 实验配置记录（本次使用，密钥已脱敏）

```bash
LLM_API_KEY="<REDACTED>" \
WORLD_NAME="baseline_low_friction" \
EVENT_DECIDER_MODE="hybrid" \
LLM_DECIDER_ALPHA=0.85 \
LLM_DECIDER_MIN_CONFIDENCE=0.20 \
LLM_DECIDER_ALPHA_MIN_HYBRID=0.30 \
FIRST_GATE_MIN_SCORE=2 \
FIRST_GATE_TOP_GAP=1 \
FIRST_GATE_REQUIRE_DIGITAL_FOR_WEAK_MATCH=1 \
STATUS_GATE_ENABLED=1 \
STATUS_GATE_MIN_SCORE=2 \
STATUS_GATE_TOP_GAP=1 \
STATUS_GATE_REQUIRE_ANCHOR=1 \
STATUS_GATE_STEP_TYPE_RELAX=1 \
STATUS_GATE_ALLOW_OVERRIDE=1 \
STATUS_GATE_OVERRIDE_MIN_SCORE=3 \
EVENT_PROB_MODEL="attempt_hazard" \
ATTEMPT_HAZARD_TARGET_RATE=0.10 \
ATTEMPT_HAZARD_CALIBRATE_ENABLED=1 \
ATTEMPT_HAZARD_CALIBRATE_LR=0.08 \
ATTEMPT_HAZARD_CALIBRATE_CLIP=0.8 \
ATTEMPT_HAZARD_REQUIRE_DIGITAL=1 \
ATTEMPT_HAZARD_REFRACTORY_DECAY=0.25 \
ATTEMPT_HAZARD_HISTORY_WINDOW=4 \
ATTEMPT_HAZARD_MIN_P=0.002 \
ATTEMPT_HAZARD_MAX_P=0.45 \
EVENT_EMIT_POLICY="natural" \
EVENT_MIN_STAGE_EVENT_EMITS=0 \
EVENT_MESSAGE_MODE="hybrid" \
AGENT_COUNT=6 \
STAGE_MODE="full" \
STAGE_DAYS=1 \
EVENT_DECISION_INTERVAL_MINUTES=60 \
DIGITAL_SUPPLY_ENABLED=1 \
DIGITAL_SUPPLY_DAILY_TASKS_PER_AGENT=1 \
DIGITAL_SUPPLY_MAX_QUEUE=3 \
DIGITAL_SUPPLY_SURFACE_PROB=0.35 \
DIGITAL_SUPPLY_SURFACE_IDLE_ONLY=1 \
DIGITAL_SUPPLY_CARRYOVER_ENABLED=1 \
DIGITAL_SUPPLY_PENDING_MAX_HOURS=18 \
MATCH_PIPELINE_MODE="llm_unified_primary" \
LLM_SCENARIO_ENABLED=1 \
LLM_UNIFIED_PREFILTER_ENABLED=1 \
LLM_UNIFIED_MIN_CONFIDENCE=0.45 \
LLM_UNIFIED_DIGITAL_MIN_CONFIDENCE=0.45 \
EXP_NAME="digital_friction_full3stage_60min_hazard_natural_$(date +%Y%m%d_%H%M%S)" \
python examples/digital_friction_mvp/main.py
```

## 2026-03-05 unified prompt 硬约束增强（中文版本）

- 变更文件：`examples/digital_friction_mvp/scenario_matching.py`
- 变更范围：仅调整 `llm_match_unified_context(...)` 的 prompt 文本，不改流程逻辑与 schema。

### 调整内容

- 将 unified `system_prompt` 改为中文“硬约束”版本，明确：
  - 只允许输出一个 RFC8259 JSON 对象
  - 禁止 markdown / code fence / 额外解释文本
  - 键集合必须且只能是：
    `is_digital, digital_confidence, scenario_name, scenario_confidence, reason, tags, status`
  - 字段联动规则：
    - `is_digital=false` ⇒ `scenario_name=""` 且 `scenario_confidence=0.0`
  - `status` 允许值建议为：`ok | non_digital | low_confidence | invalid_context`
- 将 unified `user` 提示语改为中文（`上下文 JSON` + `输出示例` + `只返回一个 JSON 对象`）。
- 将示例 `reason` 改为中文语义描述。

### 影响评估

- 对外接口与参数不变（`MATCH_PIPELINE_MODE`、`LLM_UNIFIED_*` 不变）。
- 解析逻辑不变（仍由 `sanitize_unified_match_payload(...)` 做 schema 与字段有效性校验）。
- 预期收益：降低非 JSON / 脏输出概率，提高 unified 审计稳定性。

## 2026-03-05 unified prompt 语言更正（改回英文）

- 更正原因：`examples/digital_friction_mvp/scenario_matching.py` 的 unified prompt 语言要求为英文。
- 更正内容：将 `llm_match_unified_context(...)` 的 `system/user` prompt 文本从中文改回英文，保留“硬约束 JSON”结构与原有 schema。
- 不变项：解析逻辑、字段约束、运行参数、workflow 逻辑均不变。

## 2026-03-05 实验复盘（full3stage / 60min / hazard / natural / unified）

- 实验名：`digital_friction_full3stage_60min_hazard_natural_20260305_192204`
- `exp_id`：`dd589b8c-e4d3-45d8-a7f7-2901ebb6be4b`
- 状态：`status=2`（完成）
- 运行区间：`2026-03-05 11:22:06` ~ `2026-03-05 12:32:04`（约 69 分钟）
- 备注：日志末尾 `asyncio.exceptions.CancelledError` 出现在环境关闭阶段，判定为收尾噪声，不视为业务失败。

### 总体漏斗（本轮）

- 总机会：`6 agents × 72 steps = 432`
- 决策尝试：`46`（`10.65%`）
- 事件触发：`14`（positive=`13`, negative=`1`）
- 未触发：`32`
- 尝试后触发率：`14 / 46 = 30.43%`
- 全机会触发率：`14 / 432 = 3.24%`

### unified 主流程表现

- `match_pipeline_mode=llm_unified_primary`（attempt 样本中 100%）
- 场景来源：
  - `llm_primary=45`
  - `rule_fallback=1`
  - `random_fallback=0`
- unified 指标（step 汇总）：
  - `step.llm_unified_called_count=46`
  - `step.llm_unified_digital_accept_count=45`
  - `step.llm_unified_rule_fallback_count=1`
  - `step.llm_unified_non_digital_skip_count=386`

### 分阶段结果

- `steady`：attempt=`23`，event=`6`（正=`6`，负=`0`）
- `shock`：attempt=`8`，event=`2`（正=`2`，负=`0`）
- `recovery`：attempt=`15`，event=`6`（正=`5`，负=`1`）

### 结构性观察

- 本轮 emitted 场景高度集中：`ride_hailing = 14/14`
- `llm_match_status` 以 `ok` 为主（`45`），`non_digital` 有 `1` 条。
- `llm_match_reason` 文案重复度较高，说明 unified 场景判定已形成稳定模式，但多样性偏弱。

### 本次导出

- 英文版（attempt 样本）：`examples/digital_friction_mvp/analysis/attempt_intention_action_status_outcome_dd589b8c.csv`
- 中文版（翻译 action + status）：`examples/digital_friction_mvp/analysis/attempt_intention_action_status_outcome_dd589b8c_zh.csv`

## 2026-03-06 attempt 导出时序对齐修复（action/intention）

### 问题现象

- 原导出脚本按同一 `(agent_id, day, t)` 关联 `mvp_decision_attempt` 与 `agent_status`，会出现：
  - `step_intention = Leave home`
  - 同时刻 `action = Prepare the kitchen for cooking`
- 导致 action 与事件判定输入看起来“语义错位”。

### 根因

- `agent_status` 的 `action` 在 `STEP` 内 `_save(day,t)` 阶段落盘；
- `mvp_decision_attempt` 在 `STEP` 结束后的 `trigger_event_shocks` 中写入；
- 同时刻 join 会把不同流程阶段的数据硬拼到一起，产生一拍错位。

### 代码改造

- 文件：`examples/digital_friction_mvp/analysis/export_attempt_minimal.py`
- 新增参数（向后兼容）：
  - `--join-mode`：`same_t | prev_snapshot`，默认 `prev_snapshot`
  - `--include-step-intention`：`0|1`，默认 `1`
- 新默认对齐逻辑：
  - `prev_snapshot`：按同 agent 的最近过去快照（`status_abs_t < attempt_abs_t` 且取最大）关联 action/status。
- 保留历史复盘能力：
  - `--join-mode same_t` 维持旧行为。

### 导出字段变更

- 旧字段保留：`intention, action, agent_status_status, emitted, outcome`
- 新增字段：
  - `step_intention`
  - `action_snapshot_day`
  - `action_snapshot_t`
  - `join_mode`
  - `join_lag_seconds`

### 验证结果（exp_id=dd589b8c-e4d3-45d8-a7f7-2901ebb6be4b）

- 语法检查：
  - `python -m py_compile examples/digital_friction_mvp/analysis/export_attempt_minimal.py` 通过
- 导出文件：
  - `..._same_t.csv`
  - `..._prev_snapshot.csv`
- 对比结果：
  - 行数：`46 vs 46`（一致）
  - `action_snapshot_day/t` 非空：`45/46 (same_t)` → `46/46 (prev_snapshot)`
  - `step_intention == action`：`2/46 (same_t)` → `46/46 (prev_snapshot)`
  - `join_lag_seconds`：`same_t=0`；`prev_snapshot` 全部 `3600`

### 影响范围

- 仅影响分析导出脚本与 CSV 结构；
- 不改 `main.py` 事件判定链路，不改数据库 schema，不影响仿真运行逻辑。

## 2026-03-07 unified 场景判定 Prompt 语义约束增强（防模板化）

### 变更背景

- 观察到 unified 主判存在明显模板化输出：大量样本重复 `ride_hailing + 0.73 + 相同 reason`。
- 根因之一：Prompt 对输出格式约束严格，但对输入数值语义（范围/方向）约束不足，模型更容易“按示例抄写”。

### 代码修改

- 文件：`examples/digital_friction_mvp/scenario_matching.py`
- 函数：`llm_match_unified_context(...)`
- 变更点：
  - 在 `system_prompt` 中新增“输入语义合同（Input semantics contract）”：
    - `env_levels` 六字段范围为 `0~3`，并明确风险向/支持向方向。
    - `profile` 三字段范围为 `0~1`，并明确能力向/脆弱向方向。
  - 新增“证据优先 + 反模板”规则：
    - 先用 `step_signal/status_summary` 的文本证据做场景判断；
    - 数值字段用于调节置信度，不得在缺少文本证据时强行定场景；
    - 禁止默认 `ride_hailing` 与固定置信度复用。
  - 在 `user_payload` 里新增 `input_semantics` 字段，显式把范围/方向传给模型。
  - 输出示例由“单一 ride_hailing 示例”改为“双示例（digital + non_digital）”，降低锚定效应。

### 不变项

- 输出 schema 不变：仍为
  `is_digital, digital_confidence, scenario_name, scenario_confidence, reason, tags, status`。
- 解析/校验逻辑不变：继续由 `sanitize_unified_match_payload(...)` 负责。
- 运行参数不变：`temperature/timeout/retries` 未调整。

### 校验

- 语法检查通过：
  - `python -m py_compile examples/digital_friction_mvp/scenario_matching.py`

## 2026-03-07 unified 主判去模板化修复（阈值 + 严格 JSON + 模板熔断）

### 问题背景

- unified 模式在近期实验中出现明显场景塌缩：
  - 大部分 attempt 被判到同一场景；
  - `llm_match_confidence` 与 `digital_gate_confidence` 呈现固定值；
  - `llm_match_reason` 文案高度重复。
- 现象说明 unified 主判分支对“模板化输出”缺少抑制与回退机制。

### 本次改动

- 文件：`examples/digital_friction_mvp/config_runtime.py`
  - unified 直通默认阈值由 `0.45` 提高至 `0.75`：
    - `LLM_UNIFIED_MIN_CONFIDENCE`
    - `LLM_UNIFIED_DIGITAL_MIN_CONFIDENCE`
  - 新增模板熔断参数（默认开启）：
    - `LLM_UNIFIED_TEMPLATE_GUARD_ENABLED=1`
    - `LLM_UNIFIED_TEMPLATE_WINDOW=50`
    - `LLM_UNIFIED_TEMPLATE_MIN_SAMPLES=30`
    - `LLM_UNIFIED_TEMPLATE_SCENARIO_SHARE=0.80`
    - `LLM_UNIFIED_TEMPLATE_CONF_BAND=0.02`
    - `LLM_UNIFIED_TEMPLATE_CONF_SHARE=0.80`

- 文件：`examples/digital_friction_mvp/scenario_matching.py`
  - unified prompt 删除“具体场景 + 固定分值”示例，改为仅保留 schema 类型说明。
  - 新增 `parse_unified_match_payload(...)`，执行 unified 专用严格解析：
    - 仅接受 root 为 `dict`；
    - root 为 `list` 时返回 `list_not_allowed`；
    - 非法根类型返回 `root_not_object`。
  - 解析失败/非法 schema 统一返回 `llm_error`，由上层规则链兜底。

- 文件：`examples/digital_friction_mvp/main.py`
  - 新增 `_extract_json_value(...)`，用于保留 JSON 根类型（不再默认把 list 吞成首个 dict）。
  - unified 分支调用 `llm_match_unified_context` 时改用 `_extract_json_value`。
  - 新增 `_evaluate_llm_unified_template_guard(...)`，按“最近窗口”检测模板化异常：
    - dominant 场景占比 > 阈值；
    - dominant 场景内置信度集中度 > 阈值（`|Δ| <= conf_band`）。
  - 当模板化异常触发时：
    - 不采纳该 LLM 场景；
    - 直接 `rule_fallback`；
    - 计入 `step.llm_unified_template_anomaly_count`。
  - 新增审计字段写入 `decision_json`：
    - `llm_unified_template_guard_triggered`
    - `llm_unified_template_window_size`
    - `llm_unified_template_dominant_scenario`
    - `llm_unified_template_dominant_share`
    - `llm_unified_template_conf_band`
    - `llm_unified_template_conf_share`

### 明确不做项

- 本次未加入 step_type-场景“常识硬拦截”。

### 影响范围

- 改动仅影响 unified 场景主判、运行时参数与审计指标；
- 不改数据库表结构；
- 不改 `EVENT_DECIDER_MODE / EVENT_PROB_MODEL / EVENT_EMIT_POLICY` 语义。

## 2026-03-09 概率模型瘦身：移除 `daily_rescaled`，固定 `attempt_hazard`

### 变更原因

- 当前实验全部基于 hazard 口径调参，`daily_rescaled` 分支仅用于历史兼容。
- 保留双分支会增加维护成本与审计歧义（同一配置下存在两套概率语义）。

### 代码改动

- 文件：`examples/digital_friction_mvp/main.py`
  - `EVENT_PROB_MODEL` 仅允许 `attempt_hazard`：
    - 默认值改为 `attempt_hazard`
    - 非 `attempt_hazard` 直接抛错
  - 删除 `daily_rescaled` 路径相关逻辑：
    - 删除 `_compute_agent_probabilities(...)` 中的模型分支（固定走 hazard）
    - 删除 `_flush_decision_attempt_and_metrics(...)` 中的模型分支
    - 删除 `_apply_outcome_and_updates(...)` 中的模型分支
    - 删除未再使用的 `_rescale_event_probs_to_interval(...)` 函数
  - 保留 `decision_audit["prob_model"]` 字段，统一记录为 `attempt_hazard`。

### 行为影响

- 触发概率计算完全由 hazard 路径负责（包含校准项、折返抑制、历史窗口）。
- 历史命令中若设置 `EVENT_PROB_MODEL=daily_rescaled`，现在会启动失败并提示只支持 `attempt_hazard`。
- 审计字段与表结构不变，仅字段取值收敛为单模型。

### 验证

- `python -m py_compile examples/digital_friction_mvp/main.py` 通过。

## 2026-03-10 EconomyBlock 回接与自定义 citizen 自动补机构

### 变更原因

- 需要在 `DigitalFrictionAgent` 路径下接回 `EconomyBlock`，并避免自定义 citizen 因未自动补机构而出现绑定缺失。
- 保持 trigger 主线代码不改，只引入 economy 执行层与可审计的绑定校验。

### 代码改动

- 文件：`examples/digital_friction_mvp/main.py`
  - 接回 `EconomyBlock` 引入（import）。
  - 新增开关：
    - `ECONOMY_BLOCK_ENABLED`（默认开）
    - `ECONOMY_BINDING_AUDIT_STRICT`（默认关）
  - 新增 `audit_economy_bindings(...)`，审计 `firm_id/bank_id/government_id/nbs_id` 绑定状态。
  - 在 workflow 启动阶段（economy 开启时）增加绑定审计步骤。
  - 新增 `_build_digital_friction_blocks()`，按开关将 `EconomyBlock` 注入 `DigitalFrictionAgent` 的 blocks。
  - 在 `AgentsConfig`（economy 开启时）显式补齐机构 agents（firm/government/bank/nbs）。
  - 触发主线保持不改（场景判定与触发计算代码路径未修改）。

- 文件：`packages/agentsociety/agentsociety/cityagent/__init__.py`
  - 新增“自定义 citizen 自动补机构”判定：
    - `citizens` 中若是 `SocietyAgent` 子类（如 `DigitalFrictionAgent`）且 blocks 含 `EconomyBlock`，则自动补齐机构（firm/government/bank/nbs）。
    - 若未配置 `EconomyBlock`，不触发自动补机构，避免 economy 关闭时引入额外机构噪声。

### 间接影响说明（trigger 主线不改，但结果会变）

- 原因：trigger 代码不变，但 trigger 输入来自执行层文本与状态信号；接入 economy 后，输入分布会变化。
- 具体表现：
  - `step_signal` 与 `status_summary` 可能改变；
  - `prefilter_text` 命中与 unified 判定输入会随之变化；
  - 事件参数计算依赖的步骤信号也会变化。
- 结论：这是“输入分布变化导致的间接影响”，不是 trigger 公式本身变更。

### 验证

- `python -m py_compile examples/digital_friction_mvp/main.py` 通过。

## 2026-03-09 兼容参数清理：移除 `EVENT_ALWAYS_EMIT` 与 `SCENARIO_MATCH_MODE`

### 变更原因

- 当前实验路径已收敛到 unified 主判与 `EVENT_EMIT_POLICY`，旧参数仅增加使用歧义。
- 保留旧兼容壳会导致命令可读性下降，并提高排障成本。

### 代码改动

- 文件：`examples/digital_friction_mvp/main.py`
  - 删除 `EVENT_ALWAYS_EMIT -> EVENT_EMIT_POLICY` 的兼容映射分支，改为仅使用 `EVENT_EMIT_POLICY`。
  - 删除旧场景匹配分支（`SCENARIO_MATCH_MODE=="llm_primary"`），统一走 `MATCH_PIPELINE_MODE="llm_unified_primary"` 主干。
  - 删除 `decision_audit["scenario_match_mode"]` 字段写入。

- 文件：`examples/digital_friction_mvp/config_runtime.py`
  - 删除 `scenario_match_mode` 配置字段与校验。
  - `MATCH_PIPELINE_MODE` 仅允许 `llm_unified_primary`。

- 文件：`examples/digital_friction_mvp/analysis/export_trigger_inputs_audit.py`
  - 删除导出列 `scenario_match_mode`，避免空字段残留。

### 文档同步

- 文件：`examples/digital_friction_mvp/friction_shuoming.md`
  - 运行说明改为仅保留 `MATCH_PIPELINE_MODE=llm_unified_primary`。
  - 明确标注 `SCENARIO_MATCH_MODE` 已移除。

- 文件：`examples/digital_friction_mvp/Development_Log.md`
  - 历史实验中涉及 `EVENT_ALWAYS_EMIT=1` 的描述改写为“历史参数”，并用 `EVENT_EMIT_POLICY=force` 表达当前语义。
  - 补充说明旧兼容映射逻辑已失效。

### 行为影响

- 运行命令中不再应使用：
  - `EVENT_ALWAYS_EMIT`
  - `SCENARIO_MATCH_MODE`
- 场景判定路径固定为 unified 主干；旧双路径调试方式不再可用。

### 验证

- `python -m py_compile examples/digital_friction_mvp/main.py examples/digital_friction_mvp/config_runtime.py examples/digital_friction_mvp/analysis/export_trigger_inputs_audit.py` 通过。
- 关键字检索确认核心代码无残留：
  - `SCENARIO_MATCH_MODE`
  - `EVENT_ALWAYS_EMIT`

## 2026-03-09 预筛文本源修正：`status` 枚举与文本状态解耦

### 变更原因

- 运行时 `status` 是 AgentSociety 原生运动枚举（如 sleep/driving），不适合作为数字预筛文本输入。
- 旧逻辑将 `status` 写入 `step_signal.status_text`，导致出现 `1/2` 短值覆盖，数字锚点信息丢失。

### 代码改动

- 文件：`examples/digital_friction_mvp/main.py`
  - 移除快照中的 `runtime_status_map`（原 `gather("status")` 路径不再用于预筛文本）。
  - `_build_agent_context(...)` 中：
    - 不再使用运动枚举 `status` 覆盖 `step_signal.status_text`。
    - 改为优先使用 `status_summary` 作为 `step_signal.status_text` 补充来源（截断到 500 字符）。
  - unified 预筛文本 `prefilter_text` 新增 `status_summary_text` 字段参与命中。
  - `DigitalFrictionAgent.after_forward()`：
    - `friction_step_signal.status_text` 改为读取 `status_summary`，不再读取枚举 `status`。
  - `decision_audit["status_summary_text"]` 截断长度由 `240` 调整为 `500`。

### 行为影响

- `status` 枚举继续保留原语义（运动状态），不参与数字语境预筛。
- 预筛文本来源更稳定，减少“明明是数字语境但被 5333 预筛门拦截”的误判。
- 审计保留更长的 `status_summary_text` 片段，便于复盘。

## 2026-03-10 计划提示词增强：逐步设备渠道内判（`device_needed/device_type`）

### 变更原因

- 现有 `medium` 计划提示词对“数字相关”约束主要在计划级，逐步层面的设备使用判断不够明确。
- 为减少“数字步骤表达不充分”与“线下步骤被误数字化”的情况，新增逐步内判规则。

### 代码改动

- 文件：`examples/digital_friction_mvp/main.py`
  - 在 `AGENT_PLAN_PROMPT_PROFILE=medium` 的计划提示词中新增“Device-channel decision rules (step-level)”：
    - 每步内部先判 `device_needed`（yes/no）
    - 每步内部先判 `device_type`（mobile/pc/kiosk/none）
    - `device_needed=yes` 时，步骤意图需包含明确数字载体动作
    - `device_needed=no` 时，步骤意图要求线下表达，避免数字载体词
    - 强调仅内部思考，不新增输出字段
  - 输出约束编号顺延（`13/14` -> `19/20`），保持规则编号连续且语义不变。

### 行为影响

- 不改变 `PlanBlock` 原生执行流程，仅改变 `medium` 提示词的生成约束。
- JSON 输出 schema 保持不变（仍为 `plan.target + steps[intention,type]`）。
- 预期提升步骤级数字表达清晰度，降低后续预筛误判概率。

### 验证

- `python -m py_compile examples/digital_friction_mvp/main.py` 通过。

## 2026-03-10 问卷与 Prompt 文献对齐方案沉淀（不改核心机制）

### 变更原因

- 当前数字摩擦实验问卷已扩展到多题，但需要进一步给出“构念来源可追溯”的方法学说明。
- 目标是让后续 prompt 调整与问卷解释都能对齐经典文献，而不是经验性口径。

### 本次产出

- 新增文档：`examples/digital_friction_mvp/analysis/survey_prompt_literature_alignment.md`
  - 明确问卷构念锚点与文献来源（TAM、UTAUT、Computer Self-Efficacy、Mastery、eHEALS、CNNIC 中国场景基线）。
  - 给出当前 10 题与构念的一一映射。
  - 给出不改 schema 的 prompt 改造策略（题目定义层 / 分析层 / 作答层）。
  - 给出分阶段落地顺序与对照验证建议（小样本烟测 + paired-seed A/B）。

### 明确不做项

- 本次仅新增方法文档，不修改 `surveys.py`、`agent.py`、`main.py` 逻辑。
- 不改变事件 outcome 三分类与触发主线。

## 2026-03-10 问卷与 Survey Prompt 一次性文献对齐落地

### 变更原因

- 在已有文献对齐方案基础上，直接落地到问卷与作答提示词，减少“题目口径”和“作答口径”不一致。
- 保持主实验机制不变，只增强问卷测量一致性与可解释性。

### 代码改动

- 文件：`examples/digital_friction_mvp/surveys.py`
  - 新增 `_with_recent_window(...)`。
  - 10 个题目标题统一增加“请基于最近7天的真实经历作答”前缀，固定回忆窗口。

- 文件：`packages/agentsociety/agentsociety/agent/agent.py`
  - 调整 `do_survey(...)` 的全局 survey system prompt：
    - 明确“优先最近7天事件证据”；
    - 区分“行为频率题”和“态度强度题”的打分依据；
    - 证据不足时避免极端值。
  - 调整 survey 分析 prompt：
    - 新增 `construct_type`（`acceptance/trust/helplessness/behavior/general`）分类输出。
    - 强化 `memory_query` 对最近7天事件检索。
  - 调整作答上下文 prompt：
    - 增加构念导向的评分规则与一致性约束（分值方向需和证据一致）。

### 明确不做项

- 不改问卷字段名与结果解析 schema。
- 不改 `main.py` 中事件触发逻辑与 outcome 三分类。

## 2026-03-10 Survey 文献对齐作用域收敛（仅 DigitalFrictionAgent）

### 变更原因

- 前一版将 survey 作答 prompt 规则改在框架基类 `do_survey(...)`，会影响所有实验。
- 为避免对其他实验引入不可控偏移，本次将该规则限制为 `DigitalFrictionAgent` 专用。

### 代码改动

- 文件：`packages/agentsociety/agentsociety/agent/agent.py`
  - 在 `do_survey(...)` 增加开关判断：`survey_recent_alignment`。
  - `survey_recent_alignment=True` 时使用“最近7天+构念分类+行为/态度分流评分”规则。
  - `survey_recent_alignment=False` 时回退原有通用 survey prompt 逻辑。

- 文件：`examples/digital_friction_mvp/main.py`
  - 在 `DigitalFrictionAgent` 类上设置 `survey_recent_alignment = True`，启用专用问卷作答规则。

### 行为影响

- digital_friction_mvp：保持文献对齐增强规则生效。
- 其他实验：恢复原有 survey prompt 行为，不受此次增强影响。

## 2026-03-10 平行世界对照管线升级（配对 seed + 设计口径 + QC）

### 变更原因

- 旧版平行世界 runner 使用 `base_seed + world_index`，A/B/C 同组 seed 不一致，不满足严格配对设计。
- 汇总脚本主要输出原始计数，缺少 `AttemptRate/NegShare` 等设计口径指标，且缺配对差值统计与 QC。

### 代码改动

- 文件：`examples/digital_friction_mvp/world_runner.py`
  - 同组 seed 改为严格配对：A/B/C 使用同一 `pair_seed`。
  - 新增批量配对参数：
    - `--n-seeds`
    - `--seed-list`
  - manifest 新增字段：
    - `pair_seed/pair_index/world_order/run_meta_path/config_fingerprint`
    - 分母与运行规模字段（`opportunities_total` 等）
  - 新增固定参数指纹：
    - 输出 `config_snapshot_<group>.json`
    - 若成功 run 的 `config_fingerprint` 不一致则报错。

- 文件：`examples/digital_friction_mvp/main.py`
  - 扩展 `_write_run_metadata(...)`：
    - 写入 `pair_index/pair_seed/world_order/config_fingerprint`
    - 写入分母字段：`decision_intervals_per_day/total_days/opportunities_*`
    - 写入关键开关与口径字段（`event_prob_model/match_pipeline_mode/economy/digital_supply` 等）

- 文件：`examples/digital_friction_mvp/analysis_parallel_worlds.py`
  - 输出改为设计口径指标：
    - `attempt_rate`
    - `emit_given_attempt`
    - `neg_share`
    - `helplessness_delta/trust_delta/avoidance_delta`
  - 保留必要计数，新增 pair/QC/分母字段，支持后续严格配对分析。

- 文件：`examples/digital_friction_mvp/analysis_parallel_paired.py`（新增）
  - 按 seed 做配对差值：`B-A`、`C-A`
  - 指标层输出：
    - pair-level 差值表
    - 聚合统计（均值/中位数/95% bootstrap CI/Wilcoxon p）
    - 方向一致性比例
  - QC 过滤：
    - 仅纳入 `status=ok`
    - 同 seed A/B/C 完整
    - `qc_config_match=1` 且 `config_fingerprint` 一致

### 文档同步

- 文件：`examples/digital_friction_mvp/friction_shuoming.md`
  - 更新平行世界运行示例（多 seed 配对）
  - 增加 paired 统计命令与新增输出文件说明

- 文件：`examples/digital_friction_mvp/parallel_world.md`
  - 更新 seed 说明为“已支持配对 seed”
  - 更新最小改动建议为“summary + paired”两段式分析

---

更新时间：2026-04-04  
文件范围：`examples/digital_friction_mvp/proto/models.py`, `examples/digital_friction_mvp/proto/state_update.py`, `examples/digital_friction_mvp/proto/agent.py`, `examples/digital_friction_mvp/tests/test_state_update.py`

## 本次目标

把 `helplessness update` 从旧的事件记分器，收口为 Stage 1/2 版本的“不可控感主导 + 效能/控制中介”公式，同时保持实现最小化，不扩 workflow、不扩表结构。

## 本次修改记录

### 1) 更新输入/输出 dataclass，直接接入 task self-efficacy 与 felt control

- 修改点：
  - `HelplessnessUpdateInput` 新增 `task_self_efficacy`、`felt_control`
  - `HelplessnessUpdateResult` 新增 `efficacy_loss_term`、`control_loss_term`、`mastery_recovery_term`、`raw_delta_before_damping`、`damping_factor`
- 结果：
  - 更新函数可以直接消费现有心理变量，不需要兼容包装层。

### 2) 负向事件更新改为“底分小、失控感更重、低效能/低控制放大”

- 修改点：
  - `state_update.py` 中重写 helplessness 更新公式
  - 保留 `repetition_delta(...)` 旧逻辑
  - 新增 `efficacy_loss_term(...)`、`control_loss_term(...)`、`damping_factor(...)`
  - 负向事件使用 `raw_delta * damping`
- 结果：
  - 同 outcome 下，delta 不再基本固定，而会被不可控感、task self-efficacy、felt control 拉开。

### 3) 正向事件恢复改为 mastery recovery，而不是旧版统一减分

- 修改点：
  - 新增 `mastery_recovery_term(...)`
  - `success_self`、`success_with_help` 使用不同恢复幅度
  - 结束 failure streak 和“自己做成且 felt_control 高”会得到额外恢复
- 结果：
  - 成功恢复行为更接近 todo 里 Stage 2 的机制设定。

### 4) payload audit 新增 update breakdown，不扩 attempt_rows 顶层 schema

- 修改点：
  - `agent.py` 在 `paper_backed_core` 中新增 `update_breakdown`
  - 输出 `base/repetition/uncontrollability/efficacy/control/support/mastery/damping/effective_delta`
- 结果：
  - 后续可以直接从 `payload_json` 审计 Stage 1/2 是否按预期生效，无需新增 sqlite 列。

### 5) 单元测试改成验证机制方向，而不是旧版固定数值

- 修改点：
  - `test_state_update.py` 重写为行为测试
  - 覆盖：
    - 不可控感越高，负向 delta 越大
    - task self-efficacy 越低，负向 delta 越大
    - felt control 越低，负向 delta 越大
    - helplessness 越高，负向事件的边际伤害越小
    - `success_self` 恢复强于 `success_with_help`
- 结果：
  - 测试口径与新机制一致，不再绑定旧公式。

## 备注

- 本轮没有重跑旧版 baseline。
- 现阶段仍把 `hybrid_full_2day_20260325` 视为最近一次旧公式实验快照参考。

---

更新时间：2026-04-04  
文件范围：`examples/digital_friction_mvp/proto/models.py`, `examples/digital_friction_mvp/proto/outcome_model.py`, `examples/digital_friction_mvp/proto/experience_memory.py`, `examples/digital_friction_mvp/proto/state_update.py`, `examples/digital_friction_mvp/proto/agent.py`

## 本次目标

实现 `Stage 3` 的 avoid 拆分：把 `avoid_without_attempt` 从单一桶拆成更接近机制含义的三类，并且让这个分类真正进入长期更新，而不是只停留在日志里。

## 本次修改记录

### 1) 给 avoid 增加显式原因标签

- 修改点：
  - `AttemptOutcome` 新增 `avoid_reason / avoid_reason_source / avoid_reason_confidence / avoid_reason_note`
  - `RecentEpisode` 新增 `avoid_reason`
  - `HelplessnessUpdateInput` 新增 `avoid_reason`
- 结果：
  - 后续更新链路和日志都能知道这次 avoid 到底更像 helplessness、risk 还是 low value。

### 2) 用现有 task appraisal 信号做轻量级 avoid 原因拆分

- 修改点：
  - 在 `outcome_model.py` 新增 `infer_avoid_reason(...)`
  - 规则综合使用：
    - `task_self_efficacy`
    - `felt_control`
    - `perceived_task_risk`
    - `task_value`
    - `recent_same_task_failure_count`
  - `agent.py` 在 `avoid_without_attempt` 时调用该分类器
- 结果：
  - 不需要再新建一套 avoid 专用 LLM pipeline，也能把三种 avoid 拉开。
  - 这轮本质上是“规则先决，但输入信号已经能复用现有 hybrid task appraisal”。

### 3) 让不同 avoid 原因在 helplessness 更新里不再同权

- 修改点：
  - `state_update.py` 新增 `AVOID_REASON_MULTIPLIERS`
  - `helpless_avoid = 1.0`
  - `risk_avoid = 0.35`
  - `low_value_avoid = 0.15`
  - 仅在 `avoid_without_attempt` 时启用该 multiplier
- 结果：
  - 同样是 avoid，只有 `helpless_avoid` 会明显推高 helplessness。

### 4) 让 avoid 分类也影响经验记忆，而不只是当前轮 delta

- 修改点：
  - `experience_memory.py` 中把 `avoid_without_attempt` 的 task self-efficacy 影响拆开
  - `helpless_avoid` 继续明显降低效能感
  - `risk_avoid / low_value_avoid` 的伤害更轻
  - `rationale_memory` 中不同 avoid reason 使用不同文本
- 结果：
  - 行为层和心理层开始被分开，不再把所有“没做”都记成同一种脆弱性积累。

### 5) payload 审计补充 avoid reason 证据

- 修改点：
  - `agent.py` 在 `decision` 和 `paper_backed_core` 中新增 avoid reason 信息
  - 同时输出分类 scores 和 `avoid_reason_multiplier`
- 结果：
  - 后续可以直接从 `payload_json` 审计 avoid 拆分是否按预期工作。

### 6) 测试补到 Stage 3 口径

- 修改点：
  - `test_outcome_model.py` 新增 avoid 分类测试
  - `test_state_update.py` 新增 `helpless_avoid > risk_avoid > low_value_avoid` 测试
  - `test_experience_memory.py` 新增“非 helpless avoid 对 task self-efficacy 伤害更轻”测试
- 结果：
  - Stage 3 的关键方向现在有测试兜住。

## 验证

- `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_state_update.py examples/digital_friction_mvp/tests/test_outcome_model.py examples/digital_friction_mvp/tests/test_experience_memory.py`
- `python -m py_compile examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/outcome_model.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/state_update.py examples/digital_friction_mvp/proto/agent.py`

## 备注

- 本轮没有单独新建 avoid 专用 LLM 分类器。
- 先把最关键的“avoid 不再单桶计入 helplessness”落下去，后面如果需要再把人工抽样核查或更重的 hybrid 分类补上。

---

更新时间：2026-04-04  
文件范围：`examples/digital_friction_mvp/proto/models.py`, `examples/digital_friction_mvp/proto/experience_memory.py`, `examples/digital_friction_mvp/proto/state_update.py`, `examples/digital_friction_mvp/proto/agent.py`

## 本次目标

实现 `Stage 4` 的 controllability 长期保护：把“可控成功”变成一个慢变量，并让它降低未来负向事件对 helplessness 的敏感度，而不是只给一次性恢复分。

## 本次修改记录

### 1) 给 task-domain memory 增加 controllable success 痕迹

- 修改点：
  - `TaskDomainState` 新增 `controllable_success_memory`
  - `MemoryFeatures` 同步暴露该字段，便于更新函数和 payload 直接使用
- 结果：
  - `task_self_efficacy` 和 `controllable_success_memory` 现在开始分工：
    - 前者是中速的“我现在能不能行”
    - 后者是慢速的“我过去有没有积累过自己可控地做成”

### 2) 只在高质量可控成功时积累长期保护

- 修改点：
  - `experience_memory.py` 新增 `_controllable_success_gain(...)`
  - 主要规则：
    - `success_self` 且 `felt_control >= 60` 且 `perceived_uncontrollability == 0` 时强积累
    - `success_with_help` 只有在高质量帮助成功时才给较小积累
    - 连败后自己做成会额外多给一点 gain
    - `controllable_success_memory` 按天缓慢衰减
- 结果：
  - 不是所有 success 都会形成长期保护，只有“真的像自己掌控地做成”的 success 才会留下更明显痕迹。

### 3) protection 用乘性方式进入 helplessness 更新

- 修改点：
  - `state_update.py` 新增 `controllable_success_protection(...)`
  - 负向事件改为：
    - 先得到当前正向压力 `raw_delta`
    - 再乘 `(1 - protection)`
    - 最后再乘 `damping`
- 结果：
  - `controllable_success_memory` 不再是假装“回血”的固定减项，而是真正降低未来负向压力的打击强度。

### 4) payload 审计补充 controllability 证据

- 修改点：
  - `agent.py` 在调用 helplessness 更新时传入 `controllable_success_memory`
  - `paper_backed_core.update_breakdown` 新增 `controllable_success_protection`
  - `paper_backed_core` 新增当前 `controllable_success_memory`
- 结果：
  - 后面可以直接从 payload 审计“为什么这个 agent 更耐挫”，而不是只看最终曲线。

### 5) 测试补到 Stage 4 口径

- 修改点：
  - `test_state_update.py` 新增“高 controllable success memory 会降低同样负向事件 delta”测试
  - `test_experience_memory.py` 新增：
    - 自助成功比被帮助成功更容易积累 memory
    - memory 会缓慢衰减，而不是僵住不动
- 结果：
  - Stage 4 的核心行为现在已经被测试锁住。

## 验证

- `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_state_update.py examples/digital_friction_mvp/tests/test_experience_memory.py examples/digital_friction_mvp/tests/test_outcome_model.py`
- `python -m py_compile examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/state_update.py examples/digital_friction_mvp/proto/agent.py`

## 备注

- 本轮没有新建独立 mastery memory 模块，也没有额外扩表。
- 先把最关键的“长期保护是慢变量 + 乘性调节”落下去，后面如果需要再继续细化 `enabling_support / substituting_support` 或更强的 mastery 条件。

---

更新时间：2026-04-04  
文件范围：`examples/digital_friction_mvp/proto/models.py`, `examples/digital_friction_mvp/proto/outcome_model.py`, `examples/digital_friction_mvp/proto/experience_memory.py`, `examples/digital_friction_mvp/proto/state_update.py`, `examples/digital_friction_mvp/proto/agent.py`

## 本次目标

实现 `Stage 5` 的 support 间接化：让 support 更像“帮助理解和保留主体性”的机制，而不是一个简单的 direct buffer。

## 本次修改记录

### 1) 新增轻量 support mode，把帮助分成 enabling 和 substituting

- 修改点：
  - `AttemptOutcome` 新增 `support_mode / support_mode_source`
  - `outcome_model.py` 新增 `infer_support_mode(...)`
  - 用现有 `felt_control + expected_help_effectiveness + support_quality` 规则区分：
    - `enabling_support`
    - `substituting_support`
- 结果：
  - 同样是“求助后完成”，现在可以开始区分“帮你学会了”还是“帮你做掉了”。

### 2) support 的 direct buffer 明显缩小

- 修改点：
  - `state_update.py` 中 `SUPPORT_BUFFERS` 从较明显缓冲改成更小的 `0.15 / 0.35`
- 结果：
  - support 还保留一点直接保护，但已经不是主要作用路径。

### 3) success_with_help 的即时恢复改为看 support mode 和主观帮助效果

- 修改点：
  - `HelplessnessUpdateInput` 新增 `expected_help_effectiveness` 和 `support_mode`
  - `mastery_recovery_term(...)` 中，`success_with_help` 不再只按 `support_quality` 给恢复
  - 只有 `enabling_support` 且帮助效果/控制感较高时，才给更像“修复 agency”的即时恢复
- 结果：
  - 同样是 help success，恢复强度现在会分层。

### 4) support 的主要作用迁到 task self-efficacy 和 controllability memory

- 修改点：
  - `experience_memory.py` 中：
    - `success_with_help + enabling_support` 给更高的 `task_self_efficacy` 提升
    - `success_with_help + substituting_support` 只给较小提升
    - `failure_even_with_help + enabling_support` 的伤害略轻
    - 只有 enabling support 才更可能留下 `controllable_success_memory`
- 结果：
  - support 开始主要通过中介变量修复后续行为，而不是靠一次性减分。

### 5) payload 审计补充 support mode 证据

- 修改点：
  - `agent.py` 在 `decision` 中写入 `support_mode`
  - `paper_backed_core.support_effectiveness` 中补入 `support_mode / support_mode_source / mode_note`
- 结果：
  - 后续可以直接从 payload 解释：
    - 为什么有的求助后更敢自己试
    - 为什么有的求助后只是更依赖帮助

### 6) 测试补到 Stage 5 口径

- 修改点：
  - `test_outcome_model.py` 新增 support mode 分类测试
  - `test_state_update.py` 新增 enabling vs substituting 的 help success 恢复差异测试
  - `test_experience_memory.py` 新增 enabling support 会带来更强效能提升和更多 controllability memory 的测试
- 结果：
  - Stage 5 的关键方向现在已经有测试锁住。

## 验证

- `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_state_update.py examples/digital_friction_mvp/tests/test_experience_memory.py examples/digital_friction_mvp/tests/test_outcome_model.py`
- `python -m py_compile examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/outcome_model.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/state_update.py examples/digital_friction_mvp/proto/agent.py`

## 备注

- 本轮没有新建独立 support 子模块，也没有碰 workflow 或表结构。
- 先把最关键的“support 主要通过中介修复，而不是 direct buffer”落下去，后面如果需要再继续细化更丰富的帮助类型。
