# AgentSociety 风格 Action Choice 后续改造 Todo

## 背景

当前 digital friction MVP 为了研究 digital helplessness，把数字任务行动选择压缩成三选一：

```text
attempt_self
seek_help_then_attempt
avoid
```

这对 learned helplessness / controllability / Bayesian gated-lite2 建模很清楚，但和 AgentSociety 原生的 action choice 风格有差异。

AgentSociety 原生更像：

```text
need
-> plan target
-> detailed plan steps
-> dispatcher selects block
-> block executes action
-> memory / stream update
```

因此，在完成 `Bayesian gated-lite2` 后，可以考虑把 digital task action choice 逐步改造成更接近 AgentSociety 原生 block / plan / workflow 架构。

## 当前系统与 AgentSociety 原生差异

当前 digital friction MVP：

```text
task appears
-> task appraisal
-> strategy choice over attempt_self / seek_help_then_attempt / avoid
-> outcome
-> event appraisal / attribution / scope spillover
-> helplessness / memory update
```

AgentSociety 原生：

```text
NeedsBlock determines current need
-> PlanBlock selects guidance / plan target
-> LLM generates detailed steps
-> SocietyAgent executes current step
-> BlockDispatcher routes step to Mobility / Economy / Social / Other block
-> selected block executes
-> result and stream memory update
```

核心差异：

```text
当前系统是 task-level explicit action distribution；
AgentSociety 原生是 need-plan-step-block execution workflow。
```

## 后续方向总览

建议不要在 Bayesianlite2 完成前做大改。

推荐顺序：

```text
1. 先完成 Bayesian gated-lite2。
2. 跑完 shadow / conservative gated pilot / main experiment / ablation。
3. 稳定后，再考虑 AgentSociety 原生化 action choice。
```

原因：

```text
Bayesianlite2 解决“策略机制更可信”；
AgentSociety 原生化解决“simulation architecture 更自然”。
```

## Level 1: DigitalTaskBlock 轻量封装

目标：

```text
保留当前三选一机制，但把它包装成 AgentSociety block 风格。
```

新流程：

```text
SocietyAgent plan step:
  "complete online payment confirmation"

BlockDispatcher:
  routes to DigitalTaskBlock

DigitalTaskBlock:
  internally runs current digital friction mechanism
  uses Bayesian gated-lite2 to choose attempt/help/avoid
  returns success / evaluation / consumed_time / node_id
```

需要做：

```text
新增 DigitalTaskBlock
把当前 task appraisal / policy construction / outcome / update 封装到 block 内部
让 block 输出 SocietyAgentBlockOutput-compatible result
保留 proto_attempt_rows audit
保留现有 payload_json
```

优点：

```text
工程量较小
保留当前实验主机制
更贴近 AgentSociety block architecture
不需要立刻拆分数字任务步骤
```

风险：

```text
本质上仍然是 block 内部三选一；
只是架构上更像 AgentSociety，不是完全原生化。
```

适合时间点：

```text
Bayesian gated-lite2 main experiment 稳定后。
```

## Level 2: Digital Task Step-Level Plan

目标：

```text
把一个数字任务拆成多个可执行步骤，让 action choice 发生在 step 层面。
```

示例任务：

```text
online hospital registration
```

可能步骤：

```text
1. open hospital service page
2. login account
3. complete identity verification
4. search department information
5. choose appointment slot
6. confirm risk / payment / submission
```

可能 blocks：

```text
LoginVerificationBlock
FormFillingBlock
InformationSearchBlock
PaymentRiskBlock
SubmissionBlock
HelpSeekingBlock
AvoidanceBlock
```

Bayesian 学习对象从：

```text
P(outcome | task_family, action)
```

升级为：

```text
P(outcome | task_family, step_type, action)
```

其中 action 仍可包括：

```text
attempt_self
seek_help_then_attempt
pause_or_defer
switch_offline
avoid
```

优点：

```text
更像真实数字任务过程
更容易解释 helplessness 在哪一步形成
可以区分 login friction / form friction / payment risk friction
更适合做 fine-grained attribution 和 scope spillover
```

风险：

```text
工程量明显增加
状态空间变大
Bayesian posterior 数据更稀疏
需要更多 seeds / longer horizon
payload 和 analysis 会变复杂
```

适合时间点：

```text
Bayesian gated-lite2 已经有稳定论文级结果后；
或作为下一篇 / AAMAS 扩展。
```

## Level 3: Full AgentSociety-Style Digital Life Workflow

目标：

```text
把数字任务嵌入 agent 的日常 need-plan-step-block workflow，而不是作为独立外部任务事件。
```

可能流程：

```text
NeedsBlock:
  health service need / safety need / social support need

PlanBlock:
  generates digital service plan

DigitalServiceBlock:
  executes online task steps

HelpSeekingBlock:
  routes to family / volunteer / customer service / peer

Outcome / appraisal / attribution:
  update helplessness and controllability memory
```

可以引入多主体：

```text
older adult agent
family helper agent
community volunteer agent
customer service agent
peer learner agent
```

优点：

```text
最接近 AgentSociety 原生架构
更适合 AAMAS 的 multi-agent social simulation
可以研究支持生态如何影响 digital helplessness
可以模拟课程干预、社区支持、家庭帮助质量等双赢方案
```

风险：

```text
工程量最大
机制解释更复杂
需要多主体交互验证
需要更强实验设计和 qualitative validation
```

适合时间点：

```text
Bayesian gated-lite2 作为核心机制完成后；
如果目标转向 AAMAS 或下一阶段大型系统贡献。
```

## 与 Bayesian Gated-Lite2 的关系

Bayesian gated-lite2 仍然可以作为核心策略机制，只是嵌入位置不同。

当前 task-level 版本：

```text
task_family + action
-> Bayesian posterior
-> gated shift
-> sampled action
```

AgentSociety-style step-level 版本：

```text
task_family + step_type + action
-> Bayesian posterior
-> gated shift
-> sampled step action
```

也就是说：

```text
Bayesianlite2 是 action-outcome learning 核心；
AgentSociety 原生化是外层 workflow 架构升级。
```

二者不是互相替代。

## 推荐路线

短期不做：

```text
不要在 Phase 2 / Phase 3 之前重构成 full AgentSociety-style workflow。
不要同时改 Bayesian gated-lite2 和任务执行架构。
不要在当前论文主线还不稳定时引入多主体支持生态。
```

推荐顺序：

```text
1. 完成 Bayesianlite2 Phase 2 utility calibration。
2. 完成 conservative gated-lite pilot。
3. 完成 gated-lite main experiment 和消融。
4. 如果论文主线稳定，再做 Level 1 DigitalTaskBlock 封装。
5. 如果目标转向 AAMAS，再考虑 Level 2 step-level plan 或 Level 3 multi-agent support ecology。
```

一句话总结：

```text
先把 Bayesianlite2 做成可信策略机制；
再把它包装进 AgentSociety 原生 need-plan-step-block 架构。
```

