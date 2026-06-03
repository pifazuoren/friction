# TalkingData 可验证性与四世界实验定位 0527

## 1. 核心问题

当前实验里有两个不同层次：

```text
TalkingData 真实手机使用轨迹
```

和：

```text
四个 digital friction / assistance counterfactual worlds
```

这两者不能混为一谈。TalkingData 是正常现实世界中的手机使用记录，不包含我们实验中显式操纵的 high friction / low friction / high assist / low assist 条件，也不包含 helplessness、controllability、help-seeking success、FamilyHelperAgent response 等心理和交互标签。

因此，TalkingData 不能直接验证四个世界本身是否真实，也不能直接验证 learned helplessness 机制是否正确。

它更适合作为：

```text
empirical mobile-use anchor
behavioral grounding
held-out exposure validation
```

也就是用真实数据约束和检验：

```text
手机行为什么时候出现
大概出现哪些类别
哪些类别在后续时间窗口中保持或下降
仿真任务暴露是否过度任务化
```

## 2. 用户提出的关键想法

一个重要判断是：

```text
TalkingData 是正常世界数据。
我们的四个 world 是摩擦世界特化的 counterfactual 实验。
所以 TalkingData 不应该被解释成验证所有四个 world。
```

更合理的说法是：

```text
TalkingData 可以帮助我们识别或校准一个最接近真实正常手机使用轨迹的 empirical-anchor world。
```

然后其他 world 作为在这个真实行为底座上的反事实操纵：

```text
如果数字环境更高摩擦，会怎样？
如果家庭支持更强，会怎样？
如果低摩擦且高支持，会怎样？
```

这使得实验叙事变成：

```text
先用真实数据约束正常手机使用底座，
再在 agent-based simulation 中做 friction / assistance counterfactuals。
```

而不是：

```text
用 TalkingData 证明四个摩擦世界都真实。
```

## 3. TalkingData 能验证什么

TalkingData 可以支持以下验证。

### 3.1 Task Entry / Mobile Exposure 是否合理

TalkingData 有真实：

```text
timestamp
category
is_active
device/user id
age
gender
device brand/model
```

因此可以验证：

```text
daily active volume
hourly activity profile
mobile intention distribution
category distribution
task-family opportunity distribution
finance/payment exposure rate
service/application exposure rate
navigation/service-location exposure rate
unknown_or_unmapped mass
```

这对应我们仿真中的：

```text
mobile_entry_eval_count
selected_mobile_intention
mapped_task_family
task_generated
entry_status
task_family
```

### 3.2 是否过度任务化

当前一次轻量验证暴露出一个重要问题：

```text
TalkingData validation 中 unknown_or_unmapped mass 很高，约 0.756。
当前 LLM rerank 仿真中 unknown_or_unmapped mass 约 0.31-0.33。
```

这说明当前 LLM rerank 可能把太多普通或未知手机行为解释成了明确数字任务，例如：

```text
payment
service application
help seeking
navigation
```

因此，TalkingData 对我们最直接的帮助之一是约束 entry layer：

```text
不要把真实世界中大量模糊手机使用都转成 digital friction task。
```

这可以支持后续修改：

```text
conservative rerank prompt
unknown-preserving gate
event-level mobile entry export
```

### 3.3 Reference -> Validation 的外推能力

数据可以切成：

```text
May 1-3: reference
May 4-7: validation
```

合理的验证方式是：

```text
用 May 1-3 构建 profile / hourly prior / category-intention prior。
用 simulation 生成后续行为。
用 May 4-7 真实数据做 held-out 对比。
```

这验证的是：

```text
May 1-3 学到的正常手机使用规律，能否外推到 May 4-7 的真实手机使用轨迹。
```

但这仍然主要是行为底座验证，不是心理机制验证。

### 3.4 Retention / Drop-off Proxy

TalkingData 没有 avoid 标签，但可以构造 proxy。

真实数据中可以计算：

```text
某用户 May 1-3 是否使用过某 category / task family
该用户 May 4-7 是否继续使用同类 category / task family
后四天同类活跃量是否下降
```

例如：

```text
payment_retention =
May 1-3 有 payment/finance activity 的用户中，
May 4-7 仍有 payment/finance activity 的比例。
```

仿真中可以对应计算：

```text
task_family opportunity count
attempt count
seek_help count
avoid_without_attempt count
abandon_midway count
success/failure count
```

并比较：

```text
day 1-3 vs day 4-7 的 engagement retention / dropoff proxy。
```

注意：这只能叫 behavioral proxy，不能叫 helplessness label。

## 4. TalkingData 不能验证什么

TalkingData 不能直接验证：

```text
helplessness_score
helplessness_delta
learned helplessness formation
Bayesian controllability posterior
Huys-Dayan C_family
FamilyHelperAgent support quality
help-seeking success
task success/failure
agent 是否真的主观回避
```

原因是数据集中没有这些标签。

因此论文中不能写：

```text
TalkingData validates digital helplessness.
TalkingData directly validates controllability belief.
TalkingData records task success and help-seeking.
```

更安全的写法是：

```text
TalkingData is used to ground and validate mobile-use exposure patterns,
not to directly supervise psychological states or action-outcome beliefs.
```

## 5. 四个 World 应该如何定位

四个 world 不应该都被解释为真实世界样本。

更合理的定位是：

```text
baseline_low_friction:
  empirical-anchor / observed-anchor candidate

high_friction_low_assist:
  adverse digital environment counterfactual

high_friction_high_assist:
  high-friction but socially supported counterfactual

low_friction_high_assist:
  protective / supportive counterfactual
```

其中，TalkingData 最适合用来评估：

```text
哪个 world 在 mobile exposure / category distribution / retention proxy 上最接近真实正常世界。
```

这个 world 可以被称为：

```text
empirical-anchor condition
observed-anchor condition
closest behavioral-fit condition
```

但不宜称为：

```text
the real world
the ground-truth world
```

因为 TalkingData 只是一个正常手机使用数据集，不包含我们实验里的摩擦与支持操纵标签。

## 6. 推荐实验叙事

推荐采用两层实验叙事。

### 6.1 第一层：Empirical Anchoring

目标：

```text
证明任务入口不是任意编造的，而是由真实手机使用轨迹约束。
```

方法：

```text
May 1-3 reference data
→ build mobile-use priors and profile buckets
→ simulate mobile task exposure
→ compare with May 4-7 held-out data
```

指标：

```text
mobile_intention_tvd
task_family_opportunity_tvd
hourly_activity_tvd
unknown_or_unmapped mass gap
task_generated/evaluated rate
category retention proxy
```

结论口径：

```text
The entry layer is empirically grounded in observed mobile-use traces.
```

### 6.2 第二层：Counterfactual Mechanism Experiment

目标：

```text
在真实行为底座上操纵 digital friction 与 assistance，
观察 helplessness / strategy / support / controllability dynamics。
```

方法：

```text
baseline_low_friction
high_friction_low_assist
high_friction_high_assist
low_friction_high_assist
```

指标：

```text
success_rate
negative_feedback_rate
avoid_without_attempt
abandon_midway
help_seek_rate
support_response status
helplessness_delta
Bayesian posterior trajectory
Huys policy modulation audit
```

结论口径：

```text
The four worlds are counterfactual stress tests built on top of an empirically grounded mobile-use entry process.
```

## 7. 为什么不能让 May 4-7 进入 Prompt

May 4-7 是 validation 数据。

如果把 May 4-7 的真实分布直接写进 LLM prompt，就会造成 validation leakage。

不应该做：

```text
prompt 中告诉 LLM：
真实 May 4-7 unknown_or_unmapped 是 0.756，
所以请保持这个比例。
```

可以做：

```text
prompt 中告诉 LLM：
candidate_intentions 来自 empirical reference prior；
unknown_or_unmapped 是合法且常见的手机使用状态；
不要在缺乏强证据时把 unknown 改成具体任务。
```

这里使用的是 May 1-3 reference 的含义，而不是 May 4-7 答案。

## 8. 当前应优先修改什么

### 8.1 修 entry layer 的过度任务化

当前 LLM rerank 有时把：

```text
unknown_or_unmapped
```

改成：

```text
communicate_or_seek_help
use_payment_or_finance
submit_service_application
```

导致仿真比真实数据更任务化。

建议：

```text
修改 rerank prompt，使 unknown_or_unmapped 被明确视为合法、高频、保守选择。
增加 unknown-preserving deterministic gate。
记录 rule_selected / rerank_selected / final_selected。
```

### 8.2 补 event-level mobile entry export

当前 `mvp_status` 是每日/阶段状态汇总，不适合验证 hourly activity。

需要导出每次 mobile entry evaluation：

```text
agent_id
day
t
hour
profile_bucket
candidate_intentions
rule_selected_mobile_intention
rerank_selected_mobile_intention
final_selected_mobile_intention
entry_status
task_generated
mapped_task_family
mapping_confidence
rerank_confidence
uses_validation_data
```

这样才能正式比较：

```text
hourly activity profile
mobile intention distribution
task-family exposure
task generation rate
```

### 8.3 增加 retention/dropoff analysis，不改 entry prior

不要让 agent 内部记忆反过来改 TalkingData prior。

更干净的做法是：

```text
TalkingData prior 负责 opportunity exposure。
agent mechanism 负责 strategy / avoid / abandon / help-seeking。
analysis 层统计 day 1-3 vs day 4-7 的 engagement retention。
```

需要导出：

```text
agent_id
day
task_family
opportunity_count
attempt_count
seek_help_count
avoid_without_attempt_count
abandon_midway_count
success_count
failure_count
```

再和 TalkingData 的 category retention proxy 对比。

## 9. 审稿口径

一个稳妥说法是：

```text
We do not treat TalkingData as a ground truth for digital helplessness.
Instead, we use it to anchor the mobile-use exposure process and to identify
which simulated condition best matches held-out normal-world usage traces.
The remaining simulated worlds are counterfactual manipulations of digital
friction and assistance built on top of this empirically grounded entry layer.
```

中文解释：

```text
TalkingData 不证明无助感机制。
它证明我们的任务暴露环境不是凭空编造。
四个 world 是反事实实验，不是四个真实标签世界。
```

## 10. 最终判断

TalkingData 的说服力是中等但很有用。

它不能承担：

```text
心理机制验证
四世界真实性验证
Huys / Bayesian / FamilyHelperAgent 的因果验证
```

但它可以承担：

```text
真实手机使用底座
entry layer 外部校准
observed-anchor world 识别
retention/dropoff proxy sanity check
```

因此最合理的论文结构是：

```text
1. 用 TalkingData 锚定正常手机使用机会。
2. 找到一个最接近真实 traces 的 empirical-anchor condition。
3. 在这个基础上做四个 counterfactual friction/support world。
4. 用 ablation 和机制 audit 验证 helplessness / controllability / support loop。
```

一句话：

```text
TalkingData 是真实世界入口锚点，不是无助感标签；
四个 world 是在真实入口锚点上的机制反事实实验。
```
