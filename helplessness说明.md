# Helplessness Update 机制说明

以下完全基于当前代码，按一次事件的实际执行顺序来写。

---

## 一、事件触发前：状态准备

每轮 `forward()` 开始时，agent 持有以下长期状态：

- `helplessness_score`（0-100）
- `consecutive_failures`（全局连败计数）
- `task_domain_memory`（按 task_family 分桶，每桶含 `task_self_efficacy`、`controllable_success_memory` 等）
- `help_effect_memory`（求助成功率的滑动统计）
- `recent_episode_buffer`（最近 8 条事件摘要）
- `digital_emotion_state`（anxiety / frustration / relief / confidence）

---

## 二、事件流水线

### 2.1 任务分配 → 特征提取

`extract_memory_features()` 从当前任务和记忆中抽出决策用特征：

- `task_self_efficacy`：当前任务族的效能感
- `controllable_success_memory`：当前任务族的长期可控成功记忆
- `effective_helplessness`：先计算 `helplessness + 任务特定压力 + 近期失败压力 - 求助信心缓冲`，再叠加 `task appraisal shift`，最后再叠加 `emotion pressure`；每一步都会单独 clamp 到 0-100

### 2.2 Task Appraisal（LLM hybrid）

LLM 或规则生成 5 个主观评估值：

| 变量 | 含义 | 范围 |
|---|---|---|
| `perceived_task_difficulty` | 我觉得这个任务有多难 | 0-100 |
| `perceived_task_risk` | 我觉得做错了代价有多大 | 0-100 |
| `felt_control` | 我觉得自己能控制局面吗 | 0-100 |
| `expected_help_effectiveness` | 如果求助，帮助会多有用 | 0-100 |
| `task_value` | 这件事对我有多值得做 | 0-100 |

### 2.3 策略选择 → 行为执行 → 结果生成

agent 选择 `attempt_self` / `seek_help_then_attempt` / `avoid`，概率模型产出 6 种结果之一：

`success_self` · `success_with_help` · `failure_after_attempt` · `failure_even_with_help` · `abandon_midway` · `avoid_without_attempt`

### 2.4 两个后置分类器

**Avoid 分类**（仅当 `avoid_without_attempt` 时触发）——纯规则评分，三选一：

```
helpless_score = f(helplessness, low_SE, low_control, repeat_failures, friction_type)
risk_score     = f(perceived_risk, env_risk, payment_type, moderate_control)
value_score    = f(low_task_value, low_risk, no_recent_failures)

→ 得分最高者胜出 → helpless_avoid / risk_avoid / low_value_avoid
```

**Support Mode 分类**（仅当 `help_used=True` 时触发）——纯规则评分，二选一：

```
support_signal = quality_bonus + f(felt_control - 52) + f(help_effectiveness - 58)

signal ≥ 1.05 → enabling_support（帮助理解，保留主体性）
signal < 1.05 → substituting_support（代做，agency 修复弱）
```

### 2.5 Uncontrollability 校准（LLM hybrid）

`uncontrollability_calibrator` 先给规则值 {0, 1, 2}，然后在 hybrid 模式下 LLM 可以在 ±1 范围内校正。

---

## 三、核心公式：`apply_helplessness_update()`

### 3.1 成功路径（success_self / success_with_help）

```
连败归零

recovery = mastery_recovery_term(...)
raw_delta = BASE_DELTA - recovery

H_{t+1} = clamp(H_t + raw_delta, 0, 100)
```

**BASE_DELTA**：

| outcome | base |
|---|---|
| success_self | -2.0 |
| success_with_help | -1.0 |

**mastery_recovery_term** 的组成：

| 条件 | bonus |
|---|---|
| success_self | +1.0 |
| success_with_help + enabling_support + help_effectiveness≥60 + felt_control≥55 | +0.25 |
| success_with_help + support_quality=2（但不满足 enabling 条件） | +0.10 |
| 结束了连败（之前 consecutive_failures > 0） | +0.5 |
| success_self + felt_control ≥ 60 | +0.5（额外） |

所以 `success_self` 在高控制感下的最大恢复 = -2.0 - (1.0 + 0.5 + 0.5) = **-4.0**，而 `success_with_help` + substituting_support 的恢复 ≈ **-1.0 到 -1.6**。

### 3.2 失败路径（failure / abandon / avoid）

```
positive_pressure =
    BASE_DELTA
  + repetition_delta(next_failure_count)
  + UNCONTROLLABILITY_DELTA
  + efficacy_loss_term(task_self_efficacy)
  + control_loss_term(felt_control)
  - SUPPORT_BUFFER

若 avoid_without_attempt:
    pressure *= avoid_reason_multiplier

pressure = max(0, pressure * (1 - controllable_success_protection))

damping = 1.0 - 0.3 * H_t / 100,   clamp [0.70, 1.0]

H_{t+1} = clamp(H_t + pressure * damping, 0, 100)
```

各项详细拆解：

**BASE_DELTA**：

| outcome | base |
|---|---|
| failure_after_attempt | +1.5 |
| failure_even_with_help | +2.0 |
| abandon_midway | +1.0 |
| avoid_without_attempt | +0.5 |

其中：

- 普通失败 / 中途放弃：先把 `consecutive_failures + 1`，再查 `repetition_delta`
- `avoid_without_attempt`：不增加连败数，直接用当前 `consecutive_failures`

**repetition_delta**（事件后的连败计数）：

| 连败次数 | delta |
|---|---|
| ≤1 | 0.0 |
| 2 | +1.0 |
| 3 | +2.0 |
| ≥4 | +3.0 |

**UNCONTROLLABILITY_DELTA**（0/1/2 三级不可控感）：

| level | delta |
|---|---|
| 0 | 0.0 |
| 1 | +1.8 |
| 2 | **+3.6** |

这是当前机制中最重的单项。一次 level-2 不可控失败 = 1.5 (base) + 3.6 (uncontroll) = **5.1**，远大于 base 本身。

**efficacy_loss_term**（效能感越低越痛）：

```
(55 - task_self_efficacy) / 15,   clamp [0, 2.5]
```

SE=55 时为 0；SE=25 时为 2.0；SE=10 时为 2.5（上限）。

**control_loss_term**（当事控制感越低越痛）：

```
(50 - felt_control) / 20,   clamp [0, 1.5]
```

FC=50 时为 0；FC=20 时为 1.5（上限）。

**SUPPORT_BUFFER**（直接缓冲，已极小化）：

| quality | buffer |
|---|---|
| 0 | 0.0 |
| 1 | 0.15 |
| 2 | 0.35 |

**avoid_reason_multiplier**（只有 helpless_avoid 给全额）：

| reason | multiplier |
|---|---|
| helpless_avoid | 1.0 |
| risk_avoid | 0.35 |
| low_value_avoid | 0.15 |

**controllable_success_protection**（长期可控成功记忆的乘性保护）：

```
protection = CSM * 0.35,   clamp [0, 0.35]
effective_pressure = raw * (1 - protection)
```

CSM=1.0 时最多降低 35% 负向压力；CSM=0.0 时无保护。

**damping**（高 helplessness 时边际递减）：

```
damping = 1.0 - 0.3 * H_t / 100,   clamp [0.70, 1.0]
```

H=0 时 damping=1.0（全冲击）；H=100 时 damping=0.70（冲击打七折）。

---

## 四、事后更新：经验记忆

helplessness 更新完成后，`update_experience_memory()` 同步更新：

### 4.1 task_self_efficacy 更新

基础增量按 outcome 和 support_mode 差异化：

| outcome | enabling_support | substituting_support / 不涉及 |
|---|---|---|
| success_self | +6.0 | +6.0 |
| success_with_help | **+4.5** | +1.5 |
| failure_after_attempt | -5.0 | -5.0 |
| failure_even_with_help | **-4.5** | -6.0 |
| abandon_midway | -4.0 | -4.0 |
| avoid (helpless) | -2.0 | — |
| avoid (risk) | -0.5 | — |
| avoid (low_value) | 0.0 | — |

同一任务族连续失败 2 次额外 -1.0，3 次以上额外 -2.0。

### 4.2 controllable_success_memory 更新

**衰减**：每过一天乘 0.985（半衰期 ≈ 46 天）。

**积累**（`_controllable_success_gain()`）：

| 条件 | gain |
|---|---|
| success_self + felt_control≥60 + uncontrollability=0 | 0.12 |
| ↑ 且之前该任务连败≥2 | 0.12 + 0.03 = 0.15 |
| success_with_help + enabling_support + quality≥1 + felt_control≥65 + uncontrollability≤1 | 0.05 |
| 其他所有情况 | 0 |

所有 gain 乘以 `difficulty_weight`（难度 0.5 时 ×0.85，难度 1.0 时 ×1.15）。

**不积累的情况**：substituting_support 成功、运气成功（低 felt_control 或高 uncontrollability）、失败、回避——全部 gain=0。

---

## 五、数值直觉：几种典型场景

**最轻**：low_value_avoid，低 friction

```
base=0.5, uncontroll=0, efficacy_loss≈0, control_loss≈0
→ raw ≈ 0.5 * 0.15 (low_value multiplier) ≈ 0.075
→ 几乎不涨
```

**中等**：普通失败，中等不可控，SE 适中

```
base=1.5, uncontroll=1.8, efficacy_loss≈0.5, control_loss≈0.3
→ raw ≈ 4.1 - 0.15 (buffer) ≈ 3.95
→ * damping(0.85 @H=50) ≈ 3.36
```

**最重**：failure_even_with_help + 3 连败 + 高不可控 + 低 SE + 低 control + 无保护

```
base=2.0, rep=2.0, uncontroll=3.6, efficacy=2.5, control=1.5
→ raw ≈ 11.6 - 0.35 ≈ 11.25
→ * (1-0) * damping(0.7 @H=100) ≈ 7.9
→ 但如果 CSM=0.8, protection=0.28
→ * (1-0.28) ≈ 8.1 * 0.72 ≈ 5.8 * 0.7 ≈ 4.1
```

**最强恢复**：success_self + 结束连败 + 高 control

```
base=-2.0, recovery=1.0+0.5+0.5=2.0
→ delta = -2.0 - 2.0 = -4.0
```

---

## 六、机制总结图

```
               ┌─────────────────────────────────────┐
               │         task appraisal (LLM)        │
               │  felt_control · risk · value · help  │
               └──────┬──────────────┬────────────────┘
                      │              │
              ┌───────▼───────┐ ┌────▼─────────────┐
              │ avoid_reason  │ │  support_mode     │
              │ 3-class rule  │ │  2-class rule     │
              └───────┬───────┘ └────┬─────────────┘
                      │              │
    ┌─────────────────▼──────────────▼──────────────────────┐
    │            apply_helplessness_update()                 │
    │                                                       │
    │  SUCCESS路径:                                         │
    │    delta = base - mastery_recovery(...)               │
    │    H += delta                                         │
    │                                                       │
    │  FAILURE路径:                                         │
    │    pressure = base + rep + uncontroll                 │
    │             + efficacy_loss(SE) + control_loss(FC)    │
    │             - tiny_buffer                              │
    │    if avoid: pressure *= avoid_multiplier             │
    │    pressure *= (1 - CSM_protection)    ← 乘性调节     │
    │    pressure *= damping(H_t)            ← 边际递减     │
    │    H += pressure                                      │
    └───────────────────────┬───────────────────────────────┘
                            │
    ┌───────────────────────▼───────────────────────────────┐
    │          update_experience_memory()                    │
    │                                                       │
    │  task_self_efficacy ±Δ  (support_mode 差异化)         │
    │  controllable_success_memory += gain (严格准入)       │
    │  controllable_success_memory *= 0.985^days (慢衰减)   │
    │  recent_episode_buffer.append(...)                    │
    │  rationale_memory.append(...)                         │
    └───────────────────────────────────────────────────────┘
```

核心设计思想：**outcome 本身只给小底分，真正推动 helplessness 上升的是"不可控感 + 低效能 + 低控制"三重叠加；保护来自长期可控成功记忆的乘性缓冲；support 的主效果通过 SE 差异化更新和 CSM 选择性积累间接传导，直接 buffer 已极小化。**

---

## 七、代码位置索引

| 模块 | 文件 | 主要职责 |
|---|---|---|
| 核心公式 | `proto/state_update.py` | `apply_helplessness_update()` 及所有子项函数 |
| 数据结构 | `proto/models.py` | `HelplessnessUpdateInput`、`HelplessnessUpdateResult`、`TaskDomainState` 等 |
| 经验记忆 | `proto/experience_memory.py` | SE 更新、CSM 积累/衰减、episode buffer |
| 结果与分类 | `proto/outcome_model.py` | 成功概率、avoid 分类、support mode 分类 |
| LLM 心理 | `proto/llm_psychology.py` | task appraisal、event appraisal、strategy deliberation |
| 不可控校准 | `proto/uncontrollability_calibrator.py` | rule + LLM hybrid 校准 uncontrollability |
| 主流程 | `proto/agent.py` | `forward()` 中组装所有模块 |
