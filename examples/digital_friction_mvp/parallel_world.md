# 平行世界对照设计（Digital Friction MVP）

## 1. 目标与原则

- 目标：评估不同数字环境（摩擦/辅助）对老年人数字摩擦累积与无助演化的影响。
- 核心原则：**只控制输入，不强控输出**。  
  不要求每一步 action 完全一致；要求世界间外生条件一致、仅世界参数不同。

---

## 2. 世界定义（唯一主变量）

三组世界（A/B/C）：

- A：`baseline_low_friction`
- B：`high_friction_low_assist`
- C：`low_friction_high_assist`

除 `WORLD_NAME` 外，其余参数固定（见第 4 节）。

---

## 3. 实验设计类型

采用**配对重复设计（paired repeated design）**：

- 每个 seed 构成一组：同一 seed 下分别运行 A/B/C 三世界。
- 运行多组 seed（建议至少 10 组，优选 20 组）。
- 统计时以 seed 为配对单位，比较组内差值（B-A、C-A）。

---

## 4. 运行配置规范

### 4.1 固定项（必须一致）

- `AGENT_COUNT`
- `STAGE_DAYS`
- `EVENT_DECISION_INTERVAL_MINUTES`
- 触发与判定相关参数（hazard / unified / gate / emit policy）
- prompt 配置（如 `AGENT_PLAN_PROMPT_PROFILE`）
- 是否启用 economy（`ECONOMY_BLOCK_ENABLED`）
- digital supply 参数

### 4.2 推荐项（平行世界主实验）

- `STAGE_MODE=single`  
  避免“世界差异”和“三阶段时间干预”同时叠加，导致效应混杂。

### 4.3 seed 要求（关键）

- 同一组内 A/B/C 必须使用**同一个 seed**。
- 不同组使用不同 seed。
  
> 现已支持在 `world_runner.py` 中按配对 seed 运行（同组 A/B/C 同 seed），并支持多 seed 批量。

---

## 5. 指标框架

## 5.1 主指标（建议预注册）

1. `AttemptRate = attempts / opportunities`
2. `NegShare = negative_events / emitted_events`
3. `HelplessDelta = helplessness_end - helplessness_start`

## 5.2 次指标

- `EmitGivenAttempt = emitted / attempts`
- `SkipRate = scenario_skip / opportunities`
- `NonDigitalSkipShare = non_digital_skip / scenario_skip`
- `TrustDelta = trust_end - trust_start`
- `AvoidDelta = avoidance_end - avoidance_start`
- `HintAdoptRate = hint_adopted / hint_surface`

## 5.3 分母统一

- `opportunities = AGENT_COUNT * (1440 / EVENT_DECISION_INTERVAL_MINUTES) * days`
- 禁止跨实验混用不同分母直接比较绝对计数。

---

## 6. 对比方法（统计）

对每个 seed、每个指标 `M` 计算：

- `d_BA(seed) = M(seed, B) - M(seed, A)`
- `d_CA(seed) = M(seed, C) - M(seed, A)`

对 `{d_BA}`、`{d_CA}` 汇总：

- 均值、中位数
- 95% CI（建议 bootstrap）
- 显著性（建议配对 Wilcoxon；样本足够可加 paired t-test）

报告方向一致性：

- 有多少 seed 满足 `d_BA` 与预期方向一致
- 有多少 seed 满足 `d_CA` 与预期方向一致

---

## 7. 预期方向（理论检验）

相对 A（baseline）：

- B（高摩擦低辅助）预期：
  - `AttemptRate` ↓
  - `NegShare` ↑
  - `HelplessDelta` ↑
  - `TrustDelta` ↓
- C（低摩擦高辅助）预期：
  - `AttemptRate` ↑
  - `NegShare` ↓
  - `HelplessDelta` ↓
  - `TrustDelta` ↑

---

## 8. 质量控制与排错

- 只纳入完整跑完（status=ok）的 run。
- 审核每组参数一致性（除 `WORLD_NAME` 外）。
- 记录并检查异常 run（如 LLM 错误激增、机会位点异常）。
- 对异常 run 做敏感性分析（含/不含异常 run 各报告一次）。

---

## 9. 结果呈现模板

- 表 1：A/B/C 各指标均值 ± CI
- 表 2：`B-A`、`C-A` 配对差值、CI、p 值
- 图 1：按 seed 的配对连线图（A→B、A→C）
- 图 2：主指标差值森林图

---

## 10. 当前代码适配建议（最小改动）

1. 平行世界主实验改用 `STAGE_MODE=single`。
2. 使用 `world_runner.py --n-seeds` 或 `--seed-list` 做配对多组实验。
3. 可以直接用 `world_runner.py --summarize-paired` 一次产出 manifest、world summary、stage summary 和 paired comparison csv。
4. 若需手动分析，先跑 `analysis_parallel_worlds.py`，再跑 `analysis_parallel_paired.py`。新版 `analysis_parallel_paired.py` 支持 `baseline` 对多个 comparison world 的配对统计，不再局限于旧的 `B-A/C-A` 三世界口径。
