# Digital Friction Simulation

本仓库包含一个基于 AgentSociety 的数字摩擦仿真实验代码，研究对象是老年人在使用手机 App 处理日常数字服务时，遇到数字摩擦后的任务尝试、失败反馈、求助、回避与习得性无助状态变化。

研究问题是一次受挫如何影响下一次尝试。本仓库保存模拟机制、实验入口、测试以及可核查的结果。

## 11 月 28 日最新结果

- **十人七天与个人用机习惯。** 上一轮整周模拟有 687 个没有到点待办的自由时段，最终只打开了 1 次日常 App。新的默认规则把本人的同钟点习惯直接用于用机概率，再让 LLM 根据眼前的处境提出调整。在另选的 16 个预留时段里，新版、旧版和个人同钟点多数基准分别猜对 8、6 和 12 个。新版已走过 32 个独立时段的需求、计划和执行，整周连续效果仍待验证。[两轮七天的结果、两批自由时段测试与逐小时表](report/2026结项/仓库发布/2026-11-28/seven-day-and-habits.md)
- **V7 连续模拟。** 十人各回放三天，再自主模拟两天。480 个人小时中，460 个形成有效计划（95.8%），9/10 人达到个人 95% 门槛。对齐设备留出记录后，91 个设备无活动且模拟有效的小时中，模拟仅 2 个小时也没有活动。模型能稳定给出计划，但仍倾向于过度使用手机。[连续运行与设备对照](docs/superpowers/plans/2026-11-28-continuous-app-audit.md)
- **V8 定向复测。** 在 V7 的存档状态上复问，两个频道或延期时点错误都用一次重答修好。收紧等待时段的提示后，对同一人物的三个时点分别重问，三次首答都选择不用手机。[V8 复测经过](docs/superpowers/plans/2026-11-28-continuous-app-audit.md#连续运行后的单点复测)
- **V6 帮助方式配对。** 十个合成人物昨天都在帮助下登录成功，只改变关键步骤由本人还是家人完成。今天 30 对正式比较中有 29 对选择同一种策略。指导组和代办组分别有 12/30、13/30 次选择自己试，10 对相同输入重复的行动全部一致。本次固定心理状态、单一任务的比较未显示稳定的指导优势。[研究设计与结果](docs/superpowers/plans/2026-11-28-help-mode-pairs.md)

[11 月 28 日进展与实验口径](report/2026结项/仓库发布/2026-11-28/progress.md) · [机器可读结果](report/2026结项/仓库发布/2026-11-28/progress.json)

## 11 月 27 至 28 日早期实验

| 实验 | 观察结果 |
|---|---|
| V3 昨日登录成败的配对比较 | 在同一个人物、第 5 天 09:00 的同一提醒下，10 对成败比较都选择立即登录。5 对的自报评分有差异，7 对的理由文字有差异。实验止于任务接入，后续独立操作或求助需要另行观察。 |
| V3 单人连续五天 | 前三天回放 App 活动，第 4、5 天逐小时决策。48 个小时里 35 个形成有效计划（72.9%）。13 个失败小时都出现任务与所选 App 渠道不匹配。 |
| V4 渠道修复 | 用同一个模型重问两种错误各自最早出现的场景，两条均在首答选对渠道。另对原 48 小时做离线回放。随后十人连续五天的结果见下文。 |
| V4 登录成败与次日状态，24 点 GLM 实测 | 10 对正式比较中，3 对从现在办理变为放弃这次非紧急提醒，另有 2 对仍决定现在办、但从自己试变为求助。两对相同输入重复的最终行动各自一致。单人、单时点，含重复共 62 次模型请求。 |

**11 月 28 日，十人五天连续实测。** 10 人均完成 72 小时回放。第 4、5 天的 480 个人小时全部有记录，其中 225 个产生可执行计划（46.9%），低于项目设定的 95%。255 个技术失败中有 254 个首答选择了日常 App 活动却没有列出任何 App。7 人在次日的有效计划输入中读到昨日经历。20 次求助送达中有 6 次借助帮助成功。[十人实验与结果口径](docs/superpowers/plans/2026-11-27-ten-residents-five-days.md)

**11 月 28 日，V5 日常 App 选择复测。** 现在模型可直接选“打开社交通讯 App”等动作，也可选择不用手机。用 `glm-4-flashx` 重问十人实验里的六个固定场景，四个原来失败的场景和两个对照都在首答选定了具体 App 类别。六个场景都在午夜，其中一个原先选择不用手机，这次选了数据中的“金融候选、待核实”类别。[逐人选择、回放与复现入口](docs/superpowers/plans/2026-11-28-daily-app-choice.md)

下列归档包含 V4 十人五天的分母及 V5 的六次复问。[V4、V5 实验说明](report/2026结项/仓库发布/2026-11-28/README.md) · [对应汇总数据](report/2026结项/仓库发布/2026-11-28/evidence.json) · [11 月 27 日的实验记录](report/2026结项/仓库发布/2026-11-27/README.md)

机会模式下，智能体每小时构建观察，调用规划模块，并把可执行的决定交给模拟器。[智能体执行入口](examples/digital_friction_mvp/proto/agent.py) · [小时规划](examples/digital_friction_mvp/proto/app_entry/planner.py) · [协议演变与测试记录](docs/superpowers/plans/2026-11-26-hourly-intention.md)

### 自由时段怎样决定用不用手机

在 `opportunity_v1` 整周运行中，没有到点可办的任务时，默认采用 `--free-hour-history hybrid`。例如一个人前三天下午三点都有 App 活动，模型也没看到今天有什么特别，模拟这一小时用手机的概率就是 87.5%。如果模型根据眼前的情况建议少用，概率降为 77.8%。抽到使用后，模型再选具体的 App 类别。有到点可办的任务时，人物按原有流程决定是否办理、延期或放弃。

这套算法从前三天同一钟点的活动次数估计基础概率。模型建议“照常”“比平时更想用”或“比平时更想放下”时，系统分别把用机赔率乘以 1、2 或 0.5。这些倍率是实验假设。缺少该钟点的记录时，由模型直接选择用或不用。旧实验可用 `--free-hour-history counts`（次数提示）或 `description`（中文描述提示）复现。[用机概率与抽样](examples/digital_friction_mvp/proto/app_entry/phone_policy.py) · [每小时的执行流程](examples/digital_friction_mvp/proto/app_entry/rollout.py)

用 `glm-4-flashx` 实测了同一批十人七天归档中的另外 32 个自由时段，逐时从作决定前的状态重新开始。新版实际打开 App 12 次，32 个小时中有 19 个与设备活动一致。单用前三天同钟点的多数情况预测可对上 21 个。旧版有 1 个技术失败，在两版均有结果的 31 个小时中，旧版对上 11 个，新版对上 18 个。新的预留组共 16 个小时，旧版、新版和个人习惯分别对上 6、8 和 12 个。新版能区分常用和少用的钟点，整周连续运行及模型建议的额外预测价值仍待检验。[选样、实测与评分入口](examples/digital_friction_mvp/run_habit_execution_probe.py)

本项目的 `DigitalHelplessnessAgent.forward()` 调用自定义需求与小时计划，给办理任务保存跨小时意图。原版 `SocietyAgent.forward()` 会先检查当前步骤的预计耗时与执行状态，再更新需要；没有当前计划时才生成新计划。两处代码可用来比较人物在自由时段和办事期间各自能记住什么。[本项目的智能体](examples/digital_friction_mvp/proto/agent.py) · [实际用机提示](examples/digital_friction_mvp/proto/app_entry/needs.py) · [原版市民的执行循环](packages/agentsociety/agentsociety/cityagent/societyagent.py) · [原版计划生成](packages/agentsociety/agentsociety/cityagent/blocks/plan_block.py)

## 昨天是谁完成登录，今天会怎么选？

在连续模拟中，老人实际决定向家人求助后，老人模型可以选择“请教我操作”“请替我操作”或“没指明帮法”。家人看到请求后独立回应。系统记录老人选择的帮助方式、家人的回应方式、实际代办程度、帮助是否送达和任务结果。次日遇到相关任务时，需求、计划和策略模型可以读取这段经历。五天报告按人物和日期汇总请求与回应。早期实验中的偏好列标为缺失。[求助偏好实现与检验](docs/superpowers/plans/2026-11-28-requested-support-style.md)

新实验在十个合成人物各自的前三天 App 活动背景上，给定第 4 天相同的两次独立失败和一次帮助成功。家人在两组都说明了步骤，只有最后操作的人不同：一组由老人输入验证码并确认，另一组由家人完成。第 5 天 09:00，各自面对一项同样可延期的新登录任务。当前心理数值、可获得的支持、策略规则权重和配对抽样值保持一致。模型可以独立办理、求助、推迟、放弃，或照常做其他事。[配对设计与验收口径](docs/superpowers/plans/2026-11-28-help-mode-pairs.md)

在项目 Python 环境中运行以下命令，会核对 20 份小时计划输入、对应的任务评价与策略提示，并将 80 个决策点的清单保存至 `agentsociety_data/runs/help_mode_pairs/`。默认使用本地十台参考设备各自的 72 小时活动。没有设备数据时可追加 `--synthetic-history` 使用合成活动走完整个准备流程。

```bash
python examples/digital_friction_mvp/run_help_mode_pairs.py
```

默认准备流程的真实模型请求数为零。需要正式测量时使用同一命令加 `--online`。80 个时点各有一次 Plan；每次接下任务再增加一次评价和一次策略判断，首轮为 80–240 次，请求总上限含格式修复为 480 次。探针测量首次选择及求助请求的本地接收，帮助实施、是否实际开始操作及任务成败均留作后续观测。[运行入口](examples/digital_friction_mvp/run_help_mode_pairs.py) · [按人物比较与重复噪声](examples/digital_friction_mvp/analysis_help_mode_pairs.py)

连续模拟的新版小时计划仅提供可理解的生活类别，保留“不用手机”，原设备的待核实、未映射等记录仍保留在历史统计中。需求判断改为直接填写当下需求。可用 `python examples/digital_friction_mvp/check_stratified_needs_plan.py <十人五天V4归档> --output-dir <新目录>` 离线核对昼夜、前三天同小时活跃程度和当前有无可办任务的场景。这项检查重放既有回答。后续 V7 连续运行的需求首答有效数为 473/480，7 个重答后均可用。[V7 连续运行结果](docs/superpowers/plans/2026-11-28-continuous-app-audit.md)

## V4 配对实验：昨天的成败会改变今天何时办理、是否求助吗？

同一个模拟人物在第 5 天 09:00 看到新的登录提醒。第一个情境沿用原提醒，第二个说明今天不查看不会影响权益，明天仍可查看。每个情境有 5 对昨日登录成败对照和 1 对相同输入重复，共 24 个决策点。各组沿用同一人物、前三天习惯、当天需求和配对抽样值。[实验设计](docs/superpowers/plans/2026-11-27-hourly-strategy-factorial.md)

默认的 `frozen` 对照固定当前心理和以往经验的汇总值，只改昨天的登录记录。`updated` 对照让同一人物在第 4 天 09:00 独自尝试登录，实验设定成功或失败，由仿真规则分别更新无助感、信任、回避倾向、情绪与登录经验。到第 5 天 09:00，两个分支各自带着更新后的状态面对同一新机会。这段受控实验在两个时点之间只计算情绪衰减，期间执行的其他小时计划和夜间反思均为零。两种模式分别回答“一条记忆本身是否有影响”和“一条经历连同它造成的状态变化是否有影响”。[状态计算与验收](docs/superpowers/plans/2026-11-27-login-feedback.md)

在项目 Python 环境运行以下离线命令。第一条使用本地第一台参考设备的前三天记录。没有私有数据时，第二条可用合成的 72 小时历史检查相同流程。程序会在 `agentsociety_data/runs/hourly_strategy_factorial/` 新建目录，保存四条实际提示、24 点清单、路由检查和运行源码。

```bash
python examples/digital_friction_mvp/run_hourly_strategy_factorial.py
python examples/digital_friction_mvp/run_hourly_strategy_factorial.py --synthetic-history
python examples/digital_friction_mvp/run_hourly_strategy_factorial.py --feedback-mode updated
```

对所需模式的命令追加 `--online` 即可用 `glm-4-flashx` 实测，密钥可在终端隐藏输入。更新版另存 `feedback_states.json`，可查两个分支的操作前状态、结果和次日状态。每点先做一次小时计划，接受后再做任务评价和策略判断。选择求助时，记录本地模拟帮助者是否实际收到协议请求，随后停止。首轮调用共 24 至 72 次，含格式修复的 HTTP 上限为 144 次，帮助送达及任务结果均留作未观测。

线上运行逐点写入 `decisions.jsonl` 并生成 `summary.json`。完整报告分别统计所有决策中的求助比例、已接入任务中的求助比例，还可对照模型原始评分、规则权重、融合权重和最终动作。每种场景的成败差异与相同输入重复的差异单列，服务中断、技术失败和规则回退有独立标记。[运行入口](examples/digital_friction_mvp/run_hourly_strategy_factorial.py) · [统计口径](examples/digital_friction_mvp/analysis_hourly_factorial.py)

### 谁决定现在办，谁决定怎么办

| 一次登录经历 | 程序与规则的职责 | LLM 的职责 |
|---|---|---|
| 前三天使用手机 | 根据参考 App 记录整理这个人物什么时间常用哪些 App | 第 4 天起把这些习惯作为决策参考，无需重新训练模型 |
| 第 5 天 09:00 出现登录机会 | 提供时间、人物、经历、当前状态、合法选项与服务说明，校验并执行选中的行动 | 直接选择现在办、推迟、放弃或进行日常活动。连续模拟还用 LLM 估计当下需求，这个配对实验固定需求以便比较 |
| 人物决定现在办 | 用无助感、登录经验、任务难度和可获得的支持计算三种做法各自的权重 | 先评价任务的难度和把握，再给自己试、求助再试、回避分别打分 |
| 最终选择做法 | 在本实验配置下，将归一化的模型评分按 70%、规则权重按 30% 合并，抽取一次行动。策略模型输出无效或信心不足时使用规则，并记录来源 | 一次打分最高的做法仍有可能没有被抽中 |

第 5 天的每个比较点都走这条决策路径；第 4 天的成败由实验者控制。规则设定了昨日成败如何影响次日状态，行为差异的方向和大小要由实验观察。[小时规划与任务接入](examples/digital_friction_mvp/proto/agent.py) · [模型评分融合](examples/digital_friction_mvp/proto/llm_psychology.py) · [策略抽样](examples/digital_friction_mvp/proto/attempt_strategy.py)

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
python examples/digital_friction_mvp/run_social_memory_week.py --scheduled-login --hourly-intention-mode opportunity_v1 --paired-environment-seed 101 --agents 10 --llm-concurrency 3 --check
python examples/digital_friction_mvp/run_social_memory_week.py --hourly-intention-mode opportunity_v1 --check
python examples/digital_friction_mvp/run_social_memory_week.py --hourly-intention-mode opportunity_v1 --history-shuffle-seed 101 --check
```

十人五天配置在同一个世界创建 10 位合成老人及 10 位各自绑定的家庭帮助者。每位老人使用一条独立设备轨迹回放 72 小时，后两天合计 48 个规划小时、两个定时登录机会。十人的年龄来自合成画像（63–75 岁）。十条参考轨迹中，两台设备的登记用户年满 60 岁。去掉 `--check` 启动线上运行。十人流程结束后会生成逐人报告。需要复算时，在仓库根目录运行 `python examples/digital_friction_mvp/analysis_five_day_cohort.py --run-dir <本次目录> --db agentsociety_data/sqlite.db`，可生成每个人的结果。[十人结果报告脚本](examples/digital_friction_mvp/analysis_five_day_cohort.py) · [实验与验收口径](docs/superpowers/plans/2026-11-27-ten-residents-five-days.md)

**先检查模型能否给出可执行的选择。** 在仓库根目录运行下列命令，会用第 1 台设备前三天的记录，准备两条第 5 天 09:00 的提示。一条提示写着昨天独立登录成功，另一条写着失败。两条都使用该配对实验固定的 V4 小时规划。仅准备材料时使用第一条。用智谱 `glm-4-flashx` 实测时使用第二条，按终端提示隐藏输入密钥。每条最多修复一次，两条合计最多 4 次 HTTP 请求。

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

V4 计数模式把“用公共服务 App 办理登录”列为一个完整选项。接受或继续目标时，该选项计一次打开。模型通过 `additional_apps` 填写同一小时的额外打开，仍可选择延期、放弃、日常使用或不用手机。要离线回放旧五天实验的全部 48 个规划小时，运行 `check_hourly_channel_replay.py` 并传入旧归档目录。要重问其中第 4 天 09:00 和 20:00 的真实场景，使用同目录的 `run_hourly_channel_smoke.py <旧归档目录> --online`。两条最多共发出 4 次 HTTP 请求。[实测与回放记录](docs/superpowers/plans/2026-11-26-hourly-intention.md#第-4-天两个渠道错误的定向复测)

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
