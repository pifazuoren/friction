# 2026 年 11 月模拟审计证据

这些结果来自一个设备回放案例及一个合成画像的重复判断。TalkingData 记录了真实设备的 App 活动，登录策略、帮助回应和任务结果来自模拟。各段的 `run_id` 标识对应本机归档，便于逐次核对。[机器可读汇总](evidence.json)

| 数据段 | 审计用途 |
|---|---|
| `natural_run` | 前三天回放 72 小时，后四天按自然入口运行。对比在 95 个共同有效小时预测到的主场景、无活动小时及曝光量。整段完成的数字任务为 0。 |
| `scheduled_run` | 第 4、5 天各安排一次登录机会，两个任务产生四次决策。第 5 天首次发给模型的提示含有第 4 天两个已执行的回合。任务、重试、求助送达和最终动作均已从数据库与真实请求记录核对。 |
| `previous_failed_scheduled_run` | 保留第 4 天帮助者回复格式校验导致的中断。后续完整五天案例是在新运行中产生的。 |
| `paired_experiment` | 三种提示格式各含 10 对成败对照和 3 对相同输入。每对用同一随机值抽取动作。在线结果保留当时实际使用的规则回退，另列用修复后的并列判定回放原始回复的结果。 |
| `reference_data`、`new_study_draft` | 记录参考设备的年龄口径及双组实验的准备状态。较宽的 59 台设备已按全周活跃程度预筛。双组研究只有离线设计，目前线上结果数为 0。 |

## 读数口径

- 主场景命中、曝光量平均绝对误差（MAE）和空闲小时召回共享同一组有效小时。活跃指当小时存在 App 暴露。固定猜“通讯”可作为主场景命中数的参照。
- `app_needs_parse` 中的标量是模型经过格式修复后被程序接受的值。分布中的计数为小时数。
- `denominators` 同时记录独立任务数、首次机会采取行动的任务数、最终尝试过的任务数和所有决策行。再次处理同一延期任务会增加决策行数。
- `exported_model_and_survey_fields` 是状态表中的两个实际导出字段。当前任务更新会把模型计算结果写回问卷字段，因此任务发生后两列数值相同不能独立验证心理轨迹。[更新代码](../../../../examples/digital_friction_mvp/proto/agent.py)
- 配对实验的权重是 0 到 1 的比例。`contrast` 是“昨天失败”减“昨天成功”的最终策略抽样权重平均差，乘以 100 可换算为百分点。同一画像的多次模型请求提供了重复观测。
- 本页中的运行标识可对应 `agentsociety_data/runs/` 下的私有实验归档。自然运行的评分取自 `scores/day*/hourly.csv`，定点运行取自请求轨迹、`scheduled_login_evidence.json` 和 SQLite 的状态、任务行，配对结果取自各轮 `summary.json`、决策行和离线回放验收。[七天验收](../../../../examples/digital_friction_mvp/check_social_memory_run.py) · [定点登录验收](../../../../examples/digital_friction_mvp/check_scheduled_login.py) · [配对统计](../../../../examples/digital_friction_mvp/analysis_strategy_memory_pairs.py)
