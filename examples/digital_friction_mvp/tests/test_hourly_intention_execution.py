import asyncio
import json

import pytest

from proto.models import AttemptStrategy
import test_agent_help_delivery as help_fixtures
from test_agent_help_delivery import FamilyHelper
from test_app_entry_rollout import _habit, _needs_payload


run_task = help_fixtures.run_task


class ResidentLLM:
    """Record actual prompt packets; select only an ID visible in that packet."""

    def __init__(self):
        self.action = "habitual_app"
        self.app = "communication_social_context"
        self.plans = []
        self.review = None

    async def atext_request(self, *, dialog, **kwargs):
        packet = json.loads(dialog[1]["content"].split("\n", 1)[1])
        if "digital_needs" not in packet:
            return json.dumps(_needs_payload())
        self.plans.append(packet)
        obs = packet["inputs"]
        goal = obs["current_intention"]
        offers = obs["available_opportunities"]
        action = self.action
        targeted = action not in {"no_app", "habitual_app"}
        oid = offers[0]["opportunity_id"] if targeted and not goal and offers else None
        gid = goal["goal_id"] if targeted and goal else None
        channel = self.app
        if action in {"continue_goal", "engage_goal"}:
            channel = (goal or offers[0])["required_channel"]
        target = next((alias for alias, stable_id in packet["targets"].items() if stable_id == (gid or oid)), None)
        token = f"{action}@{target}" if target else action
        if action in {"engage_goal", "continue_goal"}:
            token += f"@open:{channel}"
        if action == "defer_goal" and self.review is not None:
            token += f"@{self.review}"
        if action == "bad_id":
            token = "engage_goal@invisible"
        plan = {
            "action": token,
            "additional_apps": [] if action in {"no_app", "engage_goal", "continue_goal"} else [channel],
            "attitude": 0.7,
            "subjective_norm": 0.5,
            "perceived_control": 0.4,
            "confidence": 0.8,
            "reason": "Controlled offline choice.",
        }
        return json.dumps(plan)


@pytest.fixture
def resident(run_task, monkeypatch, tmp_path):
    agent, data = run_task
    data.update(
        proto_assigned_task_json="",
        proto_app_entry_replay_device_id="fixture",
        proto_app_entry_replay_selected_rank=1,
        proto_day4_replay_snapshot={"schema_version": "fixture"},
        proto_app_entry_habit_memory=_habit(),
    )
    for key, value in {
        "PROTO_TASK_ENTRY_MODE": "app_context_replay_then_llm_rollout",
        "STAGE_MODE": "single",
        "PROTO_HOURLY_INTENTION_MODE": "opportunity_v1",
        "PROTO_SCHEDULED_LOGIN_HOUR": "9",
        "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION": "app_entry_plan_v3",
        "PROTO_TASK_OCCURRENCE_GATE_ENABLED": "false",
        "PROTO_APP_ENTRY_ROLLOUT_JSON_ATTEMPTS": "1",
        "PROTO_LLM_TRACE_DIR": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    llm = ResidentLLM()
    agent._toolbox.llm = llm
    helper = FamilyHelper("enabling")
    agent.set_support_helper_registry({20: helper})

    def step(day, hour, action, *, app="communication_social_context", review=None):
        agent.environment._day, agent.environment._tick_seconds = day, hour * 3600 + 1
        llm.action, llm.app, llm.review = action, app, review
        asyncio.run(agent.forward())

    return step, data, llm, helper


def test_defer_no_app_invalid_and_drop_never_enter_task_or_help(resident, tmp_path):
    step, data, llm, helper = resident
    before = data["helplessness_score"]
    step(3, 9, "defer_goal", review=105)
    goal = data["proto_goal_state_json"]["goal"]
    assert goal["status"] == "deferred" and goal["next_review_at_sim_hour"] == 105
    assert (
        not data["proto_assigned_task_json"]
        and data["proto_last_scheduled_login_day"] == 3
    )
    assert (
        data["proto_app_entry_rollout_rows_json"][-1]["primary_context"]
        == "communication_social_context"
    )
    step(3, 9, "engage_goal")  # repeat the same scheduler tick
    assert len(llm.plans) == 1
    step(3, 10, "no_app")
    assert not llm.plans[-1]["inputs"]["goal_review_due"]
    assert not data["proto_app_entry_rollout_rows_json"][-1]["active"]
    step(4, 9, "bad_id")
    assert data["proto_goal_state_json"]["goal"]["goal_id"] == goal["goal_id"]
    assert (
        data["proto_app_entry_rollout_error_rows_json"][-1]["entry_status"]
        == "llm_rollout_error"
    )
    step(4, 10, "drop_goal")
    assert data["proto_goal_state_json"]["goal"]["status"] == "dropped"
    assert (
        not data["recent_episode_buffer"]
        and not helper.requests
        and data["helplessness_score"] == before
    )
    events = [
        json.loads(line)
        for p in tmp_path.glob("*.jsonl")
        for line in p.read_text().splitlines()
    ]
    choices = [e for e in events if e["kind"] == "hourly_intention"]
    assert [e["executed_choice"] for e in choices] == [
        "defer_goal",
        "no_app",
        None,
        "drop_goal",
    ]
    assert [e["technical_failure"] for e in choices] == [False, False, True, False]
    assert not any(e["module"] in {"strategy", "helper", "outcome"} for e in events)


def test_real_episode_reaches_d5_after_avoid_and_only_a_new_choice_can_retry(
    resident, monkeypatch, tmp_path
):
    import proto.agent as agent_module

    step, data, llm, helper = resident
    calls = []

    def choose(**kwargs):
        calls.append(kwargs)
        return AttemptStrategy("avoid" if len(calls) == 1 else "seek_help_then_attempt")

    monkeypatch.setattr(agent_module, "choose_attempt_strategy", choose)
    step(3, 9, "engage_goal")
    (first,) = data["recent_episode_buffer"]
    assert first["outcome_type"] == "avoid_without_attempt"
    assert (
        data["proto_goal_state_json"]["goal"]["status"] == "needs_review"
        and not data["proto_assigned_task_json"]
    )
    step(3, 10, "habitual_app")
    assert len(calls) == 1 and not helper.requests
    step(4, 9, "continue_goal")
    previous, new = data["recent_episode_buffer"]
    assert new["task_id"] == previous["task_id"] == first["task_id"]
    assert len(calls) == 2 and len(helper.requests) == 1
    assert first["episode_id"] in llm.plans[-1]["inputs"]["related_task_episode_ids"]
    assert first["episode_id"] in [
        r["episode_id"] for r in llm.plans[-1]["inputs"]["recent_task_episodes"]
    ]
    assert data["proto_goal_state_json"]["goal"]["operation_attempt_count"] == 1
    events = [
        json.loads(line)
        for p in tmp_path.glob("*.jsonl")
        for line in p.read_text().splitlines()
    ]
    outcomes = [e for e in events if e["kind"] == "goal_outcome"]
    assert [e["episode_id"] for e in outcomes] == [
        previous["episode_id"],
        new["episode_id"],
    ]
    assert [e["operation_started"] for e in outcomes] == [False, True]


def test_natural_opportunity_reaches_next_plan_then_executes_same_task(
    resident, monkeypatch
):
    step, data, llm, helper = resident
    monkeypatch.delenv("PROTO_SCHEDULED_LOGIN_HOUR")
    step(3, 9, "habitual_app", app="finance_context")
    assert not llm.plans[-1]["inputs"]["available_opportunities"]
    offers = data["proto_goal_state_json"]["opportunities"]
    (natural,) = offers.values()
    assert (
        natural["source"] == "natural_context"
        and natural["visible_from_sim_hour"] == 82
    )
    assert not data["recent_episode_buffer"] and not helper.requests
    step(3, 10, "engage_goal")
    assert (
        llm.plans[-1]["inputs"]["available_opportunities"][0]["opportunity_id"]
        == natural["opportunity_id"]
    )
    assert (
        data["recent_episode_buffer"][-1]["task_id"] == natural["template"]["task_id"]
    )


def test_pending_replay_task_is_visible_but_never_bypasses_choice(resident):
    from proto.models import DigitalTask

    step, data, llm, helper = resident
    old = DigitalTask(
        "D3-old",
        "payment_risk_confirmation",
        "payment_risk_popup",
        0.7,
        "daily_task",
        0.7,
        82801,
        1,
    )
    data.update(
        proto_assigned_task_json=json.dumps(old.to_dict()),
        recent_episode_buffer=[
            {
                "episode_id": "from-D3",
                "task_id": "D3-old",
                "day": 2,
                "tick_seconds": 82801,
                "outcome_type": "avoid_without_attempt",
                "strategy_type": "avoid",
                "task_family": old.task_family,
            }
        ],
    )
    step(3, 9, "no_app")
    obs = llm.plans[0]["inputs"]
    assert len(obs["available_opportunities"]) == 2
    goal = data["proto_goal_state_json"]["goal"]
    assert goal["linked_task_id"] == "D3-old" and obs["current_intention"][
        "last_episode_ids"
    ] == ["from-D3"]
    assert (
        not data["proto_assigned_task_json"]
        and len(data["recent_episode_buffer"]) == 1
        and not helper.requests
    )


def test_helper_transport_failure_preserves_goal_without_making_a_failure_episode(
    resident, tmp_path
):
    step, data, _, helper = resident
    helper.reply = "request_error"
    step(3, 9, "engage_goal")
    assert len(helper.requests) == 1
    assert not data["recent_episode_buffer"] and not data["proto_assigned_task_json"]
    goal = data["proto_goal_state_json"]["goal"]
    assert goal["status"] == "needs_review" and goal["operation_attempt_count"] == 0
    events = [
        json.loads(s)
        for f in tmp_path.glob("*.jsonl")
        for s in f.read_text().splitlines()
    ]
    (result,) = [r for r in events if r["kind"] == "goal_outcome"]
    assert result["status"] == "technical_failure" and result["episode_id"] is None


def test_common_randomness_skips_reference_days_and_uses_actual_strategy_and_outcome_draws(
    run_task,
    monkeypatch,
    tmp_path,
):
    from proto import agent as agent_module
    from proto.attempt_strategy import choose_attempt_strategy
    from proto.hourly_intention import opportunity_id_for_task
    from proto.paired_random import PairedRandomProvider

    agent, data = run_task
    agent.paired_random_provider = PairedRandomProvider(41)
    agent.set_support_helper_registry({20: FamilyHelper("enabling")})
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path))
    prior_task = data["proto_assigned_task_json"]
    agent.environment._day = 2
    asyncio.run(agent.forward())
    agent.environment._day = 3
    data["proto_assigned_task_json"] = prior_task
    monkeypatch.setattr(
        agent_module, "choose_attempt_strategy", choose_attempt_strategy
    )
    asyncio.run(agent.forward())
    rows = [
        json.loads(s)
        for f in tmp_path.glob("*.jsonl")
        for s in f.read_text().splitlines()
    ]
    (streams,) = [r for r in rows if r["kind"] == "paired_streams"]
    assert streams["talkingdata_day"] == 4 and streams["pair_seed"] == 41
    assert streams["opportunity_id"] == opportunity_id_for_task("help-test")
    for sample in (
        r for r in rows if r["kind"] == "sample" and r["talkingdata_day"] == 4
    ):
        assert (
            sample["draw"]
            == agent.paired_random_provider.rng(
                agent.id, streams["opportunity_id"], 1, sample["module"]
            ).random()
        )
