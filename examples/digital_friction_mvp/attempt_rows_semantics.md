# Attempt Rows vs. Daily Task Windows

## Why this note exists

During the Phase 3 `gated_lite` dry-run, a 2-world experiment produced:

```text
baseline_low_friction: 387 attempt rows
high_friction_low_assist: 475 attempt rows
total: 862 attempt rows
```

At first glance this looks surprising, because the scheduled digital task windows suggest:

```text
10 agents * 3 task windows/day * 10 days * 2 worlds = 600 scheduled new-task opportunities
```

The important distinction is:

```text
scheduled task window != attempt row
```

## Scheduled task windows

The prototype schedules up to three new digital task windows per agent per day:

```text
09:00
14:00
19:00
```

These windows are defined in `proto/task_assignment.py` as `_TASK_WINDOW_SECONDS`.
They control when a new digital task can be surfaced if the agent does not already
have an active assigned task.

## Attempt rows

`proto_attempt_rows` records actual task-handling episodes.

An attempt row is written whenever the agent processes an active digital task,
including:

```text
attempt_self
seek_help_then_attempt
avoid
```

Therefore, attempt rows count task-processing episodes, not only newly scheduled
tasks.

## Why attempt rows can exceed 3 per day

If the agent chooses `avoid_without_attempt`, the task can be carried over once:

```text
if outcome_type == "avoid_without_attempt" and defer_count < 1:
    defer_count += 1
    keep proto_assigned_task_json
```

This means the same scheduled task can generate more than one attempt row:

```text
09:00 new task appears
09:00 agent avoids it -> attempt row #1
later decision tick sees the unfinished task
later tick agent handles it again -> attempt row #2
```

So:

```text
scheduled new tasks <= 10 agents * 3 windows/day * days
attempt rows = scheduled new-task handling + carryover/retry handling
```

## Why high-friction worlds often have more rows

High-friction / low-assist worlds tend to create more avoid, abandon, and failure
events. Avoided tasks are more likely to carry over, so the number of attempt rows
can increase beyond the scheduled new-task count.

In the Phase 3 dry-run:

```text
baseline_low_friction exceeded 300 by 87 rows
high_friction_low_assist exceeded 300 by 175 rows
```

This is consistent with the high-friction world producing more unresolved task
handling episodes.

## Implication for Bayesian posterior updates

When we say:

```text
posterior update coverage = 862 / 862
payload coverage = 862 / 862
```

we mean:

```text
Every recorded task-processing episode had a bayesian_policy_lite payload.
Every recorded task-processing episode updated the observed-action posterior.
```

We do not mean:

```text
The system scheduled 862 new digital tasks.
```

## Recommended wording for papers and reports

Use:

```text
Each agent receives up to three newly surfaced digital tasks per day at scheduled
windows. Avoided tasks may carry over and generate additional subsequent attempt
records. We therefore distinguish scheduled new-task opportunities from recorded
task-handling episodes (`proto_attempt_rows`).
```

Avoid:

```text
Each agent has exactly three task events per day.
```

