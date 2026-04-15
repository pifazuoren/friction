# `export_trigger_inputs_audit.py` 用法

## 作用

- 导出 `trigger_event_shocks` 审计所需的核心输入与判定字段。
- 同时附带对齐后的 `action/status` 快照（支持 `prev_snapshot` 或 `same_t`）。
- 适合后续做“输入→场景匹配→概率→发射结果”的全链路审计。

## 使用方法（推荐）

```bash
python examples/digital_friction_mvp/analysis/export_trigger_inputs_audit.py \
  dd589b8c-e4d3-45d8-a7f7-2901ebb6be4b \
  --join-mode prev_snapshot \
  --out-csv examples/digital_friction_mvp/analysis/attempt_trigger_inputs_dd589b8c.csv
```

## 参数说明

- `exp_id`：实验编号（必填）。
- `--join-mode`：
  - `prev_snapshot`（默认）：取同 agent 在 attempt 之前最近一条 status。
  - `same_t`：取同一 `(day,t)` 的 status（仅用于历史复盘）。
- `--out-csv`：输出文件路径。
- `--include-decision-json 0|1`：是否附带原始 `decision_json`（默认 `1`）。

## 输出重点字段

- 触发输入：`intention, need, step_type, step_intention, status_text, step_eval_text, step_outcome`
- 对齐快照：`aligned_action, aligned_agent_status_status, aligned_action_snapshot_day, aligned_action_snapshot_t, aligned_join_mode, aligned_join_lag_seconds`
- 匹配审计：`scenario, scenario_match_source, llm_match_status, llm_match_confidence, digital_gate_*`
- 概率与结果：`p_negative_interval, p_positive_interval, total_event_prob, hazard_p_total, emitted, outcome`
