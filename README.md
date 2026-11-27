# Digital Friction Simulation

本仓库包含一个基于 AgentSociety 的数字摩擦仿真实验代码，研究对象是老年人在使用手机 App 处理日常数字服务时，遇到数字摩擦后的任务尝试、失败反馈、求助、回避与习得性无助状态变化。

研究问题是一次受挫如何影响下一次尝试。本仓库保存模拟机制、实验入口、测试以及可核查的结果。

## 2026 年 11 月 27 日实验结果

| 实验 | 观察结果 |
|---|---|
| V3 昨日登录成败的配对比较 | 在同一个人物、第 5 天 09:00 的同一提醒下，10 对成败比较都选择立即登录。5 对的自报评分有差异，7 对的理由文字有差异。实验止于任务接入，后续独立操作或求助需要另行观察。 |
| V3 单人连续五天 | 前三天回放 App 活动，第 4、5 天逐小时决策。48 个小时里 35 个形成有效计划（72.9%）。13 个失败小时都出现任务与所选 App 渠道不匹配。 |
| V4 渠道修复 | 用同一个模型重问两种错误各自最早出现的场景，两条均在首答选对渠道。另对原 48 小时做离线回放。V4 连续五天的有效率仍待实测。 |

审阅时可以从[本期实验说明](report/2026结项/仓库发布/2026-11-27/README.md)和[机器可读结果](report/2026结项/仓库发布/2026-11-27/evidence.json)开始。机会模式的每小时决策从[智能体执行入口](examples/digital_friction_mvp/proto/agent.py)进入[规划模块](examples/digital_friction_mvp/proto/app_entry/planner.py)。[协议演变与测试记录](docs/superpowers/plans/2026-11-26-hourly-intention.md)

## 实验主线

实验流程可以概括为：

```text
app entry
-> app-context exposure
-> task occurrence gate
-> DigitalTask
-> strategy selection
-> family support
-> outcome realization
-> helplessness / trust / avoidance update
-> memory update
-> multi-world comparison
```

其中，TalkingData 风格的 App 使用记录只用于校准和验证可观测的 app-entry / app-context 行为。它不被视为 DigitalTask 是否真实发生的标签，也不直接验证 helplessness、trust 或 avoidance 等心理状态。

## 仓库包含内容

本仓库主要包含：

- 数字摩擦仿真实验代码
- app-entry / app-context 校准与验证相关逻辑
- task occurrence gate 与 DigitalTask 映射逻辑
- outcome realization 与 helplessness update 模块
- family support 相关模块
- multi-world / multi-seed 实验运行脚本
- 实验分析与回归测试脚本
- 本实验依赖的本地 AgentSociety runtime

## 实验与审计入口（2026 年 11 月 26 日）

| 实验 | 状态与可核查结果 |
|---|---|
| 自然运行，1 个模拟人物，7 天 | 前三天回放 72 小时。后四天有 95 个共同可评分小时，GLM 主场景命中 83 次，个人同小时历史基准命中 84 次。8 个无 App 活动小时全部被 GLM 预测为活跃。此次运行没有形成可用于核对次日策略的自然任务记录。 |
| 定时登录，1 个模拟人物，5 天 | 修复帮助者回复校验后重新运行。第 4 天首次回避，稍后求助，获得帮助后中途放弃。第 5 天的实际策略提示包含昨天的两条记录。共安排两项登录任务，产生四次决策。 |
| 昨日成败的配对实验 | 同一合成人物和任务进行了 10 对成败比较、3 对相同输入重复。隐藏评分示例和规则权重后，线上运行出现并列最高分被拒绝的问题。修复后用 26 个已保存的首次回答离线回放，10 对中仅 1 对原始评分不同，同一配对随机数下动作差异为 0/10。 |
| 登录难度双组实验草案 | 已实现准备和分析入口，拟比较第 4–6 天不同登录难度对第 7 天相同任务的影响。截至本次更新，仅完成离线准备和检查。 |

[可公开核对的运行摘要](report/2026结项/仓库发布/2026-11-26/) · [自然运行及定时登录入口](examples/digital_friction_mvp/run_social_memory_week.py) · [策略配对入口](examples/digital_friction_mvp/run_strategy_memory_pairs.py) · [双组草案入口](examples/digital_friction_mvp/run_login_difficulty_study.py)

审计时可以从三个直接影响研究解释的位置开始：

- 每次任务结束时，系统将模型无助感写入问卷指数，导致两个字段在日末导出时可能相等。[任务状态更新](examples/digital_friction_mvp/proto/agent.py) · [问卷派生值写入](examples/digital_friction_mvp/proto/state_schema.py)
- 阶段报表以决策行作分母，延期后处理同一个任务会产生额外一行。首次尝试率、最终尝试过的任务比例和按决策行的尝试率分别回答不同问题。[汇总计算](examples/digital_friction_mvp/proto/metrics.py)
- 模型策略评分经过规则融合与抽样后才转成动作。帮助者响应、支持送达和最终任务成败有单独的记录。[策略生成](examples/digital_friction_mvp/proto/llm_psychology.py) · [动作抽样](examples/digital_friction_mvp/proto/attempt_strategy.py) · [帮助协议](examples/digital_friction_mvp/proto/support_protocol.py)

公开材料提供源码、回归测试及去标识化汇总。复跑完整在线仿真还需要本地参考数据、地图、模拟器和智谱凭据。逐次模型请求及 SQLite 数据库存放于本地实验归档。

## 可跨小时延期的登录机会

默认模式为 `legacy`。选择 `opportunity_v1` 时，第 4 天起，老人会在原有 App 规划请求中看到已经出现的机会、自己的待办和过往经历。每人同一时间保留一项目标。只有接受或继续，才会进入操作策略、家庭帮助和结果模块。延期到点会重新选择；期间仍可使用其他 App。由本小时 App 活动发现的自然机会最早在下一小时可见。

从仓库根目录使用含项目依赖的 Python。以下命令分别生成配对材料、检查五天受控窗口、检查七天自然窗口和检查前三天的时段置乱对照，均可离线运行。

```bash
python examples/digital_friction_mvp/run_hourly_intention_pairs.py
python examples/digital_friction_mvp/run_social_memory_week.py --scheduled-login --hourly-intention-mode opportunity_v1 --paired-environment-seed 101 --check
python examples/digital_friction_mvp/run_social_memory_week.py --hourly-intention-mode opportunity_v1 --check
python examples/digital_friction_mvp/run_social_memory_week.py --hourly-intention-mode opportunity_v1 --history-shuffle-seed 101 --check
```

**先检查模型能否给出可执行的选择。** 在仓库根目录运行下列命令，会用第 1 台设备前三天的记录，准备两条第 5 天 09:00 的提示。一条提示写着昨天独立登录成功，另一条写着失败。两条都使用新版小时规划。仅准备材料时使用第一条。用智谱 `glm-4-flashx` 实测时使用第二条，按终端提示隐藏输入密钥。每条最多修复一次，两条合计最多 4 次 HTTP 请求。

```bash
python examples/digital_friction_mvp/run_hourly_intention_pairs.py --smoke
python examples/digital_friction_mvp/run_hourly_intention_pairs.py --smoke --online
```

结果保存在 `agentsociety_data/runs/hourly_intention_smoke/` 的独立目录。`summary.json` 报告首答有效数、修复数和最终采纳数。`decisions.jsonl` 记录模型的动作以及任务是否进入执行入口。两条观测只用于检查回答格式和执行条件。

公开仓库也支持用合成历史查看模型将收到的两条提示。在安装了项目依赖的环境中运行以下命令即可生成材料，模型请求数为 0。

```bash
python examples/digital_friction_mvp/run_hourly_intention_pairs.py --smoke --synthetic-history
```

新版将延期目标和复查时点合成一次选择。例如，选择“把这次登录推迟到明天 09:00”会同时保存目标和时点。只说“再等等”会触发一次格式修复。模型仍未选定时点时，该小时记为技术失败。在此期间的通讯等日常活动由模型另外给出。

计数模式现在把“用公共服务 App 办理登录”列为一个完整选项。接受或继续目标时，该选项计一次打开。模型通过 `additional_apps` 填写同一小时的额外打开，仍可选择延期、放弃、日常使用或不用手机。要离线回放旧五天实验的全部 48 个规划小时，运行 `check_hourly_channel_replay.py` 并传入旧归档目录。要重问其中第 4 天 09:00 和 20:00 的真实场景，使用同目录的 `run_hourly_channel_smoke.py <旧归档目录> --online`。两条最多共发出 4 次 HTTP 请求。[实测与回放记录](docs/superpowers/plans/2026-11-26-hourly-intention.md#第-4-天两个渠道错误的定向复测)

**正式配对实验。** 使用 `run_hourly_intention_pairs.py --online` 会运行 A 和 B 各 10 对昨日成败、3 对相同输入，合计 52 次首轮 Plan 请求。规则参照 C 在本地运行。配对实验观察是否接受、是否延期及任务是否进入执行入口。五天连续工作流另外记录实际发生的策略、求助送达与结果。运行五天或七天的线上工作流时去掉对应命令的 `--check`，A 组选 `--hourly-intention-mode legacy`。受控窗口与自然窗口各自评分。

比较“昨天成功”和“昨天失败”时，应在同一个版本内比较实际行动，再用相同输入的重复结果估计模型波动。比较 A 与 B 时，小时任务接入方式、历史频次的呈现方式和模型的回答格式都发生了变化。

[意图改造实施与离线验收记录](docs/superpowers/plans/2026-11-26-hourly-intention.md) · [配对实验入口](examples/digital_friction_mvp/run_hourly_intention_pairs.py) · [运行验收](examples/digital_friction_mvp/check_hourly_intention_run.py)

## 历史实验（截至 2026 年 11 月 25 日）

| 实验 | 已完成的运行 | 证据范围 |
|---|---|---|
| 四环境机制对照 | 五月版本使用 10 个模拟人物、7 天、种子 101；四个场景均完成 | 高摩擦时，低辅助成功 28/270 回合，高辅助成功 34/261 回合。辅助同时改变无障碍和人力支持等参数。 |
| 应用入口回放与生成 | 代码支持第 1–3 天回放真实记录，第 3 天末保存状态，第 4–7 天按小时调用 LLM | 当时归档的智谱在线运行覆盖 1 台设备的第 4 天，有效输出 23/24 小时；19 时生成失败。 |
| 第 4 天强度校准 | 固定上述 23 小时已有的 LLM 决策，重算应用活动量 | 计数平均绝对误差从 2.13 降到 1.35，主要场景命中从 21/23 降到 17/23。个人历史基准为 1.13、23/23。这次重算新增模型请求为 0。 |
| 历史规则比较 | 同一数据来源的 59 台设备，后四天合计 5,664 个设备小时 | 汇总表列出各组的活动量预测误差。59 台中有 6 台对应 60 岁及以上用户；四天的统计以设备日志为依据。 |

[四环境结果](report/2026结项/仓库发布/simulation_worlds_20260528.csv) · [第 4 天同小时对照](report/2026结项/仓库发布/entry_day4_comparison.csv) · [第 4–7 天历史基准](report/2026结项/仓库发布/entry_days4_7_history_benchmarks.csv)

## 目录结构

```text
examples/digital_friction_mvp/
  main.py                         单次实验入口
  world_runner.py                 多 world / 多 seed 实验运行器
  config_runtime.py               运行时配置
  proto/                          核心仿真模块
  mobile_intention_artifacts/     app-entry 校准相关 artifact
  tests/                          单元测试与回归测试

packages/agentsociety/
  本实验使用的 AgentSociety 本地运行时依赖
```

核心实验代码主要位于：

```text
examples/digital_friction_mvp/proto/
```

其中：

```text
app_entry/        app-context 候选、task occurrence gate、entry audit
task_flow/        outcome 相关入口
psychology/       helplessness update 相关入口
support/          family support 相关入口
memory/           LLM memory packet 构造
```

## 数据说明

仓库中包含的是由 App 使用记录处理得到的校准 artifact，而不是原始数据。

reference artifact 用于运行时校准；held-out validation artifact 仅用于验证和分析，不应作为运行时 prior 使用。

这一设计对应实验口径：

```text
TalkingData 校准的是手机使用场景；
DigitalTask 是否发生由 task occurrence gate 和仿真机制决定；
心理状态变化由实验模型更新，不由 TalkingData 直接标注。
```

## LLM 配置

数字摩擦实验通过本机环境变量读取智谱凭据。

示例：

```bash
export LLM_API_KEY=...
# 或
export ZHIPUAI_API_KEY=...
export LLM_MODEL=glm-4-flashx
```

如果只运行 rule-based 测试，可以不配置 LLM key。涉及 survey、LLM rerank、LLM appraisal、reflection 或 family helper LLM 的实验需要可用的 LLM API。

## 基础测试

可以先运行核心回归测试：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_task_assignment.py \
  examples/digital_friction_mvp/tests/test_outcome_model.py \
  examples/digital_friction_mvp/tests/test_state_update.py \
  examples/digital_friction_mvp/tests/test_runtime.py \
  -q
```

也可以运行 app-entry 与 wrapper 兼容性测试：

```bash
python -m pytest \
  examples/digital_friction_mvp/tests/test_app_entry_import_compat.py \
  examples/digital_friction_mvp/tests/test_refactor_round2_import_compat.py \
  -q
```

## 使用个人设备数据复跑

从仓库根目录运行。单元测试可使用合成样例。实测回放和评分需要本地取得的 TalkingData 数据及相应设备名单。原始日志、逐设备实验输出、地图和 SQLite 数据库保存在实验机器。公开此处的汇总结果即可核对本文列出的数值。

1. 安装本仓库使用的 AgentSociety 运行环境。完整世界仿真需要本地模拟器和北京地图，资源目录默认为 `agentsociety_data/`。
2. 用 `scripts/clean_talkingdata_elderly_59.py` 清洗本地记录，再用 `scripts/build_talkingdata_elderly_10_artifact.py --help` 查看参考期、评分期数据包及设备名单的构建参数。默认回放目录为 `agentsociety_data/elderly/10person_v3/`。其中 `*_reference_hourly_bundle_day1_3.csv` 与 `*_selected_devices.csv` 用于运行，`*_validation_hourly_bundle_day4_7.csv` 仅用于事后评分。
3. `python examples/digital_friction_mvp/run_entry_calibration_day4.py --agents 1 --prompt-key` 在相同种子下分别运行原版和校准版。此入口覆盖前三日回放和第 4 日自主生成。观察完整第 4–7 天时，使用通用 `world_runner.py`，设置 `PROTO_TASK_ENTRY_MODE=app_context_replay_then_llm_rollout`、`STAGE_MODE=single`、`STAGE_DAYS=7`，并使用每 60 分钟一步的配置。
4. 如需复算八月同一台设备的历史数值，`replay_recorded_entry_intensity.py` 还需要该次私有运行的逐小时输出和失败记录。仅阅读此次发布的对照结果可直接打开上方 CSV。
