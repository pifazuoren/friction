# Scope Gaussian 改造 TODO

## 1. 改造目标

当前 `scope` 机制还是三分类标签驱动：

- `task_specific`
- `mixed`
- `family_generalizing`

并且在代码里主要通过“固定邻居 + 固定 penalty”的方式做跨任务扩散。

这次改造的目标是：

1. 把三分类标签从主更新机制里拿掉。
2. 保留 `scope` 作为“是否会跨任务泛化、泛化多强”的心理变量。
3. 用 `Gaussian spillover` 替代当前的硬编码邻居传播。
4. 仍然保持 `scope` 不直接进入 helplessness 主更新，而是先影响其他 task family 的 `task_self_efficacy`，再间接影响后续行为与 helplessness。

一句话：

`LLM 判断这次失败会不会扩、多强、多宽；规则根据任务相似度，用 Gaussian 把影响分配到其他 task family。`

---

## 2. 为什么这样改

### 2.1 理论理由

- Abramson, Seligman, and Teasdale (1978) 里的 `global / specific` 本质上是一个“泛化程度”维度，不要求必须离散成三档。
- Tiggemann and Winefield (1978) 支持的是“helplessness 的泛化受 situation similarity 约束”，这更适合用 similarity-bounded spillover 来表达。
- Gaussian / RBF 写法适合表达“越相似影响越大，越不相似影响越小”的连续衰减。

### 2.2 工程理由

- 现在的三分类标签太粗，`mixed` 的含义也不够稳定。
- 当前 `neighbor + fixed penalty` 太硬，不够细。
- 如果后面要做更自然的 attribution 和更平滑的 world-level 分化，把 scope 写成 Gaussian spillover 的参数会更好用。

---

## 3. 新机制总览

建议把原来的：

- `event_attribution_scope = task_specific / mixed / family_generalizing`

改成 Gaussian spillover 的两个核心参数：

- `event_attribution_scope_amplitude: float`
- `event_attribution_scope_sigma_hint: narrow | medium | wide`
- `event_attribution_scope_explanation: str`

它们各自表示：

- `scope_amplitude`：这次失败跨任务扩散的基础强度，范围 `0.0 ~ 1.0`
- `scope_sigma_hint`：如果扩散，Gaussian 的宽度应该偏窄还是偏宽
- `scope_explanation`：一句简短解释，便于分析和汇报

备注：

- `scope_score` 只是对 `scope_amplitude` 的通俗叫法
- `scope_breadth` 只是对 `scope_sigma_hint` 的通俗叫法

---

## 4. 推荐的完整公式

### 4.1 先算 Gaussian spillover 的振幅

先算这次失败的有效振幅：

\[
A_t = \beta \cdot U_t \cdot a_t \cdot c_t
\]

其中：

- `U_t`：归一化后的 `event_level_uncontrollability`
- `a_t`：LLM 输出的 `scope_amplitude`
- `c_t`：`judge_confidence`
- `beta`：总强度系数

### 4.2 按相似度分配到其他 task family

\[
d(i,j)=1-S_{ij}
\]

\[
w_{ij}=\exp\left(-\frac{d(i,j)^2}{2\sigma_t^2}\right), \quad j \neq i
\]

\[
\hat w_{ij}=\frac{w_{ij}}{\sum_{k \neq i} w_{ik}}
\]

\[
\Delta SE^{spill}_{j,t} = -A_t \cdot \hat w_{ij}
\]

其中：

- `S_ij`：task family similarity
- `sigma_t`：由 `scope_sigma_hint` 决定
- `\hat w_{ij}`：这里使用的是归一化后的 Gaussian 权重，所有目标 family 分到的权重和为 1
- 这一步只更新其他 family 的 `task_self_efficacy`

一句话理解：

- `A_t` 决定这次 spillover 总体有多强
- `sigma_t` 决定影响铺得有多宽
- `Gaussian` 决定“优先扩给谁”

这里要特别注意：

- 归一化是要做的
- `sigma_t` 只负责改变“怎么分配”
- `A_t` 负责控制“总共扩散多少”

也就是说，`sigma_t` 变宽时，不应该顺便把总 spillover 量也放大；它只应该让影响分布得更开。

---

## 5. 推荐默认参数

### 5.1 `event_level_uncontrollability` 的归一化

- `0 -> 0.0`
- `1 -> 0.5`
- `2 -> 1.0`

### 5.2 Spillover 总强度

- `beta = 1.2`

理由：
先和当前旧逻辑里 `family_generalizing -> penalty = 1.2` 接近，方便前后对比。

### 5.3 最小触发阈值

- `scope_threshold = 0.15`

如果：

`scope_amplitude * confidence < 0.15`

则直接不做 spillover。

### 5.4 `scope_sigma_hint -> sigma`

- `narrow -> 0.25`
- `medium -> 0.45`
- `wide -> 0.75`

### 5.5 初始 similarity matrix

建议先用：

| source / target | L | A | P | H |
| --- | --- | --- | --- | --- |
| L | 1.0 | 0.3 | 0.8 | 0.2 |
| A | 0.3 | 1.0 | 0.2 | 0.7 |
| P | 0.8 | 0.2 | 1.0 | 0.2 |
| H | 0.2 | 0.7 | 0.2 | 1.0 |

其中：

- `L = login_verification`
- `A = appointment_registration`
- `P = payment_checkout`
- `H = health_info_lookup`

---

## 6. 新旧机制对照

### 旧机制

- LLM 输出三分类 `scope`
- `scope` 直接决定：
  - 不扩散
  - 弱扩散
  - 强扩散
- 扩散对象由固定邻居表决定

### 新机制

- LLM 输出连续 `scope_amplitude`
- LLM 输出 `scope_sigma_hint`
- 规则维护 similarity matrix
- 规则用 Gaussian 计算 spillover 分配
- spillover 只更新其他 family 的 `task_self_efficacy`

---

## 7. 代码层面的修改清单

## 7.1 `examples/digital_friction_mvp/proto/models.py`

### 要做的事

1. 在 `AttemptOutcome` 里弱化或弃用：
   - `event_attribution_scope`

2. 新增字段：
   - `event_attribution_scope_amplitude: float = 0.0`
   - `event_attribution_scope_sigma_hint: str = "not_applicable"`

3. 在 `TaskDomainState` 里，把：
   - `recent_generalizing_attribution_ratio`

   改成：
   - `recent_scope_amplitude_ema`

4. `dominant_attribution_scope` 可以考虑降级为 debug / report 用字段，而不是主机制字段。

### 备注

如果前后兼容压力比较大，可以先保留 `event_attribution_scope` 字段，但不再用于主更新。

---

## 7.2 `examples/digital_friction_mvp/proto/attribution_inference.py`

### 要做的事

1. 改 prompt，让 LLM 不再输出三分类 `event_attribution_scope`
2. 把输出 schema 改成：
   - `event_attribution_scope_amplitude`
   - `event_attribution_scope_sigma_hint`
   - `event_attribution_explanation`
   - `judge_confidence`
3. 修改：
   - `_EXPECTED_KEYS`
   - `_sanitize_payload`
   - fallback result
   - return object

### 推荐输出格式

```json
{
  "event_attribution_locus": "self",
  "event_attribution_stability": "stable",
  "event_attribution_scope_amplitude": 0.72,
  "event_attribution_scope_sigma_hint": "medium",
  "event_attribution_explanation": "The agent begins to expect similar digital tasks may also go wrong.",
  "judge_confidence": 0.81
}
```

### Prompt 里要定义清楚的内容

- `scope_amplitude = 0.0`
  表示这次失败只局限在当前任务
- `scope_amplitude = 0.5`
  表示有一定跨任务外溢苗头
- `scope_amplitude = 1.0`
  表示明显开始泛化到相似数字任务

- `narrow`
  表示 `sigma` 较小，只影响非常相似的任务
- `medium`
  表示 `sigma` 中等，影响一小圈相似任务
- `wide`
  表示 `sigma` 较大，影响更广的数字任务家族

### 注意

第一版不要让 LLM 直接输出 `sigma` 数值，先输出离散的 `sigma_hint` 会更稳。

---

## 7.3 `examples/digital_friction_mvp/proto/experience_memory.py`

这是本次改动最大的文件。

### 要做的事

1. 删除或停用：
   - `_TASK_FAMILY_NEIGHBORS`
   - 旧的 `_apply_task_family_generalization(...)`

2. 新增：
   - similarity matrix
   - `sigma_hint -> sigma` helper
   - `uncontrollability -> normalized U_t` helper
   - Gaussian 权重函数（返回归一化后的 `\hat w_{ij}`）
   - 新版 spillover 应用函数

3. 把 attribution EMA 从“离散 generalizing ratio”改成“连续 scope amplitude EMA”

### 推荐伪代码

```python
if outcome.outcome_type not in FAILURE_OUTCOMES:
    return

if outcome.event_attribution_status != "ok":
    return

effective_amplitude = (
    outcome.event_attribution_scope_amplitude
    * outcome.event_attribution_confidence
)

if effective_amplitude < scope_threshold:
    return

sigma = sigma_from_hint(outcome.event_attribution_scope_sigma_hint)
u = normalize_uncontrollability(outcome.event_level_uncontrollability)
A_t = beta * u * effective_amplitude

weights = gaussian_weights(source_task_family, sigma, similarity_matrix)
# 注意：这里的 weights 必须是归一化后的权重，总和应为 1

for target_family, weight in weights.items():
    if target_family == source_task_family:
        continue
    state[target_family].task_self_efficacy -= A_t * weight
    state[target_family].task_self_efficacy = clamp(...)
```

### 最关键的约束

`scope -> spillover -> other-family self-efficacy`

而不是：

`scope -> helplessness direct delta`

---

## 7.4 `examples/digital_friction_mvp/config_runtime.py`

### 建议新增配置项

- `PROTO_SCOPE_GENERALIZATION_MODE=gaussian`
- `PROTO_SCOPE_SPILLOVER_BETA=1.2`
- `PROTO_SCOPE_THRESHOLD=0.15`
- `PROTO_SCOPE_SIGMA_NARROW=0.25`
- `PROTO_SCOPE_SIGMA_MEDIUM=0.45`
- `PROTO_SCOPE_SIGMA_WIDE=0.75`

### 建议

把这些参数做成 runtime config，方便后面跑消融实验。

---

## 7.5 `examples/digital_friction_mvp/proto/metrics.py`

### 建议新增记录字段

- `event_attribution_scope_amplitude`
- `event_attribution_scope_sigma_hint`
- `scope_spillover_total`
- `scope_spillover_targets_json`

### 目的

后面分析时可以回答这些问题：

- 哪些 world 的 `scope_amplitude` 更高？
- spillover 更常波及哪些 task family？
- HF / LF world 的差异到底体现在“扩不扩”，还是“扩多宽”？

---

## 8. 对现有分析逻辑的兼容方案

虽然主机制里建议删掉三分类标签，但为了兼容旧图表和旧分析，建议暂时保留一个“派生标签”。

例如：

- `scope_amplitude < 0.20 -> task_specific`
- `0.20 <= scope_amplitude < 0.60 -> mixed`
- `scope_amplitude >= 0.60 -> family_generalizing`

注意：

这个标签只用于：

- debug
- logging
- plotting
- 和旧实验对比

不再参与主更新。

---

## 9. 实施顺序

建议按下面顺序改，不要一步全改完。

### 第 1 步

先在机制设计上确定：

- 三分类从主更新里退出
- 主更新改用 `A_t + sigma_t + Gaussian`

### 第 2 步

修改 `attribution_inference.py`

- 让 LLM 输出连续 `scope_amplitude`
- 输出 `scope_sigma_hint`
- 旧的离散标签只做兼容或事后映射

### 第 3 步

修改 `models.py`

- 补新字段
- 调整 `TaskDomainState`

### 第 4 步

修改 `experience_memory.py`

- 上线 similarity matrix
- 上线 Gaussian spillover
- 删除旧邻居传播逻辑

### 第 5 步

修改 `metrics.py` 和分析脚本

- 记录新字段
- 检查分析表和图还能不能跑

### 第 6 步

做 smoke test 和小规模实验

- 先 1 seed
- 再 3 paired seeds

---

## 10. 验证重点

改完后，优先检查这几件事：

1. `scope_amplitude` 在坏环境 world 中是否整体更高。
2. 相似 task family 之间是否出现更自然的联动下滑。
3. 不相似 family 是否不再被“硬传播”误伤。
4. helplessness 是否仍然主要受 uncontrollability 驱动，而不是被 scope 直接拉高。
5. attribution 输出是否比旧三分类更平滑、更有信息量。

---

## 11. 风险与注意事项

### 风险 1：LLM 连续输出不稳定

解决办法：

- 保持低 temperature
- 给明确刻度定义
- 保留 `judge_confidence`
- 必要时加 conservative fallback

### 风险 2：Gaussian 太平滑，导致所有 family 都被轻微波及

解决办法：

- 设定最小阈值
- 让较远 family 的 similarity 足够低
- 只对 `j != i` 计算 spillover

### 风险 3：scope 和 stability 混在一起

解决办法：

- 明确：
  - `stability` 负责“会不会持续”
  - `scope` 负责“会不会扩到相似任务”

### 风险 4：scope 误入 helplessness 主公式

解决办法：

- 明确边界：
  `scope` 只通过 spillover 改 self-efficacy

---

## 12. 最终推荐版本

如果只保留一句最核心的设计建议，就是：

### 推荐主机制

- LLM 输出：
  - `scope_amplitude`
  - `scope_sigma_hint`
  - `judge_confidence`
- 规则维护：
  - similarity matrix
  - Gaussian kernel
  - spillover 更新
- spillover 只更新其他 family 的 `task_self_efficacy`
- helplessness 主更新保持独立，不直接吃 scope

### 推荐实现策略

- 三分类标签退出主更新
- 保留派生标签用于分析和汇报
- 先做最小可运行版，再做参数调优和消融实验

---

## 13. 下一步可直接开工的任务

- [ ] 改 `attribution_inference.py` 的 prompt 和 schema
- [ ] 改 `models.py` 的 outcome/state 字段
- [ ] 在 `experience_memory.py` 中加入 similarity matrix
- [ ] 在 `experience_memory.py` 中实现 Gaussian spillover
- [ ] 在 `config_runtime.py` 中加入 scope 参数
- [ ] 在 `metrics.py` 中记录新字段
- [ ] 跑 1 seed smoke test
- [ ] 跑 3 paired seeds 小实验
- [ ] 检查 attribution / behavior / helplessness 三层分化
