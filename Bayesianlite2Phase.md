# Bayesian Gated-Lite2 分阶段推进计划

## 总体定位

`Bayesian gated-lite2` 不是把当前系统改成完整 Bayesian RL agent，而是在保留 LLM social simulation 主链的前提下，引入一个受限、可审计的 Bayesian action-outcome learning 模块。

核心目标：

```text
LLM 负责语义理解、task appraisal、event appraisal、attribution、reflection、interview；
Bayesian policy-lite 负责从 task_family + action -> outcome 的经验中学习；
rule 不再作为常规策略主干，只保留为 fallback / safety guard；
Bayesian 只有在证据足够时，才能小幅影响真实行动概率。
```

完整 gated-lite2 不应一步到位上线。更稳妥的路线是：

```text
shadow validation
-> utility calibration
-> conservative gated-lite pilot
-> gated-lite main experiment
-> ablation / sensitivity / validation
```

## Phase 1: Shadow Validation

当前状态：已完成。

目标：

```text
只计算 Bayesian posterior predictive policy，不干预真实行为。
```

已完成内容：

```text
proto_bayesian_policy_memory
policy_outcome_subtype
action-specific Dirichlet prior
Q_bayes
pi_bayes_shadow
confidence_by_action
posterior_entropy_by_action
payload audit
posterior update for observed action only
```

已验证内容：

```text
shadow payload 全覆盖
uses_post_outcome_information_for_policy=false
strategy_unchanged=true
shadow mode 不改变真实策略
C_hat 与 pi_avoid 呈理论一致关系
```

当前发现：

```text
Bayesian shadow 有解释信号；
但 pi_bayes_shadow 明显偏向 avoid；
因此不能直接进入强行为介入。
```

本阶段可声称：

```text
We implemented a shadow Bayesian posterior predictive audit for action-outcome learning.
```

本阶段不可声称：

```text
Bayesian policy improves agent behavior.
Bayesian posterior already drives agent decisions.
```

## Phase 2: Utility Calibration

目标：

```text
先校准 Bayesian 小顾问的 utility，避免它因为失败成本过高而过度偏向 avoid。
```

要做的修改：

```text
重新检查 no_attempt utility
区分 helpless_avoid / risk_avoid / low_value_avoid 的长期成本
检查 success_with_help 的 utility 是否需要区分 expected enabling support 与 substituting support
确保 pre-outcome Q_bayes 不使用 post-outcome support_mode / avoid_reason / attribution
保留 action-specific prior，不把 impossible outcome 设成高先验
```

建议方向：

```text
helpless_avoid: 应有较明显长期负效用
risk_avoid: 可为轻负或接近中性，尤其在高风险任务中
low_value_avoid: 可接近中性
no_attempt: 不应比所有 failure 都“安全太多”，否则 Bayesian 会过度保守
success_self: 高正效用
success_with_help: 正效用，但应弱于真正可控的 self success；如果预期帮助有效，可适度提高
```

验证方式：

```text
仍然使用 shadow mode
重新跑 3-seed 10-day 4-world shadow 实验
检查 pi_bayes_shadow 是否仍过度偏 avoid
检查 C_hat / pi_avoid / pi_help / pi_attempt 的方向是否合理
```

成功标准：

```text
baseline_low_friction 中 avoid 不应长期成为绝对 dominant
low_friction_high_assist 中 seek_help 或 attempt_self 应该有明显优势
high_friction_low_assist 中 avoid 上升可以接受，但不能完全压倒其他 action
pi_bayes_shadow 与 friction/support 条件保持理论一致方向
```

本阶段仍不可声称：

```text
Bayesian policy has changed behavior.
```

## Phase 3: Gated-Lite Infrastructure + Smoke Validation

当前事实：

```text
截至 Phase 3，runtime 支持 PROTO_BAYESIAN_POLICY_LITE_MODE=off/shadow/gated_lite。
shadow 计算 pi_bayes_shadow 与 audit payload，不改变真实 action，但会更新 posterior。
gated_lite 计算 pi_bayes_shadow/pi_bayes，生成有界 pi_final，介入真实 action，并更新 posterior。
attempt_strategy.py 的 precomputed_final_weights 是 gated-lite 的真实策略入口。
llm_psychology.py 的 StrategyDeliberationResult.final_weights 是 pi_ref 的第一版来源。
```

本阶段目标：

```text
把 Bayesian posterior predictive policy 行为介入基础设施安全接上。
Phase 3 只做 max_delta=0 dry-run 与 1-seed smoke，不做正式 3-seed pilot。
介入必须同时满足 confidence gate、entropy gate、max_delta、probability floor、renormalization、invalid posterior fallback。
Bayesian 不能接管 agent，只能在 LLM/rule 语义策略基础上做有界微调。
```

本阶段非目标：

```text
不实现 full Bayesian RL。
不让 Bayesian 替代 task appraisal / event appraisal / attribution / reflection / interview。
不修改 outcome model、helplessness update、scope spillover、experience memory 主逻辑。
不新增数据库 schema。
不把 safety guard 写回 rule-heavy policy。
不直接进入 Phase 4 主实验。
不在 Phase 3 做 3-seed pilot、max_delta=0.10 或 gate/entropy sensitivity。
```

推荐初始配置：

```text
PROTO_BAYESIAN_POLICY_LITE_MODE=gated_lite
PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE=theory_v2
PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD=0.50
PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD=0.85
PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA=0.05
PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR=0.05
PROTO_BAYESIAN_POLICY_LITE_TAU=1.0
PROTO_BAYESIAN_POLICY_LITE_CONFIDENCE_K=4
PROTO_BAYESIAN_POLICY_LITE_RHO=1.0
PROTO_BAYESIAN_POLICY_LITE_WEIGHT=1.0
```

备注：

```text
max_delta=0.05 是第一轮 smoke 推荐值。
max_delta=0.10 不作为 Phase 3 默认值，只进入 Phase 4 sensitivity / stress test。
max_delta=0 必须等价于 no Bayesian intervention，用于回归测试。
prob_floor=0.05 与 attempt_strategy.py 现有 sampler floor 对齐。
```

需要新增或修改的文件：

```text
examples/digital_friction_mvp/config_runtime.py
  - VALID_BAYESIAN_POLICY_LITE_MODES 增加 gated_lite
  - RuntimeConfig 增加 gate_threshold / entropy_threshold / max_delta / prob_floor
  - env parsing 增加 clamp 与 ValueError

examples/digital_friction_mvp/proto/bayesian_policy_lite.py
  - 复用现有 posterior / Q_bayes / softmax / confidence / entropy
  - 新增 gated-lite policy shift helper
  - 保持 shadow mode 行为完全不变

examples/digital_friction_mvp/proto/agent.py
  - action 前先得到 strategy_deliberation.final_weights
  - 调用 policy-lite helper 生成 gated pi_final
  - gated_lite 模式下把 pi_final 传给 choose_attempt_strategy(..., precomputed_final_weights=pi_final)
  - shadow/off 模式下不传 precomputed_final_weights，保持现状
  - outcome 后仍只更新 observed action 的 posterior

examples/digital_friction_mvp/proto/attempt_strategy.py
  - 优先不改；复用已有 precomputed_final_weights 接口
  - 如需扩展，只允许补 audit/rationale，不改抽样语义

examples/digital_friction_mvp/world_runner.py
  - fingerprint 增加 gate_threshold / entropy_threshold / max_delta / prob_floor

examples/digital_friction_mvp/analysis_bayesian_policy_shadow.py
  - 可追加 gated-lite audit summary，但不是 Phase 3 最小必需项

examples/digital_friction_mvp/tests/
  - 更新 policy-lite、runtime、agent integration 相关测试
```

核心机制链：

```text
1. rule_strategy_weights = compute_rule_strategy_weights(...)
2. strategy_deliberation = resolve_strategy_deliberation(..., rule_weights=rule_strategy_weights)
3. pi_ref = normalize(strategy_deliberation.final_weights)
4. pi_bayes = softmax(Q_bayes(policy_outcome_posterior), tau)
5. confidence_by_action = update_count / (update_count + confidence_k)
6. gate_by_action[action] = confidence >= gate_threshold and entropy <= entropy_threshold
7. raw_delta[action] = pi_bayes[action] - pi_ref[action]
8. gated_delta[action] = raw_delta[action] * confidence_by_action[action] if gate opens else 0
9. delta_applied[action] = clip(gated_delta[action], -max_delta, +max_delta)
10. pi_after_bayesian_shift = normalize(pi_ref + delta_applied)
11. pi_final = safety_guard(pi_after_bayesian_shift, prob_floor)
12. choose_attempt_strategy(..., precomputed_final_weights=pi_final)
13. outcome / appraisal / attribution / helplessness / experience memory 按旧流程继续
14. Bayesian posterior 只用 observed action + policy_outcome_subtype 做 post-outcome update
```

第一版 pi_ref 定义：

```text
pi_ref = strategy_deliberation.final_weights
```

理由：

```text
这是当前系统已经存在的 LLM/rule hybrid strategy distribution。
它已经包含 rule weights、LLM strategy deliberation、fallback 和 normalization。
Phase 3 不新增 LLM-only policy 接口，避免为了论文术语创造一套未验证接口。
```

gated shift 伪代码：

```python
if mode != "gated_lite":
    pi_final = None
    intervention_applied = False

else:
    pi_ref = normalize(strategy_deliberation.final_weights)
    pi_bayes = softmax(q_bayes, tau=tau)

    for action in ACTIONS:
        gate_open = (
            confidence_by_action[action] >= gate_threshold
            and posterior_entropy_by_action[action] <= entropy_threshold
        )
        raw_delta = pi_bayes[action] - pi_ref[action]
        if gate_open:
            delta_applied[action] = clip(
                raw_delta * confidence_by_action[action],
                -max_delta,
                +max_delta,
            )
        else:
            delta_applied[action] = 0.0

    pi_after_bayesian_shift = normalize(pi_ref + delta_applied)
    pi_final = apply_probability_floor_and_normalize(
        pi_after_bayesian_shift,
        floor=prob_floor,
    )

    if invalid(pi_final):
        pi_final = pi_ref
        safety_guard_status = "fallback_to_ref"

    intervention_applied = any(abs(delta) > 0 for delta in delta_applied.values())
```

safety guard 边界：

```text
只处理数学和可行性问题：NaN、负数、全零、缺 action、概率和不为 1、低于 prob_floor、posterior invalid。
不写入“helplessness 高就 avoid”“support 差就 avoid”这类行为规则。
如果 safety guard 频繁 fallback，说明 gated-lite 机制不稳定，应暂停，而不是扩大规则补丁。
```

payload 必须记录：

```text
pi_prior
pi_strategy_reference
pi_ref
q_bayes
pi_bayes
pi_bayes_shadow
confidence_by_action
posterior_entropy_by_action
alpha_total_by_action
posterior_update_count_before
posterior_update_count_after
gate_by_action
delta_before_clamp
delta_applied
pi_after_bayesian_shift
pi_final
max_delta_per_action
gate_threshold
entropy_threshold
prob_floor
safety_guard_status
intervention_applied
final_delta_after_floor
max_abs_final_delta
total_variation_distance
uses_post_outcome_information_for_policy=false
strategy_unchanged=false
posterior_update_action
policy_outcome_subtype
utility_profile
mode=gated_lite
```

重要解释：

```text
strategy_unchanged=false 只表示 Bayesian gated-lite 接管了传入 sampler 的最终概率入口。
它不表示 sampled action 一定改变，因为 action 仍然是按 pi_final 抽样。
final_delta_after_floor = pi_final - pi_ref，用于区分 Bayesian 原始 shift 与 floor/renormalization 后 sampler 实际收到的最终变化。
 第一版可先只记录概率差，不强行做 counterfactual resampling。
```

测试计划：

```text
test_runtime.py
  - 默认 mode 仍为 off
  - env 可设置 gated_lite
  - gate_threshold clamp 到 [0, 1]
  - entropy_threshold clamp 到 [0, 1]
  - max_delta clamp 到 >= 0
  - prob_floor clamp 到 [0, 1 / action_count)
  - illegal mode/profile 抛 ValueError
  - fingerprint 包含新增 gate keys

test_bayesian_policy_lite.py
  - shadow_v1 / theory_v2 旧测试保持通过
  - mode=shadow 完全不返回 pi_final
  - mode=gated_lite 返回 pi_final
  - confidence below threshold 或 entropy above threshold 时 delta=0
  - confidence 与 entropy 同时过门时 delta 朝 pi_bayes 方向移动
  - max_delta 生效
  - max_delta=0 时没有 Bayesian intervention
  - probability floor 生效且 renormalization 后概率和为 1
  - final_delta_after_floor / max_abs_final_delta 正确
  - invalid posterior fallback 到 pi_ref
  - helper 不原地修改 memory
  - pre-outcome leakage invariance 继续通过

agent integration tests
  - mode=off/shadow 在同 seed 下保持 sampled action / outcome / helplessness 不变
  - mode=gated_lite 时 choose_attempt_strategy 收到 precomputed_final_weights
  - gated_lite payload 包含 pi_ref / pi_final / gate_by_action / delta_applied
  - outcome 后只更新 observed action posterior
  - avoid 仍只更新 avoid -> no_attempt
```

建议验证命令：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_bayesian_policy_lite.py \
  examples/digital_friction_mvp/tests/test_runtime.py \
  -q

python -m pytest \
  examples/digital_friction_mvp/tests/test_bayesian_control_audit.py \
  examples/digital_friction_mvp/tests/test_experience_memory.py \
  examples/digital_friction_mvp/tests/test_llm_psychology.py \
  examples/digital_friction_mvp/tests/test_stream_episode_recording.py \
  -q

python -m py_compile \
  examples/digital_friction_mvp/config_runtime.py \
  examples/digital_friction_mvp/proto/bayesian_policy_lite.py \
  examples/digital_friction_mvp/proto/agent.py \
  examples/digital_friction_mvp/proto/attempt_strategy.py \
  examples/digital_friction_mvp/world_runner.py

git diff --check -- \
  examples/digital_friction_mvp/config_runtime.py \
  examples/digital_friction_mvp/proto/bayesian_policy_lite.py \
  examples/digital_friction_mvp/proto/agent.py \
  examples/digital_friction_mvp/proto/attempt_strategy.py \
  examples/digital_friction_mvp/world_runner.py \
  examples/digital_friction_mvp/tests \
  Bayesianlite2Phase.md \
  frictionchangeLog.md
```

pilot 规模：

```text
Phase 3A smoke:
  max_delta=0 dry-run
  1 paired seed
  4 worlds
  10 days
  目标是验证接入路径、payload、posterior update，真实行为应等价 no intervention

Phase 3B smoke:
  1 paired seed
  4 worlds
  10 days
  max_delta=0.05
  gate_threshold=0.50
  entropy_threshold=0.85
  prob_floor=0.05

Phase 4 conservative pilot:
  3 paired seeds
  4 worlds
  10 days
  与 20260512 theory_v2 shadow-only 设置保持一致，只把 mode 改成 gated_lite

Phase 4 sensitivity:
  max_delta in {0.00, 0.05, 0.10}
  gate_threshold in {0.33, 0.50, 0.67}
  entropy_threshold in {0.75, 0.85, 0.95}
```

推荐 Phase 3B smoke 实验命名：

```text
exp_202605xx_policy_lite_gated_lite_theory_v2_smoke_10d_60min
```

重点检查：

```text
attempt_rate 是否突然崩塌
avoidance 是否异常升高
help_seek 是否合理变化
helplessness 是否出现 runaway loop
intervention_applied 比例是否合理
Bayesian delta 平均幅度是否足够小
低摩擦高支持世界是否没有被推向过度 avoid
actual behavior 与 20260512 shadow-only 的方向差异是否可解释
payload coverage 是否保持 1.0
uses_post_outcome_information_for_policy 是否始终 false
```

成功标准：

```text
intervention_applied 不是 0，但也不是每次都介入
平均 total_variation_distance 保持很小
max_delta 生效
gate_threshold 生效
行为方向不崩
payload 能解释每一次 Bayesian 是否介入和介入多少
low_friction_high_assist 不被推向过度 avoid
high_friction_low_assist 可以更保守，但不能所有 action 都被 avoid 吞掉
max_delta=0 与 shadow/off 的真实行为一致性测试通过
```

失败信号：

```text
avoidance 在所有 worlds 中异常升高
low_friction_high_assist 也被推向 avoid
helplessness 出现明显 runaway
Bayesian delta 经常达到上限
safety guard 经常 fallback
payload 缺字段或 audit 无法复盘
gated_lite 让 world manipulation 的基本方向反转且无法解释
max_delta=0 不能复现 baseline，说明接入破坏了主链
```

实施顺序：

```text
1. 先补 runtime 配置与 fingerprint，不接 agent。
2. 在 bayesian_policy_lite.py 写 gated shift helper，并用单元测试锁定数学行为。
3. 在 agent.py 用 precomputed_final_weights 接入 choose_attempt_strategy。
4. 跑 off/shadow 回归，确认旧模式不变。
5. 跑 gated_lite 单元与 integration tests。
6. 跑 Phase 3A 1-seed smoke。
7. 如果 Phase 3A 没有 runaway，再跑 Phase 3B 3-seed pilot。
8. 只有 Phase 3B 稳定后，才进入 Phase 3C sensitivity 或 Phase 4。
```

本阶段可声称：

```text
We implemented a conservative gated Bayesian posterior-predictive shift that can only make bounded, evidence-gated changes to the LLM/rule semantic policy.
```

本阶段不可声称：

```text
We have completed the main causal evaluation.
We implemented a full Bayesian RL agent.
Bayesian policy has been externally validated.
```

## Phase 4: Gated-Lite Main Experiment

目标：

```text
在 conservative pilot 稳定后，正式评估 gated-lite2 的行为机制效果。
```

建议实验设置：

```text
seeds >= 10
4 worlds
10 days 或更长
same paired design
显式记录所有 gated-lite2 env configs
```

核心对照：

```text
current rule+LLM baseline
Bayesian controllability audit-only
Bayesian policy-lite shadow-only
Bayesian gated-lite2
```

主要问题：

```text
gated-lite2 是否减少 rule-heavy dependence？
gated-lite2 是否保留 LLM semantic coherence？
gated-lite2 是否让 action-outcome learning 更可解释？
gated-lite2 是否没有导致过度 avoid？
gated-lite2 是否在不同 seeds 下稳定？
```

主要指标：

```text
attempt_rate
help_seek_rate
avoid_rate
success_rate
negative_feedback_rate
helplessness_delta
trust_delta
avoidance_delta
intervention_applied_rate
mean_bayesian_delta
total_variation_distance(pi_semantic, pi_final)
gate_open_rate
safety_guard_fallback_rate
```

本阶段可声称：

```text
gated-lite2 behavior is influenced by a bounded Bayesian posterior predictive module.
```

仍需谨慎：

```text
如果没有 human validation，不能声称真实老年人行为已被验证。
```

## Phase 5: Ablation, Sensitivity, And Validation

目标：

```text
为 AAAI / AISI / AAMAS 审稿准备机制证据，证明结果不是由某个手调参数或 prompt 偶然制造。
```

必要消融：

```text
gated-lite2 without Bayesian shift
gated-lite2 without LLM semantic adjustment
gated-lite2 without evidence gate
gated-lite2 without max_delta
gated-lite2 max_delta=0
gated-lite2 without avoid-as-evidence
shadow-only vs gated-lite2
```

敏感性分析：

```text
max_delta_per_action = 0.00 / 0.05 / 0.10 / 0.15
gate_threshold = 0.33 / 0.50 / 0.67
tau sensitivity
confidence_k sensitivity
prob_floor sensitivity
rho sensitivity
utility mapping sensitivity
```

shadow/prediction 分析：

```text
pi_bayes_shadow 是否预测下一步 action
pi_bayes_shadow 是否预测下一步 outcome
Q_bayes 是否与 success / failure / avoid 方向一致
C_hat 与 pi_avoid / helplessness_delta / avoidance_delta 的关系
posterior confidence 是否随经验增加而上升
```

human / qualitative validation：

```text
expert trajectory validation
older adult / caregiver vignette validation
LLM attribution coding validation
interview grounding validation
```

本阶段要防的 reviewer 问题：

```text
是不是 rule 仍在主导？
是不是 Bayesian 只是 heuristic？
是不是 utility 手调制造结果？
是不是 LLM prompt artifact？
是不是没有现实数据支撑？
是不是过度回避？
是不是缺少 calibration？
```

## 推荐当前下一步

当前项目已经完成 Phase 1。

最合理的下一步是：

```text
进入 Phase 2: Utility Calibration
```

不建议立刻做：

```text
full gated-lite2 main experiment
Bayesian policy 完全接管
max_delta >= 0.10 的正式实验
声称 Bayesian policy 已改善行为
```

推荐短期路线：

```text
1. 调整 utility，降低 shadow 过度 avoid 倾向。
2. 重新跑 shadow-only 小实验。
3. 如果 shadow 分布更合理，再做 conservative gated-lite pilot。
4. pilot 稳定后，再进入 main experiment 和 ablation。
```
