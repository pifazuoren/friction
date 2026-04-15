# Digital Helplessness Prototype Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current monolithic `digital_friction_mvp` event pipeline with a code-implementation-oriented `digital_helplessness_proto` centered on explicit task assignment, attempt strategy, outcome generation, state update, and metrics, while keeping AgentSociety as the simulation shell.

**Architecture:** Keep `AgentSociety` and `SocietyAgent` as the runtime substrate, but move prototype logic into a dedicated `examples/digital_friction_mvp/proto/` package. Implement a new agent subclass that overrides `forward()` with a short experimental loop: `task assignment -> attempt strategy -> outcome -> state update -> metrics/logging`. Preserve backward-compatible status fields and export tables so analysis scripts and workflow steps continue to work during migration.

**Tech Stack:** Python 3.11, AgentSociety, asyncio, SQLite, standard library `unittest`, existing `surveys.py`, `world_runner.py`, `export_results.py`, and analysis scripts under `examples/digital_friction_mvp/analysis`.

---

## Scope and Decision

This plan intentionally does **not** start with a package-wide rewrite of `packages/agentsociety/agentsociety/cityagent`.

Recommended route:

- Keep core AgentSociety package unchanged unless a hard blocker appears.
- Refactor only the example layer first.
- Introduce a new prototype agent and helper modules under `examples/digital_friction_mvp/proto/`.
- Keep legacy functions in place behind a feature flag until the new prototype reproduces baseline outputs.

Why this is the right scope:

- The current research question is not “general city life simulation”; it is “how digital helplessness forms under controlled digital-task conditions”.
- The current experimental code already lives mostly in `examples/digital_friction_mvp/main.py`, not in reusable package modules.
- Rewriting the base package first would increase risk, break other examples, and delay the research result.

Out of scope for this plan:

- General-purpose replacement of `PlanBlock`/`NeedsBlock` for all AgentSociety users
- Distributed execution redesign
- New frontend/UI
- Model fine-tuning or PPO/SFT loops

---

## File Structure

### Existing Files to Keep and Reuse

- Keep: `examples/digital_friction_mvp/surveys.py`
  - Survey definition for helplessness/trust/withdrawal measurements.
- Keep: `examples/digital_friction_mvp/world_runner.py`
  - Parallel-world orchestration.
- Keep: `examples/digital_friction_mvp/export_results.py`
  - Export bridge from SQLite to analysis-friendly tables.
- Keep: `examples/digital_friction_mvp/plot_results.py`
  - Downstream plotting layer.
- Keep for compatibility during migration: `examples/digital_friction_mvp/signal_extraction.py`
  - Explanation summaries can continue to use it if useful.
- Keep for compatibility during migration: `examples/digital_friction_mvp/persistence.py`
  - Stage explanation SQLite/CSV helpers.

### Existing Files to Shrink

- Modify: `examples/digital_friction_mvp/main.py`
  - Reduce from monolithic logic host into configuration/wiring entrypoint.
  - Keep workflow assembly and runtime metadata output.
  - Remove or gate legacy in-file probability/matching/update logic once replacement modules exist.

### New Prototype Package

- Create: `examples/digital_friction_mvp/proto/__init__.py`
  - Public exports for the new prototype modules.
- Create: `examples/digital_friction_mvp/proto/models.py`
  - Shared dataclasses / typed dictionaries for task, attempt, outcome, state delta, metrics row.
- Create: `examples/digital_friction_mvp/proto/task_assignment.py`
  - Explicit task queue management and interval-level task assignment.
- Create: `examples/digital_friction_mvp/proto/attempt_strategy.py`
  - Decide how the agent approaches the current digital task.
- Create: `examples/digital_friction_mvp/proto/outcome_model.py`
  - Rule-based or calibrated outcome generation from task + friction + support + state.
- Create: `examples/digital_friction_mvp/proto/state_update.py`
  - Apply negative/positive outcome deltas to helplessness/trust/avoidance/self-efficacy.
- Create: `examples/digital_friction_mvp/proto/metrics.py`
  - Structured event log rows, attempt rows, aggregated counters, compatibility shaping.
- Create: `examples/digital_friction_mvp/proto/agent.py`
  - `DigitalHelplessnessAgent` with new `forward()` orchestrator.
- Create: `examples/digital_friction_mvp/proto/workflow.py`
  - Thin wrappers for init/status sync/stage settlement functions used by `WorkflowStepConfig`.
- Create: `examples/digital_friction_mvp/proto/compat.py`
  - Map new proto outputs back to existing field names used by exports and plots.

### New Tests

- Create: `examples/digital_friction_mvp/tests/__init__.py`
- Create: `examples/digital_friction_mvp/tests/test_task_assignment.py`
- Create: `examples/digital_friction_mvp/tests/test_attempt_strategy.py`
- Create: `examples/digital_friction_mvp/tests/test_outcome_model.py`
- Create: `examples/digital_friction_mvp/tests/test_state_update.py`
- Create: `examples/digital_friction_mvp/tests/test_metrics.py`
- Create: `examples/digital_friction_mvp/tests/test_agent_forward_contract.py`

---

## Target Runtime Contract

The new prototype loop must be:

1. Load current digital-task queue and current state.
2. Explicitly assign at most one digital task for this interval.
3. Choose attempt strategy.
4. Generate outcome.
5. Apply state update.
6. Persist metrics/log rows.
7. Update backward-compatible status fields.

The following status keys must remain available after migration:

- `helplessness`
- `trust`
- `avoidance`
- `status_summary`
- `event_log`
- `friction_step_signal`
- `current_plan`
- `current_need`
- `digital_task_hint`
- `digital_task_hint_pending`

The following research-facing outputs must remain analyzable:

- per-attempt row
- per-event row
- per-agent status trajectory
- stage settlement summary
- survey-derived helplessness/trust indices

---

## Chunk 1: Freeze Contracts and Extract Pure Engines

### Task 1: Add Test Scaffold and Freeze the Current Data Contract

**Files:**
- Create: `examples/digital_friction_mvp/tests/__init__.py`
- Create: `examples/digital_friction_mvp/tests/test_metrics.py`
- Modify: `examples/digital_friction_mvp/main.py`

- [ ] **Step 1: Write the failing contract test for required event/status keys**

```python
import unittest

REQUIRED_STATUS_KEYS = {
    "helplessness",
    "trust",
    "avoidance",
    "event_log",
}


class TestMetricsContract(unittest.TestCase):
    def test_required_status_keys_exist_in_initial_status_payload(self):
        from examples.digital_friction_mvp.main import _build_initial_status_payload

        payload = _build_initial_status_payload(
            profile={"digital_experience": 0.5, "past_fraud": 0.0, "vision_limit": 0.0}
        )
        self.assertTrue(REQUIRED_STATUS_KEYS.issubset(payload.keys()))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_metrics -v`
Expected: FAIL because `_build_initial_status_payload` does not exist yet.

- [ ] **Step 3: Add a minimal compatibility builder in `main.py`**

```python
def _build_initial_status_payload(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "helplessness": 0.0,
        "trust": 0.0,
        "avoidance": 0.0,
        "event_log": [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_metrics -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/tests/__init__.py \
        examples/digital_friction_mvp/tests/test_metrics.py \
        examples/digital_friction_mvp/main.py
git commit -m "test: freeze digital helplessness status contract"
```

### Task 2: Introduce Shared Proto Models

**Files:**
- Create: `examples/digital_friction_mvp/proto/__init__.py`
- Create: `examples/digital_friction_mvp/proto/models.py`
- Test: `examples/digital_friction_mvp/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests for task/outcome/state dataclasses**

```python
import unittest


class TestProtoModels(unittest.TestCase):
    def test_attempt_outcome_has_expected_fields(self):
        from examples.digital_friction_mvp.proto.models import AttemptOutcome

        outcome = AttemptOutcome(
            outcome="negative",
            task_id="t1",
            success=False,
            frustration_score=0.8,
            delta_helplessness=4.0,
            delta_trust=-3.0,
            delta_avoidance=2.0,
            explanation="verification failed twice",
        )
        self.assertEqual(outcome.outcome, "negative")
        self.assertFalse(outcome.success)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_metrics -v`
Expected: FAIL with import error for `proto.models`.

- [ ] **Step 3: Create `proto/models.py` with minimal data structures**

```python
from dataclasses import dataclass, field


@dataclass
class DigitalTask:
    task_id: str
    task_type: str
    friction_type: str
    difficulty: float
    urgency: float
    assigned_at_tick: int


@dataclass
class AttemptStrategy:
    strategy_name: str
    will_attempt: bool
    will_seek_help: bool
    expected_effort: float
    rationale: str


@dataclass
class AttemptOutcome:
    outcome: str
    task_id: str
    success: bool
    frustration_score: float
    delta_helplessness: float
    delta_trust: float
    delta_avoidance: float
    explanation: str
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_metrics -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/proto/__init__.py \
        examples/digital_friction_mvp/proto/models.py \
        examples/digital_friction_mvp/tests/test_metrics.py
git commit -m "feat: add digital helplessness proto models"
```

### Task 3: Extract Explicit Task Assignment Engine

**Files:**
- Create: `examples/digital_friction_mvp/proto/task_assignment.py`
- Test: `examples/digital_friction_mvp/tests/test_task_assignment.py`

- [ ] **Step 1: Write failing tests for queue/assignment behavior**

```python
import unittest


class TestTaskAssignment(unittest.TestCase):
    def test_assigns_one_task_when_queue_has_pending_items(self):
        from examples.digital_friction_mvp.proto.models import DigitalTask
        from examples.digital_friction_mvp.proto.task_assignment import assign_current_task

        queue = [
            DigitalTask("t1", "payment", "verification", 0.7, 0.9, 100),
            DigitalTask("t2", "appointment", "navigation", 0.4, 0.3, 100),
        ]
        task = assign_current_task(queue=queue, current_tick=120, state={"avoidance": 10.0})
        self.assertIsNotNone(task)
        self.assertEqual(task.task_id, "t1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_task_assignment -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Implement assignment logic**

```python
def assign_current_task(*, queue, current_tick, state):
    pending = sorted(queue, key=lambda item: (-item.urgency, item.assigned_at_tick))
    if not pending:
        return None
    avoidance = float(state.get("avoidance", 0.0) or 0.0)
    if avoidance >= 85.0 and pending[0].urgency < 0.8:
        return None
    return pending[0]
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_task_assignment -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/proto/task_assignment.py \
        examples/digital_friction_mvp/tests/test_task_assignment.py
git commit -m "feat: add explicit digital task assignment engine"
```

### Task 4: Extract Attempt Strategy Policy

**Files:**
- Create: `examples/digital_friction_mvp/proto/attempt_strategy.py`
- Test: `examples/digital_friction_mvp/tests/test_attempt_strategy.py`

- [ ] **Step 1: Write failing tests for strategy selection**

```python
import unittest


class TestAttemptStrategy(unittest.TestCase):
    def test_high_helplessness_prefers_help_or_avoidance(self):
        from examples.digital_friction_mvp.proto.attempt_strategy import choose_attempt_strategy

        strategy = choose_attempt_strategy(
            task={"task_type": "payment", "friction_type": "verification", "difficulty": 0.8},
            state={"helplessness": 80.0, "trust": 35.0, "avoidance": 60.0},
            env={"assist_level": 3, "human_support_level": 2},
        )
        self.assertIn(strategy.strategy_name, {"seek_help", "avoid"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_attempt_strategy -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Implement minimal strategy chooser**

```python
from .models import AttemptStrategy


def choose_attempt_strategy(*, task, state, env):
    helplessness = float(state.get("helplessness", 0.0) or 0.0)
    assist = float(env.get("assist_level", 0.0) or 0.0) + float(env.get("human_support_level", 0.0) or 0.0)
    if helplessness >= 75.0 and assist >= 3.0:
        return AttemptStrategy("seek_help", True, True, 0.6, "high helplessness with support available")
    if helplessness >= 85.0 and assist < 3.0:
        return AttemptStrategy("avoid", False, False, 0.1, "high helplessness and low support")
    return AttemptStrategy("self_try", True, False, 0.8, "default self-attempt")
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_attempt_strategy -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/proto/attempt_strategy.py \
        examples/digital_friction_mvp/tests/test_attempt_strategy.py
git commit -m "feat: add attempt strategy policy"
```

### Task 5: Extract Outcome Model

**Files:**
- Create: `examples/digital_friction_mvp/proto/outcome_model.py`
- Test: `examples/digital_friction_mvp/tests/test_outcome_model.py`

- [ ] **Step 1: Write failing tests for outcome generation**

```python
import unittest


class TestOutcomeModel(unittest.TestCase):
    def test_negative_outcome_increases_helplessness(self):
        from examples.digital_friction_mvp.proto.outcome_model import generate_attempt_outcome

        outcome = generate_attempt_outcome(
            task={"task_id": "t1", "difficulty": 0.9, "friction_type": "verification"},
            strategy={"strategy_name": "self_try", "will_attempt": True, "will_seek_help": False},
            state={"helplessness": 70.0, "trust": 40.0, "avoidance": 50.0},
            env={"friction_level": 3, "assist_level": 0, "human_support_level": 0},
            rng_seed=123,
        )
        self.assertIn(outcome.outcome, {"negative", "positive", "none"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_outcome_model -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Implement outcome generator**

```python
from random import Random
from .models import AttemptOutcome


def generate_attempt_outcome(*, task, strategy, state, env, rng_seed):
    rng = Random(rng_seed)
    if not strategy["will_attempt"]:
        return AttemptOutcome("none", task["task_id"], False, 0.1, 0.5, -0.2, 1.2, "agent avoided the task")
    risk = 0.25 + 0.25 * float(task.get("difficulty", 0.0)) + 0.10 * float(env.get("friction_level", 0.0))
    support = 0.08 * float(env.get("assist_level", 0.0)) + 0.08 * float(env.get("human_support_level", 0.0))
    success = rng.random() > max(0.05, min(0.95, risk - support))
    if success:
        return AttemptOutcome("positive", task["task_id"], True, 0.2, -3.0, 4.0, -2.0, "task completed")
    return AttemptOutcome("negative", task["task_id"], False, 0.8, 4.0, -4.5, 3.0, "task failed under friction")
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_outcome_model -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/proto/outcome_model.py \
        examples/digital_friction_mvp/tests/test_outcome_model.py
git commit -m "feat: add outcome model for digital helplessness attempts"
```

### Task 6: Extract State Update Engine

**Files:**
- Create: `examples/digital_friction_mvp/proto/state_update.py`
- Test: `examples/digital_friction_mvp/tests/test_state_update.py`

- [ ] **Step 1: Write failing tests for state transitions**

```python
import unittest


class TestStateUpdate(unittest.TestCase):
    def test_negative_outcome_updates_core_state(self):
        from examples.digital_friction_mvp.proto.models import AttemptOutcome
        from examples.digital_friction_mvp.proto.state_update import apply_state_update

        state = {"helplessness": 50.0, "trust": 60.0, "avoidance": 20.0}
        outcome = AttemptOutcome("negative", "t1", False, 0.8, 4.0, -4.5, 3.0, "failed")
        updated = apply_state_update(state=state, outcome=outcome)
        self.assertGreater(updated["helplessness"], 50.0)
        self.assertLess(updated["trust"], 60.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_state_update -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Implement state update**

```python
def _clamp(value, lower=0.0, upper=100.0):
    return max(lower, min(upper, float(value)))


def apply_state_update(*, state, outcome):
    updated = dict(state)
    updated["helplessness"] = _clamp(updated.get("helplessness", 0.0) + outcome.delta_helplessness)
    updated["trust"] = _clamp(updated.get("trust", 0.0) + outcome.delta_trust)
    updated["avoidance"] = _clamp(updated.get("avoidance", 0.0) + outcome.delta_avoidance)
    return updated
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_state_update -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/proto/state_update.py \
        examples/digital_friction_mvp/tests/test_state_update.py
git commit -m "feat: add digital helplessness state update engine"
```

## Chunk 2: Replace the Runtime Orchestrator

### Task 7: Build Metrics and Compatibility Layer

**Files:**
- Create: `examples/digital_friction_mvp/proto/metrics.py`
- Create: `examples/digital_friction_mvp/proto/compat.py`
- Test: `examples/digital_friction_mvp/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests for event row shape**

```python
import unittest


class TestEventRowShape(unittest.TestCase):
    def test_metrics_row_contains_analysis_fields(self):
        from examples.digital_friction_mvp.proto.metrics import build_attempt_row

        row = build_attempt_row(
            agent_id=1,
            day=1,
            tick=3600,
            stage_name="shock",
            task={"task_id": "t1", "task_type": "payment", "friction_type": "verification"},
            strategy={"strategy_name": "self_try"},
            outcome={"outcome": "negative", "success": False, "explanation": "captcha failed"},
            state_before={"helplessness": 45.0, "trust": 60.0, "avoidance": 20.0},
            state_after={"helplessness": 49.0, "trust": 55.5, "avoidance": 23.0},
        )
        self.assertEqual(row["task_type"], "payment")
        self.assertIn("helplessness_after", row)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_metrics -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Implement metrics row builders and legacy-key compatibility helpers**

```python
def build_attempt_row(...):
    return {
        "agent_id": agent_id,
        "day": day,
        "tick": tick,
        "stage_name": stage_name,
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "friction_type": task["friction_type"],
        "strategy_name": strategy["strategy_name"],
        "outcome": outcome["outcome"],
        "success": outcome["success"],
        "explanation": outcome["explanation"],
        "helplessness_before": state_before["helplessness"],
        "helplessness_after": state_after["helplessness"],
        "trust_before": state_before["trust"],
        "trust_after": state_after["trust"],
        "avoidance_before": state_before["avoidance"],
        "avoidance_after": state_after["avoidance"],
    }
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_metrics -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/proto/metrics.py \
        examples/digital_friction_mvp/proto/compat.py \
        examples/digital_friction_mvp/tests/test_metrics.py
git commit -m "feat: add proto metrics and compatibility helpers"
```

### Task 8: Implement `DigitalHelplessnessAgent.forward()`

**Files:**
- Create: `examples/digital_friction_mvp/proto/agent.py`
- Modify: `examples/digital_friction_mvp/main.py`
- Test: `examples/digital_friction_mvp/tests/test_agent_forward_contract.py`

- [ ] **Step 1: Write failing forward-contract test**

```python
import unittest


class TestAgentForwardContract(unittest.TestCase):
    def test_forward_orchestrator_method_exists(self):
        from examples.digital_friction_mvp.proto.agent import DigitalHelplessnessAgent

        self.assertTrue(hasattr(DigitalHelplessnessAgent, "forward"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_agent_forward_contract -v`
Expected: FAIL with import error.

- [ ] **Step 3: Implement a new agent subclass**

```python
class DigitalHelplessnessAgent(SocietyAgent):
    async def forward(self):
        await self.reflect_to_environment()
        state_before = await load_proto_state(self)
        task = await assign_proto_task(self)
        strategy = choose_proto_strategy(task=task, state=state_before, env=await load_proto_env(self))
        outcome = generate_proto_outcome(task=task, strategy=strategy, state=state_before, env=await load_proto_env(self), rng_seed=self.id + self.step_count)
        state_after = apply_proto_state_update(state=state_before, outcome=outcome)
        await persist_proto_outputs(self, task=task, strategy=strategy, outcome=outcome, state_before=state_before, state_after=state_after)
        return 0.0
```

- [ ] **Step 4: Wire the new agent into `main.py` behind a feature flag**

Use an env flag like:

```python
PROTO_ENGINE = os.getenv("DIGITAL_PROTO_ENGINE", "legacy").strip().lower()
AGENT_CLASS = DigitalHelplessnessAgent if PROTO_ENGINE == "proto" else DigitalFrictionAgent
```

- [ ] **Step 5: Run tests**

Run: `python -m unittest examples.digital_friction_mvp.tests.test_agent_forward_contract -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add examples/digital_friction_mvp/proto/agent.py \
        examples/digital_friction_mvp/main.py \
        examples/digital_friction_mvp/tests/test_agent_forward_contract.py
git commit -m "feat: add forward-driven digital helplessness agent"
```

### Task 9: Move Workflow Functions Out of `main.py`

**Files:**
- Create: `examples/digital_friction_mvp/proto/workflow.py`
- Modify: `examples/digital_friction_mvp/main.py`
- Test: `examples/digital_friction_mvp/tests/test_metrics.py`

- [ ] **Step 1: Extract workflow-facing functions with stable names**

Required exported functions:

```python
async def init_proto_status(simulation): ...
async def sync_proto_survey_feedback(simulation): ...
async def log_proto_status(simulation): ...
async def stage_proto_settlement(simulation): ...
```

- [ ] **Step 2: Replace direct references in `main.py` workflow assembly**

Replace:

- `init_status`
- `sync_survey_feedback`
- `log_step_status`
- `stage_settlement`
- `trigger_event_shocks`

With proto-aware wrappers when `DIGITAL_PROTO_ENGINE=proto`.

- [ ] **Step 3: Delete `trigger_event_shocks` from the critical path for proto mode**

Proto mode must not rely on post-`STEP` shock injection for state changes.  
The state update must happen inside `DigitalHelplessnessAgent.forward()`.

- [ ] **Step 4: Run smoke test**

Run: `python examples/digital_friction_mvp/main.py`
Expected: process starts, builds workflow, and reaches simulation init without import errors.

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/proto/workflow.py \
        examples/digital_friction_mvp/main.py
git commit -m "refactor: move proto workflow hooks out of monolithic main"
```

## Chunk 3: Preserve Analysis Compatibility and Remove Legacy Pressure

### Task 10: Keep Export and Plot Layers Compatible

**Files:**
- Modify: `examples/digital_friction_mvp/export_results.py`
- Modify: `examples/digital_friction_mvp/plot_results.py`
- Modify: `examples/digital_friction_mvp/analysis_parallel_worlds.py`
- Test: `examples/digital_friction_mvp/tests/test_metrics.py`

- [ ] **Step 1: Add fallback field mapping from new proto row names to current analysis field names**

Required compatibility mappings:

- `helplessness_after -> helplessness_score`
- `trust_after -> trust_in_apps`
- `strategy_name -> attempt_strategy`
- `friction_type -> friction_subtype`

- [ ] **Step 2: Keep existing CSV headers valid**

Ensure exports still produce:

- per-agent status tables
- per-attempt CSV rows
- survey delta outputs

- [ ] **Step 3: Run export smoke check**

Run: `python examples/digital_friction_mvp/export_results.py`
Expected: no missing-column crash when proto mode is used.

- [ ] **Step 4: Commit**

```bash
git add examples/digital_friction_mvp/export_results.py \
        examples/digital_friction_mvp/plot_results.py \
        examples/digital_friction_mvp/analysis_parallel_worlds.py
git commit -m "refactor: keep analysis layer compatible with proto outputs"
```

### Task 11: Run Paired-World Validation

**Files:**
- Modify: `examples/digital_friction_mvp/world_runner.py`
- Modify: `examples/digital_friction_mvp/Development_Log.md`

- [ ] **Step 1: Add proto-mode pass-through env var in runner**

```python
env["DIGITAL_PROTO_ENGINE"] = os.getenv("DIGITAL_PROTO_ENGINE", "proto")
```

- [ ] **Step 2: Run one-seed smoke world batch**

Run:

```bash
DIGITAL_PROTO_ENGINE=proto \
python examples/digital_friction_mvp/world_runner.py --n-seeds 1 --summarize
```

Expected:

- all three worlds finish
- metadata files are written
- summary CSV is produced

- [ ] **Step 3: Check research-direction sanity**

Expected directional pattern:

- `high_friction_low_assist` -> higher helplessness delta, lower trust delta
- `low_friction_high_assist` -> lower helplessness delta, higher trust delta

- [ ] **Step 4: Log results in `Development_Log.md`**

Record:

- commit hash
- env flags
- seed(s)
- whether directional hypotheses held
- any missing metrics

- [ ] **Step 5: Commit**

```bash
git add examples/digital_friction_mvp/world_runner.py \
        examples/digital_friction_mvp/Development_Log.md
git commit -m "test: validate proto across paired worlds"
```

### Task 12: Retire or Gate Legacy Monolith Logic

**Files:**
- Modify: `examples/digital_friction_mvp/main.py`
- Modify: `examples/digital_friction_mvp/0129report.md`
- Modify: `examples/digital_friction_mvp/friction_preliminary_design.md`

- [ ] **Step 1: Mark legacy functions as deprecated in comments**

Legacy targets include:

- scenario multi-gate logic embedded in `main.py`
- inline hazard math blocks
- post-step `trigger_event_shocks` outcome mutation

- [ ] **Step 2: Keep rollback path for one milestone**

Do not delete legacy path immediately.  
Support:

- `DIGITAL_PROTO_ENGINE=legacy`
- `DIGITAL_PROTO_ENGINE=proto`

- [ ] **Step 3: Update internal design docs**

State clearly that the new experimental core is:

`task assignment -> attempt strategy -> outcome -> state update -> metrics`

and that “daily life realism” is now secondary to experimental controllability.

- [ ] **Step 4: Commit**

```bash
git add examples/digital_friction_mvp/main.py \
        examples/digital_friction_mvp/0129report.md \
        examples/digital_friction_mvp/friction_preliminary_design.md
git commit -m "docs: deprecate legacy event pipeline and document proto architecture"
```

---

## What Must Be Preserved from AgentSociety

- Preserve the simulation runtime, DB writing, workflow engine, and survey execution.
- Preserve status storage on agent memory.
- Preserve compatibility with `WorkflowStepConfig(type=STEP)` so worlds still advance in the normal AgentSociety loop.
- Preserve enough `current_plan`/`status_summary` fields that downstream scripts do not break abruptly.

## What Should Be Replaced

- Replace hidden multi-stage event gating with explicit task assignment.
- Replace large in-file probability and outcome code with focused pure modules.
- Replace post-step event shock mutation with direct in-forward state update.
- Replace “general life planning” emphasis with “current digital task attempt strategy”.

## Success Criteria

- `main.py` becomes a wiring/configuration entrypoint instead of a 7k-line logic file.
- New prototype logic lives in small files that can be tested without booting the full simulation.
- The prototype can run in three worlds and produce directionally sensible helplessness/trust results.
- The output schema remains analyzable by existing export and plotting scripts.
- The repo supports rollback to legacy mode during transition.

## Risks

- Risk: overriding `forward()` breaks assumptions used by other AgentSociety helpers.
  - Mitigation: keep changes inside example subclass; preserve status keys and workflow outputs.
- Risk: export/plot scripts silently depend on old column names.
  - Mitigation: add compatibility mapping before removing legacy columns.
- Risk: the new simplified loop becomes too detached from “agent behavior”.
  - Mitigation: keep task queue, attempt strategy, and structured outcome explanations rather than direct score injection.
- Risk: no test culture currently exists in repo.
  - Mitigation: use small `unittest`-based pure-function tests first; avoid introducing a new toolchain unless needed.

## Recommended Execution Order

1. Add tests and freeze contracts.
2. Extract pure engines.
3. Add metrics/compatibility layer.
4. Implement new agent `forward()`.
5. Switch workflow hooks in proto mode.
6. Run paired-world validation.
7. Only then deprecate legacy logic.

Plan complete and saved to `docs/superpowers/plans/2026-03-20-digital-helplessness-prototype-refactor.md`. Ready to execute?
