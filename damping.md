# Damping / Saturation / Recovery Literature Notes

本文档整理 `helplessness_score` 的 `damping`、`saturation` 和 `recovery` 校准依据。用途不是证明某个精确代码参数来自文献，而是为论文和后续调参提供可防守的理论边界：

- 文献可以支持变量方向、相对强弱、非线性边际效应、时间消散、reminder 维持、mastery recovery。
- 文献不能直接支持“单次事件应该加几分”或“damping floor 必须等于某个数值”。
- 代码参数应写成 `literature-constrained heuristic calibration`，并通过 sensitivity analysis 报告。

---

## 0. 当前问题

当前 `examples/digital_friction_mvp/proto/state_update.py` 的高 H damping 是：

```python
damping_factor = clamp(1.0 - 0.45 * helplessness_before / 100.0, 0.55, 1.0)
```

这意味着即使 `helplessness_score` 已经在 90 附近，一次负面事件仍保留至少 55% 的伤害。最近 7 天实验里，`baseline_low_friction` 最终 H 接近 98，说明当前模型有明显 ceiling effect：

- 任务 episode 太密。
- 单次负面事件增量偏大。
- 高 H 区间边际伤害衰减不够强。
- 缺少日内或阶段内 saturation。
- 成功和可控经验的恢复力不够抵消密集失败。

因此建议把修改目标定为：

```text
baseline_low_friction 7d: H roughly 45-65
low_friction_high_assist 7d: H roughly 35-60
high_friction_high_assist 7d: H roughly 65-85
high_friction_low_assist 7d: can approach 85-95, but should not trivially hit 100
```

这些目标值是仿真校准目标，不是文献直接给出的心理量表值。

---

## 1. Evidence Table

| Use in model | Literature | DOI | Original content / 原文讲了什么 | Supports which model change | Claim boundary |
|---|---|---|---|---|---|
| Core accumulation should depend on uncontrollability, not failure count alone. | Maier & Seligman (1976), *Learned helplessness: Theory and evidence*. | `10.1037/0096-3445.105.1.3` | The review describes motivational, cognitive, and emotional effects of uncontrollable events. Its core claim is that organisms learn behavior-outcome independence. | Keep `event_level_uncontrollability` as a core harm source; negative updates should be strongest when effort and outcome appear disconnected. | Does not provide event-level delta or damping floor. |
| H should be bounded and context-dependent; objective uncontrollability is not enough. | Maier & Seligman (2016), *Learned helplessness at fifty*. | `10.1037/rev0000033` | Short original phrase: "Passivity ... default, unlearned response to prolonged aversive events." The paper separates objective helplessness from subjective detection/expectation of control. | Strengthen high-H damping: after the agent is already in a high helplessness state, another similar failure should carry less new information. Keep LLM appraisal as semantic evidence, not direct H. | Supports nonlinearity and control detection, not exact formula. |
| Chronicity and generalization should depend on attribution; not every failure should accumulate equally. | Abramson, Seligman & Teasdale (1978), *Learned helplessness in humans: Critique and reformulation*. | `10.1037/0021-843X.87.1.49` | Short original phrase: "chronicity ... depend on the stability" and generality on globality. The paper says people attribute perceived noncontingency to causes that shape future helplessness. | Let stable/global/internal attribution slow recovery and increase persistence; transient/specific/external attribution should reduce carryover and support faster decay. | Does not validate LLM attribution accuracy or any fixed multiplier. |
| Repeated uncontrollable stress can produce durable deficits, but that does not imply unbounded linear accumulation. | Seligman, Rosellini & Kozak (1975), *Learned helplessness in the rat: time course, immunization, and reversibility*. | `10.1037/h0076431` | PubMed abstract reports failure to escape at multiple delays after inescapable shock and that prior escape learning prevented later retardation. | Support a persistent latent state and `controllable_success_protection`. Also supports saturation: once learned helplessness is established, repeated same-type evidence should maintain state more than add linearly. | Animal shock paradigm; not a direct numeric model for older adults' digital service friction. |
| Without reminders, learned-helplessness-like deficits can dissipate over days; reminders maintain them. | Maier (2001), *Exposure to the stressor environment prevents the temporal dissipation of behavioral depression/learned helplessness*. | `10.1016/S0006-3223(00)01095-7` | Short original phrase: "repeated exposures prolonged it indefinitely." The abstract states behavioral changes persist only a few days unless reminder cues prolong them. | Add reminder-gated temporal decay: if a day has no helplessness-relevant negative digital episodes, H should drift downward slightly; repeated similar friction should maintain H but be capped by daily saturation. | Rat IS environment and PTSD/depression analogy; use only as support for temporal decay/reminder maintenance, not clinical prediction. |
| Prior controllable success can protect against later uncontrollable stress. | Amat et al. (2006), *Previous experience with behavioral control over stress blocks...*. | `10.1523/JNEUROSCI.3630-06.2006` | The paper reports that previous control blocks later behavioral and dorsal raphe effects of uncontrollable stress through vmPFC. | Keep and possibly strengthen `controllable_success_protection`; successful self-control should buffer later negative deltas. | Neuroscience animal evidence; supports direction and mechanism, not a specific cap like 0.45. |
| Behavioral control can have enduring, cross-situational protective effects. | Baratta, Seligman & Maier (2015), *Behavioral control blunts reactions...*. | `10.1016/j.ynstr.2014.09.003` | The abstract says control limits current stressor impact and produces enduring trans-situational immunization. | Recovery should be strongest when success is active and autonomous, not merely when someone substitutes for the agent. Successful control should affect future damping/protection. | Does not prove support response should directly lower H. |
| Human perceived control can reverse passivity after repeated uncontrollability. | Wang & Delgado (2021), *The Protective Effects of Perceived Control During Repeated Exposure to Aversive Stimuli*. | `10.3389/fnins.2021.625816` | The abstract reports repeated uncontrollability reduced avoidance attempts, while later controllability rescued avoidance behavior. | Support explicit recovery terms for controllable success and enabling support. Also supports using behavior attempts as a QC signal. | Lab aversive tone task; use as directional support, not direct H-scale mapping. |
| Mastery is the strongest recovery evidence; failures hurt less after strong efficacy is established. | Bandura (1977), *Self-efficacy: Toward a unifying theory of behavioral change*. | `10.1037/0033-295X.84.2.191` | Short original phrase: "Successes raise mastery expectations; repeated failures lower them." The paper also says strong efficacy reduces the negative impact of occasional failures. | Strengthen `success_self` and `ended_failure_streak` recovery; allow high-quality enabling support to improve future self-efficacy, not directly erase H. | Self-efficacy is related to but not identical with helplessness. |
| Computationally, control can be treated as beliefs/priors; updates should be bounded and diminishing as beliefs become strong. | Huys & Dayan (2009), *A Bayesian formulation of behavioral control*. | `10.1016/j.cognition.2009.01.008` | The abstract formalizes controllability using prior distributions over environments and links maladaptive beliefs to inference. | Use bounded Bayesian-like saturation: repeated similar evidence should update less when the agent already strongly expects low control; run sensitivity for priors and decay. | Supports formalization and bounded belief update, not a particular deterministic heuristic. |
| Stress systems include negative feedback; repeated chronic stress can alter feedback. | Tafet & Ortiz Alonso (2025), *Learned helplessness and learned controllability*. | `10.3389/fpsyt.2025.1600165` | Short original phrase: "Repeated perception of lack of control may lead to learned helplessness." The review also discusses HPA negative feedback and chronic stress dysregulation. | Supports bounded feedback-style modeling and differentiating acute vs chronic repeated exposure. | Broad review; do not use it to claim exact event-level deltas. |

---

## 2. What The Literature Supports For Damping

### 2.1 Stronger high-H marginal damping

The current formula keeps a minimum harm multiplier of `0.55`. That is too weak for a bounded 0-100 psychological state when episodes are dense.

Literature-based reasoning:

- Learned helplessness is about perceived action-outcome noncontingency and expectation, not a raw count of failures.
- Once an agent already strongly expects low control, another similar failure contains less new psychological information.
- Huys & Dayan support treating control as a belief/prior. In a belief update view, repeated same-direction evidence should show diminishing marginal movement as confidence grows.

Recommended sweep:

```python
# Candidate A: stronger nonlinear high-H damping
harm_damping = clamp(1.0 - 0.80 * (H / 100.0) ** 1.25, 0.20, 1.0)

# Candidate B: very conservative near-ceiling damping
harm_damping = clamp((1.0 - H / 100.0) ** 0.85, 0.15, 1.0)

# Candidate C: piecewise readable version
if H < 50:
    harm_damping = 1.0 - 0.35 * H / 50.0
elif H < 80:
    harm_damping = 0.65 - 0.30 * (H - 50.0) / 30.0
else:
    harm_damping = 0.35 - 0.15 * (H - 80.0) / 20.0
harm_damping = clamp(harm_damping, 0.20, 1.0)
```

Practical recommendation:

```text
Use Candidate A first.
Report sensitivity over floor = 0.15 / 0.20 / 0.30.
Do not claim the floor is literature-derived.
```

### 2.2 Damping should be evidence-sensitive

High-H damping should not flatten all events equally. A high-H agent who finally experiences autonomous success should still recover meaningfully.

Recommended direction:

```text
Apply stronger damping mainly to negative harm.
Do not apply the same strong damping to success recovery.
```

Rationale:

- Bandura supports mastery success as a strong source of efficacy restoration.
- Wang & Delgado support controllability rescuing avoidance behavior after repeated uncontrollability.
- If success recovery is damped too strongly at high H, the model becomes irreversible, which is not defensible for a learned state.

---

## 3. What The Literature Supports For Saturation

### 3.1 Daily or stage-level harm saturation

Dense simulation creates many task episodes per day. Treating all of them as independent psychological shocks produces artificial ceiling effects.

Literature-based reasoning:

- Learned helplessness can be persistent, but the classic literature does not imply unlimited additive harm for every repeated exposure.
- Maier (2001) suggests repeated reminder exposure can maintain learned helplessness over time. This is closer to "maintenance pressure" than unbounded linear accumulation.
- Huys & Dayan's belief framing also supports diminishing returns when repeated evidence confirms an already-held low-control prior.

Recommended sweep:

```python
# Per-agent daily net harm cap, after event-level rule computation.
daily_positive_harm_budget = 4.0  # sweep 3.0 / 5.0 / 7.0

# Same task-family saturation.
same_family_harm_factor = 1.0 / (1.0 + 0.35 * prior_negative_events_same_family_today)
same_family_harm_factor = clamp(same_family_harm_factor, 0.35, 1.0)
```

Practical recommendation:

```text
Start with daily_positive_harm_budget = 5.0.
Add same-family saturation only if daily cap alone is not enough.
```

Claim boundary:

```text
The cap is a simulation calibration safeguard.
The literature supports nonlinearity and reminder-based maintenance, not the exact budget value.
```

### 3.2 Reminder-gated maintenance instead of runaway accumulation

The Maier (2001) result is useful because it separates two things:

- Without re-exposure/reminders, behavioral deficits can dissipate.
- With repeated reminders, deficits can persist.

For our digital-friction simulation, this suggests:

```python
if no_helplessness_relevant_negative_episode_today:
    H = max(0.0, H - daily_decay)
elif repeated_similar_negative_episode_today:
    H = H + capped_harm
```

Suggested sweep:

```text
daily_decay_if_no_reminder = 0.4 / 0.8 / 1.2
daily_decay_if_successful_mastery_day = 0.8 / 1.5 / 2.2
```

This helps make H a psychological state that can recover, rather than a one-way penalty counter.

---

## 4. What The Literature Supports For Recovery

### 4.1 Autonomous success should recover more than helped success

Bandura's self-efficacy theory supports performance accomplishments as the most dependable source of efficacy information. In our model, that maps most safely to:

```text
success_self > enabling_support_success > substituting_support_success
```

Recommended direction:

```python
success_self_recovery = base_success_recovery * mastery_multiplier
success_with_enabling_help_recovery = smaller_recovery + future_self_efficacy_credit
success_with_substituting_help_recovery = small_recovery_or_none
```

Do not let support become a universal failure-canceling buffer. Helper support should matter mainly by increasing task success probability, preserving autonomy, and creating later mastery evidence.

### 4.2 Recovery should strengthen after a broken failure streak

If the agent has had several failures and then succeeds through its own action, this is especially informative evidence against "nothing I do matters".

Recommended sweep:

```python
ended_failure_streak_bonus = 0.25  # current
# Try:
ended_failure_streak_bonus = 0.5 / 0.8 / 1.0
```

This is supported directionally by:

- Abramson et al.: expectations of uncontrollability drive symptoms.
- Bandura: mastery experiences alter efficacy expectations.
- Wang & Delgado: controllability can rescue passivity after repeated uncontrollability.

### 4.3 Prior controllable success should reduce later harm

The current code already has:

```python
controllable_success_protection = clamp(memory * 0.45, 0.0, 0.45)
```

Directionally this is well supported by Amat et al. (2006), Maier & Seligman (2016), and Baratta et al. (2015). However, the exact `0.45` cap should remain a calibrated heuristic.

Recommended sweep:

```text
protection_cap = 0.35 / 0.45 / 0.60
memory_decay_half_life = 3d / 7d / 14d
```

If the simulation still saturates, increase recovery and high-H damping before increasing protection too much. Otherwise the model may make early success overly immunizing.

---

## 5. Concrete Calibration Plan

### Pass 1: Minimal code-level scale correction

Do not change the theoretical structure. Only change the scale:

```text
1. Apply global negative update scale: 0.45 / 0.60 / 0.75.
2. Replace linear damping floor 0.55 with nonlinear high-H damping floor 0.20.
3. Add daily positive harm cap: 5.0.
4. Keep success recovery undamped by high-H harm damping.
```

Expected target:

```text
baseline_low_friction should stop near 45-65 after 7d.
low_friction_high_assist should remain lower than baseline.
high_friction_low_assist may be highest but should not hit 100 for every agent.
```

### Pass 2: Recovery tuning

If H still rises too fast:

```text
1. Increase success_self recovery.
2. Increase ended_failure_streak_bonus.
3. Add daily_decay_if_no_reminder.
```

If H becomes too volatile:

```text
1. Reduce daily decay.
2. Lower recovery bonus.
3. Keep daily harm cap but use higher cap.
```

### Pass 3: Report sensitivity

Minimum sensitivity table:

```text
damping_floor: 0.15 / 0.20 / 0.30
daily_harm_cap: off / 5.0 / 7.0
global_negative_scale: 0.45 / 0.60 / 0.75
success_recovery_scale: 1.0 / 1.25 / 1.5
daily_decay_if_no_reminder: off / 0.8 / 1.2
```

Main claim should hold across reasonable settings:

```text
world ordering and qualitative trajectory patterns remain stable;
absolute H levels do not trivially saturate.
```

---

## 6. Suggested Paper Wording

> Literature on learned helplessness and controllability motivates a bounded, nonlinear transition rather than an unbounded event counter. Uncontrollable outcomes provide stronger helplessness evidence than ordinary failures; however, repeated similar evidence has diminishing marginal impact once low-control expectations are already high. We therefore apply bounded damping and daily saturation to negative updates. Conversely, successful autonomous action and learned controllability provide recovery and protection terms. Published studies are used to constrain construct inclusion, directionality, and relative ordering; event-level constants are calibrated heuristics and are evaluated through sensitivity analyses.

---

## 7. What Not To Claim

Do not claim:

```text
The literature proves damping_floor = 0.20.
The literature proves daily_harm_cap = 5.
Seven simulated days correspond to seven real psychological days.
The model predicts clinical depression or real older adults' trajectories.
Survey score is ground-truth helplessness.
LLM appraisal is a clinical psychological measurement.
```

Safe claim:

```text
The literature supports bounded, nonlinear, controllability-sensitive, attribution-sensitive, and recovery-capable updating. The exact numeric parameters are calibrated and sensitivity-tested.
```

---

## 8. Local Original Text Pointers

These are the local MinerU / extracted text locations used to ground the table above:

| Source | Local path | Useful lines |
|---|---|---|
| Tafet & Ortiz Alonso (2025) | `paper/mineruex/learned_helplessness_and_learned_controllability_review_2025/auto/learned_helplessness_and_learned_controllability_review_2025.md` | DOI at lines 21-24; repeated lack of control and learned helplessness at line 36; sustained/prolonged uncontrollable exposure and learned controllability at line 44; HPA feedback/chronic stress at line 52; contingency and subjective control at lines 56-62; learned controllability and later moderation at lines 68-72; recovery/reversal through active responses at lines 84-88. |
| Maier & Seligman (2016) | `paper/mineruex/learned_helplessness_at_fifty_2016/auto/learned_helplessness_at_fifty_2016.md` | Abstract and default passivity/control-detection claim at lines 7-9; objective/subjective helplessness and contingency definition at lines 17-31; attribution and time-course discussion at lines 47-50; immunization and persistent control pathway at lines 157-165. |
| Abramson, Seligman & Teasdale (1978) | `paper/mineruex/Learned Helplessness in Humans./auto/Learned Helplessness in Humans..md` | Reformulation abstract at lines 1-7; old model and deficits at lines 9-15; stability/globality/chronicity at lines 213-231; therapy/recovery strategies at lines 265-305; prevention/immunization wording at line 311. |
| Bandura (1977) | `paper/mineruex/Self-Efficacy- Toward a Unifying Theory of Behavioral Change./auto/Self-Efficacy- Toward a Unifying Theory of Behavioral Change..md` | Abstract and treatment mechanism at lines 1-5; efficacy vs outcome expectations at lines 32-40; magnitude/generality/strength and cumulative effort effects at lines 48-50; performance accomplishments and failure timing at lines 52-58. |

For sources not currently in MinerU form, use the DOI/PubMed/PMC pages listed below as the source of bibliographic and abstract-level evidence.

---

## 9. References

Abramson, L. Y., Seligman, M. E. P., & Teasdale, J. D. (1978). Learned helplessness in humans: Critique and reformulation. *Journal of Abnormal Psychology, 87*(1), 49-74. https://doi.org/10.1037/0021-843X.87.1.49

Amat, J., Paul, E., Zarza, C., Watkins, L. R., & Maier, S. F. (2006). Previous experience with behavioral control over stress blocks the behavioral and dorsal raphe nucleus activating effects of later uncontrollable stress: Role of the ventral medial prefrontal cortex. *Journal of Neuroscience, 26*(51), 13264-13272. https://doi.org/10.1523/JNEUROSCI.3630-06.2006

Bandura, A. (1977). Self-efficacy: Toward a unifying theory of behavioral change. *Psychological Review, 84*(2), 191-215. https://doi.org/10.1037/0033-295X.84.2.191

Baratta, M. V., Seligman, M. E. P., & Maier, S. F. (2015). Behavioral control blunts reactions to contemporaneous and future adverse events: Medial prefrontal cortex plasticity and a corticostriatal network. *Neurobiology of Stress, 1*, 12-22. https://doi.org/10.1016/j.ynstr.2014.09.003

Huys, Q. J. M., & Dayan, P. (2009). A Bayesian formulation of behavioral control. *Cognition, 113*(3), 314-328. https://doi.org/10.1016/j.cognition.2009.01.008

Maier, S. F. (2001). Exposure to the stressor environment prevents the temporal dissipation of behavioral depression/learned helplessness. *Biological Psychiatry, 49*(9), 763-773. https://doi.org/10.1016/S0006-3223(00)01095-7

Maier, S. F., & Seligman, M. E. P. (1976). Learned helplessness: Theory and evidence. *Journal of Experimental Psychology: General, 105*(1), 3-46. https://doi.org/10.1037/0096-3445.105.1.3

Maier, S. F., & Seligman, M. E. P. (2016). Learned helplessness at fifty: Insights from neuroscience. *Psychological Review, 123*(4), 349-367. https://doi.org/10.1037/rev0000033

Seligman, M. E. P., Rosellini, R. A., & Kozak, M. J. (1975). Learned helplessness in the rat: Time course, immunization, and reversibility. *Journal of Comparative and Physiological Psychology, 88*(2), 542-547. https://doi.org/10.1037/h0076431

Tafet, G. E., & Ortiz Alonso, T. (2025). Learned helplessness and learned controllability: From neurobiology to cognitive, emotional and behavioral neurosciences. *Frontiers in Psychiatry, 16*, 1600165. https://doi.org/10.3389/fpsyt.2025.1600165

Wang, K. S., & Delgado, M. R. (2021). The protective effects of perceived control during repeated exposure to aversive stimuli. *Frontiers in Neuroscience, 15*, 625816. https://doi.org/10.3389/fnins.2021.625816
