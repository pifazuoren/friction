# frictionchangeLog

这个文件用于记录 `digital friction` 相关代码的后续修改。

记录原则：

- 只要发生与 `digital friction` 机制、实验、分析相关的实际代码改动，就追加一条记录
- 每条记录尽量写清楚修改目的、涉及文件、核心改动、验证情况
- 采用追加式记录，不覆盖历史
- 纯讨论不记；如果是与 friction 机制实现直接相关的重要文档调整，可按需要补记

建议格式：

```md
## YYYY-MM-DD

### 变更标题
- 目的：
- 涉及文件：
- 核心改动：
- 验证：
- 备注：
```

---

## 2026-04-04

### 初始化 frictionchangeLog
- 目的：建立 digital friction 相关代码修改的独立日志，便于后续追踪机制实现、参数调整和实验分析演化。
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 新建 friction 专用变更日志文件
  - 约定后续相关代码修改都追加记录
- 验证：
  - 文件已创建
- 备注：
  - 当前这次是日志初始化，不对应功能代码改动

## 2026-04-04

### Stage 1/2 helplessness update 落地
- 目的：把 helplessness 更新从旧的事件记分器改成“不可控感主导 + 效能/控制中介”的精简公式，并保留最小可审计 breakdown。
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/models.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/Development_Log.md`
- 核心改动：
  - `HelplessnessUpdateInput` 新增 `task_self_efficacy` 与 `felt_control`
  - `HelplessnessUpdateResult` 新增 `efficacy_loss_term/control_loss_term/mastery_recovery_term/raw_delta_before_damping/damping_factor`
  - 负向事件改为 `base + repetition + uncontrollability + efficacy loss + control loss - support buffer`，再乘 damping
  - 正向事件改为 `base - mastery_recovery_term`，区分自助成功与被帮助成功
  - `payload_json.paper_backed_core` 新增 `update_breakdown`，不扩表结构
  - 单元测试改为验证相对行为，不再锁旧版固定分数
- 验证：
  - 待运行 `pytest examples/digital_friction_mvp/tests/test_state_update.py`
- 备注：
  - 本轮不补跑旧版 baseline；现有 `hybrid_full_2day_20260325` 作为最近一次旧公式快照参考

## 2026-04-04

### Stage 3 avoid 拆分落地
- 目的：把 `avoid_without_attempt` 从单一桶拆成 `helpless_avoid / risk_avoid / low_value_avoid`，避免把所有回避都继续当成 helplessness。
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/models.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/outcome_model.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_outcome_model.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 为 `AttemptOutcome`、`RecentEpisode`、`HelplessnessUpdateInput` 增加 avoid reason 相关字段
  - 新增基于现有 `task_appraisal` 信号的规则分类器，用 `felt_control / task_self_efficacy / perceived_task_risk / task_value / recent_same_task_failure_count` 拆分 avoid 原因
  - `state_update.py` 对 `avoid_without_attempt` 引入 reason multiplier，仅让 `helpless_avoid` 明显推高 helplessness
  - `experience_memory.py` 让 `risk_avoid / low_value_avoid` 对 task self-efficacy 的伤害更轻，并把 avoid reason 写入 recent episode / rationale
  - `agent.py` 把 avoid reason 写进 `decision` 和 `payload_json.paper_backed_core`
- 验证：
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_state_update.py examples/digital_friction_mvp/tests/test_outcome_model.py examples/digital_friction_mvp/tests/test_experience_memory.py`
  - `python -m py_compile examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/outcome_model.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/state_update.py examples/digital_friction_mvp/proto/agent.py`
- 备注：
  - 本轮优先走“规则先决 + 复用已有 task_appraisal hybrid 信号”的轻量实现，没有再新起一套 avoid 专用 LLM 子模块

## 2026-04-04

### Stage 4 controllability 长期保护落地
- 目的：把 `controllable_success_memory` 接进长期状态，让高质量可控成功形成慢速保护，并通过乘性 protection 降低未来负向压力的伤害。
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/models.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - `TaskDomainState` 和 `MemoryFeatures` 新增 `controllable_success_memory`
  - `experience_memory.py` 在高质量可控成功时累积该 memory，并按天缓慢衰减
  - 只让 `success_self` 的高控制成功强积累；`success_with_help` 只有在高质量帮助成功时才给较小积累
  - `state_update.py` 新增 `controllable_success_protection(...)`，以乘性 protection 降低负向 `raw_delta`
  - `agent.py` 把当前 memory 传入 helplessness 更新，并写入 `payload_json.paper_backed_core`
- 验证：
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_state_update.py examples/digital_friction_mvp/tests/test_experience_memory.py examples/digital_friction_mvp/tests/test_outcome_model.py`
  - `python -m py_compile examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/state_update.py examples/digital_friction_mvp/proto/agent.py`
- 备注：
  - 本轮没有把它做成新表或独立 memory 系统，而是并进现有 task-domain memory，保持实现紧凑

## 2026-04-04

### Stage 5 support 间接修复落地
- 目的：把 support 从较直接的状态缓冲，改成主要通过 `expected_help_effectiveness / task_self_efficacy / controllable_success_memory` 的间接修复路径起作用，只保留很小的 direct buffer。
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/models.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/outcome_model.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_outcome_model.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 新增轻量 `support_mode`：`enabling_support / substituting_support`
  - 把 direct `SUPPORT_BUFFERS` 缩小到微弱水平
  - `success_with_help` 的即时恢复改由 `support_mode + expected_help_effectiveness + felt_control` 决定，不再只看 `support_quality`
  - `experience_memory.py` 中让 enabling support 明显更能提升 task self-efficacy，并更可能留下 controllable success memory
  - `agent.py` 把 support mode 写进 decision 和 `paper_backed_core.support_effectiveness`
- 验证：
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_state_update.py examples/digital_friction_mvp/tests/test_experience_memory.py examples/digital_friction_mvp/tests/test_outcome_model.py`
  - `python -m py_compile examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/outcome_model.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/state_update.py examples/digital_friction_mvp/proto/agent.py`
- 备注：
  - 本轮没有扩成独立 support 子模块，而是用现有 task appraisal 信号做轻量 support mode 分流

## 2026-04-05

### 基于 04050058 实验分析的预先机制修正
- 目的：
  - 根据 `/Users/pifazuoren/Downloads/AgentSociety-main/exp- analysis/04050058.md` 中暴露出的核心问题，先行修正一批最影响下一轮实验解释力的机制点
  - 主要针对：`task appraisal` 几乎恒定、`seed` 差异未传导、`support` 长期停留在 `substituting_support`、`controllable_success_memory` 未激活、整体 helplessness 增幅过猛、`uncontrollability` 在 hybrid 下仍默认关闭
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/config_runtime.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/outcome_model.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_update.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - `config_runtime.py`
    - 当 `PROTO_LLM_PSYCHOLOGY_MODE=hybrid` 且未显式设置 `PROTO_LLM_UNCONTROLLABILITY_MODE` 时，默认让 uncontrollability 也走 `hybrid`
    - 目的：避免 hybrid 实验里最核心的 `perceived_uncontrollability` 仍停留在 rule-only
  - `agent.py`
    - 调整 agent 级随机种子构造，把 `EXP_SEED / PARALLEL_PAIR_SEED / WORLD_NAME` 纳入 `base_rng_seed`
    - 目的：让 paired seed 的差异真正进入策略采样和 outcome 采样，而不是只由 `agent_id/day/t/task_id` 近似决定
  - `llm_psychology.py`
    - 加细 `task appraisal` 的 cache key，把 `world_context / profile_summary / recent_episode_summary` 的关键信息加入缓存粒度
    - 加细 `strategy deliberation` 的 cache key，把 `task_appraisal / task_self_efficacy / recent_negative_feedback_ratio / recent_same_task_failure_count` 加入缓存粒度
    - 修改 `resolve_task_appraisal(...)` 的 prompt：
      - 增加“不同上下文应输出不同值”的明确约束
      - 将原先高度固定的示例值替换成更中性的示例
      - 增加 calibration notes，鼓励基于当前 world/profile/recent experience 产生变化
    - 目的：缓解 `felt_control / expected_help_effectiveness / task_value` 长期近似常数的问题
  - `outcome_model.py`
    - 调整 `infer_perceived_uncontrollability(...)`
      - 仍保留高风险 friction 的高不可控判定
      - 但把“所有高 friction 直接给 2”改为更细化的 `1/2` 区分
    - 调整 `infer_support_mode(...)`
      - 降低进入 `enabling_support` 的门槛
      - 提高高质量 support 的加分
      - 让 `success_with_help` 更容易被识别成 `enabling_support`
    - 目的：让 support 不再几乎永远停留在 `substituting_support`
  - `experience_memory.py`
    - 放宽 `controllable_success_memory` 的增长条件
      - `success_self` 不再必须等到极高 `felt_control` 才能积累
      - `success_with_help` 在 `enabling_support` 下也更容易获得小幅记忆积累
    - 下调 `task_appraisal_shift` 对 `effective_helplessness` 的推高强度与范围
    - 目的：让长期保护项更容易出现，同时减少 appraisal 固定值对系统的持续放大
  - `state_update.py`
    - 整体下调 `BASE_DELTAS`
    - 下调 `repetition_delta`
    - 下调 `efficacy_loss_term / control_loss_term`
    - 下调 `UNCONTROLLABILITY_DELTAS` 的绝对量级，但保留其主导地位
    - 加强 `damping_factor`
    - 增强 `controllable_success_protection`
    - 将 direct `support_buffer` 进一步缩小，并限制为主要只在 help-involved negative events 中提供很小的缓冲
    - 调整 `mastery_recovery_term`，使 `success_self` 和高质量 `enabling_support` 成功更容易产生恢复
    - 目的：缓解 baseline 也快速冲向 `100` 的饱和问题，同时让 support 更符合“以间接修复为主”的设计
- 验证：
  - `pytest examples/digital_friction_mvp/tests/test_state_update.py`
  - `pytest examples/digital_friction_mvp/tests/test_experience_memory.py`
  - `pytest examples/digital_friction_mvp/tests/test_outcome_model.py`
  - `pytest examples/digital_friction_mvp/tests/test_llm_psychology.py`
  - `pytest examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py examples/digital_friction_mvp/tests/test_runtime.py`
  - `python -m py_compile examples/digital_friction_mvp/config_runtime.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/proto/llm_psychology.py examples/digital_friction_mvp/proto/outcome_model.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/state_update.py`
- 备注：
  - 这轮修改是在讨论 `04050058.md` 的“下一步修改方向”时提前落下的实现，不是一次纯计划输出
  - 这轮修改遵循 `/Users/pifazuoren/Downloads/AgentSociety-main/helplessnessupdatetodo.md` 的方向约束，重点对应 Stage 1、2、4、5，并补了 seed 与 appraisal 动态性两个实验性基础问题
  - 本轮只完成代码修改与单测验证，尚未重新跑完整 world experiment

## 2026-04-05

### fixed multi-seed baseline / paired-seed 对照链补齐
- 目的：
  - 对齐 `/Users/pifazuoren/Downloads/AgentSociety-main/helplessnessupdatetodo.md` 第 0 阶段里“冻结 baseline，固化多 seed 对照”的要求
  - 解决当前 `paired-seed` 分析仍偏旧三世界口径、`world_runner.py` 不能一次产出 paired 结果的问题
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/analysis_parallel_paired.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/world_runner.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/parallel_world.md`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_parallel_paired.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/0405todo.md`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - `analysis_parallel_paired.py`

## 2026-04-06

### task appraisal / uncontrollability / event appraisal 的 memory 输入补强
- 目的：
  - 解决 `digital friction` 里最关键的中间层 prompt 吃 memory 太浅的问题，尤其是：
    - `task appraisal` 只看到很薄的 3 个画像数值
    - `uncontrollability calibrator` 主要只看当前事件，没有吃到“行动-结果脱钩”的历史证据
    - `event appraisal` 没有显式比较“原本预期”和“这次结果”的落差
  - 按之前讨论的施工顺序，先补上游 memory packet，再把它接进 `task appraisal -> uncontrollability calibrator -> event appraisal`
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/uncontrollability_calibrator.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_llm_psychology.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - `proto/agent.py`
    - 新增 `_compress_background_story(...)`，把 `background_story` 压成更适合 prompt 的短摘要
    - 新增 `DigitalHelplessnessAgent._build_task_appraisal_profile_summary()`，把 `age / education / occupation / persona / background_summary / digital_experience / vision_limit / past_fraud_experience` 统一打包成 `profile_summary_v2`
    - 新增 `_extract_same_task_event_tail(...)` 与 `_build_task_relevant_memory_packet(...)`
    - 在 task appraisal 前显式构建 `task_relevant_memory_packet`，其中包含：
      - 同类任务累计尝试/成功/失败/回避
      - 同类任务 failure streak / recent negative EMA / last outcome
      - same-task help 成败统计
      - recent same-task event tail
      - controllable success evidence
    - 把 `profile_summary` 与 `task_relevant_memory_packet` 接进 `resolve_task_appraisal(...)`
    - 把 `pre_event_task_appraisal` 与 `task_relevant_memory_packet` 接进 `calibrate_uncontrollability(...)`
    - 把 `pre_event_task_appraisal` 与 `task_relevant_memory_lite` 接进 `resolve_event_appraisal(...)`
    - 在 `decision` / `payload_json` 里补记 `pre_event_felt_control`、`pre_event_task_risk`、`pre_event_help_effectiveness`、`same_task_failure_count`、`same_task_controllable_success_memory`、`profile_summary`、`task_relevant_memory`
  - `proto/llm_psychology.py`
    - `TASK_APPRAISAL_PROMPT_VERSION` 升级为新的 memory-packet 版本，防止误复用旧缓存
    - 新增 `age / education / persona / appraisal / history / recent-outcome-pattern` 的分桶 helper
    - 扩展 `_build_task_appraisal_cache_key(...)`，让新增画像和同类任务历史真正进入 cache 粒度
    - 扩展 `_build_task_appraisal_user_payload(...)`，把 `Task-Specific Memory` 从几个率值升级为完整 `task_relevant_memory`
    - 扩展 `resolve_task_appraisal(...)` 签名，新增 `task_relevant_memory`
    - 扩展 `_build_event_appraisal_cache_key(...)`
    - 扩展 `resolve_event_appraisal(...)` 签名，新增：
      - `pre_event_task_appraisal`
      - `task_relevant_memory_lite`
    - 重写 `event appraisal` 输入块，加入：
      - `current_event`
      - `current_state`
      - `pre_event_appraisal`
      - `same_task_recent_context`
      - 明确的 comparison rules
    - 让 event appraisal 更像在判断“这次结果相对原本预期有多打击”，而不是只看 outcome 本身
  - `proto/uncontrollability_calibrator.py`
    - 新增 `pre_event_task_appraisal` 和 `task_relevant_memory` 输入
    - 扩展 calibrator cache key，把 `felt_control / expected_help_effectiveness / same-task failure history / controllable success evidence / avoid reason / recent pattern` 纳入
    - 重写 `_build_user_payload(...)`，改成：
      - `current_event`
      - `current_state`
      - `world_env_levels`
      - `pre_event_appraisal`
      - `same_task_history`
      - `rule_baseline_uncontrollability`
    - 在 calibrator prompt 中明确加入规则：
      - 重点判断 action-outcome decoupling
      - `risk_avoid` 不自动等于高 uncontrollability
      - `low_value_avoid` 不自动等于高 uncontrollability
      - same-task controllable success 是重要反证
  - 测试：
    - `test_llm_psychology.py`
      - 补了 `task appraisal` prompt 是否真正包含增强画像与同类任务历史的测试
      - 补了 `event appraisal` prompt 是否真正包含 `pre_event_appraisal` 与 same-task context 的测试
    - `test_uncontrollability_calibrator.py`
      - 补了 calibrator prompt 是否真正包含 `pre_event_appraisal` 与 `same_task_history` 的测试
- 验证：
  - `python -m py_compile examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/proto/llm_psychology.py examples/digital_friction_mvp/proto/uncontrollability_calibrator.py examples/digital_friction_mvp/tests/test_llm_psychology.py examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py`
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_llm_psychology.py examples/digital_friction_mvp/tests/test_uncontrollability_calibrator.py`
  - 结果：`24 passed`
- 备注：
  - 这轮没有改 `state_update.py` 公式本身，重点仍然是“先喂活中间层”
  - 这轮也没有改 `experience_memory.py` 的底层存储结构，而是先在 `agent.py` 层做 runtime packet 组装
  - `task appraisal` 现在已经不再只依赖 3 个画像数值；但更强的 profile 结构化标签（例如 `risk_orientation / support_preference / offline_preference`）本轮还没有加到 `profiles.json`
    - 从旧的固定 `B-A / C-A` 三世界格式，扩展成 `baseline vs multiple comparison worlds`
    - 默认支持当前四世界运行结果中的三个 comparison world
    - 增加 per-contrast QC、contrast key、direction profile，并保留 legacy `--high-world / --low-world` 兼容入口
  - `world_runner.py`
    - 新增 `--summarize-paired`
    - 一次运行即可连续产出：
      - `exp_group_manifest`
      - `config_snapshot`
      - `parallel_world_summary`
      - `parallel_stage_summary`
      - `parallel_world_paired_diffs`
      - `parallel_world_paired_stats`
      - `parallel_world_paired_qc`
    - 新增 paired baseline / compare world / direction override / summary script / paired script 参数
    - 加入 baseline world 和 compare world 的基本防呆校验
  - `parallel_world.md`
    - 补充新的推荐用法和脚本文档说明
  - 新增 `test_parallel_paired.py`
    - 验证四世界 summary 的多 world paired 输出
    - 验证 `world_runner --summarize-paired` 的整条输出链

## 2026-04-06

### Task Appraisal Prompt 第一轮语义重构
- 目的：
  - 对齐 `/Users/pifazuoren/Downloads/AgentSociety-main/prompttodo.md` 中“先稳住接口，再重写语义”的计划
  - 只重构 `task appraisal` 这一层的 prompt，使 `felt_control / perceived_task_risk / task_value / expected_help_effectiveness` 更有机会形成可区分、可拉开的中间测量
  - 参考 `/Users/pifazuoren/Downloads/AgentSociety-main/agentsocietyprompt5.md` 中 4 篇论文总结的 prompt 写法，吸收其“结构化信息块、模块单职责、JSON-only、memory/context 显式注入”的设计
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 在 `llm_psychology.py` 中新增 `TASK_APPRAISAL_PROMPT_VERSION = "v2_theory_grounded_rubric_20260406"`，并写入 `_build_task_appraisal_cache_key(...)`
  - 重写 `resolve_task_appraisal(...)` 使用的 `system_prompt`
    - 明确模块只做 appraisal，不做策略选择，不做结果预测
    - 明确 5 个构念的定义
    - 明确构念边界，减少“不会做 / 怕风险 / 不值得做 / 低控制感”互相混淆
    - 加入 anti-middle 约束，要求只有证据真正模糊时才使用 `45-55`
    - 加入“先内部判断主因，再分别打分”的顺序约束，但不新增输出 schema
  - 重写 `user_payload` 的组织方式
    - 从原先较平的一组上下文字段，改成显式信息块：
      - `Agent Profile`
      - `Current Task`
      - `World / Stage Context`
      - `Current Status`
      - `Task-Specific Memory`
      - `Recent Experience`
      - `Digital Emotion State`
    - 新增 `Scale Anchors`、`Output Schema Template`、`Calibration Notes`
  - 删除原先容易形成锚定的中间 numeric example
    - 去掉 `61 / 58 / 47 / 54 / 63` 这一类中间示例
    - 改为 schema template only，不再给模型默认中间答案
  - 为 5 个维度补上 5 档量表锚点
    - `0-20 / 21-40 / 41-60 / 61-80 / 81-100`
    - 让模型更明确每个分数段分别代表什么
  - 重写 calibration notes
    - 从零散提醒改为构念判别规则
    - 强调 difficulty / risk / control / value / help 之间要分开判断
- 验证：
  - `python -m py_compile /Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py`
  - `PYTHONPATH=examples/digital_friction_mvp pytest /Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_llm_psychology.py`
  - 结果：`14 passed`
- 备注：
  - 本轮没有改 `TaskAppraisalResult` schema
  - 本轮没有改 `state_update.py` 的 helplessness 公式
  - 本轮没有改 cache 粗分桶策略本身，只做了 prompt 版本隔离
  - 本轮没有新增 `primary_barrier` 字段，仍采用“内部先分原因，再输出原有 5 个分数”的最小改动路线
- 验证：
  - `pytest examples/digital_friction_mvp/tests/test_parallel_paired.py`
  - `pytest examples/digital_friction_mvp/tests/test_parallel_summary.py`
  - `python -m py_compile examples/digital_friction_mvp/analysis_parallel_paired.py examples/digital_friction_mvp/world_runner.py`
- 备注：
  - 这轮补齐的是“运行与汇总链”，不是“已经跑完新的固定 baseline”
  - `parallel_stage_summary` 与 `parallel_world_summary` 的统计口径问题本轮没有重构，仍属于后续分析层修正

### Digital Friction 去冗余清理：移除废弃的 strategy_bias 链路
- 时间：
  - 2026-04-06 23:44:52 CST
- 目的：
  - 清理 `digital_friction_mvp` 中已经退出主运行链的旧 `strategy_bias` 结构
  - 减少“代码里看起来还有一套旧机制，但实际已经不用”的理解负担
  - 保留当前真正使用的 `strategy_deliberation` 主路径，避免后续继续在两个近似模块之间来回混淆
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/config_runtime.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/models.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/attempt_strategy.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_llm_psychology.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_attempt_strategy.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 从 runtime 配置中移除废弃的 `proto_llm_strategy_bias_enabled` 和 `proto_llm_strategy_bias_max_shift`
  - 从 `models.py` 中移除旧的 `StrategyBiasResult` 以及 `MemoryFeatures` 里对应的 `llm_*_bias` 字段
  - 从 `experience_memory.py` 中删掉这些旧 bias 特征的构造逻辑
  - 从 `attempt_strategy.py` 中移除旧的 bias 参数入口和 `_apply_legacy_bias(...)`
  - 从 `llm_psychology.py` 中移除整条 `resolve_strategy_bias(...)` 相关缓存、sanitize、cache key 和解析逻辑
  - 从 `agent.py` 的审计输出中删掉 `legacy_strategy_bias_role` 这个已无实际意义的旧标记
  - 清理测试文件里仍然引用旧 bias 链路的 import、环境变量设置和用例
- 验证：
  - `rg -n "strategy_bias|resolve_strategy_bias|llm_attempt_self_bias|llm_help_seek_bias|llm_avoid_bias|_STRATEGY_BIAS_CACHE|StrategyBiasResult|proto_llm_strategy_bias" examples/digital_friction_mvp`
    - 结果：无残留引用
  - `python -m py_compile examples/digital_friction_mvp/config_runtime.py examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/attempt_strategy.py examples/digital_friction_mvp/proto/llm_psychology.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/tests/test_llm_psychology.py examples/digital_friction_mvp/tests/test_attempt_strategy.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_llm_psychology.py examples/digital_friction_mvp/tests/test_attempt_strategy.py`
    - 结果：`22 passed`
- 备注：
  - 这轮是“去掉已经废弃的旧壳”，不是新增机制
  - 当前保留并继续使用的是 `strategy_deliberation`
  - 其他可能的冗余点，例如 `survey_summary` 的重复读取、部分重复落日志、年龄/画像分桶逻辑重复，仍可作为下一轮继续清理的候选项

### Digital Friction 去冗余清理：收束 survey_summary 与 proto 决策状态写回
- 时间：
  - 2026-04-06 23:52:04 CST
- 目的：
  - 继续清理 `agent.py` 中“同一逻辑写了多遍”的重复结构
  - 在不改变行为的前提下，让 `forward()` 和 interview 路径更容易读懂、后续更容易维护
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 新增 `_build_survey_summary()` helper
    - 把 `survey_helplessness_index / survey_withdrawal_index / survey_self_efficacy_index / survey_support_index / survey_usefulness_index / survey_anxiety_index`
      的读取和 clamp 逻辑收成一处
    - `do_interview()` 中的 stage interview 和 final interview 都改为调用这个 helper
    - `forward()` 中读取 survey 指标时也改为先拿统一的 `survey_summary`
  - 新增 `_persist_proto_decision_state()` helper
    - 把 `proto_task_appraisal` 和 `proto_strategy_deliberation` 这一对状态写回收成一个统一入口
  - 删除 `forward()` 中事件前那一轮重复 proto 写回
    - 之前 `task_appraisal` 和 `strategy_deliberation` 在事件处理中途先写一次，最后又写一次
    - 这轮检查后确认两次写回之间没有再从 status 里读取这两个值，因此保留最后统一写回即可
- 验证：
  - `python -m py_compile examples/digital_friction_mvp/proto/agent.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_llm_psychology.py examples/digital_friction_mvp/tests/test_attempt_strategy.py examples/digital_friction_mvp/tests/test_state_schema.py`
    - 结果：`27 passed`
  - `rg -n "survey_summary = \\{|_build_survey_summary|_persist_proto_decision_state|proto_task_appraisal|proto_strategy_deliberation" examples/digital_friction_mvp/proto/agent.py`
    - 结果：确认 survey 读取已集中到 helper，proto 决策状态写回已收成统一入口
- 备注：
  - 这轮主要是“减少重复代码”，不是机制更新
  - 当前还没继续处理年龄/画像分桶逻辑在 `agent.py` 与 `llm_psychology.py` 之间的重复，这部分仍可放到下一轮

### Digital Friction 去冗余清理：共享年龄与 persona 分桶逻辑
- 时间：
  - 2026-04-06 23:57:12 CST
- 目的：
  - 清理 `agent.py` 与 `llm_psychology.py` 之间重复维护的画像分桶规则
  - 避免后续一边改了年龄/persona 归类规则，另一边忘了同步，导致 cache key、日志分析和事件记录口径漂移
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/profile_buckets.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/llm_psychology.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_profile_buckets.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 新增共享模块 `proto/profile_buckets.py`
    - 提供 `age_bucket(...)`
    - 提供 `persona_bucket(...)`
    - 把 support-seeking / cautious / proactive / neutral 这一套 persona 分类规则收成唯一实现
  - `agent.py`
    - 删除本地 `_profile_age_bucket(...)`
    - 删除本地 `_persona_tag(...)`
    - 改为直接调用共享的 `age_bucket(...)` 与 `persona_bucket(...)`
  - `llm_psychology.py`
    - 删除本地 `_age_bucket(...)`
    - 删除本地 `_persona_bucket(...)`
    - 改为直接复用共享分桶函数，用于 task appraisal cache key 的 profile 部分
  - 新增 `test_profile_buckets.py`
    - 覆盖年龄桶阈值
    - 覆盖 background summary 触发 `support_seeking`
    - 覆盖常见 persona 文本映射为 `cautious / proactive / neutral`
- 验证：
  - `rg -n "_profile_age_bucket|_persona_tag|_age_bucket|_persona_bucket|age_bucket\\(|persona_bucket\\(" examples/digital_friction_mvp/proto examples/digital_friction_mvp/tests`
    - 结果：旧本地 helper 已移除，调用点已切到共享实现
  - `python -m py_compile examples/digital_friction_mvp/proto/profile_buckets.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/proto/llm_psychology.py examples/digital_friction_mvp/tests/test_profile_buckets.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_profile_buckets.py examples/digital_friction_mvp/tests/test_llm_psychology.py examples/digital_friction_mvp/tests/test_interview_sync.py`
    - 结果：`18 passed`
- 备注：
  - 这轮仍然是“共享已有规则”，不是重新设计画像分类体系
  - 当前还没有继续整理 `background_summary` 压缩逻辑或更深层的 profile/memory 注入结构，这部分可作为后续候选项

### Digital Friction 去饱和 Phase 1：减轻前置压力层
- 时间：
  - 2026-04-07 14:31:39 CST
- 阶段标识：
  - Helplessness Update De-saturation / Phase 1
- 修改目标：
  - 按 `Helplessness Update 去饱和执行计划` 先只减轻前置压力层
  - 让 `effective_helplessness` 不再在正式 `state_update` 之前就过快顶满
  - 保留现有 schema 和日志字段，不改 world 设计、prompt 和 analysis pipeline
- 改了哪些机制：
  - 降低 `task_specific_pressure` 强度
  - 冻结 `help_confidence_buffer` 对 `effective_helplessness` 的直接作用
  - 降低 `recent_failure_pressure` 公式强度
  - 将 `task_appraisal_shift` 改为弱版，并移除 `risk/value` 直接推进 helplessness 的通道
  - 将 `emotion_pressure` 改为弱版
  - 保持 `help_confidence_bonus` 仅用于策略层，不接回 `effective_helplessness`
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - `recent_failure_pressure`
    - 从 `min(15, 10*neg + 4*avoid + 2*same_task_fail)` 改为 `min(8, 5*neg + 2*avoid + 1*same_task_fail)`
  - `task_specific_pressure`
    - 从 `max(0, 50-task_self_efficacy) * 0.25` 降到 `* 0.10`
  - `help_confidence_buffer`
    - 保留字段，但固定为 `0.0`
    - 从 `effective_helplessness` 公式中移除
  - `task_appraisal_shift`
    - `difficulty_shift` 降系数到 `0.03`
    - `control_shift` 降系数到 `0.04`
    - `help_shift` 降系数到 `0.02`
    - `risk_shift = 0.0`
    - `value_shift = 0.0`
    - clamp 区间收窄为 `[-3.0, 4.0]`
  - `emotion_pressure`
    - 从 `0.6*anxiety - 0.5*confidence` 改为 `0.25*anxiety - 0.20*confidence`
    - clamp 区间改为 `[-2.0, 3.0]`
  - 补充测试：
    - 新增测试锁定弱化版 `recent_failure_pressure`
    - 新增测试确认 `help_confidence_buffer` 不再改变 `effective_helplessness`
    - 新增测试确认 `risk/value` 不再直接推进 `task_appraisal_shift`
- 为什么这样改：
  - 之前 `task_specific_pressure / task_appraisal_shift / emotion_pressure / recent_failure_pressure` 会在正式 helplessness update 之前叠加出过高的 `effective_helplessness`
  - 这会让 baseline 和高摩擦 world 很快失去动态范围，后半段贴近上限，掩盖 `felt_control / support / success memory` 的真实分化
  - 这轮优先让 appraisal 和 memory 更像“策略层输入”，而不是“提前做半次 helplessness update”
- 对 smoke / 正式实验的预期影响：
  - baseline 的 `effective_helplessness` 上升速度应明显放缓
  - `low_friction_high_assist` 仍应保持最好，但不会完全依赖前置层被动压低
  - `high_friction_high_assist` 和 `high_friction_low_assist` 之间有更大机会在 helplessness 上拉开差异
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/tests/test_experience_memory.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_experience_memory.py`
    - 结果：`18 passed`
  - `python -m py_compile examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/attempt_strategy.py examples/digital_friction_mvp/proto/llm_psychology.py examples/digital_friction_mvp/tests/test_experience_memory.py examples/digital_friction_mvp/tests/test_attempt_strategy.py examples/digital_friction_mvp/tests/test_llm_psychology.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_experience_memory.py examples/digital_friction_mvp/tests/test_attempt_strategy.py examples/digital_friction_mvp/tests/test_llm_psychology.py`
    - 结果：`40 passed`
- 备注：
  - 这轮还没有进入 `state_update.py` 的 Phase 3 轻调
  - smoke 和正式实验尚未运行

## 2026-04-07

### 删除 help_confidence_buffer 并继续冻结 risk / task_value
- 目的：
  - 进一步收紧 helplessness 前置压力层，删去已经不再承担实际作用的 `help_confidence_buffer`
  - 明确保持 `risk` 与 `task_value` 只用于 appraisal / avoid 解释，不直接推进 helplessness
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/models.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_experience_memory.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 从 `MemoryFeatures` dataclass 中删除 `help_confidence_buffer`
  - 从 `extract_memory_features(...)` 的返回值和中间变量中删除 `help_confidence_buffer`
  - 从 `agent.py` 的 `support_effectiveness` 记录中删除 `help_confidence_buffer`
  - 保持 `risk_shift = 0.0`、`value_shift = 0.0`，继续冻结二者对 helplessness 的直接推进
  - 将对应测试改为确认“help 成功历史不会再直接改变 effective_helplessness”
- 为什么这样改：
  - `help_confidence_buffer` 已经固定为 `0.0` 且不再进入 `effective_helplessness`，继续保留字段只会增加代码和日志噪音
  - `risk` 和 `task_value` 更适合解释回避原因，不适合与无助感主链混在一起
- 对 smoke / 正式实验的预期影响：
  - 不会改变当前数值行为方向，只会让前置压力层更干净、更容易解释
  - 后续分析时，`support_effectiveness` 输出不再包含一个恒为 `0.0` 的无效字段
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/proto/models.py examples/digital_friction_mvp/proto/experience_memory.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/tests/test_experience_memory.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_experience_memory.py`
    - 结果：`18 passed`
- 备注：
  - 本轮没有修改 `strategy deliberation`、`event appraisal`、`state_update.py`

## 2026-04-07

### 加入固定 3 次/天的数字任务机会层原型
- 目的：
  - 只改数字任务“怎么出现”，不动后面的 `task appraisal -> strategy -> outcome -> uncontrollability -> helplessness update` 主链
  - 把高密度“每个 step 都可能派任务”的模式，收紧成“每天固定 3 个任务窗口”
  - 让四个 world 共享同一批任务机会，只在任务内摩擦强度和支持条件上拉开差异
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/task_assignment.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/runtime.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_task_assignment.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_runtime.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_outcome_model.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 在 `task_assignment.py` 中新增固定任务窗口：`09:00 / 14:00 / 19:00`
  - `select_task_for_agent(...)` 改成“命中窗口才返回任务，否则返回 `None`”
  - 每日任务机会表只由 `PARALLEL_PAIR_SEED`（无则回退 `EXP_SEED`）、`agent_id`、`day` 决定，不看 world
  - 保留四类任务：
    - `login_verification`
    - `appointment_registration`
    - `payment_checkout`
    - `health_info_lookup`
  - 每日任务安排改为四类任务的循环旋转表：当天取旋转后的前 3 个任务，第 4 个任务留到后续日期轮转
  - 在 `runtime.py` 中让 `assign_task_if_missing(...)` 兼容无任务窗口：非窗口不写新 surface，返回 `(None, {}, False)`
  - 保持“已有未完成任务时不补发、不排队”的原行为
  - 更新测试以覆盖：
    - 非窗口返回 `None`
    - 只有三个固定窗口派任务
    - 四个 world 共享同一批任务机会
    - 连续 4 天里四类任务总体等频
    - 已有未完成任务时，新窗口不会塞第二个任务
- 为什么这样改：
  - 之前任务分配更像“时钟驱动固定轮播”，会把任务机会和摩擦出现绑得过紧
  - 这会让 world 差异同时混进“任务数量不同”和“任务更难”两种来源，不利于 paired comparison
  - 这轮原型先只把任务机会层减重，让 world 更接近“同样任务在不同环境里更难或更容易”
- 对 smoke / 正式实验的预期影响：
  - 每个 world、每个 agent、每天最多只有 `3` 个数字任务机会
  - 四个 world 的任务机会表一致，差异主要留在 `difficulty / friction / support`
  - baseline 与高摩擦 world 的 helplessness 累积速度应下降，动态范围更容易保留下来
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/proto/task_assignment.py examples/digital_friction_mvp/proto/runtime.py examples/digital_friction_mvp/tests/test_task_assignment.py examples/digital_friction_mvp/tests/test_runtime.py examples/digital_friction_mvp/tests/test_outcome_model.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_task_assignment.py examples/digital_friction_mvp/tests/test_runtime.py examples/digital_friction_mvp/tests/test_outcome_model.py`
    - 结果：`17 passed`
  - `PYTHONPATH=examples/digital_friction_mvp python - <<'PY' ...`
    - 结果：脚本级验证通过，四个 world 都是 `30` 个任务机会，`shared_schedule_ok = True`
  - `world_runner.py` 的 `1 seed × 4 worlds × 1 day` smoke 已尝试两次
    - 结果：均被本机 Ray / psutil 的 `PermissionError: Operation not permitted (sysctl)` 阻断，未能完成完整运行链
- 备注：
  - 这轮没有修改 state schema、CSV schema、analysis pipeline、helplessness update 公式
  - 当前对“每天 3 次”和“固定三个窗口”的选择是原型化实现，后续若原型稳定，再升级为 `2-4` 次/天和画像驱动频率

## 2026-04-08

### 0408 单页汇报页整理
- 目的：
  - 按 `0325report.tex` 的 beamer 风格，整理一页可直接汇报的 helplessness 机制文献对应表
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/0408report.tex`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 新建 `0408report.tex`
  - 复用 `0325report.tex` 的 `beamer + Madrid + beaver + ctex` 格式
  - 将当前 `helplessness_mechanism_literature_mapping.md` 压缩为单页四列表格：
    - 机制
    - 代码干了什么
    - 理论依据
    - 文献层（来源文献 + 句子）
- 为什么这样改：
  - 便于导师汇报时在一页内同时展示代码实现、理论解释与文献依据
  - 保留 appendix 风格的结构化映射，而不展开成长篇文字
- 预期影响：
  - 仅影响汇报材料组织
  - 不改变任何实验逻辑或仿真结果
- 已运行验证命令：
  - 尚未运行

### Proto `status_summary()` 去 LLM 化
- 目的：
  - 去掉 `DigitalHelplessnessAgent` 在 friction proto 实验里每步一次的 `status_summary()` LLM 调用
  - 保留 `status_summary` 字段和状态表写入，但改为本地字符串摘要，减少空 step 的稳定 LLM 开销
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 在 `DigitalHelplessnessAgent` 内 override `status_summary()`，不再调用 `super().status_summary()`
  - 只使用现有状态字段生成紧凑的单行 `key=value` 摘要：
    - `day/time`
    - `stage`
    - `step`
    - `current_intention`
    - `step_outcome`
    - `helplessness/trust/avoidance`
    - `status_text`
  - 增加文本规整辅助函数，统一处理：
    - 空白折叠
    - `HH:MM` 时间格式
    - 缺省回退为 `unknown`/`none`
    - `note` 截断到 `160` 字符
  - 新增单元测试覆盖：
    - `idle` step 摘要
    - `digital_task` 摘要、空白折叠、截断
    - 关键字段缺失时的安全回退
    - 测试替身 LLM 不被访问
- 为什么这样改：
  - 当前 friction proto 主链并不依赖 LLM 版 `status_summary()` 的自然语言内容
  - 但框架会在每步末尾固定调用 `status_summary()`，导致非任务窗口也稳定消耗 LLM
  - 用本地摘要替代 LLM 文本可以保留状态字段，同时显著降低空 step 的固定开销
- 对 smoke / 正式实验的预期影响：
  - 非任务窗口不再因 `status_summary()` 产生“每个 agent 每步一次”的固定 LLM 请求
  - `status_summary` 仍可供状态表、导出和审计脚本读取
  - helplessness 主机制、schema 和分析脚本口径保持不变
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：`3 passed`
- 备注：
  - 这轮只处理 `status_summary()` 的 LLM 开销，不顺带清理 `EconomyBlock` 或其他框架钩子

## 2026-04-08

### proto 空窗口早返回与最小 housekeeping
- 目的：
  - 让 `none step` 不再先跑完整 proto 主链再发现 `task is None`
  - 在不动 helplessness 主机制的前提下，尽早跳过非任务窗口的重状态读取
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/task_assignment.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/state_schema.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_task_assignment.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_state_schema.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 在 `task_assignment.py` 新增 `is_task_window_tick(...)`，提供便宜的窗口判断
  - 在 `state_schema.py` 新增 `proto_last_housekeeping_day`
  - 在 `agent.py` 中把 `proto_assigned_task_json` 和窗口判断前移：
    - 非窗口且无遗留任务时，直接进入最小 housekeeping + idle 写回 + 返回
    - 只有任务窗口或有遗留任务时，才继续完整 proto 主链
  - 增加 `_run_minimal_daily_housekeeping(...)`，只保留：
    - `digital_emotion_state` 日切更新
    - 基础 stage 标记更新
    - `proto_last_housekeeping_day` 标记
  - full path 完成 housekeeping 后同步写入 `proto_last_housekeeping_day`
  - 补充测试覆盖：
    - 窗口判断
    - 新 schema 字段
    - 非窗口 idle step 早返回并写入 housekeeping marker
- 为什么这样改：
  - 当前空窗口的主要问题不是没有任务，而是“太晚才发现没任务”
  - 很多只应在有任务时才读取的状态，之前在每个 step 都提前读了
- 对 smoke / 正式实验的预期影响：
  - `06:00 / 06:30 / 07:00 / 07:30 / 08:00` 这类空窗口应明显变快
  - `09:00 / 14:00 / 19:00` 的任务窗口行为应保持不变
  - helplessness 主链公式与任务成功/失败逻辑不变
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/proto/task_assignment.py examples/digital_friction_mvp/proto/state_schema.py examples/digital_friction_mvp/tests/test_task_assignment.py examples/digital_friction_mvp/tests/test_state_schema.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_task_assignment.py examples/digital_friction_mvp/tests/test_state_schema.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：`15 passed`
- 备注：
  - 这轮还没有动 `before_forward()`、默认 blocks、economy agents 或 workflow function 瘦身

## 2026-04-08

### proto 轻量逻辑时钟原型
- 目的：
  - 让 `proto` friction 实验在保持 `30` 分钟 decision step 和任务窗口不变的前提下，不再为每步真实推进 `1800` 个 simulator tick
  - 只优化 friction proto 的时间推进成本，不改 helplessness 主链和 analysis schema
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/logical_clock.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/main.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/world_runner.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_logical_clock.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 新增 `enable_proto_logical_clock(...)` runtime patch：
    - 将 `environment.step(n)` 改为直接累加 `_tick`
    - 将 `environment.get_metrics()` 改为返回空列表
    - 在 environment 上写入逻辑时钟标记与原始方法引用
  - 在 `main.py` 中新增 `PROTO_LOGICAL_CLOCK_ENABLED` 开关，并在 `agentsociety.init()` 后安装逻辑时钟 patch
  - 在 `DigitalHelplessnessAgent` 中新增 `before_forward()` override：
    - 逻辑时钟模式下直接返回
    - 跳过 `update_motion()` 与 `SocietyAgent.before_forward()` 的位置/AOI/context 准备
  - 在 `log_step_status(...)` 中兼容逻辑时钟：
    - trip metrics 三项统一写为 `0.0`
    - 保留原有 metric key 和输出字段
  - 在 `world_runner.py` 中将 `PROTO_LOGICAL_CLOCK_ENABLED` 纳入 fingerprint
  - 新增/补充测试覆盖：
    - 逻辑时钟 patch 的 step 跳时、metrics 空返回、跨天推进、幂等安装
    - 逻辑时钟模式下 `before_forward()` 不触发 motion sync
- 为什么这样改：
  - 当前空 step 最大耗时来自 `environment.step(1800)` 的逐 tick 推进
  - friction proto 机制本身主要依赖 `day/t` 和 world 参数，不依赖真实城市模拟的逐秒前进
  - 通过 runtime patch 保留现有 workflow 和时间语义，可以最小范围验证轻量逻辑时钟原型
- 对 smoke / 正式实验的预期影响：
  - 非任务窗口的 step 间隔应明显下降
  - `09:00 / 14:00 / 19:00` 任务窗口仍保持一致
  - trip metrics 在该模式下失效并固定为 `0.0`
  - helplessness、trust、avoidance 及其 analysis 口径保持不变
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/main.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/proto/logical_clock.py examples/digital_friction_mvp/world_runner.py examples/digital_friction_mvp/tests/test_logical_clock.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_logical_clock.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：`9 passed`
- 备注：
  - 这轮不修改 `packages/agentsociety/...` 源码
  - 这轮不顺带清理 `_save`、DB 写入或 message/survey fetch 的框架耗时

## 2026-04-08

### proto 轻量逻辑时钟测试修正
- 目的：
  - 修复逻辑时钟测试桩与 runtime patch 接口不一致的问题
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 为测试内 `_FakeEnvironment` 补充最小 `step()` 与 `get_metrics()` 异步桩方法
  - 使 `enable_proto_logical_clock(...)` 能在测试中按真实接口安装 patch
- 为什么这样改：
  - 失败原因来自测试替身环境缺少 `step/get_metrics`
  - 不属于生产逻辑缺陷，而是测试桩未覆盖新接口要求
- 对 smoke / 正式实验的预期影响：
  - 仅影响单元测试稳定性
  - 不改变 runtime 行为
- 已运行验证命令：
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_logical_clock.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：`9 passed`

### proto 轻量逻辑时钟运行时修正
- 目的：
  - 修复逻辑时钟 smoke 中 `xy_position` 缺失导致的 step 保存失败
  - 修复 run 失败后 metadata 写入再次访问已关闭 environment 的问题
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/agent.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/main.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 在 `DigitalHelplessnessAgent.before_forward()` 中保留最小 `update_motion()`：
    - 逻辑时钟模式下不再完全空返回
    - 仍跳过 `SocietyAgent.before_forward()` 的重 context 准备
  - 在 `_write_run_metadata(...)` 中新增缓存参数 `proto_logical_clock_enabled`
  - 在 `main()` 中于 `init()` 后缓存逻辑时钟状态，并在 `close()` 后写 metadata 时直接使用缓存值
  - 更新测试预期：
    - 逻辑时钟模式下 `before_forward()` 应保留一次最小 motion sync
- 为什么这样改：
  - 框架 `_save()` 仍要求 citizen status 中存在 `position.xy_position`
  - 完全跳过 `before_forward()` 会把 `update_motion()` 一起跳掉，导致 step 保存阶段崩溃
  - run 失败后 environment 会在 `close()` 中被置空，metadata 再经 property 访问会触发二次异常
- 对 smoke / 正式实验的预期影响：
  - 逻辑时钟提速保留
  - 空 step 恢复最小位置同步后应不再因 `xy_position` 缺失而崩溃
  - metadata 在 run 失败路径下也能稳定落盘
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/main.py examples/digital_friction_mvp/proto/agent.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_logical_clock.py examples/digital_friction_mvp/tests/test_proto_agent_status_summary.py`
    - 结果：`9 passed`

### 任务窗口 2 分钟容差热修复
- 目的：
  - 修复逻辑时钟 smoke 中 step tick 与固定窗口秒数存在 1 秒错位，导致整轮实验 `task_count=0` 的问题
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/proto/task_assignment.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/examples/digital_friction_mvp/tests/test_task_assignment.py`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 在 `task_assignment.py` 中将固定窗口判断从“精确秒数相等”改为“距窗口不超过 `120s` 即命中”
  - 当多个窗口理论上都在容差内时，返回距离最近的窗口
  - 在测试中新增 runtime 偏移场景，覆盖 `32401` 这类真实 step tick 仍能正常派任务
- 为什么这样改：
  - 当前 proto run 的实际窗口 tick 为 `32401 / 50401 / 68401`
  - 原来的固定窗口秒数是 `32400 / 50400 / 68400`
  - 精确相等判断会把所有应派任务窗口误判为非窗口，导致行为指标全部归零
- 对 smoke / 正式实验的预期影响：
  - 任务窗口会重新开始派发任务
  - `30` 分钟步长下 `±120s` 不会误伤相邻窗口
  - 这是当前最小热修复，后续仍可升级成更干净的 slot/HH:MM 判断
- 已运行验证命令：
  - `python -m py_compile examples/digital_friction_mvp/proto/task_assignment.py examples/digital_friction_mvp/tests/test_task_assignment.py`
    - 结果：通过
  - `PYTHONPATH=examples/digital_friction_mvp pytest examples/digital_friction_mvp/tests/test_task_assignment.py examples/digital_friction_mvp/tests/test_runtime.py`
    - 结果：`14 passed`

### 2026-04-08 汇报文档整理
- 目的：
  - 按 `[0325report.tex](/Users/pifazuoren/Downloads/AgentSociety-main/0325report.tex)` 的 beamer 风格重做 `[0408report.tex](/Users/pifazuoren/Downloads/AgentSociety-main/0408report.tex)`
  - 将 helplessness mechanism mapping 从单页极小表整理成可汇报的多页 appendix 风格版本
- 涉及文件：
  - `/Users/pifazuoren/Downloads/AgentSociety-main/0408report.tex`
  - `/Users/pifazuoren/Downloads/AgentSociety-main/frictionchangeLog.md`
- 核心改动：
  - 为 `0408report` 补齐 title page、section、总结页与结束页
  - 将 10 条机制映射拆成 4 页表格，保留“代码干了什么 / 理论依据 / 文献层”三列结构
  - 明确标注阻尼、无自动回落、trust/avoidance 独立链属于建模选择，而非文献直推公式
- 为什么这样改：
  - 单页超密表虽然信息完整，但不适合导师汇报和论文 appendix 展示
  - 多页拆分后能在不损失内容的前提下提高可读性，并保持和 `0325report` 一致的汇报风格
- 预期影响：
  - `0408report.pdf` 可直接作为 2026-04-08 的汇报版本使用
  - 机制表更适合投屏、答辩和附录排版
  - 不改变任何 simulation / analysis runtime 行为
- 已运行验证命令：
  - `latexmk -xelatex -interaction=nonstopmode -halt-on-error /Users/pifazuoren/Downloads/AgentSociety-main/0408report.tex`
    - 结果：通过，已生成 `/Users/pifazuoren/Downloads/AgentSociety-main/0408report.pdf`
